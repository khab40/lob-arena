from types import SimpleNamespace

import pytest

from app.ml.transformer.holdout_runtime import (
    MAX_INJECTION, MAX_REQUEST, bounded_read, encode_request, inspect_runtime, load_request,
)
from app.ml.transformer.verification_spec import canonical, digest
from app.ml.transformer.holdout_spec import G8_PREFIX
from transformer_holdout_fixtures import reference, request


def fixture_request():
    return request([reference("tabular.json", b"metadata"), reference("sequence.json", b"metadata"),
                    reference("baseline.parquet", b"metadata", uri=G8_PREFIX + "predictions.parquet")])[0]


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
    if defect:
        with pytest.raises(ValueError):
            inspect_runtime(tmp_path, installed=actual)
    else:
        assert inspect_runtime(tmp_path, installed=actual)["model_execution"] is False


@pytest.mark.parametrize("raw", [b"", b"a" * 4])
def test_bounded_file_reader_rejects_empty_or_oversized_file(tmp_path, raw):
    path = tmp_path / "file"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="envelope"):
        bounded_read(path, 3)
