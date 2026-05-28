"""Hosted paper contract report helpers."""

from __future__ import annotations

import json
from typing import Any

from .promotion_constants import (
    PROMOTION_AGENT_REPORT_SCHEMA,
    PROMOTION_CONTRACT_REPORT_FILENAME,
    PROMOTION_HOSTED_CONTRACT_SCOPE,
)
from .promotion_models import PromotionHostedPaperContractRequired
from .promotion_utils import _clean

def _report_has_hosted_paper_contract(report: dict[str, Any]) -> bool:
    return (
        _clean(report.get("kind")) == PROMOTION_HOSTED_CONTRACT_SCOPE
        and _clean(report.get("scope")) == PROMOTION_HOSTED_CONTRACT_SCOPE
    )
def _paper_signal_continuation_payload(
    paper_signal: dict[str, Any],
) -> dict[str, Any] | None:
    continuation = paper_signal.get("continuation")
    if isinstance(continuation, dict):
        return continuation
    return None


def _paper_signal_design_payload(paper_signal: dict[str, Any]) -> dict[str, Any] | None:
    design = paper_signal.get("design")
    if isinstance(design, dict):
        return design
    return None


def _paper_signal_evidence_payload(
    paper_signal: dict[str, Any],
) -> dict[str, Any] | None:
    evidence = paper_signal.get("evidence")
    if isinstance(evidence, dict):
        return evidence
    return None
def _report_continuation_method(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return ""
    paper_signal = report.get("paperSignal")
    if not isinstance(paper_signal, dict):
        return ""
    continuation = _paper_signal_continuation_payload(paper_signal)
    return _clean(continuation.get("method")) if isinstance(continuation, dict) else ""


def _report_paper_execution_profile(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None
    paper_signal = report.get("paperSignal")
    if not isinstance(paper_signal, dict):
        return None
    design = _paper_signal_design_payload(paper_signal)
    if not isinstance(design, dict):
        return None
    history = design.get("history")
    if not isinstance(history, dict):
        return None
    boundary = _clean(history.get("boundary")) or "origin_anchored"
    feeds = [
        _clean(item)
        for item in (history.get("feeds") if isinstance(history.get("feeds"), list) else [])
        if _clean(item)
    ]
    profile_history: dict[str, Any] = {
        "boundary": boundary if boundary in {"fixed_lookback", "origin_anchored"} else "origin_anchored",
    }
    if profile_history["boundary"] == "fixed_lookback":
        raw_lookback = history.get("lookbackBars", history.get("minBars"))
        try:
            lookback_bars = int(raw_lookback)
        except (TypeError, ValueError) as exc:
            raise PromotionHostedPaperContractRequired(
                "paperSignal.design.history.lookbackBars or minBars must be a "
                "positive integer for fixed_lookback paper execution"
            ) from exc
        if lookback_bars <= 0:
            raise PromotionHostedPaperContractRequired(
                "paperSignal.design.history.lookbackBars or minBars must be a "
                "positive integer for fixed_lookback paper execution"
            )
        profile_history["lookbackBars"] = lookback_bars
    else:
        origin = _clean(history.get("origin"))
        if origin:
            profile_history["origin"] = origin
    if feeds:
        profile_history["feeds"] = feeds
    reason = _clean(history.get("reason"))
    if reason:
        profile_history["reason"] = reason
    return {
        "schema": "abel.paper-execution-profile/v1",
        "history": profile_history,
    }
def _load_agent_contract_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{PROMOTION_CONTRACT_REPORT_FILENAME} must be an object")
    if payload.get("schema") != PROMOTION_AGENT_REPORT_SCHEMA:
        raise RuntimeError(
            f"{PROMOTION_CONTRACT_REPORT_FILENAME} has unsupported schema"
        )
    if payload.get("kind") != PROMOTION_HOSTED_CONTRACT_SCOPE:
        raise RuntimeError(
            f"{PROMOTION_CONTRACT_REPORT_FILENAME} kind must be "
            f"{PROMOTION_HOSTED_CONTRACT_SCOPE}"
        )
    return payload


def _report_replacements(report: dict[str, Any]) -> list[dict[str, str]]:
    raw_replacements = report.get("replacements")
    if not isinstance(raw_replacements, list):
        return []
    replacements: list[dict[str, str]] = []
    for item in raw_replacements:
        if not isinstance(item, dict):
            continue
        path = _clean(item.get("path"))
        replacement = _clean(item.get("replacement"))
        if path and replacement:
            payload = {"path": path, "replacement": replacement}
            reason = _clean(item.get("reason"))
            if reason:
                payload["reason"] = reason
            replacements.append(payload)
    return replacements
