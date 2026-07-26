from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.evaluation.governed_metrics import SessionMetricComponents


RELEASE_ARTIFACTS = (
    "benchmark-results.json",
    "session-metrics.jsonl",
    "benchmark-report.md",
    "validation-report.json",
    "signature.json",
    "validation-public-key.pem",
    "manifest.json",
    "manifest.sig",
    "checksums.sha256",
)


def write_governed_benchmark_release(
    output_dir: Path,
    *,
    results: dict[str, Any],
    session_metrics: list[SessionMetricComponents],
    validation: dict[str, Any],
    signing_key: Path | None,
    signer: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    if validation.get("verdict") != "pass":
        raise ValueError("governed benchmark release requires a passing validation report")
    if signing_key is not None and not signing_key.is_file():
        raise ValueError("governed benchmark signing key is missing")
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = [output_dir / name for name in RELEASE_ARTIFACTS]
    if not overwrite and any(path.exists() for path in targets):
        raise ValueError("governed benchmark release artifacts already exist")
    staging = output_dir / f".governed-release-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        _write_json(staging / "benchmark-results.json", results)
        (staging / "session-metrics.jsonl").write_text(
            "".join(
                json.dumps(asdict(item), sort_keys=True, separators=(",", ":")) + "\n"
                for item in sorted(session_metrics, key=lambda value: value.base_session_id)
            ),
            encoding="utf-8",
        )
        (staging / "benchmark-report.md").write_text(
            _benchmark_markdown(results, validation),
            encoding="utf-8",
        )
        _write_json(staging / "validation-report.json", validation)
        signature_names: list[str] = []
        if signing_key is not None:
            signature_names = _prepare_signature_metadata(
                staging,
                signing_key=signing_key,
                signer=signer,
            )
        inventory_names = [
            "benchmark-results.json",
            "session-metrics.jsonl",
            "benchmark-report.md",
            "validation-report.json",
            *signature_names,
        ]
        manifest = {
            "schema_version": "governed_benchmark_release_v1",
            "protocol_id": results["protocol_id"],
            "protocol_hash": results["protocol_hash"],
            "corpus_id": results["corpus_id"],
            "corpus_hash": results["corpus_hash"],
            "split_id": results["split_id"],
            "assignment_hash": results["assignment_hash"],
            "fold": results["fold"],
            "results_schema_version": results["schema_version"],
            "validation_verdict": validation["verdict"],
            "signed": signing_key is not None,
            "artifacts": _inventory(staging, inventory_names),
        }
        _write_json(staging / "manifest.json", manifest)
        if signing_key is not None:
            _sign_manifest(staging, signing_key)
            verify_governed_benchmark_release(staging)
        checksum_names = [
            *inventory_names,
            "manifest.json",
            *(["manifest.sig"] if signing_key is not None else []),
        ]
        (staging / "checksums.sha256").write_text(
            "".join(f"{_sha256(staging / name)}  {name}\n" for name in sorted(checksum_names)),
            encoding="utf-8",
        )
        published_names = [
            *inventory_names,
            "manifest.json",
            "checksums.sha256",
            *(["manifest.sig"] if signing_key is not None else []),
        ]
        for name in published_names:
            os.replace(staging / name, output_dir / name)
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_governed_benchmark_release(output_dir: Path) -> None:
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "governed_benchmark_release_v1":
        raise ValueError("unsupported governed benchmark release schema")
    if manifest.get("validation_verdict") != "pass":
        raise ValueError("governed benchmark release validation did not pass")
    inventory = manifest.get("artifacts")
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError("governed benchmark release inventory is missing")
    for name, expected in inventory.items():
        if not isinstance(name, str) or Path(name).name != name or not isinstance(expected, dict):
            raise ValueError("governed benchmark artifact inventory is invalid")
        artifact = output_dir / name
        if (
            not artifact.is_file()
            or artifact.stat().st_size != expected.get("size_bytes")
            or _sha256(artifact) != expected.get("sha256")
        ):
            raise ValueError(f"governed benchmark artifact failed integrity validation: {name}")
    if manifest.get("signed") is not True:
        raise ValueError("governed benchmark release is not signed")
    metadata = json.loads((output_dir / "signature.json").read_text(encoding="utf-8"))
    if (
        metadata.get("schema_version") != "governed_release_signature_v1"
        or metadata.get("algorithm") != "Ed25519"
        or metadata.get("signed_artifact") != "manifest.json"
    ):
        raise ValueError("governed benchmark signature metadata is invalid")
    public_key = output_dir / str(metadata.get("public_key_file"))
    signature = output_dir / str(metadata.get("signature_file"))
    if (
        public_key.name != metadata.get("public_key_file")
        or signature.name != metadata.get("signature_file")
        or metadata.get("key_id") != f"sha256:{_sha256(public_key)}"
    ):
        raise ValueError("governed benchmark signature key binding is invalid")
    completed = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-sigfile",
            str(signature),
            "-rawin",
            "-in",
            str(manifest_path),
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValueError("governed benchmark manifest signature verification failed")


def _prepare_signature_metadata(
    output_dir: Path,
    *,
    signing_key: Path,
    signer: str,
) -> list[str]:
    public_key = output_dir / "validation-public-key.pem"
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            str(signing_key),
            "-pubout",
            "-out",
            str(public_key),
        ],
        check=True,
        capture_output=True,
    )
    _write_json(
        output_dir / "signature.json",
        {
            "schema_version": "governed_release_signature_v1",
            "algorithm": "Ed25519",
            "signer": signer,
            "key_id": f"sha256:{_sha256(public_key)}",
            "signed_artifact": "manifest.json",
            "signature_file": "manifest.sig",
            "public_key_file": public_key.name,
        },
    )
    return ["signature.json", public_key.name]


def _sign_manifest(output_dir: Path, signing_key: Path) -> None:
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(signing_key),
            "-in",
            str(output_dir / "manifest.json"),
            "-out",
            str(output_dir / "manifest.sig"),
        ],
        check=True,
        capture_output=True,
    )


def _benchmark_markdown(results: dict[str, Any], validation: dict[str, Any]) -> str:
    metrics = results["metrics"]
    return "\n".join(
        (
            "# Governed ML Benchmark Report",
            "",
            f"- Protocol: `{results['protocol_id']}`",
            f"- Corpus: `{results['corpus_id']}`",
            f"- Split: `{results['split_id']}` / `{results['fold']}`",
            f"- Validation: **{validation['verdict'].upper()}**",
            "",
            "## Headline metrics",
            "",
            f"- Precision: `{metrics.get('precision')}`",
            f"- Recall / attack-level recall: `{metrics.get('attack_level_recall')}`",
            f"- F1: `{metrics.get('f1')}`",
            f"- False alerts per million events: `{metrics.get('false_alerts_per_million_events')}`",
            f"- Detection before benefit: `{metrics.get('detection_before_benefit_rate')}`",
            f"- Duplicate alert load: `{metrics.get('duplicate_alert_load')}`",
            "",
            "Confidence intervals, regime cells, worst-decile sessions, complete",
            "input hashes, and exclusions are recorded in `benchmark-results.json`.",
            "",
        )
    )


def _inventory(output_dir: Path, names: list[str]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "sha256": _sha256(output_dir / name),
            "size_bytes": (output_dir / name).stat().st_size,
        }
        for name in sorted(names)
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
