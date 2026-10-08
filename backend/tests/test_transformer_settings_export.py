"""CLI boundary uses bounded retained files and publishes only validated metadata."""
import importlib.util
import json
from pathlib import Path

import pytest

from transformer_settings_fixtures import SettingsFixture

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("settings_export_cli", ROOT / "scripts/export_transformer_settings.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def artifact_map(tmp_path):
    fixture = SettingsFixture().prepare()
    mapping = {}
    for name, ref in fixture.artifacts:
        path = tmp_path / (name + ".blob")
        path.write_bytes(fixture.reads[ref.uri].data)
        mapping[name] = {"reference": ref.model_dump(mode="json"), "path": path.name}
    path = tmp_path / "map.json"
    path.write_text(json.dumps(mapping))
    return path, fixture


def test_cli_export_preserves_the_selected_release_without_model_execution(tmp_path):
    mapping, fixture = artifact_map(tmp_path)
    output = tmp_path / "settings.json"
    receipt = CLI.export(mapping, output, **fixture.pins)
    assert receipt["sha256"] == fixture.release().sha256()
    assert receipt["research_inference_gates_passed"] is True
    assert receipt["serving_eligible"] is False
    assert receipt["cloud_gets"] == 0 and receipt["model_execution"] is False
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        CLI.export(mapping, output, **fixture.pins)
    assert output.read_bytes() == before


@pytest.mark.parametrize("defect", ["missing", "truncated", "changed", "trust_pin"])
def test_cli_invalid_input_never_publishes_a_manifest(tmp_path, defect):
    mapping, fixture = artifact_map(tmp_path)
    output = tmp_path / "settings.json"
    path = tmp_path / "checkpoint.blob"
    if defect == "missing":
        path.unlink()
    elif defect == "truncated":
        path.write_bytes(b"x")
    elif defect == "changed":
        path.write_bytes(b"x" * path.stat().st_size)
    else:
        fixture.pins["selection_sha256"] = "0" * 64
    with pytest.raises((ValueError, FileNotFoundError)):
        CLI.export(mapping, output, **fixture.pins)
    assert not output.exists()
