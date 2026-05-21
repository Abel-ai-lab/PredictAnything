"""Readiness payload helpers for Abel strategy discovery."""

from __future__ import annotations


def readiness_results(readiness: dict) -> list[dict]:
    results = readiness.get("results") or []
    return [item for item in results if isinstance(item, dict)]


def readiness_usable_tickers(readiness: dict) -> list[str]:
    return [
        str(item.get("ticker") or "").strip().upper()
        for item in readiness_results(readiness)
        if item.get("usable")
    ]


def readiness_start_covered_tickers(readiness: dict) -> list[str]:
    return [
        str(item.get("ticker") or "").strip().upper()
        for item in readiness_results(readiness)
        if item.get("covers_requested_start")
    ]


def format_data_readiness_summary(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    requested = report.get("requested_window") or {}
    probe = report.get("probe") or {}
    probe_limit = probe.get("limit")
    return (
        f"{summary.get('start_covered_count', 0)} start-covered, "
        f"{summary.get('partial_window_count', 0)} partial, "
        f"{summary.get('no_data_count', 0)} no-data, "
        f"{summary.get('error_count', 0)} error "
        f"(start {requested.get('start', 'latest')}, probe {probe_limit or 'n/a'})"
    )


def render_target_boundary_line(readiness: dict) -> str:
    report = readiness or {}
    target_boundary = report.get("target_boundary") or {}
    classification = target_boundary.get("classification")
    if not classification:
        return "not recorded"
    observed_first = target_boundary.get("observed_first_timestamp")
    observed_last = target_boundary.get("observed_last_timestamp")
    parts = [str(classification)]
    if observed_first:
        parts.append(f"observed_first={observed_first}")
    if observed_last:
        parts.append(f"observed_last={observed_last}")
    return ", ".join(parts)


def render_readiness_guidance(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    requested_start = str((report.get("requested_window") or {}).get("start") or "latest")
    coverage_hints = report.get("coverage_hints") or {}
    target_safe = coverage_hints.get("target_safe_start")
    dense_overlap = coverage_hints.get("dense_overlap_hint_start")
    if target_safe and dense_overlap and target_safe != dense_overlap:
        return (
            f"Desired start remains {requested_start}. Target-safe coverage is currently observed from "
            f"{target_safe}, while denser driver overlap appears around {dense_overlap} if the branch needs it."
        )
    if target_safe and target_safe != requested_start:
        return (
            f"Desired start remains {requested_start}. Target-safe coverage is currently observed from "
            f"{target_safe}; later driver overlap is optional, not mandatory."
        )
    if dense_overlap:
        return (
            f"Desired start remains {requested_start}. Dense overlap is hinted around {dense_overlap}, "
            "while earlier starts remain a branch-level coverage tradeoff."
        )
    return (
        f"Desired start remains {requested_start}. Use readiness as a coverage profile, not as a mandatory "
        "strategy-design verdict."
    )


def render_discovery_readiness_section(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return "`No data readiness report recorded yet. Run live discovery again after edge verification is available.`"
    start_covered = ", ".join(readiness_start_covered_tickers(readiness)) or "none"
    usable = ", ".join(readiness_usable_tickers(readiness)) or "none"
    lines = [
        f"- summary: `{format_data_readiness_summary(readiness)}`\n"
        f"- target_boundary: `{render_target_boundary_line(readiness)}`\n"
        f"- usable_tickers: `{usable}`\n"
        f"- start_covered_tickers: `{start_covered}`"
    ]
    warning = build_readiness_warning(readiness)
    if warning:
        lines.append(f"- warning: `{warning}`")
    for line in readiness_coverage_hint_lines(readiness):
        lines.append(f"- coverage_hint: `{line}`")
    guidance = render_readiness_guidance(readiness)
    if guidance:
        lines.append(f"- interpretation: `{guidance}`")
    return "\n".join(lines)


def build_readiness_warning(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    if int(summary.get("usable_count", 0) or 0) == 0:
        return "No usable tickers were confirmed for the requested backtest window."
    requested_start = (report.get("requested_window") or {}).get("start", "latest")
    target_boundary = report.get("target_boundary") or {}
    classification = target_boundary.get("classification")
    observed_first = target_boundary.get("observed_first_timestamp")
    if classification == "confirmed_after_requested_start":
        return (
            "Target history begins after the session requested backtest_start "
            f"{requested_start}. Treat this as a session-level coverage note; branches may still "
            "choose narrower explicit starts intentionally."
        )
    if classification == "unknown_probe_truncated":
        observed_suffix = (
            f" The deepest observed target history begins at {observed_first}."
            if observed_first
            else ""
        )
        return (
            "Target coverage before the requested backtest_start "
            f"{requested_start} is not yet confirmed.{observed_suffix}"
        )
    if int(summary.get("start_covered_count", 0) or 0) <= 0:
        return (
            "Discovered graph inputs are only partially available from the session requested start "
            f"{requested_start}. Treat this as coverage context; branches that depend on strict "
            "overlap should inspect coverage hints."
        )
    return ""


def readiness_coverage_hint_lines(readiness: dict) -> list[str]:
    report = readiness or {}
    coverage_hints = report.get("coverage_hints") or {}
    lines: list[str] = []
    target_start = coverage_hints.get("target_safe_start")
    common_start = coverage_hints.get("dense_overlap_hint_start")
    if target_start:
        lines.append(f"target_safe={target_start}")
    if common_start:
        lines.append(f"dense_overlap={common_start}")
    return lines
