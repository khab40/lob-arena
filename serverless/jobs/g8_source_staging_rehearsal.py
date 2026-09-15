"""Offline protocol rehearsal using retained synthetic sources; remote transport is simulated."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

if __package__:
    from . import stage_g8_native_sources as staging
else:
    import stage_g8_native_sources as staging


class SyntheticS3:
    def __init__(self):
        self.objects, self.metadata, self.calls = {}, {}, []
        self.fail = self.lost = None
        self.denial = "403"
        self.real_run = staging.subprocess.run

    def aws(self, endpoint, *args):
        assert endpoint == staging.transport.ENDPOINT
        operation = args[1]
        bucket = args[args.index("--bucket") + 1]
        if operation == "list-objects-v2":
            prefix = args[args.index("--prefix") + 1]
            return {"Contents": [{"Key": k} for b, k in sorted(self.objects) if b == bucket and k.startswith(prefix)]}
        key = args[args.index("--key") + 1]
        self.calls.append((operation, bucket, key))
        identity = (bucket, key)
        if operation == "head-object":
            if identity not in self.objects:
                raise RuntimeError("missing synthetic object")
            return {"ContentLength": len(self.objects[identity]), "Metadata": self.metadata[identity]}
        if operation == "put-object":
            assert args[args.index("--if-none-match") + 1] == "*"
            if identity in self.objects or identity == self.fail:
                raise RuntimeError("conditional synthetic failure")
            self.objects[identity] = Path(args[args.index("--body") + 1]).read_bytes()
            self.metadata[identity] = {"sha256": args[args.index("--metadata") + 1].removeprefix("sha256=")}
            if identity == self.lost:
                raise RuntimeError("lost synthetic success response")
            return {}
        if operation == "get-object":
            Path(args[-1]).write_bytes(self.objects[identity])
            return {}
        raise AssertionError("forbidden operation: " + operation)

    def run(self, command, **kwargs):
        if command[0] != "/synthetic/aws":
            return self.real_run(command, **kwargs)  # Keep real Ed25519 verification.
        assert command[1:3] == ["--endpoint-url", staging.transport.ENDPOINT]
        args = command[3:-2]
        if args[1] == "head-object" and staging.PRODUCTION_KEY in args:
            self.calls.append(("production-head", staging.PRODUCTION_BUCKET, staging.PRODUCTION_KEY))
            return SimpleNamespace(returncode=0 if self.denial == "allowed" else 1, stdout="{}",
                                   stderr=f"An error occurred ({self.denial}) when calling the HeadObject operation")
        try:
            value = self.aws(staging.transport.ENDPOINT, *args)
            return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr="")
        except RuntimeError:
            return SimpleNamespace(returncode=1, stdout="", stderr="synthetic failure")

    @property
    def puts(self):
        return [(bucket, key) for operation, bucket, key in self.calls if operation == "put-object"]


def rehearse(package: Path, output: Path, digest: str) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    fake = SyntheticS3()
    _, _, plans = staging._plans(package, digest)
    _, bucket, prefix, _ = plans[1]
    fake.fail = (bucket, prefix + "/SUCCESS")
    with (
        patch.dict(staging.os.environ, {"AWS_ACCESS_KEY_ID": "synthetic-not-a-real-key",
                                       "AWS_SECRET_ACCESS_KEY": "synthetic-not-a-secret"}),
        patch.object(staging.transport.storage, "_aws_json", fake.aws),
        patch.object(staging.transport.shutil, "which", return_value="/synthetic/aws"),
        patch.object(staging.transport.subprocess, "run", fake.run),
    ):
        try:
            staging.publish(package, expected_sha256=digest)
        except RuntimeError:
            pass
        else:
            raise AssertionError("injected marker interruption did not occur")
        preserved = dict(fake.objects)
        if not preserved or fake.fail in preserved:
            raise AssertionError("partial source upload was not retained without SUCCESS")
        fake.fail = None
        staging.publish(package, expected_sha256=digest)
        if any(fake.objects[k] != v for k, v in preserved.items()):
            raise AssertionError("resume changed existing objects")
        count = len(fake.puts)
        repeat = staging.publish(package, expected_sha256=digest)
        if len(fake.puts) != count or any(r["put_attempts"] for r in repeat["releases"]):
            raise AssertionError("completed source repeat performed writes")
        receipt = staging.readback(package, output / "readback", expected_sha256=digest)
        if not receipt["remote_source_bytes_verified"] or len(fake.puts) != count:
            raise AssertionError("readback did not verify the source bytes without writes")
    evidence = {
        "schema_version": "g8_source_staging_offline_rehearsal_v1",
        "source_package_sha256": digest,
        "transport": "simulated_s3_not_authenticated_remote",
        "retained_before_marker_resume": len(preserved),
        "verified_source_objects": len(fake.objects),
        "matching_partial_objects_preserved": True,
        "completed_repeat_puts": 0,
        "replay_domains_reverified": receipt["comparison_replay_domains_verified"],
        "production_head_request_simulated_only": True,
        "production_body_downloaded": False,
        "remote_authentication_verified": False,
        "pinned_job_credentials_verified": False,
        "native_storage_verified": False,
        "mlflow_remote_verified": False,
        "production_g8_complete": False,
    }
    (output / "rehearsal.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(rehearse(args.package, args.output, args.expected_sha256), indent=2))
