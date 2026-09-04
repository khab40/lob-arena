from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.features.models import FeaturePipelineConfig
from app.market_data.acquisition import _require_environment
from app.market_data.preparation import (
    ATTACK_FAMILIES,
    FEATURE_CONFIG,
    SEEDS,
    SYMBOLS,
    WINDOW_END_MS,
    WINDOW_START_MS,
    PreparationManifest,
    NasdaqPreparationRequest,
)
from app.market_data.preparation_checkpoints import (
    ComparisonCheckpoint,
    PreparationCheckpointBinding,
    inventory_model_evidence,
)
from app.market_data.projections import (
    EXPECTED_SOURCE_DATES,
    EXPECTED_SOURCE_FILES,
    EXPECTED_SOURCE_FOLDS,
    FrozenPublicSampleRoot,
    FrozenSourceBinding,
    SequenceProjectionManifest,
    TabularProjectionManifest,
    materialize_sequence_shard,
    materialize_tabular_shard,
    load_tabular_projection_dataset,
    verify_sequence_projection,
    verify_tabular_projection,
    write_manifest,
)
from app.market_data.public_sample import (
    DEVELOPMENT_BUCKET,
    OBJECT_STORAGE_ENDPOINT,
    PROJECT_ID,
    PUBLIC_SAMPLE_PREFIX,
)
from app.ml.lightgbm.cloud_contracts import IMMUTABLE_IMAGE_PATTERN
from app.ml.lightgbm.contracts import GIT_COMMIT_PATTERN, IDENTIFIER_PATTERN, SHA256_PATTERN
from app.nebius.job_logging import JobLogger
from app.nebius.object_storage import (
    TransferLimits,
    download_s3_release,
    download_verified_s3_release_members,
    publish_local_result,
    publish_s3_result,
    sha256_file,
    verify_complete_result,
)


JOB_LOG = JobLogger("market-data-projection-freeze")
FINAL_BUCKET = "aimada-wave1-final-e00g6zvxpr00"
FOLDS = tuple(EXPECTED_SOURCE_FOLDS)
SEQUENCE_LENGTH = 64


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class PreparedReleaseBinding(_StrictModel):
    sequence_number: int = Field(ge=1, le=4)
    trade_date: date
    fold: Literal["train", "validation", "test"]
    filename: str = Field(min_length=1)
    result_uri: str
    preparation_sha256: str = Field(pattern=SHA256_PATTERN)


class ProjectionFreezeLimits(_StrictModel):
    prepared_max_files: Literal[8] = 8
    prepared_max_bytes: Literal[4_194_304] = 4_194_304
    checkpoint_max_files: Literal[100] = 100
    checkpoint_max_bytes: Literal[8_589_934_592] = 8_589_934_592
    selected_checkpoint_max_files: Literal[16] = 16
    selected_checkpoint_max_bytes: Literal[16_777_216] = 16_777_216
    result_max_files: Literal[512] = 512
    result_max_bytes: Literal[2_147_483_648] = 2_147_483_648


class ProjectionFreezeResourceRequest(_StrictModel):
    platform: Literal["cpu-d3"] = "cpu-d3"
    preset: Literal["4vcpu-16gb"] = "4vcpu-16gb"
    cpu_count: Literal[4] = 4
    memory_gib: Literal[16] = 16
    disk_size_gib: Literal[100] = 100
    timeout_seconds: Literal[14_400] = 14_400
    gpu_count: Literal[0] = 0


class NasdaqProjectionFreezeRequest(_StrictModel):
    schema_version: Literal["market_data_wave1_projection_freeze_request_v1"] = (
        "market_data_wave1_projection_freeze_request_v1"
    )
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    release_id: str = Field(pattern=IDENTIFIER_PATTERN)
    project_id: Literal["project-e00g6zvxpr00waz8t3y51k"] = PROJECT_ID
    region: Literal["eu-north1"] = "eu-north1"
    image: str = Field(pattern=IMMUTABLE_IMAGE_PATTERN)
    git_commit: str = Field(pattern=GIT_COMMIT_PATTERN)
    created_at: AwareDatetime
    source_config_sha256: str = Field(pattern=SHA256_PATTERN)
    prepared_releases: tuple[PreparedReleaseBinding, ...]
    result_uri: str
    resource: ProjectionFreezeResourceRequest = Field(
        default_factory=ProjectionFreezeResourceRequest
    )
    limits: ProjectionFreezeLimits = Field(default_factory=ProjectionFreezeLimits)
    sequence_length: Literal[64] = SEQUENCE_LENGTH
    restart_policy: Literal["never"] = "never"

    @model_validator(mode="after")
    def validate_exact_corpus(self) -> "NasdaqProjectionFreezeRequest":
        if len(self.prepared_releases) != 4:
            raise ValueError("projection freeze requires exactly four prepared releases")
        observed = tuple(
            (item.sequence_number, item.trade_date, item.fold, item.filename)
            for item in self.prepared_releases
        )
        expected = tuple(
            (index, trade_date, fold, filename)
            for index, (trade_date, fold, filename) in enumerate(
                zip(EXPECTED_SOURCE_DATES, EXPECTED_SOURCE_FOLDS, EXPECTED_SOURCE_FILES, strict=True),
                1,
            )
        )
        if observed != expected:
            raise ValueError("projection freeze changed the exact chronological 2/1/1 corpus")
        for item in self.prepared_releases:
            expected_uri = (
                f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/prepared/"
                f"{item.trade_date.isoformat()}/[a-z0-9][a-z0-9-]{{2,62}}"
            )
            if re.fullmatch(expected_uri, item.result_uri.rstrip("/")) is None:
                raise ValueError("prepared release escaped its governed date prefix")
        expected_result = (
            f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
            f"projection-candidates/{self.run_id}"
        )
        if self.result_uri != expected_result:
            raise ValueError("projection candidate escaped its exact run prefix")
        return self


class ProjectionFreezeManifest(_StrictModel):
    schema_version: Literal["market_data_wave1_projection_freeze_result_v1"] = (
        "market_data_wave1_projection_freeze_result_v1"
    )
    run_id: str
    release_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_root_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_root_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    development_tabular_sha256: str = Field(pattern=SHA256_PATTERN)
    development_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    final_tabular_sha256: str = Field(pattern=SHA256_PATTERN)
    final_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    development_tabular_shards: Literal[90] = 90
    final_tabular_shards: Literal[30] = 30
    development_folds: tuple[Literal["train", "validation"], ...] = (
        "train",
        "validation",
    )
    final_folds: tuple[Literal["test"], ...] = ("test",)
    sequence_length: Literal[64] = SEQUENCE_LENGTH
    final_bucket: Literal["aimada-wave1-final-e00g6zvxpr00"] = FINAL_BUCKET
    created_at: AwareDatetime


def execute_projection_freeze_s3(
    input_uri: str,
    *,
    work_root: Path,
    endpoint_url: str = OBJECT_STORAGE_ENDPOINT,
) -> str:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("projection freeze requires the approved eu-north1 endpoint")
    _require_environment()
    pattern = (
        rf"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
        r"projection-requests/[a-z0-9][a-z0-9-]{2,62}/staging"
    )
    if re.fullmatch(pattern, input_uri.rstrip("/")) is None:
        raise ValueError("projection freeze input escaped its exact request prefix")
    work_root = work_root.resolve()
    if str(work_root) in {"/", str(Path.home().resolve())}:
        raise ValueError("projection freeze work root is too broad")
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="market-data-c4-", dir=work_root) as value:
        stage = Path(value)
        request_root = stage / "request"
        with JOB_LOG.phase(
            "request-download",
            "Download and verify the exact reviewed four-date C4 request package.",
            input_uri=input_uri.rstrip("/"),
        ):
            download_s3_release(
                input_uri,
                request_root,
                endpoint_url=endpoint_url,
                limits=TransferLimits(max_files=8, max_bytes=1024 * 1024),
            )
        request_path = request_root / "request.json"
        request = NasdaqProjectionFreezeRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        _verify_job_context(request)
        candidate_staging = stage / "candidate-staging"
        _materialize_candidate(
            request, candidate_staging, stage=stage, endpoint_url=endpoint_url
        )
        result = stage / "candidate"
        publish_local_result(
            candidate_staging,
            result.resolve().as_uri(),
            limits=TransferLimits(
                max_files=request.limits.result_max_files,
                max_bytes=request.limits.result_max_bytes,
            ),
        )
        with JOB_LOG.phase(
            "candidate-publication",
            "Publish the verified C4 candidate under the preparation-only prefix.",
            result_uri=request.result_uri,
        ):
            publish_s3_result(
                result,
                request.result_uri,
                endpoint_url=endpoint_url,
                limits=TransferLimits(
                    max_files=request.limits.result_max_files,
                    max_bytes=request.limits.result_max_bytes,
                ),
            )
        return request.result_uri


def _materialize_candidate(
    request: NasdaqProjectionFreezeRequest,
    result: Path,
    *,
    stage: Path,
    endpoint_url: str,
) -> Path:
    source_config = Path(__file__).resolve().parents[3] / "configs/data/nasdaq-public-sample-v1.json"
    if sha256_file(source_config) != request.source_config_sha256:
        raise ValueError("projection request source config differs from the immutable image")
    feature_config_artifact_sha = sha256_file(FEATURE_CONFIG)
    feature_config_hash = FeaturePipelineConfig.model_validate_json(
        FEATURE_CONFIG.read_text(encoding="utf-8")
    ).config_hash()
    preparations: list[
        tuple[PreparedReleaseBinding, PreparationManifest, NasdaqPreparationRequest]
    ] = []
    for binding in request.prepared_releases:
        prepared_root = stage / "prepared" / f"{binding.sequence_number:02d}"
        with JOB_LOG.phase(
            "prepared-release-verification",
            "Download and verify one small C3 manifest-of-shards release.",
            sequence_number=binding.sequence_number,
            trade_date=binding.trade_date.isoformat(),
            fold=binding.fold,
        ):
            download_s3_release(
                binding.result_uri,
                prepared_root,
                endpoint_url=endpoint_url,
                limits=TransferLimits(
                    max_files=request.limits.prepared_max_files,
                    max_bytes=request.limits.prepared_max_bytes,
                ),
            )
            preparation_path = prepared_root / "preparation.json"
            if sha256_file(preparation_path) != binding.preparation_sha256:
                raise ValueError("prepared release manifest changed after review")
            preparation = PreparationManifest.model_validate_json(
                preparation_path.read_text(encoding="utf-8")
            )
            prepared_request = _verify_preparation(
                binding,
                preparation,
                feature_config_artifact_sha,
                prepared_root / "request.json",
            )
            preparations.append((binding, preparation, prepared_request))

    root = _build_frozen_root(request, preparations, feature_config_hash)
    root_bytes = json.dumps(
        root.model_dump(mode="json"), indent=2, sort_keys=True
    ).encode() + b"\n"
    root_sha = hashlib.sha256(root_bytes).hexdigest()
    root_identity = root.canonical_hash()
    scope_roots = {
        "development": result / ".development-staging",
        "final": result / ".final-staging",
    }
    tabular_by_fold: dict[str, list] = {"train": [], "validation": [], "test": []}
    sequence_by_fold: dict[str, list] = {"train": [], "validation": [], "test": []}

    for binding, preparation, prepared_request in preparations:
        with JOB_LOG.phase(
            "projection-materialization",
            "Selectively verify feature members and materialize fold-bound tabular and sequence rows.",
            sequence_number=binding.sequence_number,
            trade_date=binding.trade_date.isoformat(),
            fold=binding.fold,
            comparison_count=len(preparation.comparison_checkpoints),
        ):
            seen_runs: set[str] = set()
            plan = tuple(
                (number, symbol, family, seed)
                for number, (symbol, family, seed) in enumerate(
                    (
                        (symbol, family, seed)
                        for symbol in SYMBOLS
                        for family in ATTACK_FAMILIES
                        for seed in SEEDS
                    ),
                    1,
                )
            )
            for reference, expected_comparison in zip(
                preparation.comparison_checkpoints, plan, strict=True
            ):
                number, symbol, family, seed = expected_comparison
                expected_shard = (
                    f"comparisons/{number:03d}-{symbol.lower()}-"
                    f"{family.replace('_', '-')}-s{seed}"
                )
                if reference.uri != f"{prepared_request.checkpoint_uri}/{expected_shard}":
                    raise ValueError("comparison checkpoint URI or order changed after C3")
                selected_root = stage / "selected" / str(binding.sequence_number) / Path(
                    reference.uri
                ).name
                selection = download_verified_s3_release_members(
                    reference.uri,
                    selected_root,
                    endpoint_url=endpoint_url,
                    required_members=("checkpoint.json",),
                    include_suffixes=("features.parquet", "run-metadata.json"),
                    limits=TransferLimits(
                        max_files=request.limits.checkpoint_max_files,
                        max_bytes=request.limits.checkpoint_max_bytes,
                    ),
                    selected_limits=TransferLimits(
                        max_files=request.limits.selected_checkpoint_max_files,
                        max_bytes=request.limits.selected_checkpoint_max_bytes,
                    ),
                )
                checkpoint_path = selected_root / "checkpoint.json"
                if sha256_file(checkpoint_path) != reference.checkpoint_sha256:
                    raise ValueError("comparison checkpoint changed after C3 freeze")
                checkpoint = ComparisonCheckpoint.model_validate_json(
                    checkpoint_path.read_text(encoding="utf-8")
                )
                observed_payload = inventory_model_evidence(
                    selection.inventory,
                    exclude_checkpoint=True,
                )
                expected_payload = (
                    reference.payload_inventory_sha256,
                    reference.payload_file_count,
                    reference.payload_size_bytes,
                )
                if observed_payload != expected_payload:
                    raise ValueError("comparison checkpoint payload no longer matches C3")
                if checkpoint.binding_sha256 != preparation.checkpoint_binding_sha256:
                    raise ValueError("comparison checkpoint escaped its preparation binding")
                if (
                    checkpoint.comparison_number,
                    checkpoint.symbol,
                    checkpoint.attack_family,
                    checkpoint.seed,
                ) != expected_comparison:
                    raise ValueError("comparison checkpoint changed the frozen experiment plan")
                expected_control_run = (
                    f"xnas-{binding.trade_date.isoformat()}-{symbol.lower()}-control"
                )
                expected_hybrid_run = (
                    f"xnas-{binding.trade_date.isoformat()}-{symbol.lower()}-{family}-s{seed}"
                )
                expected_control_included = family == ATTACK_FAMILIES[0] and seed == SEEDS[0]
                if (
                    checkpoint.control_run_id != expected_control_run
                    or checkpoint.hybrid_run_id != expected_hybrid_run
                    or checkpoint.includes_control_artifacts != expected_control_included
                ):
                    raise ValueError("comparison checkpoint changed its exact run inventory")
                run_specs = [(checkpoint.hybrid_run_id, checkpoint.hybrid_event_stream_sha256, True)]
                if checkpoint.includes_control_artifacts:
                    run_specs.insert(
                        0,
                        (checkpoint.control_run_id, checkpoint.control_event_stream_sha256, False),
                    )
                for run_id, replay_sha, is_hybrid in run_specs:
                    if run_id in seen_runs:
                        raise ValueError("C3 checkpoint duplicated a projection run")
                    seen_runs.add(run_id)
                    feature_root = selected_root / "features" / run_id
                    feature_path = feature_root / "features.parquet"
                    metadata_path = feature_root / "run-metadata.json"
                    metadata = _verify_feature_run(
                        metadata_path,
                        feature_path,
                        expected_run_id=run_id,
                        expected_date=binding.trade_date,
                        expected_feature_config_sha=feature_config_hash,
                        expected_replay_sha=replay_sha,
                        is_hybrid=is_hybrid,
                    )
                    scope = "final" if binding.fold == "test" else "development"
                    artifact_root = scope_roots[scope] / "artifacts"
                    tabular = materialize_tabular_shard(
                        feature_path,
                        artifact_root / "tabular" / binding.fold / f"{run_id}.parquet",
                        artifact_root=artifact_root,
                        root_sha256=root_identity,
                        assignment_sha256=root.assignment_sha256,
                        replay_sha256=replay_sha,
                        fold=binding.fold,
                        base_session_id=metadata["session_id"],
                        campaign_id=run_id if is_hybrid else None,
                        run_id=run_id,
                    )
                    sequence = materialize_sequence_shard(
                        tabular,
                        artifact_root / "sequence" / binding.fold / f"{run_id}.parquet",
                        artifact_root=artifact_root,
                        sequence_length=request.sequence_length,
                    )
                    tabular_by_fold[binding.fold].append(tabular)
                    sequence_by_fold[binding.fold].append(sequence)
                JOB_LOG.info(
                    "projection-checkpoint.completed",
                    "Verified one C3 checkpoint and materialized its selected governed rows.",
                    sequence_number=binding.sequence_number,
                    trade_date=binding.trade_date.isoformat(),
                    fold=binding.fold,
                    comparison_number=number,
                    comparison_count=27,
                    symbol=symbol,
                    attack_family=family,
                    seed=seed,
                    materialized_runs=len(run_specs),
                    selected_files=len(selection.selected_inventory.files),
                    selected_bytes=sum(
                        item.size_bytes for item in selection.selected_inventory.files
                    ),
                )
            if len(seen_runs) != 30:
                raise ValueError("each prepared date must produce exactly 30 projection runs")

    for scope in ("development", "final"):
        manifests = scope_roots[scope] / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        (manifests / "frozen-root.json").write_bytes(root_bytes)
    expected_counts = {"train": 60, "validation": 30, "test": 30}
    if any(
        len(tabular_by_fold[fold]) != count
        or len(sequence_by_fold[fold]) != count
        or any(
            tabular.supervised_row_count != sequence.sequence_count
            or tabular.row_identity_sha256 != sequence.sequence_identity_sha256
            for tabular, sequence in zip(
                tabular_by_fold[fold], sequence_by_fold[fold], strict=True
            )
        )
        for fold, count in expected_counts.items()
    ):
        raise ValueError("C4 projection inventory or tabular/sequence row identity changed")
    development_tabular = _tabular_manifest(
        request, root, "development", tabular_by_fold["train"] + tabular_by_fold["validation"]
    )
    final_tabular = _tabular_manifest(request, root, "final_test", tabular_by_fold["test"])
    development_sequence = _sequence_manifest(
        request, root, "development", sequence_by_fold["train"] + sequence_by_fold["validation"]
    )
    final_sequence = _sequence_manifest(request, root, "final_test", sequence_by_fold["test"])
    hashes = {}
    for scope, name, manifest in (
        ("development", "tabular", development_tabular),
        ("development", "sequence", development_sequence),
        ("final", "tabular", final_tabular),
        ("final", "sequence", final_sequence),
    ):
        path = scope_roots[scope] / "manifests" / f"{name}-projection.json"
        hashes[f"{scope}_{name}"] = write_manifest(path, manifest)
        if name == "tabular":
            verify_tabular_projection(
                path,
                expected_sha256=hashes[f"{scope}_{name}"],
                root=root,
                artifact_root=scope_roots[scope] / "artifacts",
            )
            load_tabular_projection_dataset(
                path,
                expected_sha256=hashes[f"{scope}_{name}"],
                root=root,
                artifact_root=scope_roots[scope] / "artifacts",
                access_mode="development" if scope == "development" else "final_test",
            )
        else:
            verify_sequence_projection(
                path,
                expected_sha256=hashes[f"{scope}_{name}"],
                root=root,
                artifact_root=scope_roots[scope] / "artifacts",
            )
    for scope in ("development", "final"):
        publish_local_result(
            scope_roots[scope],
            (result / scope).resolve().as_uri(),
            limits=TransferLimits(
                max_files=request.limits.result_max_files,
                max_bytes=request.limits.result_max_bytes,
            ),
        )
    freeze = ProjectionFreezeManifest(
        run_id=request.run_id,
        release_id=request.release_id,
        request_sha256=request.canonical_hash(),
        frozen_root_sha256=root_sha,
        frozen_root_identity_sha256=root_identity,
        development_tabular_sha256=hashes["development_tabular"],
        development_sequence_sha256=hashes["development_sequence"],
        final_tabular_sha256=hashes["final_tabular"],
        final_sequence_sha256=hashes["final_sequence"],
        created_at=datetime.now(UTC),
    )
    (result / "request.json").write_bytes(request.canonical_bytes())
    (result / "projection-freeze.json").write_bytes(freeze.canonical_bytes())
    return result


def verify_projection_candidate(root: Path) -> ProjectionFreezeManifest:
    root = root.resolve()
    verify_complete_result(
        root,
        limits=TransferLimits(max_files=512, max_bytes=2_147_483_648),
    )
    request = NasdaqProjectionFreezeRequest.model_validate_json(
        (root / "request.json").read_text(encoding="utf-8")
    )
    freeze = ProjectionFreezeManifest.model_validate_json(
        (root / "projection-freeze.json").read_text(encoding="utf-8")
    )
    if freeze.request_sha256 != request.canonical_hash():
        raise ValueError("projection candidate is not bound to its reviewed request")
    for scope, access_mode, tabular_sha, sequence_sha in (
        (
            "development",
            "development",
            freeze.development_tabular_sha256,
            freeze.development_sequence_sha256,
        ),
        (
            "final",
            "final_test",
            freeze.final_tabular_sha256,
            freeze.final_sequence_sha256,
        ),
    ):
        release = root / scope
        verify_complete_result(
            release,
            limits=TransferLimits(max_files=512, max_bytes=2_147_483_648),
        )
        frozen_root_path = release / "manifests/frozen-root.json"
        if sha256_file(frozen_root_path) != freeze.frozen_root_sha256:
            raise ValueError("projection scope changed the frozen root file")
        frozen_root = FrozenPublicSampleRoot.model_validate_json(
            frozen_root_path.read_text(encoding="utf-8")
        )
        if frozen_root.canonical_hash() != freeze.frozen_root_identity_sha256:
            raise ValueError("projection scope changed the frozen root identity")
        tabular_path = release / "manifests/tabular-projection.json"
        sequence_path = release / "manifests/sequence-projection.json"
        verify_tabular_projection(
            tabular_path,
            expected_sha256=tabular_sha,
            root=frozen_root,
            artifact_root=release / "artifacts",
        )
        load_tabular_projection_dataset(
            tabular_path,
            expected_sha256=tabular_sha,
            root=frozen_root,
            artifact_root=release / "artifacts",
            access_mode=access_mode,
        )
        verify_sequence_projection(
            sequence_path,
            expected_sha256=sequence_sha,
            root=frozen_root,
            artifact_root=release / "artifacts",
        )
    return freeze


def _verify_preparation(
    binding: PreparedReleaseBinding,
    preparation: PreparationManifest,
    feature_config_sha: str,
    request_path: Path,
) -> NasdaqPreparationRequest:
    prepared_request = NasdaqPreparationRequest.model_validate_json(
        request_path.read_text(encoding="utf-8")
    )
    checkpoint_binding = PreparationCheckpointBinding(
        request_sha256=prepared_request.canonical_hash(),
        source_manifest_sha256=prepared_request.source_release_manifest_sha256,
        source_sha256=preparation.source_sha256,
        image=prepared_request.image,
        git_commit=prepared_request.git_commit,
        feature_config_sha256=prepared_request.feature_config_sha256,
    )
    if (
        preparation.source_filename != binding.filename
        or preparation.run_id != prepared_request.run_id
        or preparation.source_manifest_sha256
        != prepared_request.source_release_manifest_sha256
        or prepared_request.source.filename != binding.filename
        or prepared_request.source.date != binding.trade_date
        or prepared_request.source.fold != binding.fold
        or prepared_request.sequence_number != binding.sequence_number
        or prepared_request.result_uri != binding.result_uri
        or prepared_request.feature_config_sha256 != feature_config_sha
        or checkpoint_binding.canonical_hash() != preparation.checkpoint_binding_sha256
        or preparation.feature_run_count != 30
        or preparation.replay_domain_count != 30
        or preparation.comparison_count != 27
        or preparation.repeat_determinism_verified is not True
    ):
        raise ValueError("prepared release is incompatible with the C4 corpus contract")
    if not preparation.comparison_checkpoints:
        raise ValueError("prepared release omits comparison checkpoints")
    return prepared_request


def _build_frozen_root(
    request: NasdaqProjectionFreezeRequest,
    preparations: list[
        tuple[PreparedReleaseBinding, PreparationManifest, NasdaqPreparationRequest]
    ],
    feature_config_sha: str,
) -> FrozenPublicSampleRoot:
    protocol = {
        "schema_version": "nasdaq_public_sample_projection_protocol_v1",
        "dates": [item.isoformat() for item in EXPECTED_SOURCE_DATES],
        "folds": list(EXPECTED_SOURCE_FOLDS),
        "symbols": list(SYMBOLS),
        "window_ms": [WINDOW_START_MS, WINDOW_END_MS],
        "depth": 10,
        "attacks": list(ATTACK_FAMILIES),
        "seeds": list(SEEDS),
        "feature_schema_version": "lob_features_v2",
        "negative_label_source": "research_control_assumption",
        "sequence_length": request.sequence_length,
    }
    protocol_sha = _canonical_hash(protocol)
    sources = tuple(
        FrozenSourceBinding(
            trade_date=binding.trade_date,
            fold=binding.fold,
            filename=binding.filename,
            source_sha256=preparation.source_sha256,
            source_manifest_sha256=preparation.source_manifest_sha256,
            preparation_manifest_sha256=binding.preparation_sha256,
            parser_config_sha256=preparation.parser_config_sha256,
        )
        for binding, preparation, _ in preparations
    )
    corpus_sha = _canonical_hash(
        {
            "protocol_sha256": protocol_sha,
            "sources": [item.model_dump(mode="json") for item in sources],
        }
    )
    assignment_sha = _canonical_hash(
        [
            {"trade_date": binding.trade_date.isoformat(), "fold": binding.fold}
            for binding, _, _ in preparations
        ]
    )
    feature_release_sha = _canonical_hash(
        [
            {
                "preparation_sha256": binding.preparation_sha256,
                "checkpoint_binding_sha256": preparation.checkpoint_binding_sha256,
                "comparison_checkpoints": [
                    item.model_dump(mode="json") for item in preparation.comparison_checkpoints
                ],
            }
            for binding, preparation, _ in preparations
        ]
    )
    return FrozenPublicSampleRoot(
        release_id=request.release_id,
        protocol_sha256=protocol_sha,
        corpus_id=f"{request.release_id}-corpus",
        corpus_sha256=corpus_sha,
        split_id=f"{request.release_id}-chronological-split",
        assignment_sha256=assignment_sha,
        feature_release_id=f"{request.release_id}-features",
        feature_release_sha256=feature_release_sha,
        feature_config_sha256=feature_config_sha,
        source_config_sha256=request.source_config_sha256,
        sources=sources,
    )


def _verify_feature_run(
    metadata_path: Path,
    feature_path: Path,
    *,
    expected_run_id: str,
    expected_date: date,
    expected_feature_config_sha: str,
    expected_replay_sha: str,
    is_hybrid: bool,
) -> dict[str, object]:
    if not metadata_path.is_file() or not feature_path.is_file():
        raise ValueError("selected checkpoint omits required feature artifacts")
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    run = payload.get("run")
    inputs = payload.get("input")
    output = payload.get("output")
    if not all(isinstance(item, dict) for item in (run, inputs, output)):
        raise ValueError("feature run metadata is malformed")
    expected_source_type = "hybrid" if is_hybrid else "nasdaq_itch"
    if (
        payload.get("schema_version") != "feature_stream_run_metadata_v1"
        or payload.get("feature_schema_version") != "lob_features_v2"
        or payload.get("feature_config_hash") != expected_feature_config_sha
        or run.get("run_id") != expected_run_id
        or run.get("session_date") != expected_date.isoformat()
        or run.get("source_type") != expected_source_type
        or run.get("historical_source_type") != "nasdaq_itch"
        or inputs.get("java_canonical_event_stream_hash") != expected_replay_sha
        or output.get("feature_file") != "features.parquet"
        or output.get("feature_file_size_bytes") != feature_path.stat().st_size
        or output.get("feature_file_sha256") != sha256_file(feature_path)
        or output.get("invalid_row_count") != 0
    ):
        raise ValueError("feature run metadata is not bound to its C3 checkpoint")
    if run.get("instrument") not in SYMBOLS or not isinstance(run.get("session_id"), str):
        raise ValueError("feature run escaped the exact symbol/session contract")
    return run


def _tabular_manifest(request, root, scope, shards):
    folds = ("train", "validation") if scope == "development" else ("test",)
    suffix = "development" if scope == "development" else "final"
    return TabularProjectionManifest(
        projection_id=f"{request.release_id}-tabular-{suffix}",
        access_scope=scope,
        root_release_id=root.release_id,
        root_sha256=root.canonical_hash(),
        protocol_sha256=root.protocol_sha256,
        corpus_sha256=root.corpus_sha256,
        assignment_sha256=root.assignment_sha256,
        feature_release_sha256=root.feature_release_sha256,
        folds=folds,
        shards=tuple(shards),
    )


def _sequence_manifest(request, root, scope, shards):
    folds = ("train", "validation") if scope == "development" else ("test",)
    suffix = "development" if scope == "development" else "final"
    return SequenceProjectionManifest(
        projection_id=f"{request.release_id}-sequence-{suffix}",
        access_scope=scope,
        root_release_id=root.release_id,
        root_sha256=root.canonical_hash(),
        protocol_sha256=root.protocol_sha256,
        corpus_sha256=root.corpus_sha256,
        assignment_sha256=root.assignment_sha256,
        feature_release_sha256=root.feature_release_sha256,
        folds=folds,
        shards=tuple(shards),
    )


def _verify_job_context(request: NasdaqProjectionFreezeRequest) -> None:
    repository, digest = request.image.rsplit("@sha256:", maxsplit=1)
    expected = {
        "MARKET_DATA_ACTUAL_PROJECT_ID": request.project_id,
        "MARKET_DATA_ACTUAL_IMAGE_REPOSITORY": repository,
        "MARKET_DATA_ACTUAL_IMAGE_SHA256": digest,
        "MARKET_DATA_ACTUAL_PLATFORM": request.resource.platform,
        "MARKET_DATA_ACTUAL_PRESET": request.resource.preset,
        "MARKET_DATA_ACTUAL_DISK_SIZE_GIB": str(request.resource.disk_size_gib),
        "MARKET_DATA_ACTUAL_TIMEOUT_SECONDS": str(request.resource.timeout_seconds),
    }
    if any(os.environ.get(name, "").strip() != value for name, value in expected.items()):
        raise RuntimeError("projection-freeze Job context does not match its reviewed request")


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
