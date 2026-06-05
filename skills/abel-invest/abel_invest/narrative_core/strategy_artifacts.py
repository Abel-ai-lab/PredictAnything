"""Hosted strategy artifact selection helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from abel_invest.narrative_core.contracts.branch_spec import (
    branch_selected_graph_nodes,
    branch_selected_inputs,
    default_graph_node_id,
    load_branch_spec,
)
from abel_invest.narrative_core.contracts.paths import (
    branch_spec_path,
    data_manifest_path,
    dependencies_path,
    runtime_profile_path,
)
from abel_invest.narrative_core.io import _now, read_tsv_rows
from abel_invest.narrative_core.promotion import (
    PROMOTION_GATE_FILENAME,
    PROMOTION_TAIL_TRACE_FILENAME,
    PROMOTION_HOSTED_CONTRACT_SCOPE,
    PROMOTION_MODE_AGENT_PAPER_CONTRACT,
    PROMOTION_STATUS_HOSTED_PAPER_CONTRACT_REQUIRED,
    PROMOTION_MODE_ZERO_CHANGE,
    PROMOTION_PATCH_FILENAME,
    PROMOTION_CONTRACT_REPORT_FILENAME,
    PROMOTION_CONTRACT_REQUEST_FILENAME,
    PromotionHostedPaperContractRequired,
    PromotionResult,
    prepare_promotion,
)
from abel_invest.narrative_core.runtime.edge_commands import resolve_default_python_bin
from abel_invest.narrative_core.session_lifecycle import resolve_workspace_arg_path
from abel_invest.workspace_core.edge_runtime import build_workspace_runtime_env
from abel_invest.workspace_core.workspace import find_workspace_root


STRATEGY_ARTIFACT_SCHEMA = "abel-invest.strategy-artifact/v1"
BEST_STRATEGY_REPORT_SCHEMA = "abel-invest.best-strategy/v1"
STRATEGY_ARTIFACT_ENTRYPOINT = "strategy/strategy.py"
STRATEGY_ARTIFACT_CLASS_NAME = "BranchEngine"
STRATEGY_ARTIFACT_PAPER_MODE = "paper_signal"
STRATEGY_ARTIFACT_WORKSPACE_KIND = "abel-invest"
SELECTION_MODE_AUTO_BEST_PASS = "auto_best_validation_by_pass_rate"
SELECTION_MODE_EXPLICIT_BRANCH_ROUND = "explicit_branch_round"
SELECTION_SCOPE_SESSION = "session"
SELECTION_SCOPE_BRANCH = "branch"
SELECTION_METRIC_ORDER = (
    "sharpe",
    "near_tie_full_pass",
    "annual_return",
    "max_dd_abs",
    "pass_rate",
)
SELECTION_MANIFEST_METRIC_ORDER = (
    "pass_rate",
    "sharpe",
    "calmar",
    "max_dd",
)
SELECTION_NEAR_TIE_SHARPE_DELTA = 0.1
SELECTION_RULE_AUTO_BEST_PASS = "sharpe_desc_near_tie_full_pass_v4"
SELECTION_REASON_AUTO_BEST_PASS = (
    "highest Sharpe; if an all-pass strategy is within 0.10 Sharpe of the top "
    "near-pass strategy, prefer the all-pass strategy, then highest annualized "
    "return, least severe max drawdown, highest validation pass rate, and "
    "latest recorded round"
)
DEFAULT_PROMOTIONS_DIRNAME = "promotions"
LEGACY_SESSION_ARTIFACT_DIRNAME = "paper_ready_artifact"
RUNTIME_STATE_SCHEMA = "abel-invest.runtime-state/v1"
DENYLISTED_STRATEGY_PARTS = {
    ".git",
    ".abel-runtime",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "inputs",
    "outputs",
    "promotions",
    "rounds",
    "strategy_artifacts",
    "venv",
}
DENYLISTED_STRATEGY_FILENAMES = {
    ".env",
    "branch_state.json",
    "id_rsa",
    "id_rsa.pub",
    "results.tsv",
    "state_intent.json",
}
DENYLISTED_STRATEGY_SUFFIXES = {
    ".key",
    ".pem",
    ".pyc",
    ".pyo",
}
STRATEGY_EXTRA_FILE_SUFFIXES = {
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
ARTIFACT_NULL_METRIC_KEYS_BY_APPLICABILITY = (
    ("omega_applicable", ("omega",)),
    ("position_ic_applicable", ("position_ic", "position_hit_rate")),
    (
        "position_ic_stability_applicable",
        ("position_ic_stability", "position_ic_monthly_mean"),
    ),
    ("loss_years_applicable", ("loss_years",)),
)
STALE_STRATEGY_ARTIFACT_FILES = (
    "artifact.zip",
    "edge-result.artifact.json",
    "edge-result.json",
    "edge-validation.md",
    "extra-source-map.json",
    "manifest.json",
    "metric-input.csv",
    PROMOTION_GATE_FILENAME,
    PROMOTION_TAIL_TRACE_FILENAME,
    "trade-log.csv",
)
STALE_PROMOTED_GENERATED_FILES = (
    PROMOTION_PATCH_FILENAME,
    "paper-contract-report.artifact.json",
)


@dataclass(frozen=True)
class StrategyArtifactCandidate:
    session: Path
    branch: Path
    strategy_source_path: Path
    edge_result_path: Path
    edge_report_path: Path | None
    edge_handoff_path: Path | None
    edge_metric_input_path: Path | None
    source_session_id: str
    ticker: str
    branch_id: str
    round_id: str
    decision: str
    mode: str
    description: str
    score: str
    pass_rate: float
    sharpe: float
    lo_adjusted: float
    annual_return: float | None
    calmar: float
    max_dd: float
    row: dict[str, str]
    edge_result: dict[str, Any]
    selection_rank: int
    session_round_index: int = 0
    selection_mode: str = SELECTION_MODE_AUTO_BEST_PASS
    selection_scope: str = SELECTION_SCOPE_SESSION

    @property
    def selection_metric_values(self) -> dict[str, float | None]:
        return {
            "lo_adjusted": self.lo_adjusted,
            "annual_return": self.annual_return,
            "pass_rate": self.pass_rate,
            "sharpe": self.sharpe,
            "calmar": self.calmar,
            "max_dd": self.max_dd,
            "max_dd_abs": abs(self.max_dd),
        }


@dataclass(frozen=True)
class StrategySelectionResult:
    selected: StrategyArtifactCandidate | None
    skip_reason: str
    pass_round_count: int
    eligible_count: int

    @property
    def validation_round_count(self) -> int:
        return self.pass_round_count

    @property
    def selected_branch_id(self) -> str | None:
        return self.selected.branch_id if self.selected is not None else None

    @property
    def selected_round_id(self) -> str | None:
        return self.selected.round_id if self.selected is not None else None


def select_best_pass_strategy(session: Path) -> StrategySelectionResult:
    """Select the best ranked hostable validation strategy in one Abel Invest session."""

    session = resolve_workspace_arg_path(session).resolve()
    rows = _iter_session_result_rows(session)
    session_round_indexes = _session_round_indexes(session)
    validation_rows = [
        item for item in rows if _is_validation_verdict(item[1].get("verdict"))
    ]
    if not validation_rows:
        return StrategySelectionResult(
            selected=None,
            skip_reason="no_validation_strategy",
            pass_round_count=0,
            eligible_count=0,
        )

    candidates: list[StrategyArtifactCandidate] = []
    for branch, row in validation_rows:
        branch_id = _clean(row.get("branch_id")) or branch.name
        round_id = _clean(row.get("round_id"))
        if session_round_indexes and (branch_id, round_id) not in session_round_indexes:
            continue
        candidate = _candidate_from_row(
            session=session,
            branch=branch,
            row=row,
            session_round_index=session_round_indexes.get((branch_id, round_id), 0),
        )
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        return StrategySelectionResult(
            selected=None,
            skip_reason="no_hostable_validation_strategy",
            pass_round_count=len(validation_rows),
            eligible_count=0,
        )

    selected = _with_rank(_select_auto_best_strategy(candidates), selection_rank=1)
    return StrategySelectionResult(
        selected=selected,
        skip_reason="",
        pass_round_count=len(validation_rows),
        eligible_count=len(candidates),
    )


def select_branch_promotion_candidate(
    branch: Path,
    *,
    round_id: str | None = None,
) -> StrategySelectionResult:
    """Resolve one explicit branch/round candidate for branch-level promotion."""

    branch = resolve_workspace_arg_path(branch).resolve()
    session = _session_from_branch(branch)
    rows = [(branch, row) for row in read_tsv_rows(branch / "results.tsv")]
    validation_rows = [
        item for item in rows if _is_validation_verdict(item[1].get("verdict"))
    ]
    if round_id:
        matched = [
            item for item in validation_rows if _clean(item[1].get("round_id")) == round_id
        ]
        if not matched:
            return StrategySelectionResult(
                selected=None,
                skip_reason="branch_round_not_validation",
                pass_round_count=len(validation_rows),
                eligible_count=0,
            )
        target_rows = matched
    else:
        target_rows = validation_rows
        if not target_rows:
            return StrategySelectionResult(
                selected=None,
                skip_reason="no_validation_round_in_branch",
                pass_round_count=0,
                eligible_count=0,
            )
        if len(target_rows) > 1:
            return StrategySelectionResult(
                selected=None,
                skip_reason="ambiguous_branch_promotion_round",
                pass_round_count=len(target_rows),
                eligible_count=0,
            )

    candidates: list[StrategyArtifactCandidate] = []
    for _, row in target_rows:
        candidate = _candidate_from_row(
            session=session,
            branch=branch,
            row=row,
            selection_mode=SELECTION_MODE_EXPLICIT_BRANCH_ROUND,
            selection_scope=SELECTION_SCOPE_BRANCH,
            session_round_index=0,
        )
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        return StrategySelectionResult(
            selected=None,
            skip_reason="no_hostable_branch_round",
            pass_round_count=len(validation_rows),
            eligible_count=0,
        )
    selected = _with_rank(candidates[0], selection_rank=1)
    return StrategySelectionResult(
        selected=selected,
        skip_reason="",
        pass_round_count=len(validation_rows),
        eligible_count=len(candidates),
    )


def best_strategy_report_payload(session: Path) -> dict[str, Any]:
    """Return the read-only best strategy selection for stop/progress reports."""

    session = resolve_workspace_arg_path(session).resolve()
    selection = select_best_pass_strategy(session)
    selected = selection.selected
    payload: dict[str, Any] = {
        "schema": BEST_STRATEGY_REPORT_SCHEMA,
        "session": str(session),
        "status": "selected" if selected is not None else "skipped",
        "skipReason": selection.skip_reason,
        "selectionPolicy": {
            "scope": SELECTION_SCOPE_SESSION,
            "rule": SELECTION_RULE_AUTO_BEST_PASS,
            "reason": SELECTION_REASON_AUTO_BEST_PASS,
            "metricOrder": list(SELECTION_METRIC_ORDER),
            "nearTieSharpeDelta": SELECTION_NEAR_TIE_SHARPE_DELTA,
        },
        "validationRoundCount": selection.validation_round_count,
        "eligibleCount": selection.eligible_count,
        "selectedBranchId": selection.selected_branch_id,
        "selectedRoundId": selection.selected_round_id,
        "selection": _selection_payload(selected),
        "artifactExported": False,
        "artifactUploadSkipped": True,
        "promotionStarted": False,
    }
    if selected is None:
        return payload

    metrics = (
        selected.edge_result.get("metrics")
        if isinstance(selected.edge_result.get("metrics"), dict)
        else {}
    )
    effective_window = (
        selected.edge_result.get("effective_window")
        if isinstance(selected.edge_result.get("effective_window"), dict)
        else {}
    )
    requested_window = (
        selected.edge_result.get("requested_window")
        if isinstance(selected.edge_result.get("requested_window"), dict)
        else {}
    )
    total_return = _to_float(metrics.get("total_return"))
    payload.update(
        {
            "ticker": selected.ticker,
            "branchId": selected.branch_id,
            "roundId": selected.round_id,
            "decision": selected.decision,
            "verdict": _clean(selected.edge_result.get("verdict")),
            "score": selected.score or _clean(selected.edge_result.get("score")),
            "description": selected.description,
            "metrics": {
                "totalReturn": total_return,
                "sharpe": selected.sharpe,
                "maxDrawdown": selected.max_dd,
                "loAdjusted": selected.lo_adjusted,
                "annualReturn": selected.annual_return,
                "calmar": selected.calmar,
                "passRate": selected.pass_rate,
            },
            "backtestPeriod": {
                "start": _clean(effective_window.get("start"))
                or _clean(requested_window.get("start")),
                "end": _clean(effective_window.get("end"))
                or _clean(requested_window.get("end")),
            },
            "paths": {
                "branch": str(selected.branch),
                "engine": str(selected.strategy_source_path),
                "edgeResult": str(selected.edge_result_path),
                "edgeReport": str(selected.edge_report_path or ""),
                "edgeHandoff": str(selected.edge_handoff_path or ""),
            },
        }
    )
    return payload


def build_strategy_artifact_manifest(
    candidate: StrategyArtifactCandidate,
    *,
    trade_log_path: Path,
    promotion: PromotionResult | None = None,
    created_at: str | None = None,
    abel_edge_version: str | None = None,
    abel_invest_version: str | None = None,
) -> dict[str, Any]:
    """Build the router upload manifest for one selected validation strategy."""

    branch_spec = load_branch_spec(candidate.branch)
    runtime_profile = _load_json_object(runtime_profile_path(candidate.branch))
    metrics = candidate.edge_result.get("metrics")
    if not isinstance(metrics, dict):
        raise RuntimeError("selected strategy edge result is missing metrics")

    source_files = _required_artifact_source_files(
        candidate,
        trade_log_path=trade_log_path,
        promotion=promotion,
    )
    target_asset = _target_asset(candidate, branch_spec)
    selected_inputs = branch_selected_inputs(branch_spec)
    selected_graph_nodes = branch_selected_graph_nodes(branch_spec)
    if selected_inputs and not selected_graph_nodes:
        selected_graph_nodes = [
            default_graph_node_id(asset) for asset in selected_inputs
        ]

    effective_window = (
        candidate.edge_result.get("effective_window")
        if isinstance(candidate.edge_result.get("effective_window"), dict)
        else {}
    )
    start_at = _required_timestamptz(
        effective_window.get("start"),
        field_name="backtest.effective_window.start",
    )
    end_at = _required_timestamptz(
        effective_window.get("end"),
        field_name="backtest.effective_window.end",
    )

    has_initial_state = (
        promotion is not None
        and any(_is_runtime_initial_state_file(item.artifact_path) for item in promotion.packaged_files)
    )
    runtime_state = {
        "schema": RUNTIME_STATE_SCHEMA,
        "mode": "explicit_state_dir",
        "path": "state/",
        "bootstrap": {
            "mode": "copy_from_base" if has_initial_state else "none",
            "path": "runtime/initial-state/" if has_initial_state else None,
        },
    }
    promotion_payload = _manifest_promotion_payload(candidate, promotion=promotion)

    backtest_payload = {
        "verdict": _clean(candidate.edge_result.get("verdict")).upper(),
        "startAt": start_at,
        "endAt": end_at,
        "resultRef": "edge/edge-result.json",
        "metrics": _manifest_backtest_metrics(candidate, metrics),
    }
    if candidate.edge_report_path is not None:
        backtest_payload["reportRef"] = "edge/edge-validation.md"
    latest_decision = _latest_decision_from_frame(candidate)
    if latest_decision is not None:
        backtest_payload["latestDecision"] = latest_decision

    manifest = {
        "schema": STRATEGY_ARTIFACT_SCHEMA,
        "createdAt": created_at or _now(),
        "source": {
            "workspaceKind": STRATEGY_ARTIFACT_WORKSPACE_KIND,
            "sourceSessionId": candidate.source_session_id,
            "ticker": _clean(candidate.ticker).upper(),
            "branchId": candidate.branch_id,
            "roundId": candidate.round_id,
            "selectionMode": candidate.selection_mode,
            "selectionScope": candidate.selection_scope,
            "selectionMetricOrder": list(SELECTION_MANIFEST_METRIC_ORDER)
            if candidate.selection_mode == SELECTION_MODE_AUTO_BEST_PASS
            else [],
            "selectionMetricValues": candidate.selection_metric_values,
            "selectionRank": candidate.selection_rank,
        },
        "runtime": {
            "profile": _clean(candidate.edge_result.get("profile"))
            or _clean(runtime_profile.get("profile"))
            or "unknown",
            "timeframe": _runtime_timeframe(branch_spec),
            "decisionEvent": _clean(runtime_profile.get("decision_event")) or "bar_close",
            "executionDelayBars": int(runtime_profile.get("execution_delay_bars") or 1),
            "returnBasis": _clean(runtime_profile.get("return_basis"))
            or "close_to_close",
            "implementationContract": _clean(
                candidate.edge_result.get("implementation_contract")
            )
            or "unknown",
            "abelEdgeVersion": abel_edge_version or _package_version("abel-edge"),
            "abelInvestVersion": abel_invest_version or _package_version("abel-invest"),
            "state": runtime_state,
            "resultChannel": {"mode": "return_value_first"},
        },
        "strategy": {
            "entrypoint": STRATEGY_ARTIFACT_ENTRYPOINT,
            "className": STRATEGY_ARTIFACT_CLASS_NAME,
            "targetAsset": target_asset,
            "targetNode": _clean(branch_spec.get("target_node"))
            or default_graph_node_id(target_asset),
            "selectedInputs": selected_inputs,
            "selectedGraphNodes": selected_graph_nodes,
            "paperMode": STRATEGY_ARTIFACT_PAPER_MODE,
        },
        "files": [
            _artifact_file_entry(artifact_path=artifact_path, source_path=source_path)
            for artifact_path, source_path in source_files
        ],
        "backtest": backtest_payload,
    }
    if promotion is not None and promotion.paper_execution_profile:
        manifest["runtime"]["paperExecutionProfile"] = promotion.paper_execution_profile
    manifest["promotion"] = promotion_payload
    return manifest


def export_selected_strategy_artifact(
    session: Path,
    *,
    output_dir: Path | None = None,
    python_bin: str | None = None,
    runner=subprocess.run,
) -> dict[str, Any]:
    """Export the selected hosted strategy artifact locally without uploading it."""

    selection = select_best_pass_strategy(session)
    if selection.selected is None:
        return _artifact_skip_result(selection.skip_reason)

    return _export_strategy_artifact_candidate(
        selection.selected,
        selection=selection,
        output_dir=output_dir,
        python_bin=python_bin,
        runner=runner,
    )


def promote_branch_strategy(
    branch: Path,
    *,
    round_id: str | None = None,
    output_dir: Path | None = None,
    python_bin: str | None = None,
    runner=subprocess.run,
) -> dict[str, Any]:
    """Promote one explicit branch/round into a paper-ready artifact."""

    branch = resolve_workspace_arg_path(branch).resolve()
    selection = select_branch_promotion_candidate(branch, round_id=round_id)
    if selection.selected is None:
        return _artifact_skip_result(
            selection.skip_reason,
            selection=selection,
            selected_branch_id=branch.name,
            selected_round_id=round_id,
        )

    return _export_strategy_artifact_candidate(
        selection.selected,
        selection=selection,
        output_dir=output_dir,
        python_bin=python_bin,
        runner=runner,
    )


def _export_strategy_artifact_candidate(
    candidate: StrategyArtifactCandidate,
    *,
    selection: StrategySelectionResult,
    output_dir: Path | None,
    python_bin: str | None,
    runner,
) -> dict[str, Any]:
    destination = _artifact_output_dir(candidate, output_dir=output_dir)
    _cleanup_stale_strategy_artifact_outputs(candidate, destination=destination)
    python_bin = _normalize_python_bin(
        python_bin or resolve_default_python_bin(candidate.branch),
        anchor=candidate.session,
    )

    candidate = _ensure_metric_input_for_artifact(
        candidate,
        destination=destination,
        python_bin=python_bin,
        runner=runner,
    )
    if candidate is None:
        return _artifact_skip_result("artifact_metric_input_unavailable", selection=selection)

    assert candidate.edge_metric_input_path is not None
    trade_log_path = destination / "trade-log.csv"
    _run_edge_trade_log_export(
        python_bin=python_bin,
        session=candidate.session,
        metric_input_path=candidate.edge_metric_input_path,
        trade_log_path=trade_log_path,
        runner=runner,
    )

    promotion_or_result = _prepare_promotion_for_export(
        candidate,
        destination=destination,
        selection=selection,
    )
    if isinstance(promotion_or_result, dict):
        return promotion_or_result
    promotion = promotion_or_result
    candidate = _candidate_with_artifact_edge_result_metric_nulls(
        candidate,
        destination=destination,
    )
    manifest = build_strategy_artifact_manifest(
        candidate,
        trade_log_path=trade_log_path,
        promotion=promotion,
    )
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_path = destination / "artifact.zip"
    artifact_result = _run_edge_artifact_export(
        python_bin=python_bin,
        session=candidate.session,
        candidate=candidate,
        manifest_path=manifest_path,
        trade_log_path=trade_log_path,
        artifact_path=artifact_path,
        extra_source_map=promotion.extra_source_map,
        runner=runner,
    )

    return {
        "status": "exported",
        "nextAction": "done",
        "artifactExported": True,
        "artifactUploadSkipped": False,
        "skipReason": "",
        "selectedBranchId": candidate.branch_id,
        "selectedRoundId": candidate.round_id,
        "selection": _selection_payload(candidate),
        "manifestPath": str(manifest_path),
        "artifactPath": str(artifact_path),
        "tradeLogPath": str(trade_log_path),
        "artifactSha256": artifact_result.get("artifactSha256", ""),
        "artifactBytes": artifact_result.get("artifactBytes", 0),
        "fileCount": artifact_result.get("fileCount", 0),
        "artifact": {
            "path": str(artifact_path),
            "sha256": artifact_result.get("artifactSha256", ""),
            "bytes": artifact_result.get("artifactBytes", 0),
            "fileCount": artifact_result.get("fileCount", 0),
        },
        "promotionMode": promotion.mode,
        "promotionReport": promotion.report,
        "promotion": _promotion_completion_payload(promotion),
        "validation": _promotion_validation_payload(promotion),
        "paths": {
            "manifest": str(manifest_path),
            "tradeLog": str(trade_log_path),
            "gate": str(promotion.gate_path),
            "trace": str(destination / PROMOTION_TAIL_TRACE_FILENAME)
            if (destination / PROMOTION_TAIL_TRACE_FILENAME).is_file()
            else "",
        },
    }


def _prepare_promotion_for_export(
    candidate: StrategyArtifactCandidate,
    *,
    destination: Path,
    selection: StrategySelectionResult,
) -> PromotionResult | dict[str, Any]:
    try:
        return prepare_promotion(
            candidate,
            destination=destination,
            strategy_entrypoint=STRATEGY_ARTIFACT_ENTRYPOINT,
            is_denylisted_source=_is_denylisted_strategy_source,
            sha256_file=_sha256_file,
            runtime_env=_runtime_env(candidate.branch),
        )
    except PromotionHostedPaperContractRequired as exc:
        request_path = _promotion_contract_request_path(destination)
        result = _artifact_skip_result(
            PROMOTION_STATUS_HOSTED_PAPER_CONTRACT_REQUIRED,
            selection=selection,
        )
        result["promotionMode"] = PROMOTION_STATUS_HOSTED_PAPER_CONTRACT_REQUIRED
        result["promotionReport"] = {
            "mode": PROMOTION_STATUS_HOSTED_PAPER_CONTRACT_REQUIRED,
            "reason": str(exc),
        }
        if request_path.is_file():
            result["promotionReport"]["requestPath"] = str(request_path)
            request_payload = _load_json_object(request_path)
            result["requestPath"] = str(request_path)
            result["sourcePath"] = _clean(request_payload.get("sourcePath"))
            output = (
                request_payload.get("output")
                if isinstance(request_payload.get("output"), dict)
                else {}
            )
            result["reportPath"] = _clean(output.get("reportPath"))
            result["rerunCommand"] = _promotion_rerun_command(candidate)
        gate_path = destination / PROMOTION_GATE_FILENAME
        if gate_path.is_file():
            result["promotionReport"]["gatePath"] = str(gate_path)
            result["gatePath"] = str(gate_path)
            result["failureSummary"] = _gate_failure_summary(gate_path)
            result["nextAction"] = "fix_paper_contract_and_rerun"
        return result


def _promotion_contract_request_path(destination: Path) -> Path:
    return destination / "promoted" / PROMOTION_CONTRACT_REQUEST_FILENAME


def export_strategy_artifact_command(args) -> int:
    """CLI adapter for local strategy artifact export."""

    session = resolve_workspace_arg_path(args.session).resolve()
    output_dir = Path(args.output_dir) if args.output_dir else None
    result = export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin=args.python_bin,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def best_strategy_command(args) -> int:
    """CLI adapter for read-only session best-strategy selection."""

    session = resolve_workspace_arg_path(args.session).resolve()
    payload = best_strategy_report_payload(session)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if payload.get("status") != "selected":
        print(
            "No best strategy selected "
            f"(reason={payload.get('skipReason') or 'unknown'})."
        )
        print("Read-only selection: no artifact export, upload, or promotion was run.")
        return 0

    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    period = (
        payload.get("backtestPeriod")
        if isinstance(payload.get("backtestPeriod"), dict)
        else {}
    )
    print(f"Best strategy: {payload.get('branchId')}/{payload.get('roundId')}")
    print(
        "Backtest: "
        f"{period.get('start') or 'unknown'} -> {period.get('end') or 'unknown'}"
    )
    print(
        "Metrics: "
        f"total_return={metrics.get('totalReturn')}, "
        f"sharpe={metrics.get('sharpe')}, "
        f"max_drawdown={metrics.get('maxDrawdown')}"
    )
    selection_policy = (
        payload.get("selectionPolicy")
        if isinstance(payload.get("selectionPolicy"), dict)
        else {}
    )
    print(f"Selection rule: {selection_policy.get('rule', '')}")
    print("Read-only selection: no artifact export, upload, or promotion was run.")
    return 0


def promote_strategy_command(args) -> int:
    """CLI adapter for explicit branch-level strategy promotion."""

    branch = resolve_workspace_arg_path(args.branch).resolve()
    output_dir = Path(args.output_dir) if args.output_dir else None
    result = promote_branch_strategy(
        branch,
        round_id=args.round,
        output_dir=output_dir,
        python_bin=args.python_bin,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _iter_session_result_rows(session: Path) -> list[tuple[Path, dict[str, str]]]:
    branch_root = session / "branches"
    if not branch_root.exists():
        return []

    rows: list[tuple[Path, dict[str, str]]] = []
    for branch in sorted(path for path in branch_root.iterdir() if path.is_dir()):
        for row in read_tsv_rows(branch / "results.tsv"):
            rows.append((branch, row))
    return rows


def _session_round_indexes(session: Path) -> dict[tuple[str, str], int]:
    order: dict[tuple[str, str], int] = {}
    for row in read_tsv_rows(session / "events.tsv"):
        if _clean(row.get("event")) != "round_recorded":
            continue
        key = (_clean(row.get("branch_id")), _clean(row.get("round_id")))
        if key[0] and key[1] and key not in order:
            order[key] = len(order) + 1
    return order


def _session_from_branch(branch: Path) -> Path:
    if branch.parent.name != "branches":
        raise RuntimeError(f"branch path must be under a branches directory: {branch}")
    session = branch.parent.parent
    if not session.is_dir():
        raise RuntimeError(f"branch session directory is missing: {session}")
    return session


def _candidate_from_row(
    *,
    session: Path,
    branch: Path,
    row: dict[str, str],
    selection_mode: str = SELECTION_MODE_AUTO_BEST_PASS,
    selection_scope: str = SELECTION_SCOPE_SESSION,
    session_round_index: int = 0,
) -> StrategyArtifactCandidate | None:
    result_path = _resolve_session_relative_path(session, row.get("result_path"))
    round_id = _clean(row.get("round_id"))
    if result_path is None and round_id:
        inferred_result_path = branch / "outputs" / f"{round_id}-edge-result.json"
        if inferred_result_path.is_file():
            result_path = inferred_result_path
    if result_path is None or not result_path.is_file():
        return None

    strategy_source_path = branch / "engine.py"
    if not strategy_source_path.is_file():
        return None

    edge_result = _load_json_object(result_path)
    if not edge_result:
        return None
    if not _is_validation_verdict(edge_result.get("verdict")):
        return None

    metrics = edge_result.get("metrics") if isinstance(edge_result.get("metrics"), dict) else {}
    pass_rate = _score_pass_rate(_clean(row.get("score")) or _clean(edge_result.get("score")))
    sharpe = _metric(row, metrics, row_key="sharpe", result_key="sharpe")
    lo_adjusted = _metric(row, metrics, row_key="lo_adj", result_key="lo_adjusted")
    annual_return = _to_float(metrics.get("annual_return"))
    calmar = _to_float(metrics.get("calmar"))
    max_dd = _metric(row, metrics, row_key="max_dd", result_key="max_dd")
    if (
        pass_rate is None
        or sharpe is None
        or lo_adjusted is None
        or calmar is None
        or max_dd is None
    ):
        return None

    report_path = _existing_optional_path(session, row.get("report_path"))
    if report_path is None and round_id:
        report_path = _existing_optional_file(branch / "outputs" / f"{round_id}-edge-validation.md")
    handoff_path = _existing_optional_path(session, row.get("handoff_path"))
    if handoff_path is None and round_id:
        handoff_path = _existing_optional_file(branch / "outputs" / f"{round_id}-edge-handoff.json")
    metric_input_path = _infer_metric_input_path(result_path)
    return StrategyArtifactCandidate(
        session=session,
        branch=branch,
        strategy_source_path=strategy_source_path,
        edge_result_path=result_path,
        edge_report_path=report_path,
        edge_handoff_path=handoff_path,
        edge_metric_input_path=metric_input_path if metric_input_path.is_file() else None,
        source_session_id=_clean(row.get("exp_id")) or session.name,
        ticker=_clean(row.get("ticker")) or session.parent.name.upper(),
        branch_id=_clean(row.get("branch_id")) or branch.name,
        round_id=round_id,
        decision=_clean(row.get("decision")),
        mode=_clean(row.get("mode")),
        description=_clean(row.get("description")),
        score=_clean(row.get("score")),
        pass_rate=pass_rate,
        sharpe=sharpe,
        lo_adjusted=lo_adjusted,
        annual_return=annual_return,
        calmar=calmar,
        max_dd=max_dd,
        row=dict(row),
        edge_result=edge_result,
        selection_rank=0,
        session_round_index=session_round_index,
        selection_mode=selection_mode,
        selection_scope=selection_scope,
    )


def _with_rank(
    candidate: StrategyArtifactCandidate,
    *,
    selection_rank: int,
) -> StrategyArtifactCandidate:
    return replace(candidate, selection_rank=selection_rank)


def _auto_best_strategy_rank_key(
    item: StrategyArtifactCandidate,
) -> tuple[float, float, float, float, int]:
    annual_return = (
        item.annual_return if item.annual_return is not None else float("-inf")
    )
    return (
        -item.sharpe,
        -annual_return,
        abs(item.max_dd),
        -item.pass_rate,
        -item.session_round_index,
    )


def _select_auto_best_strategy(
    candidates: list[StrategyArtifactCandidate],
) -> StrategyArtifactCandidate:
    ranked = sorted(candidates, key=_auto_best_strategy_rank_key)
    top = ranked[0]
    if _is_full_pass_candidate(top):
        return top

    near_tie_full_pass = [
        item
        for item in ranked
        if _is_full_pass_candidate(item)
        and top.sharpe - item.sharpe <= SELECTION_NEAR_TIE_SHARPE_DELTA + 1e-9
    ]
    if near_tie_full_pass:
        return near_tie_full_pass[0]
    return top


def _is_full_pass_candidate(item: StrategyArtifactCandidate) -> bool:
    return (
        _clean(item.edge_result.get("verdict")).upper() == "PASS"
        and item.pass_rate >= 1.0
    )


def _artifact_skip_result(
    skip_reason: str,
    *,
    selection: StrategySelectionResult | None = None,
    selected_branch_id: str | None = None,
    selected_round_id: str | None = None,
) -> dict[str, Any]:
    selected = selection.selected if selection else None
    action_required = skip_reason == PROMOTION_STATUS_HOSTED_PAPER_CONTRACT_REQUIRED
    result = {
        "artifactExported": False,
        "artifactUploadSkipped": True,
        "skipReason": skip_reason,
        "selectedBranchId": (selection.selected_branch_id if selection else None)
        or selected_branch_id,
        "selectedRoundId": (selection.selected_round_id if selection else None)
        or selected_round_id,
    }
    if action_required:
        result["status"] = "action_required"
        result["nextAction"] = "write_paper_contract_report"
        result["selection"] = _selection_payload(selected) if selected is not None else {}
    return result


def _selection_payload(candidate: StrategyArtifactCandidate | None) -> dict[str, Any]:
    if candidate is None:
        return {}
    mode = (
        "auto_best"
        if candidate.selection_mode == SELECTION_MODE_AUTO_BEST_PASS
        else "explicit"
    )
    return {
        "mode": mode,
        "rawMode": candidate.selection_mode,
        "scope": candidate.selection_scope,
        "branchId": candidate.branch_id,
        "roundId": candidate.round_id,
        "rank": candidate.selection_rank,
        "rule": SELECTION_RULE_AUTO_BEST_PASS if mode == "auto_best" else "",
        "reason": SELECTION_REASON_AUTO_BEST_PASS if mode == "auto_best" else "",
    }


def _promotion_rerun_command(candidate: StrategyArtifactCandidate) -> str:
    if candidate.selection_mode == SELECTION_MODE_AUTO_BEST_PASS:
        return f"abel-invest export-strategy-artifact --session {candidate.session}"
    command = f"abel-invest promote-strategy --branch {candidate.branch}"
    if candidate.round_id:
        command += f" --round {candidate.round_id}"
    return command


def _promotion_completion_payload(promotion: PromotionResult) -> dict[str, Any]:
    report = promotion.report if isinstance(promotion.report, dict) else {}
    return {
        "mode": promotion.mode,
        "sourceEdit": {
            "changed": bool(
                report.get("replacementCount") or report.get("contractReplacementCount")
            )
        },
        "continuationMethod": _promotion_continuation_method(report),
        "paperExecutionProfile": promotion.paper_execution_profile or {},
        "initialStateFileCount": report.get("initialStateFileCount", 0),
        "packagedFileCount": report.get("packagedFileCount", 0),
    }


def _promotion_validation_payload(promotion: PromotionResult) -> dict[str, Any]:
    gate = _load_json_object(promotion.gate_path)
    paper_gate = _paper_dry_run_gate(gate)
    smoke = (
        paper_gate.get("details", {}).get("smoke")
        if isinstance(paper_gate.get("details"), dict)
        else {}
    )
    tail = smoke.get("tailConsistency") if isinstance(smoke, dict) else {}
    return {
        "gateStatus": _clean(gate.get("status")) or "unknown",
        "paperDryRun": _clean(paper_gate.get("status")) or "unknown",
        "tailParity": {
            "status": _clean(tail.get("status")) if isinstance(tail, dict) else "",
            "mismatchCount": tail.get("mismatchCount")
            if isinstance(tail, dict)
            else None,
            "comparisonCount": tail.get("comparisonCount")
            if isinstance(tail, dict)
            else None,
        },
        "smokeElapsedSeconds": smoke.get("elapsedSeconds")
        if isinstance(smoke, dict)
        else None,
        "idempotent": smoke.get("sameResult") if isinstance(smoke, dict) else None,
        "generatedInitialStateFileCount": smoke.get("generatedInitialStateFileCount")
        if isinstance(smoke, dict)
        else 0,
    }


def _gate_failure_summary(gate_path: Path) -> dict[str, Any]:
    gate = _load_json_object(gate_path)
    failed = []
    for item in gate.get("gates") if isinstance(gate.get("gates"), list) else []:
        if not isinstance(item, dict) or item.get("status") == "passed":
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        failed.append(
            {
                "name": _clean(item.get("name")),
                "status": _clean(item.get("status")),
                "method": _clean(item.get("method")),
                "reason": _clean(details.get("reason") or item.get("reason")),
            }
        )
    return {"status": _clean(gate.get("status")), "failedGates": failed}


def _paper_dry_run_gate(gate: dict[str, Any]) -> dict[str, Any]:
    for item in gate.get("gates") if isinstance(gate.get("gates"), list) else []:
        if isinstance(item, dict) and item.get("name") == "paper_dry_run":
            return item
    return {}


def _promotion_continuation_method(report: dict[str, Any]) -> str:
    profile = report.get("paperExecutionProfile")
    if not isinstance(profile, dict):
        return ""
    # The report keeps the canonical profile, but method lives in the gate
    # details. The top-level mode remains the stable completion signal here.
    return _clean(report.get("continuationMethod"))


def _artifact_output_dir(
    candidate: StrategyArtifactCandidate,
    *,
    output_dir: Path | None,
) -> Path:
    if output_dir is not None:
        destination = resolve_workspace_arg_path(output_dir).resolve()
    else:
        destination = (
            candidate.branch
            / DEFAULT_PROMOTIONS_DIRNAME
            / (candidate.round_id or "selected")
        )
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _cleanup_stale_strategy_artifact_outputs(
    candidate: StrategyArtifactCandidate,
    *,
    destination: Path,
) -> None:
    legacy_session_artifact = candidate.session / LEGACY_SESSION_ARTIFACT_DIRNAME
    if legacy_session_artifact.is_dir():
        shutil.rmtree(legacy_session_artifact)
    elif legacy_session_artifact.exists():
        legacy_session_artifact.unlink()

    active_contract = _destination_has_active_agent_contract(destination)
    for name in STALE_STRATEGY_ARTIFACT_FILES:
        path = destination / name
        if path.is_file() or path.is_symlink():
            path.unlink()
    promoted_dir = destination / "promoted"
    if not promoted_dir.exists():
        return
    if not active_contract:
        shutil.rmtree(promoted_dir)
        return
    for name in STALE_PROMOTED_GENERATED_FILES:
        path = promoted_dir / name
        if path.is_file() or path.is_symlink():
            path.unlink()


def _destination_has_active_agent_contract(destination: Path) -> bool:
    promoted_dir = destination / "promoted"
    promoted_source = promoted_dir / "engine.py"
    report = promoted_dir / PROMOTION_CONTRACT_REPORT_FILENAME
    if not promoted_source.is_file() or not report.is_file():
        return False
    gate_status = _promotion_gate_status(destination / PROMOTION_GATE_FILENAME)
    if gate_status == "failed":
        return True
    if gate_status == "passed":
        return False
    if (destination / "artifact.zip").exists() or (destination / "manifest.json").exists():
        return False
    return True


def _promotion_gate_status(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return _clean(payload.get("status"))


def _ensure_metric_input_for_artifact(
    candidate: StrategyArtifactCandidate,
    *,
    destination: Path,
    python_bin: str,
    runner,
) -> StrategyArtifactCandidate | None:
    if (
        candidate.edge_metric_input_path is not None
        and candidate.edge_metric_input_path.is_file()
    ):
        return candidate

    result_path = destination / "edge-result.json"
    report_path = destination / "edge-validation.md"
    metric_input_path = destination / "metric-input.csv"
    result = _run_edge_metric_input_export(
        python_bin=python_bin,
        candidate=candidate,
        result_path=result_path,
        report_path=report_path,
        metric_input_path=metric_input_path,
        runner=runner,
    )
    if not _is_validation_verdict(result.get("verdict")) or not metric_input_path.is_file():
        return None
    return replace(
        candidate,
        edge_result_path=result_path,
        edge_report_path=report_path if report_path.is_file() else None,
        edge_result=result,
        edge_metric_input_path=metric_input_path,
    )


def _run_edge_metric_input_export(
    *,
    python_bin: str,
    candidate: StrategyArtifactCandidate,
    result_path: Path,
    report_path: Path,
    metric_input_path: Path,
    runner,
) -> dict[str, Any]:
    command = [
        python_bin,
        "-m",
        "abel_edge.cli",
        "evaluate",
        "--workdir",
        str(candidate.branch),
        "--output-json",
        str(result_path),
        "--output-md",
        str(report_path),
        "--output-csv",
        str(metric_input_path),
    ]
    start = _edge_result_requested_start(candidate.edge_result)
    if start:
        command.extend(["--start", start])
    context_path = _edge_result_context_path(candidate.edge_result)
    if context_path is not None:
        command.extend(["--context-json", str(context_path)])

    completed = runner(
        command,
        cwd=candidate.session,
        capture_output=True,
        text=True,
        env=_runtime_env(candidate.branch),
    )
    if not result_path.exists():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Abel-edge evaluate did not export metric input: {detail}")
    return _load_json_object(result_path)


def _run_edge_trade_log_export(
    *,
    python_bin: str,
    session: Path,
    metric_input_path: Path,
    trade_log_path: Path,
    runner,
) -> dict[str, Any]:
    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from abel_edge.research.artifact_export import "
        "write_backtest_trade_log_from_metric_input\n"
        "result = write_backtest_trade_log_from_metric_input("
        "Path(sys.argv[1]), Path(sys.argv[2]))\n"
        "print(json.dumps(result, sort_keys=True))\n"
    )
    completed = runner(
        [python_bin, "-c", script, str(metric_input_path), str(trade_log_path)],
        cwd=session,
        capture_output=True,
        text=True,
        env=_runtime_env(session),
    )
    if completed.returncode != 0 or not trade_log_path.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Abel-edge trade log export failed: {detail}")
    try:
        payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Abel-edge trade log export returned invalid JSON: {exc}") from exc
    return payload if isinstance(payload, dict) else {}


def _run_edge_artifact_export(
    *,
    python_bin: str,
    session: Path,
    candidate: StrategyArtifactCandidate,
    manifest_path: Path,
    trade_log_path: Path,
    artifact_path: Path,
    extra_source_map: dict[str, Path] | None = None,
    runner,
) -> dict[str, Any]:
    extra_source_map_path = None
    if extra_source_map:
        extra_source_map_path = artifact_path.with_name("extra-source-map.json")
        extra_source_map_path.write_text(
            json.dumps(
                {
                    artifact_path: str(source_path)
                    for artifact_path, source_path in extra_source_map.items()
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    command = [
        python_bin,
        "-m",
        "abel_edge.cli",
        "export-artifact",
        "--workdir",
        str(candidate.branch),
        "--manifest-json",
        str(manifest_path),
        "--edge-result",
        str(candidate.edge_result_path),
        "--trade-log",
        str(trade_log_path),
        "--output-zip",
        str(artifact_path),
    ]
    if candidate.edge_report_path is not None:
        command.extend(["--edge-report", str(candidate.edge_report_path)])
    if extra_source_map_path is not None:
        command.extend(["--extra-source-map", str(extra_source_map_path)])
    completed = runner(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=_runtime_env(candidate.branch),
    )
    if completed.returncode != 0 or not artifact_path.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Abel-edge artifact export failed: {detail}")
    try:
        payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Abel-edge artifact export returned invalid JSON: {exc}") from exc
    return payload if isinstance(payload, dict) else {}


def _candidate_with_artifact_edge_result_metric_nulls(
    candidate: StrategyArtifactCandidate,
    *,
    destination: Path,
) -> StrategyArtifactCandidate:
    edge_result = _edge_result_with_artifact_metric_nulls(candidate.edge_result)
    if edge_result == candidate.edge_result:
        return candidate

    edge_result_path = destination / "edge-result.artifact.json"
    edge_result_path.write_text(
        json.dumps(edge_result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return replace(candidate, edge_result_path=edge_result_path, edge_result=edge_result)


def _edge_result_with_artifact_metric_nulls(edge_result: dict[str, Any]) -> dict[str, Any]:
    metrics = edge_result.get("metrics")
    if not isinstance(metrics, dict):
        return edge_result

    artifact_metrics = dict(metrics)
    changed = False
    for flag_key, metric_keys in ARTIFACT_NULL_METRIC_KEYS_BY_APPLICABILITY:
        if artifact_metrics.get(flag_key) is not False:
            continue
        for metric_key in metric_keys:
            if metric_key not in artifact_metrics or artifact_metrics.get(metric_key) is not None:
                changed = True
            artifact_metrics[metric_key] = None
    if not changed:
        return edge_result

    payload = dict(edge_result)
    payload["metrics"] = artifact_metrics
    return payload


def _runtime_env(path: Path) -> dict[str, str] | None:
    workspace_root = find_workspace_root(path)
    return build_workspace_runtime_env(workspace_root) if workspace_root is not None else None


def _infer_metric_input_path(result_path: Path) -> Path:
    name = result_path.name
    if name.endswith("-edge-result.json"):
        prefix = name.removesuffix("-edge-result.json")
        frame_path = result_path.with_name(prefix + "-edge-frame.csv")
        if frame_path.is_file():
            return frame_path
        return result_path.with_name(prefix + "-metric-input.csv")
    return result_path.with_name(result_path.stem + "-metric-input.csv")


def _edge_result_requested_start(edge_result: dict[str, Any]) -> str:
    requested = edge_result.get("requested_window")
    if isinstance(requested, dict):
        value = _clean(requested.get("start"))
        if value:
            return value
    effective = edge_result.get("effective_window")
    if isinstance(effective, dict):
        return _clean(effective.get("start"))
    return ""


def _edge_result_context_path(edge_result: dict[str, Any]) -> Path | None:
    value = _clean(edge_result.get("context_path"))
    if not value:
        return None
    path = Path(value)
    return path if path.is_file() else None


def _normalize_python_bin(python_bin: str, *, anchor: Path) -> str:
    """Make path-like Python executables stable across subprocess cwd changes."""

    text = str(python_bin or "").strip()
    if not text:
        return text
    if "/" not in text and "\\" not in text:
        return text
    path = Path(text).expanduser()
    if path.is_absolute():
        return str(path)
    workspace_root = find_workspace_root(anchor)
    base = workspace_root if workspace_root is not None else Path.cwd()
    return str((base / path).absolute())


def _manifest_promotion_payload(
    candidate: StrategyArtifactCandidate,
    *,
    promotion: PromotionResult | None,
) -> dict[str, Any]:
    source_path = candidate.strategy_source_path
    promoted_path = promotion.strategy_source_path if promotion is not None else source_path
    mode = promotion.mode if promotion is not None else PROMOTION_MODE_ZERO_CHANGE
    payload: dict[str, Any] = {
        "mode": mode,
        "originalSourceSha256": _sha256_file(source_path),
        "promotedSourceSha256": _sha256_file(promoted_path),
        "patchSha256": _sha256_file(promotion.patch_path)
        if promotion is not None and promotion.patch_path is not None
        else None,
        "gate": {
            "status": "passed",
            "evidencePath": f"edge/{PROMOTION_GATE_FILENAME}"
            if promotion is not None
            else None,
        },
    }
    if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT:
        contract = {
            "kind": PROMOTION_HOSTED_CONTRACT_SCOPE,
            "summary": promotion.report.get("contractSummary")
            if promotion is not None
            else "Agent declared the hosted paper contract.",
            "reportPath": f"edge/{PROMOTION_CONTRACT_REPORT_FILENAME}",
        }
        if promotion is not None and promotion.patch_path is not None:
            contract["patchPath"] = f"edge/{PROMOTION_PATCH_FILENAME}"
        payload["contract"] = contract
    return payload


def _required_artifact_source_files(
    candidate: StrategyArtifactCandidate,
    *,
    trade_log_path: Path,
    promotion: PromotionResult | None = None,
) -> list[tuple[str, Path]]:
    files = [
        ("edge/edge-result.json", candidate.edge_result_path),
        ("edge/trade-log.csv", trade_log_path),
    ]
    strategy_files = _strategy_source_files(candidate, promotion=promotion)
    if candidate.edge_report_path is not None:
        files.append(("edge/edge-validation.md", candidate.edge_report_path))
    files.extend(
        [
            ("runtime/strategy.yaml", branch_spec_path(candidate.branch)),
            ("runtime/dependencies.json", dependencies_path(candidate.branch)),
            ("runtime/data_manifest.json", data_manifest_path(candidate.branch)),
        ]
    )

    files = strategy_files + files
    if promotion is not None:
        for item in promotion.packaged_files:
            if any(existing_path == item.artifact_path for existing_path, _ in files):
                continue
            files.append((item.artifact_path, item.source_path))
        files.append((f"edge/{PROMOTION_GATE_FILENAME}", promotion.gate_path))
        if promotion.patch_path is not None:
            files.append((f"edge/{PROMOTION_PATCH_FILENAME}", promotion.patch_path))
        if promotion.mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT:
            if promotion.contract_report_path is None:
                raise RuntimeError("agent_paper_contract promotion is missing contract evidence")
            files.append(
                (
                    f"edge/{PROMOTION_CONTRACT_REPORT_FILENAME}",
                    promotion.contract_report_path,
                )
            )
        for artifact_path, source_path in sorted(promotion.extra_source_map.items()):
            if any(existing_path == artifact_path for existing_path, _ in files):
                continue
            files.append((artifact_path, source_path))
    seen_paths: set[str] = set()
    for artifact_path, source_path in files:
        if artifact_path in seen_paths:
            raise RuntimeError(f"duplicate strategy artifact path: {artifact_path}")
        seen_paths.add(artifact_path)
        if not source_path.is_file():
            raise RuntimeError(
                f"strategy artifact source file is missing for {artifact_path}: {source_path}"
            )
    return files


def _strategy_source_files(
    candidate: StrategyArtifactCandidate,
    *,
    promotion: PromotionResult | None = None,
) -> list[tuple[str, Path]]:
    strategy_source_path = (
        promotion.strategy_source_path if promotion is not None else candidate.strategy_source_path
    )
    files = [(STRATEGY_ARTIFACT_ENTRYPOINT, strategy_source_path)]
    packaged_branch_sources = _packaged_branch_sources(candidate, promotion=promotion)
    for source_path in sorted(path for path in candidate.branch.rglob("*") if path.is_file()):
        if source_path == candidate.strategy_source_path:
            continue
        relative = source_path.relative_to(candidate.branch)
        if source_path.resolve() in packaged_branch_sources:
            continue
        if _is_denylisted_strategy_source(relative):
            continue
        files.append((f"strategy/{relative.as_posix()}", source_path))
    return files


def _is_runtime_initial_state_file(artifact_path: str) -> bool:
    return str(artifact_path or "").startswith("runtime/initial-state/")


def _packaged_branch_sources(
    candidate: StrategyArtifactCandidate,
    *,
    promotion: PromotionResult | None,
) -> set[Path]:
    if promotion is None:
        return set()
    branch_root = candidate.branch.resolve()
    sources: set[Path] = set()
    for item in promotion.packaged_files:
        try:
            source = item.source_path.resolve()
            source.relative_to(branch_root)
        except ValueError:
            continue
        sources.add(source)
    return sources


def _is_denylisted_strategy_source(relative: Path) -> bool:
    if any(part in DENYLISTED_STRATEGY_PARTS for part in relative.parts):
        return True
    if relative.name in DENYLISTED_STRATEGY_FILENAMES:
        return True
    if relative.suffix in DENYLISTED_STRATEGY_SUFFIXES:
        return True
    if relative.name == "branch.yaml":
        return True
    return relative.suffix not in STRATEGY_EXTRA_FILE_SUFFIXES


def _artifact_file_entry(*, artifact_path: str, source_path: Path) -> dict[str, Any]:
    return {
        "path": artifact_path,
        "sha256": _sha256_file(source_path),
        "bytes": source_path.stat().st_size,
    }


def _target_asset(candidate: StrategyArtifactCandidate, branch_spec: dict[str, Any]) -> str:
    return _clean(
        branch_spec.get("target") or branch_spec.get("target_asset") or candidate.ticker
    ).upper()


def _runtime_timeframe(branch_spec: dict[str, Any]) -> str:
    data_requirements = branch_spec.get("data_requirements")
    if isinstance(data_requirements, dict):
        timeframe = _clean(data_requirements.get("timeframe"))
        if timeframe:
            return timeframe
    return "1d"


def _required_timestamptz(value: Any, *, field_name: str) -> str:
    normalized = _clean(value)
    if not normalized:
        raise RuntimeError(f"{field_name} is required")
    return _as_utc_iso(normalized)


def _as_utc_iso(value: str) -> str:
    normalized = value.strip()
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        return f"{normalized}T00:00:00Z"
    parseable = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError:
        return normalized
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_float(value: Any, *, field_name: str) -> float:
    parsed = _to_float(value)
    if parsed is None:
        raise RuntimeError(f"{field_name} is required")
    return parsed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "unknown"


def _resolve_session_relative_path(session: Path, value: str | None) -> Path | None:
    raw = _clean(value)
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return None
    resolved = (session / path).resolve()
    try:
        resolved.relative_to(session)
    except ValueError:
        return None
    return resolved


def _existing_optional_path(session: Path, value: str | None) -> Path | None:
    path = _resolve_session_relative_path(session, value)
    if path is None or not path.is_file():
        return None
    return path


def _existing_optional_file(path: Path) -> Path | None:
    return path if path.is_file() else None


def _manifest_backtest_metrics(
    candidate: StrategyArtifactCandidate,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sharpe": _required_float(
            metrics.get("sharpe"),
            field_name="metrics.sharpe",
        ),
        "loAdjusted": _required_float(
            metrics.get("lo_adjusted", metrics.get("lo_adj")),
            field_name="metrics.lo_adjusted",
        ),
        "maxDrawdown": _required_float(
            metrics.get("max_dd", metrics.get("max_drawdown")),
            field_name="metrics.max_dd",
        ),
        "totalReturn": _required_float(
            metrics.get("total_return"),
            field_name="metrics.total_return",
        ),
        "calmar": _required_float(
            metrics.get("calmar"),
            field_name="metrics.calmar",
        ),
    }
    _set_optional_float(payload, "annualReturn", _to_float(metrics.get("annual_return")))
    score = _clean(candidate.score) or _clean(candidate.edge_result.get("score"))
    if score:
        payload["score"] = score
    _set_optional_artifact_metric(
        payload,
        "positionIc",
        _metric(candidate.row, metrics, row_key="ic", result_key="position_ic"),
        applicable=metrics.get("position_ic_applicable") is not False,
    )
    _set_optional_artifact_metric(
        payload,
        "positionIcStability",
        _to_float(metrics.get("position_ic_stability")),
        applicable=metrics.get("position_ic_stability_applicable") is not False,
    )
    _set_optional_artifact_metric(
        payload,
        "positionHitRate",
        _to_float(metrics.get("position_hit_rate")),
        applicable=metrics.get("position_ic_applicable") is not False,
    )
    _set_optional_artifact_metric(
        payload,
        "omega",
        _metric(candidate.row, metrics, row_key="omega", result_key="omega"),
        applicable=metrics.get("omega_applicable") is not False,
    )
    _set_optional_float(payload, "dsr", _to_float(metrics.get("dsr")))
    _set_optional_artifact_metric(
        payload,
        "lossYears",
        _to_int(metrics.get("loss_years")),
        applicable=metrics.get("loss_years_applicable") is not False,
    )
    _set_optional_int(
        payload,
        "k",
        _first_not_none(
            _to_int(candidate.row.get("K")),
            _to_int(candidate.edge_result.get("K")),
        ),
    )
    return payload


def _latest_decision_from_frame(candidate: StrategyArtifactCandidate) -> dict[str, Any] | None:
    result_ref = _clean(candidate.row.get("result_path"))
    if not result_ref:
        return None
    frame_path = _frame_path_for_result_ref(candidate.session, result_ref)
    if frame_path is None or not frame_path.exists():
        return None
    with frame_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    latest = rows[-1]
    previous = rows[-2] if len(rows) > 1 else {}
    previous_position = _to_float(previous.get("position"))
    previous_position_for_action = previous_position if previous_position is not None else 0.0
    position = _to_float(latest.get("position")) or 0.0
    next_position = _to_float(latest.get("next_position")) or 0.0
    trading_date = _date_text(latest.get("date"))
    close = _to_float(latest.get("close"))
    if close is None:
        close = _latest_close_from_edge_result(candidate.edge_result, trading_date=trading_date)
    return {
        "tradingDate": trading_date,
        "previousPosition": previous_position,
        "currentPosition": position,
        "position": position,
        "nextPosition": next_position,
        "delta": round(next_position - previous_position_for_action, 10),
        "action": _position_action(previous_position_for_action, next_position),
        "close": close,
        "source": "abel_invest_edge_frame_csv",
    }


def _frame_path_for_result_ref(session: Path, result_ref: str) -> Path | None:
    result_path = _resolve_session_relative_path(session, result_ref)
    if result_path is None:
        return None
    name = result_path.name
    if not name.endswith("-edge-result.json"):
        return None
    return result_path.with_name(name.replace("-edge-result.json", "-edge-frame.csv"))


def _position_action(previous_position: float, next_position: float) -> str:
    if previous_position == 0 and next_position > 0:
        return "buy/open_long"
    if next_position == 0 and previous_position > 0:
        return "sell/close"
    if next_position > previous_position:
        return "increase"
    if next_position < previous_position:
        return "reduce"
    return "hold"


def _date_text(value: Any) -> str:
    text = _clean(value)
    if "T" in text:
        return text.split("T", 1)[0]
    return text.split(" ", 1)[0]


def _latest_close_from_edge_result(
    edge_result: dict[str, Any],
    *,
    trading_date: str,
) -> float | None:
    preview = edge_result.get("decision_preview")
    if not isinstance(preview, list):
        return None
    for item in reversed(preview):
        if not isinstance(item, dict):
            continue
        if _date_text(item.get("date")) != trading_date:
            continue
        return _to_float(item.get("target_close"))
    return None


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _metric(
    row: dict[str, str],
    metrics: dict[str, Any],
    *,
    row_key: str,
    result_key: str,
) -> float | None:
    row_value = _to_float(row.get(row_key))
    if row_value is not None:
        return row_value
    return _to_float(metrics.get(result_key))


def _is_validation_verdict(value: Any) -> bool:
    return _clean(value).upper() in {"PASS", "FAIL"}


def _score_pass_rate(value: Any) -> float | None:
    text = _clean(value)
    if "/" not in text:
        return None
    passed, total = text.split("/", 1)
    passed_value = _to_float(passed)
    total_value = _to_float(total)
    if passed_value is None or total_value is None or total_value <= 0:
        return None
    return passed_value / total_value


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    parsed = _to_float(value)
    return None if parsed is None else int(parsed)


def _set_optional_float(payload: dict[str, Any], key: str, value: float | None) -> None:
    if value is not None:
        payload[key] = value


def _set_optional_artifact_metric(
    payload: dict[str, Any],
    key: str,
    value: Any,
    *,
    applicable: bool,
) -> None:
    if not applicable:
        payload[key] = None
        return
    if value is not None:
        payload[key] = value


def _set_optional_int(payload: dict[str, Any], key: str, value: int | None) -> None:
    if value is not None:
        payload[key] = value


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _clean(value: Any) -> str:
    return str(value or "").strip()
