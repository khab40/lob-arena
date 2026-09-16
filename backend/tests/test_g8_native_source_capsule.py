"""Static capsule checks; no fixture training or scoring is performed."""
import json

import pytest

from serverless.jobs import g8_native_source_capsule as capsule


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    source = tmp_path / "source"
    entries = []
    for name in (*capsule.METADATA, "sources/input/SUCCESS", "sources/candidate/SUCCESS"):
        target = source / "payload" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = name.encode()
        target.write_bytes(raw)
        entries.append({"path": name, "size_bytes": len(raw), "sha256": capsule.sha(raw)})
    raw = json.dumps({"inventory": {"files": entries}}).encode().ljust(74744, b" ")
    (source / "source-package.json").write_bytes(raw)
    monkeypatch.setattr(capsule, "SOURCE_SHA256", capsule.sha(raw))
    output = tmp_path / "capsule"
    capsule.build(source, output)
    return source, output


def test_original_inventory_survives_split_and_relocation(prepared, tmp_path):
    source, output = prepared
    moved = tmp_path / "relocated"
    output.rename(moved)
    receipt = capsule.verify(moved)
    assert all(x["size_bytes"] <= 65536 for x in receipt["injections"].values())
    assert b"".join((moved / f"inventory-{i}.part").read_bytes() for i in range(2)) == (
        source / "source-package.json").read_bytes()
    assert not receipt["submission_authorized"]


@pytest.mark.parametrize("name", ["inventory-0.part", "inventory-1.part", "metadata-5.part"])
def test_corruption_rejected(prepared, name):
    _, output = prepared
    path = output / name
    raw = path.read_bytes()
    path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    with pytest.raises(ValueError, match="differs"):
        capsule.verify(output)


def test_link_and_extra_file_rejected(prepared, tmp_path):
    _, output = prepared
    path = output / "metadata-0.part"
    retained = tmp_path / "retained"
    path.rename(retained)
    path.symlink_to(retained)
    with pytest.raises(ValueError, match="linked"):
        capsule.verify(output)
    path.unlink()
    retained.rename(path)
    (output / "unreviewed.py").write_text("extra")
    with pytest.raises(ValueError, match="unexpected"):
        capsule.verify(output)


def test_changed_source_and_occupied_destination_preserved(prepared, tmp_path):
    source, output = prepared
    with pytest.raises(FileExistsError):
        capsule.build(source, output)
    path = source / "payload/sources/input/SUCCESS"
    path.write_bytes(b"x" * path.stat().st_size)
    with pytest.raises(ValueError, match="retained source bytes"):
        capsule.build(source, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_nested_output_rejected_before_source_mutation(prepared):
    source, _ = prepared
    with pytest.raises(ValueError, match="canonical"):
        capsule.build(source, source / "nested")
    assert not (source / "nested").exists()


@pytest.mark.parametrize("fault", [None, "denial", "bytes"])
def test_hydration_reads_only_reviewed_sources_and_seals_last(prepared, tmp_path, monkeypatch, fault):
    pytest.importorskip("lightgbm")
    from serverless.jobs import stage_g8_native_sources as staging

    source, output = prepared
    monkeypatch.setattr(staging, "_credential_identity", lambda: capsule.ACCESS_ID_SHA256)
    destination = tmp_path / "hydrated"

    class Remote:
        calls = []

        def production_head_denied(self, bucket, key):
            self.calls.append("head")
            assert bucket == staging.PRODUCTION_BUCKET and key == staging.PRODUCTION_KEY
            if fault == "denial":
                raise ValueError("HEAD denial not verified")

        def _transfer_json(self, size, *args):
            assert self.calls[0] == "head"
            assert not (destination / "source-package.json").exists()
            assert args[:2] == ("s3api", "get-object")
            bucket, key = args[3], args[5]
            name = next(n for n, (b, p) in capsule.PREFIXES.items() if b == bucket and key == p + "/SUCCESS")
            from pathlib import Path
            Path(args[-1]).write_bytes((source / f"payload/sources/{name}/SUCCESS").read_bytes())
            if fault == "bytes":
                Path(args[-1]).write_bytes(b"corrupted")
            self.calls.append("get")

    remote = Remote()
    if fault:
        with pytest.raises(ValueError):
            capsule.hydrate(output, destination, s3=remote)
        assert not (destination / "source-package.json").exists()
        if fault == "denial":
            assert remote.calls == ["head"]
        return
    result = capsule.hydrate(output, destination, s3=remote)
    assert remote.calls == ["head", "get", "get"]
    assert (destination / "source-package.json").read_bytes() == (source / "source-package.json").read_bytes()
    assert not result["credential_version_provenance_verified"]
    assert result["remote_objects_verified"] == 2
