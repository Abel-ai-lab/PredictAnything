from __future__ import annotations

import ast
import json
import subprocess
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from . import api as ni
from abel_invest.narrative_core import promotion as promotion_helpers



def _candidate_result_payload() -> dict:
    return {
        "verdict": "PASS",
        "score": "7/7",
        "failures": [],
        "warnings": [],
        "profile": "equity_daily",
        "implementation_contract": "decision_context",
        "K": 1,
        "metrics": {
            "sharpe": 2.1,
            "lo_adjusted": 2.4,
            "position_ic": 0.03,
            "position_ic_stability": 0.61,
            "position_hit_rate": 0.58,
            "omega": 1.5,
            "total_return": 0.42,
            "annual_return": 0.42,
            "calmar": 3.28,
            "dsr": 0.44,
            "loss_years": 1,
            "max_dd": -0.08,
        },
        "decision_preview": [
            {"date": "2020-12-31", "target_close": 17.06},
        ],
        "requested_window": {"start": "2020-01-01", "end": None},
        "effective_window": {"start": "2020-01-01", "end": "2020-12-31"},
        "diagnostics": {
            "failure_signature": "clean_pass",
            "runtime_stage": "validation",
            "signal": {"active_days": 120, "total_days": 252},
            "hints": [],
        },
        "runtime_facts": {
            "contract": "abel-edge.runtime-facts/v1",
            "verdict": "PASS",
            "semantic_verdict": "PASS",
            "runtime_stage": "validation",
            "workflow_status": "evaluation_completed",
            "read_summary": {
                "target_reads": ["primary"],
                "auxiliary_reads": ["AAPL"],
                "read_count": 3,
                "decision_count": 120,
            },
            "prepared_inputs": {
                "selected_inputs": ["AAPL"],
                "traced_inputs": ["AAPL"],
                "effective_window": {"start": "2020-01-01", "end": "2020-12-31"},
                "issues": [],
            },
            "temporal_visibility": {"issue_kinds": [], "has_error": False},
        },
    }


def _paper_design(
    *,
    min_bars: int | None = 1,
    uses_state: bool = False,
    uses_ordinal: bool = False,
    cutover_state_required: bool = False,
) -> dict:
    return {
        "history": {
            "boundary": "fixed_lookback",
            "minBars": min_bars,
            "origin": "2020-01-01" if uses_ordinal or cutover_state_required else None,
            "feeds": ["TSLA"],
            "reason": "test strategy needs a bounded paper history declaration",
        },
        "state": {
            "usesPersistentState": uses_state,
            "stateFiles": ["strategy/paper_state.json"] if uses_state else [],
            "reason": "test state declaration",
        },
        "calendar": {
            "usesAbsoluteDecisionOrdinal": uses_ordinal,
            "origin": "2020-01-01" if uses_ordinal else None,
            "reason": "test calendar declaration",
        },
        "cutover": {
            "requiresStartupState": cutover_state_required,
            "mode": "minimal_cutover_state" if cutover_state_required else "none",
            "dataHistoryStart": "2020-01-01" if cutover_state_required else None,
            "stateEnd": "2020-12-31" if cutover_state_required else None,
            "bootstrapHook": (
                "build_paper_initial_state" if cutover_state_required else None
            ),
            "reason": "test cutover declaration",
        },
        "dailyStep": {
            "reason": "test daily step declaration",
        },
    }


def _paper_continuation(method: str = "stateless_recompute") -> dict:
    return {
        "method": method,
        "reason": "test continuation preserves research decision semantics",
        "futureDailyFlow": "test future as_of flow",
    }


def _paper_evidence() -> dict:
    return {
        "observations": ["test source reading observation"],
        "agentOverrides": [],
        "semanticChecks": ["test cutover state semantic check"],
        "whySufficient": "test evidence supports the continuation method",
    }


def _paper_signal(
    *,
    design: dict | None = None,
    method: str = "stateless_recompute",
    live_readiness: str = "continuing paper signal from bounded live history",
) -> dict:
    return {
        "implemented": True,
        "incrementalReady": True,
        "continuation": _paper_continuation(method),
        "design": design if design is not None else _paper_design(),
        "evidence": _paper_evidence(),
        "liveReadiness": live_readiness,
    }


def _source_edit(reason: str) -> dict:
    return {
        "changed": True,
        "reason": reason,
        "paths": ["engine.py"],
    }


def _seed_promoted_stateless_paper_artifact(
    destination: Path,
    *,
    next_position: float = 1.0,
) -> None:
    promoted_dir = destination / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    (promoted_dir / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        f"        return ctx.decisions({next_position!r})\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        f"        return {{'next_position': {next_position!r}, 'date': str(as_of)}}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Test fixture already has hosted paper fast path.",
                "scope": "hosted_paper_contract",
                "sourceEdit": {
                    "changed": True,
                    "reason": "source_bug_fix",
                    "paths": ["engine.py"],
                },
                "paths": {"packagedFiles": [], "initialStateFiles": []},
                "paperSignal": _paper_signal(),
                "limitations": [],
                "replacements": [],
            }
        ),
        encoding="utf-8",
    )


def _write_strategy_result_row(
    session: Path,
    branch: Path,
    *,
    round_id: str,
    verdict: str,
    sharpe: float,
    lo_adj: float,
    max_dd: float,
    score: str = "9/9",
    calmar: float = 3.28,
    annual_return: float = 0.42,
    decision: str = "keep",
) -> None:
    result_path = branch / "outputs" / f"{round_id}-edge-result.json"
    report_path = branch / "outputs" / f"{round_id}-edge-validation.md"
    handoff_path = branch / "outputs" / f"{round_id}-edge-handoff.json"
    payload = _candidate_result_payload()
    payload["verdict"] = verdict
    payload["metrics"]["sharpe"] = sharpe
    payload["metrics"]["lo_adjusted"] = lo_adj
    payload["metrics"]["max_dd"] = max_dd
    payload["metrics"]["calmar"] = calmar
    payload["metrics"]["annual_return"] = annual_return
    payload["score"] = score
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    report_path.write_text("# validation\n", encoding="utf-8")
    handoff_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    ni.append_tsv_row(
        branch / "results.tsv",
        ni.RESULTS_HEADER,
        {
            "exp_id": session.name,
            "ticker": "TSLA",
            "branch_id": branch.name,
            "round_id": round_id,
            "decision": decision,
            "lo_adj": f"{lo_adj:.3f}",
            "ic": "0.0300",
            "omega": "1.500",
            "sharpe": f"{sharpe:.3f}",
            "max_dd": f"{max_dd:.4f}",
            "pnl": "42.0",
            "K": "1",
            "score": score,
            "verdict": verdict,
            "mode": "explore",
            "description": f"{branch.name} {round_id}",
            "result_path": str(result_path.relative_to(session)),
            "report_path": str(report_path.relative_to(session)),
            "handoff_path": str(handoff_path.relative_to(session)),
        },
    )

def _write_strategy_artifact_inputs(
    branch: Path,
    *,
    target: str = "TSLA",
    selected_inputs: list[str] | None = None,
) -> Path:
    selected_inputs = selected_inputs or ["AAPL", "MSFT"]
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "target": target,
            "target_node": f"{target}.price",
            "selected_inputs": selected_inputs,
            "data_requirements": {"timeframe": "1d", "fields": ["close"]},
        }
    )
    ni.write_branch_spec(branch, spec)
    (branch / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (branch / "__pycache__").mkdir(exist_ok=True)
    (branch / "__pycache__" / "helper.pyc").write_bytes(b"denylisted")

    inputs_dir = ni.dependencies_path(branch).parent
    inputs_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = inputs_dir / "market-cache"
    cache_results = []
    for idx, symbol in enumerate([target, *selected_inputs], start=1):
        feed_path = cache_dir / f"{symbol}.csv"
        _write_prepared_market_feed(feed_path, symbol=symbol, offset=idx)
        cache_results.append(
            {
                "symbol": symbol,
                "ok": True,
                "row_count": 4,
                "available_range": {"start": "2020-01-01", "end": "2020-01-04"},
                "data_path": str(feed_path),
            }
        )

    dependencies = {
        "version": 1,
        "branch_id": branch.name,
        "target": target,
        "target_node": f"{target}.price",
        "selected_inputs": selected_inputs,
        "selected_graph_nodes": [f"{ticker}.price" for ticker in selected_inputs],
        "requested_start": "2020-01-01",
        "data_requirements": {"timeframe": "1d"},
        "cache": {
            "adapter": "test-cache",
            "timeframe": "1d",
            "profile": "daily",
            "results": cache_results,
        },
    }
    ni.dependencies_path(branch).write_text(json.dumps(dependencies), encoding="utf-8")
    ni.runtime_profile_path(branch).write_text(
        json.dumps(ni.build_runtime_profile_payload(target=target)),
        encoding="utf-8",
    )
    data_manifest = {
        "version": 1,
        "target": target,
        "target_node": f"{target}.price",
        "selected_inputs": selected_inputs,
        "selected_graph_nodes": [f"{ticker}.price" for ticker in selected_inputs],
        "feeds": [],
    }
    ni.data_manifest_path(branch).write_text(json.dumps(data_manifest), encoding="utf-8")
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        return ctx.decisions(1)\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )

    trade_log_path = branch / "outputs" / "round-006-trade-log.csv"
    trade_log_path.parent.mkdir(parents=True, exist_ok=True)
    trade_log_path.write_text(
        "date,asset_return,pnl,position,cum_return,source,next_position\n"
        "2020-01-01,0,0,0,0,backtest,0\n"
        "2020-01-02,0.01,0.01,1,0.01,backtest,1\n",
        encoding="utf-8",
    )
    return trade_log_path


def _write_prepared_market_feed(path: Path, *, symbol: str, offset: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["timestamp,symbol,open,high,low,close,volume"]
    for idx in range(4):
        close = 100 + offset + idx
        day = idx + 1
        lines.append(
            f"2020-01-{day:02d}T00:00:00Z,{symbol},{close},{close},{close},{close},1000"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_metric_input(branch: Path, *, round_id: str) -> Path:
    metric_input_path = branch / "outputs" / f"{round_id}-metric-input.csv"
    metric_input_path.parent.mkdir(parents=True, exist_ok=True)
    metric_input_path.write_text(
        "date,asset_return,pnl,position,gross_pnl,turnover,execution_cost,next_position\n"
        "2020-01-01,0,0,0,0,0,0,0\n"
        "2020-01-02,0.01,0.01,1,0.01,1,0,1\n",
        encoding="utf-8",
    )
    return metric_input_path


def _fake_evaluate_command(command) -> subprocess.CompletedProcess | None:
    if "evaluate" not in command:
        return None
    result_path = Path(command[command.index("--output-json") + 1])
    metric_input_path = Path(command[command.index("--output-csv") + 1])
    report_path = Path(command[command.index("--output-md") + 1])
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(_candidate_result_payload()), encoding="utf-8")
    metric_input_path.write_text(
        "date,asset_return,pnl,position,gross_pnl,turnover,execution_cost,next_position\n"
        "2020-01-01,0,0,0,0,0,0,0\n"
        "2020-01-02,0.01,0.01,1,0.01,1,0,1\n",
        encoding="utf-8",
    )
    report_path.write_text("# replay validation\n", encoding="utf-8")
    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _fake_artifact_export_runner(command, cwd=None, capture_output=None, text=None, env=None):
    evaluated = _fake_evaluate_command(command)
    if evaluated is not None:
        return evaluated
    if "-c" in command:
        trade_log_path = Path(command[-1])
        trade_log_path.write_text(
            "date,asset_return,pnl,position,cum_return,source,next_position\n"
            "2020-01-01,0,0,0,0,backfill,0\n"
            "2020-01-02,0,0,1,0,backfill,1\n"
            "2020-01-03,0,0,1,0,backfill,1\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
            stderr="",
        )
    if "export-artifact" in command:
        artifact_path = Path(command[command.index("--output-zip") + 1])
        artifact_path.write_bytes(b"artifact zip")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "artifactSha256": "abc123",
                    "artifactBytes": artifact_path.stat().st_size,
                    "fileCount": 10,
                }
            ),
            stderr="",
        )
    raise AssertionError(f"unexpected command: {command}")



__all__ = [
    'ast',
    'json',
    'subprocess',
    'Namespace',
    'datetime',
    'timedelta',
    'timezone',
    'Path',
    'pytest',
    'ni',
    'promotion_helpers',
    '_candidate_result_payload',
    '_paper_design',
    '_paper_continuation',
    '_paper_evidence',
    '_paper_signal',
    '_source_edit',
    '_seed_promoted_stateless_paper_artifact',
    '_write_strategy_result_row',
    '_write_strategy_artifact_inputs',
    '_write_prepared_market_feed',
    '_write_metric_input',
    '_fake_evaluate_command',
    '_fake_artifact_export_runner',
]
