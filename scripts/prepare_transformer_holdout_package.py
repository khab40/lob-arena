"""Prepare private portable evidence from retained development artifacts only."""
import argparse
from pathlib import Path
import os
from tempfile import NamedTemporaryFile

from app.ml.transformer.holdout_spec import SETTINGS_SHA
from app.ml.transformer.holdout_worker import TRUST
from app.ml.transformer.settings_release import ArtifactRead, json_record, load_release
from app.ml.transformer.verification_spec import canonical, digest


def prepare(artifact_map, settings, output):
    artifact_map, settings, output = map(Path, (artifact_map, settings, output))
    if artifact_map.stat().st_size > 65536 or settings.stat().st_size > 65536:
        raise ValueError("holdout metadata input exceeds bound")
    mapping = json_record(artifact_map.read_bytes())
    locations = {item["reference"]["uri"]: item for item in mapping.values()}
    base = artifact_map.parent.resolve()
    reads = {}

    def reader(ref):
        item = locations[ref.uri]
        path = (base / item["path"]).resolve()
        if (base not in path.parents or path.stat().st_size != ref.size_bytes
                or item["reference"] != ref.model_dump(mode="json")):
            raise ValueError("retained artifact location, version or size differs")
        with path.open("rb") as stream:
            raw = stream.read(ref.size_bytes + 1)
        reads[ref.uri] = raw
        return ArtifactRead(raw, ref.version_id)

    settings_raw = settings.read_bytes()
    release = load_release(settings_raw, reader, expected_sha256=SETTINGS_SHA, **TRUST)
    release.require_research_inference()
    raw = canonical({"settings": settings_raw.decode(),
        "evidence": {ref.uri: reads[ref.uri].hex() for _, ref in release.artifacts
                     if ref.uri.startswith("evidence:sha256:")}})
    if len(raw) > 512 * 1024:
        raise ValueError("portable package exceeds worker bound")
    temporary = None
    try:
        with NamedTemporaryFile(dir=output.parent, prefix=".holdout-package-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return {"package_sha256": digest(raw), "size_bytes": len(raw), "settings_sha256": release.sha256(),
            "verified_artifacts": 7, "checkpoint_embedded": False, "cloud_gets": 0,
            "model_execution": False, "execution_authorized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifact-map", "settings", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    import json
    print(json.dumps(prepare(**vars(parser.parse_args())), sort_keys=True))
