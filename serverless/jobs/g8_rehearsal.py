"""Offline C4-shaped scoring rehearsal; never authorizes a production evaluation.

Run with the *unmodified pinned image*, mounting this file and run_lightgbm_g8.py.
Only transport is replaced: no loader, model, calibration, signature or release
verification is mocked. Local MLflow is real; authenticated remote MLflow and
remote S3 still require a separate live smoke test before final access.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from app.market_data.projections import (
    C4MlflowDatasetReleaseReceipt,
    EXPECTED_SOURCE_DATES,
    EXPECTED_SOURCE_FILES,
    EXPECTED_SOURCE_FOLDS,
    FrozenPublicSampleRoot,
    FrozenSourceBinding,
    TabularProjectionManifest,
    materialize_tabular_shard,
    write_manifest,
)
from app.ml.lightgbm import cloud_runner
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import (
    CloudArtifact,
    LightGbmCloudJobRequest,
    Wave1ExperimentSpec,
    Wave1FinalAuthorization,
    Wave1TabularProjectionInput,
)
from app.ml.lightgbm.cloud_fixture import build_wave1_fixture_dataset, fixture_hash


IMAGE = "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/lob-arena-jobs@sha256:dc32b12d7216bfeef8e5d95c50363f34bb76f34159ef9343ff3d6996983a89b2"
CAMPAIGN = "g8-synthetic-rehearsal"
RESULTS = "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/" + CAMPAIGN
FINAL = "s3://aimada-wave1-final-e00g6zvxpr00/releases/g8-synthetic-rehearsal/staging"


def artifact(path: Path, root: Path, name: str) -> CloudArtifact:
    return CloudArtifact(
        logical_name=name,
        uri=path.relative_to(root).as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def projections(output: Path) -> tuple[Path, Path]:
    """Generate only synthetic rows; mirror C4's artifacts/tabular/<fold> layout."""
    root = FrozenPublicSampleRoot(
        release_id=CAMPAIGN,
        protocol_sha256=fixture_hash("protocol"),
        corpus_id=CAMPAIGN,
        corpus_sha256=fixture_hash("corpus"),
        split_id=CAMPAIGN,
        assignment_sha256=fixture_hash("assignment"),
        feature_release_id=CAMPAIGN,
        feature_release_sha256=fixture_hash("features"),
        feature_config_sha256=fixture_hash("wave1-fixture-feature-config"),
        source_config_sha256=fixture_hash("source"),
        sources=tuple(
            FrozenSourceBinding(
                trade_date=day,
                fold=fold,
                filename=name,
                source_sha256=fixture_hash(name),
                source_manifest_sha256=fixture_hash(name + "manifest"),
                preparation_manifest_sha256=fixture_hash(name + "preparation"),
                parser_config_sha256=fixture_hash("parser"),
            )
            for day, fold, name in zip(EXPECTED_SOURCE_DATES, EXPECTED_SOURCE_FOLDS, EXPECTED_SOURCE_FILES, strict=True)
        ),
    )
    packages = []
    for scope in ("development", "final_test"):
        package = output / scope
        manifests = package / "manifests"
        manifests.mkdir(parents=True)
        write_manifest(manifests / "frozen-root.json", root)
        dataset = build_wave1_fixture_dataset(output / "source" / scope, access_mode=scope)
        shards = []
        for fold in dataset.folds:
            for shard in fold.shards:
                table = pq.read_table(shard.feature_path)
                rows = table.to_pylist()
                for row in rows:
                    if row["label"] == 0:
                        row["label_source"] = "research_control_assumption"
                pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), shard.feature_path)
                shards.append(
                    materialize_tabular_shard(
                        shard.feature_path,
                        package / "artifacts" / "tabular" / fold.fold / (shard.run_id + ".parquet"),
                        artifact_root=package / "artifacts",
                        root_sha256=root.canonical_hash(),
                        assignment_sha256=root.assignment_sha256,
                        replay_sha256=fixture_hash(shard.run_id),
                        fold=fold.fold,
                        base_session_id=shard.base_session_id,
                        campaign_id=shard.campaign_id,
                        run_id=shard.run_id,
                    )
                )
        write_manifest(
            manifests / "tabular-projection.json",
            TabularProjectionManifest(
                projection_id=CAMPAIGN + "-" + scope.replace("_", "-"),
                access_scope=scope,
                root_release_id=root.release_id,
                root_sha256=root.canonical_hash(),
                protocol_sha256=root.protocol_sha256,
                corpus_sha256=root.corpus_sha256,
                assignment_sha256=root.assignment_sha256,
                feature_release_sha256=root.feature_release_sha256,
                folds=tuple(fold.fold for fold in dataset.folds),
                shards=tuple(shards),
            ),
        )
        packages.append(package)
    receipt = C4MlflowDatasetReleaseReceipt(
        mlflow_run_id="0" * 32,
        release_id=root.release_id,
        root_file_sha256=sha256_file(packages[0] / "manifests/frozen-root.json"),
        root_identity_sha256=root.canonical_hash(),
        tabular_development_sha256=sha256_file(packages[0] / "manifests/tabular-projection.json"),
        tabular_final_sha256=sha256_file(packages[1] / "manifests/tabular-projection.json"),
        sequence_development_sha256=fixture_hash("unused synthetic sequence development"),
        sequence_final_sha256=fixture_hash("unused synthetic sequence final"),
        access_denial_sha256=fixture_hash("offline network disabled"),
    )
    for package in packages:
        write_manifest(package / "manifests/c4-mlflow-dataset-release.json", receipt)
    return packages[0], packages[1]


def projected_input(package: Path) -> Wave1TabularProjectionInput:
    return Wave1TabularProjectionInput(
        frozen_root=artifact(package / "manifests/frozen-root.json", package, "root"),
        projection=artifact(package / "manifests/tabular-projection.json", package, "projection"),
        dataset_lineage_receipt=artifact(package / "manifests/c4-mlflow-dataset-release.json", package, "lineage"),
        projection_artifact_root="artifacts",
    )


def rehearse(output: Path, runner_path: Path, *, wrong_root: bool = False) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location("g8_rehearsed_runner", runner_path)
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    development, final_input = projections(output)
    selected = output / "selected"
    common = dict(
        campaign_id=CAMPAIGN,
        project_id="project-e00g6zvxpr00waz8t3y51k",
        image=IMAGE,
        created_at=datetime.now(UTC),
        git_commit="0" * 40,
        experiment=Wave1ExperimentSpec(calibration_method="isotonic"),
    )
    request = LightGbmCloudJobRequest(
        **common,
        run_id="synthetic-development",
        mode="development",
        input=projected_input(development),
        result_uri=selected.as_uri(),
    )
    request_path = development / "request.json"
    request_path.write_bytes(request.canonical_bytes())
    cloud_runner.execute_wave1_request(request_path, input_root=development)
    cloud_runner.verify_wave1_result(selected)
    auth_dir = output / "authorization"
    auth_dir.mkdir()
    auth = auth_dir / "authorization.json"
    signature = auth_dir / "authorization.sig"
    public = auth_dir / "authorization-public.pem"
    candidate_hash = sha256_file(selected / "candidate.json")
    signed_at = datetime.now(UTC)
    auth.write_bytes(
        Wave1FinalAuthorization(
            campaign_id=CAMPAIGN,
            candidate_hash=candidate_hash,
            # The frozen schema fixes this label. The synthetic candidate and
            # ephemeral trust key cannot authorize the production candidate.
            signer="Alexey Khabalov — Wave 1 Release Approver",
            signed_at=signed_at,
            statement=f"APPROVE WAVE1 FINAL TEST {candidate_hash} {signed_at.isoformat()}",
        ).canonical_bytes()
    )
    with tempfile.TemporaryDirectory() as temporary:
        private = str(Path(temporary) / "key.pem")
        for command in (
            ["genpkey", "-algorithm", "Ed25519", "-out", private],
            ["pkey", "-in", private, "-pubout", "-out", str(public)],
            ["pkeyutl", "-sign", "-inkey", private, "-rawin", "-in", str(auth), "-out", str(signature)],
        ):
            subprocess.run(["openssl", *command], check=True, capture_output=True)
    final_projection = projected_input(final_input)
    if wrong_root:
        final_projection = final_projection.model_copy(update={"projection_artifact_root": "projection-artifacts"})
    final_request = LightGbmCloudJobRequest(
        **common,
        run_id="synthetic-final",
        mode="final-evaluation",
        input=final_projection,
        input_release_uri=FINAL,
        result_uri=RESULTS + "/final/synthetic-final",
        candidate=CloudArtifact(
            logical_name="candidate",
            uri="candidate/candidate.json",
            sha256=candidate_hash,
            size_bytes=(selected / "candidate.json").stat().st_size,
        ),
        authorization=artifact(auth, output, "authorization"),
        authorization_signature=artifact(signature, output, "signature"),
        authorization_public_key=artifact(public, output, "public_key"),
        mlflow_tracking_uri="http://10.4.0.54:5500",
    )
    final_request_path = output / "request.json"
    final_request_path.write_bytes(final_request.canonical_bytes())
    argv = [
        str(runner_path),
        "--request",
        str(final_request_path),
        "--authorization",
        str(auth),
        "--authorization-signature",
        str(signature),
        "--authorization-public-key",
        str(public),
        "--dataset-lineage",
        str(final_input / "manifests/c4-mlflow-dataset-release.json"),
        "--final-input-uri",
        FINAL,
        "--candidate-uri",
        RESULTS + "/development/selected",
        "--work-root",
        str(output / "work"),
    ]
    environment = {
        "MLFLOW_ALLOW_FILE_STORE": "true",
        "WAVE1_ACTUAL_PROJECT_ID": common["project_id"],
        "WAVE1_ACTUAL_IMAGE_REPOSITORY": IMAGE.split("@sha256:")[0],
        "WAVE1_ACTUAL_IMAGE_SHA256": IMAGE.split("@sha256:")[1],
        "WAVE1_ACTUAL_PLATFORM": "cpu-d3",
        "WAVE1_ACTUAL_PRESET": "4vcpu-16gb",
        "WAVE1_ACTUAL_DISK_SIZE_GIB": "100",
        "WAVE1_ACTUAL_TIMEOUT_SECONDS": "3600",
        "WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256": sha256_file(public),
    }
    downloads = []

    def download(uri, destination, **kwargs):
        downloads.append(uri)
        source = {FINAL: final_input, RESULTS + "/development/selected": selected}[uri]
        shutil.copytree(source, destination)

    tracking_uri = (output / "mlruns").as_uri()
    original_log = cloud_runner.log_governed_evaluation_run

    def log(**kwargs):
        kwargs["tracking_uri"] = tracking_uri
        return original_log(**kwargs)

    published = output / "published"
    objects = {}
    hashes = {}
    puts = []

    def aws_json(endpoint, *args):
        # Same positional-only calling convention as the frozen helper.
        key = args[args.index("--key") + 1]
        operation = args[1]
        if operation == "put-object":
            if args[args.index("--if-none-match") + 1] != "*" or key in objects:
                raise AssertionError("publication attempted an overwrite")
            objects[key] = Path(args[args.index("--body") + 1]).read_bytes()
            hashes[key] = args[args.index("--metadata") + 1].removeprefix("sha256=")
            puts.append(key)
            return {}
        if operation == "head-object":
            return {"ContentLength": len(objects[key]), "Metadata": {"sha256": hashes[key]}}
        if operation == "get-object":
            Path(args[-1]).write_bytes(objects[key])
            return {}
        if operation == "delete-object":
            objects.pop(key, None)
            return {}
        raise AssertionError("unexpected S3 operation: " + operation)

    original_publish = runner.publish_s3_result

    def publish(source, *args, **kwargs):
        cloud_runner.verify_wave1_result(source)
        original_publish(source, *args, **kwargs)
        prefix = "campaigns/" + CAMPAIGN + "/final/synthetic-final/"
        for key, content in objects.items():
            target = published / key.removeprefix(prefix)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        if not puts or puts[-1] != prefix + "SUCCESS":
            raise AssertionError("result marker was not published last")

    with (
        patch.dict(os.environ, environment),
        patch.object(sys, "argv", argv),
        patch.object(runner, "download_s3_release", download),
        patch.object(runner, "_verify_mlflow_ready"),
        patch.object(
            runner, "_require_empty_result", return_value=runner.S3PublicationIntent(final_request.result_uri)
        ),
        patch.object(runner, "publish_s3_result", publish),
        patch.object(runner, "publish_s3_failure"),
        patch.object(runner.object_storage, "_aws_json", aws_json),
        patch.object(cloud_runner, "log_governed_evaluation_run", log),
    ):
        runner.main()
    run = cloud_runner.verify_wave1_result(published)
    if downloads.count(FINAL) != 1 or not run.mlflow_run_id:
        raise AssertionError("rehearsal did not score once and log a verified release")
    from mlflow import MlflowClient

    with patch.dict(os.environ, {"MLFLOW_ALLOW_FILE_STORE": "true"}):
        client = MlflowClient(tracking_uri=tracking_uri)
    logged = client.get_run(run.mlflow_run_id)
    if logged.info.status != "FINISHED":
        raise AssertionError("MLflow run did not finish")
    # Real artifact and metric round-trips, not just presence of an MLflow ID.
    for relative in ("prediction/prediction-manifest.json", "bundle/model-bundle.json", "bundle/checksums.sha256"):
        readback = Path(client.download_artifacts(run.mlflow_run_id, "governed/" + Path(relative).name, str(output)))
        if sha256_file(readback) != sha256_file(published / "artifacts" / relative):
            raise AssertionError("MLflow artifact readback differs: " + relative)
    metrics = json.loads((published / "metrics.json").read_text())
    for remote_name, local_name in (
        ("test_row_count", "test_row_count"),
        ("test_alert_count", "test_alert_count"),
        ("frozen_threshold", "threshold"),
    ):
        if logged.data.metrics.get(remote_name) != metrics[local_name]:
            raise AssertionError("MLflow metric readback differs: " + remote_name)
    experiment = client.get_experiment_by_name("lob-arena/governed-evaluation")
    if len(client.search_runs([experiment.experiment_id])) != 1:
        raise AssertionError("rehearsal created more than one MLflow evaluation run")
    runner._runtime_compatibility_check()
    receipt = dict(
        schema_version="g8_synthetic_rehearsal_v1",
        production_test_accessed=False,
        runner_sha256=sha256_file(runner_path),
        rehearsal_sha256=sha256_file(Path(__file__)),
        request_image=IMAGE,
        mlflow_run_id=run.mlflow_run_id,
        local_mlflow_status=logged.info.status,
        final_download_count=downloads.count(FINAL),
        release_verified=True,
        mlflow_artifact_readback_verified=True,
        mlflow_metric_readback_verified=True,
        publication_object_count=len(puts),
        conditional_publication_verified=True,
        remote_authentication_verified=False,
        remote_storage_verified=False,
        rules_comparison_verified=False,
        production_g8_complete=False,
    )
    (output / "rehearsal.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runner", type=Path, default=Path(__file__).with_name("run_lightgbm_g8.py"))
    parser.add_argument("--wrong-root", action="store_true", help="Negative control: reproduce R4 before scoring")
    args = parser.parse_args()
    print(json.dumps(rehearse(args.output, args.runner, wrong_root=args.wrong_root), indent=2))
