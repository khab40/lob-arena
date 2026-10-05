import io
import time
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

np = pytest.importorskip("numpy")

from app.market_data.projections import supervised_row_id  # noqa: E402
from app.ml.transformer.holdout_metrics import fixed_comparison, paired_bootstrap  # noqa: E402
from app.ml.transformer.holdout_readback import verify_result  # noqa: E402
from app.ml.transformer.holdout_spec import G8_PREFIX, object_location  # noqa: E402
from app.ml.transformer.holdout_storage import HoldoutStore  # noqa: E402
from app.ml.transformer.settings_release import ArtifactRead  # noqa: E402
from app.ml.transformer.verification_spec import canonical, digest  # noqa: E402
from transformer_holdout_fixtures import FakeS3, final_inputs, reference, request  # noqa: E402
from test_transformer_holdout_metrics import release  # noqa: E402


def publication(tmp_path, monkeypatch):
    _, _, contract, args, _ = final_inputs(tmp_path)
    import json
    tabular = json.loads(args["tabular_path"].read_bytes())
    template = tabular["shards"][0]
    ledger, saved, shards, families, symbols = [], [], [], [], []
    # Declared metadata only, matching protocol counts; no market feed or model.
    for symbol_index, symbol in enumerate(("AAPL", "MSFT", "NVDA")):
        for domain_index in range(10):
            session = "2019-12-30-" + symbol.lower()
            run = session + "-" + str(domain_index)
            campaign = run if domain_index else None
            count = 506 if symbol_index == 2 else 505  # 15,160 declared observations.
            targets = []
            for index in range(count):
                seq, timestamp = index + 1, index * 100
                target = supervised_row_id(root_sha256=contract.root.canonical_hash(),
                    assignment_sha256=contract.root.assignment_sha256,
                    replay_sha256="b" * 64, run_id=run, sequence=seq, timestamp_ns=timestamp)
                targets.append(target)
                label = int(domain_index != 0 and index < 5)
                row = {"target_id": target, "label": label, "run_id": run, "base_session_id": session,
                       "campaign_id": campaign, "prediction_timestamp_ns": timestamp}
                ledger.append(row)
                probability = .9 if label else .1
                family = "wall" if campaign else "control"
                families.append(family)
                symbols.append(symbol)
                saved.append({"fold": "test", "run_id": run, "base_session_id": session, "campaign_id": campaign,
                    "prediction_row_id": digest(f"{run}|{timestamp}|{seq}".encode()),
                    "sequence": seq, "prediction_timestamp_ns": timestamp, "label": label,
                    "calibrated_probability": probability, "threshold": .5769230769230769,
                    "alert": bool(label), "attack_family": family, "instrument": symbol})
            shards.append({**template, "run_id": run, "base_session_id": session, "campaign_id": campaign,
                "supervised_row_count": count, "row_identity_sha256": digest(
                    "".join(target + "\n" for target in targets).encode()),
                "rows": {**template["rows"], "uri": run + ".parquet"}})
    tabular["shards"] = shards
    tab_raw = canonical(tabular)
    output = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(saved), output)
    baseline_raw = output.getvalue()
    items = [reference("tabular.json", tab_raw), reference("sequence.json", b"sequence metadata"),
             reference("baseline.parquet", baseline_raw, uri=G8_PREFIX + "predictions.parquet")]
    req, envelope, gate, saved_reference = request(items)
    s3 = FakeS3()
    for item, raw in zip(items, (tab_raw, b"sequence metadata", baseline_raw), strict=True):
        s3.objects[object_location(item.reference)] = raw
    s3.objects[object_location(req.input("reference.json").reference)] = saved_reference
    settings = release()
    settings.lineage = SimpleNamespace(root_sha256=contract.root.canonical_hash())
    settings.artifacts = SimpleNamespace(contract=SimpleNamespace(size_bytes=len(contract.canonical_bytes())),
        selection_verification=SimpleNamespace(size_bytes=38))
    settings.canonical_bytes = lambda: b"declared settings"
    settings.sha256 = lambda: req.settings_sha256
    monkeypatch.setattr("app.ml.transformer.holdout_readback.load_release", lambda *a, **k: settings)
    monkeypatch.setattr("app.ml.transformer.holdout_readback.checked_read",
        lambda ref, reader: contract.canonical_bytes() if ref is settings.artifacts.contract
        else canonical({"result": {"bindings": {"original": True}}}))
    logits = np.asarray([3. if row["label"] else -3. for row in ledger])
    baseline = np.asarray([row["calibrated_probability"] for row in saved])
    comparison, probability = fixed_comparison(ledger, logits, baseline, families, symbols, settings)
    comparison["bootstrap"] = paired_bootstrap(ledger, logits, baseline, settings)
    predictions = [{**row, "logit": float(z), "probability": float(p), "baseline_probability": float(b),
                    "family": family, "symbol": symbol} for row, z, p, b, family, symbol in
                   zip(ledger, logits, probability, baseline, families, symbols, strict=True)]
    result = {"request_sha256": req.sha256(), "job_id": gate.job_id, "settings_sha256": settings.sha256(),
        "context": envelope["context"], "parity": gate.parity, "comparison": comparison,
        "final_test_access": True, "fitting": False, "baseline_rescored": False,
        "original_checkpoint_bindings": {"original": True},
        "measurements": {"elapsed_seconds": 1.25, "batch_size": 64, "rows": len(ledger),
            "peak_gpu_allocated_bytes": 1024, "peak_gpu_reserved_bytes": 2048,
            "includes_host_to_device": True, "lightgbm_latency": "not_measured_saved_predictions_reused",
            "ordered_targets_sha256": digest(canonical([row["target_id"] for row in ledger]))},
        "execution_bindings": {"source_commit": req.source_commit, "image_digest": req.image_digest,
            "tabular_sha256": items[0].reference.sha256, "sequence_sha256": items[1].reference.sha256}}
    store = HoldoutStore(s3, req, expires=time.monotonic() + 60)
    for name, value in (("execution-context.json", envelope), ("reference-parity.json", gate.parity),
                        ("predictions.json", predictions), ("target-ledger.json", ledger)):
        store.put(name, canonical(value))
    return store, settings, result


@pytest.mark.parametrize("defect", [None, "metric", "baseline_flag", "original_binding", "execution_binding",
                                  "missing_measurements", "elapsed", "rows", "targets", "gpu_memory"])
def test_independent_end_to_end_readback_of_declared_artifacts(tmp_path, monkeypatch, defect):
    store, settings, result = publication(tmp_path, monkeypatch)
    if defect == "metric":
        result["comparison"]["modes"]["balanced"]["transformer"]["fp"] += 1
    elif defect == "baseline_flag":
        result["baseline_rescored"] = True
    elif defect == "original_binding":
        result["original_checkpoint_bindings"] = {}
    elif defect == "execution_binding":
        result["execution_bindings"]["source_commit"] = "0" * 40
    elif defect == "missing_measurements":
        del result["measurements"]
    elif defect == "elapsed":
        result["measurements"]["elapsed_seconds"] = -1
    elif defect == "rows":
        result["measurements"]["rows"] -= 1
    elif defect == "targets":
        result["measurements"]["ordered_targets_sha256"] = "0" * 64
    elif defect == "gpu_memory":
        result["measurements"]["peak_gpu_reserved_bytes"] = 1
    success = store.finish(result)
    args = dict(approved_request_sha256=store.request.sha256(),
                trusted_public_key=store.request.context_public_key, settings_reader=lambda ref: ArtifactRead(b"", "1"))
    if defect:
        with pytest.raises(ValueError):
            verify_result(store, success, settings, **args)
    else:
        receipt = verify_result(store, success, settings, **args)
        assert receipt["status"] == "verified" and receipt["rows"] == 15160
        assert receipt["model_execution"] is False
        assert receipt["measurements_verified"] is True
