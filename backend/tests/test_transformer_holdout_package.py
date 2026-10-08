import importlib.util
from pathlib import Path

import pytest

from test_transformer_settings_export import artifact_map  # noqa: E402
from app.ml.transformer.settings_release import save_release  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("holdout_package_cli", ROOT / "scripts/prepare_transformer_holdout_package.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def prepared(tmp_path, monkeypatch):
    mapping, fixture = artifact_map(tmp_path)
    release = fixture.release()
    monkeypatch.setattr(CLI, "SETTINGS_SHA", release.sha256())
    monkeypatch.setattr(CLI, "TRUST", fixture.pins)
    settings = tmp_path / "settings.json"
    save_release(release, settings)
    return mapping, settings, tmp_path / "package.json"


def test_portable_package_hashes_all_original_artifacts_without_embedding_weights(tmp_path, monkeypatch):
    mapping, settings, output = prepared(tmp_path, monkeypatch)
    receipt = CLI.prepare(mapping, settings, output)
    assert receipt["verified_artifacts"] == 7
    assert receipt["checkpoint_embedded"] is False
    assert receipt["model_execution"] is False and receipt["cloud_gets"] == 0
    assert receipt["execution_authorized"] is False
    import json
    package = json.loads(output.read_bytes())
    assert set(package) == {"settings", "evidence"}
    assert len(package["evidence"]) == 4
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        CLI.prepare(mapping, settings, output)
    assert output.read_bytes() == before


@pytest.mark.parametrize("defect", ["missing", "changed", "outside", "settings"])
def test_invalid_retained_evidence_never_publishes_package(tmp_path, monkeypatch, defect):
    mapping, settings, output = prepared(tmp_path, monkeypatch)
    if defect == "settings":
        settings.write_bytes(settings.read_bytes() + b" ")
    elif defect == "outside":
        import json
        record = json.loads(mapping.read_bytes())
        record["checkpoint"]["path"] = "../outside.blob"
        mapping.write_text(json.dumps(record))
    elif defect == "missing":
        (tmp_path / "checkpoint.blob").unlink()
    else:
        path = tmp_path / "checkpoint.blob"
        path.write_bytes(b"x" * path.stat().st_size)
    with pytest.raises((ValueError, FileNotFoundError)):
        CLI.prepare(mapping, settings, output)
    assert not output.exists()
