import copy
from pathlib import Path
import subprocess
import sys

import pytest

from app.ml.transformer import source_contract as c
from app.ml.transformer.verification_spec import canonical, digest


def test_source_metadata_import_needs_no_site_packages():
    result = subprocess.run([sys.executable, "-S", "-c",
        "import sys; from app.ml.transformer import source_contract; "
        "assert source_contract.SYMBOLS == ('AAPL', 'MSFT', 'NVDA'); "
        "assert 'numpy' not in sys.modules; "
        "assert 'app.ml.transformer.data' not in sys.modules"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def fixture():
    source = {"fold": "validation", "trade_date": "2019-10-30",
        "filename": "10302019.NASDAQ_ITCH50.gz", "source_sha256": "a" * 64,
        "parser_config_sha256": digest(canonical({"start_time_ms": 36000000,
            "end_time_ms": 37800000, "depth": 10, "min_free_bytes": 10 * 1024**3,
            "max_working_bytes": 20 * 1024**3, "format": "itch_parquet_v1",
            "parser_version": "nasdaq_itch_5_0_v1", "symbols": ["AAPL", "MSFT", "NVDA"],
            "trade_date": "2019-10-30"}))}
    manifests = {}
    for symbol in ("AAPL", "MSFT", "NVDA"):
        identity = digest(f'{source["source_sha256"]}:{source["parser_config_sha256"]}:{symbol}'.encode())[:12]
        manifests[symbol] = {"dataset_id": f"itch-{symbol.lower()}-2019-10-30-36000000-37800000-d10-{identity}",
            "dataset_schema_version": 1, "manifest_version": 1, "source_type": "nasdaq_itch",
            "format": "itch_parquet_v1", "parser_version": "nasdaq_itch_5_0_v1", "venue": "XNAS",
            "ingestion_mode": "streaming", "status": "ready", "price_scale": 10000,
            "symbol": symbol, "trade_date": source["trade_date"], "start_time_ms": 36000000,
            "end_time_ms": 37800000, "depth": 10, "row_count": 25,
            "source_name": source["filename"], "source_stream_sha256": source["source_sha256"],
            "parser_config_sha256": source["parser_config_sha256"],
            "truncation_limits": {"min_free_bytes": 10 * 1024**3, "max_working_bytes": 20 * 1024**3},
            "filters": {"start_time_ms": 36000000, "end_time_ms": 37800000, "depth": 10,
                "symbol": symbol, "symbols_normalized_in_one_pass": ["AAPL", "MSFT", "NVDA"]},
            "source_files": [{"name": source["filename"], "sha256": source["source_sha256"], "size_bytes": 100}]}
    return manifests, source


def test_entire_instrument_ancestry_is_kept_despite_shared_file_and_time():
    manifests, source = fixture()
    before = copy.deepcopy(manifests)
    result = c.verify_domains(manifests, source)
    assert set(result) == {"AAPL", "MSFT", "NVDA"}
    assert {v["source_sha256"] for v in result.values()} == {source["source_sha256"]}
    assert all(v["ancestry_scope"] == "entire_source_file_instrument_including_warmup" for v in result.values())
    assert result["AAPL"]["normalized_rows"] == 25 and manifests == before


@pytest.mark.parametrize("field,value", [("fold", "test"), ("trade_date", "2019-10-31"),
    ("filename", "alias.gz"), ("source_sha256", "bad"), ("parser_config_sha256", "b" * 64)])
def test_unknown_source_contract_is_rejected(field, value):
    manifests, source = fixture()
    source[field] = value
    with pytest.raises(ValueError):
        c.verify_domains(manifests, source)


@pytest.mark.parametrize("field,value", [("symbol", "MSFT"), ("venue", "OTHER"),
    ("source_type", "canonical_csv"), ("format", "new"), ("parser_version", "new"),
    ("dataset_schema_version", True), ("manifest_version", 2), ("ingestion_mode", "batch"),
    ("status", "invalid"), ("price_scale", 100), ("start_time_ms", 36000001),
    ("end_time_ms", 37800001), ("depth", 20), ("row_count", True), ("row_count", 0),
    ("source_name", "alias.gz"), ("source_stream_sha256", "b" * 64),
    ("parser_config_sha256", "b" * 64), ("dataset_id", "other")])
def test_changed_or_coerced_normalization_contract_is_rejected(field, value):
    manifests, source = fixture()
    manifests["AAPL"][field] = value
    with pytest.raises(ValueError):
        c.verify_domains(manifests, source)


@pytest.mark.parametrize("defect", ["missing_symbol", "extra_symbol", "missing_field", "filters",
    "extra_filter", "quotas", "missing_file", "duplicate_file", "file_name", "file_hash", "file_size", "file_bool"])
def test_incomplete_or_cross_symbol_evidence_is_rejected(defect):
    manifests, source = fixture()
    record = manifests["AAPL"]
    if defect == "missing_symbol":
        manifests.pop("NVDA")
    elif defect == "extra_symbol":
        manifests["OTHER"] = copy.deepcopy(record)
    elif defect == "missing_field":
        record.pop("parser_version")
    elif defect == "filters":
        record["filters"]["symbol"] = "MSFT"
    elif defect == "extra_filter":
        record["filters"]["cross_instrument"] = True
    elif defect == "quotas":
        record["truncation_limits"]["min_free_bytes"] += 1
    elif defect == "missing_file":
        record["source_files"] = []
    elif defect == "duplicate_file":
        record["source_files"] *= 2
    else:
        key, value = {"file_name": ("name", "alias.gz"), "file_hash": ("sha256", "b" * 64),
            "file_size": ("size_bytes", 101), "file_bool": ("size_bytes", True)}[defect]
        record["source_files"][0][key] = value
    with pytest.raises(ValueError):
        c.verify_domains(manifests, source)
