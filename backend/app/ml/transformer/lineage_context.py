"""Authenticate the frozen anchor and each ordered phase before interpreting metadata."""
import json

from app.market_data.preparation import PreparationManifest
from app.market_data.projections import FrozenPublicSampleRoot
from . import role_audit_bundle
from .lineage_inventory import member_entry, phase_keys, verify_inventory, verify_member, verify_request
from .role_provenance import checkpoint_keys
from .verification_spec import canonical, digest


def context(raw):
    receipt = role_audit_bundle.verify(raw)
    files = json.loads(raw)["files"]
    root = FrozenPublicSampleRoot.model_validate_json(files["frozen-root.json"])
    return {"anchor_sha256": receipt["bundle_sha256"],
        "source": next(source for source in root.sources if source.fold == "validation"),
        "prepared": PreparationManifest.model_validate_json(files["metadata-00.json"]),
        "checkpoints": [files[f"metadata-{i:02d}.json"].encode() for i in range(2, 29)]}


class PhaseVerifier:
    def __init__(self, anchor, phase, inventories=None):
        self.anchor, self.phase, self.keys = anchor, phase, phase_keys(phase)
        self.inventories = {} if inventories is None else inventories
        self.completed = 0
        self.accepted = []
        if phase == 2:
            for key in self.keys:
                member_entry(key, self.inventories)

    def accept(self, key, raw):
        if self.completed >= len(self.keys) or self.keys[self.completed] != key:
            raise ValueError("metadata phase is incomplete, repeated or out of order")
        index = self.completed
        if self.phase == 1 and index == 0:
            verify_request(raw, self.anchor["source"], self.anchor["prepared"])
        elif self.phase == 1 and index <= 27:
            ref = self.anchor["prepared"].comparison_checkpoints[index - 1]
            prefix = checkpoint_keys()[index].removesuffix("checkpoint.json")
            self.inventories[prefix] = verify_inventory(raw, ref, self.anchor["checkpoints"][index - 1])
            if index == 27:
                # Reject missing or oversized future members before any member GET.
                for member in phase_keys(1)[28:] + phase_keys(2):
                    member_entry(member, self.inventories)
        else:
            verify_member(key, raw, self.inventories)
        self.completed += 1
        self.accepted.append({"key": key, "size_bytes": len(raw), "sha256": digest(raw)})

    def result(self, receipts):
        if self.completed != len(self.keys):
            raise ValueError("metadata phase is incomplete")
        if not isinstance(receipts, list) or len(receipts) != self.completed:
            raise ValueError("metadata receipts are incomplete")
        for actual, receipt in zip(self.accepted, receipts, strict=True):
            version = receipt.get("version_id")
            if (not isinstance(version, str) or not version or version == "null"
                    or receipt != {**actual, "version_id": version}):
                raise ValueError("metadata receipt does not match authenticated bytes")
        return {"schema_version": "transformer_lineage_phase_receipt_v1", "phase": self.phase,
            "anchor_sha256": self.anchor["anchor_sha256"], "authenticated_objects": self.completed,
            "receipts_sha256": digest(canonical(receipts)), "metadata_bytes_authenticated": True,
            "source_separation_verified": False, "gpu_ready": False,
            "execution_authorized": False, "payload_reads": 0, "model_runs": 0}
