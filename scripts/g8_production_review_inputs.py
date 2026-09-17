"""Read frozen production metadata and prior evidence without model or cloud access."""
from __future__ import annotations

import hashlib
import json


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def collect(r4, candidate, rehearsal, constants, run_id):
    request = read(r4 / "preflight/request.json")
    if (request["run_id"] != "nasdaq-g8-final-r4-20260913" or run_id == request["run_id"]
            or request["image"] != constants["IMAGE"]
            or request["candidate"]["sha256"] != constants["CANDIDATE"]
            or request["input_release_uri"] != constants["FINAL_RELEASE"]
            or request["input"]["frozen_root"]["sha256"] != constants["FROZEN_ROOT"]
            or request["input"]["projection"]["sha256"] != constants["FINAL_PROJECTION"]):
        raise ValueError("R4 request differs from frozen production identities")
    candidate_raw = candidate.read_bytes()
    if digest(candidate_raw) != constants["CANDIDATE"]:
        raise ValueError("frozen candidate changed")
    frozen = json.loads(candidate_raw)
    if frozen["experiment"] != request["experiment"]:
        raise ValueError("R4 experiment differs from frozen candidate")
    artifacts = r4 / "result/artifacts"
    calibration_raw = (artifacts / frozen["calibration_manifest"]["uri"]).read_bytes()
    features_raw = (artifacts / frozen["feature_schema"]["uri"]).read_bytes()
    if (digest(calibration_raw) != frozen["calibration_manifest"]["sha256"]
            or digest(features_raw) != frozen["feature_schema"]["sha256"]):
        raise ValueError("frozen calibration/features changed")
    calibration = json.loads(calibration_raw)
    history = {}
    for name, expected in {
        "monitor.json": "e6975dcd517dda25b91a0b6bea9a786c87f7d82a451fcb71a8dcc34355016b72",
        "monitor.logs.txt": "eadddbdbac943939a9b8243398584ac8866352b30117ef7ea0e3fb9ed9ac2a8c",
    }.items():
        raw = (r4 / name).read_bytes()
        if digest(raw) != expected:
            raise ValueError("R4 execution history changed")
        history[name] = raw
    observed = read(r4 / "nebius-readback.json")
    if observed["metadata"]["id"] != "aijob-e00vtamgkr07mwzt4t":
        raise ValueError("wrong R4 Job")
    selectors = {item["name"]: item["mysterybox_secret"]["secret_id"] + "@" +
                 item["mysterybox_secret"]["version_id"] for item in observed["spec"]["environment_variables"]
                 if "mysterybox_secret" in item}
    if len(selectors) != 4:
        raise ValueError("four historical secret selectors required")
    mlflow = read(rehearsal / "independent-mlflow.json")
    s3_path = rehearsal / "independent-s3-reader/verification.json"
    s3 = read(s3_path)
    snapshot = read(rehearsal / "independent-native-snapshot.json")
    reattachment = snapshot["native-evidence/job-reattachment.json"]["value"]
    runtime = snapshot["native-evidence/recover-runtime.json"]["value"]
    if (mlflow["status"] != "FINISHED" or mlflow["metric_count"] != 24
            or mlflow["dataset_input_count"] != 30 or len(mlflow["artifact_hashes"]) != 4
            or s3["object_count"] != 64 or not s3["all_object_bytes_and_hashes_verified"]
            or not s3["mlflow_run_and_c4_artifact_crosschecked"]
            or not reattachment["native_checkpoint_reattachment_verified"]
            or runtime["filesystem_id"] != reattachment["filesystem_id"]):
        raise ValueError("completed independent rehearsal evidence required")
    history.update({"request.json": (r4 / "preflight/request.json").read_bytes(),
                    "nebius-readback.json": (r4 / "nebius-readback.json").read_bytes()})
    lineage_raw = (r4 / "preflight/manifests/c4-mlflow-dataset-release.json").read_bytes()
    if digest(lineage_raw) != request["input"]["dataset_lineage_receipt"]["sha256"]:
        raise ValueError("retained dataset lineage changed")
    native = {"filesystem_id": runtime["filesystem_id"], "mount_source": runtime["mount"]["source"],
              "mount_type": runtime["mount"]["type"], "capacity_gib": 10,
              "job_loss_reattachment_verified": True, "verified_at": s3["verified_at"],
              "snapshot_sha256": digest((rehearsal / "independent-native-snapshot.json").read_bytes())}
    remote = {"authenticated_mlflow_artifact_readback": True, "authenticated_s3_readback": True,
              "tracking_uri": request["mlflow_tracking_uri"], "image": constants["IMAGE"],
              "verified_at": s3["verified_at"], "mlflow_receipt_sha256": digest((rehearsal / "independent-mlflow.json").read_bytes()),
              "s3_receipt_sha256": digest(s3_path.read_bytes())}
    bindings = {"run_id": run_id, "candidate_sha256": constants["CANDIDATE"], "image": constants["IMAGE"],
        "calibration_manifest_sha256": digest(calibration_raw), "feature_schema_sha256": digest(features_raw),
        "calibration_method": frozen["experiment"]["calibration_method"],
        "operating_mode": frozen["experiment"]["operating_mode"],
        "thresholds": {point["mode"]: point["threshold"] for point in calibration["operating_points"]},
        "prior_run_id": request["run_id"], "prior_job_id": observed["metadata"]["id"],
        "prior_final_jobs_submitted": 4, "prior_test_fold_accessed": True,
        "prior_monitor_sha256": digest(history["monitor.json"]), "prior_log_sha256": digest(history["monitor.logs.txt"]),
        "replacement_executions_allowed": 1, "no_retraining_recalibration_or_threshold_changes": True,
        "secret_selectors_from_r4_not_live_revalidated": selectors,
        "candidate_release_uri": read(r4 / "preflight/g8-preflight.json")["candidate_release_uri"],
        "filesystem_id": native["filesystem_id"], "mount_source": native["mount_source"],
        "mount_type": "virtiofs", "capacity_gib": 10}
    for field in ("authorization", "authorization_signature", "authorization_public_key"):
        request[field] = None  # Consumed R4 approval is history, never replacement authority.
    request["run_id"] = run_id
    request["result_uri"] = f"s3://aimada-wave1-results-e00g6zvxpr00/campaigns/{request['campaign_id']}/final/{run_id}"
    request["input"]["projection_artifact_root"] = "artifacts"
    return bindings, request, {"candidate.json": candidate_raw, "dataset-lineage.json": lineage_raw}, {
        "calibration-manifest.json": calibration_raw, "feature-schema.json": features_raw,
        **{"r4/" + name: raw for name, raw in history.items()}}, native, remote
