"""Offline ggshield 1.55.0 collector/formatter regression; no auth or API."""
from __future__ import annotations

from collections import Counter
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch


def formatter_report(directory: Path, arguments: list[str], incomplete: bool = False) -> bytes:
    from ggshield.core.config.user_config import SecretConfig
    from ggshield.core.scan.file import create_files_from_paths
    from ggshield.utils.files import ListFilesMode, expand_path_args
    from ggshield.verticals.secret.output.secret_json_output_handler import SecretJSONOutputHandler
    from ggshield.verticals.secret.secret_scan_collection import Result, Results, SecretScanCollection

    previous = Path.cwd()
    try:
        os.chdir(directory)
        paths = expand_path_args(tuple(arguments))
        files, binary_paths = create_files_from_paths(paths, set(), ListFilesMode.ALL)
    finally:
        os.chdir(previous)
    assert not binary_paths and len(files) == len(arguments) == 3
    selected = files[:-1] if incomplete else files
    results = [Result(filename=file.filename, filemode=file.filemode, path=file.path,
        url=file.url, secrets=[], ignored_secrets_count_by_kind=Counter()) for file in selected]
    collection = SecretScanCollection(id=directory, type="path", results=Results(results=results))
    handler = SecretJSONOutputHandler(verbose=False, secret_config=SecretConfig())
    report = json.loads(handler._process_scan_impl(collection))
    assert not report.get("errors") and report["total_incidents"] == 0
    names = [entry["filename"] for entry in report["entities_with_incidents"]]
    assert all(Path(name).is_absolute() for name in names)
    assert sorted(names) == sorted(str(file.path) for file in selected)
    return json.dumps(report).encode()


def check() -> dict:
    version = importlib.metadata.version("ggshield")  # Missing package must fail.
    if version != "1.55.0":
        raise RuntimeError("ggshield 1.55.0 is required for this schema regression")
    from pygitguardian import GGClient

    path = Path(__file__).with_name("publication_secret_scan.py")
    spec = importlib.util.spec_from_file_location("publication_secret_scan", path)
    assert spec and spec.loader
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    with (patch.object(GGClient, "__init__", side_effect=AssertionError("API client forbidden")),
          patch("socket.socket", side_effect=AssertionError("network forbidden")),
          patch("socket.create_connection", side_effect=AssertionError("network forbidden"))):
        with tempfile.TemporaryDirectory(prefix="ggshield-schema-") as temporary:
            directory = Path(temporary)
            arguments = [f"./document-{index}.txt" for index in range(3)]
            for name in arguments:
                (directory / name).write_text("Neutral inert document.\n")
            formatter_report(directory, arguments)

        def fake_git(directory, *arguments):
            if arguments == ("init", "-q"):
                (directory / ".git/info").mkdir(parents=True)
                return b""
            if arguments == ("add", "--force", "--all"):
                return b""
            if len(arguments) == 2 and arguments[0] == "show" and arguments[1].startswith(":"):
                return (directory / arguments[1][1:]).read_bytes()
            raise AssertionError("unexpected Git operation")

        incomplete = False
        calls = Counter()

        def fake_run(arguments, directory, **kwargs):
            calls[arguments[0]] += 1
            if arguments[0] == "gitleaks-fixture":
                return b""
            assert arguments[0] == "ggshield-fixture"
            return formatter_report(directory, arguments[arguments.index("--json") + 1:], incomplete)

        material = {f"document-{index}.txt": b"Neutral inert document.\n" for index in range(3)}
        with (patch.object(gate, "git", fake_git), patch.object(gate, "run", fake_run),
              patch.object(gate.shutil, "which", lambda name: name), patch.object(gate.os, "environ", {})):
            gate.scan(path.parents[1], material, "gitleaks-fixture", "ggshield-fixture")
            incomplete = True
            try:
                gate.scan(path.parents[1], material, "gitleaks-fixture", "ggshield-fixture")
            except gate.ScanFailure as error:
                assert "coverage incomplete" in str(error)
            else:
                raise AssertionError("incomplete real formatter coverage was accepted")
        assert calls == {"gitleaks-fixture": 2, "ggshield-fixture": 2}
    return {"ggshield_version": version, "documents": 3, "absolute_filename_schema": "pass",
            "complete_coverage": "accepted", "incomplete_coverage": "rejected", "api_requests": 0}


if __name__ == "__main__":
    print(json.dumps(check(), sort_keys=True))
