"""Reviewed C4 symbol-local producer contract; not a payload observation audit."""
from __future__ import annotations

import re

from .role_manifest import SYMBOLS
from .verification_spec import canonical, digest

PRODUCER_COMMIT = "cf426c0db0940a985133fc7c8482623186acd5a4"
PRODUCER_IMAGE = ("cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/mdp@sha256:"
    "8ba71e9ed8ef90b10efe7abd3b2d8d8e0089990281a12c0c903ab8f7508e7195")
DATE = "2019-10-30"
WINDOW = {"start_time_ms": 36_000_000, "end_time_ms": 37_800_000, "depth": 10}
LIMITS = {"min_free_bytes": 10 * 1024**3, "max_working_bytes": 20 * 1024**3}
PARSER = "nasdaq_itch_5_0_v1"
FORMAT = "itch_parquet_v1"


def _matches(record, expected):
    return isinstance(record, dict) and all(
        key in record and canonical(record[key]) == canonical(value)
        for key, value in expected.items())


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def verify_domains(manifests: dict, source: dict) -> dict:
    """Caller must authenticate these raw dictionaries against the frozen anchor.

    Distinct instruments partition the entire source, including book warm-up.
    Different parser hashes, output hashes or time windows never prove separation.
    """
    if (not isinstance(manifests, dict) or set(manifests) != set(SYMBOLS)
            or not _matches(source, {"fold": "validation", "trade_date": DATE,
                "filename": "10302019.NASDAQ_ITCH50.gz"})
            or not _sha(source.get("source_sha256"))
            or not _sha(source.get("parser_config_sha256"))):
        raise ValueError("source contract requires the exact C4 validation domain")
    parser_config = {**WINDOW, **LIMITS, "format": FORMAT,
        "parser_version": PARSER, "symbols": list(SYMBOLS), "trade_date": DATE}
    parser_sha = digest(canonical(parser_config))
    if source["parser_config_sha256"] != parser_sha:
        raise ValueError("source parser configuration differs from reviewed producer")
    domains, common_file = {}, None
    for symbol in SYMBOLS:
        record = manifests[symbol]
        identity = digest(f'{source["source_sha256"]}:{parser_sha}:{symbol}'.encode())[:12]
        dataset_id = f"itch-{symbol.lower()}-{DATE}-36000000-37800000-d10-{identity}"
        expected = {**WINDOW, "dataset_id": dataset_id, "dataset_schema_version": 1,
            "manifest_version": 1, "source_type": "nasdaq_itch", "format": FORMAT,
            "parser_version": PARSER, "ingestion_mode": "streaming", "venue": "XNAS",
            "status": "ready", "price_scale": 10000, "symbol": symbol, "trade_date": DATE,
            "source_name": source["filename"], "source_stream_sha256": source["source_sha256"],
            "parser_config_sha256": parser_sha, "truncation_limits": LIMITS,
            "filters": {**WINDOW, "symbol": symbol, "symbols_normalized_in_one_pass": list(SYMBOLS)}}
        if not _matches(record, expected):
            raise ValueError("normalized manifest differs from symbol-local producer contract")
        files, rows = record.get("source_files"), record.get("row_count")
        if (type(rows) is not int or rows <= 0 or not isinstance(files, list) or len(files) != 1
                or not isinstance(files[0], dict) or set(files[0]) != {"name", "sha256", "size_bytes"}
                or not _matches(files[0], {"name": source["filename"], "sha256": source["source_sha256"]})
                or type(files[0]["size_bytes"]) is not int or files[0]["size_bytes"] <= 0):
            raise ValueError("normalized manifest lacks one complete source file or positive row count")
        if common_file is not None and files[0] != common_file:
            raise ValueError("normalized instruments disagree on source file identity")
        common_file = files[0]
        domains[symbol] = {"source_sha256": source["source_sha256"], "instrument": symbol,
            "dataset_id": dataset_id, "normalized_rows": rows,
            "ancestry_scope": "entire_source_file_instrument_including_warmup"}
    return domains
