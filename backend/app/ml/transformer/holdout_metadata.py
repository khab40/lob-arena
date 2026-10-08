"""One bounded metadata audit: three manifest GETs and 62 object HEADs, no rows."""
from pathlib import Path

from .holdout_reference import _json
from .verification_spec import ENDPOINT, canonical, digest
from .verification_transport import deadline

BUCKET = "aimada-wave1-final-e00g6zvxpr00"
PREFIX = "releases/nasdaq-public-sample-v1-c4-5c85182-20260905/staging/"
ROOT_IDENTITY_SHA = "eec7f9801ec0131ee88e51ace855fc0e0c22fb525de0432c281d8f80025c4803"
MANIFESTS = {
    "frozen-root.json": "642c7258b3424de05bbe8054a0b5c963b3f9fc9c2af65e1892e906c68fe0e7b9",
    "tabular-projection.json": "2464d7b4e952ee5b007f06e1809eba66e7502efb1484ab1e7f4e034be32e13e7",
    "sequence-projection.json": "bd26a35b3042ec7afbf9c16f26a913a0f51a6389e17a48cbe8838f520094ebfb"}
MAX_OBJECT = 256 * 1024
RUNS = tuple(f"xnas-2019-12-30-{symbol}-{variant}" for symbol in ("aapl", "msft", "nvda")
             for variant in ("control", *(f"{family}-s{seed}" for family in
                 ("layering_like", "quote_stuffing", "spoofing_like_wall") for seed in (41, 42, 43))))
FINAL_KEYS = tuple(PREFIX + "manifests/" + name for name in MANIFESTS) + tuple(
    PREFIX + f"artifacts/{kind}/test/{run}.parquet" for kind in ("tabular", "sequence") for run in RUNS)
BASELINE_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
BASELINE_PREFIX = "campaigns/nasdaq-g6-development-20260907/final/nasdaq-g8-replacement-r5-20260917/artifacts/prediction/"
BASELINE = {"prediction-manifest.json": {"sha256": "7909c017ff2f0bbbbf5fbaf821b550047ccdefcbb9f0359f370818bbb5d3736d", "size_bytes": 13416, "version_id": "1"},
            "predictions.parquet": {"sha256": "05298a29c1875a26b638bda26be43d6e79e0c978818779502ee964db1f5ead9f", "size_bytes": 931523, "version_id": "1"}}


def shard_inventory(manifests):
    root, tab, seq = (manifests[name] for name in MANIFESTS)
    if digest(canonical(root)) != ROOT_IDENTITY_SHA:
        raise ValueError("final frozen root identity differs")
    for value in (tab, seq):
        if (value["access_scope"] != "final_test" or value["root_sha256"] != ROOT_IDENTITY_SHA
                or value["folds"] != ["test"] or len(value["shards"]) != 30
                or {s["run_id"] for s in value["shards"]} != set(RUNS)):
            raise ValueError("final manifest scope, root or replay inventory differs")
    if (sum(s["supervised_row_count"] for s in tab["shards"]) != 15160
            or seq["order_columns"] != ["prediction_timestamp_ns", "sequence"]):
        raise ValueError("final manifest count or causal order differs")
    by_run = {s["run_id"]: s for s in seq["shards"]}
    result = []
    for shard in tab["shards"]:
        history = by_run[shard["run_id"]]
        if (history["sequence_count"] != shard["supervised_row_count"] or history["sequence_length"] != 64
                or history["sequence_identity_sha256"] != shard["row_identity_sha256"]):
            raise ValueError("final sequence shape or row identities differ")
        for kind, ref in (("tabular", shard["rows"]), ("sequence", history["sequences"])):
            expected = f"{kind}/test/{shard['run_id']}.parquet"
            if ref["uri"] != expected:
                raise ValueError("final shard leaves exact HEAD allowlist")
            result.append({"bucket": BUCKET, "key": PREFIX + "artifacts/" + expected,
                           "sha256": ref["sha256"], "size_bytes": ref["size_bytes"]})
    return result


def _header(response, expected=None):
    version, size = response.get("VersionId"), response.get("ContentLength")
    if (type(version) is not str or not version or version == "null"
            or type(size) is not int or size <= 0):
        raise ValueError("object has no bounded size or immutable version")
    if expected and (size != expected["size_bytes"] or version != expected.get("version_id", version)):
        raise ValueError("object header differs from expected size or version")
    if expected and response.get("Metadata", {}).get("sha256", expected["sha256"]) != expected["sha256"]:
        raise ValueError("object checksum metadata differs")
    return {"version_id": version, "size_bytes": size}


def collect(s3, proposal_raw, approved_sha256, output):
    """Operator supplies the separately approved proposal hash; never issue credentials."""
    if (type(proposal_raw) is not bytes or len(proposal_raw) > 65536
            or digest(proposal_raw) != approved_sha256):
        raise ValueError("metadata proposal differs from operator approval")
    proposal = _json(proposal_raw)
    if (proposal["final_keys"] != list(FINAL_KEYS)
            or proposal["baseline_keys"] != [BASELINE_PREFIX + name for name in BASELINE]
            or proposal["bounds"] != {"get_attempts": 3, "head_attempts": 62,
                "max_object_bytes": MAX_OBJECT, "seconds": 300, "automatic_retries": 0}):
        raise ValueError("metadata proposal scope or bounds differ")
    config = s3.meta.config
    if (s3.meta.endpoint_url != ENDPOINT or config.region_name != "eu-north1"
            or config.s3.get("addressing_style") != "path"
            or config.retries.get("total_max_attempts") != 1
            or config.connect_timeout != 5 or config.read_timeout != 5):
        raise ValueError("metadata audit requires tested bounded no-retry transport")
    output = Path(output)
    output.mkdir(exist_ok=False)
    manifests, receipts = {}, []
    gets = heads = 0
    try:
        with deadline(300):
            for name, expected_sha in MANIFESTS.items():
                key = PREFIX + "manifests/" + name
                gets += 1
                response = s3.get_object(Bucket=BUCKET, Key=key)
                body = response["Body"]
                try:
                    header = _header(response)
                    if header["size_bytes"] > MAX_OBJECT:
                        raise ValueError("manifest exceeds byte bound")
                    raw = body.read(header["size_bytes"] + 1)
                    if len(raw) != header["size_bytes"] or digest(raw) != expected_sha:
                        raise ValueError("manifest bytes differ from frozen hash or length")
                    manifests[name] = _json(raw)
                    (output / name).write_bytes(raw)
                    receipts.append({"method": "GET", "bucket": BUCKET, "key": key,
                                     "sha256": expected_sha, **header})
                finally:
                    body.close()
            refs = shard_inventory(manifests) + [{"bucket": BASELINE_BUCKET, "key": BASELINE_PREFIX + name,
                                                 **ref} for name, ref in BASELINE.items()]
            for ref in refs:
                heads += 1
                args = {"Bucket": ref["bucket"], "Key": ref["key"]}
                if "version_id" in ref:
                    args["VersionId"] = ref["version_id"]
                response = s3.head_object(**args)
                receipts.append({"method": "HEAD", **ref, **_header(response, ref),
                                 "payload_bytes_read": 0, "payload_hash_verified": False})
        result = {"schema_version": "transformer_holdout_metadata_audit_v1", "status": "verified_metadata",
            "proposal_sha256": approved_sha256, "objects": receipts, "get_attempts": gets,
            "head_attempts": heads, "final_payload_reads": 0, "model_execution": False,
            "execution_authorized": False, "fresh_payload_integrity_verified": False}
        (output / "verification.json").write_bytes(canonical(result))
        return result
    except Exception as error:
        (output / "failure.json").write_bytes(canonical({"error_type": type(error).__name__,
            "get_attempts": gets, "head_attempts": heads, "automatic_retry": False}))
        raise
    finally:
        (output / "receipts.json").write_bytes(canonical(receipts))
