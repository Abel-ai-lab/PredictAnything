"""Hosted paper contract validation helpers."""

from __future__ import annotations

import json
from typing import Any

from . import source_scan
from .constants import (
    PROMOTION_CONTINUATION_METHODS,
    PROMOTION_LIVE_READINESS_CONFLICT_PHRASES,
    PROMOTION_ML_STATE_EVIDENCE_TERMS,
    PROMOTION_RECONSTRUCTION_MODES,
)
from .facts import (
    _candidate_cutover_end,
    _observed_source_training_calls,
    _scan_has_external_file_dependency,
)
from .models import PromotionHostedPaperContractRequired
from .report import (
    _paper_signal_continuation_payload,
    _paper_signal_design_payload,
    _paper_signal_evidence_payload,
)
from .utils import _clean, _date_part, _json_safe

_paper_signal_design_facts = source_scan.paper_signal_design_facts
_source_overrides_get_paper_signal = source_scan.source_overrides_get_paper_signal

def _validate_agent_paper_signal_contract(
    report: dict[str, Any],
    source: str,
    *,
    require_paper_signal: bool,
    candidate: Any | None = None,
    full_replay_fallback_allowed: bool = False,
    source_dependency_scan: dict[str, Any] | None = None,
    original_source: str | None = None,
) -> None:
    paper_signal = report.get("paperSignal")
    if not isinstance(paper_signal, dict):
        if require_paper_signal:
            raise PromotionHostedPaperContractRequired(
                "hosted paper contract report must include paperSignal"
            )
        return
    implemented = paper_signal.get("implemented")
    incremental_ready = paper_signal.get("incrementalReady")
    if require_paper_signal and implemented is not True:
        raise PromotionHostedPaperContractRequired(
            "hosted paper contract must set paperSignal.implemented=true"
        )
    continuation = _paper_signal_continuation_payload(paper_signal)
    continuation_method = _clean(continuation.get("method")) if continuation else ""
    if require_paper_signal and incremental_ready is not True:
        if continuation_method == "not_hostable":
            raise PromotionHostedPaperContractRequired(
                "paper contract report declares paperSignal.continuation.method=not_hostable; "
                "promotion cannot export a continuing hosted paper artifact"
            )
        raise PromotionHostedPaperContractRequired(
            "hosted paper contract must set paperSignal.incrementalReady=true"
        )
    if incremental_ready is True:
        _validate_live_readiness_claim(report)
        _validate_paper_signal_continuation_contract(paper_signal)
        if (
            continuation_method == "full_replay_fallback"
            and not full_replay_fallback_allowed
        ):
            raise PromotionHostedPaperContractRequired(
                "paperSignal.continuation.method=full_replay_fallback is only "
                "available after attemptPolicy.fullReplayFallbackEligible=true"
            )
        _validate_paper_signal_design_contract(
            report,
            paper_signal,
            cutover_end=_candidate_cutover_end(candidate),
            continuation_method=continuation_method,
        )
        _validate_paper_signal_evidence_contract(
            paper_signal,
            continuation_method=continuation_method,
        )
        _validate_continuation_method_admissibility(
            report,
            source,
            paper_signal,
            continuation_method=continuation_method,
            full_replay_fallback_allowed=full_replay_fallback_allowed,
            source_dependency_scan=source_dependency_scan,
        )
        _validate_source_edit_contract(
            report,
            source_changed=original_source is not None and source != original_source,
            continuation_method=continuation_method,
            source_dependency_scan=source_dependency_scan,
        )
    if (
        implemented is True
        and continuation_method != "stateless_recompute"
        and not _source_overrides_get_paper_signal(source)
    ):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.implemented=true but promoted source does not define get_paper_signal"
        )

def _validate_source_edit_contract(
    report: dict[str, Any],
    *,
    source_changed: bool,
    continuation_method: str,
    source_dependency_scan: dict[str, Any] | None,
) -> None:
    source_edit = report.get("sourceEdit")
    if not source_changed:
        if isinstance(source_edit, dict) and source_edit.get("changed") is True:
            raise PromotionHostedPaperContractRequired(
                "sourceEdit.changed=true conflicts with unchanged promoted source"
            )
        return
    if not isinstance(source_edit, dict):
        raise PromotionHostedPaperContractRequired(
            "promoted source changed; paper-contract report must declare sourceEdit"
        )
    if source_edit.get("changed") is not True:
        raise PromotionHostedPaperContractRequired(
            "promoted source changed; sourceEdit.changed must be true"
        )
    reason = _clean(source_edit.get("reason"))
    allowed = _allowed_source_edit_reasons(
        continuation_method,
        source_dependency_scan=source_dependency_scan,
    )
    if reason not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise PromotionHostedPaperContractRequired(
            "promoted source changed for an unsupported sourceEdit.reason "
            f"{reason!r}; allowed reasons: {allowed_text}"
        )
    paths = source_edit.get("paths")
    if not isinstance(paths, list) or not paths:
        raise PromotionHostedPaperContractRequired(
            "sourceEdit.paths must list the promoted files changed"
        )

def _allowed_source_edit_reasons(
    continuation_method: str,
    *,
    source_dependency_scan: dict[str, Any] | None,
) -> set[str]:
    allowed = {"asset_path_normalization", "source_bug_fix"}
    if continuation_method in {"stateful_continuation", "full_replay_fallback"}:
        allowed.add(continuation_method)
    if _scan_has_external_file_dependency(source_dependency_scan):
        allowed.add("asset_path_normalization")
    return allowed

def _validate_paper_signal_continuation_contract(
    paper_signal: dict[str, Any],
) -> None:
    continuation = _paper_signal_continuation_payload(paper_signal)
    if not isinstance(continuation, dict):
        raise PromotionHostedPaperContractRequired(
            "continuing hosted paper reports must declare "
            "paperSignal.continuation"
        )
    method = _clean(continuation.get("method"))
    if method not in PROMOTION_CONTINUATION_METHODS:
        raise PromotionHostedPaperContractRequired(
            "paperSignal.continuation.method must be one of "
            "stateless_recompute, stateful_continuation, "
            "full_replay_fallback, or not_hostable"
        )
    if method == "not_hostable":
        raise PromotionHostedPaperContractRequired(
            "paperSignal.incrementalReady=true conflicts with "
            "paperSignal.continuation.method=not_hostable"
        )
    if not _clean(continuation.get("reason")):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.continuation.reason must explain why the chosen "
            "continuation shape preserves research decision semantics"
        )
    if not _clean(continuation.get("futureDailyFlow")):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.continuation.futureDailyFlow must explain how future "
            "hosted paper as_of calls continue after cutover"
        )

def _validate_paper_signal_design_contract(
    report: dict[str, Any],
    paper_signal: dict[str, Any],
    *,
    cutover_end: str = "",
    continuation_method: str = "",
) -> None:
    design = _paper_signal_design_payload(paper_signal)
    if not isinstance(design, dict):
        raise PromotionHostedPaperContractRequired(
            "continuing hosted paper reports must declare "
            "paperSignal.design with history/state/calendar/cutover/dailyStep"
        )
    history = design.get("history")
    if not isinstance(history, dict):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.history must describe the bounded "
            "history needed by hosted paper execution"
        )
    min_bars = history.get("minBars")
    if min_bars is not None:
        if not isinstance(min_bars, int) or isinstance(min_bars, bool) or min_bars < 0:
            raise PromotionHostedPaperContractRequired(
                "paperSignal.design.history.minBars must be a "
                "non-negative integer or null"
            )
    if not _clean(history.get("reason")):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.history.reason must explain the "
            "lookback/history requirement"
        )
    boundary = _clean(history.get("boundary"))
    if boundary and boundary not in {
        "fixed_lookback",
        "origin_anchored",
        "state_only",
        "full_replay",
    }:
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.history.boundary must be one of "
            "fixed_lookback, origin_anchored, state_only, or full_replay"
        )

    state = design.get("state")
    if not isinstance(state, dict) or not isinstance(
        state.get("usesPersistentState"), bool
    ):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.state.usesPersistentState must be true or false"
        )
    state_files = state.get("stateFiles")
    if state.get("usesPersistentState") is True and not (
        isinstance(state_files, list) and bool(state_files)
    ):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.state.stateFiles must list the "
            "strategy-owned state files used by hosted paper"
        )

    calendar = design.get("calendar")
    if not isinstance(calendar, dict) or not isinstance(
        calendar.get("usesAbsoluteDecisionOrdinal"), bool
    ):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.calendar.usesAbsoluteDecisionOrdinal "
            "must be true or false"
        )
    if calendar.get("usesAbsoluteDecisionOrdinal") is True and not _clean(
        calendar.get("origin")
    ):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.calendar.origin is required when "
            "absolute decision ordinals are used"
        )

    cutover = design.get("cutover")
    if not isinstance(cutover, dict) or not isinstance(
        cutover.get("requiresStartupState"), bool
    ):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.cutover.requiresStartupState must be true or false"
        )
    mode = _clean(cutover.get("mode") or cutover.get("approach"))
    if not mode:
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.cutover.mode must be one of "
            "none, minimal_cutover_state, or full_replay"
        )
    if mode not in PROMOTION_RECONSTRUCTION_MODES:
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.cutover.mode must be one of "
            "none, minimal_cutover_state, or full_replay"
        )
    required = cutover.get("requiresStartupState") is True
    if required and mode == "none":
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.cutover.requiresStartupState=true must use "
            "cutover.mode=minimal_cutover_state or full_replay"
        )
    if not required and not (
        mode == "none"
        or (continuation_method == "full_replay_fallback" and mode == "full_replay")
    ):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.cutover.requiresStartupState=false must use "
            "cutover.mode=none"
        )
    if mode == "full_replay" and continuation_method != "full_replay_fallback":
        raise PromotionHostedPaperContractRequired(
            "paperSignal.incrementalReady=true conflicts with "
            "cutover.mode=full_replay unless continuation.method is "
            "full_replay_fallback"
        )
    if required:
        state_end = _date_part(_clean(cutover.get("stateEnd")))
        if not _clean(cutover.get("dataHistoryStart")) or not state_end:
            raise PromotionHostedPaperContractRequired(
                "paperSignal.design.cutover must declare "
                "dataHistoryStart and stateEnd when startup state is required"
            )
        if cutover_end and state_end != cutover_end:
            raise PromotionHostedPaperContractRequired(
                "paperSignal.design.cutover.stateEnd must equal "
                f"the selected round cutover end {cutover_end}; startup state should "
                "be valid through the selected research result before future paper "
                "continues"
            )
    if continuation_method == "stateless_recompute" and required:
        raise PromotionHostedPaperContractRequired(
            "paperSignal.continuation.method=stateless_recompute must not "
            "require startup cutover state; use stateful_continuation when "
            "startup state is required"
        )
    if continuation_method == "stateful_continuation":
        if not required or mode != "minimal_cutover_state":
            raise PromotionHostedPaperContractRequired(
                "paperSignal.continuation.method=stateful_continuation requires "
                "paperSignal.design.cutover.requiresStartupState=true and "
                "cutover.mode=minimal_cutover_state"
            )
        if state.get("usesPersistentState") is not True:
            raise PromotionHostedPaperContractRequired(
                "paperSignal.continuation.method=stateful_continuation requires "
                "paperSignal.design.state.usesPersistentState=true"
            )
        if _clean(cutover.get("bootstrapHook")) != "build_paper_initial_state":
            raise PromotionHostedPaperContractRequired(
                "paperSignal.design.cutover.bootstrapHook must be "
                "build_paper_initial_state for stateful_continuation"
            )

    if continuation_method == "full_replay_fallback":
        if boundary != "full_replay" or mode != "full_replay":
            raise PromotionHostedPaperContractRequired(
                "paperSignal.continuation.method=full_replay_fallback requires "
                "history.boundary=full_replay and cutover.mode=full_replay"
            )

    daily_step = design.get("dailyStep")
    if not isinstance(daily_step, dict) or not _clean(daily_step.get("reason")):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.design.dailyStep.reason must explain how one future as_of "
            "runs and how state advances if any"
        )

def _validate_paper_signal_evidence_contract(
    paper_signal: dict[str, Any],
    *,
    continuation_method: str,
) -> None:
    evidence = _paper_signal_evidence_payload(paper_signal)
    if not isinstance(evidence, dict):
        raise PromotionHostedPaperContractRequired(
            "continuing hosted paper reports must declare paperSignal.evidence"
        )
    observations = evidence.get("observations")
    if not isinstance(observations, list) or not any(
        _clean(item) for item in observations
    ):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.evidence.observations must include at least one "
            "source or local evidence fact supporting the continuation design"
        )
    if not isinstance(evidence.get("semanticChecks", []), list):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.evidence.semanticChecks must be a list"
        )
    if not _clean(evidence.get("whySufficient")):
        raise PromotionHostedPaperContractRequired(
            "paperSignal.evidence.whySufficient must explain why the evidence "
            "supports the chosen continuation method"
        )
    if continuation_method == "stateful_continuation":
        checks = " ".join(
            _clean(item).lower() for item in evidence.get("semanticChecks") or []
        )
        if "state" not in checks and "cutover" not in checks:
            raise PromotionHostedPaperContractRequired(
                "paperSignal.continuation.method=stateful_continuation requires "
                "paperSignal.evidence.semanticChecks to support cutover state validity"
            )

def _ml_state_evidence_text(report: dict[str, Any], paper_signal: dict[str, Any]) -> str:
    snippets: list[Any] = []
    design = _paper_signal_design_payload(paper_signal)
    if isinstance(design, dict):
        for key in ("state", "cutover", "dailyStep"):
            value = design.get(key)
            if isinstance(value, dict):
                snippets.append(value.get("reason"))
    paths = report.get("paths")
    if isinstance(paths, dict):
        for item in paths.get("initialStateFiles") or []:
            if isinstance(item, dict):
                snippets.append(item.get("purpose"))
    snippets.append(paper_signal.get("liveReadiness"))
    return json.dumps(_json_safe(snippets), sort_keys=True).lower()

def _has_ml_state_continuation_evidence(
    report: dict[str, Any],
    paper_signal: dict[str, Any],
) -> bool:
    text = _ml_state_evidence_text(report, paper_signal)
    return any(term in text for term in PROMOTION_ML_STATE_EVIDENCE_TERMS)

def _validate_continuation_method_admissibility(
    report: dict[str, Any],
    source: str,
    paper_signal: dict[str, Any],
    *,
    continuation_method: str,
    full_replay_fallback_allowed: bool,
    source_dependency_scan: dict[str, Any] | None = None,
) -> None:
    source_facts = _paper_signal_design_facts(source)
    observed_fit_calls = _observed_source_training_calls(
        source_dependency_scan
    ) or source_facts.get("sourceTrainingCalls") or source_facts.get("trainingCalls") or []
    if continuation_method == "stateless_recompute" and observed_fit_calls:
        joined = ", ".join(_clean(item) for item in observed_fit_calls if _clean(item))
        raise PromotionHostedPaperContractRequired(
            "paperSignal.continuation.method=stateless_recompute conflicts with "
            f"observed ML training/refit/update calls in the selected source: {joined}. "
            "Use stateful_continuation and reread references/hosted-paper-contract.md."
        )
    if (
        observed_fit_calls
        and continuation_method != "stateful_continuation"
        and not (
            continuation_method == "full_replay_fallback"
            and full_replay_fallback_allowed
        )
    ):
        joined = ", ".join(_clean(item) for item in observed_fit_calls if _clean(item))
        raise PromotionHostedPaperContractRequired(
            "observed ML training/refit/update calls require "
            "paperSignal.continuation.method=stateful_continuation before "
            f"fallback eligibility opens: {joined}. "
            "After attemptPolicy.fullReplayFallbackEligible=true, "
            "full_replay_fallback is allowed but must pass tail parity and the "
            "hosted paper performance limit."
        )
    if continuation_method == "stateful_continuation":
        if observed_fit_calls and not _has_ml_state_continuation_evidence(
            report, paper_signal
        ):
            joined = ", ".join(
                _clean(item) for item in observed_fit_calls if _clean(item)
            )
            raise PromotionHostedPaperContractRequired(
                "observed ML training/refit/update calls require the "
                "stateful_continuation design to evidence persisted fitted-object "
                "or equivalent training state, not only cursor/cache state: "
                f"{joined}. Reread the stateful continuation section of "
                "references/hosted-paper-contract.md."
            )

def _validate_live_readiness_claim(report: dict[str, Any]) -> None:
    snippets = _live_readiness_text_snippets(report)
    conflicts: list[str] = []
    for snippet in snippets:
        lowered = snippet.lower()
        if _live_readiness_conflict_phrase(lowered) is not None:
            conflicts.append(snippet)
    if not conflicts:
        return
    sample = "; ".join(conflicts[:3])
    raise PromotionHostedPaperContractRequired(
        "paperSignal.incrementalReady=true conflicts with report text that "
        f"describes finite replay, research evidence, or not-continuing readiness: {sample}"
    )

def _live_readiness_conflict_phrase(lowered_snippet: str) -> str | None:
    for phrase in PROMOTION_LIVE_READINESS_CONFLICT_PHRASES:
        start = lowered_snippet.find(phrase)
        while start >= 0:
            if not _conflict_occurrence_is_negated(lowered_snippet, start, phrase):
                return phrase
            start = lowered_snippet.find(phrase, start + len(phrase))
    return None

def _conflict_occurrence_is_negated(text: str, start: int, phrase: str) -> bool:
    if phrase.startswith(("no ", "not ", "cannot ", "can't ")):
        return False
    sentence_start = max(
        text.rfind(".", 0, start),
        text.rfind(";", 0, start),
        text.rfind("\n", 0, start),
    )
    prefix = text[sentence_start + 1 : start]
    return any(
        marker in prefix
        for marker in (
            "not a ",
            "not an ",
            "not ",
            "never ",
            "without ",
        )
    )

def _live_readiness_text_snippets(report: dict[str, Any]) -> list[str]:
    snippets: list[str] = []
    paper_signal = report.get("paperSignal")
    if isinstance(paper_signal, dict):
        for key in ("liveReadiness", "notes"):
            value = _clean(paper_signal.get(key))
            if value:
                snippets.append(value)
    limitations = report.get("limitations")
    if isinstance(limitations, list):
        for item in limitations:
            snippets.extend(_string_leaf_values(item))
    paths = report.get("paths")
    if isinstance(paths, dict):
        for key in ("packagedFiles", "initialStateFiles"):
            entries = paths.get(key)
            if not isinstance(entries, list):
                continue
            for item in entries:
                if isinstance(item, dict):
                    for field in ("purpose", "notes", "reason"):
                        value = _clean(item.get(field))
                        if value:
                            snippets.append(value)
    return snippets

def _string_leaf_values(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = _clean(value)
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        snippets: list[str] = []
        for item in value.values():
            snippets.extend(_string_leaf_values(item))
        return snippets
    if isinstance(value, list):
        snippets = []
        for item in value:
            snippets.extend(_string_leaf_values(item))
        return snippets
    return []
