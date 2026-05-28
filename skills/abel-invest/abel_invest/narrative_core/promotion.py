"""Strategy promotion helpers for paper-ready runtime state boundaries."""

from __future__ import annotations


import ast
import csv
import json
from pathlib import Path
from typing import Any, Callable

from . import promotion_source, promotion_tail
from .promotion_constants import *  # noqa: F403 - facade re-exports promotion constants.
from .promotion_contract import (
    _load_agent_contract_report,
    _paper_signal_continuation_payload,
    _paper_signal_design_payload,
    _paper_signal_evidence_payload,
    _report_continuation_method,
    _report_has_hosted_paper_contract,
    _report_paper_execution_profile,
    _report_replacements,
)
from .promotion_gate import (
    _build_contract_promotion_gate_report,
    _promotion_gate_failure_request_payload,
)
from .promotion_models import (
    PromotionHostedPaperContractRequired,
    PromotionHostedPaperRewriteRequired,
    PromotionPackagedFile,
    PromotionResult,
)
from .promotion_legacy import cleanup_legacy_promotion_outputs as _cleanup_legacy_promotion_outputs
from .promotion_packaging import (
    _report_packaged_files,
    _validate_packaged_artifact_path,
    _validate_packaged_research_evidence_sources,
)
from .promotion_paper_smoke import (
    _fast_paper_validation,
    _generated_replay_initial_state_files,
    _paper_smoke_context,
    _run_edge_paper_run_one_smoke,
    _run_edge_paper_run_one_smoke_unbounded,
)
from .promotion_paper_trace import (
    PROMOTION_TAIL_TRACE_FILENAME,
    paper_dry_run_gate_summary as _paper_dry_run_gate_summary,
    write_paper_tail_trace as _write_paper_tail_trace,
)
from .promotion_utils import (
    _clean,
    _date_part,
    _finite_float,
    _json_safe,
)


_call_name = promotion_source.call_name
_paper_signal_design_facts = promotion_source.paper_signal_design_facts
_paper_signal_full_runtime_compute_path = (
    promotion_source.paper_signal_full_runtime_compute_path
)
_paper_signal_uses_full_runtime_compute = (
    promotion_source.paper_signal_uses_full_runtime_compute
)
_source_file_access_facts = promotion_source.source_file_access_facts
_source_import_facts = promotion_source.source_import_facts
_source_overrides_get_paper_signal = promotion_source.source_overrides_get_paper_signal
_source_scan_observations = promotion_source.source_scan_observations
_source_temporal_dependency_facts = promotion_source.source_temporal_dependency_facts
_training_call_facts = promotion_source.training_call_facts
PROMOTION_PAPER_TAIL_MAX_COUNT = promotion_tail.PROMOTION_PAPER_TAIL_MAX_COUNT
PROMOTION_PAPER_TAIL_TARGET_COUNT = promotion_tail.PROMOTION_PAPER_TAIL_TARGET_COUNT
PROMOTION_PAPER_TAIL_TOLERANCE = promotion_tail.PROMOTION_PAPER_TAIL_TOLERANCE
_paper_tail_oracle_rows = promotion_tail.paper_tail_oracle_rows
_paper_tail_position_change_count = promotion_tail.paper_tail_position_change_count
_paper_tail_prior_row = promotion_tail.paper_tail_prior_row
_paper_tail_selection_reason = promotion_tail.paper_tail_selection_reason
_redacted_timeline_row = promotion_tail.redacted_timeline_row
_redacted_trade_log_oracle_sample = promotion_tail.redacted_trade_log_oracle_sample
_select_paper_tail_oracle_sample = promotion_tail.select_paper_tail_oracle_sample
_tail_consistency_payload = promotion_tail.tail_consistency_payload



def prepare_promotion(
    candidate: Any,
    *,
    destination: Path,
    strategy_entrypoint: str,
    is_denylisted_source: Callable[[Path], bool],
    sha256_file: Callable[[Path], str],
    runtime_env: dict[str, str] | None = None,
) -> PromotionResult:
    promoted_dir = destination / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_legacy_promotion_outputs(destination, promoted_dir)
    promoted_source = promoted_dir / "engine.py"
    existing_contract_report = promoted_dir / PROMOTION_CONTRACT_REPORT_FILENAME
    original_text = candidate.strategy_source_path.read_text(encoding="utf-8")
    agent_contract_ready = promoted_source.is_file() and existing_contract_report.is_file()
    dependency_scan = _collect_hosted_paper_dependency_scan(
        candidate.branch,
        strategy_source_path=candidate.strategy_source_path,
        is_denylisted_source=is_denylisted_source,
        candidate=candidate,
        destination=destination,
    )

    hosted_contract_signals = _hosted_paper_contract_signals(dependency_scan)
    if not agent_contract_ready:
        contract_signals = _initial_hosted_paper_contract_signals(
            hosted_contract_signals
        )
        promoted_source.write_text(original_text, encoding="utf-8")
        request_path = _write_hosted_paper_contract_request(
            promoted_dir,
            branch=candidate.branch,
            source_path=promoted_source,
            dependency_scan=dependency_scan,
            signals=contract_signals,
        )
        raise PromotionHostedPaperContractRequired(
            "hosted paper contract required before first artifact export; "
            f"request written to {request_path}"
        )

    strategy_source_path = candidate.strategy_source_path
    patch_path = None
    contract_report_path = None
    mode = PROMOTION_MODE_ZERO_CHANGE
    contract_replacements: list[dict[str, str]] = []
    contract_summary = ""
    packaged_files: tuple[PromotionPackagedFile, ...] = ()
    contract_report: dict[str, Any] | None = None
    paper_execution_profile: dict[str, Any] | None = None
    promoted_text = original_text

    if agent_contract_ready:
        promoted_text = promoted_source.read_text(encoding="utf-8")
        contract_report = _load_agent_contract_report(existing_contract_report)
        contract_replacements = _report_replacements(contract_report)
        if not _report_has_hosted_paper_contract(contract_report):
            raise PromotionHostedPaperContractRequired(
                "hosted paper contract report must use hosted_paper_contract scope"
            )
        contract_summary = _clean(contract_report.get("summary")) or (
            "Agent declared the hosted paper contract."
        )
        packaged_files = tuple(
            _report_packaged_files(
                contract_report,
                branch=candidate.branch,
                is_denylisted_source=is_denylisted_source,
            )
        )
        _validate_packaged_research_evidence_sources(
            packaged_files,
            branch=candidate.branch,
            destination=destination,
            report=contract_report,
        )
        artifact_contract_report_path = _write_artifact_contract_report(
            promoted_dir,
            contract_report,
        )
        _validate_agent_paper_signal_contract(
            contract_report,
            promoted_text,
            require_paper_signal=True,
            candidate=candidate,
            full_replay_fallback_allowed=_full_replay_fallback_allowed(promoted_dir),
            source_dependency_scan=dependency_scan,
            original_source=original_text,
        )
        paper_execution_profile = _report_paper_execution_profile(contract_report)
        mode = PROMOTION_MODE_AGENT_PAPER_CONTRACT
        strategy_source_path = promoted_source
        contract_report_path = artifact_contract_report_path

    replacements = contract_replacements
    if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT:
        patch_path = promoted_dir / PROMOTION_PATCH_FILENAME
        patch_path.write_text(
            _simple_patch_summary(
                candidate.strategy_source_path,
                replacements,
                scope=_clean(contract_report.get("scope"))
                if contract_report is not None
                else "agent_paper_contract",
            ),
            encoding="utf-8",
        )
    _validate_promoted_source_static(strategy_source_path)

    original_sha = sha256_file(candidate.strategy_source_path)
    promoted_sha = sha256_file(strategy_source_path)
    contract_payload = (
        {
            "kind": PROMOTION_HOSTED_CONTRACT_SCOPE,
            "summary": contract_summary,
            "patchPath": f"edge/{PROMOTION_PATCH_FILENAME}",
            "reportPath": f"edge/{PROMOTION_CONTRACT_REPORT_FILENAME}",
        }
        if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT
        else None
    )
    behavior_equivalence = _default_behavior_equivalence(
        mode=mode,
        replacements=replacements,
    )
    paper_dry_run = _fast_paper_validation(
        mode=mode,
        source=promoted_text,
        report=contract_report,
        candidate=candidate,
        strategy_source_path=strategy_source_path,
        packaged_files=packaged_files,
        destination=destination,
        strategy_entrypoint=strategy_entrypoint,
        runtime_env=runtime_env,
        is_denylisted_source=is_denylisted_source,
    )
    tail_trace_path = _write_paper_tail_trace(destination, paper_dry_run)
    gate_paper_dry_run = _paper_dry_run_gate_summary(
        paper_dry_run,
        trace_path=tail_trace_path,
    )
    if paper_dry_run.get("status") == "passed":
        replay_state_files = _generated_replay_initial_state_files(destination)
        if replay_state_files:
            replay_artifact_paths = {
                item.artifact_path for item in replay_state_files
            }
            packaged_files = tuple(
                item
                for item in packaged_files
                if item.artifact_path not in replay_artifact_paths
            ) + replay_state_files
    gate_path = destination / PROMOTION_GATE_FILENAME
    gate_report = _build_contract_promotion_gate_report(
        promotion_mode=mode,
        original_source_sha256=original_sha,
        promoted_source_sha256=promoted_sha,
        patch_sha256=sha256_file(patch_path) if patch_path is not None else None,
        contract=contract_payload,
        state_entries=packaged_files,
        behavior_equivalence=behavior_equivalence,
        paper_dry_run=gate_paper_dry_run,
    )
    gate_path.write_text(
        json.dumps(gate_report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if gate_report.get("status") != "passed":
        request_source_path = strategy_source_path
        if request_source_path.resolve() == candidate.strategy_source_path.resolve():
            promoted_source.write_text(original_text, encoding="utf-8")
            request_source_path = promoted_source
        failure_scan = _collect_hosted_paper_dependency_scan(
            candidate.branch,
            strategy_source_path=request_source_path,
            is_denylisted_source=is_denylisted_source,
            candidate=candidate,
            destination=destination,
        )
        failure_details = _promotion_gate_failure_request_payload(
            gate_report,
            selected_round_cutover_end=_scan_cutover_end(failure_scan),
        )
        failure_signals = _hosted_paper_contract_signals(failure_scan)
        failure_signals.append(
            {
                "kind": "promotion_gate_failed",
                "value": ",".join(
                    item.get("name", "")
                    for item in failure_details.get("failedGates", [])
                    if item.get("name")
                )
                or _clean(gate_report.get("status"))
                or "unknown",
                "reason": "latest promotion gate did not pass",
            }
        )
        request_path = _write_hosted_paper_contract_request(
            promoted_dir,
            branch=candidate.branch,
            source_path=request_source_path,
            dependency_scan=failure_scan,
            signals=failure_signals,
            validation_failure=failure_details,
        )
        raise PromotionHostedPaperContractRequired(
            "promotion gate did not pass: "
            f"{gate_report.get('status')}; request updated at {request_path}"
        )

    extra_source_map = {strategy_entrypoint: strategy_source_path}
    for item in packaged_files:
        extra_source_map[item.artifact_path] = item.source_path
    extra_source_map[f"edge/{PROMOTION_GATE_FILENAME}"] = gate_path
    if patch_path is not None:
        extra_source_map[f"edge/{PROMOTION_PATCH_FILENAME}"] = patch_path
    if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT:
        assert contract_report_path is not None
        extra_source_map[f"edge/{PROMOTION_CONTRACT_REPORT_FILENAME}"] = contract_report_path
    if tail_trace_path is not None:
        extra_source_map[f"edge/{PROMOTION_TAIL_TRACE_FILENAME}"] = tail_trace_path

    return PromotionResult(
        mode=mode,
        strategy_source_path=strategy_source_path,
        packaged_files=packaged_files,
        extra_source_map=extra_source_map,
        patch_path=patch_path,
        gate_path=gate_path,
        contract_report_path=contract_report_path,
        paper_execution_profile=paper_execution_profile,
        report={
            "mode": mode,
            "continuationMethod": _report_continuation_method(contract_report),
            "paperExecutionProfile": paper_execution_profile or {},
            "initialStateFileCount": len(
                [
                    item
                    for item in packaged_files
                    if item.role == "initial_state"
                    or item.artifact_path.startswith("runtime/initial-state/")
                ]
            ),
            "packagedFileCount": len(packaged_files),
            "replacementCount": len(replacements),
            "contractReplacementCount": len(contract_replacements),
            "contractSummary": contract_summary,
            "patchPath": str(patch_path) if patch_path is not None else "",
            "contractReportPath": str(contract_report_path)
            if contract_report_path is not None
            else "",
            "gatePath": str(gate_path),
        },
    )


def _collect_hosted_paper_dependency_scan(
    branch: Path,
    *,
    strategy_source_path: Path,
    is_denylisted_source: Callable[[Path], bool],
    candidate: Any | None = None,
    destination: Path | None = None,
) -> dict[str, Any]:
    source = strategy_source_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    imports = _source_import_facts(tree)
    file_accesses = _source_file_access_facts(tree)
    absolute_literals = [
        {"value": literal, "reason": "developer_local_absolute_path"}
        for literal in _source_string_literals(source)
        if _is_local_absolute_path(literal)
    ]
    branch_files = []
    state_dependency_signals = _state_dependency_signals(
        branch,
        strategy_source_path=strategy_source_path,
        is_denylisted_source=is_denylisted_source,
    )
    for path in sorted(branch.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(branch)
        if relative.name == "engine.py" or is_denylisted_source(relative):
            continue
        if relative.suffix.lower() not in PROMOTION_BRANCH_FILE_SUFFIXES:
            continue
        branch_files.append(
            {
                "path": relative.as_posix(),
                "suffix": relative.suffix.lower(),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "schema": "abel-invest.hosted-paper-facts/v2",
        "sourcePath": _display_source_path(branch, strategy_source_path),
        "sourceScan": _source_scan_observations(
            source,
            tree,
            file_accesses=file_accesses,
        ),
        "paperSignal": {
            "implemented": _source_overrides_get_paper_signal(source),
            "fullRuntimeCompute": _paper_signal_uses_full_runtime_compute(source),
            "fullRuntimeComputePath": _paper_signal_full_runtime_compute_path(source),
            **_paper_signal_design_facts(source),
        },
        "absolutePathLiterals": absolute_literals,
        "fileAccesses": file_accesses,
        "imports": imports,
        "branchFiles": branch_files[:200],
        "researchEvidenceFiles": _research_evidence_file_facts(branch),
        "stateDependencies": state_dependency_signals,
        "backtestWindow": _candidate_backtest_window_facts(candidate),
        "validationOracle": _trade_log_oracle_facts(
            destination / "trade-log.csv" if destination is not None else None
        ),
        "temporalDependencies": _source_temporal_dependency_facts(source, tree),
    }


def _hosted_paper_contract_signals(scan: dict[str, Any]) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    observed_training_calls = _observed_source_training_calls(scan)
    if observed_training_calls:
        _append_hosted_contract_signal(
            signals,
            seen,
            kind="ml_training_observed",
            value=", ".join(observed_training_calls[:8]),
            reason=(
                "source scan observed training/refit/update calls; hosted paper "
                "contract should use stateful_continuation first, with "
                "full_replay_fallback available only after attemptPolicy allows it"
            ),
        )
    paper_signal = scan.get("paperSignal")
    if (
        observed_training_calls
        and (
            not isinstance(paper_signal, dict)
            or paper_signal.get("implemented") is not True
        )
    ):
        _append_hosted_contract_signal(
            signals,
            seen,
            kind="missing_paper_signal",
            value="get_paper_signal",
            reason="stateful continuation must implement hosted paper signal path",
        )
    elif paper_signal.get("fullRuntimeCompute") is True:
        full_compute_path = paper_signal.get("fullRuntimeComputePath")
        value = (
            " -> ".join(str(item) for item in full_compute_path)
            if isinstance(full_compute_path, list) and full_compute_path
            else "compute_runtime_output"
        )
        _append_hosted_contract_signal(
            signals,
            seen,
            kind="paper_signal_full_recompute",
            value=value,
            reason=(
                "get_paper_signal must not wrap full historical strategy compute; "
                "stateful/direct paper code must use a live-paper fast path"
            ),
        )
    for item in scan.get("absolutePathLiterals") or []:
        if not isinstance(item, dict):
            continue
        _append_hosted_contract_signal(
            signals,
            seen,
            kind="developer_local_absolute_path",
            value=_clean(item.get("value")),
            reason="promoted strategy must not depend on developer-local absolute paths",
        )
    for item in scan.get("fileAccesses") or []:
        if not isinstance(item, dict):
            continue
        value = _clean(item.get("path"))
        if not _is_local_absolute_path(value):
            continue
        _append_hosted_contract_signal(
            signals,
            seen,
            kind="developer_local_file_access",
            value=value,
            reason="file dependency must be packaged and read through runtime paths",
        )
    for item in scan.get("imports") or []:
        if not isinstance(item, dict):
            continue
        if item.get("classification") in {"stdlib", "allowed_runtime"}:
            continue
        _append_hosted_contract_signal(
            signals,
            seen,
            kind="nonstandard_import",
            value=_clean(item.get("module")),
            reason="non-standard imports must be confirmed for hosted paper runtime",
        )
    for item in scan.get("stateDependencies") or []:
        if not isinstance(item, dict):
            continue
        _append_hosted_contract_signal(
            signals,
            seen,
            kind=_clean(item.get("kind")) or "state_dependency",
            value=_clean(item.get("value")),
            reason=_clean(item.get("reason"))
            or "state-like dependency must be classified by hosted paper contract",
        )
    return signals


def _initial_hosted_paper_contract_signals(
    scan_signals: list[dict[str, str]],
) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = [
        {
            "kind": "hosted_paper_contract_required",
            "value": "first_export",
            "reason": (
                "research strategy must declare an explicit hosted live-paper "
                "contract before first artifact export; only stateful "
                "continuation normally requires source edits"
            ),
        }
    ]
    signals.extend(scan_signals)
    return signals


def _append_hosted_contract_signal(
    signals: list[dict[str, str]],
    seen: set[tuple[str, str]],
    *,
    kind: str,
    value: str,
    reason: str,
) -> None:
    if not value:
        return
    key = (kind, value)
    if key in seen:
        return
    seen.add(key)
    signals.append({"kind": kind, "value": value, "reason": reason})


def _research_evidence_file_facts(branch: Path) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    evidence_roots = {"outputs", "promotions", "strategy_artifacts"}
    for path in sorted(item for item in branch.rglob("*") if item.is_file()):
        try:
            relative = path.relative_to(branch)
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] not in evidence_roots:
            continue
        if relative.suffix.lower() not in PROMOTION_BRANCH_FILE_SUFFIXES:
            continue
        facts.append(
            {
                "path": relative.as_posix(),
                "suffix": relative.suffix.lower(),
                "bytes": path.stat().st_size,
                "origin": "research_or_promotion_evidence",
            }
        )
        if len(facts) >= 100:
            break
    return facts


def _candidate_backtest_window_facts(candidate: Any | None) -> dict[str, Any]:
    if candidate is None:
        return {}
    edge_result = getattr(candidate, "edge_result", None)
    if not isinstance(edge_result, dict):
        return {}
    payload: dict[str, Any] = {}
    effective = edge_result.get("effective_window")
    if isinstance(effective, dict):
        payload["effectiveWindow"] = {
            key: _clean(effective.get(key)) for key in ("start", "end") if effective.get(key)
        }
    requested = edge_result.get("requested_window")
    if isinstance(requested, dict):
        payload["requestedWindow"] = {
            key: _clean(requested.get(key)) for key in ("start", "end") if requested.get(key)
        }
    for source_key, target_key in (
        ("total_days", "totalDays"),
        ("active_days", "activeDays"),
    ):
        if source_key in edge_result:
            payload[target_key] = edge_result.get(source_key)
    branch_id = _clean(getattr(candidate, "branch_id", ""))
    round_id = _clean(getattr(candidate, "round_id", ""))
    if branch_id:
        payload["branchId"] = branch_id
    if round_id:
        payload["roundId"] = round_id
    return _json_safe(payload)


def _candidate_cutover_end(candidate: Any | None) -> str:
    return _scan_cutover_end({"backtestWindow": _candidate_backtest_window_facts(candidate)})


def _scan_cutover_end(scan: dict[str, Any]) -> str:
    backtest_window = scan.get("backtestWindow")
    if not isinstance(backtest_window, dict):
        return ""
    effective = backtest_window.get("effectiveWindow")
    if not isinstance(effective, dict):
        return ""
    return _date_part(_clean(effective.get("end")))


def _trade_log_oracle_facts(trade_log_path: Path | None) -> dict[str, Any]:
    if trade_log_path is None or not trade_log_path.is_file():
        return {}
    try:
        with trade_log_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return {}
    comparable: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        decision_time = _date_part(_clean(row.get("decision_time") or row.get("date")))
        effective_time = _date_part(_clean(row.get("effective_time") or row.get("date")))
        as_of = _date_part(_clean(row.get("date") or row.get("decision_time")))
        expected = _finite_float(row.get("next_position") or row.get("nextPosition"))
        if as_of and expected is not None:
            comparable.append(
                {
                    "decisionIndex": idx,
                    "asOf": as_of,
                    "decisionTime": decision_time or as_of,
                    "effectiveTime": effective_time or as_of,
                    "expectedNextPosition": expected,
                    "source": trade_log_path.name,
                }
            )
    if not comparable:
        return {
            "rowCount": len(rows),
            "assetPolicy": (
                "selected-round validation oracle only; do not package this "
                "generated export trade-log.csv as a live strategy asset or startup state"
            ),
        }
    return {
        "rowCount": len(rows),
        "comparableRowCount": len(comparable),
        "firstComparableDate": comparable[0]["asOf"],
        "lastComparableDate": comparable[-1]["asOf"],
        "tailSample": _redacted_trade_log_oracle_sample(comparable),
        "canonicalDecisionTimeline": {
            "source": trade_log_path.name,
            "indexOrigin": 0,
            "rowOrder": (
                "CSV row order after the header is the selected-round canonical "
                "decision order"
            ),
            "rowCount": len(comparable),
            "first": _redacted_timeline_row(comparable[0]),
            "last": _redacted_timeline_row(comparable[-1]),
            "tailSample": _redacted_trade_log_oracle_sample(comparable),
            "usage": (
                "Use decisionIndex/date mappings as canonical selected-round "
                "timeline evidence for calendar anchoring and tail parity. This "
                "timeline is validation evidence, not a live strategy asset."
            ),
        },
        "assetPolicy": (
            "selected-round validation oracle only; do not package this generated "
            "export trade-log.csv as a live strategy asset or startup state"
        ),
        "diagnosticPolicy": (
            "tail sample dates are shown for debugging; expected next_position "
            "answers are withheld from the initial request and may appear only "
            "inside gate-failure comparisons. Do not encode oracle answers in "
            "strategy assets or initial state."
        ),
    }


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
) -> list[dict[str, str]]:
    if not requirements.get("statefulContinuationRequired"):
        return []
    return [
        {
            "name": "stateful_continuation_paper_state_store",
            "guideSection": "Stateful PaperStateStore Scaffold",
            "when": "requirements.statefulContinuationRequired=true",
            "purpose": (
                "Adapt this scaffold so build_paper_initial_state and "
                "get_paper_signal share the same PaperStateStore state file."
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
        "continuationMethod": continuation_method,
        "statefulContinuationRequired": stateful_required,
        "sourceEditPolicy": source_edit_policy,
        "reason": reason,
        "observedTrainingCalls": training_calls,
        "fallback": {
            "fullReplayFallbackEligible": bool(
                attempt_policy.get("fullReplayFallbackEligible")
            ),
            "notHostableAllowed": bool(attempt_policy.get("notHostableAllowed")),
            "liveContractFailures": _nonnegative_int(
                attempt_policy.get("liveContractFailures")
            ),
            "fallbackAfterFailures": _nonnegative_int(
                attempt_policy.get("fallbackAfterFailures")
            ),
            "contractRequestRefreshes": _nonnegative_int(
                attempt_policy.get("contractRequestRefreshes")
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
        },
        "hardBoundaries": [
            "Do not edit the original research branch source.",
            "Edit sourcePath only when sourceEditPolicy.required is true or when a listed allowed reason is genuinely needed.",
            "Do not package selected-round trade-log.csv, gate answers, or promotion outputs as live strategy assets or startup state.",
            "Do not choose full_replay_fallback or not_hostable unless fallback.fullReplayFallbackEligible is true.",
            "full_replay_fallback must pass tail parity and the 120s hosted paper timeout.",
        ],
    }


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


def _observed_source_training_calls(scan: dict[str, Any] | None) -> list[str]:
    if not isinstance(scan, dict):
        return []
    source_scan = scan.get("sourceScan")
    if not isinstance(source_scan, dict):
        return []
    findings = source_scan.get("positiveFindings")
    if not isinstance(findings, dict):
        return []
    calls = findings.get("observedFitCalls")
    if not isinstance(calls, list):
        return []
    observed: list[str] = []
    for item in calls:
        text = _clean(item)
        if text and text not in observed:
            observed.append(text)
    return observed[:20]


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
        "notHostableAllowed": eligible,
        "fallbackAfterFailures": PROMOTION_LIVE_CONTRACT_FAILURES_BEFORE_FALLBACK,
        "fallbackAfterRequestRefreshes": PROMOTION_CONTRACT_REQUESTS_BEFORE_FALLBACK,
        "fallbackEligibilityReason": eligibility_reason,
        "fullReplayFallbackMaxSeconds": PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS,
        "rule": (
            "Use stateless_recompute or stateful_continuation first. "
            "full_replay_fallback and not_hostable are only available after "
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
    facts_sidecar = _write_hosted_paper_contract_facts_sidecar(
        promoted_dir,
        facts=facts,
    )
    compact_facts = _hosted_paper_contract_work_order_facts(facts)
    guide = _hosted_paper_contract_guide_reference()
    guide["instruction"] = (
        "Use this guide only when stateful continuation, source edits, or a "
        "gate failure require deeper details. Clear stateless cases should be "
        "solvable from this request and sourcePath."
    )
    request_payload = {
        "schema": PROMOTION_AGENT_REQUEST_SCHEMA,
        "kind": PROMOTION_HOSTED_CONTRACT_SCOPE,
        "scope": PROMOTION_HOSTED_CONTRACT_SCOPE,
        "sourcePath": str(source_path),
        "branchPath": str(branch),
        "output": {
            "artifactDir": str(promoted_dir.parent),
            "promotedDir": str(promoted_dir),
            "reportPath": str(promoted_dir / PROMOTION_CONTRACT_REPORT_FILENAME),
        },
        "contractGuide": guide,
        "task": _hosted_paper_contract_work_order_task(requirements),
        "requirements": requirements,
        "signals": signals,
        "facts": compact_facts,
        "factSidecars": {
            "fullFactsPath": str(facts_sidecar),
            "fullFactsRelativePath": PROMOTION_CONTRACT_FACTS_FILENAME,
            "usage": (
                "Optional debugging evidence. Start from this request; inspect "
                "the sidecar only when sourcePath plus compact facts are insufficient."
            ),
        },
        "reportTemplate": _hosted_paper_contract_report_template(
            requirements,
            cutover_end=cutover_end,
        ),
        "attemptPolicy": attempt_policy,
        "validation": validation_payload,
        "selectedRoundCutoverEnd": cutover_end,
    }
    if scaffolds:
        request_payload["scaffolds"] = scaffolds
    request_path.write_text(
        json.dumps(request_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return request_path



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
        "If source inspection confirms the compact facts, preserve sourcePath and "
        "write only paper-contract-report.json with stateless_recompute plus a "
        "history boundary."
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
    ):
        value = temporal.get(key)
        if value not in (None, [], {}, ""):
            compact[key] = value[:12] if isinstance(value, list) else value
    return _json_safe(compact)


def _hosted_paper_contract_report_template(
    requirements: dict[str, Any],
    *,
    cutover_end: str,
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
    return {
        "schema": PROMOTION_AGENT_REPORT_SCHEMA,
        "kind": PROMOTION_HOSTED_CONTRACT_SCOPE,
        "scope": PROMOTION_HOSTED_CONTRACT_SCOPE,
        "sourceEdit": {
            "changed": bool(source_edit_policy.get("required")),
            "reason": source_edit_policy.get("reason") or "",
            "paths": ["engine.py"] if source_edit_policy.get("required") else [],
        },
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "continuation": {
                "method": continuation_method,
                "reason": "Fill in why this execution shape preserves semantics.",
                "futureDailyFlow": "Fill in how one future as_of call advances.",
            },
            "design": {
                "history": {
                    "boundary": "fixed_lookback_or_origin_anchored",
                    "lookbackBars": None,
                    "origin": "",
                    "reason": "Fill in the minimum history requirement.",
                },
                "state": {
                    "usesPersistentState": stateful_required,
                    "stateFiles": [] if not stateful_required else ["strategy/..."],
                    "reason": "",
                },
                "calendar": {
                    "usesAbsoluteDecisionOrdinal": False,
                    "origin": "",
                    "reason": "",
                },
                "cutover": {
                    "requiresStartupState": stateful_required,
                    "mode": "minimal_cutover_state" if stateful_required else "none",
                    "bootstrapHook": "build_paper_initial_state"
                    if stateful_required
                    else "",
                    "dataHistoryStart": "",
                    "stateEnd": cutover_end if stateful_required else "",
                    "reason": "",
                },
                "dailyStep": {
                    "reason": "Fill in what is recomputed or loaded each paper day."
                },
            },
            "evidence": {
                "observations": ["Fill in the source fact you verified."],
                "semanticChecks": [],
                "whySufficient": "Fill in why these checks are sufficient.",
            },
        },
    }


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


def _scan_has_external_file_dependency(scan: dict[str, Any] | None) -> bool:
    if not isinstance(scan, dict):
        return False
    if scan.get("absolutePathLiterals"):
        return True
    for item in scan.get("fileAccesses") or []:
        if not isinstance(item, dict):
            continue
        if _is_local_absolute_path(_clean(item.get("path"))):
            return True
    return False




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


def _validate_promoted_source_static(source_path: Path) -> None:
    source = source_path.read_text(encoding="utf-8")
    local_literals = [
        literal for literal in _source_string_literals(source) if _is_local_absolute_path(literal)
    ]
    if local_literals:
        sample = ", ".join(sorted(local_literals)[:3])
        raise PromotionHostedPaperContractRequired(
            f"promoted source still contains developer-local absolute path(s): {sample}"
        )


def _state_dependency_signals(
    branch: Path,
    *,
    strategy_source_path: Path,
    is_denylisted_source: Callable[[Path], bool],
) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    runtime_state_dir = branch / LOCAL_RUNTIME_STATE_DIR
    if runtime_state_dir.is_dir():
        for path in sorted(runtime_state_dir.rglob("*")):
            if path.is_file():
                runtime_relative = path.relative_to(runtime_state_dir).as_posix()
                _append_self_check_signal(
                    signals,
                    seen,
                    kind="runtime_state_file",
                    value=(LOCAL_RUNTIME_STATE_DIR / runtime_relative).as_posix(),
                    reason="file already exists under .abel-runtime/state",
                )

    for path in sorted(branch.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(branch)
        if _skip_state_self_check_file(relative):
            continue
        if is_denylisted_source(relative):
            continue
        lower_parts = {part.lower() for part in relative.parts}
        suffix = relative.suffix.lower()
        if suffix in STATE_SELF_CHECK_FILE_SUFFIXES:
            _append_self_check_signal(
                signals,
                seen,
                kind="state_like_file",
                value=relative.as_posix(),
                reason=f"state-like file suffix {suffix}",
            )
        elif (
            lower_parts & STATE_SELF_CHECK_DIRECTORY_PARTS
            and suffix in STATE_SELF_CHECK_DIRECTORY_SUFFIXES
        ):
            _append_self_check_signal(
                signals,
                seen,
                kind="state_like_branch_file",
                value=relative.as_posix(),
                reason="file is under a model/checkpoint/cache/state directory",
            )

    if strategy_source_path.is_file():
        source = strategy_source_path.read_text(encoding="utf-8")
        for literal in _source_string_literals(source):
            signal = _source_state_reference_signal(literal)
            if signal is None:
                continue
            _append_self_check_signal(
                signals,
                seen,
                kind="source_state_reference",
                value=literal,
                reason=signal,
            )
    return signals


def _skip_state_self_check_file(relative: Path) -> bool:
    if any(
        part
        in {
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
            "inputs",
            "outputs",
            "promotions",
            "rounds",
        }
        for part in relative.parts
    ):
        return True
    return relative.name in {
        "branch.yaml",
        "branch_state.json",
        "engine.py",
        "results.tsv",
        "state_intent.json",
    }


def _append_self_check_signal(
    signals: list[dict[str, str]],
    seen: set[tuple[str, str]],
    *,
    kind: str,
    value: str,
    reason: str,
) -> None:
    key = (kind, value)
    if key in seen:
        return
    seen.add(key)
    payload = {"kind": kind, "value": value, "reason": reason}
    signals.append(payload)


def _display_source_path(branch: Path, source_path: Path) -> str:
    try:
        return source_path.relative_to(branch).as_posix()
    except ValueError:
        if source_path.name == "engine.py" and source_path.parent.name == "promoted":
            return "promoted/engine.py"
        return source_path.name


def _is_local_absolute_path(value: str) -> bool:
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        return False
    if any(text.startswith(prefix) for prefix in ("http://", "https://", "s3://", "efs://")):
        return False
    return Path(text).is_absolute()


def _source_string_literals(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.strip()
            if text:
                literals.append(text)
    return literals


def _source_state_reference_signal(value: str) -> str | None:
    text = value.replace("\\", "/").strip()
    if not text:
        return None
    path = Path(text)
    parts = {part.lower() for part in path.parts}
    suffix = path.suffix.lower()
    if suffix in STATE_SELF_CHECK_FILE_SUFFIXES:
        return f"source string references state-like file suffix {suffix}"
    if parts & STATE_SELF_CHECK_SOURCE_PATH_PARTS:
        return "source string references model/checkpoint/registry/scaler path"
    lowered = text.lower()
    if any(keyword in lowered for keyword in STATE_SELF_CHECK_SOURCE_KEYWORDS) and (
        "/" in text or "." in path.name
    ):
        return "source string looks like a durable state path"
    return None


def _default_behavior_equivalence(
    *,
    mode: str,
    replacements: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "status": "passed",
        "method": "agent_declared_hosted_paper_contract"
        if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT
        else "source_hash_identity",
        "replacements": replacements,
    }






def _simple_patch_summary(
    source_path: Path,
    replacements: list[dict[str, str]],
    *,
    scope: str = PROMOTION_HOSTED_CONTRACT_SCOPE,
) -> str:
    lines = [
        f"source: {source_path}",
        f"scope: {scope}",
        "replacements:",
    ]
    for replacement in replacements:
        reason = replacement.get("reason")
        suffix = f" ({reason})" if reason else ""
        lines.append(f"- {replacement['path']} -> {replacement['replacement']}{suffix}")
    return "\n".join(lines) + "\n"
