"""Narrow label contract for authenticated, instrument-local C4 replay metadata."""

_WINDOW_FIELDS = {
    "label", "attack_family", "label_source", "provenance_id", "start_tick", "end_tick",
    "start_timestamp_ns", "end_timestamp_ns", "end_inclusive", "phases",
}
_FAMILIES = {"spoofing_like_wall", "layering_like", "quote_stuffing"}


def verify_labels(run: dict) -> int:
    """Check pointwise labels; the caller authenticates and groups whole source domains.

    Tick windows are run-local, not absolute time. Their conservative ancestry is
    the entire source file for the instrument, including pre-window book state.
    Passing does not establish temporal or statistical independence, class support,
    or independently clean negative observations.
    """
    if (run.get("negative_label_source") != "research_control_assumption"
            or run.get("independently_verified_clean") is not False):
        raise ValueError("label proof requires the research-control limitation")
    run_id = run.get("run_id")
    windows = run.get("label_windows")
    if (not isinstance(run_id, str) or not run_id or "campaign_id" not in run
            or not isinstance(windows, list)):
        raise ValueError("label proof requires explicit run, campaign and windows")
    if run["campaign_id"] is None:
        if windows:
            raise ValueError("control replay cannot supply synthetic label windows")
        return 0
    if run["campaign_id"] != run_id or len(windows) != 1:
        raise ValueError("hybrid replay requires its own single label window")
    window = windows[0]
    if not isinstance(window, dict) or set(window) != _WINDOW_FIELDS:
        raise ValueError("unsupported label-window schema")
    if (type(window["label"]) is not int or window["label"] != 1
            or not isinstance(window["attack_family"], str) or window["attack_family"] not in _FAMILIES
            or window["label_source"] != "synthetic_scenario"
            or window["provenance_id"] is not None
            or not isinstance(window["phases"], dict)):
        raise ValueError("unsupported synthetic label contract")
    start, end = window["start_tick"], window["end_tick"]
    if (type(start) is not int or type(end) is not int or not 0 < start <= end
            or window["end_inclusive"] is not True
            or window["start_timestamp_ns"] is not None
            or window["end_timestamp_ns"] is not None):
        raise ValueError("label proof requires positive inclusive producer tick bounds")
    return 1
