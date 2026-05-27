"""Tail holdout helpers for hosted paper promotion validation."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


PROMOTION_PAPER_TAIL_TARGET_COUNT = 20
PROMOTION_PAPER_TAIL_MAX_COUNT = 60
PROMOTION_PAPER_TAIL_TOLERANCE = 1e-9


def paper_tail_oracle_rows(trade_log_path: Path) -> list[dict[str, Any]]:
    if not trade_log_path.is_file():
        return []
    try:
        with trade_log_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return []
    comparable: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        as_of = _date_part(_clean(row.get("date") or row.get("decision_time")))
        expected = _finite_float(row.get("next_position") or row.get("nextPosition"))
        if not as_of or expected is None:
            continue
        comparable.append(
            {
                "decisionIndex": idx,
                "asOf": as_of,
                "expectedNextPosition": expected,
                "source": trade_log_path.name,
            }
        )
    selected = select_paper_tail_oracle_sample(comparable)
    if not selected:
        return []
    holdout_start_index = _nonnegative_int(selected[0].get("decisionIndex"))
    cutover = comparable[holdout_start_index - 1] if holdout_start_index > 0 else None
    prior = paper_tail_prior_row(comparable, selected)
    position_change_count = paper_tail_position_change_count(selected, prior=prior)
    selection_reason = paper_tail_selection_reason(comparable, selected)
    for item in selected:
        item["validationRole"] = "holdout"
        item["holdoutStartDecisionIndex"] = holdout_start_index
        item["validationCutoverAsOf"] = cutover.get("asOf") if cutover else None
        item["validationCutoverDecisionIndex"] = (
            cutover.get("decisionIndex") if cutover else None
        )
        item["positionChangeCount"] = position_change_count
        item["selectionReason"] = selection_reason
    return selected


def select_paper_tail_oracle_sample(
    comparable: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not comparable:
        return []
    available = len(comparable) - 1 if len(comparable) > 1 else len(comparable)
    if available <= 0:
        return comparable[-1:]

    target_count = min(PROMOTION_PAPER_TAIL_TARGET_COUNT, available)
    max_count = min(PROMOTION_PAPER_TAIL_MAX_COUNT, available)
    selected = comparable[-target_count:]
    prior = paper_tail_prior_row(comparable, selected)
    if paper_tail_position_change_count(selected, prior=prior) > 0:
        return selected

    for count in range(target_count + 1, max_count + 1):
        expanded = comparable[-count:]
        prior = paper_tail_prior_row(comparable, expanded)
        if paper_tail_position_change_count(expanded, prior=prior) > 0:
            return expanded
        selected = expanded
    return selected


def paper_tail_prior_row(
    comparable: list[dict[str, Any]],
    selected: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not selected:
        return None
    start_index = _nonnegative_int(selected[0].get("decisionIndex"))
    if start_index is None or start_index <= 0:
        return None
    for item in reversed(comparable):
        if item.get("decisionIndex") == start_index - 1:
            return item
    return None


def paper_tail_position_change_count(
    selected: list[dict[str, Any]],
    *,
    prior: dict[str, Any] | None = None,
) -> int:
    previous = (
        _finite_float(prior.get("expectedNextPosition"))
        if isinstance(prior, dict)
        else None
    )
    count = 0
    for item in selected:
        current = _finite_float(item.get("expectedNextPosition"))
        if current is None:
            continue
        if (
            previous is not None
            and abs(current - previous) > PROMOTION_PAPER_TAIL_TOLERANCE
        ):
            count += 1
        previous = current
    return count


def paper_tail_selection_reason(
    comparable: list[dict[str, Any]],
    selected: list[dict[str, Any]],
) -> str:
    if not selected:
        return "none"
    available = len(comparable) - 1 if len(comparable) > 1 else len(comparable)
    target_count = min(PROMOTION_PAPER_TAIL_TARGET_COUNT, available)
    if len(selected) < target_count:
        return "all_available_with_cutover"
    if len(selected) == target_count:
        return "target_tail_window"
    prior = paper_tail_prior_row(comparable, selected)
    changes = paper_tail_position_change_count(selected, prior=prior)
    if changes > 0:
        return "expanded_to_recent_position_change"
    return "expanded_to_max_without_position_change"


def tail_consistency_payload(
    oracle_rows: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "method": "trade_log_holdout_next_position",
        "sampleSize": len(oracle_rows),
        "tolerance": PROMOTION_PAPER_TAIL_TOLERANCE,
        "windowStartAsOf": oracle_rows[0].get("asOf") if oracle_rows else None,
        "windowEndAsOf": oracle_rows[-1].get("asOf") if oracle_rows else None,
        "holdoutStartDecisionIndex": oracle_rows[0].get("holdoutStartDecisionIndex")
        if oracle_rows
        else None,
        "positionChangeCount": oracle_rows[0].get("positionChangeCount")
        if oracle_rows
        else None,
        "selectionReason": oracle_rows[0].get("selectionReason")
        if oracle_rows
        else None,
        "validationCutoverAsOf": oracle_rows[0].get("validationCutoverAsOf")
        if oracle_rows
        else None,
        "comparisons": _json_safe(comparisons),
    }


def redacted_trade_log_oracle_sample(
    comparable: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        redacted_timeline_row(item)
        for item in select_paper_tail_oracle_sample(comparable)
    ]


def redacted_timeline_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "decisionIndex": item.get("decisionIndex"),
        "asOf": item["asOf"],
        "decisionTime": item.get("decisionTime") or item["asOf"],
        "effectiveTime": item.get("effectiveTime") or item["asOf"],
        "source": item.get("source"),
    }


def redacted_tail_failure_payload(tail: dict[str, Any]) -> dict[str, Any]:
    comparisons = tail.get("comparisons")
    failed: list[dict[str, Any]] = []
    checked = 0
    if isinstance(comparisons, list):
        for item in comparisons:
            if not isinstance(item, dict):
                continue
            checked += 1
            abs_diff = _finite_float(item.get("absDiff"))
            if abs_diff is not None and abs_diff <= PROMOTION_PAPER_TAIL_TOLERANCE:
                continue
            failed.append(
                {
                    "asOf": _clean(item.get("asOf")),
                    "decisionIndex": item.get("decisionIndex"),
                    "absDiffPresent": abs_diff is not None,
                    "stateChanged": item.get("stateChanged") is True,
                }
            )
    return {
        "status": _clean(tail.get("status")),
        "method": _clean(tail.get("method")),
        "sampleSize": tail.get("sampleSize"),
        "checkedCount": checked or None,
        "failedSampleDates": failed,
        "diagnostic": (
            "sampled behavior diverged from the selected-round continuation "
            "oracle; revisit paperSignal.continuation and paperSignal.evidence "
            "instead of patching individual expected values"
        ),
    }


def _date_part(value: str) -> str:
    if not value:
        return ""
    if "T" in value:
        return value.split("T", 1)[0]
    return value.split(" ", 1)[0]


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _clean(value: Any) -> str:
    return str(value or "").strip()
