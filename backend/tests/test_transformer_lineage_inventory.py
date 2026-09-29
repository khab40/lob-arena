import json
from copy import deepcopy
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import lineage_inventory as inv  # noqa: E402
from app.ml.transformer.lineage_context import PhaseVerifier, context  # noqa: E402
from app.ml.transformer.lineage_policy import rules_for, transition  # noqa: E402
from app.ml.transformer.lineage_proposal import proposal_bytes, require_proposal  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402
from transformer_lineage_fixtures import fixture  # noqa: E402


def test_exact_scope_and_complete_integrity_chain():
    anchor, blobs = fixture()
    assert len(inv.phase_keys(1)) == 58 and len(inv.phase_keys(2)) == 57
    assert len(set(inv.phase_keys(1) + inv.phase_keys(2))) == 115
    first = PhaseVerifier(anchor, 1)
    for key in first.keys:
        assert "*" not in key and not key.endswith((".parquet", "events.jsonl"))
        first.accept(key, blobs[key])
    second = PhaseVerifier(anchor, 2, first.inventories)
    for key in second.keys:
        second.accept(key, blobs[key])
    with pytest.raises(ValueError, match="receipts"):
        second.result([])
    result = second.result([{**item, "version_id": "1"} for item in second.accepted])
    assert result["metadata_bytes_authenticated"] and result["authenticated_objects"] == 57
    assert not result["source_separation_verified"] and not result["gpu_ready"]


@pytest.mark.parametrize("index", [0, 1, 27, 28, 57])
def test_tampered_phase_one_rejected(index):
    anchor, blobs = fixture()
    verifier = PhaseVerifier(anchor, 1)
    for key in verifier.keys[:index]:
        verifier.accept(key, blobs[key])
    key = verifier.keys[index]
    raw = json.loads(blobs[key])
    if index == 0:
        raw["git_commit"] = "c" * 40
    elif index <= 27:
        raw["files"][0]["sha256"] = "9" * 64
    else:
        raw["fixture_key"] = "unrelated"
    with pytest.raises(ValueError):
        verifier.accept(key, canonical(raw))
    with pytest.raises(ValueError, match="incomplete"):
        verifier.result([])


def test_historical_request_hash_excludes_later_model_defaults():
    from app.ml.transformer.verification_spec import digest
    anchor, blobs = fixture()
    original = json.loads(blobs[inv.REQUEST_KEY])
    original.pop("mlflow_tracking_uri")
    raw = canonical(original)
    request = inv.NasdaqPreparationRequest.model_validate_json(raw)
    binding = inv.PreparationCheckpointBinding(request_sha256=digest(raw),
        source_manifest_sha256=request.source_release_manifest_sha256,
        source_sha256=anchor["source"].source_sha256, image=request.image,
        git_commit=request.git_commit, feature_config_sha256=request.feature_config_sha256)
    anchor["prepared"].checkpoint_binding_sha256 = binding.canonical_hash()
    assert raw != request.canonical_bytes()
    assert inv.verify_request(raw, anchor["source"], anchor["prepared"]) == request
    with pytest.raises(ValueError, match="binding"):
        inv.verify_request(raw + b" ", anchor["source"], anchor["prepared"])


def test_unanchored_bundle_and_out_of_order_members_fail():
    with pytest.raises(ValueError):
        context(b"{}")
    anchor, blobs = fixture()
    verifier = PhaseVerifier(anchor, 1)
    with pytest.raises(ValueError, match="order"):
        verifier.accept(verifier.keys[1], blobs[verifier.keys[1]])
    with pytest.raises(ValueError, match="authenticated"):
        PhaseVerifier(anchor, 2, {})


def test_policies_fit_provider_limits_and_preserve_unrelated_rules():
    base = [{"group_id": "existing", "roles": ["storage.viewer"], "paths": ["releases/*"]}]
    original = deepcopy(base)
    first = transition(base, before=None, after=1)
    concurrent = {"group_id": "concurrent", "roles": ["storage.viewer"], "paths": ["other"]}
    second = transition(first + [concurrent], before=1, after=2)
    assert base == original and len(first) == 7 and len(second) == 8
    assert transition(second, before=2, after=None) == base + [concurrent]
    assert transition(first, before=1, after=None) == base
    assert [len(r["paths"]) for r in rules_for(1)] == [10, 10, 10, 10, 10, 8]
    assert [len(r["paths"]) for r in rules_for(2)] == [10, 10, 10, 10, 10, 7]


@pytest.mark.parametrize("kind", ["duplicate", "partial", "changed", "capacity", "skip"])
def test_policy_transition_rejects_unreviewed_state(kind):
    current = rules_for(1)
    before, after = 1, 2
    if kind == "duplicate":
        current.append(current[0])
    elif kind == "partial":
        current.pop()
    elif kind == "changed":
        current[0]["paths"][0] += "unreviewed"
    elif kind == "capacity":
        current += [{"paths": [f"other{i}"], "roles": ["storage.viewer"]} for i in range(5)]
    else:
        before, after = None, 2
    with pytest.raises(ValueError):
        transition(current, before=before, after=after)


def test_partial_path_grant_cannot_be_combined_with_new_grant():
    rule = rules_for(1)[0]
    rule["paths"] = rule["paths"][:1]
    with pytest.raises(ValueError, match="partial"):
        transition([rule], before=None, after=1)


def test_committed_proposal_exactly_matches_code_and_approval_digest():
    from app.ml.transformer.verification_spec import digest
    committed = Path(__file__).resolve().parents[2] / "docs/evidence/transformer-lineage-access-proposal-20260929.json"
    assert committed.read_bytes() == proposal_bytes()
    require_proposal(digest(committed.read_bytes()))
    with pytest.raises(ValueError, match="approval"):
        require_proposal("0" * 64)


@pytest.mark.parametrize("kind", ["missing", "oversized", "zero", "outside", "changed"])
def test_member_requires_exact_authenticated_inventory(kind):
    from app.nebius.object_storage import InventoryEntry
    key = inv.phase_keys(2)[0]
    prefix, relative = key.split("replays/", 1)
    entry = InventoryEntry(path="replays/" + relative, sha256="a" * 64, size_bytes=2)
    inventories = {prefix: {entry.path: entry}}
    if kind == "missing":
        inventories[prefix] = {}
    elif kind in ("oversized", "zero"):
        inventories[prefix][entry.path] = entry.model_copy(update={"size_bytes": inv.MAX_OBJECT + 1 if kind == "oversized" else 0})
    elif kind == "outside":
        key += ".parquet"
    with pytest.raises(ValueError):
        inv.verify_member(key, b"{}", inventories)


def test_handoff_checks_bucket_identity_and_never_overwrites(tmp_path):
    from app.ml.transformer.lineage_handoff import render
    from app.ml.transformer.lineage_proposal import BUCKET_ID
    from app.ml.transformer.verification_spec import INPUT_BUCKET, digest
    snapshot, output = tmp_path / "bucket.json", tmp_path / "policy.json"
    bucket = {"metadata": {"id": BUCKET_ID, "name": INPUT_BUCKET, "resource_version": "134"},
        "status": {"state": "ACTIVE"}, "spec": {"bucket_policy": {"rules": []}}}
    snapshot.write_bytes(canonical(bucket))
    sha = digest(proposal_bytes())
    result = render(snapshot, output, sha, None, 1)
    assert result["rule_count"] == 6 and result["resource_version"] == "134"
    with pytest.raises(FileExistsError):
        render(snapshot, output, sha, None, 1)
    bucket["metadata"]["id"] = "unrelated"
    snapshot.write_bytes(canonical(bucket))
    with pytest.raises(ValueError, match="another"):
        render(snapshot, tmp_path / "second.json", sha, None, 1)
