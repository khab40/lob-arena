"""Retain verified holdout reads immediately; replay without a cloud client."""
import os
from pathlib import Path

from .holdout_runtime import bounded_read
from .holdout_storage import HoldoutStore
from .research_execution_spec import receipt
from .settings_release import ArtifactRead, json_record
from .verification_spec import canonical, digest

NAMES = {"SUCCESS", "checksums.json", "execution-context.json", "reference-parity.json",
         "predictions.json", "target-ledger.json", "result.json"}


def input_name(item):
    return digest(canonical(item.model_dump(mode="json")))


def checked_input(request, item, gate):
    paths = {request.reference_logits_path, request.tabular_path, *request.baseline_paths}
    if item not in request.inputs or item.path not in paths:
        raise ValueError("unexpected verification input")
    if item.scope == "final_test":
        if gate is None:
            raise ValueError("final input requires reference parity")
        gate.require(request)


def checked_result(name, expected):
    receipt(expected)
    bound = 16384 if name == "SUCCESS" else (65536 if name == "checksums.json" else 64 * 1024**2)
    if name not in NAMES or expected["size_bytes"] > bound:
        raise ValueError("result outside exact collection scope")


def write_once(base, path, raw):
    if base.is_symlink() or path.parent.is_symlink() or not path.parent.resolve().is_relative_to(base):
        raise ValueError("retention directory changed")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def local_read(base, path, size, sha):
    if path.is_symlink() or not path.resolve().is_relative_to(base) or path.stat().st_size != size:
        raise ValueError("retained path or size differs")
    raw = bounded_read(path, size)
    if digest(raw) != sha:
        raise ValueError("retained checksum differs")
    return raw


class RetainingReadbackStore(HoldoutStore):
    def __init__(self, s3, request, *, expires, destination):
        super().__init__(s3, request, expires=expires)
        path = Path(destination)
        path.mkdir(mode=0o700)  # A separate directory per authorized collection.
        self.destination = path.resolve()
        (self.destination / "inputs").mkdir(mode=0o700)
        (self.destination / "receipts").mkdir(mode=0o700)
        self.results, self.inputs = {}, {}

    def start(self):
        if self.calls >= 40:
            raise ValueError("collection call budget exhausted")
        super().start()

    def read(self, name, expected):
        checked_result(name, expected)
        if name in self.results:
            previous, raw = self.results[name]
            if previous != expected:
                raise ValueError("result receipt changed")
            return raw
        raw = super().read(name, expected)
        write_once(self.destination, self.destination / name, raw)
        write_once(self.destination, self.destination / "receipts" / (name + ".json"), canonical(expected))
        self.results[name] = (dict(expected), raw)
        return raw

    def input(self, item, gate=None):
        checked_input(self.request, item, gate)
        if item.path in self.inputs:
            return self.inputs[item.path]
        value = super().input(item, gate)
        name = input_name(item)
        write_once(self.destination, self.destination / "inputs" / (name + ".bin"), value.data)
        write_once(self.destination, self.destination / "inputs" / (name + ".json"), canonical(item.model_dump(mode="json")))
        self.inputs[item.path] = value
        return value

    def put(self, *args, **kwargs):
        raise ValueError("readback cannot publish")

    def claim(self):
        raise ValueError("readback cannot claim an execution")


class OfflineReadbackStore(HoldoutStore):
    def __init__(self, request, directory):
        path = Path(directory)
        if path.is_symlink() or not path.is_dir():
            raise ValueError("retained directory required")
        self.request, self.destination = request, path.resolve()
        self.calls, self.read_bytes = 0, 0

    def read(self, name, expected):
        checked_result(name, expected)
        base = self.destination / "receipts"
        if base.is_symlink() or not base.is_dir():
            raise ValueError("retained publication receipts required")
        record = canonical(expected)
        local_read(self.destination, base / (name + ".json"), len(record), digest(record))
        return local_read(self.destination, self.destination / name,
                          expected["size_bytes"], expected["sha256"])

    def input(self, item, gate=None):
        checked_input(self.request, item, gate)
        base = self.destination / "inputs"
        name = input_name(item)
        if base.is_symlink() or not base.is_dir():
            raise ValueError("retained inputs required")
        expected = canonical(item.model_dump(mode="json"))
        record = local_read(self.destination, base / (name + ".json"), len(expected), digest(expected))
        if json_record(record) != item.model_dump(mode="json"):
            raise ValueError("retained input identity differs")
        ref = item.reference
        raw = local_read(self.destination, base / (name + ".bin"), ref.size_bytes, ref.sha256)
        return ArtifactRead(raw, ref.version_id)

    def get(self, *args, **kwargs):
        raise ValueError("offline readback cannot access cloud")

    def put(self, *args, **kwargs):
        raise ValueError("offline readback cannot publish")

    def claim(self):
        raise ValueError("offline readback cannot claim an execution")
