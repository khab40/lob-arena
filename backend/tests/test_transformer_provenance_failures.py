import json
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import role_provenance_transport as t  # noqa: E402
from test_transformer_role_provenance import bind_local_metadata, chain  # noqa: E402


@pytest.mark.parametrize("error", [PermissionError("private diagnostic"), TimeoutError("deadline")])
def test_denied_or_timed_out_read_preserves_sanitized_failure(tmp_path, monkeypatch, error):
    _, source, runs = chain()
    bind_local_metadata(monkeypatch, source, runs)
    calls = []

    def fail(**args):
        calls.append(args)
        raise error

    with pytest.raises(type(error)):
        t.collect(NS(get_object=fail), tmp_path, tmp_path / "out")
    assert len(calls) == 1
    assert json.loads((tmp_path / "out/receipts.json").read_bytes()) == []
    failure = (tmp_path / "out/failure.json").read_text()
    assert "private diagnostic" not in failure and '"gpu_ready":false' in failure
    assert not (tmp_path / "out/provenance.json").exists()
    measurements = json.loads((tmp_path / "out/measurements.json").read_bytes())
    assert measurements["get_attempts"] == 1 and measurements["payload_reads"] == 0


def test_unknown_metadata_key_rejected_without_network_call():
    def unexpected(**_):
        pytest.fail("network call escaped allowlist")
    with pytest.raises(ValueError, match="inventory"):
        t.read_metadata(NS(get_object=unexpected), "data/other/checkpoint.json")


def test_existing_evidence_directory_is_not_overwritten(tmp_path, monkeypatch):
    _, source, runs = chain()
    bind_local_metadata(monkeypatch, source, runs)
    (tmp_path / "out").mkdir()
    (tmp_path / "out/receipts.json").write_text("preserved")
    with pytest.raises(FileExistsError):
        t.collect(None, tmp_path, tmp_path / "out")
    assert (tmp_path / "out/receipts.json").read_text() == "preserved"
