"""Strategy promotion helpers for paper-ready runtime state boundaries."""

from __future__ import annotations

import ast
import csv
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from typing import Any, Callable

import pandas as pd

from abel_edge.engine.ledger import read_trade_log
from abel_edge.engine.trader import paper_run_one
from abel_edge.research.promotion_gate import build_promotion_gate_report

from . import promotion_source


LOCAL_RUNTIME_STATE_DIR = Path(".abel-runtime") / "state"
PROMOTION_MODE_ZERO_CHANGE = "zero_change"
PROMOTION_STATUS_HOSTED_PAPER_CONTRACT_REQUIRED = "hosted_paper_contract_required"
PROMOTION_MODE_AGENT_PAPER_CONTRACT = "agent_paper_contract"
PROMOTION_GATE_FILENAME = "promotion-gate.json"
PROMOTION_PATCH_FILENAME = "promotion.patch"
PROMOTION_CONTRACT_REPORT_FILENAME = "paper-contract-report.json"
PROMOTION_CONTRACT_REQUEST_FILENAME = "paper-contract-request.json"
PROMOTION_AGENT_REPORT_SCHEMA = "abel-invest.agent-paper-contract-report/v1"
PROMOTION_AGENT_REQUEST_SCHEMA = "abel-invest.agent-paper-contract-request/v1"
PROMOTION_HOSTED_CONTRACT_SCOPE = "hosted_paper_contract"
PROMOTION_PAPER_SMOKE_WARN_SECONDS = 5.0
PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS = 5.0
PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS = 150.0
PROMOTION_LIVE_REWRITE_FAILURES_BEFORE_FALLBACK = 3
PROMOTION_PAPER_TAIL_TARGET_COUNT = 20
PROMOTION_PAPER_TAIL_MAX_COUNT = 60
PROMOTION_PAPER_TAIL_TOLERANCE = 1e-9
PROMOTION_LIVE_READINESS_CONFLICT_PHRASES = (
    "after the packaged log",
    "can only replay",
    "cannot produce future",
    "can't produce future",
    "edge output",
    "finite historical",
    "finite replay",
    "historical replay",
    "no future signal",
    "not continuing",
    "not hostable",
    "not safely hostable",
    "promotion output",
    "research evidence",
)
PROMOTION_INITIAL_STATE_ORACLE_PHRASES = (
    "expectednextposition",
    "selected round",
    "selected-round",
    "selected_round",
    "tail_overrides",
    "tradelogoracle",
    "validationoracle",
    "validation oracle",
)
PROMOTION_LEGACY_PROMOTED_FILES = (
    "dependency-scan.json",
    "packaging-plan.json",
    "refactor-request.json",
    "refactor-report.json",
    "refactor-report.artifact.json",
)
PROMOTION_LEGACY_DESTINATION_DIRS = (
    "promotion-replay",
)
PROMOTION_RECONSTRUCTION_MODES = {
    "none",
    "minimal_cutover_state",
    "full_replay",
}
PROMOTION_CONTINUATION_METHODS = {
    "stateless_recompute",
    "stateful_continuation",
    "full_replay_fallback",
    "not_hostable",
}
PROMOTION_REWRITE_REQUESTS_BEFORE_FALLBACK = 3
PROMOTION_ML_STATE_EVIDENCE_TERMS = (
    "calibrator",
    "checkpoint",
    "coef",
    "coefficient",
    "coefficients",
    "encoder",
    "estimator",
    "feature selector",
    "fit index",
    "fitted",
    "forest",
    "last fit",
    "learner",
    "model",
    "models",
    "parameter",
    "parameters",
    "rf state",
    "scaler",
    "scalers",
    "training state",
    "transformer",
    "weights",
)
STATE_SELF_CHECK_FILE_SUFFIXES = {
    ".joblib",
    ".npy",
    ".npz",
    ".onnx",
    ".pkl",
    ".pickle",
    ".pt",
    ".pth",
    ".safetensors",
}
STATE_SELF_CHECK_DIRECTORY_PARTS = {
    "cache",
    "caches",
    "checkpoint",
    "checkpoints",
    "model",
    "models",
    "registry",
    "registries",
    "scaler",
    "scalers",
    "state",
    "states",
}
STATE_SELF_CHECK_DIRECTORY_SUFFIXES = STATE_SELF_CHECK_FILE_SUFFIXES | {
    ".json",
    ".yaml",
    ".yml",
}
STATE_SELF_CHECK_SOURCE_KEYWORDS = (
    "cache",
    "checkpoint",
    "joblib",
    "model",
    "pickle",
    "registry",
    "scaler",
    "state",
)
STATE_SELF_CHECK_SOURCE_PATH_PARTS = {
    "checkpoint",
    "checkpoints",
    "model",
    "models",
    "registry",
    "registries",
    "scaler",
    "scalers",
}
PROMOTION_ALLOWED_RUNTIME_IMPORTS = {
    "abel_edge",
    "numpy",
    "pandas",
}
PROMOTION_FILE_READ_FUNCTIONS = {
    "open",
    "pd.read_csv",
    "pd.read_json",
    "pd.read_parquet",
    "pd.read_pickle",
    "pandas.read_csv",
    "pandas.read_json",
    "pandas.read_parquet",
    "pandas.read_pickle",
    "np.load",
    "numpy.load",
    "joblib.load",
    "pickle.load",
}
PROMOTION_FILE_WRITE_FUNCTIONS = {
    "Path.write_text",
    "Path.write_bytes",
    "np.save",
    "numpy.save",
    "joblib.dump",
    "pickle.dump",
}
PROMOTION_BRANCH_FILE_SUFFIXES = {
    ".csv",
    ".json",
    ".joblib",
    ".npy",
    ".npz",
    ".pkl",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class PromotionPackagedFile:
    artifact_path: str
    source_path: Path
    purpose: str
    role: str

    @property
    def path(self) -> str:
        if self.artifact_path.startswith("runtime/initial-state/"):
            return self.artifact_path.removeprefix("runtime/initial-state/")
        if self.artifact_path.startswith("strategy/"):
            return self.artifact_path.removeprefix("strategy/")
        return self.artifact_path


@dataclass(frozen=True)
class PromotionResult:
    mode: str
    strategy_source_path: Path
    packaged_files: tuple[PromotionPackagedFile, ...]
    extra_source_map: dict[str, Path]
    patch_path: Path | None
    gate_path: Path
    contract_report_path: Path | None
    paper_execution_profile: dict[str, Any] | None
    report: dict[str, Any]

    @property
    def adapted(self) -> bool:
        return self.mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT


class PromotionHostedPaperRewriteRequired(RuntimeError):
    """Raised when promotion needs a hosted paper contract before publishing."""


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
        raise PromotionHostedPaperRewriteRequired(
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
            raise PromotionHostedPaperRewriteRequired(
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
        paper_dry_run=paper_dry_run,
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
        failure_details = _promotion_gate_failure_request_payload(gate_report)
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
        raise PromotionHostedPaperRewriteRequired(
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


def _cleanup_legacy_promotion_outputs(destination: Path, promoted_dir: Path) -> None:
    for name in PROMOTION_LEGACY_PROMOTED_FILES:
        path = promoted_dir / name
        if path.is_file() or path.is_symlink():
            path.unlink()
    for name in PROMOTION_LEGACY_DESTINATION_DIRS:
        path = destination / name
        if path.is_dir():
            shutil.rmtree(path)


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
                "contract must use stateful_continuation and edit source"
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
        _append_hosted_contract_signal(
            signals,
            seen,
            kind="paper_signal_full_recompute",
            value="compute_runtime_output",
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


def _redacted_trade_log_oracle_sample(
    comparable: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        _redacted_timeline_row(item)
        for item in _select_paper_tail_oracle_sample(comparable)
    ]


def _redacted_timeline_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "decisionIndex": item.get("decisionIndex"),
        "asOf": item["asOf"],
        "decisionTime": item.get("decisionTime") or item["asOf"],
        "effectiveTime": item.get("effectiveTime") or item["asOf"],
        "source": item.get("source"),
    }


TEMPORAL_CONSTANT_NAME_PARTS = (
    "bars",
    "calendar",
    "horizon",
    "lag",
    "lookback",
    "min",
    "period",
    "refit",
    "retrain",
    "row",
    "shift",
    "train",
    "window",
)
TEMPORAL_KEYWORD_NAMES = {
    "alpha",
    "halflife",
    "lag",
    "limit",
    "lookback",
    "min_periods",
    "min_rows",
    "periods",
    "refit_every",
    "span",
    "train_window",
    "window",
    "windows",
}
TEMPORAL_CALL_SUFFIXES = (
    ".bfill",
    ".cummax",
    ".cummin",
    ".cumprod",
    ".cumsum",
    ".ewm",
    ".expanding",
    ".ffill",
    ".pct_change",
    ".quantile",
    ".rank",
    ".rolling",
    ".shift",
)


def _source_temporal_dependency_facts(source: str, tree: ast.AST | None) -> dict[str, Any]:
    if tree is None:
        return {
            "lookbackHints": [],
            "calendarHints": [],
            "parameterHints": [],
            "constantHints": [],
        }
    lookback_hints: list[dict[str, Any]] = []
    calendar_hints: list[dict[str, Any]] = []
    parameter_hints: list[dict[str, Any]] = []
    constant_hints: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()

    def append_unique(collection: list[dict[str, Any]], item: dict[str, Any]) -> None:
        key = (_clean(item.get("kind")), _clean(item.get("expression")), int(item.get("line") or 0))
        if key in seen:
            return
        seen.add(key)
        collection.append(item)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _literal_or_tuple_display(node.value)
            if value is not None:
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    lowered_name = target.id.lower()
                    if not any(part in lowered_name for part in TEMPORAL_CONSTANT_NAME_PARTS):
                        continue
                    append_unique(
                        constant_hints,
                        {
                            "name": target.id,
                            "value": value,
                            "line": getattr(node, "lineno", 0),
                            "kind": "constant",
                            "expression": target.id,
                        },
                    )
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            lowered_call = call_name.lower()
            if lowered_call in {"range"} or lowered_call.endswith(".range"):
                append_unique(
                    calendar_hints,
                    {
                        "kind": "rangeLoop",
                        "expression": _source_segment(source, node),
                        "line": getattr(node, "lineno", 0),
                    },
                )
            if lowered_call in {
                "bfill",
                "cummax",
                "cummin",
                "cumprod",
                "cumsum",
                "ewm",
                "expanding",
                "ffill",
                "pct_change",
                "quantile",
                "rank",
                "rolling",
                "shift",
            } or lowered_call.endswith(TEMPORAL_CALL_SUFFIXES):
                append_unique(
                    lookback_hints,
                    {
                        "kind": lowered_call.rsplit(".", 1)[-1],
                        "expression": _source_segment(source, node),
                        "line": getattr(node, "lineno", 0),
                    },
                )
            for keyword in node.keywords:
                if keyword.arg not in TEMPORAL_KEYWORD_NAMES:
                    continue
                value = _literal_or_tuple_display(keyword.value) or _source_segment(
                    source, keyword.value
                )
                append_unique(
                    parameter_hints,
                    {
                        "kind": "parameter",
                        "name": keyword.arg,
                        "value": value,
                        "expression": f"{keyword.arg}={value}",
                        "line": getattr(keyword, "lineno", getattr(node, "lineno", 0)),
                    },
                )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            expression = _source_segment(source, node)
            if expression:
                append_unique(
                    calendar_hints,
                    {
                        "kind": "moduloOrdinal",
                        "expression": expression,
                        "line": getattr(node, "lineno", 0),
                    },
                )
        if isinstance(node, ast.Attribute) and node.attr == "iloc":
            append_unique(
                calendar_hints,
                {
                    "kind": "positionalIndexing",
                    "expression": _source_segment(source, node),
                    "line": getattr(node, "lineno", 0),
                },
            )

    return {
        "lookbackHints": lookback_hints[:40],
        "calendarHints": calendar_hints[:40],
        "parameterHints": parameter_hints[:40],
        "constantHints": constant_hints[:40],
        "interpretation": (
            "Facts only. The agent decides the temporal dependency contract; "
            "calendar hints such as range/modulo/iloc often mean row-index "
            "chronology must be anchored to the selected backtest window."
        ),
    }


def _source_scan_observations(
    source: str,
    tree: ast.AST | None,
    *,
    file_accesses: list[dict[str, Any]],
) -> dict[str, Any]:
    temporal = _source_temporal_dependency_facts(source, tree)
    observed_fit_calls = _training_call_facts(tree) if tree is not None else []
    observed_state_writes = [
        item
        for item in file_accesses
        if isinstance(item, dict) and item.get("access") == "write"
    ]
    return {
        "coverage": "best_effort_static_ast",
        "positiveFindings": {
            "observedFitCalls": observed_fit_calls,
            "observedStateWriteCalls": observed_state_writes,
            "observedLookbackOps": temporal.get("lookbackHints", []),
            "observedCalendarOps": temporal.get("calendarHints", []),
        },
        "unprovenAbsences": [
            "No observed fit/train call does not prove absence.",
            "No observed state write does not prove statelessness.",
            "Static scan does not replace source reading by the agent.",
        ],
        "agentDuty": (
            "Inspect source and report semantic dependencies the static scan missed."
        ),
    }


def _literal_or_tuple_display(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return repr(node.value) if isinstance(node.value, str) else str(node.value)
    if isinstance(node, (ast.Tuple, ast.List)):
        values: list[str] = []
        for item in node.elts:
            item_value = _literal_or_tuple_display(item)
            if item_value is None:
                return None
            values.append(item_value)
        opener, closer = ("(", ")") if isinstance(node, ast.Tuple) else ("[", "]")
        return f"{opener}{', '.join(values)}{closer}"
    return None


def _source_segment(source: str, node: ast.AST) -> str:
    try:
        segment = ast.get_source_segment(source, node)
    except Exception:
        segment = None
    if segment:
        return " ".join(segment.strip().split())
    try:
        return ast.unparse(node)
    except Exception:
        return ""


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
            "Read this Markdown guide before editing. The request contains only "
            "this promotion's facts and hard requirements; the guide contains "
            "the live-paper contract method, report shape, and validation model."
        ),
    }


def _hosted_paper_contract_requirements(
    dependency_scan: dict[str, Any],
    *,
    attempt_policy: dict[str, Any],
) -> dict[str, Any]:
    training_calls = _observed_source_training_calls(dependency_scan)
    stateful_required = bool(training_calls)
    source_edit_policy = _source_edit_policy(
        dependency_scan,
        stateful_required=stateful_required,
    )
    return {
        "continuationMethod": (
            "stateful_continuation" if stateful_required else "agent_choice"
        ),
        "statefulContinuationRequired": stateful_required,
        "sourceEditPolicy": source_edit_policy,
        "reason": (
            "Static source scan observed training/refit/update calls in the "
            "selected research source. ML or fitted-object strategies must "
            "continue strategy-owned state instead of cold refitting on every "
            "paper call."
            if stateful_required
            else (
                "No training call was observed by static scan. This is not proof "
                "of statelessness; inspect the source and choose the continuation "
                "method that preserves the strategy semantics."
            )
        ),
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
        },
        "hardBoundaries": [
            "Do not edit the original research branch source.",
            "Edit sourcePath only when sourceEditPolicy.required is true or when a listed allowed reason is genuinely needed.",
            "Do not package selected-round trade-log.csv, gate answers, or promotion outputs as live strategy assets or startup state.",
            "Do not choose full_replay_fallback or not_hostable unless fallback.fullReplayFallbackEligible is true.",
        ],
    }


def _source_edit_policy(
    dependency_scan: dict[str, Any],
    *,
    stateful_required: bool,
) -> dict[str, Any]:
    allowed_reasons = ["asset_path_normalization", "source_bug_fix"]
    if stateful_required:
        allowed_reasons.insert(0, "stateful_continuation")
    expected = stateful_required or _scan_has_external_file_dependency(dependency_scan)
    required = stateful_required
    reason = "stateful_continuation" if stateful_required else ""
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
    failure_eligible = failures >= PROMOTION_LIVE_REWRITE_FAILURES_BEFORE_FALLBACK
    refresh_eligible = request_refreshes >= PROMOTION_REWRITE_REQUESTS_BEFORE_FALLBACK
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
        "fallbackAfterFailures": PROMOTION_LIVE_REWRITE_FAILURES_BEFORE_FALLBACK,
        "fallbackAfterRequestRefreshes": PROMOTION_REWRITE_REQUESTS_BEFORE_FALLBACK,
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
    request_path.write_text(
        json.dumps(
            {
                "schema": PROMOTION_AGENT_REQUEST_SCHEMA,
                "kind": PROMOTION_HOSTED_CONTRACT_SCOPE,
                "scope": PROMOTION_HOSTED_CONTRACT_SCOPE,
                "sourcePath": str(source_path),
                "branchPath": str(branch),
                "output": {
                    "artifactDir": str(promoted_dir.parent),
                    "promotedDir": str(promoted_dir),
                    "reportPath": str(
                        promoted_dir / PROMOTION_CONTRACT_REPORT_FILENAME
                    ),
                },
                "contractGuide": _hosted_paper_contract_guide_reference(),
                "task": (
                    "Declare the selected research strategy's hosted live-paper "
                    "contract. Read contractGuide first, then use this request "
                    "for the current branch/round facts. Stateless strategies "
                    "usually need only a history boundary profile and should "
                    "preserve promoted source."
                ),
                "requirements": requirements,
                "signals": signals,
                "facts": facts,
                "attemptPolicy": attempt_policy,
                "validation": validation_payload,
                "selectedRoundCutoverEnd": cutover_end,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return request_path


def _promotion_gate_failure_request_payload(gate_report: dict[str, Any]) -> dict[str, Any]:
    failed_gates: list[dict[str, Any]] = []
    gates = gate_report.get("gates") if isinstance(gate_report.get("gates"), list) else []
    for gate in gates:
        if not isinstance(gate, dict) or gate.get("status") == "passed":
            continue
        details = gate.get("details") if isinstance(gate.get("details"), dict) else {}
        failure: dict[str, Any] = {
            "name": _clean(gate.get("name")),
            "status": _clean(gate.get("status")),
            "method": _clean(gate.get("method")),
        }
        reason = _clean(details.get("reason") or gate.get("reason"))
        if reason:
            failure["reason"] = reason
        smoke = details.get("smoke")
        if isinstance(smoke, dict):
            compact_smoke: dict[str, Any] = {}
            tail = smoke.get("tailConsistency")
            if isinstance(tail, dict):
                compact_smoke["tailConsistency"] = _redacted_tail_failure_payload(tail)
            for key in (
                "validationBootstrap",
                "warmStart",
                "elapsedSeconds",
                "firstElapsedSeconds",
                "secondElapsedSeconds",
                "warnings",
            ):
                if key in smoke:
                    compact_smoke[key] = _json_safe(smoke[key])
            if compact_smoke:
                failure["smoke"] = _json_safe(compact_smoke)
                failure["oraclePolicy"] = (
                    "gate failures are semantic diagnostics only; exact oracle "
                    "answers are not part of the paper contract request and must not be "
                    "patched into strategy code, assets, or initial state"
                )
        failed_gates.append(failure)
    return {
        "status": _clean(gate_report.get("status")),
        "failedGates": failed_gates,
    }


def _redacted_tail_failure_payload(tail: dict[str, Any]) -> dict[str, Any]:
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


def _report_has_hosted_paper_contract(report: dict[str, Any]) -> bool:
    return (
        _clean(report.get("kind")) == PROMOTION_HOSTED_CONTRACT_SCOPE
        and _clean(report.get("scope")) == PROMOTION_HOSTED_CONTRACT_SCOPE
    )


def _report_packaged_files(
    report: dict[str, Any],
    *,
    branch: Path,
    is_denylisted_source: Callable[[Path], bool],
) -> list[PromotionPackagedFile]:
    paths = report.get("paths")
    packaged_groups: list[tuple[Any, str | None]] = []
    if isinstance(paths, dict):
        packaged_groups.append((paths.get("packagedFiles") or [], None))
        packaged_groups.append((paths.get("initialStateFiles") or [], "initial_state"))
    else:
        packaged_groups.append(([], None))
    if isinstance(report.get("packagedFiles"), list):
        packaged_groups.append((report.get("packagedFiles") or [], None))

    packaged: list[PromotionPackagedFile] = []
    seen: set[str] = set()
    for raw_files, forced_role in packaged_groups:
        if not isinstance(raw_files, list):
            raise PromotionHostedPaperRewriteRequired(
                "paper contract report paths packaged file fields must be lists"
            )
        for raw in raw_files:
            if not isinstance(raw, dict):
                raise PromotionHostedPaperRewriteRequired("packaged file entries must be objects")
            artifact_path = _normalize_report_packaged_artifact_path(
                raw.get("artifactPath") or raw.get("path"),
                forced_role=forced_role,
            )
            if artifact_path in seen:
                raise PromotionHostedPaperRewriteRequired(
                    f"duplicate packaged artifact path: {artifact_path}"
                )
            seen.add(artifact_path)
            role = _packaged_file_role(artifact_path)
            _validate_packaged_artifact_path(
                artifact_path,
                role=role,
                is_denylisted_source=is_denylisted_source,
            )
            source_path = _resolve_report_source_path(raw, branch=branch, artifact_path=artifact_path)
            if not source_path.is_file():
                raise PromotionHostedPaperRewriteRequired(
                    f"packaged source file is missing for {artifact_path}: {source_path}"
                )
            packaged.append(
                PromotionPackagedFile(
                    artifact_path=artifact_path,
                    source_path=source_path,
                    purpose=_clean(raw.get("purpose")),
                    role=role,
                )
            )
    _validate_packaged_source_roles(packaged)
    return packaged


def _validate_packaged_source_roles(packaged: list[PromotionPackagedFile]) -> None:
    roles_by_source: dict[Path, set[str]] = {}
    for item in packaged:
        roles_by_source.setdefault(item.source_path.resolve(), set()).add(item.role)
    duplicated = [
        source
        for source, roles in roles_by_source.items()
        if "base_asset" in roles and "initial_state" in roles
    ]
    if duplicated:
        sample = ", ".join(str(path) for path in duplicated[:3])
        raise PromotionHostedPaperRewriteRequired(
            "the same source file cannot be packaged as both immutable strategy "
            f"asset and mutable initial state seed: {sample}"
        )


def _validate_packaged_research_evidence_sources(
    packaged: tuple[PromotionPackagedFile, ...],
    *,
    branch: Path,
    destination: Path | None = None,
    report: dict[str, Any],
) -> None:
    paper_signal = report.get("paperSignal")
    incremental_ready = (
        isinstance(paper_signal, dict) and paper_signal.get("incrementalReady") is True
    )
    if not incremental_ready:
        return

    evidence_assets = [
        item
        for item in packaged
        if item.role == "base_asset"
        and _is_generated_live_asset_source(
            item.source_path,
            branch=branch,
            destination=destination,
        )
    ]
    if not evidence_assets:
        _validate_initial_state_not_oracle_answers(packaged)
        return
    sample = _packaged_file_sample(evidence_assets)
    raise PromotionHostedPaperRewriteRequired(
        "generated research evidence or export output cannot be packaged as a live "
        "strategy asset "
        f"while paperSignal.incrementalReady=true: {sample}. Package the original "
        "external dependency instead, or use the fallback/not_hostable path only "
        "when attemptPolicy allows it."
    )


def _validate_initial_state_not_oracle_answers(
    packaged: tuple[PromotionPackagedFile, ...],
) -> None:
    contaminated = [
        item
        for item in packaged
        if item.role == "initial_state"
        and _initial_state_looks_like_oracle_answers(item.source_path)
    ]
    if not contaminated:
        return
    sample = _packaged_file_sample(contaminated)
    raise PromotionHostedPaperRewriteRequired(
        "validation oracle answers cannot be packaged as mutable startup state "
        f"while paperSignal.incrementalReady=true: {sample}. Initial state must be "
        "strategy-owned cutover state such as model/cache/cursor/retrain metadata, "
        "not selected-round tail expected positions."
    )


def _packaged_file_sample(items: list[PromotionPackagedFile]) -> str:
    return ", ".join(
        f"{item.source_path} -> {item.artifact_path}" for item in items[:3]
    )


def _initial_state_looks_like_oracle_answers(source_path: Path) -> bool:
    try:
        text = source_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    lowered = text[:1_000_000].lower()
    return any(phrase in lowered for phrase in PROMOTION_INITIAL_STATE_ORACLE_PHRASES)


def _is_generated_live_asset_source(
    source_path: Path,
    *,
    branch: Path,
    destination: Path | None = None,
) -> bool:
    if _is_research_evidence_source(source_path, branch=branch):
        return True
    if destination is not None and _is_export_evidence_source(
        source_path,
        destination=destination,
    ):
        return True
    resolved = source_path.resolve()
    text = resolved.as_posix().lower()
    parts = {part.lower() for part in resolved.parts}
    if parts & {"promoted", "promotions", "promotion-replay", "strategy_artifacts"}:
        return True
    if "tmp" in parts and ("hosted-paper" in text or "promotion" in text):
        return True
    if "temp" in parts and ("hosted-paper" in text or "promotion" in text):
        return True
    return False


def _is_export_evidence_source(source_path: Path, *, destination: Path) -> bool:
    try:
        relative = source_path.resolve().relative_to(destination.resolve())
    except ValueError:
        return False
    if not relative.parts:
        return False
    return True


def _is_research_evidence_source(source_path: Path, *, branch: Path) -> bool:
    try:
        relative = source_path.resolve().relative_to(branch.resolve())
    except ValueError:
        return False
    if not relative.parts:
        return False
    if relative.parts[0] in {"outputs", "promotions", "strategy_artifacts"}:
        return True
    return relative.name.lower() in {
        "edge-result.json",
        "edge-validation.md",
        "promotion-gate.json",
        "trade-log.csv",
    }


def _normalize_report_packaged_artifact_path(value: Any, *, forced_role: str | None) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if forced_role == "initial_state" and text and not text.startswith("runtime/initial-state/"):
        text = f"runtime/initial-state/{text.removeprefix('state/')}"
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise PromotionHostedPaperRewriteRequired(f"invalid packaged artifact path: {text!r}")
    return path.as_posix()


def _packaged_file_role(artifact_path: str) -> str:
    if artifact_path.startswith("runtime/initial-state/"):
        return "initial_state"
    if artifact_path.startswith("strategy/"):
        return "base_asset"
    raise PromotionHostedPaperRewriteRequired(
        "packaged files must use strategy/** or runtime/initial-state/** artifact paths: "
        f"{artifact_path}"
    )


def _validate_packaged_artifact_path(
    artifact_path: str,
    *,
    role: str,
    is_denylisted_source: Callable[[Path], bool],
) -> None:
    if role == "base_asset":
        relative = Path(artifact_path.removeprefix("strategy/"))
        if is_denylisted_source(relative):
            raise PromotionHostedPaperRewriteRequired(
                f"packaged artifact path is denylisted: {artifact_path}"
            )
        return
    if role == "initial_state":
        relative = Path(artifact_path.removeprefix("runtime/initial-state/"))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise PromotionHostedPaperRewriteRequired(
                f"invalid runtime initial state artifact path: {artifact_path}"
            )
        if is_denylisted_source(relative):
            raise PromotionHostedPaperRewriteRequired(
                f"runtime initial state artifact path is denylisted: {artifact_path}"
            )


def _resolve_report_source_path(
    raw: dict[str, Any],
    *,
    branch: Path,
    artifact_path: str,
) -> Path:
    source_text = _clean(raw.get("sourcePath") or raw.get("source"))
    if source_text:
        source = Path(source_text).expanduser()
        return source if source.is_absolute() else branch / source
    if artifact_path.startswith("strategy/"):
        return branch / artifact_path.removeprefix("strategy/")
    if artifact_path.startswith("runtime/initial-state/"):
        return branch / artifact_path.removeprefix("runtime/initial-state/")
    return branch / artifact_path


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
            raise PromotionHostedPaperRewriteRequired(
                "hosted paper contract report must include paperSignal"
            )
        return
    implemented = paper_signal.get("implemented")
    incremental_ready = paper_signal.get("incrementalReady")
    if require_paper_signal and implemented is not True:
        raise PromotionHostedPaperRewriteRequired(
            "hosted paper contract must set paperSignal.implemented=true"
        )
    continuation = _paper_signal_continuation_payload(paper_signal)
    continuation_method = _clean(continuation.get("method")) if continuation else ""
    if require_paper_signal and incremental_ready is not True:
        if continuation_method == "not_hostable":
            raise PromotionHostedPaperRewriteRequired(
                "paper contract report declares paperSignal.continuation.method=not_hostable; "
                "promotion cannot export a continuing hosted paper artifact"
            )
        raise PromotionHostedPaperRewriteRequired(
            "hosted paper contract must set paperSignal.incrementalReady=true"
        )
    if incremental_ready is True:
        _validate_live_readiness_claim(report)
        _validate_paper_signal_continuation_contract(paper_signal)
        if (
            continuation_method == "full_replay_fallback"
            and not full_replay_fallback_allowed
        ):
            raise PromotionHostedPaperRewriteRequired(
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
        raise PromotionHostedPaperRewriteRequired(
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
            raise PromotionHostedPaperRewriteRequired(
                "sourceEdit.changed=true conflicts with unchanged promoted source"
            )
        return
    if not isinstance(source_edit, dict):
        raise PromotionHostedPaperRewriteRequired(
            "promoted source changed; paper-contract report must declare sourceEdit"
        )
    if source_edit.get("changed") is not True:
        raise PromotionHostedPaperRewriteRequired(
            "promoted source changed; sourceEdit.changed must be true"
        )
    reason = _clean(source_edit.get("reason"))
    allowed = _allowed_source_edit_reasons(
        continuation_method,
        source_dependency_scan=source_dependency_scan,
    )
    if reason not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise PromotionHostedPaperRewriteRequired(
            "promoted source changed for an unsupported sourceEdit.reason "
            f"{reason!r}; allowed reasons: {allowed_text}"
        )
    paths = source_edit.get("paths")
    if not isinstance(paths, list) or not paths:
        raise PromotionHostedPaperRewriteRequired(
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


def _validate_paper_signal_continuation_contract(
    paper_signal: dict[str, Any],
) -> None:
    continuation = _paper_signal_continuation_payload(paper_signal)
    if not isinstance(continuation, dict):
        raise PromotionHostedPaperRewriteRequired(
            "continuing hosted paper reports must declare "
            "paperSignal.continuation"
        )
    method = _clean(continuation.get("method"))
    if method not in PROMOTION_CONTINUATION_METHODS:
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.continuation.method must be one of "
            "stateless_recompute, stateful_continuation, "
            "full_replay_fallback, or not_hostable"
        )
    if method == "not_hostable":
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.incrementalReady=true conflicts with "
            "paperSignal.continuation.method=not_hostable"
        )
    if not _clean(continuation.get("reason")):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.continuation.reason must explain why the chosen "
            "continuation shape preserves research decision semantics"
        )
    if not _clean(continuation.get("futureDailyFlow")):
        raise PromotionHostedPaperRewriteRequired(
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
        raise PromotionHostedPaperRewriteRequired(
            "continuing hosted paper reports must declare "
            "paperSignal.design with history/state/calendar/cutover/dailyStep"
        )
    history = design.get("history")
    if not isinstance(history, dict):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.history must describe the bounded "
            "history needed by hosted paper execution"
        )
    min_bars = history.get("minBars")
    if min_bars is not None:
        if not isinstance(min_bars, int) or isinstance(min_bars, bool) or min_bars < 0:
            raise PromotionHostedPaperRewriteRequired(
                "paperSignal.design.history.minBars must be a "
                "non-negative integer or null"
            )
    if not _clean(history.get("reason")):
        raise PromotionHostedPaperRewriteRequired(
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
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.history.boundary must be one of "
            "fixed_lookback, origin_anchored, state_only, or full_replay"
        )

    state = design.get("state")
    if not isinstance(state, dict) or not isinstance(
        state.get("usesPersistentState"), bool
    ):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.state.usesPersistentState must be true or false"
        )
    state_files = state.get("stateFiles")
    if state.get("usesPersistentState") is True and not (
        isinstance(state_files, list) and bool(state_files)
    ):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.state.stateFiles must list the "
            "strategy-owned state files used by hosted paper"
        )

    calendar = design.get("calendar")
    if not isinstance(calendar, dict) or not isinstance(
        calendar.get("usesAbsoluteDecisionOrdinal"), bool
    ):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.calendar.usesAbsoluteDecisionOrdinal "
            "must be true or false"
        )
    if calendar.get("usesAbsoluteDecisionOrdinal") is True and not _clean(
        calendar.get("origin")
    ):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.calendar.origin is required when "
            "absolute decision ordinals are used"
        )

    cutover = design.get("cutover")
    if not isinstance(cutover, dict) or not isinstance(
        cutover.get("requiresStartupState"), bool
    ):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.cutover.requiresStartupState must be true or false"
        )
    mode = _clean(cutover.get("mode") or cutover.get("approach"))
    if not mode:
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.cutover.mode must be one of "
            "none, minimal_cutover_state, or full_replay"
        )
    if mode not in PROMOTION_RECONSTRUCTION_MODES:
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.cutover.mode must be one of "
            "none, minimal_cutover_state, or full_replay"
        )
    required = cutover.get("requiresStartupState") is True
    if required and mode == "none":
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.cutover.requiresStartupState=true must use "
            "cutover.mode=minimal_cutover_state or full_replay"
        )
    if not required and not (
        mode == "none"
        or (continuation_method == "full_replay_fallback" and mode == "full_replay")
    ):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.design.cutover.requiresStartupState=false must use "
            "cutover.mode=none"
        )
    if mode == "full_replay" and continuation_method != "full_replay_fallback":
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.incrementalReady=true conflicts with "
            "cutover.mode=full_replay unless continuation.method is "
            "full_replay_fallback"
        )
    if required:
        state_end = _date_part(_clean(cutover.get("stateEnd")))
        if not _clean(cutover.get("dataHistoryStart")) or not state_end:
            raise PromotionHostedPaperRewriteRequired(
                "paperSignal.design.cutover must declare "
                "dataHistoryStart and stateEnd when startup state is required"
            )
        if cutover_end and state_end != cutover_end:
            raise PromotionHostedPaperRewriteRequired(
                "paperSignal.design.cutover.stateEnd must equal "
                f"the selected round cutover end {cutover_end}; startup state should "
                "be valid through the selected research result before future paper "
                "continues"
            )
    if continuation_method == "stateless_recompute" and required:
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.continuation.method=stateless_recompute must not "
            "require startup cutover state; use stateful_continuation when "
            "startup state is required"
        )
    if continuation_method == "stateful_continuation":
        if not required or mode != "minimal_cutover_state":
            raise PromotionHostedPaperRewriteRequired(
                "paperSignal.continuation.method=stateful_continuation requires "
                "paperSignal.design.cutover.requiresStartupState=true and "
                "cutover.mode=minimal_cutover_state"
            )
        if state.get("usesPersistentState") is not True:
            raise PromotionHostedPaperRewriteRequired(
                "paperSignal.continuation.method=stateful_continuation requires "
                "paperSignal.design.state.usesPersistentState=true"
            )
        if _clean(cutover.get("bootstrapHook")) != "build_paper_initial_state":
            raise PromotionHostedPaperRewriteRequired(
                "paperSignal.design.cutover.bootstrapHook must be "
                "build_paper_initial_state for stateful_continuation"
            )

    if continuation_method == "full_replay_fallback":
        if boundary != "full_replay" or mode != "full_replay":
            raise PromotionHostedPaperRewriteRequired(
                "paperSignal.continuation.method=full_replay_fallback requires "
                "history.boundary=full_replay and cutover.mode=full_replay"
            )

    daily_step = design.get("dailyStep")
    if not isinstance(daily_step, dict) or not _clean(daily_step.get("reason")):
        raise PromotionHostedPaperRewriteRequired(
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
        raise PromotionHostedPaperRewriteRequired(
            "continuing hosted paper reports must declare paperSignal.evidence"
        )
    observations = evidence.get("observations")
    if not isinstance(observations, list) or not any(
        _clean(item) for item in observations
    ):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.evidence.observations must include at least one "
            "source or local evidence fact supporting the continuation design"
        )
    if not isinstance(evidence.get("semanticChecks", []), list):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.evidence.semanticChecks must be a list"
        )
    if not _clean(evidence.get("whySufficient")):
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.evidence.whySufficient must explain why the evidence "
            "supports the chosen continuation method"
        )
    if continuation_method == "stateful_continuation":
        checks = " ".join(
            _clean(item).lower() for item in evidence.get("semanticChecks") or []
        )
        if "state" not in checks and "cutover" not in checks:
            raise PromotionHostedPaperRewriteRequired(
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
    source_dependency_scan: dict[str, Any] | None = None,
) -> None:
    source_facts = _paper_signal_design_facts(source)
    observed_fit_calls = _observed_source_training_calls(
        source_dependency_scan
    ) or source_facts.get("sourceTrainingCalls") or source_facts.get("trainingCalls") or []
    if continuation_method == "stateless_recompute" and observed_fit_calls:
        joined = ", ".join(_clean(item) for item in observed_fit_calls if _clean(item))
        raise PromotionHostedPaperRewriteRequired(
            "paperSignal.continuation.method=stateless_recompute conflicts with "
            f"observed ML training/refit/update calls in the selected source: {joined}. "
            "Use stateful_continuation and reread references/hosted-paper-contract.md."
        )
    if observed_fit_calls and continuation_method != "stateful_continuation":
        joined = ", ".join(_clean(item) for item in observed_fit_calls if _clean(item))
        raise PromotionHostedPaperRewriteRequired(
            "observed ML training/refit/update calls require "
            f"paperSignal.continuation.method=stateful_continuation: {joined}. "
            "Fallback methods are only available after attemptPolicy allows them."
        )
    if continuation_method == "stateful_continuation":
        if observed_fit_calls and not _has_ml_state_continuation_evidence(
            report, paper_signal
        ):
            joined = ", ".join(
                _clean(item) for item in observed_fit_calls if _clean(item)
            )
            raise PromotionHostedPaperRewriteRequired(
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
    raise PromotionHostedPaperRewriteRequired(
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
        raise PromotionHostedPaperRewriteRequired(
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


def _source_import_facts(tree: ast.AST | None) -> list[dict[str, str]]:
    if tree is None:
        return []
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = _top_level_module(alias.name)
                if module:
                    modules.add(module)
        elif isinstance(node, ast.ImportFrom):
            module = _top_level_module(node.module or "")
            if module:
                modules.add(module)
    return [
        {"module": module, "classification": _import_classification(module)}
        for module in sorted(modules)
    ]


def _top_level_module(value: str) -> str:
    return str(value or "").split(".", 1)[0].strip()


def _import_classification(module: str) -> str:
    if module == "__future__" or module in sys.stdlib_module_names:
        return "stdlib"
    if module in PROMOTION_ALLOWED_RUNTIME_IMPORTS:
        return "allowed_runtime"
    return "nonstandard"


def _source_file_access_facts(tree: ast.AST | None) -> list[dict[str, Any]]:
    if tree is None:
        return []
    constants = _string_constants(tree)
    facts: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        access = _file_access_kind(call_name)
        if access is None:
            continue
        path_value = ""
        if node.args:
            path_value = _string_expr_value(node.args[0], constants)
        facts.append(
            {
                "function": call_name,
                "access": access,
                "path": path_value,
                "line": getattr(node, "lineno", 0),
            }
        )
    return facts


def _file_access_kind(call_name: str) -> str | None:
    if (
        call_name in PROMOTION_FILE_READ_FUNCTIONS
        or call_name in {"read_text", "read_bytes"}
        or call_name.endswith(".read_text")
        or call_name.endswith(".read_bytes")
    ):
        return "read"
    if (
        call_name in PROMOTION_FILE_WRITE_FUNCTIONS
        or call_name in {"write_text", "write_bytes"}
        or call_name.endswith(".write_text")
        or call_name.endswith(".write_bytes")
    ):
        return "write"
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _string_expr_value(node: ast.AST, constants: dict[str, str]) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, "")
    return ""


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


def _source_overrides_get_paper_signal(source: str) -> bool:
    return promotion_source.source_overrides_get_paper_signal(source)


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


def _string_constants(tree: ast.AST) -> dict[str, str]:
    values: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = node.value.value
    return values


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


def _build_contract_promotion_gate_report(
    **kwargs: Any,
) -> dict[str, Any]:
    contract = kwargs.pop("contract", None)
    return build_promotion_gate_report(contract=contract, **kwargs)


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
            raise PromotionHostedPaperRewriteRequired(
                "paperSignal.design.history.lookbackBars or minBars must be a "
                "positive integer for fixed_lookback paper execution"
            ) from exc
        if lookback_bars <= 0:
            raise PromotionHostedPaperRewriteRequired(
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


def _paper_smoke_max_call_elapsed(smoke: dict[str, Any]) -> float:
    values: list[float] = []
    for key in ("firstElapsedSeconds", "secondElapsedSeconds"):
        value = _finite_float(smoke.get(key))
        if value is not None:
            values.append(value)
    tail = smoke.get("tailConsistency")
    comparisons = tail.get("comparisons") if isinstance(tail, dict) else None
    if isinstance(comparisons, list):
        for item in comparisons:
            if not isinstance(item, dict):
                continue
            value = _finite_float(item.get("elapsedSeconds"))
            if value is not None:
                values.append(value)
    return max(values, default=0.0)


def _run_edge_paper_run_one_smoke(
    candidate: Any,
    *,
    strategy_source_path: Path,
    packaged_files: tuple[PromotionPackagedFile, ...],
    destination: Path,
    strategy_entrypoint: str,
    runtime_env: dict[str, str] | None,
    is_denylisted_source: Callable[[Path], bool],
    report: dict[str, Any] | None,
) -> dict[str, Any]:
    started_at = time.monotonic()
    oracle_rows = _paper_tail_oracle_rows(destination / "trade-log.csv")
    if not oracle_rows:
        return {
            "status": "failed",
            "reason": (
                "paper signal tail consistency oracle is unavailable; "
                "trade-log.csv must contain date and next_position columns"
            ),
        }
    try:
        with tempfile.TemporaryDirectory(prefix="abel-paper-run-one-") as temp_name:
            root = Path(temp_name)
            strategy_dir = root / "strategy"
            runtime_dir = root / "runtime"
            state_dir = root / "state"
            strategy_dir.mkdir(parents=True)
            runtime_dir.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            _stage_paper_smoke_files(
                candidate,
                strategy_source_path=strategy_source_path,
                packaged_files=packaged_files,
                strategy_dir=strategy_dir,
                runtime_dir=runtime_dir,
                state_dir=state_dir,
                strategy_entrypoint=strategy_entrypoint,
                is_denylisted_source=is_denylisted_source,
            )
            (strategy_dir / "__init__.py").touch()
            context = _paper_smoke_context(
                candidate,
                strategy_dir=strategy_dir,
                runtime_dir=runtime_dir,
                state_dir=state_dir,
                workspace_dir=root,
            )
            context["engine"] = "strategy.strategy"
            context["trade_log"] = str(root / "trade-log.csv")
            context["paper_log"] = str(state_dir / "paper-log.csv")
            validation_context = context.get("_promotion_validation")
            profile = _report_paper_execution_profile(report)
            if profile:
                context["runtime"] = {"paperExecutionProfile": profile}
            requires_validation_bootstrap = (
                _report_continuation_method(report) == "stateful_continuation"
            )
            if requires_validation_bootstrap:
                _clear_replay_initial_state(destination)
                _clear_directory(state_dir)
            seed = _seed_paper_smoke_log(
                destination / "trade-log.csv",
                oracle_rows=oracle_rows,
                trade_log_path=Path(context["trade_log"]),
                paper_log_path=Path(context["paper_log"]),
            )
            if seed.get("status") == "failed":
                return seed
            with _temporary_environ(runtime_env or {}), _temporary_sys_path(
                [strategy_dir.parent, strategy_dir]
            ):
                bootstrap = {"required": False, "status": "skipped"}
                if requires_validation_bootstrap:
                    cls = _load_smoke_strategy_class(strategy_dir / "strategy.py")
                    engine = cls(context)
                    bootstrap = _run_paper_validation_state_bootstrap(
                        engine,
                        state_dir=state_dir,
                        oracle_rows=oracle_rows,
                        required=True,
                    )
                    if bootstrap.get("status") == "failed":
                        return {
                            "status": "failed",
                            "reason": _clean(bootstrap.get("reason"))
                            or "paper validation state bootstrap failed",
                            "validationBootstrap": bootstrap,
                        }
                before_first = _snapshot_tree(state_dir)
                run_started = time.monotonic()
                first = paper_run_one(context, as_of=oracle_rows[-1]["asOf"])
                first_elapsed = time.monotonic() - run_started
                after_first = _snapshot_tree(state_dir)
                comparisons = _paper_run_tail_comparisons(
                    Path(context["paper_log"]),
                    oracle_rows=oracle_rows,
                    elapsed_seconds=first_elapsed,
                    state_changed=after_first != before_first,
                )
                failed = [
                    item
                    for item in comparisons
                    if item.get("absDiff") is None
                    or float(item.get("absDiff")) > PROMOTION_PAPER_TAIL_TOLERANCE
                ]
                if failed:
                    return {
                        "status": "failed",
                        "reason": (
                            "paper_run_one next_position diverged from the "
                            "selected round trade-log tail"
                        ),
                        "tailConsistency": _tail_consistency_payload(
                            oracle_rows,
                            comparisons,
                            status="failed",
                        ),
                        "validationContext": _json_safe(validation_context),
                        "result": _json_safe(first),
                    }
                before_second = after_first
                second_started = time.monotonic()
                second = paper_run_one(context, as_of=oracle_rows[-1]["asOf"])
                second_elapsed = time.monotonic() - second_started
                after_second = _snapshot_tree(state_dir)
            if second.get("n_rows") != 0 or after_second != before_second:
                return {
                    "status": "failed",
                    "reason": "paper_run_one was not idempotent for the same as_of",
                    "asOf": oracle_rows[-1]["asOf"],
                    "firstResult": _json_safe(first),
                    "secondResult": _json_safe(second),
                    "validationContext": _json_safe(validation_context),
                    "tailConsistency": _tail_consistency_payload(
                        oracle_rows,
                        comparisons,
                        status="passed",
                    ),
                }
            latest_position = _finite_float(comparisons[-1].get("actualNextPosition"))
            generated_initial_state_files = []
            if requires_validation_bootstrap:
                generated_initial_state_files = _materialize_replay_initial_state(
                    state_dir,
                    destination=destination,
                )
                if not generated_initial_state_files:
                    return {
                        "status": "failed",
                        "reason": (
                            "stateful_continuation replay produced no startup "
                            "strategy state files to package"
                        ),
                        "tailConsistency": _tail_consistency_payload(
                            oracle_rows,
                            comparisons,
                            status="passed",
                        ),
                        "validationBootstrap": bootstrap,
                    }
            return {
                "status": "passed",
                "asOf": oracle_rows[-1]["asOf"],
                "nextPosition": latest_position,
                "firstElapsedSeconds": round(first_elapsed, 6),
                "secondElapsedSeconds": round(second_elapsed, 6),
                "elapsedSeconds": round(time.monotonic() - started_at, 6),
                "stateChangedFirstCall": after_first != before_first,
                "stateChangedSecondCall": False,
                "sameResult": second.get("n_rows") == 0,
                "tailConsistency": _tail_consistency_payload(
                    oracle_rows,
                    comparisons,
                    status="passed",
                ),
                "validationBootstrap": bootstrap,
                "generatedInitialStateFiles": generated_initial_state_files,
                "validationContext": _json_safe(validation_context),
                "warmStart": _warm_start_payload(
                    comparisons,
                    repeated_elapsed=second_elapsed,
                    repeated_state_changed=False,
                ),
                "warnings": [],
                "result": _json_safe(first),
            }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"{exc.__class__.__name__}: {exc}",
            "elapsedSeconds": round(time.monotonic() - started_at, 6),
        }


def _seed_paper_smoke_log(
    source_trade_log: Path,
    *,
    oracle_rows: list[dict[str, Any]],
    trade_log_path: Path,
    paper_log_path: Path,
) -> dict[str, Any]:
    cutover_as_of = _clean(oracle_rows[0].get("validationCutoverAsOf")) if oracle_rows else ""
    frame = read_trade_log(source_trade_log)
    trade_log_path.parent.mkdir(parents=True, exist_ok=True)
    paper_log_path.parent.mkdir(parents=True, exist_ok=True)
    if not cutover_as_of:
        return {
            "status": "failed",
            "reason": (
                "paper_run_one smoke requires a real selected-round cutover row "
                "before the holdout tail; refusing to synthesize a paper ledger seed"
            ),
        }
    dates = pd.to_datetime(frame["date"], utc=True, format="mixed")
    cutover = pd.to_datetime(cutover_as_of, utc=True)
    seed = frame[dates <= cutover].tail(1).copy()
    if seed.empty:
        return {
            "status": "failed",
            "reason": f"paper_run_one smoke could not find cutover row {cutover_as_of}",
        }
    seed.to_csv(trade_log_path, index=False)
    seed.to_csv(paper_log_path, index=False)
    return {"status": "passed", "cutoverAsOf": cutover_as_of}


def _paper_run_tail_comparisons(
    paper_log_path: Path,
    *,
    oracle_rows: list[dict[str, Any]],
    elapsed_seconds: float,
    state_changed: bool,
) -> list[dict[str, Any]]:
    frame = read_trade_log(paper_log_path)
    by_date: dict[str, float | None] = {}
    for _, row in frame.iterrows():
        as_of = _date_part(_clean(row.get("date") or row.get("decision_time")))
        if not as_of:
            continue
        by_date[as_of] = _finite_float(row.get("next_position"))
    per_row_elapsed = elapsed_seconds / max(len(oracle_rows), 1)
    comparisons: list[dict[str, Any]] = []
    for oracle in oracle_rows:
        actual = by_date.get(_clean(oracle.get("asOf")))
        expected = float(oracle["expectedNextPosition"])
        comparisons.append(
            {
                "asOf": oracle["asOf"],
                "decisionIndex": oracle.get("decisionIndex"),
                "expectedNextPosition": expected,
                "actualNextPosition": actual,
                "absDiff": abs(actual - expected) if actual is not None else None,
                "elapsedSeconds": round(per_row_elapsed, 6),
                "stateChanged": state_changed,
            }
        )
    return comparisons


def _fast_paper_validation(
    *,
    mode: str,
    source: str,
    report: dict[str, Any] | None,
    candidate: Any,
    strategy_source_path: Path,
    packaged_files: tuple[PromotionPackagedFile, ...],
    destination: Path,
    strategy_entrypoint: str,
    runtime_env: dict[str, str] | None,
    is_denylisted_source: Callable[[Path], bool],
) -> dict[str, Any]:
    full_compute = _paper_signal_uses_full_runtime_compute(source)
    continuation_method = _report_continuation_method(report)
    design_facts = _paper_signal_design_facts(source)
    requires_direct_signal = continuation_method != "stateless_recompute"
    if requires_direct_signal and full_compute and continuation_method != "full_replay_fallback":
        return {
            "status": "failed",
            "method": "paper_signal_contract_static",
            "reason": (
                "get_paper_signal calls compute_runtime_output, which reruns "
                "the historical strategy path instead of using a live-paper fast path"
            ),
            **design_facts,
        }
    if requires_direct_signal and not _source_overrides_get_paper_signal(source):
        return {
            "status": "failed",
            "method": "paper_signal_contract_static",
            "reason": "promoted source does not define get_paper_signal",
            **design_facts,
        }
    source_overrides_signal = _source_overrides_get_paper_signal(source)
    details: dict[str, Any] = {
        "paperExecution": "edge_paper_run_one",
        "paperSignal": "direct_get_paper_signal"
        if source_overrides_signal
        else "edge_compiled_recompute",
        "fullRuntimeCompute": full_compute,
        **design_facts,
    }
    profile = _report_paper_execution_profile(report)
    if profile:
        details["paperExecutionProfile"] = _json_safe(profile)
    if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT and report is not None:
        paper_signal = report.get("paperSignal")
        if isinstance(paper_signal, dict):
            details["incrementalReady"] = paper_signal.get("incrementalReady") is True
            live_readiness = _clean(
                paper_signal.get("liveReadiness") or paper_signal.get("notes")
            )
            if live_readiness:
                details["agentLiveReadiness"] = live_readiness
            design = _paper_signal_design_payload(paper_signal)
            if isinstance(design, dict):
                details["agentDesign"] = _json_safe(design)
            continuation = _paper_signal_continuation_payload(paper_signal)
            if isinstance(continuation, dict):
                details["agentContinuation"] = _json_safe(continuation)
            evidence = _paper_signal_evidence_payload(paper_signal)
            if isinstance(evidence, dict):
                details["agentEvidence"] = _json_safe(evidence)

    smoke = _run_edge_paper_run_one_smoke(
        candidate,
        strategy_source_path=strategy_source_path,
        packaged_files=packaged_files,
        destination=destination,
        strategy_entrypoint=strategy_entrypoint,
        runtime_env=runtime_env,
        is_denylisted_source=is_denylisted_source,
        report=report,
    )
    details["smoke"] = {
        key: value for key, value in smoke.items() if key not in {"status", "reason"}
    }
    if smoke.get("status") != "passed":
        return {
            "status": "failed",
            "method": "edge_paper_run_one_tail_smoke",
            "reason": _clean(smoke.get("reason")) or "paper_run_one smoke failed",
            **details,
        }
    if continuation_method == "full_replay_fallback":
        max_call_elapsed = _paper_smoke_max_call_elapsed(smoke)
        if max_call_elapsed > PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS:
            return {
                "status": "failed",
                "method": "full_replay_fallback_performance",
                "reason": (
                    "full_replay_fallback exceeded the hosted paper fallback "
                    f"limit of {PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS:g}s "
                    "for a single paper signal call"
                ),
                "maxCallElapsedSeconds": round(max_call_elapsed, 6),
                **details,
            }
    return {
        "status": "passed",
        "method": "edge_paper_run_one_tail_smoke",
        **details,
    }


def _replay_initial_state_root(destination: Path) -> Path:
    return destination / "promoted" / "runtime" / "initial-state"


def _clear_replay_initial_state(destination: Path) -> None:
    root = _replay_initial_state_root(destination)
    if root.exists():
        shutil.rmtree(root)


def _materialize_replay_initial_state(
    state_dir: Path,
    *,
    destination: Path,
) -> list[dict[str, Any]]:
    target_root = _replay_initial_state_root(destination)
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    strategy_state_root = state_dir / "strategy"
    search_root = strategy_state_root if strategy_state_root.is_dir() else state_dir
    for source in sorted(path for path in search_root.rglob("*") if path.is_file()):
        relative = source.relative_to(state_dir)
        if relative.name in {"paper-log.csv", "trade-log.csv"}:
            continue
        if relative.parts and relative.parts[0] != "strategy":
            continue
        artifact_path = f"runtime/initial-state/{relative.as_posix()}"
        _validate_packaged_artifact_path(
            artifact_path,
            role="initial_state",
            is_denylisted_source=lambda _relative: False,
        )
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        data = target.read_bytes()
        entries.append(
            {
                "artifactPath": artifact_path,
                "bytes": len(data),
                "sha256": _sha256_bytes(data),
                "source": "gate_tail_replay_state",
            }
        )
    return entries


def _generated_replay_initial_state_files(
    destination: Path,
) -> tuple[PromotionPackagedFile, ...]:
    root = _replay_initial_state_root(destination)
    if not root.is_dir():
        return ()
    generated: list[PromotionPackagedFile] = []
    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = source.relative_to(root)
        artifact_path = f"runtime/initial-state/{relative.as_posix()}"
        generated.append(
            PromotionPackagedFile(
                artifact_path=artifact_path,
                source_path=source,
                purpose=(
                    "Gate-generated startup state after successful stateful "
                    "tail paper replay."
                ),
                role="initial_state",
            )
        )
    return tuple(generated)


def _stage_paper_smoke_files(
    candidate: Any,
    *,
    strategy_source_path: Path,
    packaged_files: tuple[PromotionPackagedFile, ...],
    strategy_dir: Path,
    runtime_dir: Path,
    state_dir: Path,
    strategy_entrypoint: str,
    is_denylisted_source: Callable[[Path], bool],
) -> None:
    staged_packaged_sources: set[Path] = {
        item.source_path.resolve()
        for item in packaged_files
        if _is_branch_relative(item.source_path, candidate.branch)
    }
    for source_path in sorted(path for path in candidate.branch.rglob("*") if path.is_file()):
        if source_path.resolve() == candidate.strategy_source_path.resolve():
            continue
        if source_path.resolve() in staged_packaged_sources:
            continue
        relative = source_path.relative_to(candidate.branch)
        if is_denylisted_source(relative):
            continue
        destination = strategy_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)

    shutil.copy2(strategy_source_path, strategy_dir / Path(strategy_entrypoint).name)
    _copy_if_exists(candidate.branch / "branch.yaml", runtime_dir / "strategy.yaml")
    _copy_if_exists(candidate.branch / "inputs" / "dependencies.json", runtime_dir / "dependencies.json")
    _copy_if_exists(candidate.branch / "inputs" / "data_manifest.json", runtime_dir / "data_manifest.json")

    for item in packaged_files:
        if item.role == "base_asset":
            relative = Path(item.artifact_path.removeprefix("strategy/"))
            target = strategy_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, target)
        elif item.role == "initial_state":
            relative = Path(item.artifact_path.removeprefix("runtime/initial-state/"))
            runtime_target = runtime_dir / "initial-state" / relative
            runtime_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, runtime_target)
            state_target = state_dir / relative
            state_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, state_target)


def _clear_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _run_paper_validation_state_bootstrap(
    engine: Any,
    *,
    state_dir: Path,
    oracle_rows: list[dict[str, Any]],
    required: bool,
) -> dict[str, Any]:
    if not required:
        return {"required": False, "status": "skipped"}
    cutover_as_of = _clean(oracle_rows[0].get("validationCutoverAsOf")) if oracle_rows else ""
    if not cutover_as_of:
        return {
            "required": True,
            "status": "failed",
            "reason": (
                "stateful_continuation validation needs at least one trade-log "
                "row before the holdout sample to choose cutover_as_of"
            ),
        }
    hook = getattr(engine, "build_paper_initial_state", None)
    if not callable(hook):
        return {
            "required": True,
            "status": "failed",
            "reason": (
                "stateful_continuation requires BranchEngine.build_paper_initial_state"
            ),
            "cutoverAsOf": cutover_as_of,
        }

    before = _snapshot_tree(state_dir)
    started_at = time.monotonic()
    result = hook(cutover_as_of=cutover_as_of)
    elapsed = time.monotonic() - started_at
    after = _snapshot_tree(state_dir)
    wrote_default_state = False
    if after == before and isinstance(result, dict):
        default_state = state_dir / "strategy" / "paper-state.json"
        default_state.parent.mkdir(parents=True, exist_ok=True)
        default_state.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        after = _snapshot_tree(state_dir)
        wrote_default_state = True
    return {
        "required": True,
        "status": "passed",
        "method": "build_paper_initial_state",
        "cutoverAsOf": cutover_as_of,
        "elapsedSeconds": round(elapsed, 6),
        "stateChanged": after != before,
        "wroteDefaultStateFile": wrote_default_state,
        "result": _json_safe(result),
    }


def _paper_smoke_context(
    candidate: Any,
    *,
    strategy_dir: Path,
    runtime_dir: Path,
    state_dir: Path,
    workspace_dir: Path,
) -> dict[str, Any]:
    dependencies = _load_json_object_if_exists(runtime_dir / "dependencies.json")
    runtime_profile = _load_json_object_if_exists(candidate.branch / "inputs" / "runtime_profile.json")
    requirements = dependencies.get("data_requirements")
    if not isinstance(requirements, dict):
        requirements = {}
    target_asset = _clean(dependencies.get("target") or candidate.ticker).upper()
    target_node = _clean(dependencies.get("target_node")) or f"{target_asset}.price"
    timeframe = _clean(requirements.get("timeframe")) or "1d"
    fields = [
        str(field)
        for field in (requirements.get("fields") if isinstance(requirements.get("fields"), list) else ["close"])
    ]
    selected_inputs = _selected_input_symbols(dependencies.get("selected_inputs"))
    staged_feeds = _stage_paper_smoke_market_feeds(
        dependencies,
        data_dir=workspace_dir / "data",
        target_asset=target_asset,
        selected_inputs=selected_inputs,
    )
    feeds = {
        "primary": _csv_bars_feed(
            name="primary",
            symbol=target_asset,
            timeframe=timeframe,
            fields=fields,
            path=staged_feeds[target_asset]["path"],
        )
    }
    for symbol in selected_inputs:
        feeds[symbol] = _csv_bars_feed(
            name=symbol,
            symbol=symbol,
            timeframe=timeframe,
            fields=fields,
            path=staged_feeds[symbol]["path"],
        )
    requested_start = _clean(dependencies.get("requested_start"))
    return {
        "id": _clean(candidate.branch_id) or "paper_smoke_strategy",
        "asset": target_asset,
        "ticker": target_asset,
        "branch_spec": {
            "target": target_asset,
            "target_asset": target_asset,
            "target_node": target_node,
            "selected_inputs": selected_inputs,
            "data_requirements": requirements,
            "requested_start": requested_start,
        },
        "dependencies": dependencies,
        "_research": {
            "requested_window": {
                "start": requested_start,
                "end": _clean((candidate.edge_result.get("effective_window") or {}).get("end"))
                if isinstance(candidate.edge_result.get("effective_window"), dict)
                else None,
            }
        },
        "_data_contract": {"profile": "daily"},
        "_runtime_paths": {
            "base_strategy": str(strategy_dir),
            "runtime": str(runtime_dir),
            "state": str(state_dir),
            "workspace_dir": str(workspace_dir),
            "package_dir": str(workspace_dir),
            "base_dir": str(workspace_dir),
            "strategy_dir": str(strategy_dir),
            "runtime_dir": str(runtime_dir),
            "state_dir": str(state_dir),
            "output_dir": str(workspace_dir / "output"),
            "tmp_dir": str(workspace_dir / "tmp"),
        },
        "_runtime_profile": {
            "profile": "daily",
            "target": target_asset,
            "target_asset": target_asset,
            "target_node": target_node,
            "decision_event": _clean(runtime_profile.get("decision_event")) or "bar_close",
            "execution_delay_bars": int(runtime_profile.get("execution_delay_bars") or 1),
            "return_basis": _clean(runtime_profile.get("return_basis")) or "close_to_close",
        },
        "_feeds": feeds,
        "_promotion_validation": {
            "feedMode": "prepared_cache",
            "feedSources": {
                symbol: {
                    "path": str(payload["path"]),
                    "sourcePath": str(payload["sourcePath"]),
                }
                for symbol, payload in staged_feeds.items()
            },
        },
    }


def _csv_bars_feed(
    *,
    name: str,
    symbol: str,
    timeframe: str,
    fields: list[str],
    path: Path,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "bars",
        "adapter": "csv",
        "symbol": symbol,
        "timeframe": timeframe,
        "profile": "daily",
        "fields": fields,
        "path": str(path),
    }


def _stage_paper_smoke_market_feeds(
    dependencies: dict[str, Any],
    *,
    data_dir: Path,
    target_asset: str,
    selected_inputs: list[str],
) -> dict[str, dict[str, Path]]:
    cache = dependencies.get("cache")
    results = cache.get("results") if isinstance(cache, dict) else None
    if not isinstance(results, list):
        raise ValueError(
            "paper_run_one smoke requires prepared market cache results in "
            "inputs/dependencies.json; refusing to synthesize feeds from trade-log.csv"
        )

    sources: dict[str, Path] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        if item.get("ok") is False:
            continue
        symbol = _clean(item.get("symbol") or item.get("ticker"))
        data_path = _clean(item.get("data_path") or item.get("path"))
        if not symbol or not data_path:
            continue
        source = Path(data_path)
        if source.is_file():
            sources[_market_symbol_key(symbol)] = source

    required_symbols = list(dict.fromkeys([target_asset, *selected_inputs]))
    missing = [
        symbol
        for symbol in required_symbols
        if _market_symbol_key(symbol) not in sources
    ]
    if missing:
        raise ValueError(
            "paper_run_one smoke missing prepared market data for "
            f"{', '.join(missing)}; validation must use real cache/dependencies feeds"
        )

    data_dir.mkdir(parents=True, exist_ok=True)
    staged: dict[str, dict[str, Path]] = {}
    for symbol in required_symbols:
        source = sources[_market_symbol_key(symbol)]
        _validate_market_feed_csv(source, symbol=symbol)
        path = data_dir / f"{_safe_feed_filename(symbol)}.csv"
        shutil.copy2(source, path)
        staged[symbol] = {"path": path, "sourcePath": source}
    return staged


def _market_symbol_key(symbol: str) -> str:
    value = _clean(symbol)
    if value.endswith(".price"):
        value = value.removesuffix(".price")
    return value.upper()


def _validate_market_feed_csv(path: Path, *, symbol: str) -> None:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            has_row = next(reader, None) is not None
    except OSError as exc:
        raise ValueError(
            f"paper_run_one smoke cannot read prepared feed for {symbol}: {exc}"
        ) from exc
    required = {"timestamp", "close"}
    missing = sorted(required - fields)
    if missing:
        raise ValueError(
            f"paper_run_one smoke prepared feed for {symbol} is missing columns: "
            f"{', '.join(missing)}"
        )
    if not has_row:
        raise ValueError(f"paper_run_one smoke prepared feed for {symbol} is empty")


def _safe_feed_filename(symbol: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", _clean(symbol) or "asset")
    return value.strip("._") or "asset"


def _selected_input_symbols(value: Any) -> list[str]:
    symbols: list[str] = []
    if not isinstance(value, list):
        return symbols
    for item in value:
        if isinstance(item, dict):
            raw = item.get("symbol") or item.get("ticker") or item.get("node_id")
        else:
            raw = item
        text = _clean(raw)
        if text.endswith(".price"):
            text = text.removesuffix(".price")
        if text and text not in symbols:
            symbols.append(text)
    return symbols


def _paper_tail_oracle_rows(trade_log_path: Path) -> list[dict[str, Any]]:
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
    selected = _select_paper_tail_oracle_sample(comparable)
    if not selected:
        return []
    holdout_start_index = _nonnegative_int(selected[0].get("decisionIndex"))
    cutover = comparable[holdout_start_index - 1] if holdout_start_index > 0 else None
    prior = _paper_tail_prior_row(comparable, selected)
    position_change_count = _paper_tail_position_change_count(selected, prior=prior)
    selection_reason = _paper_tail_selection_reason(comparable, selected)
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


def _select_paper_tail_oracle_sample(
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
    prior = _paper_tail_prior_row(comparable, selected)
    if _paper_tail_position_change_count(selected, prior=prior) > 0:
        return selected

    for count in range(target_count + 1, max_count + 1):
        expanded = comparable[-count:]
        prior = _paper_tail_prior_row(comparable, expanded)
        if _paper_tail_position_change_count(expanded, prior=prior) > 0:
            return expanded
        selected = expanded
    return selected


def _paper_tail_prior_row(
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


def _paper_tail_position_change_count(
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


def _paper_tail_selection_reason(
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
    prior = _paper_tail_prior_row(comparable, selected)
    changes = _paper_tail_position_change_count(selected, prior=prior)
    if changes > 0:
        return "expanded_to_recent_position_change"
    return "expanded_to_max_without_position_change"


def _tail_consistency_payload(
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


def _warm_start_payload(
    comparisons: list[dict[str, Any]],
    *,
    repeated_elapsed: float,
    repeated_state_changed: bool,
) -> dict[str, Any]:
    elapsed = [float(item.get("elapsedSeconds") or 0.0) for item in comparisons]
    slow_count = sum(
        1 for value in elapsed if value > PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS
    )
    max_elapsed = max(elapsed, default=0.0)
    return {
        "method": "tail_distinct_dates_plus_repeated_latest",
        "sampleSize": len(comparisons),
        "distinctDateElapsedSeconds": [round(value, 6) for value in elapsed],
        "maxDistinctDateElapsedSeconds": round(max_elapsed, 6),
        "slowDistinctCallCount": slow_count,
        "slowThresholdSeconds": PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS,
        "distinctDateStateChangedCount": sum(
            1 for item in comparisons if item.get("stateChanged") is True
        ),
        "repeatedSameAsOfElapsedSeconds": round(repeated_elapsed, 6),
        "repeatedSameAsOfStateChanged": repeated_state_changed,
    }


def _date_part(value: str) -> str:
    if not value:
        return ""
    if "T" in value:
        return value.split("T", 1)[0]
    return value.split(" ", 1)[0]


def _load_smoke_strategy_class(path: Path):
    module_name = f"abel_paper_smoke_{hashlib.sha256(str(path).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import promoted strategy source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine_cls = getattr(module, "BranchEngine", None)
    if engine_cls is None:
        raise RuntimeError("promoted strategy source does not define BranchEngine")
    return engine_cls


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _snapshot_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        snapshot[path.relative_to(root).as_posix()] = _sha256_bytes(path.read_bytes())
    return snapshot


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_if_exists(source: Path, target: Path) -> None:
    if not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _is_branch_relative(source_path: Path, branch: Path) -> bool:
    try:
        source_path.resolve().relative_to(branch.resolve())
    except ValueError:
        return False
    return True


def _load_json_object_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@contextmanager
def _temporary_environ(env: dict[str, str]):
    original: dict[str, str | None] = {}
    for key, value in env.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _temporary_sys_path(paths: list[Path]):
    previous = list(sys.path)
    for path in reversed([str(item) for item in paths]):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        yield
    finally:
        sys.path[:] = previous


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


def _paper_signal_design_facts(source: str) -> dict[str, Any]:
    return promotion_source.paper_signal_design_facts(source)


def _training_call_facts(function: ast.AST | None) -> list[str]:
    return promotion_source.training_call_facts(function)


def _paper_signal_uses_full_runtime_compute(source: str) -> bool:
    return promotion_source.paper_signal_uses_full_runtime_compute(source)


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


def _clean(value: Any) -> str:
    return str(value or "").strip()
