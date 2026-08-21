import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml


def test_render_job_config_applies_experiment_overrides(tmp_path: Path) -> None:
    renderer = _load_renderer()
    rendered_path = tmp_path / "outputs" / "experiments" / "EXP-001" / "nebius_job_config.rendered.yaml"

    path = renderer.render_job_config(
        experiment_id="EXP-001",
        runs=17,
        batch_size=4,
        scenarios=["spoofing_like_wall", "quote_stuffing"],
        random_seed=1234,
        image="ghcr.io/acme/aimada-jobs:test-tag",
        output_dir="/job/outputs/experiments/EXP-001/local-batch",
        rendered_path=rendered_path,
    )

    assert path == rendered_path
    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert config["image"] == {"repository": "ghcr.io/acme/aimada-jobs", "tag": "test-tag"}
    assert config["scenarios"] == ["spoofing_like_wall", "quote_stuffing"]
    assert config["outputs"]["directory"] == "/job/outputs/experiments/EXP-001/local-batch"
    assert "--runs 17" in config["args"]
    assert "--batch-size 4" in config["args"]
    assert "--scenarios spoofing_like_wall,quote_stuffing" in config["args"]
    assert "--random-seed 1234" in config["args"]
    assert "--output /job/outputs/experiments/EXP-001/local-batch" in config["args"]


def test_render_job_config_defaults_image_tag_and_output_path(tmp_path: Path, monkeypatch: Any) -> None:
    renderer = _load_renderer()
    monkeypatch.chdir(tmp_path)

    path = renderer.render_job_config(
        experiment_id="EXP-002",
        runs=3,
        batch_size=2,
        scenarios=["normal_market"],
        random_seed=91,
        image="ghcr.io/acme/aimada-jobs",
        output_dir="/job/outputs/experiments/EXP-002/local-batch",
    )

    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert path == tmp_path / "outputs" / "experiments" / "EXP-002" / "nebius_job_config.rendered.yaml"
    assert config["image"] == {"repository": "ghcr.io/acme/aimada-jobs", "tag": "latest"}
    assert config["scenarios"] == ["normal_market"]


def test_render_lightgbm_job_config_requires_digest_and_governed_runner(tmp_path: Path) -> None:
    renderer = _load_renderer()
    rendered = tmp_path / "wave1.yaml"
    image = "registry.eu-north1.nebius.cloud/project/jobs@sha256:" + "a" * 64

    renderer.render_lightgbm_job_config(
        input_uri="s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging",
        endpoint_url="https://storage.eu-north1.nebius.cloud",
        work_root="/job/wave1",
        image=image,
        rendered_path=rendered,
    )
    config = yaml.safe_load(rendered.read_text(encoding="utf-8"))
    assert config["kind"] == "governed_lightgbm_wave1"
    assert config["image"]["digest"] == "sha256:" + "a" * 64
    assert "run_lightgbm_wave1.py run-s3" in config["args"]
    assert "--input-uri s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging" in config["args"]
    assert "/job/inputs" not in config["args"]

    try:
        renderer.render_lightgbm_job_config(
            input_uri="s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging",
            endpoint_url="https://storage.eu-north1.nebius.cloud",
            work_root="/job/wave1",
            image="registry.eu-north1.nebius.cloud/project/jobs:latest",
            rendered_path=rendered,
        )
    except ValueError as error:
        assert "sha256" in str(error)
    else:
        raise AssertionError("mutable Wave 1 image was accepted")

    try:
        renderer.render_lightgbm_job_config(
            input_uri="s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging",
            endpoint_url="https://unapproved.example.test",
            work_root="/job/wave1",
            image=image,
            rendered_path=rendered,
        )
    except ValueError as error:
        assert "approved eu-north1" in str(error)
    else:
        raise AssertionError("unapproved credential endpoint was accepted")


def _load_renderer() -> ModuleType:
    module_path = Path(__file__).resolve().parents[2] / "serverless" / "jobs" / "render_job_config.py"
    spec = importlib.util.spec_from_file_location("render_job_config_for_tests", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load renderer from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
