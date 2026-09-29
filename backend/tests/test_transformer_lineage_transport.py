import json
from io import BytesIO
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import lineage_transport as t  # noqa: E402
from app.ml.transformer.lineage_inventory import phase_keys  # noqa: E402
from app.ml.transformer.verification_spec import INPUT_BUCKET  # noqa: E402
from transformer_lineage_fixtures import fixture  # noqa: E402


class S3:
    def __init__(self, blobs):
        self.blobs, self.calls = blobs, []

    def get_object(self, *, Bucket, Key):
        assert Bucket == INPUT_BUCKET
        self.calls.append(Key)
        raw = self.blobs[Key]
        return dict(Body=BytesIO(raw), ContentLength=len(raw), VersionId="version-fixture")


@pytest.fixture
def audit(tmp_path, monkeypatch):
    anchor, blobs = fixture()
    monkeypatch.setattr(t, "context", lambda _: anchor)
    bundle = tmp_path / "anchor.json"
    bundle.write_bytes(b"inert bundle fixture")
    return S3(blobs), bundle, tmp_path / "phase-one", tmp_path / "phase-two"


def test_both_phases_read_exactly_once_and_reverify_retained_bytes(audit):
    s3, bundle, first, second = audit
    t.collect(s3, bundle, 1, first)
    result = t.collect(s3, bundle, 2, second, first)
    assert s3.calls == phase_keys(1) + phase_keys(2)
    assert result["authenticated_objects"] == 57 and not result["gpu_ready"]
    assert len(json.loads((first / "receipts.json").read_bytes())) == 58
    assert json.loads((second / "measurements.json").read_bytes())["get_attempts"] == 57
    with pytest.raises(FileExistsError):
        t.collect(s3, bundle, 2, second, first)
    assert len(s3.calls) == 115


@pytest.mark.parametrize("target", ["metadata-00.json", "metadata-28.json", "receipts.json", "verification.json"])
def test_phase_two_rejects_changed_local_evidence_before_get(audit, target):
    s3, bundle, first, second = audit
    t.collect(s3, bundle, 1, first)
    (first / target).write_bytes(b"{}")
    with pytest.raises(ValueError):
        t.collect(s3, bundle, 2, second, first)
    assert len(s3.calls) == 58 and not second.exists()


@pytest.mark.parametrize("index", [0, 1, 28])
def test_failure_stops_collection_without_success(audit, index):
    s3, bundle, first, _ = audit
    s3.blobs[phase_keys(1)[index]] = b"{}"
    with pytest.raises(ValueError):
        t.collect(s3, bundle, 1, first)
    assert len(s3.calls) == index + 1
    assert (first / "failure.json").exists() and not (first / "verification.json").exists()


def test_provider_exception_text_is_not_retained(audit):
    s3, bundle, first, _ = audit
    def fail(**_):
        raise RuntimeError("sensitive provider exception fixture")
    s3.get_object = fail
    with pytest.raises(RuntimeError):
        t.collect(s3, bundle, 1, first)
    assert "sensitive" not in (first / "failure.json").read_text()


@pytest.mark.parametrize("size,version", [(0, "1"), (t.MAX_OBJECT + 1, "1"), (2, "1"), (1, None), (1, "null")])
def test_invalid_body_is_bounded_and_closed(size, version):
    body = BytesIO(b"x")
    s3 = NS(get_object=lambda **_: dict(Body=body, ContentLength=size, VersionId=version))
    with pytest.raises(ValueError):
        t.read_metadata(s3, 1, phase_keys(1)[0])
    assert body.closed


def test_out_of_scope_or_missing_prior_phase_never_reads(audit):
    s3, bundle, first, second = audit
    with pytest.raises(ValueError, match="allowlist"):
        t.read_metadata(s3, 1, phase_keys(2)[0])
    with pytest.raises(ValueError, match="requires"):
        t.collect(s3, bundle, 2, second)
    with pytest.raises(ValueError, match="must not"):
        t.collect(s3, bundle, 1, first, second)
    assert not s3.calls
