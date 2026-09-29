import json
from io import BytesIO
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import role_provenance as p  # noqa: E402
from app.ml.transformer import role_provenance_transport as t  # noqa: E402
from app.ml.transformer.verification_spec import canonical, digest  # noqa: E402


def chain():
    blobs, refs, runs, controls, datasets = {}, [], [], {}, {}
    payload = dict(payload_inventory_sha256="a" * 64, payload_file_count=1, payload_size_bytes=1)
    for symbol in p.SYMBOLS:
        base = f"xnas-{p.DATE}-{symbol.lower()}"
        controls[symbol] = base + "-control"
        datasets[symbol] = dict(dataset_id=base, source_type="nasdaq_itch", symbol=symbol,
            trade_date=p.DATE, start_time_ms=1, end_time_ms=2, depth=10, row_count=1,
            event_counts={}, imported_at="2026-09-28T00:00:00Z", source_files=[], output_files=[],
            source_stream_sha256="b" * 64, parser_config_sha256="c" * 64)
    records = [dict(schema_version="market_data_normalized_checkpoint_v2",
        binding_sha256="d" * 64, manifests=datasets, **payload)]
    for number, (symbol, family, seed) in p.COMPARISONS:
        run = f"xnas-{p.DATE}-{symbol.lower()}-{family}-s{seed}"
        runs.append(run)
        records.append(dict(schema_version="market_data_comparison_checkpoint_v2",
            binding_sha256="d" * 64, comparison_number=number, symbol=symbol,
            attack_family=family, seed=seed, control_run_id=controls[symbol],
            control_event_stream_sha256="e" * 64, hybrid_run_id=run,
            hybrid_event_stream_sha256="f" * 64, includes_control_artifacts=seed == 41,
            repeat_determinism_verified=True, **payload))
    for index, (key, record) in enumerate(zip(p.checkpoint_keys(), records, strict=True)):
        blobs[key] = canonical(record)
        refs.append(dict(kind="normalized" if index == 0 else "comparison",
            uri=f"s3://{p.INPUT_BUCKET}/{key.removesuffix('/checkpoint.json')}",
            checkpoint_sha256=digest(blobs[key]), **payload))
    prep = dict(run_id=p.PREPARATION_RUN, source_filename="10302019.NASDAQ_ITCH50.gz",
        source_sha256="1" * 64, source_manifest_sha256="2" * 64, parser_version="fixture",
        parser_config_sha256="c" * 64, itch_message_counts={}, system_event_count=1,
        symbols=list(p.SYMBOLS), dataset_ids={s: d["dataset_id"] for s, d in datasets.items()},
        control_run_ids=controls, campaign_run_ids=runs, checkpoint_binding_sha256="d" * 64,
        normalized_checkpoint=refs[0], comparison_checkpoints=refs[1:],
        checkpoint_payload_bytes=28, created_at="2026-09-28T00:00:00Z")
    blobs[p.PREPARATION_KEY] = canonical(prep)
    source = NS(fold="validation", trade_date=p.DATE, filename=prep["source_filename"],
        source_sha256=prep["source_sha256"], source_manifest_sha256=prep["source_manifest_sha256"],
        parser_config_sha256=prep["parser_config_sha256"],
        preparation_manifest_sha256=digest(blobs[p.PREPARATION_KEY]))
    return blobs, source, runs + list(controls.values())


def alter_preparation(blobs, source, mutate):
    prepared = json.loads(blobs[p.PREPARATION_KEY])
    mutate(prepared)
    blobs[p.PREPARATION_KEY] = canonical(prepared)
    source.preparation_manifest_sha256 = digest(blobs[p.PREPARATION_KEY])


def alter_checkpoint(blobs, source, index, mutate):
    key = p.checkpoint_keys()[index]
    record = json.loads(blobs[key])
    mutate(record)
    blobs[key] = canonical(record)
    def rebind(prepared):
        ref = prepared["normalized_checkpoint"] if index == 0 else prepared["comparison_checkpoints"][index - 1]
        ref["checkpoint_sha256"] = digest(blobs[key])
    alter_preparation(blobs, source, rebind)


def test_verified_metadata_never_claims_source_separation():
    result = p.verify_chain(*chain())
    assert result["metadata_objects"] == 29 and len(result["replay_event_streams"]) == 30
    assert result["metadata_chain_verified"]
    assert not result["gpu_ready"] and not result["source_separation_verified"]


@pytest.mark.parametrize("defect", ["missing", "extra", "prep_hash", "checkpoint_hash", "final", "runs"])
def test_unbound_or_incomplete_metadata_fails(defect):
    blobs, source, runs = chain()
    if defect == "missing":
        blobs.pop(p.checkpoint_keys()[-1])
    elif defect == "extra":
        blobs["unreviewed"] = b"{}"
    elif defect == "prep_hash":
        blobs[p.PREPARATION_KEY] += b" "
    elif defect == "checkpoint_hash":
        blobs[p.checkpoint_keys()[1]] += b" "
    elif defect == "final":
        source.fold = "test"
    else:
        runs[-1] = runs[0]
    with pytest.raises(ValueError):
        p.verify_chain(blobs, source, runs)


@pytest.mark.parametrize("field,value", [("source_sha256", "9" * 64), ("symbols", ["AAPL"]),
    ("run_id", "another-run"), ("control_run_ids", {}), ("campaign_run_ids", [])])
def test_hash_valid_preparation_still_checks_semantics(field, value):
    blobs, source, runs = chain()
    alter_preparation(blobs, source, lambda r: r.update({field: value}))
    with pytest.raises(ValueError):
        p.verify_chain(blobs, source, runs)


@pytest.mark.parametrize("field,value", [("binding_sha256", "9" * 64),
    ("payload_size_bytes", 2), ("symbol", "NVDA"), ("seed", 43),
    ("hybrid_run_id", "unrelated"), ("control_event_stream_sha256", "9" * 64)])
def test_hash_valid_checkpoint_still_checks_semantics(field, value):
    blobs, source, runs = chain()
    alter_checkpoint(blobs, source, 2, lambda r: r.update({field: value}))
    with pytest.raises(ValueError):
        p.verify_chain(blobs, source, runs)


def test_normalized_source_domain_must_match():
    blobs, source, runs = chain()
    alter_checkpoint(blobs, source, 0,
        lambda r: r["manifests"]["AAPL"].update(trade_date="2019-12-30"))
    with pytest.raises(ValueError, match="source domain"):
        p.verify_chain(blobs, source, runs)


class S3:
    def __init__(self, blobs):
        self.blobs, self.calls = blobs, []

    def get_object(self, **args):
        assert args["Bucket"] == p.INPUT_BUCKET
        self.calls.append(args["Key"])
        raw = self.blobs[args["Key"]]
        return dict(Body=BytesIO(raw), ContentLength=len(raw), VersionId="1")


def bind_local_metadata(monkeypatch, source, runs):
    monkeypatch.setattr(t, "load_metadata", lambda _: (NS(sources=[source],
        canonical_hash=lambda: "0" * 64), NS(shards=[NS(fold="validation", run_id=r) for r in runs]), None))


def test_collector_retains_versions_and_complete_report(tmp_path, monkeypatch):
    blobs, source, runs = chain()
    bind_local_metadata(monkeypatch, source, runs)
    s3 = S3(blobs)
    result = t.collect(s3, tmp_path, tmp_path / "out")
    assert s3.calls == p.metadata_keys() and result["metadata_chain_verified"]
    receipts = json.loads((tmp_path / "out/receipts.json").read_bytes())
    assert len(receipts) == 29 and all(r["version_id"] == "1" for r in receipts)
    assert result["object_receipts_sha256"] == digest(canonical(receipts))


def test_reference_escape_rejected_before_checkpoint_get(tmp_path, monkeypatch):
    blobs, source, runs = chain()
    alter_preparation(blobs, source, lambda r: r["normalized_checkpoint"].update(uri="s3://elsewhere/data"))
    bind_local_metadata(monkeypatch, source, runs)
    s3 = S3(blobs)
    with pytest.raises(ValueError, match="allowlist"):
        t.collect(s3, tmp_path, tmp_path / "out")
    assert s3.calls == [p.PREPARATION_KEY]
    assert (tmp_path / "out/failure.json").exists()
    assert not (tmp_path / "out/provenance.json").exists()


@pytest.mark.parametrize("size,version", [(0, "1"), (t.MAX_OBJECT + 1, "1"), (2, "1"), (1, None), (1, "null")])
def test_invalid_response_is_bounded_and_closed(size, version):
    body = BytesIO(b"x")
    s3 = NS(get_object=lambda **_: dict(Body=body, ContentLength=size, VersionId=version))
    with pytest.raises(ValueError):
        t.read_metadata(s3, p.PREPARATION_KEY)
    assert body.closed
