"""Inference-only holdout orchestration; cloud submission is a separate gate."""
import io
from pathlib import Path
import time

import pyarrow.parquet as pq

from .contracts import InputContract, Normalization
from .data import DevelopmentInputs
from .holdout_baseline import pair_saved_predictions
from .holdout_context import check_parity, verify_context
from .holdout_data import HoldoutInputs
from .holdout_metrics import fixed_comparison, paired_bootstrap
from .holdout_storage import HoldoutStore
from .holdout_spec import TRUST
from .role_deadline import deadline
from .settings_release import ArtifactRead, checked_read, json_record, load_release
from .verification_spec import canonical, digest

def retain(directory, item, raw):
    path = directory / item.path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    return path


def execute(s3, request, package_raw, envelope, *, approved_request_sha256, trusted_public_key,
            work, source_commit, consumer_factory=None):
    if (source_commit != request.source_commit or len(package_raw) > 512 * 1024
            or digest(package_raw) != request.package_sha256):
        raise ValueError("holdout image source or sealed package differs")
    context = verify_context(request, envelope, approved_request_sha256=approved_request_sha256,
                             trusted_public_key=trusted_public_key)
    package = json_record(package_raw)
    if set(package) != {"settings", "evidence"}:
        raise ValueError("invalid holdout package")
    expires = time.monotonic() + request.timeout_seconds
    store = HoldoutStore(s3, request, expires=expires)
    work = Path(work)
    work.mkdir(parents=True, exist_ok=False)
    stage = "claim"
    with deadline(request.timeout_seconds):
        store.claim()
        try:
            store.put("execution-context.json", canonical(envelope))
            stage = "development_inputs"
            for item in request.inputs:
                if item.scope == "development":
                    retain(work, item, store.input(item).data)

            def reader(ref):
                if ref.uri.startswith("evidence:sha256:"):
                    return ArtifactRead(bytes.fromhex(package["evidence"][ref.uri]), "content-addressed")
                item = next(item for item in request.inputs if item.reference == ref and item.scope == "development")
                path = work / item.path
                if path.stat().st_size != ref.size_bytes:
                    raise ValueError("retained settings artifact changed")
                return ArtifactRead(path.read_bytes(), ref.version_id)

            release = load_release(package["settings"].encode(), reader,
                                   expected_sha256=request.settings_sha256, **TRUST)
            release.require_research_inference()
            contract = InputContract.model_validate_json(checked_read(release.artifacts.contract, reader))
            normalizer = Normalization.model_validate_json(checked_read(release.artifacts.normalization, reader))
            dataset = DevelopmentInputs.open(root=contract.root, artifact_root=work,
                tabular_path=work / "development-tabular.json", tabular_sha256=contract.tabular_manifest_sha256,
                sequence_path=work / "development-sequences.json", sequence_sha256=contract.sequence_manifest_sha256)
            if dataset.contract.canonical_bytes() != contract.canonical_bytes():
                raise ValueError("development parity contract differs from checkpoint")
            for shard in dataset.tabular.shards:
                allowed = ("2019-01-30", "2019-03-27") if shard.fold == "train" else ("2019-10-30",)
                if ("2019-12-30" in shard.base_session_id + shard.run_id
                        or not any(day in shard.base_session_id and day in shard.run_id for day in allowed)):
                    raise ValueError("consumed development inventory lacks chronological exclusion proof")
            checkpoint = next(item for item in request.inputs if item.reference == release.artifacts.checkpoint)
            selection = json_record(checked_read(release.artifacts.selection_verification, reader))
            stage = "reference_parity"
            if consumer_factory is None:
                from .holdout_gpu import FixedGpuConsumer
                consumer_factory = FixedGpuConsumer
            consumer = consumer_factory(release, work / checkpoint.path, selection["result"]["bindings"], expires=expires)
            reference = (work / request.reference_logits_path).read_bytes()
            targets = tuple(row["target_id"] for row in json_record(reference))
            ids, labels, logits = consumer.infer(dataset, normalizer, targets=targets)
            gate = check_parity(request, context, reference, ids, labels, logits)
            store.put("reference-parity.json", canonical(gate.parity))
            stage = "final_inputs"
            for item in request.inputs:
                if item.scope == "final_test":
                    retain(work, item, store.input(item, gate).data)
            holdout = HoldoutInputs.open(request=request, gate=gate, contract=contract, artifact_root=work)
            saved = [row for path in request.baseline_paths
                     for row in pq.read_table(io.BytesIO((work / path).read_bytes())).to_pylist()]
            ledger, baseline, families, symbols = pair_saved_predictions(holdout, saved)
            if (len(ledger) != 15160 or sum(row["label"] for row in ledger) != 135
                    or set(symbols) != {"AAPL", "MSFT", "NVDA"}
                    or len({row["base_session_id"] for row in ledger}) != 3
                    or len({row["campaign_id"] for row in ledger if row["campaign_id"]}) != 27
                    or len(holdout.tabular.shards) != 30
                    or any("2019-12-30" not in row["base_session_id"] for row in ledger)):
                raise ValueError("December population differs from locked protocol")
            stage = "holdout_inference"
            ids, labels, logits = consumer.infer(holdout, normalizer)
            if ids != tuple(row["target_id"] for row in ledger) or labels != tuple(row["label"] for row in ledger):
                raise ValueError("inference output identity or label differs")
            comparison, probabilities = fixed_comparison(ledger, logits, baseline, families, symbols, release)
            comparison["bootstrap"] = paired_bootstrap(ledger, logits, baseline, release)
            predictions = [{**row, "logit": float(logit), "probability": float(p),
                "baseline_probability": float(b), "family": family, "symbol": symbol}
                for row, logit, p, b, family, symbol in
                zip(ledger, logits, probabilities, baseline, families, symbols, strict=True)]
            store.put("predictions.json", canonical(predictions))
            store.put("target-ledger.json", canonical(ledger))
            result = {"schema_version": "transformer_holdout_result_v1", "request_sha256": request.sha256(),
                "job_id": gate.job_id, "settings_sha256": release.sha256(), "context": context,
                "parity": gate.parity, "comparison": comparison, "measurements": consumer.measurements,
                "final_test_access": True, "fitting": False, "baseline_rescored": False,
                "mlflow": "pending_reconciliation", "original_checkpoint_bindings": selection["result"]["bindings"],
                "execution_bindings": {"source_commit": source_commit, "image_digest": request.image_digest,
                                       "tabular_sha256": request.input(request.tabular_path).reference.sha256,
                                       "sequence_sha256": request.input(request.sequence_path).reference.sha256}}
            return store.finish(result)
        except Exception as error:
            from .role_execution_transport import PublicationUncertain
            if not isinstance(error, PublicationUncertain) and time.monotonic() < expires:
                store.put("FAILED", canonical({"stage": stage, "error_type": type(error).__name__,
                                              "request_sha256": request.sha256()}), artifact=False)
            raise
