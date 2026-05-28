"""Compact paper validation traces for hosted paper promotion."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from abel_invest.narrative_core import promotion_tail


PROMOTION_TAIL_TRACE_FILENAME = "promotion-tail-trace.json"
PROMOTION_TAIL_TRACE_SCHEMA = "abel-invest.paper-tail-trace/v1"


def write_paper_tail_trace(
    destination: Path,
    paper_dry_run: dict[str, Any],
) -> Path | None:
    smoke = paper_dry_run.get("smoke")
    if not isinstance(smoke, dict):
        return None
    trace_path = destination / PROMOTION_TAIL_TRACE_FILENAME
    trace_path.write_text(
        json.dumps(
            {
                "schema": PROMOTION_TAIL_TRACE_SCHEMA,
                "paperDryRun": _json_safe(paper_dry_run),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return trace_path


def paper_dry_run_gate_summary(
    paper_dry_run: dict[str, Any],
    *,
    trace_path: Path | None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "status",
        "method",
        "reason",
        "paperExecution",
        "paperSignal",
        "fullRuntimeCompute",
        "incrementalReady",
        "paperExecutionProfile",
        "maxCallElapsedSeconds",
    ):
        if key in paper_dry_run:
            summary[key] = _json_safe(paper_dry_run[key])
    continuation = paper_dry_run.get("agentContinuation")
    if isinstance(continuation, dict):
        summary["agentContinuation"] = {
            key: _json_safe(continuation.get(key))
            for key in ("method", "reason")
            if continuation.get(key) is not None
        }
    smoke = paper_dry_run.get("smoke")
    if isinstance(smoke, dict):
        summary["smoke"] = _paper_smoke_gate_summary(smoke, trace_path=trace_path)
    if trace_path is not None:
        summary["tracePath"] = f"edge/{PROMOTION_TAIL_TRACE_FILENAME}"
    return summary


def tail_parity_failure_diagnosis(
    tail: dict[str, Any],
    *,
    selected_round_cutover_end: str = "",
    trace_path: str = "",
) -> dict[str, Any]:
    summary = (
        _tail_consistency_summary(tail)
        if isinstance(tail.get("comparisons"), list)
        else dict(tail)
    )
    diagnosis = {
        key: _json_safe(summary.get(key))
        for key in (
            "status",
            "method",
            "sampleSize",
            "comparisonCount",
            "mismatchCount",
            "stateChangedCount",
            "positionChangeCount",
            "windowStartAsOf",
            "windowEndAsOf",
            "validationCutoverAsOf",
            "holdoutStartDecisionIndex",
            "selectionReason",
        )
        if key in summary
    }
    first_mismatch = summary.get("firstMismatch")
    if isinstance(first_mismatch, dict):
        diagnosis["firstMismatch"] = _json_safe(first_mismatch)
        mismatch_as_of = _clean(first_mismatch.get("asOf"))
        if selected_round_cutover_end:
            diagnosis["firstMismatchIsSelectedRoundEnd"] = (
                mismatch_as_of == selected_round_cutover_end
            )
    if trace_path:
        diagnosis["tracePath"] = trace_path
    if selected_round_cutover_end:
        diagnosis["selectedRoundCutoverEnd"] = selected_round_cutover_end
        diagnosis["immutableContractFacts"] = [
            "selectedRoundCutoverEnd is the terminal selected research date",
            (
                "stateful continuation startup state must be valid through "
                "selectedRoundCutoverEnd; do not shorten stateEnd to a mismatch date"
            ),
            (
                "tail expected positions are validation evidence only and must not be "
                "copied into strategy code, assets, or initial state"
            ),
        ]
    diagnosis["repairGoal"] = (
        "make the live paper continuation produce the same next_position as the "
        "selected research tail while preserving the declared hosted paper contract"
    )
    return diagnosis


def _paper_smoke_gate_summary(
    smoke: dict[str, Any],
    *,
    trace_path: Path | None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "asOf",
        "nextPosition",
        "elapsedSeconds",
        "firstElapsedSeconds",
        "secondElapsedSeconds",
        "stateChangedFirstCall",
        "stateChangedSecondCall",
        "sameResult",
        "warnings",
        "timeoutSeconds",
        "diagnosis",
    ):
        if key in smoke:
            summary[key] = _json_safe(smoke[key])
    tail = smoke.get("tailConsistency")
    if isinstance(tail, dict):
        summary["tailConsistency"] = _tail_consistency_summary(tail)
    bootstrap = smoke.get("validationBootstrap")
    if isinstance(bootstrap, dict):
        summary["validationBootstrap"] = _validation_bootstrap_summary(bootstrap)
    warm_start = smoke.get("warmStart")
    if isinstance(warm_start, dict):
        summary["warmStart"] = _json_safe(warm_start)
    result = smoke.get("result")
    if isinstance(result, dict):
        summary["result"] = _paper_run_result_summary(result)
    validation_context = smoke.get("validationContext")
    if isinstance(validation_context, dict):
        summary["validationContext"] = _validation_context_summary(validation_context)
    generated = smoke.get("generatedInitialStateFiles")
    if isinstance(generated, list):
        summary["generatedInitialStateFileCount"] = len(generated)
        summary["generatedInitialStateFiles"] = [
            item.get("artifactPath")
            for item in generated
            if isinstance(item, dict) and item.get("artifactPath")
        ]
    if trace_path is not None:
        summary["tracePath"] = f"edge/{PROMOTION_TAIL_TRACE_FILENAME}"
    return summary


def _tail_consistency_summary(tail: dict[str, Any]) -> dict[str, Any]:
    comparisons = tail.get("comparisons")
    comparison_rows = [
        item for item in comparisons if isinstance(item, dict)
    ] if isinstance(comparisons, list) else []
    mismatches = [
        item
        for item in comparison_rows
        if _finite_float(item.get("absDiff")) is None
        or float(item.get("absDiff")) > promotion_tail.PROMOTION_PAPER_TAIL_TOLERANCE
    ]
    summary = {
        key: _json_safe(tail.get(key))
        for key in (
            "status",
            "method",
            "sampleSize",
            "tolerance",
            "windowStartAsOf",
            "windowEndAsOf",
            "holdoutStartDecisionIndex",
            "positionChangeCount",
            "selectionReason",
            "validationCutoverAsOf",
        )
        if key in tail
    }
    summary["comparisonCount"] = len(comparison_rows)
    summary["mismatchCount"] = len(mismatches)
    summary["stateChangedCount"] = sum(
        1 for item in comparison_rows if item.get("stateChanged") is True
    )
    if mismatches:
        summary["firstMismatch"] = _tail_mismatch_summary(mismatches[0])
    return summary


def _tail_mismatch_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _json_safe(item.get(key))
        for key in (
            "asOf",
            "decisionIndex",
            "expectedNextPosition",
            "actualNextPosition",
            "absDiff",
            "elapsedSeconds",
            "stateChanged",
        )
        if key in item
    }


def _validation_bootstrap_summary(bootstrap: dict[str, Any]) -> dict[str, Any]:
    summary = {
        key: _json_safe(bootstrap.get(key))
        for key in (
            "required",
            "status",
            "method",
            "cutoverAsOf",
            "elapsedSeconds",
            "stateChanged",
            "wroteDefaultStateFile",
        )
        if key in bootstrap
    }
    result = bootstrap.get("result")
    if isinstance(result, dict):
        summary["result"] = {
            key: _json_safe(result.get(key))
            for key in (
                "cutover_as_of",
                "last_as_of",
                "last_next_position",
                "state_file",
                "state_kind",
                "state_schema",
            )
            if key in result
        }
    return summary


def _paper_run_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    decision_rows = result.get("decision_rows")
    latest_snapshot = result.get("latest_snapshot")
    return {
        key: value
        for key, value in {
            "id": _json_safe(result.get("id")),
            "n_rows": _json_safe(result.get("n_rows")),
            "last_date": _json_safe(result.get("last_date")),
            "execution_mode": _json_safe(result.get("execution_mode")),
            "paper_history_boundary": _json_safe(result.get("paper_history_boundary")),
            "decisionRowCount": len(decision_rows)
            if isinstance(decision_rows, list)
            else None,
            "latest_snapshot": _json_safe(latest_snapshot)
            if isinstance(latest_snapshot, dict)
            else None,
        }.items()
        if value is not None
    }


def _validation_context_summary(context: dict[str, Any]) -> dict[str, Any]:
    feed_sources = context.get("feedSources")
    feed_names = sorted(feed_sources) if isinstance(feed_sources, dict) else []
    return {
        "feedMode": _json_safe(context.get("feedMode")),
        "feedCount": len(feed_names),
        "feeds": feed_names,
    }


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


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
