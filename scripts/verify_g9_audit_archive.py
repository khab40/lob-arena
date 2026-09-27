"""Verify portable G9 audit metadata without model execution or cloud access."""
import hashlib
import json
from pathlib import Path
import zipfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(root):
    evidence = root / "docs/evidence"
    directory = evidence / "g9-audit-20260927"

    def read(path):
        return json.loads(path.read_bytes())

    decision = read(evidence / "g9-exit-decision-20260927.json")
    for name, digest in decision["approved_artifacts"].items():
        require(sha((root / name).read_bytes()) == digest, "approved artifact: " + name)
    proposal = read(evidence / "g9-exit-proposal-20260927.json")
    for name, digest in proposal["evidence_bindings"].items():
        require(sha((root / name).read_bytes()) == digest, "evidence anchor: " + name)
    audit_bytes = (evidence / "g9-artifact-audit-20260927.json").read_bytes()
    require(sha(audit_bytes) == proposal["local_artifact_audit_sha256"], "audit anchor")
    audit = json.loads(audit_bytes)
    manifest = read(directory / "archive.json")
    source = (directory / "assemble.py.txt").read_bytes()
    require(sha(source) == audit["assembler_sha256"] == manifest["assembler_sha256"],
            "assembler anchor")
    archive = directory / "metadata.zip"
    require(sha(archive.read_bytes()) == manifest["archive_sha256"], "archive hash")
    require(archive.stat().st_size == manifest["archive_size_bytes"], "archive size")
    with zipfile.ZipFile(archive) as zipped:
        require(len(zipped.namelist()) == len(set(zipped.namelist())), "duplicate member")
        require(set(zipped.namelist()) == set(manifest["files"]), "archive members")
        blobs = {}
        for name, expected in manifest["files"].items():
            require(zipped.getinfo(name).file_size == expected["size_bytes"], name)
            data = zipped.read(name)
            require(sha(data) == expected["sha256"], name)
            blobs[name] = data
    run = "outputs/g8-final-execution-20260923/"
    release = run + "independent-s3/release/"
    verified = read(evidence / "g8-final-verification-20260923.json")
    lineage = read(evidence / "lightgbm-lineage-verification-20260922.json")
    require(blobs["outputs/g9-exit-20260927/artifact-audit.json"] == audit_bytes,
            "original audit receipt")
    receipt_bytes = blobs[run + "independent-s3/verification.json"]
    require(sha(receipt_bytes) == verified["s3_receipt_sha256"], "S3 receipt anchor")
    inventory_bytes = blobs["outputs/lightgbm-candidate-inventory-20260922/inventory-final.json"]
    require(sha(inventory_bytes) == lineage["inventory_sha256"], "inventory anchor")
    receipt, inventory = json.loads(receipt_bytes), json.loads(inventory_bytes)
    objects = {item["path"]: item for item in receipt["objects"]}
    require(len(objects) == len(receipt["objects"]) == audit["objects_rehashed"] == 176,
            "object count")
    require(sum(item["size_bytes"] for item in objects.values()) ==
            receipt["total_bytes"] == audit["bytes_rehashed"] == 24463251, "byte count")
    for name, data in blobs.items():
        if name.startswith(release):
            item = objects[name.removeprefix(release)]
            require(sha(data) == item["sha256"] and len(data) == item["size_bytes"], name)
    bundle = json.loads(blobs[release + "artifacts/bundle/model-bundle.json"])
    require(len(bundle["artifacts"]) == audit["bundle_references_verified"], "bundle count")
    for item in bundle["artifacts"]:
        saved = objects["artifacts/" + item["uri"]]
        require((item["sha256"], item["size_bytes"]) ==
                (saved["sha256"], saved["size_bytes"]), "bundle reference")
    require(len(lineage["artifacts"]) == audit["development_mlflow_artifacts_matched_to_final_bundle"],
            "development artifact count")
    for item in lineage["artifacts"]:
        matches = [obj for name, obj in objects.items() if Path(name).name == Path(item["path"]).name]
        require(len(matches) == 1 and all(matches[0][key] == item[key]
                for key in ("sha256", "size_bytes")), "development artifact identity")
    training = json.loads(blobs[release + "artifacts/training/training-run.json"])
    require(training["ordered_feature_columns"] == inventory["configuration"]["ordered_features"]
            and len(training["ordered_feature_columns"]) == 31, "feature order")
    require(training["preprocessing"] == inventory["configuration"]["preprocessing"], "preprocessing")
    report = json.loads(blobs[release + "artifacts/c4-evaluation.json"])
    require(report["metrics"] == proposal["quality"]["metrics"], "metrics")
    require(report["candidate_sha256"] == proposal["candidate_sha256"] ==
            inventory["candidate_sha256"], "candidate")
    return {"object_identities": len(objects), "recorded_bytes": receipt["total_bytes"],
            "archive_members": len(blobs), "payload_bytes_rehashed": False,
            "cloud_calls": 0, "model_execution": False}


if __name__ == "__main__":
    print(json.dumps(verify(Path(__file__).resolve().parents[1]), indent=2))
