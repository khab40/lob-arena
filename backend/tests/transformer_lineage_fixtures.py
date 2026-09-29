"""Inert metadata only: no event rows, training, scoring or cloud clients."""
from types import SimpleNamespace as NS

from app.market_data.preparation import NasdaqPreparationRequest
from app.market_data.preparation_checkpoints import PreparationCheckpointBinding, inventory_model_evidence
from app.nebius.object_storage import ChecksumInventory, InventoryEntry
from app.ml.transformer.lineage_inventory import REQUEST_KEY, phase_keys
from app.ml.transformer.role_provenance import CHECKPOINT_PREFIX, DATE, PREPARATION_RUN, checkpoint_keys
from app.ml.transformer.verification_spec import INPUT_BUCKET, canonical, digest


def fixture():
    source = NS(filename="10302019.NASDAQ_ITCH50.gz", source_sha256="1" * 64,
        source_manifest_sha256="2" * 64)
    request = NasdaqPreparationRequest(run_id=PREPARATION_RUN, sequence_number=3,
        image="registry.example/jobs@sha256:" + "a" * 64, git_commit="b" * 40,
        created_at="2026-09-03T00:00:00Z", source=dict(filename=source.filename,
            date=DATE, fold="validation", expected_content_length=3872931242,
            url="https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/" + source.filename),
        source_release_uri=f"s3://{INPUT_BUCKET}/data/public-sample-v1/quarantine/nasdaq/{DATE}/source-release",
        source_release_manifest_sha256=source.source_manifest_sha256,
        result_uri=f"s3://{INPUT_BUCKET}/{REQUEST_KEY.rsplit('/', 1)[0]}",
        checkpoint_uri=f"s3://{INPUT_BUCKET}/{CHECKPOINT_PREFIX.rstrip('/')}", feature_config_sha256="3" * 64)
    binding = PreparationCheckpointBinding(request_sha256=request.canonical_hash(),
        source_manifest_sha256=source.source_manifest_sha256, source_sha256=source.source_sha256,
        image=request.image, git_commit=request.git_commit, feature_config_sha256=request.feature_config_sha256)
    prepared = NS(checkpoint_binding_sha256=binding.canonical_hash(), comparison_checkpoints=[])
    anchor = dict(anchor_sha256="4" * 64, source=source, prepared=prepared, checkpoints=[])
    blobs = {REQUEST_KEY: request.canonical_bytes()}
    for key in phase_keys(1)[28:] + phase_keys(2):
        blobs[key] = canonical({"fixture_key": key})
    for cp in checkpoint_keys()[1:]:
        prefix = cp.removesuffix("checkpoint.json")
        entries = [InventoryEntry(path=k.removeprefix(prefix), sha256=digest(v), size_bytes=len(v))
            for k, v in blobs.items() if k.startswith(prefix)]
        inventory = ChecksumInventory(files=tuple(entries))
        sha, count, size = inventory_model_evidence(inventory)
        checkpoint = canonical(dict(payload_inventory_sha256=sha, payload_file_count=count, payload_size_bytes=size))
        anchor["checkpoints"].append(checkpoint)
        prepared.comparison_checkpoints.append(NS(payload_inventory_sha256=sha,
            payload_file_count=count, payload_size_bytes=size, checkpoint_sha256=digest(checkpoint)))
        inventory = ChecksumInventory(files=(*inventory.files, InventoryEntry(path="checkpoint.json",
            sha256=digest(checkpoint), size_bytes=len(checkpoint))))
        blobs[prefix + "SUCCESS"] = inventory.model_dump_json().encode()
    return anchor, blobs
