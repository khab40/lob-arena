from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.market_data import public_sample
from app.market_data.public_sample import (
    C0PreflightRequest,
    EXPECTED_SOURCES,
    EXPECTED_TOTAL_BYTES,
    HttpHeadEvidence,
    S3ProbeEvidence,
    config_artifact,
    execute_c0_preflight,
    load_source_config,
    verify_c0_result,
)
from app.nebius.object_storage import sha256_file
from scripts import market_data_wave1, submit_market_data_job


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "data" / "nasdaq-public-sample-v1.json"
IMAGE = "ghcr.io/khab40/lob-arena-jobs@sha256:" + "a" * 64


def test_source_config_is_the_complete_exact_allowlist() -> None:
    config = load_source_config(CONFIG)

    assert [item.filename for item in config.sources] == list(EXPECTED_SOURCES)
    assert sum(item.expected_content_length for item in config.sources) == EXPECTED_TOTAL_BYTES
    assert config.instruments == ("AAPL", "MSFT", "NVDA")
    assert config.window_start_et == "10:00:00"
    assert config.window_end_et == "10:30:00"


def test_source_config_rejects_url_or_length_drift() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["sources"][0]["url"] = "https://example.test/file.gz"
    with pytest.raises(ValidationError, match="exact approved Nasdaq path"):
        public_sample.NasdaqPublicSampleConfig.model_validate(payload)

    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["sources"][0]["expected_content_length"] += 1
    with pytest.raises(ValidationError, match="exact approved Nasdaq allowlist"):
        public_sample.NasdaqPublicSampleConfig.model_validate(payload)


def test_c0_local_execution_proves_zero_body_and_deleted_probe(tmp_path: Path) -> None:
    input_root, request = _input_package(tmp_path)
    config = load_source_config(CONFIG)

    def head(source: public_sample.NasdaqPublicSource) -> HttpHeadEvidence:
        return HttpHeadEvidence(
            filename=source.filename,
            status=200,
            content_length=source.expected_content_length,
            etag=f"etag-{source.filename}",
            last_modified="Wed, 28 Aug 2026 00:00:00 GMT",
        )

    def probe(uri: str, payload: str, limit: int) -> S3ProbeEvidence:
        content = payload.encode()
        assert uri == request.s3_probe_uri
        assert len(content) <= limit == 256
        return S3ProbeEvidence(
            uri=uri,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            etag="probe-etag",
        )

    result = execute_c0_preflight(
        input_root / "request.json",
        input_root=input_root,
        result_root=tmp_path / "result",
        head_requester=head,
        s3_prober=probe,
    )
    evidence = verify_c0_result(result)

    assert evidence.http_request_count == len(config.sources) == 7
    assert evidence.http_body_bytes == 0
    assert all(item.response_body_bytes == 0 for item in evidence.sources)
    assert evidence.s3_probe.deleted is True
    assert evidence.s3_probe.deletion_verified is True
    assert evidence.disposition == "c0_preflight_passed"
    assert all(evidence.gates.values())


def test_c0_stops_on_declared_length_change_before_s3_probe(tmp_path: Path) -> None:
    input_root, _ = _input_package(tmp_path)
    probes = 0

    def wrong_head(source: public_sample.NasdaqPublicSource) -> HttpHeadEvidence:
        return HttpHeadEvidence(
            filename=source.filename,
            status=200,
            content_length=source.expected_content_length + 1,
        )

    def probe(*_: object) -> S3ProbeEvidence:
        nonlocal probes
        probes += 1
        raise AssertionError("probe must not run after Nasdaq metadata drift")

    with pytest.raises(ValueError, match="declared Nasdaq content length changed"):
        execute_c0_preflight(
            input_root / "request.json",
            input_root=input_root,
            result_root=tmp_path / "result",
            head_requester=wrong_head,
            s3_prober=probe,
        )
    assert probes == 0


def test_disposable_s3_probe_is_read_back_and_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    uploaded = b""

    def aws_json(_endpoint: str, *args: str) -> dict[str, object]:
        nonlocal uploaded
        calls.append(args)
        operation = args[1]
        if operation == "put-object":
            uploaded = Path(args[args.index("--body") + 1]).read_bytes()
            digest = hashlib.sha256(uploaded).hexdigest()
            assert args[args.index("--metadata") + 1] == (
                f"sha256={digest},purpose=c0-disposable-probe"
            )
            return {"ETag": '"put-etag"'}
        if operation == "head-object":
            return {
                "ContentLength": len(uploaded),
                "Metadata": {"sha256": hashlib.sha256(uploaded).hexdigest()},
                "ETag": '"probe-etag"',
            }
        if operation == "get-object":
            Path(args[-1]).write_bytes(uploaded)
            return {}
        if operation in {"delete-object", "list-objects-v2"}:
            return {"Contents": []}
        raise AssertionError(args)

    monkeypatch.setattr(public_sample, "_aws_json", aws_json)
    uri = (
        "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
        "preflight/c0-test/probe/probe.bin"
    )
    evidence = public_sample._probe_s3_object(uri, "bounded-probe\n", 256)

    assert evidence.read_back_verified is True
    assert evidence.deleted is True
    assert evidence.deletion_verified is True
    assert [call[1] for call in calls] == [
        "put-object",
        "head-object",
        "get-object",
        "delete-object",
        "list-objects-v2",
    ]
    for call in calls:
        selector = "--prefix" if call[1] == "list-objects-v2" else "--key"
        assert call[call.index(selector) + 1].endswith("/probe/probe.bin")


def test_c0_requires_injected_credentials_and_exact_job_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, request = _input_package(tmp_path)
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "AWS_EC2_METADATA_DISABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="MysteryBox-injected"):
        public_sample._require_c0_environment()

    repository, digest = request.image.rsplit("@sha256:", maxsplit=1)
    environment = {
        "AWS_ACCESS_KEY_ID": "injected-access",
        "AWS_SECRET_ACCESS_KEY": "injected-secret",
        "AWS_DEFAULT_REGION": "eu-north1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "MARKET_DATA_ACTUAL_PROJECT_ID": request.project_id,
        "MARKET_DATA_ACTUAL_IMAGE_REPOSITORY": repository,
        "MARKET_DATA_ACTUAL_IMAGE_SHA256": digest,
        "MARKET_DATA_ACTUAL_PLATFORM": "cpu-d3",
        "MARKET_DATA_ACTUAL_PRESET": "4vcpu-16gb",
        "MARKET_DATA_ACTUAL_DISK_SIZE_GIB": "100",
        "MARKET_DATA_ACTUAL_TIMEOUT_SECONDS": "3600",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    public_sample._require_c0_environment()
    public_sample._verify_c0_job_context(request)
    monkeypatch.setenv("MARKET_DATA_ACTUAL_PRESET", "other")
    with pytest.raises(RuntimeError, match="does not match"):
        public_sample._verify_c0_job_context(request)


def test_prepare_and_submit_dry_run_are_bounded_and_redacted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(market_data_wave1, "_git_commit", lambda: "0" * 40)
    package = tmp_path / "package"
    package_evidence = tmp_path / "package-evidence.json"
    market_data_wave1.prepare_c0(
        run_id="c0-test-run",
        image=IMAGE,
        source_config=CONFIG,
        package=package,
        evidence_output=package_evidence,
    )
    dry_run = tmp_path / "dry-run.json"
    for name in (
        "NEBIUS_VOLUME",
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
        "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "NEBIUS_OBJECT_STORAGE_SESSION_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    submit_market_data_job.main(
        [
            "--image",
            IMAGE,
            "--name",
            "market-data-c0-test",
            "--subnet-id",
            "subnet-test",
            "--input-uri",
            json.loads(package_evidence.read_text(encoding="utf-8"))["destination"],
            "--request-evidence",
            str(package_evidence),
            "--access-key-secret-id",
            "access-selector-must-not-leak",
            "--secret-key-secret-id",
            "secret-selector-must-not-leak",
            "--data-prep-spend-usd",
            "0",
            "--data-prep-jobs-consumed",
            "0",
            "--evidence-output",
            str(dry_run),
            "--dry-run",
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(dry_run.read_text(encoding="utf-8"))
    command = payload["command"]

    assert "access-selector-must-not-leak" not in output
    assert "secret-selector-must-not-leak" not in output
    assert "AWS_ACCESS_KEY_ID=[MYSTERYBOX_SELECTOR]" in command
    assert "AWS_SECRET_ACCESS_KEY=[MYSTERYBOX_SELECTOR]" in command
    assert payload["max_http_requests"] == 7
    assert payload["max_http_body_bytes"] == 0
    assert payload["s3_probe_size_limit_bytes"] == 256
    assert payload["storage_mounts"] == []
    assert payload["market_data_transferred"] is False
    assert command[command.index("--restart-policy") + 1] == "never"
    assert command[command.index("--platform") + 1] == "cpu-d3"
    assert command[command.index("--preset") + 1] == "4vcpu-16gb"
    assert command[command.index("--disk-size") + 1] == "100Gi"
    assert command[command.index("--timeout") + 1] == "1h"


def test_actual_submission_requires_publication_and_reviewed_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(market_data_wave1, "_git_commit", lambda: "0" * 40)
    package = tmp_path / "package"
    evidence_path = tmp_path / "package.json"
    market_data_wave1.prepare_c0(
        run_id="c0-submit-test",
        image=IMAGE,
        source_config=CONFIG,
        package=package,
        evidence_output=evidence_path,
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit, match="input-publication evidence"):
        submit_market_data_job.main(
            [
                "--image",
                IMAGE,
                "--name",
                "market-data-c0-submit-test",
                "--subnet-id",
                "subnet-test",
                "--input-uri",
                evidence["destination"],
                "--request-evidence",
                str(evidence_path),
                "--access-key-secret-id",
                "access-selector",
                "--secret-key-secret-id",
                "secret-selector",
                "--data-prep-spend-usd",
                "0",
                "--data-prep-jobs-consumed",
                "0",
                "--approval-reference",
                "chat:20260828:c0",
                "--evidence-output",
                str(tmp_path / "submission.json"),
            ]
        )


def _input_package(tmp_path: Path) -> tuple[Path, C0PreflightRequest]:
    input_root = tmp_path / "input"
    input_root.mkdir()
    staged_config = input_root / "nasdaq-public-sample-v1.json"
    staged_config.write_bytes(CONFIG.read_bytes())
    request = C0PreflightRequest(
        run_id="c0-test",
        image=IMAGE,
        git_commit="0" * 40,
        created_at="2026-08-28T00:00:00Z",
        source_config=config_artifact(staged_config),
        s3_probe_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            "preflight/c0-test/probe/probe.bin"
        ),
        result_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            "preflight/c0-test/result"
        ),
    )
    (input_root / "request.json").write_bytes(request.canonical_bytes())
    assert sha256_file(staged_config) == request.source_config.sha256
    return input_root, request
