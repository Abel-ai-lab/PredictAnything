"""Promotion dependency facts and source self-check helpers."""

from __future__ import annotations

import ast
import csv
from pathlib import Path
from typing import Any, Callable

from . import source_scan, tail_oracle
from .constants import (
    LOCAL_RUNTIME_STATE_DIR,
    PROMOTION_BRANCH_FILE_SUFFIXES,
    STATE_SELF_CHECK_DIRECTORY_PARTS,
    STATE_SELF_CHECK_DIRECTORY_SUFFIXES,
    STATE_SELF_CHECK_FILE_SUFFIXES,
    STATE_SELF_CHECK_SOURCE_KEYWORDS,
    STATE_SELF_CHECK_SOURCE_PATH_PARTS,
)
from .models import PromotionHostedPaperContractRequired
from .utils import _clean, _date_part, _finite_float, _json_safe

_call_name = source_scan.call_name
_paper_signal_design_facts = source_scan.paper_signal_design_facts
_paper_signal_full_runtime_compute_path = source_scan.paper_signal_full_runtime_compute_path
_paper_signal_uses_full_runtime_compute = source_scan.paper_signal_uses_full_runtime_compute
_source_file_access_facts = source_scan.source_file_access_facts
_source_import_facts = source_scan.source_import_facts
_source_overrides_get_paper_signal = source_scan.source_overrides_get_paper_signal
_source_scan_observations = source_scan.source_scan_observations
_source_temporal_dependency_facts = source_scan.source_temporal_dependency_facts
_training_call_facts = source_scan.training_call_facts
_redacted_timeline_row = tail_oracle.redacted_timeline_row
_redacted_trade_log_oracle_sample = tail_oracle.redacted_trade_log_oracle_sample

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
