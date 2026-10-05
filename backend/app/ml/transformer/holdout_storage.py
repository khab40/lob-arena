"""One-attempt holdout IO with shared request/byte/deadline budgets."""
import re
import time

from .holdout_spec import MAX_OUTPUT, MAX_READ, object_location
from .role_execution_transport import PublicationUncertain, _body, verify_sha_metadata
from .settings_release import ArtifactRead, json_record
from .verification_spec import canonical, digest


class HoldoutStore:
    def __init__(self, s3, request, *, expires):
        if not time.monotonic() < expires <= time.monotonic() + request.timeout_seconds:
            raise ValueError("bounded holdout execution deadline required")
        self.s3, self.request, self.expires = s3, request, expires
        self.calls, self.read_bytes, self.written = 0, 0, 0
        self.artifacts = {}

    def start(self):
        if time.monotonic() >= self.expires or self.calls >= 10000:
            raise TimeoutError("holdout deadline or request budget exhausted")
        self.calls += 1  # Failed calls consume the request budget too.

    def input(self, item, gate=None):
        if item not in self.request.inputs:
            raise ValueError("input absent from approved request")
        if item.scope == "final_test":
            if gate is None:
                raise ValueError("final input requires reference parity")
            gate.require(self.request)
        ref = item.reference
        bucket, key = object_location(ref)
        self.start()
        response = self.s3.get_object(Bucket=bucket, Key=key, VersionId=ref.version_id)
        raw, observed = self.consume(response, ref.size_bytes, ref.version_id)
        if observed != {k: getattr(ref, k) for k in ("size_bytes", "version_id", "sha256")}:
            raise ValueError("input bytes differ from approved version")
        return ArtifactRead(raw, observed["version_id"])

    def consume(self, response, limit, version):
        # Reserve worst-case bytes before streaming, including failed partial reads.
        if self.read_bytes + limit + 1 > MAX_READ:
            response["Body"].close()
            raise ValueError("holdout read byte budget exhausted")
        self.read_bytes += limit + 1
        raw, observed = _body(response, limit, version)
        return raw, observed

    def key(self, name):
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name):
            raise ValueError("invalid holdout artifact name")
        return self.request.output_prefix + name

    def read(self, name, expected):
        from .research_execution_spec import receipt
        receipt(expected)
        self.start()
        response = self.s3.get_object(Bucket=self.request.output_bucket, Key=self.key(name),
                                     VersionId=expected["version_id"])
        raw, observed = self.consume(response, expected["size_bytes"], expected["version_id"])
        verify_sha_metadata(response, observed["sha256"])
        if observed != expected:
            raise ValueError("holdout result version, size or checksum differs")
        return raw

    def put(self, name, raw, *, artifact=True):
        if (type(raw) is not bytes or not 0 < len(raw) <= 64 * 1024**2
                or self.written + len(raw) > MAX_OUTPUT or name in self.artifacts):
            raise ValueError("invalid or duplicate holdout publication")
        self.written += len(raw)
        self.start()
        try:
            response = self.s3.put_object(Bucket=self.request.output_bucket, Key=self.key(name), Body=raw,
                IfNoneMatch="*", Metadata={"sha256": digest(raw)}, ContentType="application/octet-stream")
            item = {"sha256": digest(raw), "size_bytes": len(raw), "version_id": response.get("VersionId")}
            self.read(name, item)
        except Exception as error:
            raise PublicationUncertain("holdout PUT requires reconciliation; never retry") from error
        if artifact:
            self.artifacts[name] = item
        return item

    def claim(self):
        self.start()
        response = self.s3.list_objects_v2(Bucket=self.request.output_bucket,
                                          Prefix=self.request.output_prefix, MaxKeys=1)
        if response.get("Contents") or response.get("KeyCount", 0) or response.get("IsTruncated"):
            raise ValueError("holdout attempt already has evidence; no replacement")
        return self.put("INTENT", self.request.canonical_bytes(), artifact=False)

    def finish(self, result):
        self.put("result.json", canonical(result))
        checksums = self.put("checksums.json", canonical(self.artifacts), artifact=False)
        return self.put("SUCCESS", canonical({"request_sha256": self.request.sha256(),
            "checksums": checksums, "files": len(self.artifacts)}), artifact=False)

    def reconcile(self, success):
        terminal = json_record(self.read("SUCCESS", success))
        if terminal["request_sha256"] != self.request.sha256():
            raise ValueError("publication belongs to another request")
        inventory = json_record(self.read("checksums.json", terminal["checksums"]))
        if (not isinstance(inventory, dict) or len(inventory) != terminal["files"]
                or not 1 <= len(inventory) <= 32 or {"SUCCESS", "INTENT", "FAILED", "checksums.json"} & set(inventory)
                or sum(item["size_bytes"] for item in inventory.values()) > MAX_OUTPUT):
            raise ValueError("invalid holdout publication inventory")
        return {name: self.read(name, item) for name, item in inventory.items()}, inventory
