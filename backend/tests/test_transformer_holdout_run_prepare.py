import importlib.util
import json
from pathlib import Path
import stat

import pytest

from app.ml.transformer.holdout_runtime import load_request
from app.ml.transformer.holdout_spec import G8_PREFIX, InputObject
from app.ml.transformer.verification_spec import canonical, digest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("run_prepare", ROOT / "scripts/prepare_transformer_holdout_run.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def envelope(tmp_path, monkeypatch):
    root, output = tmp_path / "repository", tmp_path / "evidence"
    settings = root / "outputs/transformer-settings-release-20261005/selected-settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_bytes((ROOT / "configs/releases/transformer/selected-settings-20261005.json").read_bytes())
    output.mkdir()
    def item(path, uri, scope):
        return InputObject(path=path, scope=scope, reference={"uri": uri, "version_id": "1",
            "size_bytes": 1, "sha256": "a" * 64})
    inputs = [item(f"dev-{i}", f"s3://development/key-{i}", "development") for i in range(185)]
    final_paths = ["manifests/tabular-projection.json", "manifests/sequence-projection.json"]
    final_paths += [f"shard-{i}" for i in range(60)]
    inputs += [item(p, "s3://aimada-wave1-final-fixture/" + p, "final_test") for p in final_paths]
    inputs += [item("baseline/predictions.parquet", G8_PREFIX + "artifacts/prediction/predictions.parquet", "final_test")]
    monkeypatch.setattr(CLI, "audited_inputs", lambda *args: tuple(inputs))
    records = {"reference-publication.json": {"artifact": {"uri": "s3://development/reference.json",
        "version_id": "1", "sha256": "220a2cf373290c846e1da29252ed149156b3f74d6598d2da4e9863bfbca364a5", "size_bytes": 7544}},
        "image-publication.json": {"repository": "cr.eu-north1.nebius.cloud/fixture/tr",
            "source_commit": "a" * 40, "image_digest": "sha256:" + "b" * 64},
        "final-policy-baseline.json": [{"group_id": "retained", "roles": ["storage.viewer"], "paths": ["original/*"]}],
        "results-policy-baseline.json": [{"group_id": "retained", "roles": ["storage.viewer"], "paths": ["original/*"]}]}
    for name, value in records.items():
        (output / name).write_bytes(canonical(value))
    return root, output


def test_exact_package_has_no_submission_and_retains_one_identity(tmp_path, monkeypatch):
    root, output = envelope(tmp_path, monkeypatch)
    receipt = CLI.prepare(root, output, ROOT)
    request = load_request(output / "request.json.gz")
    proposal = json.loads((output / "proposal.json").read_bytes())
    assert receipt["jobs_created"] == 0 and len(request.inputs) == 252
    assert proposal["status"] == "awaiting_exact_authorization" and not proposal["fitting"]
    assert proposal["additional_spend_cap_usd_excluding_vat"] == "6.25"
    assert request.provider_spec_sha256 == digest((output / "provider-spec.json").read_bytes())
    assert stat.S_IMODE((output / "context-private.key").stat().st_mode) == 0o600
    before = (output / "context-private.key").read_bytes()
    with pytest.raises(ValueError, match="never be regenerated"):
        CLI.prepare(root, output, ROOT)
    assert (output / "context-private.key").read_bytes() == before


def test_changed_settings_fail_before_key_or_execution_identity(tmp_path, monkeypatch):
    root, output = envelope(tmp_path, monkeypatch)
    (root / "outputs/transformer-settings-release-20261005/selected-settings.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="settings differ"):
        CLI.prepare(root, output, ROOT)
    assert not (output / "context-private.key").exists()
    assert not (output / "request.json").exists()
