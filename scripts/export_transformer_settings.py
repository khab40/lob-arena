"""Export from operator-retained artifact bytes; no cloud or model execution."""
import argparse
import json
from pathlib import Path

from app.ml.transformer.settings_release import ArtifactRead, build_release, json_record, save_release
from app.ml.transformer.settings_schema import Artifacts


def export(artifact_map: Path, output: Path, *, verification_sha256, decision_sha256, selection_sha256):
    if artifact_map.stat().st_size > 64 * 1024:
        raise ValueError("artifact map exceeds bound")
    mapping = json_record(artifact_map.read_bytes())
    artifacts = Artifacts.model_validate_json(json.dumps({k: v["reference"] for k, v in mapping.items()}))
    locations = {}
    for name, ref in artifacts:
        item = mapping[name]
        if ref.uri in locations:
            raise ValueError("duplicate artifact map location")
        locations[ref.uri] = (ref, artifact_map.parent / item["path"])

    def reader(ref):
        retained, path = locations[ref.uri]
        if retained != ref or path.stat().st_size != ref.size_bytes:
            raise ValueError("local artifact map version or size differs")
        with path.open("rb") as stream:
            raw = stream.read(ref.size_bytes + 1)
        return ArtifactRead(raw, retained.version_id)

    release = build_release(artifacts, reader, verification_sha256=verification_sha256,
                            decision_sha256=decision_sha256, selection_sha256=selection_sha256)
    checksum = save_release(release, output)
    return {"release_id": release.release_id, "sha256": checksum, "output": str(output.resolve()),
            "decision": release.decision,
            "research_inference_gates_passed": release.gates_passed, "serving_eligible": False,
            "model_execution": False, "cloud_gets": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    for name in ("verification-sha256", "decision-sha256", "selection-sha256"):
        parser.add_argument("--" + name, required=True)
    print(json.dumps(export(**vars(parser.parse_args())), sort_keys=True))
