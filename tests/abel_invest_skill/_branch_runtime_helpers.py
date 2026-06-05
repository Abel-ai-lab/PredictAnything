from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from abel_invest.narrative_core import session_lifecycle
from abel_invest.narrative_core.evidence import graph_frontier
from . import api as ni


def _sample_discovery() -> dict:
    return {
        "ticker": "TSLA",
        "source": "abel_live",
        "parents": [{"ticker": "AAPL"}, {"ticker": "MSFT"}],
        "blanket_new": [],
        "children": [],
        "K_discovery": 2,
        "backtest": {"start": "2020-01-01"},
    }


def _sample_readiness() -> dict:
    return {
        "results": [
            {
                "ticker": "TSLA",
                "status": "full",
                "usable": True,
                "covers_requested_start": True,
            },
            {
                "ticker": "AAPL",
                "status": "full",
                "usable": True,
                "covers_requested_start": True,
            },
            {
                "ticker": "MSFT",
                "status": "partial",
                "usable": True,
                "covers_requested_start": False,
            },
        ]
    }


def _write_runtime_files(branch: Path) -> None:
    ni.dependencies_path(branch).parent.mkdir(parents=True, exist_ok=True)
    ni.dependencies_path(branch).write_text(
        json.dumps(
            {
                "version": 1,
                "cache": {
                    "adapter": "abel",
                    "timeframe": "1d",
                    "profile": "daily",
                    "cache_root": "/tmp/cache",
                    "results": [
                        {
                            "symbol": "TSLA",
                            "ok": True,
                            "row_count": 120,
                            "available_range": {"start": "2020-01-01", "end": "2020-12-31"},
                        },
                        {
                            "symbol": "AAPL",
                            "ok": True,
                            "row_count": 120,
                            "available_range": {"start": "2020-01-01", "end": "2020-12-31"},
                        },
                        {
                            "symbol": "MSFT",
                            "ok": True,
                            "row_count": 90,
                            "available_range": {"start": "2020-03-01", "end": "2020-12-31"},
                        },
                    ],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ni.runtime_profile_path(branch).write_text(
        json.dumps(
            {
                "profile": "daily",
                "target": "TSLA",
                "decision_event": "bar_close",
                "execution_delay_bars": 2,
                "return_basis": "close_to_close",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ni.execution_constraints_path(branch).write_text(
        json.dumps({"long_only": False, "position_bounds": [-0.5, 0.5]}, indent=2),
        encoding="utf-8",
    )
    ni.data_manifest_path(branch).write_text(
        json.dumps(
            {
                "version": 1,
                "target": "TSLA",
                "selected_inputs": ["AAPL", "MSFT"],
                "feeds": [
                    {
                        "name": "primary",
                        "symbol": "TSLA",
                        "role": "target",
                        "adapter": "abel",
                        "timeframe": "1d",
                        "profile": "daily",
                        "cache_root": "/tmp/cache",
                    },
                    {
                        "name": "AAPL",
                        "symbol": "AAPL",
                        "role": "driver",
                        "adapter": "abel",
                        "timeframe": "1d",
                        "profile": "daily",
                        "cache_root": "/tmp/cache",
                    },
                    {
                        "name": "MSFT",
                        "symbol": "MSFT",
                        "role": "driver",
                        "adapter": "abel",
                        "timeframe": "1d",
                        "profile": "daily",
                        "cache_root": "/tmp/cache",
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ni.probe_samples_path(branch).write_text(
        json.dumps(
            {
                "version": 1,
                "target": "TSLA",
                "requested_start": "2020-01-01",
                "sample_decision_dates": ["2020-01-01", "2020-06-17", "2020-12-31"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ni.context_guide_path(branch).write_text(
        "# TSLA Branch Context Guide\n\n- use `ctx.target.series(\"close\")`\n",
        encoding="utf-8",
    )


def _edge_result(
    *,
    traced_inputs: list[str] | None = None,
    verdict: str = "PASS",
    sharpe: float = 1.2,
    metric_failures: list[dict] | None = None,
    k: int = 1,
    current_round_trials: int = 1,
    prior_effective_trials: int = 0,
) -> dict:
    return {
        "verdict": verdict,
        "score": "7/7" if verdict == "PASS" else "3/7",
        "failures": [item.get("message", "") for item in (metric_failures or []) if item.get("message")],
        "warnings": [],
        "profile": "equity_daily",
        "K": k,
        "metrics": {
            "sharpe": sharpe,
            "lo_adjusted": 1.5,
            "position_ic": 0.02,
            "omega": 1.3,
            "total_return": 0.22,
            "max_dd": -0.08,
            "dsr_trials_used": k,
        },
        "K_detail": {
            "source": "alpha_context",
            "engine_ast_k": 1,
            "tickers": [],
            "lags": [],
            "n_tickers": 0,
            "n_lags": 0,
            "declared_dsr_trials": {
                "count": k,
                "source": "abel-invest.session/v1",
                "method": "session_effective_exploration_trials_v1",
                "scope": "ticker_session_requested_window",
                "components": {
                    "prior_effective_trials": prior_effective_trials,
                    "current_round_trials": current_round_trials,
                },
            },
        },
        "requested_window": {"start": "2020-01-01", "end": None},
        "effective_window": {"start": "2020-01-01", "end": "2020-12-31"},
        "diagnostics": {
            "failure_signature": "healthy_signal",
            "runtime_stage": "validation",
            "signal": {"active_days": 120, "total_days": 252},
            "hints": [],
            "metric_failures": metric_failures or [],
        },
        "runtime_facts": {
            "contract": "abel-edge.runtime-facts/v1",
            "verdict": verdict,
            "semantic_verdict": "PASS",
            "runtime_stage": "validation",
            "workflow_status": "evaluation_completed",
            "read_summary": {
                "target_reads": ["primary"],
                "auxiliary_reads": traced_inputs or [],
                "read_count": 3,
                "decision_count": 120,
            },
            "metric_failures": metric_failures or [],
            "prepared_inputs": {
                "selected_inputs": ["AAPL", "MSFT"],
                "traced_inputs": traced_inputs or [],
                "effective_window": {"start": "2020-01-01", "end": "2020-12-31"},
                "issues": [],
            },
            "temporal_visibility": {"issue_kinds": [], "has_error": False},
        },
        "semantic": {
            "verdict": "PASS",
            "read_count": 3,
            "prepared_inputs": {
                "selected_inputs": ["AAPL", "MSFT"],
                "traced_inputs": traced_inputs or [],
                "effective_window": {"start": "2020-01-01", "end": "2020-12-31"},
                "issues": [],
            },
        },
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _record_synthetic_round(
    session: Path,
    branch: Path,
    *,
    spec: dict,
    result: dict,
    round_id: str = "round-001",
    decision: str = "keep",
    mode: str = "explore",
    changed_dimensions: list[str] | None = None,
    result_path_override: str | None = None,
) -> None:
    ni.write_branch_spec(branch, spec)
    metrics = result.get("metrics", {})
    outputs = branch / "outputs"
    outputs.mkdir(exist_ok=True)
    result_path = outputs / f"{round_id}-edge-result.json"
    report_path = outputs / f"{round_id}-edge-validation.md"
    handoff_path = outputs / f"{round_id}-edge-handoff.json"
    context_path = outputs / f"{round_id}-alpha-context.json"
    context_path.write_text(json.dumps({"branch_spec": spec}, indent=2), encoding="utf-8")
    if result_path_override is None:
        result_path.write_text(json.dumps(result), encoding="utf-8")
    report_path.write_text("# validation\n", encoding="utf-8")
    handoff_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    result_rel = result_path_override or str(result_path.relative_to(session))
    (branch / "rounds" / f"{round_id}.md").write_text(
        ni.render_round_note(
            ticker="TSLA",
            exp_id=session.name,
            branch_id=branch.name,
            round_id=round_id,
            mode=mode,
            decision=decision,
            description="synthetic evidence run",
            result=result,
            backtest_start="2020-01-01",
            input_note="",
            hypothesis=spec.get("hypothesis", ""),
            expected_signal="",
            trigger="test",
            change_summary="test",
            changed_dimensions=changed_dimensions or [],
            time_spent_min="1",
            summary="",
            next_step="",
            actions=[],
            context_mode="injected",
            context_path=str(context_path.relative_to(session)),
            result_path=result_rel,
            report_path=str(report_path.relative_to(session)),
            handoff_path=str(handoff_path.relative_to(session)),
        ),
        encoding="utf-8",
    )
    ni.append_tsv_row(
        branch / "results.tsv",
        ni.RESULTS_HEADER,
        {
            "exp_id": session.name,
            "ticker": "TSLA",
            "branch_id": branch.name,
                "round_id": round_id,
                "decision": decision,
            "lo_adj": "1.500",
            "ic": "0.0200",
            "omega": "1.300",
            "sharpe": f"{float(metrics.get('sharpe', 0)):.3f}",
            "max_dd": "-0.0800",
            "pnl": "22.0",
            "K": "1",
            "score": result.get("score", "7/7"),
            "verdict": result.get("verdict", "PASS"),
            "mode": mode,
            "description": "synthetic evidence run",
            "result_path": result_rel,
            "report_path": str(report_path.relative_to(session)),
            "handoff_path": str(handoff_path.relative_to(session)),
        },
    )


def _complete_candidate_spec(
    branch: Path,
    *,
    selected_inputs: list[str] | None = None,
    mechanism_family: str = "driver_momentum",
    model_family: str = "rule_signal",
    complexity_class: str = "simple_signal",
    exploration_role: str = "candidate",
) -> dict:
    selected = selected_inputs or ["AAPL"]
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": f"{', '.join(selected)} driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": mechanism_family,
            "model_family": model_family,
            "complexity_class": complexity_class,
            "exploration_role": exploration_role,
            "invalidation_condition": "Driver reads disappear or validation fails repeatedly.",
            "requested_start": "2020-01-01",
            "selected_inputs": selected,
        }
    )
    return spec



__all__ = [
    'json',
    'subprocess',
    'sys',
    'Namespace',
    'Path',
    'session_lifecycle',
    'graph_frontier',
    'ni',
    '_sample_discovery',
    '_sample_readiness',
    '_write_runtime_files',
    '_edge_result',
    '_read_jsonl',
    '_record_synthetic_round',
    '_complete_candidate_spec',
]
