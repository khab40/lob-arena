from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
JOBS = ROOT / "serverless" / "jobs"


def test_acquisition_image_is_python_only() -> None:
    dockerfile = (JOBS / "Dockerfile.market-data-acquisition").read_text(encoding="utf-8")
    dockerignore = (JOBS / "Dockerfile.market-data-acquisition.dockerignore").read_text(
        encoding="utf-8"
    )
    requirements = (JOBS / "requirements.market-data-acquisition.txt").read_text(
        encoding="utf-8"
    )

    assert "run_market_data_acquisition.py" in dockerfile
    assert "run_market_data_preparation.py" not in dockerfile
    assert "control-plane" not in dockerfile
    assert "java" not in dockerfile.lower()
    assert "pyarrow" not in requirements
    assert "protobuf" not in requirements
    assert "lightgbm" not in requirements
    assert "mlflow" not in requirements
    assert "control-plane.jar" not in dockerignore
    assert "!java" not in dockerignore


def test_preparation_image_consumes_prebuilt_control_plane() -> None:
    dockerfile = (JOBS / "Dockerfile.market-data-preparation").read_text(encoding="utf-8")
    dockerignore = (JOBS / "Dockerfile.market-data-preparation.dockerignore").read_text(
        encoding="utf-8"
    )
    requirements = (JOBS / "requirements.market-data-preparation.txt").read_text(
        encoding="utf-8"
    )

    assert "run_market_data_preparation.py" in dockerfile
    assert "build/market-data/control-plane.jar" in dockerfile
    assert "eclipse-temurin:25-jre" in dockerfile
    assert "gradlew" not in dockerfile
    assert "COPY java" not in dockerfile
    assert "pyarrow" in requirements
    assert "protobuf" in requirements
    assert "lightgbm" not in requirements
    assert "mlflow" not in requirements
    assert "!build/market-data/control-plane.jar" in dockerignore
    assert "!java" not in dockerignore


def test_split_entrypoints_expose_only_their_c_steps() -> None:
    acquisition = (JOBS / "run_market_data_acquisition.py").read_text(encoding="utf-8")
    preparation = (JOBS / "run_market_data_preparation.py").read_text(encoding="utf-8")

    assert '"c0-s3"' in acquisition
    assert '"acquire-s3"' in acquisition
    assert '"prepare-s3"' not in acquisition
    assert "app.market_data.preparation" not in acquisition
    assert '"prepare-s3"' in preparation
    assert '"acquire-s3"' not in preparation
    assert "app.market_data.acquisition" not in preparation

    c0_submitter = (ROOT / "scripts" / "submit_market_data_job.py").read_text(
        encoding="utf-8"
    )
    stage_submitter = (ROOT / "scripts" / "submit_market_data_stage_job.py").read_text(
        encoding="utf-8"
    )
    assert "run_market_data_acquisition.py c0-s3" in c0_submitter
    assert "run_market_data_acquisition.py" in stage_submitter
    assert "run_market_data_preparation.py" in stage_submitter


def test_acquisition_import_does_not_require_pyarrow() -> None:
    script = """
import importlib.abc
import sys

class BlockPyArrow(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "pyarrow" or fullname.startswith("pyarrow."):
            raise ModuleNotFoundError(fullname)
        return None

sys.meta_path.insert(0, BlockPyArrow())
from app.market_data.acquisition import execute_acquisition_s3
from app.market_data.public_sample import execute_c0_s3
assert execute_acquisition_s3
assert execute_c0_s3
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "backend",
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
