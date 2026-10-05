"""Tiny declared records and fake IO; never train or execute a detector."""
import io
import json
from pathlib import Path

import pyarrow.parquet as pq
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.ml.transformer.data import DevelopmentInputs
from app.ml.transformer.holdout_context import check_parity
from app.ml.transformer.holdout_spec import G8_PREFIX, HoldoutRequest, InputObject, OUTPUT_ROOT
from app.ml.transformer.settings_schema import Artifact
from app.ml.transformer.verification_spec import canonical, digest
from transformer_input_fixtures import make_inputs


def reference(path, raw, scope="final_test", uri=None):
    return InputObject(path=path, scope=scope, reference=Artifact(uri=uri or "s3://fixture/" + path,
        version_id="1", sha256=digest(raw), size_bytes=len(raw)))


def request(items, **updates):
    saved = canonical([{"target_id": "a" * 64, "label": 1, "logit": 1.0}])
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    fields = dict(run_id="transformer-holdout-fixture", source_commit="1" * 40,
        image_repository="cr.eu-north1.nebius.cloud/fixture/tr", image_digest="sha256:" + "2" * 64,
        context_public_key=public, nonce="3" * 32, package_sha256="4" * 64, provider_spec_sha256="5" * 64,
        inputs=tuple(items) + (reference("reference.json", saved, "development"),),
        tabular_path="tabular.json", sequence_path="sequence.json", baseline_paths=("baseline.parquet",),
        reference_logits_path="reference.json", reference_targets_sha256=digest(canonical(("a" * 64,))),
        reference_rows=1, output_prefix=OUTPUT_ROOT + "transformer-holdout-fixture/")
    fields.update(updates)
    value = HoldoutRequest(**fields)
    context = {"request_sha256": value.sha256(), "run_id": value.run_id,
        "image_digest": value.image_digest, "nonce": value.nonce,
        "provider_spec_sha256": value.provider_spec_sha256,
        "job_id": "aijob-fixture", "provider_readback_sha256": "6" * 64}
    envelope = {"context": context, "signature": private.sign(canonical(context)).hex()}
    gate = check_parity(value, context, saved, ("a" * 64,), (1,), (1.0,))
    return value, envelope, gate, saved


def final_inputs(path, *, mutate=None):
    args = make_inputs(path, mutate=mutate)
    contract = DevelopmentInputs.open(**make_inputs(path / "development")).contract
    items = []
    for name in ("tabular", "sequence"):
        manifest = json.loads(args[name + "_path"].read_bytes())
        manifest.update(access_scope="final_test", folds=["test"])
        shard = manifest["shards"][1]
        shard.update(fold="test", base_session_id="2019-12-30-aapl")
        manifest["shards"] = [shard]
        raw = canonical(manifest)
        args[name + "_path"].write_bytes(raw)
        items.append(reference(name + ".json", raw))
    for name in ("validation.parquet", "validation-sequences.parquet"):
        items.append(reference(name, (path / name).read_bytes()))
    items.append(reference("baseline.parquet", b"unused", uri=G8_PREFIX + "predictions.parquet"))
    req, envelope, gate, saved = request(items)
    return req, gate, contract, args, envelope


def baseline_rows(dataset):
    source = pq.read_table(dataset.artifact_root / "validation.parquet").to_pylist()
    for row in source:
        yield {"prediction_row_id": digest(
            f'{row["run_id"]}|{row["prediction_timestamp_ns"]}|{row["sequence"]}'.encode()),
            "fold": "test", "base_session_id": "2019-12-30-aapl", "campaign_id": None,
            "instrument": "AAPL", "attack_family": "spoofing_like_wall" if row["label"] else None,
            "calibrated_probability": .9 if row["label"] else .1,
            **{key: row[key] for key in ("run_id", "sequence", "prediction_timestamp_ns", "label")}}


class FakeS3:
    def __init__(self):
        self.objects, self.calls, self.fail_put = {}, [], None

    def get_object(self, **args):
        self.calls.append(("get", args))
        raw = self.objects[(args["Bucket"], args["Key"])]
        return {"Body": io.BytesIO(raw), "VersionId": "1", "ContentLength": len(raw),
                "Metadata": {"sha256": digest(raw)}}

    def put_object(self, **args):
        self.calls.append(("put", args))
        location = (args["Bucket"], args["Key"])
        if location in self.objects:
            raise ValueError("immutable object exists")
        self.objects[location] = args["Body"]
        if self.fail_put:
            raise TimeoutError("ambiguous write")
        return {"VersionId": "1"}

    def list_objects_v2(self, **args):
        self.calls.append(("list", args))
        matches = [key for bucket, key in self.objects if bucket == args["Bucket"] and key.startswith(args["Prefix"])]
        return {"KeyCount": len(matches), "Contents": matches[:1]}
