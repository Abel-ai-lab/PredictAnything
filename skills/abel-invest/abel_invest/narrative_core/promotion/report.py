"""Hosted paper contract report helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import (
    PROMOTION_AGENT_REPORT_SCHEMA,
    PROMOTION_CONTRACT_REPORT_FILENAME,
    PROMOTION_HOSTED_CONTRACT_SCOPE,
)
from .models import PromotionHostedPaperContractRequired
from .utils import _clean


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


def _write_artifact_contract_report(
    promoted_dir: Path,
    report: dict[str, Any],
) -> Path:
    path = promoted_dir / "paper-contract-report.artifact.json"
    payload = json.loads(json.dumps(report))
    paths = payload.get("paths")
    if isinstance(paths, dict):
        paths["packagedFiles"] = [
            _sanitized_packaged_file_entry(item)
            for item in paths.get("packagedFiles") or []
            if isinstance(item, dict)
        ]
        paths["initialStateFiles"] = [
            _sanitized_packaged_file_entry(item)
            for item in paths.get("initialStateFiles") or []
            if isinstance(item, dict)
        ]
    if isinstance(payload.get("packagedFiles"), list):
        payload["packagedFiles"] = [
            _sanitized_packaged_file_entry(item)
            for item in payload.get("packagedFiles") or []
            if isinstance(item, dict)
        ]
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _sanitized_packaged_file_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"source", "sourcePath", "localSourcePath"}
    }
