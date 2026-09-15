"""Real staging/reverification code with explicitly simulated S3 transport."""
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("lightgbm")

from serverless.jobs import prepare_g8_native_sources as sources  # noqa: E402
from serverless.jobs import stage_g8_native_sources as staging  # noqa: E402


from serverless.jobs.g8_source_staging_rehearsal import SyntheticS3  # noqa: E402


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("source-staging") / "build"
    receipt = sources.prepare(output)
    return output / "package", receipt["source_package_sha256"]


@pytest.fixture
def fake(monkeypatch):
    remote = SyntheticS3()
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic-not-a-real-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-not-a-secret")
    monkeypatch.setattr(staging.transport.storage, "_aws_json", remote.aws)
    monkeypatch.setattr(staging.transport.shutil, "which", lambda _: "/synthetic/aws")
    monkeypatch.setattr(staging.transport.subprocess, "run", remote.run)
    return remote


def test_conditional_staging_complete_readback_and_zero_write_repeat(prepared, fake, tmp_path):
    package, digest = prepared
    published = staging.publish(package, expected_sha256=digest)
    assert published["conditional_source_publication_verified"]
    assert not published["pinned_job_credentials_verified"]
    count = len(fake.puts)
    for uri in (sources.CANDIDATE_URI, sources.INPUT_URI):
        bucket, prefix = uri.removeprefix("s3://").split("/", 1)
        assert [key for b, key in fake.puts if b == bucket][-1] == prefix + "/SUCCESS"
    again = staging.publish(package, expected_sha256=digest)
    assert all(r["put_attempts"] == 0 for r in again["releases"])
    assert len(fake.puts) == count
    observed = staging.readback(package, tmp_path / "remote-copy", expected_sha256=digest)
    assert observed["remote_source_bytes_verified"]
    assert observed["comparison_replay_domains_verified"] == 30
    assert observed["production_head_denial_verified"]
    assert not any(observed[name] for name in (
        "pinned_job_credentials_verified", "mlflow_remote_verified", "native_storage_verified", "production_body_downloaded"
    ))
    assert len(fake.puts) == count
    assert all(key != staging.PRODUCTION_KEY for operation, _, key in fake.calls if operation == "get-object")


@pytest.mark.parametrize("fault", ["middle", "marker", "lost"])
def test_preserved_partial_upload_resumes_without_overwrite(prepared, fake, fault):
    package, digest = prepared
    _, _, plans = staging._plans(package, digest)
    _, bucket, prefix, entries = plans[1]
    key = prefix + "/SUCCESS" if fault == "marker" else sorted(entries)[5]
    if fault == "lost":
        fake.lost = (bucket, key)
    else:
        fake.fail = (bucket, key)
    if fault != "lost":
        with pytest.raises(RuntimeError):
            staging.publish(package, expected_sha256=digest)
        retained = dict(fake.objects)
        assert retained
        assert (bucket, prefix + "/SUCCESS") not in retained
        fake.fail = None
    else:
        retained = {}
    staging.publish(package, expected_sha256=digest)
    assert all(fake.objects[key] == value for key, value in retained.items())
    if fault == "lost":
        assert fake.puts.count((bucket, key)) == 1


@pytest.mark.parametrize("conflict", ["extra", "bytes", "metadata", "premature-marker"])
def test_conflicting_input_prevents_all_candidate_writes(prepared, fake, conflict):
    package, digest = prepared
    _, _, plans = staging._plans(package, digest)
    _, bucket, prefix, entries = plans[1]
    key = prefix + "/SUCCESS" if conflict == "premature-marker" else sorted(entries)[3]
    item = entries[key]
    fake.objects[bucket, key] = (package / "payload" / item.path).read_bytes()
    fake.metadata[bucket, key] = {"sha256": item.sha256}
    if conflict == "bytes":
        fake.objects[bucket, key] = b"x" * item.size_bytes
    elif conflict == "metadata":
        fake.metadata[bucket, key] = {"sha256": "0" * 64}
    elif conflict == "extra":
        fake.objects[bucket, prefix + "/unlisted"] = b"extra"
    with pytest.raises(ValueError):
        staging.publish(package, expected_sha256=digest)
    assert not fake.puts


@pytest.mark.parametrize("denial", ["404", "InvalidAccessKeyId", "SignatureDoesNotMatch", "allowed", "timeout"])
def test_only_explicit_head_denial_is_accepted(fake, denial):
    fake.denial = denial
    with pytest.raises(ValueError, match="explicit access denial"):
        staging._production_head_denied()


def test_missing_credentials_stop_before_remote_access(prepared, fake, monkeypatch):
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    with pytest.raises(ValueError, match="explicit AWS"):
        staging.publish(prepared[0], expected_sha256=prepared[1])
    assert not fake.calls


def test_changed_local_package_rejected_before_remote_access(prepared, fake, tmp_path):
    package, digest = prepared
    copy = tmp_path / "copy"
    shutil.copytree(package, copy)
    (copy / "payload/unlisted").write_text("changed")
    with pytest.raises(ValueError):
        staging.publish(copy, expected_sha256=digest)
    assert not fake.calls


def test_readback_does_not_overwrite_or_nest_in_original(prepared, fake, tmp_path):
    package, digest = prepared
    for destination in (package / "nested", package.parent, tmp_path):
        with pytest.raises((ValueError, FileExistsError)):
            staging.readback(package, destination, expected_sha256=digest)
    assert not fake.calls


def test_credential_identity_is_a_digest_not_a_secret(fake):
    assert staging._credential_identity() == hashlib.sha256(b"synthetic-not-a-real-key").hexdigest()


def test_remote_inventory_change_during_download_cannot_pass(prepared, fake, tmp_path, monkeypatch):
    package, digest = prepared
    staging.publish(package, expected_sha256=digest)
    destination = tmp_path / "downloaded"
    original_verify = sources.verify

    def verify_then_change(root, **kwargs):
        result = original_verify(root, **kwargs)
        if root == destination:
            bucket, prefix = sources.INPUT_URI.removeprefix("s3://").split("/", 1)
            fake.objects[bucket, prefix + "/unexpected-after-download"] = b"changed"
        return result

    monkeypatch.setattr(sources, "verify", verify_then_change)
    with pytest.raises(ValueError, match="unexpected"):
        staging.readback(package, destination, expected_sha256=digest)
    assert not any(operation == "production-head" for operation, _, _ in fake.calls)


def test_proposed_staging_grants_preserve_existing_policies():
    path = Path(__file__).resolve().parents[2] / "docs/evidence/g8-source-staging-access-proposal-20260915.json"
    proposal = json.loads(path.read_bytes())
    assert proposal["status"] == "proposed_not_applied_requires_operator_approval"
    assert not proposal["cloud_mutations_performed"]
    assert not proposal["automatic_expiration"]
    assert not proposal["production_final_key_activation"]
    assert not proposal["original_grants_rerun"]
    uris = [sources.CANDIDATE_URI, sources.INPUT_URI]
    for item, uri in zip(proposal["buckets"], uris, strict=True):
        before, after = item["before"], item["proposed_update"]
        assert after["metadata"] == {"id": before["metadata"]["id"],
                                     "resource_version": before["metadata"]["resource_version"]}
        assert set(after["spec"]) == {"bucket_policy"}
        rules = after["spec"]["bucket_policy"]["rules"]
        assert rules[:-1] == before["spec"]["bucket_policy"]["rules"]
        assert rules[-1] == {"paths": [uri.removeprefix("s3://").split("/", 1)[1] + "/*"],
                             "roles": ["storage.object-editor"], "group_id": proposal["group_id"]}


def test_closed_staging_window_restored_baseline_and_does_not_claim_full_success():
    evidence = Path(__file__).resolve().parents[2] / "docs/evidence"
    receipt = json.loads((evidence / "g8-source-staging-session-20260915.json").read_bytes())
    proposal = json.loads((evidence / "g8-source-staging-access-proposal-20260915.json").read_bytes())
    elapsed = (datetime.fromisoformat(receipt["revoked_at"]) -
               datetime.fromisoformat(receipt["session_started_at"])).total_seconds()
    assert 0 < elapsed < 3600
    assert abs(elapsed - receipt["conservative_write_window_seconds"]) < 1
    assert receipt["cleanup_complete"] and receipt["cloud_jobs_created"] == 0
    assert not receipt["original_grants_rerun"]
    for result, original in zip(receipt["policy_checks"], proposal["buckets"], strict=True):
        assert result["original_spec_restored"]
        assert result["independent_after"]["spec"] == original["before"]["spec"]
        assert int(result["revoked_resource_version"]) > int(result["granted_resource_version"])
    readback = receipt["read_only_candidate_verification"]
    assert readback["candidate_complete_release_verified"]
    assert readback["candidate_object_count"] == 25
    assert readback["input_prefix_empty"] and readback["production_head_denied"]
    assert readback["production_final_key_state"] == "INACTIVE"
    assert not any(readback[key] for key in (
        "production_body_downloaded", "full_source_staging_complete", "native_storage_verified",
        "mlflow_remote_verified", "production_g8_complete",
    ))
