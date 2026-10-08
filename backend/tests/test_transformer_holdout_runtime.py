from types import SimpleNamespace

import pytest

from app.ml.transformer.holdout_runtime import (
    MAX_INJECTION, MAX_REQUEST, bounded_read, encode_request, inspect_runtime, load_request,
)
from app.ml.transformer.verification_spec import canonical, digest
from app.ml.transformer.holdout_spec import G8_PREFIX, HoldoutRequest, InputObject, OUTPUT_ROOT
from app.ml.transformer.settings_schema import Artifact


def fixture_request():
    def item(path, scope="final_test", uri=None):
        return InputObject(path=path, scope=scope, reference=Artifact(uri=uri or "s3://fixture/" + path,
            sha256="a" * 64, version_id="1", size_bytes=1))
    return HoldoutRequest(run_id="transformer-holdout-fixture", source_commit="1" * 40,
        image_repository="cr.eu-north1.nebius.cloud/fixture/tr", image_digest="sha256:" + "2" * 64,
        context_public_key="3" * 64, nonce="4" * 32, package_sha256="5" * 64,
        provider_spec_sha256="6" * 64, inputs=(item("tabular.json"), item("sequence.json"),
            item("baseline.parquet", uri=G8_PREFIX + "predictions.parquet"), item("reference.json", "development")),
        tabular_path="tabular.json", sequence_path="sequence.json", baseline_paths=("baseline.parquet",),
        reference_logits_path="reference.json", reference_targets_sha256="7" * 64, reference_rows=1,
        output_prefix=OUTPUT_ROOT + "transformer-holdout-fixture/")


def manifest(root):
    (root / "source-commit").write_text("1" * 40)
    value = {"source_commit": "1" * 40, "base_image": "digest-pinned-fixture", "files": {
        name: {"sha256": digest((root / name).read_bytes()), "size_bytes": (root / name).stat().st_size}
        for name in ("source-commit", "numerical.py")}}
    (root / "context-manifest.json").write_bytes(canonical(value))


def test_compressed_request_roundtrip_is_canonical_and_deterministic(tmp_path):
    req = fixture_request()
    raw = encode_request(req)
    assert raw == encode_request(req) and len(raw) <= MAX_INJECTION
    path = tmp_path / "request.gz"
    path.write_bytes(raw)
    assert load_request(path) == req


@pytest.mark.parametrize("defect", ["large_compressed", "large_expanded", "noncanonical", "broken"])
def test_bad_injection_never_loads_a_request(tmp_path, defect):
    import gzip
    req = fixture_request()
    raw = encode_request(req)
    if defect == "large_compressed":
        raw = b"x" * (MAX_INJECTION + 1)
    elif defect == "large_expanded":
        raw = gzip.compress(b" " * (MAX_REQUEST + 1))
    elif defect == "noncanonical":
        raw = gzip.compress(req.canonical_bytes() + b" ")
    else:
        raw = b"not gzip"
    path = tmp_path / "request.gz"
    path.write_bytes(raw)
    with pytest.raises((ValueError, OSError)):
        load_request(path)


def test_request_encoder_rejects_oversized_manifest():
    with pytest.raises(ValueError, match="injection envelope"):
        encode_request(SimpleNamespace(canonical_bytes=lambda: b"x" * (MAX_REQUEST + 1)))


@pytest.mark.parametrize("defect", [None, "source", "dependency", "extra_dependency", "escape"])
def test_runtime_inspection_checks_trained_bytes_and_all_dependencies(tmp_path, defect):
    (tmp_path / "numerical.py").write_bytes(b"static source, no executable model")
    lock = {"base_image": "digest-pinned-fixture", "files": {"numerical.py": digest(
        (tmp_path / "numerical.py").read_bytes())}, "dependencies": {"declared-library": "1.0"}}
    actual = dict(lock["dependencies"])
    if defect == "source":
        (tmp_path / "numerical.py").write_bytes(b"changed")
    elif defect == "dependency":
        actual["declared-library"] = "2.0"
    elif defect == "extra_dependency":
        actual["extra"] = "1.0"
    elif defect == "escape":
        lock["files"] = {"../outside.py": digest(b"outside")}
    (tmp_path / "runtime-lock.json").write_bytes(canonical(lock))
    manifest(tmp_path)
    if defect:
        with pytest.raises(ValueError):
            inspect_runtime(tmp_path, installed=actual)
    else:
        assert inspect_runtime(tmp_path, installed=actual)["model_execution"] is False


@pytest.mark.parametrize("defect", ["source", "overlay", "size", "escape", "missing_manifest"])
def test_post_preparation_corruption_fails_static_inspection(tmp_path, defect):
    (tmp_path / "numerical.py").write_bytes(b"original static source")
    (tmp_path / "runtime-lock.json").write_bytes(canonical({"base_image": "digest-pinned-fixture",
        "files": {}, "dependencies": {}}))
    manifest(tmp_path)
    if defect == "source":
        (tmp_path / "source-commit").write_text("2" * 40)
    elif defect == "overlay":
        (tmp_path / "numerical.py").write_bytes(b"tampered source")
    elif defect == "missing_manifest":
        (tmp_path / "context-manifest.json").rename(tmp_path / "retained-manifest.json")
    else:
        from app.ml.transformer.settings_release import json_record
        value = json_record((tmp_path / "context-manifest.json").read_bytes())
        if defect == "size":
            value["files"]["numerical.py"]["size_bytes"] += 1
        else:
            value["files"]["../outside.py"] = value["files"].pop("numerical.py")
        (tmp_path / "context-manifest.json").write_bytes(canonical(value))
    with pytest.raises((ValueError, FileNotFoundError)):
        inspect_runtime(tmp_path, installed={})


@pytest.mark.parametrize("raw", [b"", b"a" * 4])
def test_bounded_file_reader_rejects_empty_or_oversized_file(tmp_path, raw):
    path = tmp_path / "file"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="envelope"):
        bounded_read(path, 3)
