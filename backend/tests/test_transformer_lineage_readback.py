import json
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import lineage_readback as r, lineage_transport as t  # noqa: E402
from app.ml.transformer.lineage_inventory import REQUEST_KEY, phase_keys, run_members  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402
from transformer_lineage_fixtures import fixture  # noqa: E402
from transformer_semantics_fixtures import fixture as semantic_fixture  # noqa: E402
from test_transformer_lineage_transport import S3  # noqa: E402


@pytest.fixture
def phases(tmp_path, monkeypatch):
    anchor, blobs = fixture()
    monkeypatch.setattr(t, "context", lambda _: anchor)
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b"inert")
    first, second = tmp_path / "first", tmp_path / "second"
    client = S3(blobs)
    t.collect(client, bundle, 1, first)
    t.collect(client, bundle, 2, second, first)
    return anchor, first, second


def test_offline_readback_authenticates_all_115_objects(phases):
    anchor, first, second = phases
    one, inventories, receipt = r.phase_readback(anchor, 1, first)
    two, _, other = r.phase_readback(anchor, 2, second, inventories)
    assert len(one) == receipt["authenticated_objects"] == 58
    assert len(two) == other["authenticated_objects"] == 57


@pytest.mark.parametrize("phase,filename", [(1, "metadata-00.json"), (1, "metadata-01.json"),
    (1, "metadata-57.json"), (2, "metadata-00.json"), (2, "metadata-56.json"),
    (1, "receipts.json"), (2, "receipts.json"), (1, "verification.json"), (2, "verification.json")])
def test_changed_retained_evidence_cannot_pass(phases, phase, filename):
    anchor, first, second = phases
    (first if phase == 1 else second).joinpath(filename).write_bytes(b"{}")
    with pytest.raises(ValueError):
        _, inventories, _ = r.phase_readback(anchor, 1, first)
        r.phase_readback(anchor, 2, second, inventories)


def test_full_domain_semantics_keeps_remaining_gates_closed(tmp_path, monkeypatch):
    # Authentication is exercised above; isolate frozen-model setup here.
    anchor, request_blobs = fixture()
    anchor["prepared"].dataset_ids = dict.fromkeys(("AAPL", "MSFT", "NVDA"), "fixture-dataset")
    blobs, inventories, shards = {REQUEST_KEY: request_blobs[REQUEST_KEY]}, {}, []
    for index, member in enumerate(run_members()):
        _, raw, inventory = semantic_fixture(index)
        blobs.update(raw)
        inventories.setdefault(member["prefix"], {}).update(inventory[member["prefix"]])
        shards.append(NS(run_id=member["run_id"], fold="validation", replay_manifest_sha256="a" * 64,
            base_session_id=member["base_session_id"], campaign_id=member["run_id"] if member["mode"] == "hybrid" else None))
    files = {name: "{}" for name in (*r.METADATA_NAMES, "frozen-root.json", "tabular-projection.json")}
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(canonical(dict(files=files)))
    monkeypatch.setattr(r, "context", lambda _: anchor)
    config_sha = json.loads(blobs[run_members()[0]["feature_key"]])["feature_config_hash"]
    monkeypatch.setattr(r, "FrozenPublicSampleRoot", NS(model_validate_json=lambda _: NS(feature_config_sha256=config_sha)))
    monkeypatch.setattr(r, "TabularProjectionManifest", NS(model_validate_json=lambda _: NS(shards=shards)))
    monkeypatch.setattr(r, "verify_chain", lambda *_: dict(replay_event_streams={s.run_id: "a" * 64 for s in shards}))
    # SUCCESS bytes are needed only by the independently tested authenticator.
    blobs.update({key: b"{}" for key in phase_keys(1)[1:28]})
    monkeypatch.setattr(r, "phase_readback", lambda _, phase, *args:
        ({key: blobs[key] for key in phase_keys(phase)}, inventories, dict(receipts_sha256="b" * 64)))
    result = r.verify(bundle, tmp_path, tmp_path)
    assert len(result["runs"]) == 30 and result["metadata_lineage_verified"]
    assert result["authenticated_metadata_objects"] == 115
    assert all(result[key] is False for key in ("source_separation_verified", "class_support_verified",
        "gpu_ready", "execution_authorized"))
    assert result["payload_reads"] == result["cloud_reads"] == result["model_runs"] == 0
    shards.pop()
    with pytest.raises(ValueError, match="cover"):
        r.verify(bundle, tmp_path, tmp_path)


def test_failed_readback_does_not_publish_success(tmp_path, monkeypatch):
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(r.sys, "argv", ["readback", "missing", "missing", "missing", str(output)])
    with pytest.raises(SystemExit, match="failed: FileNotFoundError"):
        r.main()
    assert not output.exists()
    output.write_bytes(b"existing receipt")
    with pytest.raises(SystemExit, match="FileExistsError"):
        r.main()
    assert output.read_bytes() == b"existing receipt"
