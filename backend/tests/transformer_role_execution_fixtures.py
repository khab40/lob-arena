"""Inert provider identities and publication bytes; no data/model execution."""
from copy import deepcopy
from datetime import UTC, datetime
from io import BytesIO

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.ml.transformer.role_execution_spec import PROJECT, RUN_ID, provider_spec, request_template
from app.ml.transformer.verification_spec import digest


def request_and_key():
    key = Ed25519PrivateKey.generate()
    request = request_template("a" * 40, "sha256:" + "b" * 64,
                               key.public_key().public_bytes_raw().hex(), "c" * 32)
    return request, key


def job_for(request):
    return {"metadata": {"id": "aijob-fixture", "name": RUN_ID, "parent_id": PROJECT},
            "spec": deepcopy(provider_spec(request)), "status": {"state": "RUNNING"}}


class Missing(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class MemoryStore:
    def __init__(self):
        self.objects, self.calls = {}, []

    def list_objects_v2(self, **args):
        self.calls.append(("list", args))
        keys = [k for k in self.objects if k.startswith(args["Prefix"])]
        return {"KeyCount": len(keys), "IsTruncated": False}

    def put_object(self, **args):
        self.calls.append(("put", args))
        assert args["IfNoneMatch"] == "*"
        if args["Key"] in self.objects:
            raise ValueError("conditional write conflict")
        self.objects[args["Key"]] = args["Body"]
        return {"VersionId": "1"}

    def get_object(self, **args):
        self.calls.append(("get", args))
        raw = self.objects.get(args["Key"])
        if raw is None:
            raise Missing()
        assert args.get("VersionId", "1") == "1"
        return {"VersionId": "1", "ContentLength": len(raw), "Body": BytesIO(raw),
                "Metadata": {"sha256": digest(raw)}}

    def head_object(self, **args):
        self.calls.append(("head", args))
        if args["Key"] not in self.objects:
            raise Missing()
        return {"LastModified": datetime.now(UTC), "VersionId": "1"}
