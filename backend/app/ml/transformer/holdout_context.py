"""Require external approval pin, observed Job signature and actual reference parity."""
from dataclasses import dataclass
import re

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .settings_release import json_record
from .verification_spec import canonical, digest


@dataclass(frozen=True)
class HoldoutGate:
    request_sha256: str
    job_id: str
    context: dict
    parity: dict

    def require(self, request):
        if self.request_sha256 != request.sha256() or self.parity.get("passed") is not True:
            raise ValueError("final access requires approved request and reference parity")


def verify_context(request, envelope, *, approved_request_sha256, trusted_public_key):
    # Both pins originate outside the request. A caller cannot approve its own hash/key.
    if (request.sha256() != approved_request_sha256
            or request.context_public_key != trusted_public_key
            or set(envelope) != {"context", "signature"}):
        raise ValueError("holdout request has no matching external authorization")
    context = envelope["context"]
    expected = {"request_sha256": request.sha256(), "run_id": request.run_id,
                "image_digest": request.image_digest, "nonce": request.nonce,
                "provider_spec_sha256": request.provider_spec_sha256}
    if (set(context) != {*expected, "job_id", "provider_readback_sha256"}
            or any(context[k] != v for k, v in expected.items())
            or not re.fullmatch(r"aijob-[a-z0-9]+", context["job_id"])
            or not re.fullmatch(r"[0-9a-f]{64}", context["provider_readback_sha256"])):
        raise ValueError("holdout provider context differs")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted_public_key)).verify(
        bytes.fromhex(envelope["signature"]), canonical(context))
    return context


def check_parity(request, context, saved_raw, target_ids, labels, logits):
    if digest(saved_raw) != request.input(request.reference_logits_path).reference.sha256:
        raise ValueError("reference bytes differ from approved saved artifact")
    saved = json_record(saved_raw)
    if (not isinstance(saved, list) or len(saved) != request.reference_rows
            or tuple(r["target_id"] for r in saved) != tuple(target_ids)
            or len(set(target_ids)) != request.reference_rows
            or digest(canonical(tuple(target_ids))) != request.reference_targets_sha256
            or any(type(r["label"]) is not int or r["label"] not in (0, 1) for r in saved)
            or any(type(label) is not int or label not in (0, 1) for label in labels)
            or tuple(r["label"] for r in saved) != tuple(labels)):
        raise ValueError("reference identity, label or count differs")
    expected = np.asarray([r["logit"] for r in saved], dtype=np.float64)
    actual = np.asarray(logits, dtype=np.float64)
    if (actual.shape != expected.shape or not np.isfinite(expected).all()
            or not np.isfinite(actual).all() or not np.allclose(
                actual, expected, atol=request.reference_atol, rtol=request.reference_rtol)):
        raise ValueError("development reference parity failed before final access")
    parity = {"passed": True, "rows": len(saved), "targets_sha256": request.reference_targets_sha256,
              "reference_sha256": digest(saved_raw), "actual_logits_sha256": digest(canonical(actual.tolist())),
              "maximum_absolute_error": float(np.max(np.abs(actual - expected))),
              "atol": request.reference_atol, "rtol": request.reference_rtol,
              "target_ids": list(target_ids), "labels": list(map(int, labels)),
              "actual_logits": actual.tolist()}
    return HoldoutGate(request.sha256(), context["job_id"], context, parity)
