"""Hosted paper contract request and work-order generation."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from .constants import (
    PROMOTION_AGENT_REPORT_SCHEMA,
    PROMOTION_AGENT_REQUEST_SCHEMA,
    PROMOTION_CONTRACT_FACTS_FILENAME,
    PROMOTION_CONTRACT_REPORT_FILENAME,
    PROMOTION_CONTRACT_REQUEST_FILENAME,
    PROMOTION_CONTRACT_REQUESTS_BEFORE_FALLBACK,
    PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS,
    PROMOTION_HOSTED_CONTRACT_SCOPE,
    PROMOTION_LIVE_CONTRACT_FAILURES_BEFORE_FALLBACK,
)
from .facts import (
    _observed_source_training_calls,
    _scan_cutover_end,
    _scan_has_external_file_dependency,
)
from . import source_scan
from .utils import _clean, _date_part, _finite_float, _json_safe

_source_scan_observations = source_scan.source_scan_observations

def _hosted_paper_contract_guide_reference() -> dict[str, Any]:
    guide_path = Path(__file__).resolve().parents[2] / "references" / "hosted-paper-contract.md"
    return {
        "path": str(guide_path),
        "relativePath": "references/hosted-paper-contract.md",
        "instruction": (
            "Use this Markdown guide when stateful continuation, source edits, "
            "or gate diagnosis need deeper guidance. The request is the normal "
            "work order."
        ),
    }

def _hosted_paper_contract_scaffold_references(
    requirements: dict[str, Any],
) -> list[dict[str, Any]]:
    if not requirements.get("statefulContinuationRequired"):
        return []
    return [
        {
            "name": "stateful_continuation_paper_state_store",
            "when": "requirements.statefulContinuationRequired=true",
            "purpose": (
                "Minimal interface shape for strategy-owned hosted paper state. "
                "Adapt the helper methods to the selected strategy semantics."
            ),
            "statePath": "strategy/paper_state.pkl",
            "interfaces": [
                "PaperStateStore.from_context(self.context, 'strategy/paper_state.pkl')",
                "build_paper_initial_state(self, *, cutover_as_of=None)",
                "get_paper_signal(self, *, as_of=None)",
                "store.is_current(state, as_of)",
                "store.mark_current(state, as_of)",
                "store.signal(next_position=..., payload=state, as_of=as_of)",
            ],
            "code": (
                "from abel_edge.paper_state import PaperStateStore\n\n"
                "STATE_SCHEMA = 'my-strategy.paper-state/v1'\n\n"
                "def _paper_store(self):\n"
                "    return PaperStateStore.from_context(self.context, 'strategy/paper_state.pkl')\n\n"
                "def build_paper_initial_state(self, *, cutover_as_of=None):\n"
                "    store = self._paper_store()\n"
                "    state = self._build_state_through(cutover_as_of)\n"
                "    state['schema'] = STATE_SCHEMA\n"
                "    state = store.mark_current(state, cutover_as_of)\n"
                "    store.save(state)\n"
                "    return store.summary(state, as_of=cutover_as_of)\n\n"
                "def get_paper_signal(self, *, as_of=None):\n"
                "    store = self._paper_store()\n"
                "    state = store.load(default={})\n"
                "    if store.is_current(state, as_of):\n"
                "        return store.signal(next_position=state['next_position'], payload=state, as_of=as_of)\n"
                "    state = self._advance_paper_state(state, as_of=as_of)\n"
                "    state = store.mark_current(state, as_of)\n"
                "    store.save(state)\n"
                "    return store.signal(next_position=state['next_position'], payload=state, as_of=as_of)\n"
            ),
            "gateHandoff": (
                "Promotion calls build_paper_initial_state for the validation cutover, "
                "then replays the tail with Edge paper_run_one. If parity passes, the "
                "state produced by that replay is packaged as runtime/initial-state/**. "
                "Do not hand-build final startup state or encode expected positions."
            ),
        }
    ]

def _hosted_paper_contract_requirements(
    dependency_scan: dict[str, Any],
    *,
    attempt_policy: dict[str, Any],
) -> dict[str, Any]:
    training_calls = _observed_source_training_calls(dependency_scan)
    fallback_allowed = bool(attempt_policy.get("fullReplayFallbackEligible"))
    training_observed = bool(training_calls)
    stateful_required = training_observed and not fallback_allowed
    source_edit_policy = _source_edit_policy(
        dependency_scan,
        ml_training_observed=training_observed,
        stateful_required=stateful_required,
        fallback_allowed=fallback_allowed,
    )
    fallback_payload = _fallback_payload(attempt_policy, expanded=fallback_allowed)
    if training_observed and fallback_allowed:
        continuation_method = "stateful_continuation_or_full_replay_fallback"
        reason = (
            "Static source scan observed training/refit/update calls in the "
            "selected research source. ML or fitted-object strategies should "
            "use stateful_continuation first. Because fallback eligibility is "
            "now open, full_replay_fallback is also allowed if it passes tail "
            "parity and the hosted paper performance limit."
        )
    elif training_observed:
        continuation_method = "stateful_continuation"
        reason = (
            "Static source scan observed training/refit/update calls in the "
            "selected research source. ML or fitted-object strategies must "
            "continue strategy-owned state instead of cold refitting on every "
            "paper call until fallback eligibility opens."
        )
    else:
        continuation_method = "agent_choice"
        reason = (
            "No training call was observed by static scan. This is not proof "
            "of statelessness; inspect the source and choose the continuation "
            "method that preserves the strategy semantics."
        )
    return {
        "expectedAction": "implement_stateful_continuation"
        if stateful_required
        else "write_profile_report_only",
        "continuationMethod": continuation_method,
        "statefulContinuationRequired": stateful_required,
        "sourceEditPolicy": source_edit_policy,
        "reason": reason,
        "observedTrainingCalls": training_calls,
        "fallback": fallback_payload,
        "hardBoundaries": [
            "Do not edit the original research branch source.",
            "Edit sourcePath only when sourceEditPolicy.required is true or when a listed allowed reason is genuinely needed.",
            "Do not package selected-round trade-log.csv, gate answers, or promotion outputs as live strategy assets or startup state.",
            "Do not choose full_replay_fallback unless fallback.fullReplayFallbackEligible is true.",
        ],
    }


def _fallback_payload(
    attempt_policy: dict[str, Any],
    *,
    expanded: bool,
) -> dict[str, Any]:
    eligible = bool(attempt_policy.get("fullReplayFallbackEligible"))
    payload: dict[str, Any] = {
        "fullReplayFallbackEligible": eligible,
        "liveContractFailures": _nonnegative_int(
            attempt_policy.get("liveContractFailures")
        ),
        "contractRequestRefreshes": _nonnegative_int(
            attempt_policy.get("contractRequestRefreshes")
        ),
    }
    if not expanded:
        payload["status"] = "unavailable"
        return payload
    payload.update(
        {
            "status": "available",
            "fallbackAfterFailures": _nonnegative_int(
                attempt_policy.get("fallbackAfterFailures")
            ),
            "fallbackAfterRequestRefreshes": _nonnegative_int(
                attempt_policy.get("fallbackAfterRequestRefreshes")
            ),
            "fallbackEligibilityReason": _clean(
                attempt_policy.get("fallbackEligibilityReason")
            ),
            "fullReplayFallbackMaxSeconds": _finite_float(
                attempt_policy.get("fullReplayFallbackMaxSeconds")
            )
            or PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS,
        }
    )
    return payload

def _source_edit_policy(
    dependency_scan: dict[str, Any],
    *,
    ml_training_observed: bool,
    stateful_required: bool,
    fallback_allowed: bool,
) -> dict[str, Any]:
    allowed_reasons = ["asset_path_normalization", "source_bug_fix"]
    if ml_training_observed:
        allowed_reasons.insert(0, "stateful_continuation")
        if fallback_allowed:
            allowed_reasons.insert(1, "full_replay_fallback")
    expected = ml_training_observed or _scan_has_external_file_dependency(dependency_scan)
    required = stateful_required
    reason = "stateful_continuation" if stateful_required else ""
    if not reason and ml_training_observed and fallback_allowed:
        reason = "stateful_continuation_or_full_replay_fallback"
    if not reason and _scan_has_external_file_dependency(dependency_scan):
        reason = "asset_path_normalization"
    return {
        "expected": expected,
        "required": required,
        "reason": reason,
        "allowedReasons": allowed_reasons,
        "defaultForStateless": (
            "Preserve sourcePath and write only paper-contract-report.json "
            "unless an allowed source edit is genuinely required."
        ),
    }

def _contract_attempt_policy(
    promoted_dir: Path,
    *,
    validation_failure: dict[str, Any] | None,
) -> dict[str, Any]:
    previous = _read_previous_contract_attempt_policy(
        promoted_dir / PROMOTION_CONTRACT_REQUEST_FILENAME
    )
    failures = _nonnegative_int(previous.get("liveContractFailures"))
    if validation_failure is not None:
        failures += 1
    request_refreshes = _nonnegative_int(previous.get("contractRequestRefreshes")) + 1
    failure_eligible = failures >= PROMOTION_LIVE_CONTRACT_FAILURES_BEFORE_FALLBACK
    refresh_eligible = request_refreshes >= PROMOTION_CONTRACT_REQUESTS_BEFORE_FALLBACK
    eligible = failure_eligible or refresh_eligible
    eligibility_reason = ""
    if failure_eligible:
        eligibility_reason = "live_contract_failures"
    elif refresh_eligible:
        eligibility_reason = "contract_request_budget"
    return {
        "liveContractFailures": failures,
        "contractRequestRefreshes": request_refreshes,
        "fullReplayFallbackEligible": eligible,
        "fallbackAfterFailures": PROMOTION_LIVE_CONTRACT_FAILURES_BEFORE_FALLBACK,
        "fallbackAfterRequestRefreshes": PROMOTION_CONTRACT_REQUESTS_BEFORE_FALLBACK,
        "fallbackEligibilityReason": eligibility_reason,
        "fullReplayFallbackMaxSeconds": PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS,
        "rule": (
            "Use stateless_recompute or stateful_continuation first. "
            "full_replay_fallback is only available after "
            "enough complete live contract failures or contract request refreshes."
        ),
    }

def _full_replay_fallback_allowed(promoted_dir: Path) -> bool:
    policy = _read_previous_contract_attempt_policy(
        promoted_dir / PROMOTION_CONTRACT_REQUEST_FILENAME
    )
    return bool(policy.get("fullReplayFallbackEligible"))

def _read_previous_contract_attempt_policy(request_path: Path) -> dict[str, Any]:
    if not request_path.is_file():
        return {}
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    policy = payload.get("attemptPolicy")
    if isinstance(policy, dict):
        return policy
    validation = payload.get("validation")
    if isinstance(validation, dict) and isinstance(validation.get("attemptPolicy"), dict):
        return validation["attemptPolicy"]
    return {}

def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)

def _write_hosted_paper_contract_request(
    promoted_dir: Path,
    *,
    branch: Path,
    source_path: Path,
    dependency_scan: dict[str, Any],
    signals: list[dict[str, str]],
    validation_failure: dict[str, Any] | None = None,
) -> Path:
    request_path = promoted_dir / PROMOTION_CONTRACT_REQUEST_FILENAME
    attempt_policy = _contract_attempt_policy(
        promoted_dir,
        validation_failure=validation_failure,
    )
    validation_payload: dict[str, Any] = {
        "smoke": (
            "Rerun the same promote/export command after writing "
            "paper-contract-report.json. Promotion will run an Edge paper_run_one "
            "tail smoke automatically before export."
        )
    }
    if validation_failure:
        validation_payload["lastGateFailure"] = validation_failure
    validation_payload["attemptPolicy"] = attempt_policy
    cutover_end = _scan_cutover_end(dependency_scan)
    facts = dict(dependency_scan)
    if "sourceScan" not in facts:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source_text)
        except SyntaxError:
            tree = None
        facts["sourceScan"] = _source_scan_observations(
            source_text,
            tree,
            file_accesses=facts.get("fileAccesses", []),
        )
    requirements = _hosted_paper_contract_requirements(
        facts,
        attempt_policy=attempt_policy,
    )
    scaffolds = _hosted_paper_contract_scaffold_references(requirements)
    facts_sidecar = (
        _write_hosted_paper_contract_facts_sidecar(promoted_dir, facts=facts)
        if _should_write_facts_sidecar(
            facts,
            validation_failure=validation_failure,
        )
        else None
    )
    compact_facts = _hosted_paper_contract_work_order_facts(facts)
    request_payload = {
        "schema": PROMOTION_AGENT_REQUEST_SCHEMA,
        "kind": PROMOTION_HOSTED_CONTRACT_SCOPE,
        "scope": PROMOTION_HOSTED_CONTRACT_SCOPE,
        "sourcePath": str(source_path),
        "branchPath": str(branch),
        "selection": _request_selection_payload(branch, promoted_dir),
        "output": {
            "artifactDir": str(promoted_dir.parent),
            "promotedDir": str(promoted_dir),
            "reportPath": str(promoted_dir / PROMOTION_CONTRACT_REPORT_FILENAME),
        },
        "rerun": {
            "instruction": "Write paper-contract-report.json, then rerun the same export, visualize, or promote command.",
        },
        "task": _hosted_paper_contract_work_order_task(requirements),
        "requirements": requirements,
        "signals": signals,
        "facts": compact_facts,
        "reportTemplate": _hosted_paper_contract_report_template(
            requirements,
            cutover_end=cutover_end,
            data_history_start=_scan_data_history_start(facts),
        ),
        "validation": validation_payload,
        "selectedRoundCutoverEnd": cutover_end,
    }
    if _should_include_contract_guide(
        requirements,
        validation_failure=validation_failure,
    ):
        guide = _hosted_paper_contract_guide_reference()
        guide["instruction"] = (
            "Use this guide only when stateful continuation, source edits, or a "
            "gate failure require deeper details. Clear stateless cases should be "
            "solvable from this request and sourcePath."
        )
        request_payload["contractGuide"] = guide
    if facts_sidecar is not None:
        request_payload["factSidecars"] = {
            "fullFactsPath": str(facts_sidecar),
            "fullFactsRelativePath": PROMOTION_CONTRACT_FACTS_FILENAME,
            "usage": (
                "Optional debugging evidence. Start from this request; inspect "
                "the sidecar only when sourcePath plus compact facts are insufficient."
            ),
        }
    if scaffolds:
        request_payload["scaffolds"] = scaffolds
    request_path.write_text(
        json.dumps(request_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return request_path


def _should_include_contract_guide(
    requirements: dict[str, Any],
    *,
    validation_failure: dict[str, Any] | None,
) -> bool:
    if validation_failure is not None or requirements.get("statefulContinuationRequired"):
        return True
    source_edit_policy = requirements.get("sourceEditPolicy")
    return isinstance(source_edit_policy, dict) and bool(source_edit_policy.get("expected"))


def _should_write_facts_sidecar(
    facts: dict[str, Any],
    *,
    validation_failure: dict[str, Any] | None,
) -> bool:
    if validation_failure is not None or _scan_has_external_file_dependency(facts):
        return True
    if facts.get("stateDependencies"):
        return True
    imports = facts.get("imports") if isinstance(facts.get("imports"), list) else []
    return any(
        isinstance(item, dict)
        and item.get("classification") not in {"stdlib", "allowed_runtime"}
        for item in imports
    )


def _request_selection_payload(branch: Path, promoted_dir: Path) -> dict[str, str]:
    round_dir = promoted_dir.parent
    return {
        "branchId": branch.name,
        "roundId": round_dir.name,
        "mode": "selected_strategy",
    }


def _scan_data_history_start(facts: dict[str, Any]) -> str:
    backtest_window = facts.get("backtestWindow")
    if not isinstance(backtest_window, dict):
        return ""
    effective = backtest_window.get("effectiveWindow")
    if isinstance(effective, dict):
        value = _date_part(_clean(effective.get("start")))
        if value:
            return value
    requested = backtest_window.get("requestedWindow")
    if isinstance(requested, dict):
        return _date_part(_clean(requested.get("start")))
    return ""

def _write_hosted_paper_contract_facts_sidecar(
    promoted_dir: Path,
    *,
    facts: dict[str, Any],
) -> Path:
    path = promoted_dir / PROMOTION_CONTRACT_FACTS_FILENAME
    path.write_text(
        json.dumps(_json_safe(facts), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path

def _hosted_paper_contract_work_order_task(requirements: dict[str, Any]) -> str:
    if requirements.get("statefulContinuationRequired"):
        return (
            "Implement the hosted live-paper contract for this selected strategy. "
            "Because fitted/training state was observed, use stateful_continuation "
            "first, update sourcePath only as needed, then rerun the same export command."
        )
    return (
        "Declare the hosted live-paper contract for this selected strategy. "
        "Preserve sourcePath by default, read the source, choose the paper history "
        "boundary from source semantics, and write only paper-contract-report.json "
        "unless sourceEditPolicy shows a genuine allowed edit."
    )

def _hosted_paper_contract_work_order_facts(
    facts: dict[str, Any],
) -> dict[str, Any]:
    paper_signal = (
        facts.get("paperSignal") if isinstance(facts.get("paperSignal"), dict) else {}
    )
    source_scan = (
        facts.get("sourceScan") if isinstance(facts.get("sourceScan"), dict) else {}
    )
    validation_oracle = (
        facts.get("validationOracle")
        if isinstance(facts.get("validationOracle"), dict)
        else {}
    )
    temporal = (
        facts.get("temporalDependencies")
        if isinstance(facts.get("temporalDependencies"), dict)
        else {}
    )
    return {
        "schema": "abel-invest.hosted-paper-work-order-facts/v1",
        "sourcePath": facts.get("sourcePath"),
        "strategyProfile": {
            "getPaperSignalImplemented": paper_signal.get("implemented") is True,
            "fullRuntimeCompute": paper_signal.get("fullRuntimeCompute") is True,
            "fullRuntimeComputePath": paper_signal.get("fullRuntimeComputePath") or [],
            "observedTrainingCalls": _observed_source_training_calls(facts),
            "externalFileDependencyObserved": _scan_has_external_file_dependency(facts),
            "absolutePathLiteralCount": len(facts.get("absolutePathLiterals") or []),
            "fileAccessCount": len(facts.get("fileAccesses") or []),
            "branchFileCount": len(facts.get("branchFiles") or []),
        },
        "sourceScan": _compact_source_scan(source_scan),
        "historyProfile": {
            "allowedBoundaries": ["fixed_lookback", "origin_anchored"],
            "backtestWindow": _json_safe(facts.get("backtestWindow") or {}),
            "validationOracle": _compact_validation_oracle(validation_oracle),
            "temporalHints": _compact_temporal_dependency_hints(temporal),
            "decisionRule": (
                "Harness boundary candidates are observations, not answers. Read "
                "sourcePath before choosing history.boundary. Use fixed_lookback "
                "only when source semantics are finite-window; use origin_anchored "
                "for expanding/cumulative/ranked history, row-index dependencies "
                "that affect the emitted as_of decision, fitted calendars, or "
                "unresolved history needs."
            ),
        },
        "assetPolicy": validation_oracle.get("assetPolicy")
        or (
            "Selected-round trade-log.csv and promotion outputs are validation "
            "evidence only; do not package them as live strategy assets or startup state."
        ),
    }

def _compact_source_scan(source_scan: dict[str, Any]) -> dict[str, Any]:
    findings = (
        source_scan.get("positiveFindings")
        if isinstance(source_scan.get("positiveFindings"), dict)
        else {}
    )
    compact: dict[str, Any] = {}
    for key in (
        "observedFitCalls",
        "stateLikeNames",
        "paperSignalMethods",
        "runtimePathHelpers",
    ):
        value = findings.get(key)
        if isinstance(value, list) and value:
            compact[key] = value[:12]
    return compact

def _compact_validation_oracle(oracle: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "rowCount",
        "comparableRowCount",
        "firstComparableDate",
        "lastComparableDate",
    )
    compact = {key: oracle.get(key) for key in keys if key in oracle}
    timeline = oracle.get("canonicalDecisionTimeline")
    if isinstance(timeline, dict):
        compact["canonicalDecisionTimeline"] = {
            key: timeline.get(key)
            for key in ("source", "indexOrigin", "rowCount", "first", "last", "usage")
            if key in timeline
        }
    return _json_safe(compact)

def _compact_temporal_dependency_hints(temporal: dict[str, Any]) -> dict[str, Any]:
    if not temporal:
        return {}
    compact: dict[str, Any] = {}
    for key in (
        "maxRollingWindow",
        "rollingWindows",
        "usesExpanding",
        "usesCumulative",
        "usesRank",
        "usesAbsoluteIndex",
        "retrainCadence",
        "historyBoundaryCandidates",
    ):
        value = temporal.get(key)
        if value not in (None, [], {}, ""):
            compact[key] = value[:12] if isinstance(value, list) else value
    return _json_safe(compact)

def _hosted_paper_contract_report_template(
    requirements: dict[str, Any],
    *,
    cutover_end: str,
    data_history_start: str = "",
) -> dict[str, Any]:
    stateful_required = requirements.get("statefulContinuationRequired") is True
    continuation_method = (
        "stateful_continuation" if stateful_required else "stateless_recompute"
    )
    source_edit_policy = (
        requirements.get("sourceEditPolicy")
        if isinstance(requirements.get("sourceEditPolicy"), dict)
        else {}
    )
    paper_signal: dict[str, Any] = {
        "implemented": True,
        "incrementalReady": True,
        "continuation": {
            "method": continuation_method,
            "reason": "Fill in why this execution shape preserves semantics.",
            "futureDailyFlow": "Fill in how one future as_of call runs.",
        },
        "design": {
            "history": {
                "boundary": "",
                "lookbackBars": None,
                "origin": "",
                "reason": (
                    "Choose after reading sourcePath; do not copy harness "
                    "historyBoundaryCandidates blindly."
                ),
            },
            "state": {
                "usesPersistentState": stateful_required,
                "stateFiles": [] if not stateful_required else ["strategy/..."],
                "reason": "No strategy-owned state is needed."
                if not stateful_required
                else "",
            },
        },
        "evidence": {
            "observations": ["Fill in the source fact you verified."],
            "whySufficient": "Fill in why these observations support the method.",
        },
    }
    if stateful_required:
        paper_signal["design"].update(
            {
                "calendar": {
                    "usesAbsoluteDecisionOrdinal": False,
                    "origin": "",
                    "reason": "",
                },
                "cutover": {
                    "requiresStartupState": True,
                    "mode": "minimal_cutover_state",
                    "bootstrapHook": "build_paper_initial_state",
                    "dataHistoryStart": data_history_start,
                    "stateEnd": cutover_end,
                    "reason": "",
                },
                "dailyStep": {
                    "reason": "Fill in what is loaded, advanced, or recomputed each paper day."
                },
            }
        )
    return {
        "schema": PROMOTION_AGENT_REPORT_SCHEMA,
        "kind": PROMOTION_HOSTED_CONTRACT_SCOPE,
        "scope": PROMOTION_HOSTED_CONTRACT_SCOPE,
        "sourceEdit": {
            "changed": bool(source_edit_policy.get("required")),
            "reason": source_edit_policy.get("reason") or "",
            "paths": ["engine.py"] if source_edit_policy.get("required") else [],
        },
        "paperSignal": paper_signal,
    }
