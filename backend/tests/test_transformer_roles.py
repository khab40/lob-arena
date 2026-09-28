from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("numpy")

from app.ml.transformer.role_manifest import ROLES, assign_roles, metadata_plan  # noqa: E402
from app.ml.transformer.role_audit import summarize_rows  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402


def groups():
    return [{"base_session_id": f"session-{i}", "source_identity": {
        "source_sha256": "a" * 64, "trade_date": "2019-10-30", "instrument": symbol}}
        for i, symbol in enumerate(("AAPL", "MSFT", "NVDA"))]


def test_roles_are_independent_of_input_order_and_merge_replay_aliases():
    values = groups()
    values.append({**deepcopy(values[0]), "base_session_id": "another-replay-alias"})
    assigned = assign_roles(values)
    assert canonical(assigned) == canonical(assign_roles(reversed(values)))
    assert {g["role"] for g in assigned} == set(ROLES)
    same_source = next(g for g in assigned if "session-0" in g["base_sessions"])
    assert same_source["base_sessions"] == ["another-replay-alias", "session-0"]


def test_source_aliases_do_not_create_independent_roles():
    values = groups()
    values[1]["source_identity"] = deepcopy(values[0]["source_identity"])
    with pytest.raises(ValueError, match="three independent"):
        assign_roles(values)
    with pytest.raises(ValueError, match="duplicate base"):
        assign_roles(groups() + [groups()[0]])


def rows(positive=20):
    return [NS(fold="validation", run_id=role, target_id=f"{role}-{i}", label=int(i < positive))
            for role in ROLES for i in range(40)]


def summarize(values):
    return summarize_rows(values, {r: r for r in ROLES}, {r: 40 for r in ROLES})


def test_exact_role_row_coverage_and_class_support_boundary():
    result = summarize(rows())
    assert all(r["support_passed"] for r in result.values())
    assert all(r["row_count"] == len(r["target_ids"]) == 40 for r in result.values())
    assert not any(r["support_passed"] for r in summarize(rows(19)).values())
    assert len({r["row_identity_sha256"] for r in result.values()}) == 3


@pytest.mark.parametrize("defect", ["duplicate", "missing", "extra", "final", "run", "label"])
def test_audit_rejects_incomplete_or_cross_role_payloads(defect):
    values = rows()
    if defect == "duplicate":
        values[-1].target_id = values[0].target_id
    elif defect == "missing":
        values.pop()
    elif defect == "extra":
        values.append(NS(fold="validation", run_id=ROLES[0], target_id="extra", label=0))
    elif defect == "final":
        values[-1].fold = "test"
    elif defect == "run":
        values[-1].run_id = "unknown"
    else:
        values[-1].label = True
    with pytest.raises(ValueError):
        summarize(values)


def metadata():
    sources = [NS(trade_date=day, fold=fold, source_sha256="a" * 64,
        source_manifest_sha256="b" * 64, parser_config_sha256="c" * 64)
        for day, fold in (("2019-01-30", "train"), ("2019-03-27", "train"),
                          ("2019-10-30", "validation"), ("2019-12-30", "test"))]
    root = NS(sources=sources, canonical_hash=lambda: "d" * 64,
        feature_release_id="fixture", feature_release_sha256="e" * 64)
    shards = [NS(fold=s.fold, base_session_id=f"xnas-{s.trade_date}-{symbol.lower()}",
        campaign_id=None, run_id=f"{s.trade_date}-{symbol}", replay_manifest_sha256="f" * 64,
        rows=NS(sha256="a" * 64), row_identity_sha256="b" * 64,
        supervised_row_count=5575 if s.fold == "train" else 3070)
        for s in sources if s.fold != "test" for symbol in ("AAPL", "MSFT", "NVDA")]
    seq = [NS(**{k: v for k, v in vars(s).items() if k not in ("rows",)},
        sequence_length=64, sequence_count=s.supervised_row_count,
        sequence_identity_sha256=s.row_identity_sha256, sequences=NS(sha256="c" * 64)) for s in shards]
    return root, NS(access_scope="development", root_sha256="d" * 64, shards=shards), NS(
        access_scope="development", root_sha256="d" * 64, shards=seq)


def test_metadata_never_claims_payload_or_gpu_readiness():
    result = metadata_plan(*metadata())
    assert result["fold_rows"] == {"train": 33450, "validation": 9210}
    assert result["payload_audit"] == "pending" and result["gpu_ready"] is False
    assert sorted(g["row_count"] for g in result["groups"]) == [3070] * 3


@pytest.mark.parametrize("defect", ["scope", "root", "session", "count", "sequence", "domain", "fold"])
def test_metadata_corruption_fails_before_any_payload_access(defect):
    root, tab, seq = metadata()
    if defect == "scope":
        tab.access_scope = "final_test"
    elif defect == "root":
        tab.root_sha256 = "0" * 64
    elif defect == "session":
        tab.shards[-1].base_session_id = "unknown"
    elif defect == "count":
        tab.shards[-1].supervised_row_count -= 1
    elif defect == "sequence":
        seq.shards[-1].sequence_identity_sha256 = "0" * 64
    elif defect == "domain":
        seq.shards.pop()
    else:
        tab.shards[-1].fold = seq.shards[-1].fold = "train"
    with pytest.raises(ValueError):
        metadata_plan(root, tab, seq)
