from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]


def assert_compatible_protobuf(requirements: str) -> None:
    matches = re.findall(
        r"^protobuf>=(\d+\.\d+\.\d+),<8\.0\.0$", requirements, flags=re.MULTILINE
    )
    assert len(matches) == 1, "Protobuf needs a patched floor and the <8.0.0 ceiling"
    assert (7, 36, 1) <= tuple(map(int, matches[0].split("."))) < (8, 0, 0)


@pytest.mark.parametrize("version", ["7.36.1", "7.36.2", "7.37.0"])
def test_protobuf_contract_accepts_patch_and_minor_updates(version: str) -> None:
    assert_compatible_protobuf(f"protobuf>={version},<8.0.0")


@pytest.mark.parametrize(
    "requirement",
    [
        "protobuf>=7.36.0,<8.0.0",
        "protobuf>=7.36.2",
        "protobuf>=7.36.2,<9.0.0",
        "protobuf>=8.0.0,<8.0.0",
        "# protobuf>=7.36.2,<8.0.0",
    ],
)
def test_protobuf_contract_rejects_weaker_or_incompatible_bounds(requirement: str) -> None:
    with pytest.raises(AssertionError):
        assert_compatible_protobuf(requirement)


def test_serverless_builds_use_context_specific_dockerignore_files() -> None:
    build_script = (ROOT / "scripts" / "build-serverless-images.sh").read_text(encoding="utf-8")
    root_ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    endpoint_ignore = (ROOT / "serverless" / "endpoint" / ".dockerignore").read_text(encoding="utf-8")

    assert '"${ROOT_DIR}/serverless/endpoint"' in build_script
    assert '"${ROOT_DIR}"' in build_script
    assert root_ignore.splitlines()[3] == "**"
    assert "backend/**" in root_ignore
    assert "!backend/app/**" in root_ignore
    assert "!backend/compose-entrypoint.sh" in root_ignore
    assert "!serverless/jobs/**" in root_ignore
    assert "!assets/" not in root_ignore
    assert "!evidence/" not in root_ignore
    assert "test_*.py" in endpoint_ignore
    assert "endpoint_config*.yaml" in endpoint_ignore


def test_serverless_images_use_distinct_dockerfiles_and_tags() -> None:
    build_script = (ROOT / "scripts" / "build-serverless-images.sh").read_text(encoding="utf-8")
    jobs_dockerfile = (ROOT / "serverless" / "jobs" / "Dockerfile").read_text(encoding="utf-8")

    assert 'serverless/endpoint/Dockerfile"' in build_script
    assert 'serverless/jobs/Dockerfile"' in build_script
    assert 'if [[ "${ENDPOINT_IMAGE}" == "${JOBS_IMAGE}" ]]' in build_script
    assert (
        "python /job/serverless/jobs/run_lightgbm_g8.py --runtime-compatibility-check"
        in jobs_dockerfile
    )


def test_runtime_images_exclude_development_dependencies() -> None:
    backend_dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    jobs_requirements = (ROOT / "serverless" / "jobs" / "requirements.txt").read_text(encoding="utf-8")
    frontend_dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert "pytest" not in backend_dockerfile
    assert "numpy" not in backend_dockerfile
    assert "numpy" not in jobs_requirements
    assert "fastapi" not in jobs_requirements
    assert "COPY --from=build /app/dist /dist" in frontend_dockerfile
    assert 'CMD ["npm", "run", "dev"' not in frontend_dockerfile
    assert 'CMD ["pnpm", "run", "dev"' not in frontend_dockerfile


def test_jobs_mlflow_dependencies_match_the_locked_compatible_pair() -> None:
    jobs_requirements = (ROOT / "serverless" / "jobs" / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "databricks-sdk==0.67.0" in jobs_requirements
    assert_compatible_protobuf(jobs_requirements)
    assert_compatible_protobuf(
        (ROOT / "serverless" / "jobs" / "requirements.market-data-preparation.txt").read_text(
            encoding="utf-8"
        )
    )
    names = [
        re.split(r"[<>=!~]", line)[0].lower().replace("_", "-")
        for line in jobs_requirements.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(names) == len(set(names)), "Each dependency must have one requirement"
