"""Independent hash, authorization, row-pairing and arithmetic readback; no model."""
from dataclasses import dataclass
import io

import numpy as np
import pyarrow.parquet as pq

from app.market_data.projections import TabularProjectionManifest

from .holdout_baseline import pair_saved_predictions
from .holdout_context import check_parity, verify_context
from .holdout_metrics import fixed_comparison, paired_bootstrap
from .research_comparison_readback import arithmetic_matches
from .settings_release import checked_read, json_record, load_release
from .holdout_worker import TRUST
from .verification_spec import canonical, digest


@dataclass
class SavedPopulation:
    root: object
    tabular: object
    rows: list

    def ledger(self):
        return iter(self.rows)


def verify_result(store, success, release, *, approved_request_sha256, trusted_public_key, settings_reader):
    request = store.request
    release = load_release(release.canonical_bytes(), settings_reader,
                           expected_sha256=request.settings_sha256, **TRUST)
    from .contracts import InputContract
    root = InputContract.model_validate_json(checked_read(release.artifacts.contract, settings_reader)).root
    original = json_record(checked_read(release.artifacts.selection_verification, settings_reader))["result"]["bindings"]
    files, inventory = store.reconcile(success)
    if set(files) != {"execution-context.json", "reference-parity.json",
                      "predictions.json", "target-ledger.json", "result.json"}:
        raise ValueError("incomplete holdout publication")
    envelope = json_record(files["execution-context.json"])
    context = verify_context(request, envelope, approved_request_sha256=approved_request_sha256,
                             trusted_public_key=trusted_public_key)
    parity = json_record(files["reference-parity.json"])
    reference = store.input(request.input(request.reference_logits_path)).data
    gate = check_parity(request, context, reference, parity["target_ids"], parity["labels"], parity["actual_logits"])
    if canonical(gate.parity) != canonical(parity):
        raise ValueError("saved reference parity differs from independent calculation")
    raw = store.input(request.input(request.tabular_path), gate).data
    tabular = TabularProjectionManifest.model_validate_json(raw)
    if (tabular.access_scope != "final_test" or tabular.root_sha256 != root.canonical_hash()
            or tabular.assignment_sha256 != root.assignment_sha256
            or tabular.feature_release_sha256 != root.feature_release_sha256
            or tabular.protocol_sha256 != root.protocol_sha256
            or tabular.corpus_sha256 != root.corpus_sha256 or tabular.root_release_id != root.release_id):
        raise ValueError("independent final manifest lineage differs")
    result = json_record(files["result.json"])
    ledger = json_record(files["target-ledger.json"])
    predictions = json_record(files["predictions.json"])
    if (result["request_sha256"] != request.sha256() or result["job_id"] != context["job_id"]
            or result["settings_sha256"] != release.sha256() or result["context"] != context
            or result["parity"] != parity or result["final_test_access"] is not True
            or result["fitting"] is not False or result["baseline_rescored"] is not False
            or result["original_checkpoint_bindings"] != original
            or len(predictions) != len(ledger) or len({r["target_id"] for r in ledger}) != len(ledger)
            or root.canonical_hash() != release.lineage.root_sha256):
        raise ValueError("holdout result lineage or population differs")
    saved = [row for path in request.baseline_paths
             for row in pq.read_table(io.BytesIO(store.input(request.input(path), gate).data)).to_pylist()]
    population = SavedPopulation(root, tabular, ledger)
    _, baseline, families, symbols = pair_saved_predictions(population, saved)
    if (len(ledger) != 15160 or sum(row["label"] for row in ledger) != 135
            or set(symbols) != {"AAPL", "MSFT", "NVDA"} or len(tabular.shards) != 30
            or len({row["base_session_id"] for row in ledger}) != 3
            or len({row["campaign_id"] for row in ledger if row["campaign_id"]}) != 27
            or any("2019-12-30" not in row["base_session_id"] for row in ledger)):
        raise ValueError("independent December population differs")
    for shard in tabular.shards:
        ids = [r["target_id"] for r in ledger if r["run_id"] == shard.run_id]
        if (len(ids) != shard.supervised_row_count
                or digest("".join(target + "\n" for target in ids).encode()) != shard.row_identity_sha256):
            raise ValueError("readback row ledger differs from frozen manifest")
    execution = result["execution_bindings"]
    if execution != {"source_commit": request.source_commit, "image_digest": request.image_digest,
                     "tabular_sha256": request.input(request.tabular_path).reference.sha256,
                     "sequence_sha256": request.input(request.sequence_path).reference.sha256}:
        raise ValueError("readback execution bindings differ")
    logits = [row["logit"] for row in predictions]
    for row, expected, p, family, symbol in zip(predictions, ledger, baseline, families, symbols, strict=True):
        if ({key: row[key] for key in expected} != expected or row["baseline_probability"] != p
                or row["family"] != family or row["symbol"] != symbol):
            raise ValueError("published predictions differ from exact paired baseline")
    comparison, probabilities = fixed_comparison(ledger, logits, baseline, families, symbols, release)
    comparison["bootstrap"] = paired_bootstrap(ledger, logits, baseline, release)
    if (not np.array_equal(probabilities, np.asarray([r["probability"] for r in predictions]))
            or not arithmetic_matches(result["comparison"], comparison)):
        raise ValueError("saved holdout metrics differ from independent arithmetic")
    return {"status": "verified", "request_sha256": request.sha256(), "job_id": context["job_id"],
        "rows": len(ledger), "result_sha256": digest(files["result.json"]), "inventory": inventory,
        "model_execution": False, "baseline_rescored": False, "production_qualified": False,
        "arithmetic_policy": "named_float64_reductions_max_8_ulp"}
