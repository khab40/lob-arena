import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.ground_truth import (  # noqa: E402
    binary_classification_metrics,
    evaluate_detection,
)
from app.evaluation.hybrid_validation import build_hybrid_validation  # noqa: E402

GENERATED_ARTIFACT_NAMES = {
    "checksums.sha256",
    "comparison.json",
    "control.json",
    "hybrid.json",
    "manifest.json",
    "manifest.sig",
    "signature.json",
    "validation-public-key.pem",
    "validation-report.json",
    "validation-report.sig",
}


def build_comparison(raw: dict[str, Any]) -> dict[str, Any]:
    control = raw["control"]
    hybrid = raw["hybrid"]
    detector_names = sorted(
        set(control.get("detector_alert_ticks", {}))
        | set(hybrid.get("detector_alert_ticks", {}))
        | {
            "spoofing_like_detector",
            "layering_like_detector",
            "quote_stuffing_detector",
            "liquidity_shock_detector",
        }
    )
    metrics: list[dict[str, Any]] = []
    for detector in detector_names:
        control_predicted = bool(control.get("detector_alert_ticks", {}).get(detector))
        hybrid_predicted = bool(hybrid.get("detector_alert_ticks", {}).get(detector))
        control_ticks = control.get("detector_alert_ticks", {}).get(detector, [])
        hybrid_ticks = hybrid.get("detector_alert_ticks", {}).get(detector, [])
        classification = binary_classification_metrics(
            tp=int(hybrid_predicted),
            fp=int(control_predicted),
            fn=int(not hybrid_predicted),
            tn=int(not control_predicted),
        )
        metrics.append(
            {
                "detector": detector,
                **classification,
                "control_alert_ticks": control_ticks,
                "hybrid_alert_ticks": hybrid_ticks,
                "control_evaluation": evaluate_detection(
                    alert_ticks=control_ticks, label=None
                ),
                "hybrid_evaluation": evaluate_detection(
                    alert_ticks=hybrid_ticks,
                    label=hybrid.get("ground_truth"),
                ),
            }
        )
    return {
        "schema_version": "historical_replay_metrics_v1",
        "dataset_id": raw["dataset_id"],
        "master_seed": raw.get("master_seed", 42),
        "events_sha256": raw["events_sha256"],
        "same_historical_window": (
            control["source_rows_replayed"] == hybrid["source_rows_replayed"]
            and control["events_sha256"] == raw["events_sha256"]
            and hybrid["events_sha256"] == raw["events_sha256"]
        ),
        "event_counts": {
            "control": control["canonical_event_count"],
            "hybrid": hybrid["canonical_event_count"],
            "delta": raw["realism_impact"]["canonical_event_count_delta"],
        },
        "detector_metrics": metrics,
        "realism_impact": raw["realism_impact"],
    }


def write_bundle(
    raw: dict[str, Any],
    output: Path,
    *,
    signing_key: Path | None = None,
    signer: str | None = None,
) -> dict[str, Any]:
    if signing_key is not None and not signing_key.is_file():
        raise ValueError("bundle signing key does not exist or is not a regular file")
    output.mkdir(parents=True, exist_ok=True)
    for name in GENERATED_ARTIFACT_NAMES:
        candidate = output / name
        if candidate.is_file():
            candidate.unlink()
    comparison = build_comparison(raw)
    artifacts = {
        "control.json": raw["control"],
        "hybrid.json": raw["hybrid"],
        "comparison.json": comparison,
    }
    if raw["control"].get("validation_trace") is not None:
        artifacts["validation-report.json"] = build_hybrid_validation(raw)
    for name, payload in artifacts.items():
        _write_json(output / name, payload)
    signature_artifacts: list[str] = []
    if signing_key is not None:
        if "validation-report.json" not in artifacts:
            raise ValueError(
                "a validation trace is required before the report can be signed"
            )
        signature_artifacts = _prepare_bundle_signature(
            output,
            signing_key=signing_key,
            signer=signer or "unspecified",
        )
    inventory_names = [*artifacts, *signature_artifacts]
    manifest = {
        "schema_version": "historical_replay_bundle_v2",
        "dataset_id": raw["dataset_id"],
        "master_seed": raw.get("master_seed", 42),
        "events_sha256": raw["events_sha256"],
        "source_integrity": raw["control"].get("source_integrity"),
        "source_counts": {
            "row_count": raw["control"].get("source_row_count"),
            "rows_replayed": raw["control"].get("source_rows_replayed"),
            "historical_source_sequences": raw["control"].get(
                "historical_source_sequences"
            ),
        },
        "injection_schedule": raw.get("injection_schedule"),
        "synthetic_lifecycle": artifacts.get("validation-report.json", {})
        .get("checks", {})
        .get("injected_order_lifecycle"),
        "artifacts": _artifact_inventory(output, inventory_names),
        "validation_verdict": artifacts.get("validation-report.json", {}).get(
            "verdict"
        ),
        "signed": bool(signature_artifacts),
    }
    _write_json(output / "manifest.json", manifest)
    if signing_key is not None:
        sign_bundle_manifest(output, signing_key=signing_key)
        verify_bundle_signature(output)
    checksum_files = [
        *sorted(inventory_names),
        "manifest.json",
        *(["manifest.sig"] if signing_key is not None else []),
    ]
    (output / "checksums.sha256").write_text(
        "".join(f"{_sha256(output / name)}  {name}\n" for name in checksum_files),
        encoding="utf-8",
    )
    return comparison


def run(args: argparse.Namespace) -> dict[str, Any]:
    payload = json.dumps(
        {
            "dataset_id": args.dataset,
            "scenario_family": args.scenario,
            "max_ticks": args.max_ticks,
            "master_seed": args.master_seed,
            "trigger_source_sequence": args.trigger_source_sequence,
            "trigger_timestamp_ns": args.trigger_timestamp_ns,
            "scenario_parameters": json.loads(args.scenario_parameters),
        }
    ).encode()
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/api/arena/replay-comparison",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw = json.load(response)
    except urllib.error.URLError as exception:
        raise SystemExit(
            f"historical replay request failed: {exception}"
        ) from exception
    return write_bundle(
        raw,
        args.output,
        signing_key=args.signing_key,
        signer=args.signer,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Java historical control and hybrid replay and write checksummed comparison artifacts."
    )
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--dataset", default="sample-btcusdt-0945")
    parser.add_argument("--scenario", default="spoofing_like_wall")
    parser.add_argument("--max-ticks", type=int, default=10_000)
    parser.add_argument("--master-seed", type=int, default=42)
    trigger = parser.add_mutually_exclusive_group()
    trigger.add_argument("--trigger-source-sequence", type=int)
    trigger.add_argument("--trigger-timestamp-ns", type=int)
    parser.add_argument(
        "--scenario-parameters",
        default="{}",
        help="JSON object overriding bounded parameters for the selected existing scenario",
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "outputs" / "historical-replay"
    )
    parser.add_argument(
        "--signing-key",
        type=Path,
        help="PEM Ed25519 private key used to sign the bundle manifest",
    )
    parser.add_argument(
        "--signer",
        default="LOB Arena validation",
        help="Signer identity recorded in signature.json",
    )
    return parser.parse_args()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_inventory(output: Path, names: list[str]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "sha256": _sha256(output / name),
            "size_bytes": (output / name).stat().st_size,
        }
        for name in sorted(names)
    }


def _prepare_bundle_signature(
    output: Path,
    *,
    signing_key: Path,
    signer: str,
) -> list[str]:
    public_key = output / "validation-public-key.pem"
    metadata = output / "signature.json"
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
        metadata,
        {
            "schema_version": "hybrid_bundle_signature_v1",
            "algorithm": "Ed25519",
            "signer": signer,
            "key_id": f"sha256:{_sha256(public_key)}",
            "signed_artifact": "manifest.json",
            "signature_file": "manifest.sig",
            "public_key_file": public_key.name,
        },
    )
    return [public_key.name, metadata.name]


def sign_bundle_manifest(output: Path, *, signing_key: Path) -> None:
    manifest = output / "manifest.json"
    signature = output / "manifest.sig"
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(signing_key),
            "-in",
            str(manifest),
            "-out",
            str(signature),
        ],
        check=True,
        capture_output=True,
    )


def verify_bundle_signature(output: Path) -> None:
    metadata = json.loads((output / "signature.json").read_text(encoding="utf-8"))
    if metadata.get("schema_version") != "hybrid_bundle_signature_v1":
        raise ValueError("unsupported bundle signature metadata schema")
    if metadata.get("algorithm") != "Ed25519":
        raise ValueError("unsupported bundle signature algorithm")
    if metadata.get("signed_artifact") != "manifest.json":
        raise ValueError("bundle signature metadata must bind manifest.json")
    public_key_name = metadata.get("public_key_file")
    signature_name = metadata.get("signature_file")
    if (
        not isinstance(public_key_name, str)
        or Path(public_key_name).name != public_key_name
        or not isinstance(signature_name, str)
        or Path(signature_name).name != signature_name
    ):
        raise ValueError("bundle signature files must be local basenames")
    public_key = output / public_key_name
    if metadata.get("key_id") != f"sha256:{_sha256(public_key)}":
        raise ValueError("bundle signing key does not match signature metadata")
    manifest_path = output / "manifest.json"
    completed = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-sigfile",
            str(output / signature_name),
            "-rawin",
            "-in",
            str(manifest_path),
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValueError("bundle manifest signature verification failed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "historical_replay_bundle_v2":
        raise ValueError("unsupported signed bundle manifest schema")
    if manifest.get("signed") is not True:
        raise ValueError("signed bundle manifest is not marked as signed")
    required = {
        "comparison.json",
        "control.json",
        "hybrid.json",
        "signature.json",
        "validation-public-key.pem",
        "validation-report.json",
    }
    inventory = manifest.get("artifacts")
    if not isinstance(inventory, dict) or not required.issubset(inventory):
        raise ValueError("signed bundle manifest has an incomplete artifact inventory")
    for name, expected in inventory.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("signed bundle artifact names must be local basenames")
        if not isinstance(expected, dict):
            raise ValueError(f"signed bundle artifact metadata is invalid: {name}")
        expected_size = expected.get("size_bytes")
        expected_hash = expected.get("sha256")
        if (
            not isinstance(expected_size, int)
            or expected_size < 0
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(character not in "0123456789abcdef" for character in expected_hash)
        ):
            raise ValueError(f"signed bundle artifact metadata is invalid: {name}")
        artifact = output / name
        if not artifact.is_file():
            raise ValueError(f"signed bundle artifact is missing: {name}")
        if artifact.stat().st_size != expected_size:
            raise ValueError(f"signed bundle artifact size mismatch: {name}")
        if _sha256(artifact) != expected_hash:
            raise ValueError(f"signed bundle artifact checksum mismatch: {name}")


if __name__ == "__main__":
    print(json.dumps(run(parse_args()), indent=2, sort_keys=True))
