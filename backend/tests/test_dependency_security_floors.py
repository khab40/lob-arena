import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def locked_version(package: str, path: Path = ROOT / "backend" / "uv.lock") -> tuple[int, ...]:
    lockfile = path.read_text(encoding="utf-8")
    match = re.search(
        rf'\[\[package\]\]\nname = "{re.escape(package)}"\nversion = "([0-9.]+)"',
        lockfile,
    )
    assert match is not None, f"{package} is missing from backend/uv.lock"
    return tuple(int(part) for part in match.group(1).split("."))


def test_active_lock_uses_patched_framework_versions() -> None:
    assert locked_version("starlette") >= (1, 3, 1)
    assert locked_version("pydantic-settings") >= (2, 14, 2)


def test_every_backend_lock_uses_patched_cryptography() -> None:
    lockfiles = [
        ROOT / "backend" / "uv.lock",
        ROOT
        / "evidence"
        / "deployment-2026-07-14-1412"
        / "versions"
        / "requirements"
        / "backend"
        / "uv.lock",
    ]

    for path in lockfiles:
        assert locked_version("cryptography", path) >= (50, 0, 0), path


def test_every_python_install_surface_enforces_security_floors() -> None:
    starlette_surfaces = [
        ROOT / "backend" / "pyproject.toml",
        ROOT / "backend" / "Dockerfile",
        ROOT / "agent-runner" / "Dockerfile",
        ROOT / "serverless" / "endpoint" / "requirements.txt",
    ]
    pydantic_settings_surfaces = [
        ROOT / "backend" / "pyproject.toml",
        ROOT / "backend" / "Dockerfile",
    ]

    for path in starlette_surfaces:
        assert "starlette>=1.6.0" in path.read_text(encoding="utf-8"), path
    for path in pydantic_settings_surfaces:
        assert "pydantic-settings>=2.14.2" in path.read_text(encoding="utf-8"), path
