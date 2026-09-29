"""Inert metadata only: no model, source rows, cloud reads or training."""
import json

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import role_audit_bundle as b  # noqa: E402
from app.market_data.projections import TabularProjectionShard  # noqa: E402
from test_transformer_role_provenance import chain  # noqa: E402
from transformer_input_fixtures import frozen_root  # noqa: E402


@pytest.fixture
def bundle(monkeypatch):
    blobs, source, runs = chain()
    root = frozen_root()
    sources = list(root.sources)
    sources[2] = sources[2].model_copy(update={field: getattr(source, field) for field in (
        "source_sha256", "source_manifest_sha256", "parser_config_sha256", "preparation_manifest_sha256")})
    root = root.model_copy(update={"sources": tuple(sources)})
    shards, sequences = [], []
    for s in root.sources:
        if s.fold == "test":
            continue
        for symbol in ("AAPL", "MSFT", "NVDA"):
            base = f"xnas-{s.trade_date}-{symbol.lower()}"
            for run in ([r for r in runs if r.startswith(base)] if s.fold == "validation" else [base + "-control"]):
                count = 307 if s.fold == "validation" else 5575
                shard = TabularProjectionShard(fold=s.fold, base_session_id=base,
                    campaign_id=None if run.endswith("-control") else run, run_id=run,
                    replay_manifest_sha256="f" * 64, supervised_row_count=count,
                    row_identity_sha256="e" * 64, rows=dict(uri=run + ".parquet", sha256="a" * 64,
                        size_bytes=1, logical_name=run, schema_version="tabular_projection_rows_v1"))
                shards.append(shard)
                sequences.append(dict(fold=s.fold, base_session_id=base, campaign_id=shard.campaign_id,
                    run_id=run, replay_manifest_sha256="f" * 64, sequence_count=count,
                    sequence_length=64, sequence_identity_sha256="e" * 64,
                    sequences=dict(uri=run + "-sequence.parquet", sha256="b" * 64, size_bytes=1,
                        logical_name=run, schema_version="causal_feature_sequences_v1")))
    common = dict(access_scope="development", root_release_id=root.release_id,
        root_sha256=root.canonical_hash(), protocol_sha256=root.protocol_sha256,
        corpus_sha256=root.corpus_sha256, assignment_sha256=root.assignment_sha256,
        feature_release_sha256=root.feature_release_sha256, folds=("train", "validation"))
    tab = b.TabularProjectionManifest(projection_id="fixture-tab", shards=shards, **common)
    seq = b.SequenceProjectionManifest(projection_id="fixture-seq", shards=sequences, **common)
    files = {"frozen-root.json": root.canonical_bytes(), "tabular-projection.json": tab.canonical_bytes(),
        "sequence-projection.json": seq.canonical_bytes()}
    monkeypatch.setattr(b, "MANIFESTS", {name: b.digest(raw) for name, raw in files.items()})
    contract = b.InputContract(root=root, tabular_manifest_sha256=b.TABULAR_SHA,
        sequence_manifest_sha256=b.SEQUENCE_SHA, training_shards=tuple(sorted(
            (s for s in shards if s.fold == "train"), key=b.baseline_order)))
    files["normalization.json"] = b.Normalization(training_binding_sha256=contract.training_binding(),
        fitting_row_sha256="c" * 64, fitting_rows=33450, observed_counts=(0,) * 60,
        means=(0.,) * 60, scales=(1.,) * 60).canonical_bytes()
    config = b.configuration()
    config["inputs"]["normalization_sha256"] = b.digest(files["normalization.json"])
    monkeypatch.setattr(b, "configuration", lambda: config)
    receipts = []
    for name, key in zip(b.METADATA_NAMES, b.metadata_keys(), strict=True):
        files[name] = blobs[key]
        receipts.append(dict(key=key, version_id="1", size_bytes=len(blobs[key]), sha256=b.digest(blobs[key])))
    files["receipts.json"] = b.canonical(receipts)
    monkeypatch.setattr(b, "RECEIPTS_SHA", b.digest(files["receipts.json"]))
    return dict(schema_version="transformer_role_audit_bundle_v1", campaign_sha256=b.configuration_sha256(),
        files={name: raw.decode() for name, raw in files.items()})


def test_verified_bundle_retains_all_readiness_gates(bundle):
    result = b.verify(b.canonical(bundle))
    assert result["metadata_chain_verified"] and result["training_binding_verified"]
    assert result["metadata_objects"] == 29
    assert not any(result[k] for k in ("gpu_ready", "source_separation_verified", "execution_authorized"))
    assert result["payload_reads"] == result["model_runs"] == 0


@pytest.mark.parametrize("name", sorted(b.NAMES))
def test_every_evidence_file_is_independently_bound(bundle, name):
    bundle["files"][name] += " "
    with pytest.raises(ValueError):
        b.verify(b.canonical(bundle))


@pytest.mark.parametrize("defect", ["missing", "extra", "campaign", "schema", "value", "large"])
def test_rejects_inventory_or_envelope_changes(bundle, defect):
    if defect == "missing":
        bundle["files"].pop("metadata-00.json")
    elif defect == "extra":
        bundle["files"]["../payload.parquet"] = "unapproved"
    elif defect == "campaign":
        bundle["campaign_sha256"] = "0" * 64
    elif defect == "schema":
        bundle["schema_version"] = "other"
    elif defect == "value":
        bundle["files"]["metadata-00.json"] = None
    else:
        bundle["files"]["metadata-00.json"] = "x" * (b.MAX_FILE + 1)
    with pytest.raises(ValueError):
        b.verify(b.canonical(bundle))


def test_rejects_ambiguous_or_oversized_json(bundle):
    raw = b.canonical(bundle)
    for altered in (raw + b"\n", b'{"files":{},' + raw[1:], b" " * (b.MAX_BUNDLE + 1), b"null"):
        with pytest.raises(ValueError):
            b.verify(altered)


def test_rechecks_training_binding_even_with_valid_normalizer_checksum(bundle, monkeypatch):
    value = json.loads(bundle["files"]["normalization.json"])
    value["training_binding_sha256"] = "0" * 64
    raw = b.canonical(value)
    bundle["files"]["normalization.json"] = raw.decode()
    b.configuration()["inputs"]["normalization_sha256"] = b.digest(raw)
    with pytest.raises(ValueError, match="training release"):
        b.verify(b.canonical(bundle))


def test_packaging_is_deterministic_and_never_overwrites(tmp_path, bundle):
    inputs, metadata = tmp_path / "inputs", tmp_path / "metadata"
    (inputs / "manifests").mkdir(parents=True)
    metadata.mkdir()
    for name, value in bundle["files"].items():
        base = inputs / "manifests" if name in b.MANIFESTS else metadata
        (base / name).write_text(value)
    output = tmp_path / "bundle.json"
    result = b.prepare(inputs, metadata, metadata / "normalization.json", output)
    assert result == b.verify(output.read_bytes()) and output.read_bytes() == b.canonical(bundle)
    with pytest.raises(FileExistsError):
        b.prepare(inputs, metadata, metadata / "normalization.json", output)
    assert output.read_bytes() == b.canonical(bundle)
    (metadata / "metadata-00.json").write_bytes(b"x" * (b.MAX_FILE + 1))
    with pytest.raises(ValueError, match="byte bound"):
        b.prepare(inputs, metadata, metadata / "normalization.json", tmp_path / "failed.json")
    assert not (tmp_path / "failed.json").exists()
