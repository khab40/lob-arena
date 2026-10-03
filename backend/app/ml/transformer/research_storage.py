"""Bounded conditional S3 publication with byte-verified acknowledgements."""
import json
from pathlib import Path
import re

from .research_execution_spec import MAX_OBJECT, MAX_OUTPUT, PREFIX, SLOTS, receipt, request_sha, validate
from .role_execution_transport import PublicationUncertain, _body, verify_sha_metadata
from .verification_spec import OUTPUT_BUCKET, canonical, digest


def key(slot, name):
    if (slot not in SLOTS or not isinstance(name, str)
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name)):
        raise ValueError("research artifact leaves its fixed slot")
    return PREFIX + slot + "/" + name


class Store:
    def __init__(self, s3, request):
        validate(request)
        self.s3, self.request = s3, request
        self.artifacts, self.events = {}, []
        self.written, self.read_bytes, self.gets = 0, 0, 0

    def read(self, slot, name, expected=None, limit=MAX_OBJECT):
        if self.gets >= 1024 or self.read_bytes >= 4 * MAX_OUTPUT:
            raise ValueError("research readback budget exhausted")
        if not 0 < limit <= MAX_OBJECT:
            raise ValueError("invalid read size")
        args = {"Bucket": OUTPUT_BUCKET, "Key": key(slot, name)}
        if expected is not None:
            receipt(expected)
            args["VersionId"] = expected["version_id"]
            limit = min(limit, expected["size_bytes"])
        self.gets += 1
        response = self.s3.get_object(**args)
        raw, observed = _body(response, limit, args.get("VersionId"))
        self.read_bytes += len(raw)
        if self.read_bytes > 4 * MAX_OUTPUT or expected is not None and observed != expected:
            raise ValueError("versioned research artifact differs")
        verify_sha_metadata(response, observed["sha256"])
        return raw, observed

    def put(self, name, raw, *, artifact=True):
        object_key = key(self.request["slot"], name)
        if (not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_OBJECT
                or self.written + len(raw) > MAX_OUTPUT or len(self.artifacts) >= 512
                or name in self.artifacts):
            raise ValueError("research publication bound exceeded or duplicate artifact")
        self.written += len(raw)  # Failed/ambiguous attempts still consume the budget.
        try:
            response = self.s3.put_object(Bucket=OUTPUT_BUCKET, Key=object_key, Body=raw,
                IfNoneMatch="*", Metadata={"sha256": digest(raw)}, ContentType="application/octet-stream")
            observed = {"sha256": digest(raw), "size_bytes": len(raw), "version_id": response.get("VersionId")}
            receipt(observed)
            self.read(self.request["slot"], name, observed)
        except Exception as error:
            raise PublicationUncertain("resolve immutable publication by versioned readback; do not retry") from error
        if artifact:
            self.artifacts[name] = observed
        return observed

    def claim(self):
        response = self.s3.list_objects_v2(Bucket=OUTPUT_BUCKET,
            Prefix=PREFIX + self.request["slot"] + "/", MaxKeys=1)
        if response.get("Contents") or response.get("KeyCount", 0) or response.get("IsTruncated"):
            raise ValueError("research slot already has evidence; no automatic replacement")
        return self.put("INTENT", canonical(self.request), artifact=False)

    def event(self, kind, payload):
        name = f"event-{len(self.events):04}.json"
        raw = canonical({"index": len(self.events), "kind": kind, "payload": payload,
            "previous_sha256": self.events[-1]["sha256"] if self.events else None,
            "request_sha256": request_sha(self.request)})
        item = self.put(name, raw)
        self.events.append(item)
        return item

    def checkpoint(self, path, checksum):
        raw = Path(path).read_bytes()
        if digest(raw) != checksum:
            raise ValueError("checkpoint changed before publication")
        name = path.parent.name + "-" + path.name
        item = self.put(name, raw)
        self.event("checkpoint", {"name": name, **item})
        return {**item, "object_name": name}

    def finish(self, result):
        self.put("result.json", canonical(result))
        self.event("completed", {"result_sha256": self.artifacts["result.json"]["sha256"]})
        manifest = canonical(self.artifacts)
        inventory = self.put("checksums.json", manifest, artifact=False)
        return self.put("SUCCESS", canonical({"request_sha256": request_sha(self.request),
            "checksums": inventory, "files": len(self.artifacts)}), artifact=False)

    def read_publication(self, slot, success, expected_request_sha):
        raw, _ = self.read(slot, "SUCCESS", success, 16384)
        terminal = json.loads(raw)
        if terminal.get("request_sha256") != expected_request_sha:
            raise ValueError("prior publication belongs to another request")
        raw, _ = self.read(slot, "checksums.json", terminal["checksums"], 262144)
        inventory = json.loads(raw)
        if not isinstance(inventory, dict) or len(inventory) != terminal["files"] or len(inventory) > 512:
            raise ValueError("invalid publication inventory")
        for name, item in inventory.items():
            key(slot, name)
            receipt(item)
        if sum(i["size_bytes"] for i in inventory.values()) > MAX_OUTPUT:
            raise ValueError("published inventory exceeds slot budget")
        return inventory
