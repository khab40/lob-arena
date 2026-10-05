"""Declared metadata and inert checkpoint bytes; no fitting or model execution."""
import hashlib
import json

from app.market_data.projections import TabularProjectionShard
from app.ml.transformer.contracts import InputContract, Normalization
from app.ml.transformer.research_comparison_contract import MANIFEST, REPLACEMENT_PREFIX
from app.ml.transformer.research_confirmation_contract import LEGACY_PREFIX
from app.ml.transformer.settings_release import ArtifactRead, BUCKET, build_release
from app.ml.transformer.settings_schema import Artifact, Artifacts
from transformer_input_fixtures import frozen_root


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SettingsFixture:
    def __init__(self):
        shard = TabularProjectionShard(fold="train", base_session_id="fixture-train", run_id="fixture-train",
            replay_manifest_sha256="a" * 64, supervised_row_count=4, row_identity_sha256="b" * 64,
            rows=dict(uri="fixture.parquet", sha256="c" * 64, size_bytes=1,
                      logical_name="fixture-train", schema_version="tabular_projection_rows_v1"))
        self.contract = InputContract(root=frozen_root(), tabular_manifest_sha256="d" * 64,
            sequence_manifest_sha256="e" * 64, training_shards=(shard,))
        self.normalization = Normalization(training_binding_sha256=self.contract.training_binding(),
            fitting_row_sha256="f" * 64, fitting_rows=4, observed_counts=(4,) * 60, means=(0.,) * 60, scales=(1.,) * 60)
        self.checkpoint = b"inert metadata-test bytes, never a serialized neural network"
        self.report = self.make_report()
        self.decision = "continue_research"
        self.calls = []

    def make_report(self):
        fixed = MANIFEST["selected"]
        bindings = {"contract_sha256": self.contract.sha256(), "normalization_sha256": self.normalization.sha256(),
            "source_commit": "1" * 40, "image_digest": "sha256:" + "2" * 64,
            "role_manifest_sha256": "3" * 64,
            "ordered_targets_sha256": {r: "f" * 64 for r in ("train", "selection", "calibration", "operating_point")},
            "source_binding": {"feature_release_id": self.contract.root.feature_release_id,
                               "feature_release_sha256": self.contract.root.feature_release_sha256}}
        result = {"kind": "inference", "final_test_access": False, "job_id": "fixture-job",
            "request_sha256": "4" * 64, "winner_trial_sha256": fixed["trial_sha256"],
            "checkpoint_origin": {"slot": fixed["slot"], "trial_sha256": fixed["trial_sha256"],
                "request_sha256": MANIFEST["prior"][fixed["slot"]]["request"]["sha256"],
                "bindings": bindings, "checkpoint": {**fixed["checkpoint"], "sha256": sha(self.checkpoint),
                                                        "size_bytes": len(self.checkpoint)}},
            "execution_bindings": {**bindings, "source_commit": "5" * 40, "image_digest": "sha256:" + "6" * 64},
            "freeze_blocked": False, "stability": {"passed": True, "candidate_seed": 42},
            "calibration": {"converged": True, "boundary_hit": False, "fitting_role": "calibration", "temperature": 1.0},
            "comparison": {"freeze_blocked": False, "unattainable_floor": False,
                "calibration_worsened_brier_and_ece": False, "limitations": ["inert fixture; research only"],
                "transformer_selected_operating_points": [{"mode": m, "threshold": .5}
                    for m in ("high_precision", "balanced", "high_recall")]}}
        return {"status": "verified", "result": result,
            "context": {"job_id": result["job_id"], "request_sha256": result["request_sha256"],
                        "run_id": "fixture-comparison-run",
                        "image_digest": result["execution_bindings"]["image_digest"]}, "inventory": {}}

    def prepare(self):
        self.reads = {}

        def reference(raw, uri=None):
            ref = Artifact(uri=uri or "evidence:sha256:" + sha(raw), sha256=sha(raw), size_bytes=len(raw),
                           version_id="1" if uri else "content-addressed")
            self.reads[ref.uri] = ArtifactRead(raw, ref.version_id)
            return ref

        contract = reference(self.contract.canonical_bytes(), f"s3://{BUCKET}/{REPLACEMENT_PREFIX}inference/input-contract.json")
        normalization = reference(self.normalization.canonical_bytes(),
                                  f"s3://{BUCKET}/{REPLACEMENT_PREFIX}inference/normalization.json")
        self.report["inventory"] = {n: {k: getattr(ref, k) for k in ("sha256", "size_bytes", "version_id")}
            for n, ref in (("input-contract.json", contract), ("normalization.json", normalization))}
        checkpoint = reference(self.checkpoint,
            f"s3://{BUCKET}/{LEGACY_PREFIX}search-128-0003/search-128-0003-epoch-04.pt")
        verification = reference(encode(self.report))
        result = self.report["result"]
        origin = result["checkpoint_origin"]
        selection = reference(encode({"status": "verified", "result": {"status": "verified",
            "job_id": "fixture-training-job", "request_sha256": origin["request_sha256"],
            "trial": MANIFEST["selected"]["trial"], "trial_sha256": origin["trial_sha256"],
            "selected_checkpoint": origin["checkpoint"], "bindings": origin["bindings"]},
            "inventory": {origin["checkpoint"]["object_name"]: {
                k: getattr(checkpoint, k) for k in ("sha256", "size_bytes", "version_id")}},
            "context": {"request_sha256": origin["request_sha256"], "job_id": "fixture-training-job",
                        "run_id": "fixture-training-run", "image_digest": origin["bindings"]["image_digest"]}}))
        summary = reference(encode({"verification": {"status": "verified", "receipt_sha256": verification.sha256},
            "candidate": {"checkpoint": result["checkpoint_origin"]["checkpoint"]},
            "job_id": result["job_id"], "request_sha256": result["request_sha256"]}))
        decision = reference(encode({"decision": self.decision, "results_evidence_sha256": summary.sha256}))
        self.pins = {"verification_sha256": verification.sha256, "decision_sha256": decision.sha256,
                     "selection_sha256": selection.sha256}
        self.artifacts = Artifacts(checkpoint=checkpoint, contract=contract, normalization=normalization,
            verification=verification, selection_verification=selection, comparison_summary=summary, decision=decision)
        return self

    def reader(self, reference):
        self.calls.append(reference.uri)
        return self.reads[reference.uri]

    def release(self):
        self.prepare()
        return build_release(self.artifacts, self.reader, **self.pins)
