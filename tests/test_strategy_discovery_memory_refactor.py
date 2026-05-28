from __future__ import annotations

import ast
import json
import subprocess
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import strategy_discovery_api as ni
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
            "boundary": "state_only" if cutover_state_required else "fixed_lookback",
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
            "2020-01-02,0,0,1,0,backfill,1\n",
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


def test_render_writes_agent_context_with_exploration_path_view(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")

    assert (session / ni.EVIDENCE_LEDGER_FILENAME).exists()
    assert (session / ni.FRONTIER_MARKDOWN_FILENAME).exists()
    assert (session / ni.AGENT_CONTEXT_FILENAME).exists()
    assert not (branch / "memory.md").exists()
    assert not (session / "views").exists()

    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")
    assert "## Evidence Frontier" in context_text
    assert "## Exploration Path" in context_text
    assert "## Research Journal" not in context_text
    assert "## Input Realization" in context_text


def test_run_branch_round_updates_ledger_and_agent_context(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v3", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")

    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "No AAPL reads or negative holdout IC.",
            "selected_inputs": ["AAPL"],
        }
    )
    ni.write_branch_spec(branch, spec)
    engine_path = branch / "engine.py"
    engine_path.write_text(
        engine_path.read_text(encoding="utf-8")
        + "\n# Branch-specific implementation marker for evidence admission.\n",
        encoding="utf-8",
    )

    deps_path = ni.dependencies_path(branch)
    deps_path.parent.mkdir(parents=True, exist_ok=True)
    dependencies = {
        "version": 1,
        "branch_id": branch.name,
        "target": "TSLA",
        "selected_inputs": ["AAPL"],
        "requested_start": "2020-01-01",
        "cache": {
            "adapter": "abel",
            "timeframe": "1d",
            "profile": "daily",
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
            ],
        },
    }
    deps_path.write_text(json.dumps(dependencies), encoding="utf-8")
    runtime_profile = ni.build_runtime_profile_payload(target="TSLA")
    execution_constraints = ni.build_execution_constraints_payload(ni.load_branch_spec(branch))
    data_manifest = ni.build_data_manifest_payload(
        target="TSLA",
        selected_inputs=["AAPL"],
        cache_payload=dependencies["cache"],
        readiness={},
    )
    probe_samples = ni.build_probe_samples_payload(
        target="TSLA",
        requested_start="2020-01-01",
        data_manifest=data_manifest,
    )
    ni.runtime_profile_path(branch).write_text(json.dumps(runtime_profile), encoding="utf-8")
    ni.execution_constraints_path(branch).write_text(json.dumps(execution_constraints), encoding="utf-8")
    ni.data_manifest_path(branch).write_text(json.dumps(data_manifest), encoding="utf-8")
    ni.probe_samples_path(branch).write_text(json.dumps(probe_samples), encoding="utf-8")
    ni.context_guide_path(branch).write_text(
        ni.build_context_guide_markdown(
            target="TSLA",
            runtime_profile=runtime_profile,
            execution_constraints=execution_constraints,
            data_manifest=data_manifest,
        ),
        encoding="utf-8",
    )

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None, check=False, input=None):
        if "evaluate" in command:
            result_path = Path(command[command.index("--output-json") + 1])
            report_path = Path(command[command.index("--output-md") + 1])
            handoff_path = Path(command[command.index("--output-handoff") + 1])
            frame_path = Path(command[command.index("--output-csv") + 1])
            payload = {
                "verdict": "PASS",
                "score": "7/7",
                "failures": [],
                "warnings": [],
                "profile": "equity_daily",
                "K": 1,
                "metrics": {
                    "sharpe": 2.1,
                    "lo_adjusted": 2.4,
                    "position_ic": 0.03,
                    "omega": 1.5,
                    "total_return": 0.42,
                    "max_dd": -0.08,
                },
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
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            report_path.write_text("# validation\n", encoding="utf-8")
            handoff_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
            if "--output-csv" in command:
                frame_path = Path(command[command.index("--output-csv") + 1])
                frame_path.write_text(
                    "date,asset_return,pnl,position,gross_pnl,turnover,"
                    "execution_cost,next_position,close\n"
                    "2026-04-30,0.01,0.01,0.25,0.01,0.25,0.0,0.50,101.0\n"
                    "2026-05-01,0.02,0.02,0.50,0.02,0.25,0.0,0.75,102.0\n",
                    encoding="utf-8",
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)
    expected_experiment = {
        "protocol_id": "alpha-exec-sandbox-v1",
        "experiment_mode": "causal",
        "round_budget": "10",
        "abel_skills_commit": "skills-sha-123",
        "abel_edge_commit": "edge-sha-456",
    }
    monkeypatch.setenv("ABEL_EXPERIMENT_PROTOCOL_ID", expected_experiment["protocol_id"])
    monkeypatch.setenv("ABEL_EXPERIMENT_MODE", expected_experiment["experiment_mode"])
    monkeypatch.setenv("ABEL_EXPERIMENT_ROUND_BUDGET", expected_experiment["round_budget"])
    monkeypatch.setenv("ABEL_SKILLS_COMMIT", expected_experiment["abel_skills_commit"])
    monkeypatch.setenv("ABEL_EDGE_COMMIT", expected_experiment["abel_edge_commit"])

    ni.run_branch_round(
        Namespace(
            branch=str(branch),
            mode="explore",
            description="causal driver vote",
            input_note="",
            hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
            expected_signal="",
            trigger="graph discovery seed",
            change_summary="first causal pass",
            time_spent_min="15",
            summary="",
            next_step="",
            action=[],
            python_bin=None,
        )
    )
    round_output = capsys.readouterr().out
    assert "From here:" in round_output
    assert "exploration_path.md" in round_output
    assert "before another recorded round" in round_output

    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    context = json.loads((branch / "outputs" / "round-001-alpha-context.json").read_text(encoding="utf-8"))
    assert context["experiment"] == expected_experiment
    assert ledger["experiment"] == expected_experiment
    assert ledger["rows"][-1]["experiment"] == expected_experiment
    assert ledger["rows"][-1]["evidence_label"] == "candidate_causal_evidence"
    assert "candidate_causal_evidence" in (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    ni.print_status(session)
    status_output = capsys.readouterr().out
    assert "Session visualization available:" not in status_output
    assert "Ask the user whether to create an online view of this session." not in status_output
    assert "create it and share the returned link" not in status_output
    assert "abel-invest visualize-session --session" not in status_output
    assert "--base-url" not in status_output
    assert "Exploration path:" in status_output
    assert "Agent memory:" not in status_output
    assert ni.check_session(session, strict=False) == 0
    assert ni.check_session(session, strict=True) == 1
    assert ni.path_coverage_warning_lines(session) == []


def test_build_skill_dashboard_bundle_uses_current_evidence_surfaces(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dashboard", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")
    ni.write_branch_state(branch, {"created_at": "2026-04-24T01:00:00+00:00"})
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "No AAPL reads or negative holdout IC.",
            "selected_inputs": ["AAPL"],
        }
    )
    ni.write_branch_spec(branch, spec)

    result_path = branch / "outputs" / "round-001-edge-result.json"
    report_path = branch / "outputs" / "round-001-edge-validation.md"
    handoff_path = branch / "outputs" / "round-001-edge-handoff.json"
    result_path.write_text(json.dumps(_candidate_result_payload()), encoding="utf-8")
    report_path.write_text("# validation\n", encoding="utf-8")
    handoff_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    round_note = branch / "rounds" / "round-001.md"
    round_note.write_text(
        "\n".join(
            [
                "# round-001",
                "- candidate_note: `AAPL driver strength leads TSLA next-day risk appetite.`",
                "- expected_signal: `positive cross-asset lead`",
                "- changed_dimensions: `drivers`",
                "- summary: `candidate evidence round`",
                "- next_step: `inspect dashboard bundle`",
                f"- result_path: `{result_path.relative_to(session)}`",
                f"- report_path: `{report_path.relative_to(session)}`",
                f"- handoff_path: `{handoff_path.relative_to(session)}`",
            ]
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
            "round_id": "round-001",
            "decision": "keep",
            "lo_adj": "2.400",
            "ic": "0.0300",
            "omega": "1.500",
            "sharpe": "2.100",
            "max_dd": "-0.0800",
            "pnl": "42.0",
            "K": "1",
            "score": "7/7",
            "verdict": "PASS",
            "mode": "explore",
            "description": "causal driver vote",
            "result_path": str(result_path.relative_to(session)),
            "report_path": str(report_path.relative_to(session)),
            "handoff_path": str(handoff_path.relative_to(session)),
        },
    )
    ni.append_tsv_row(
        session / "events.tsv",
        ni.EVENTS_HEADER,
        {
            "timestamp": "2026-04-24T01:05:00+00:00",
            "event": "round_recorded",
            "branch_id": branch.name,
            "round_id": "round-001",
            "mode": "explore",
            "verdict": "PASS",
            "decision": "keep",
            "description": "causal driver vote",
            "artifact_path": str(result_path.relative_to(session)),
        },
    )
    ni.render_session(session)
    (session / "exploration_path.md").write_text(
        "# Exploration Path\n\n"
        "## Entries\n\n"
        "### graph-v1 round-001\n\n"
        "- ledger: `ledger:graph-v1:round-001`\n"
        "- path: causal driver vote\n"
        "- why: Driver concentration matters more than raw parent count.\n",
        encoding="utf-8",
    )

    bundle = ni.build_skill_dashboard_bundle(
        branch,
        uploaded_at="2026-04-24T01:30:00+00:00",
    )

    assert bundle["sessionId"] == "tsla-dashboard"
    assert bundle["branchId"] == "graph-v1"
    assert bundle["startAt"] == "2026-04-24T01:00:00+00:00"
    assert bundle["endAt"] == "2026-04-24T01:30:00+00:00"
    assert set(bundle["payload"]) == {
        "session",
        "branch",
        "rounds",
        "branchInsights",
        "episodes",
    }
    assert bundle["payload"]["branch"]["selectedInputs"] == ["AAPL"]
    assert bundle["payload"]["branch"]["latestEvidenceLabel"] == "candidate_causal_evidence"
    assert bundle["payload"]["session"]["inputRealization"] == {
        "declared_graph_supported_rounds": 1,
        "realized_graph_supported_rounds": 1,
        "graph_input_read_gap_count": 0,
        "graph_input_read_gap_rows": [],
    }
    assert bundle["payload"]["session"]["pathCoverage"] == {
        "recorded_round_count": 1,
        "covered_round_count": 1,
        "path_coverage_complete": True,
        "missing_path_rounds": [],
    }
    assert bundle["payload"]["rounds"][0]["roundId"] == "round-001"
    assert bundle["payload"]["rounds"][0]["branchId"] == "graph-v1"
    assert bundle["payload"]["rounds"][0]["branchRoundIndex"] == 1
    assert bundle["payload"]["rounds"][0]["sessionRoundIndex"] == 1
    assert bundle["payload"]["rounds"][0]["evidenceLabel"] == "candidate_causal_evidence"
    assert bundle["payload"]["rounds"][0]["inputRealization"]["realized_input_claim"] == "graph_supported"
    assert any(
        "Driver concentration matters" in item["summary"]
        for item in bundle["payload"]["branchInsights"]
    )
    assert "replaySnapshot" not in bundle["payload"]
    assert "promotion" not in bundle["payload"]


def test_build_skill_dashboard_session_bundle_aggregates_branches_and_rounds(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-session-dashboard", tmp_path / "research")
    branch_a = ni.init_branch_dir(session, "graph-v1")
    branch_b = ni.init_branch_dir(session, "target-control")
    ni.write_branch_state(branch_a, {"created_at": "2026-04-24T01:00:00+00:00"})
    ni.write_branch_state(branch_b, {"created_at": "2026-04-24T01:10:00+00:00"})
    spec_a = ni.load_branch_spec(branch_a)
    spec_a.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "selected_inputs": ["AAPL"],
        }
    )
    ni.write_branch_spec(branch_a, spec_a)
    spec_b = ni.load_branch_spec(branch_b)
    spec_b.update(
        {
            "hypothesis": "TSLA target-only control branch.",
            "evidence_intent": "control",
            "input_claim": "target_only",
            "mechanism_family": "target_momentum",
            "selected_inputs": [],
        }
    )
    ni.write_branch_spec(branch_b, spec_b)
    for branch, round_id, verdict, decision in [
        (branch_a, "round-001", "FAIL", "discard"),
        (branch_b, "round-001", "PASS", "keep"),
    ]:
        ni.append_tsv_row(
            branch / "results.tsv",
            ni.RESULTS_HEADER,
            {
                "exp_id": session.name,
                "ticker": "TSLA",
                "branch_id": branch.name,
                "round_id": round_id,
                "decision": decision,
                "lo_adj": "",
                "ic": "",
                "omega": "",
                "sharpe": "",
                "max_dd": "",
                "pnl": "",
                "K": "",
                "score": "7/9",
                "verdict": verdict,
                "mode": "explore",
                "description": f"{branch.name} round",
                "result_path": "",
                "report_path": "",
                "handoff_path": "",
            },
        )
    for branch, round_id, verdict, decision in [
        (branch_b, "round-001", "PASS", "keep"),
        (branch_a, "round-001", "FAIL", "discard"),
    ]:
        ni.append_tsv_row(
            session / "events.tsv",
            ni.EVENTS_HEADER,
            {
                "timestamp": "2026-04-24T01:20:00+00:00",
                "event": "round_recorded",
                "branch_id": branch.name,
                "round_id": round_id,
                "mode": "explore",
                "verdict": verdict,
                "decision": decision,
                "description": f"{branch.name} round",
                "artifact_path": "",
            },
        )
    ni.render_session(session)
    uploaded_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    bundle = ni.build_skill_dashboard_session_bundle(
        session,
        uploaded_at=uploaded_at,
    )

    assert bundle["sessionId"] == "tsla-session-dashboard"
    assert "branchId" not in bundle
    assert bundle["payload"]["session"]["id"] == "tsla-session-dashboard"
    assert [branch["id"] for branch in bundle["payload"]["branches"]] == [
        "graph-v1",
        "target-control",
    ]
    assert [
        (branch["id"], branch["thesis"])
        for branch in bundle["payload"]["branches"]
    ] == [
        ("graph-v1", "AAPL driver strength leads TSLA next-day risk appetite."),
        ("target-control", "TSLA target-only control branch."),
    ]
    exploration_map = bundle["payload"]["explorationMap"]
    assert exploration_map["source"] == "local_session_evidence"
    assert exploration_map["confidence"] == "high"
    assert any(node["nodeId"] == "TSLA.price" for node in exploration_map["nodes"])
    assert any(node["nodeId"] == "AAPL.price" for node in exploration_map["nodes"])
    assert any(edge["edgeId"] == "AAPL.price->TSLA.price" for edge in exploration_map["edges"])
    assert [
        (route["branchId"], route["status"])
        for route in exploration_map["routes"]
    ] == [
        ("graph-v1", "discarded"),
        ("target-control", "kept"),
    ]
    assert [
        (
            round_item["branchId"],
            round_item["roundId"],
            round_item["sessionRoundIndex"],
            round_item["hypothesis"],
        )
        for round_item in bundle["payload"]["rounds"]
    ] == [
        ("target-control", "round-001", 1, "TSLA target-only control branch."),
        ("graph-v1", "round-001", 2, "AAPL driver strength leads TSLA next-day risk appetite."),
    ]


def test_build_skill_dashboard_session_bundle_omits_primary_strategy_and_trade_log(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dashboard", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")
    for round_id in ["round-001", "round-002"]:
        result_ref = f"branches/{branch.name}/outputs/{round_id}-edge-result.json"
        report_ref = f"branches/{branch.name}/outputs/{round_id}-edge-validation.md"
        result_path = session / result_ref
        frame_path = session / f"branches/{branch.name}/outputs/{round_id}-edge-frame.csv"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "decision_preview": [
                        {"date": "2026-05-04", "target_close": 16.13},
                        {"date": "2026-05-05", "target_close": 17.06},
                    ],
                    "metrics": {
                        "position_ic_stability": 0.6,
                        "dsr": 0.99,
                        "loss_years": 1,
                    },
                }
            ),
            encoding="utf-8",
        )
        frame_path.write_text(
            "date,pnl,position,next_position,close\n"
            "2026-05-04,0.01,0.75,0.30,16.13\n"
            "2026-05-05,0.02,0.30,0.60,\n",
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
                "decision": "keep",
                "lo_adj": "1.300",
                "ic": "0.0500",
                "omega": "1.700",
                "sharpe": "1.400",
                "max_dd": "-0.1000",
                "pnl": "55.0",
                "K": "3",
                "score": "9/9",
                "verdict": "PASS",
                "mode": "explore",
                "description": f"{branch.name} {round_id}",
                "result_path": result_ref,
                "report_path": report_ref,
                "handoff_path": f"branches/{branch.name}/outputs/{round_id}-edge-handoff.json",
            },
        )
        ni.append_tsv_row(
            session / "events.tsv",
            ni.EVENTS_HEADER,
            {
                "timestamp": "2026-04-24T01:20:00+00:00",
                "event": "round_recorded",
                "branch_id": branch.name,
                "round_id": round_id,
                "mode": "explore",
                "verdict": "PASS",
                "decision": "keep",
                "description": f"{branch.name} {round_id}",
                "artifact_path": result_ref,
            },
        )

    bundle = ni.build_skill_dashboard_session_bundle(
        session,
        uploaded_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )

    assert "primaryStrategy" not in bundle["payload"]
    assert not list(session.glob("branches/*/outputs/*-trade-log.csv"))


def test_post_skill_dashboard_bundle_sends_api_key_header() -> None:
    calls = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"code": 200, "data": {"bundleId": "bundle-1"}}'

    def fake_opener(request, timeout):
        calls.append((request, timeout))
        return _Response()

    result = ni.post_skill_dashboard_bundle(
        base_url="https://router.example",
        api_key="secret-key",
        bundle={"sessionId": "s1", "branchId": "b1", "payload": {"branch": {}}},
        opener=fake_opener,
    )

    request, timeout = calls[0]
    assert result["data"]["bundleId"] == "bundle-1"
    assert request.full_url == "https://router.example/web/skill-dashboard/bundles"
    assert request.get_header("Api-key") == "secret-key"
    assert request.get_header("Content-type") == "application/json"
    assert timeout == 60


def test_post_skill_dashboard_session_sends_to_session_endpoint() -> None:
    calls = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"code": 200, "data": {"sessionId": "s1"}}'

    def fake_opener(request, timeout):
        calls.append((request, timeout))
        return _Response()

    result = ni.post_skill_dashboard_session(
        base_url="https://router.example",
        api_key="secret-key",
        bundle={"sessionId": "s1", "payload": {"session": {}, "branches": [], "rounds": []}},
        opener=fake_opener,
    )

    request, timeout = calls[0]
    assert result["data"]["sessionId"] == "s1"
    assert request.full_url == "https://router.example/web/skill-dashboard/sessions"
    assert request.get_header("Api-key") == "secret-key"
    assert request.get_header("Content-type") == "application/json"
    assert timeout == 60


def test_select_best_pass_strategy_sorts_validation_rounds_by_sharpe_first(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    branch_a = ni.init_branch_dir(session, "driver_explore")
    branch_b = ni.init_branch_dir(session, "momentum_lead")
    branch_c = ni.init_branch_dir(session, "regime_switch")
    _write_strategy_result_row(
        session,
        branch_a,
        round_id="round-003",
        verdict="PASS",
        sharpe=0.674,
        lo_adj=0.695,
        max_dd=-0.1440,
        score="9/13",
        calmar=5.0,
    )
    _write_strategy_result_row(
        session,
        branch_b,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
        score="10/13",
        calmar=1.0,
    )
    _write_strategy_result_row(
        session,
        branch_b,
        round_id="round-010",
        verdict="PASS",
        sharpe=0.945,
        lo_adj=1.041,
        max_dd=-0.1340,
        score="13/13",
        calmar=9.0,
        decision="discard",
    )
    _write_strategy_result_row(
        session,
        branch_c,
        round_id="round-002",
        verdict="FAIL",
        sharpe=0.508,
        lo_adj=0.866,
        max_dd=-0.1805,
        score="11/13",
        calmar=0.5,
    )

    result = ni.select_best_pass_strategy(session)

    assert result.skip_reason == ""
    assert result.validation_round_count == 4
    assert result.pass_round_count == 4
    assert result.eligible_count == 4
    assert result.selected_branch_id == "momentum_lead"
    assert result.selected_round_id == "round-006"
    assert result.selected is not None
    assert result.selected.selection_rank == 1
    assert result.selected.selection_metric_values["sharpe"] == 0.967
    assert result.selected.selection_metric_values["annual_return"] == 0.42
    assert result.selected.selection_metric_values["max_dd_abs"] == 0.1278
    assert result.selected.selection_metric_values["pass_rate"] == 10 / 13


def test_select_best_pass_strategy_sorts_by_sharpe_return_drawdown_then_latest(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    lower_sharpe = ni.init_branch_dir(session, "lower_sharpe")
    lower_return = ni.init_branch_dir(session, "lower_return")
    worse_drawdown = ni.init_branch_dir(session, "worse_drawdown")
    earlier = ni.init_branch_dir(session, "earlier")
    later = ni.init_branch_dir(session, "later")
    for branch, sharpe, annual_return, max_dd in [
        (lower_sharpe, 1.1, 0.90, -0.05),
        (lower_return, 1.2, 0.20, -0.03),
        (worse_drawdown, 1.2, 0.30, -0.12),
        (earlier, 1.2, 0.30, -0.08),
        (later, 1.2, 0.30, -0.08),
    ]:
        _write_strategy_result_row(
            session,
            branch,
            round_id="round-001",
            verdict="PASS",
            sharpe=sharpe,
            lo_adj=1.0,
            max_dd=max_dd,
            score="9/13",
            annual_return=annual_return,
        )
        ni.append_tsv_row(
            session / "events.tsv",
            ni.EVENTS_HEADER,
            {
                "timestamp": "2026-04-24T01:20:00+00:00",
                "event": "round_recorded",
                "branch_id": branch.name,
                "round_id": "round-001",
                "mode": "explore",
                "verdict": "PASS",
                "decision": "keep",
                "description": branch.name,
                "artifact_path": (
                    f"branches/{branch.name}/outputs/round-001-edge-result.json"
                ),
            },
        )

    result = ni.select_best_pass_strategy(session)

    assert result.selected_branch_id == "later"
    assert result.selected is not None
    assert result.selected.session_round_index == 5


def test_select_best_pass_strategy_can_host_discarded_fail_validation_rounds(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("AAPL", "aapl-v1", tmp_path / "research")
    lower = ni.init_branch_dir(session, "lower_discarded_fail")
    higher = ni.init_branch_dir(session, "higher_discarded_fail")
    for index, (branch, sharpe, annual_return, max_dd) in enumerate(
        [
            (lower, 1.1, 0.10, -0.08),
            (higher, 1.4, 0.05, -0.12),
        ],
        start=1,
    ):
        _write_strategy_result_row(
            session,
            branch,
            round_id="round-001",
            verdict="FAIL",
            sharpe=sharpe,
            lo_adj=sharpe,
            max_dd=max_dd,
            score="7/9",
            annual_return=annual_return,
            decision="discard",
        )
        ni.append_tsv_row(
            session / "events.tsv",
            ni.EVENTS_HEADER,
            {
                "timestamp": f"2026-04-24T01:2{index}:00+00:00",
                "event": "round_recorded",
                "branch_id": branch.name,
                "round_id": "round-001",
                "mode": "explore",
                "verdict": "FAIL",
                "decision": "discard",
                "description": branch.name,
                "artifact_path": (
                    f"branches/{branch.name}/outputs/round-001-edge-result.json"
                ),
            },
        )

    result = ni.select_best_pass_strategy(session)

    assert result.skip_reason == ""
    assert result.validation_round_count == 2
    assert result.eligible_count == 2
    assert result.selected_branch_id == "higher_discarded_fail"
    assert result.selected_round_id == "round-001"
    assert result.selected is not None
    assert result.selected.decision == "discard"
    assert result.selected.selection_metric_values["sharpe"] == 1.4


def test_select_best_pass_strategy_returns_skip_when_no_validation(tmp_path: Path) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "regime_switch")
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-001",
        verdict="ERROR",
        sharpe=0.685,
        lo_adj=0.831,
        max_dd=-0.1654,
    )

    result = ni.select_best_pass_strategy(session)

    assert result.selected is None
    assert result.skip_reason == "no_validation_strategy"
    assert result.pass_round_count == 0
    assert result.eligible_count == 0


def test_select_best_pass_strategy_skips_unhostable_validation_rounds(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    ni.append_tsv_row(
        branch / "results.tsv",
        ni.RESULTS_HEADER,
        {
            "exp_id": session.name,
            "ticker": "MSFT",
            "branch_id": branch.name,
            "round_id": "round-001",
            "decision": "keep",
            "lo_adj": "1.000",
            "ic": "0.0300",
            "omega": "1.500",
            "sharpe": "1.000",
            "max_dd": "-0.1000",
            "pnl": "42.0",
            "K": "1",
            "score": "9/9",
            "verdict": "FAIL",
            "mode": "explore",
            "description": "missing result",
            "result_path": "branches/momentum_lead/outputs/missing-edge-result.json",
            "report_path": "",
            "handoff_path": "",
        },
    )

    result = ni.select_best_pass_strategy(session)

    assert result.selected is None
    assert result.skip_reason == "no_hostable_validation_strategy"
    assert result.pass_round_count == 1
    assert result.eligible_count == 0


def test_build_strategy_artifact_manifest_uses_router_contract_fields(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    trade_log_path = _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    (branch / "outputs" / "round-006-edge-frame.csv").write_text(
        "date,pnl,position,next_position,close\n"
        "2020-12-30,0.01,0.25,0.50,16.13\n"
        "2020-12-31,0.02,0.50,0.75,\n",
        encoding="utf-8",
    )

    selection = ni.select_best_pass_strategy(session)
    assert selection.selected is not None
    manifest = ni.build_strategy_artifact_manifest(
        selection.selected,
        trade_log_path=trade_log_path,
        created_at="2026-05-07T00:00:00Z",
        abel_edge_version="0.8.test",
        abel_invest_version="3.5.test",
    )

    assert manifest["schema"] == "abel-invest.strategy-artifact/v1"
    assert manifest["createdAt"] == "2026-05-07T00:00:00Z"
    assert manifest["source"] == {
        "workspaceKind": "abel-invest",
        "sourceSessionId": "tsla-v1",
        "ticker": "TSLA",
        "branchId": "momentum_lead",
        "roundId": "round-006",
        "selectionMode": "auto_best_validation_by_pass_rate",
        "selectionScope": "session",
        "selectionMetricOrder": ["pass_rate", "sharpe", "calmar", "max_dd"],
        "selectionMetricValues": {
            "lo_adjusted": 1.056,
            "annual_return": 0.42,
            "pass_rate": 1.0,
            "sharpe": 0.967,
            "calmar": 3.28,
            "max_dd": -0.1278,
            "max_dd_abs": 0.1278,
        },
        "selectionRank": 1,
    }
    assert manifest["runtime"] == {
        "profile": "equity_daily",
        "timeframe": "1d",
        "decisionEvent": "bar_close",
        "executionDelayBars": 1,
        "returnBasis": "close_to_close",
        "implementationContract": "decision_context",
        "abelEdgeVersion": "0.8.test",
        "abelInvestVersion": "3.5.test",
        "state": {
            "schema": "abel-invest.runtime-state/v1",
            "mode": "explicit_state_dir",
            "path": "state/",
            "bootstrap": {"mode": "none", "path": None},
        },
        "resultChannel": {"mode": "return_value_first"},
    }
    assert manifest["promotion"]["mode"] == "zero_change"
    assert manifest["promotion"]["gate"] == {
        "status": "passed",
        "evidencePath": None,
    }
    assert manifest["strategy"] == {
        "entrypoint": "strategy/strategy.py",
        "className": "BranchEngine",
        "targetAsset": "TSLA",
        "targetNode": "TSLA.price",
        "selectedInputs": ["AAPL", "MSFT"],
        "selectedGraphNodes": ["AAPL.price", "MSFT.price"],
        "paperMode": "paper_signal",
    }
    assert manifest["backtest"] == {
        "verdict": "PASS",
        "startAt": "2020-01-01T00:00:00Z",
        "endAt": "2020-12-31T00:00:00Z",
        "resultRef": "edge/edge-result.json",
        "reportRef": "edge/edge-validation.md",
        "latestDecision": {
            "tradingDate": "2020-12-31",
            "previousPosition": 0.25,
            "currentPosition": 0.5,
            "position": 0.5,
            "nextPosition": 0.75,
            "delta": 0.5,
            "action": "increase",
            "close": 17.06,
            "source": "abel_invest_edge_frame_csv",
        },
        "metrics": {
            "sharpe": 0.967,
            "loAdjusted": 1.056,
            "maxDrawdown": -0.1278,
            "totalReturn": 0.42,
            "calmar": 3.28,
            "annualReturn": 0.42,
            "score": "9/9",
            "positionIc": 0.03,
            "positionIcStability": 0.61,
            "positionHitRate": 0.58,
            "omega": 1.5,
            "dsr": 0.44,
            "lossYears": 1,
            "k": 1,
        },
    }
    file_paths = [item["path"] for item in manifest["files"]]
    assert file_paths == [
        "strategy/strategy.py",
        "strategy/helper.py",
        "edge/edge-result.json",
        "edge/trade-log.csv",
        "edge/edge-validation.md",
        "runtime/strategy.yaml",
        "runtime/dependencies.json",
        "runtime/data_manifest.json",
    ]
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    assert all(item["bytes"] > 0 for item in manifest["files"])


def test_build_strategy_artifact_manifest_requires_trade_log(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )

    selection = ni.select_best_pass_strategy(session)
    assert selection.selected is not None
    with pytest.raises(RuntimeError, match="edge/trade-log.csv"):
        ni.build_strategy_artifact_manifest(
            selection.selected,
            trade_log_path=branch / "outputs" / "missing-trade-log.csv",
        )


def test_export_selected_strategy_artifact_writes_local_bundle(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"
    _seed_promoted_stateless_paper_artifact(output_dir)

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                    "2020-01-01,0,0,0,0,backfill,0\n"
                    "2020-01-02,0,0,1,0,backfill,1\n",
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
                        "fileCount": 8,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    assert result["artifactUploadSkipped"] is False
    assert result["selectedBranchId"] == "momentum_lead"
    assert result["selectedRoundId"] == "round-006"
    assert result["artifactSha256"] == "abc123"
    assert Path(result["manifestPath"]).exists()
    assert Path(result["tradeLogPath"]).exists()
    assert Path(result["artifactPath"]).exists()
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert [item["path"] for item in manifest["files"]] == [
        "strategy/strategy.py",
        "strategy/helper.py",
        "edge/edge-result.json",
        "edge/trade-log.csv",
        "edge/edge-validation.md",
        "runtime/strategy.yaml",
        "runtime/dependencies.json",
        "runtime/data_manifest.json",
        "edge/promotion-gate.json",
        "edge/promotion.patch",
        "edge/paper-contract-report.json",
        "edge/promotion-tail-trace.json",
    ]
    assert (
        manifest["source"]["selectionMode"]
        == "auto_best_validation_by_pass_rate"
    )
    assert manifest["source"]["selectionScope"] == "session"
    assert manifest["promotion"]["mode"] == "agent_paper_contract"
    assert manifest["runtime"]["paperExecutionProfile"]["history"]["boundary"] == "fixed_lookback"
    assert manifest["runtime"]["paperExecutionProfile"]["history"]["lookbackBars"] == 1


def test_export_selected_strategy_artifact_nulls_inapplicable_metrics(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    result_path = branch / "outputs" / "round-006-edge-result.json"
    edge_result = json.loads(result_path.read_text(encoding="utf-8"))
    edge_result["metrics"].update(
        {
            "omega": 0.0,
            "omega_applicable": False,
            "position_ic": 0.0,
            "position_hit_rate": 0.0,
            "position_ic_applicable": False,
            "position_ic_stability": 0.0,
            "position_ic_monthly_mean": 0.0,
            "position_ic_stability_applicable": False,
            "loss_years": 0,
            "loss_years_applicable": False,
        }
    )
    result_path.write_text(json.dumps(edge_result), encoding="utf-8")
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"
    _seed_promoted_stateless_paper_artifact(output_dir)
    captured: dict[str, object] = {}

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                    "2020-01-01,0,0,0,0,backfill,0\n"
                    "2020-01-02,0,0,1,0,backfill,1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
                stderr="",
            )
        if "export-artifact" in command:
            edge_result_arg = Path(command[command.index("--edge-result") + 1])
            captured["edge_result_arg"] = edge_result_arg
            captured["edge_result"] = json.loads(edge_result_arg.read_text(encoding="utf-8"))
            artifact_path = Path(command[command.index("--output-zip") + 1])
            artifact_path.write_bytes(b"artifact zip")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "artifactSha256": "abc123",
                        "artifactBytes": artifact_path.stat().st_size,
                        "fileCount": 8,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    metrics = manifest["backtest"]["metrics"]
    assert metrics["positionIc"] is None
    assert metrics["positionIcStability"] is None
    assert metrics["positionHitRate"] is None
    assert metrics["omega"] is None
    assert metrics["lossYears"] is None
    assert Path(captured["edge_result_arg"]).name == "edge-result.artifact.json"
    artifact_edge_metrics = captured["edge_result"]["metrics"]
    assert artifact_edge_metrics["position_ic"] is None
    assert artifact_edge_metrics["position_ic_stability"] is None
    assert artifact_edge_metrics["position_hit_rate"] is None
    assert artifact_edge_metrics["position_ic_monthly_mean"] is None
    assert artifact_edge_metrics["omega"] is None
    assert artifact_edge_metrics["loss_years"] is None


def test_promote_branch_strategy_uses_explicit_branch_round(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-003",
        verdict="PASS",
        sharpe=0.850,
        lo_adj=0.910,
        max_dd=-0.1700,
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "promoted-artifact"
    _seed_promoted_stateless_paper_artifact(output_dir)

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,0,0,backfill,0\n"
                "2020-01-02,0,0,1,0,backfill,1\n",
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
                        "fileCount": 9,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    result = ni.promote_branch_strategy(
        branch,
        round_id="round-006",
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    assert result["selectedBranchId"] == "momentum_lead"
    assert result["selectedRoundId"] == "round-006"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["source"]["selectionMode"] == "explicit_branch_round"
    assert manifest["source"]["selectionScope"] == "branch"
    assert manifest["source"]["selectionMetricOrder"] == []
    assert manifest["promotion"]["gate"]["evidencePath"] == "edge/promotion-gate.json"


def test_promote_branch_strategy_requires_round_when_branch_has_multiple_passes(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-003",
        verdict="PASS",
        sharpe=0.850,
        lo_adj=0.910,
        max_dd=-0.1700,
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )

    result = ni.promote_branch_strategy(branch, python_bin="python-test")

    assert result["artifactExported"] is False
    assert result["skipReason"] == "ambiguous_branch_promotion_round"
    assert result["selectedBranchId"] == "momentum_lead"
    assert result["selectedRoundId"] is None


def test_export_selected_strategy_artifact_agent_packages_initial_state(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "stateful_model")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from pathlib import Path\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = Path(\"model/latest.joblib\")\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"
    commands_seen = []

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        commands_seen.append(command)
        evaluated = _fake_evaluate_command(command)
        if evaluated is not None:
            return evaluated
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,1,0,backfill,1\n"
                "2020-01-02,0,0,1,0,backfill,1\n"
                "2020-01-03,0,0,1,0,backfill,1\n"
                "2020-01-04,0,0,1,0,backfill,1\n",
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

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert first_result["artifactExported"] is False
    assert first_result["skipReason"] == "hosted_paper_contract_required"
    request_path = Path(first_result["promotionReport"]["requestPath"])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["kind"] == "hosted_paper_contract"
    assert any(signal["kind"] == "state_like_file" for signal in request["signals"])
    promoted_dir = request_path.parent
    (promoted_dir / "engine.py").write_text(
        "import json\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def _state_path(self):\n"
        "        return context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"strategy/model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'state_root': str(path.parent), 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent rewrote model access and packaged startup state.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": "model/latest.joblib",
                            "purpose": "model seed required by hosted paper signal",
                        }
                    ],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(
                        uses_state=True,
                        cutover_state_required=True,
                    ),
                ),
                "limitations": [],
                "replacements": [
                    {
                        "path": "model/latest.joblib",
                        "replacement": "ctx.state_dir / \"strategy/model/latest.joblib\"",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (promoted_dir / "dependency-scan.json").write_text("{}", encoding="utf-8")
    (promoted_dir / "packaging-plan.json").write_text("{}", encoding="utf-8")
    legacy_replay_dir = output_dir / "promotion-replay"
    legacy_replay_dir.mkdir()
    (legacy_replay_dir / "edge-result.json").write_text("{}", encoding="utf-8")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert result["promotionMode"] == "agent_paper_contract"
    assert manifest["runtime"]["state"]["bootstrap"] == {
        "mode": "copy_from_base",
        "path": "runtime/initial-state/",
    }
    assert manifest["promotion"]["mode"] == "agent_paper_contract"
    assert manifest["promotion"]["gate"] == {
        "status": "passed",
        "evidencePath": "edge/promotion-gate.json",
    }
    file_paths = [item["path"] for item in manifest["files"]]
    assert "runtime/initial-state/strategy/model/latest.joblib" in file_paths
    assert "runtime/initial-state/strategy/paper_state.json" in file_paths
    assert "edge/promotion-gate.json" in file_paths
    assert "edge/promotion.patch" in file_paths
    assert "edge/paper-contract-report.json" in file_paths
    promoted_engine = output_dir / "promoted" / "engine.py"
    assert 'ctx.state_dir / "strategy/model/latest.joblib"' in promoted_engine.read_text(
        encoding="utf-8"
    )
    export_command = next(command for command in commands_seen if "export-artifact" in command)
    assert "--extra-source-map" in export_command


def test_export_selected_strategy_artifact_requires_hosted_contract_for_runtime_state(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "runtime_state_without_intent")
    _write_strategy_artifact_inputs(branch)
    runtime_state = branch / ".abel-runtime" / "state" / "model" / "latest.json"
    runtime_state.parent.mkdir(parents=True)
    runtime_state.write_text(json.dumps({"model": "latest"}), encoding="utf-8")
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactUploadSkipped"] is True
    assert result["skipReason"] == "hosted_paper_contract_required"
    report = result["promotionReport"]
    assert report["mode"] == "hosted_paper_contract_required"
    assert "hosted paper contract required" in report["reason"]
    request = json.loads(Path(report["requestPath"]).read_text(encoding="utf-8"))
    assert request["kind"] == "hosted_paper_contract"
    assert request["scope"] == "hosted_paper_contract"
    assert any(signal["kind"] == "runtime_state_file" for signal in request["signals"])
    full_facts = json.loads(
        Path(request["factSidecars"]["fullFactsPath"]).read_text(encoding="utf-8")
    )
    assert any(
        item["kind"] == "runtime_state_file"
        for item in full_facts["stateDependencies"]
    )


def test_export_selected_strategy_artifact_requires_hosted_contract_for_ad_hoc_paths(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "ad_hoc_model_registry")
    _write_strategy_artifact_inputs(branch)
    (branch / "engine.py").write_text(
        "from pathlib import Path\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        registry = Path('models') / 'AAPL' / 'registry.json'\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactUploadSkipped"] is True
    request = json.loads(
        Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8")
    )
    assert request["kind"] == "hosted_paper_contract"
    assert any(signal["kind"] == "source_state_reference" for signal in request["signals"])


def test_export_selected_strategy_artifact_requires_hosted_contract_for_absolute_asset_path(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("ETHUSD", "eth-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "absolute_asset_path")
    _write_strategy_artifact_inputs(branch, target="ETHUSD")
    external_asset = tmp_path / "trading-internal" / "data" / "trade_log_dual_resonance.csv"
    external_asset.parent.mkdir(parents=True)
    external_asset.write_text("date,position\n2020-01-01,1\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "import pandas as pd\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        f"_LOG = \"{external_asset}\"\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        df = pd.read_csv(_LOG)\n"
        "        return ctx.decisions(float(df['position'].iloc[-1]))\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is False
    assert result["skipReason"] == "hosted_paper_contract_required"
    request = json.loads(
        Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8")
    )
    assert request["kind"] == "hosted_paper_contract"
    assert request["scope"] == "hosted_paper_contract"
    assert request["facts"]["strategyProfile"]["getPaperSignalImplemented"] is False
    assert any(
        signal["kind"] == "developer_local_absolute_path"
        for signal in request["signals"]
    )
    assert (Path(result["promotionReport"]["requestPath"]).parent / "engine.py").is_file()


def test_export_selected_strategy_artifact_agent_packages_external_base_asset(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("ETHUSD", "eth-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "agent_packaged_asset")
    _write_strategy_artifact_inputs(branch, target="ETHUSD")
    external_asset = tmp_path / "trading-internal" / "data" / "trade_log_dual_resonance.csv"
    external_asset.parent.mkdir(parents=True)
    external_asset.write_text("date,position\n2020-01-01,1\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "import pandas as pd\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        f"_LOG = \"{external_asset}\"\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        df = pd.read_csv(_LOG)\n"
        "        return ctx.decisions(float(df['position'].iloc[-1]))\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )
    request_path = Path(first_result["promotionReport"]["requestPath"])
    promoted_dir = request_path.parent
    (promoted_dir / "engine.py").write_text(
        "import pandas as pd\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        log_path = ctx.paths.base_strategy / \"assets/trade_log_dual_resonance.csv\"\n"
        "        df = pd.read_csv(log_path)\n"
        "        return ctx.decisions(float(df['position'].iloc[-1]))\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        date = str(as_of) if as_of is not None else 'not-run'\n"
        "        return {'next_position': 1.0, 'date': date}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent packaged external replay log as read-only base asset.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("asset_path_normalization"),
                "paths": {
                    "packagedFiles": [
                        {
                            "artifactPath": "strategy/assets/trade_log_dual_resonance.csv",
                            "sourcePath": str(external_asset),
                            "purpose": "read-only replay log used by the promoted strategy",
                        }
                    ],
                },
                "paperSignal": _paper_signal(
                    live_readiness="simple one-row paper signal for hosted smoke coverage",
                ),
                "limitations": [],
                "replacements": [
                    {
                        "path": "external replay log",
                        "replacement": (
                            "ctx.paths.base_strategy / "
                            "\"assets/trade_log_dual_resonance.csv\""
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (promoted_dir / "dependency-scan.json").write_text("{}", encoding="utf-8")
    (promoted_dir / "packaging-plan.json").write_text("{}", encoding="utf-8")
    legacy_replay_dir = output_dir / "promotion-replay"
    legacy_replay_dir.mkdir()
    (legacy_replay_dir / "edge-result.json").write_text("{}", encoding="utf-8")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is True
    assert result["promotionMode"] == "agent_paper_contract"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    file_paths = [item["path"] for item in manifest["files"]]
    assert "strategy/assets/trade_log_dual_resonance.csv" in file_paths
    assert "edge/paper-contract-report.json" in file_paths
    assert "edge/dependency-scan.json" not in file_paths
    assert "edge/packaging-plan.json" not in file_paths
    assert not (promoted_dir / "dependency-scan.json").exists()
    assert not (promoted_dir / "packaging-plan.json").exists()
    assert not legacy_replay_dir.exists()
    gate = json.loads((output_dir / "promotion-gate.json").read_text(encoding="utf-8"))
    paper_gate = next(item for item in gate["gates"] if item["name"] == "paper_dry_run")
    assert paper_gate["method"] == "edge_paper_run_one_tail_smoke"
    assert paper_gate["details"]["smoke"]["nextPosition"] == 1.0
    assert paper_gate["details"]["smoke"]["tailConsistency"]["status"] == "passed"
    assert paper_gate["details"]["smoke"]["tailConsistency"]["sampleSize"] == 1
    promoted_source = (output_dir / "promoted" / "engine.py").read_text(encoding="utf-8")
    assert str(external_asset) not in promoted_source
    artifact_report = json.loads(
        (output_dir / "promoted" / "paper-contract-report.artifact.json").read_text(
            encoding="utf-8"
        )
    )
    assert str(external_asset) not in json.dumps(artifact_report)
    artifact_packaged_file = artifact_report["paths"]["packagedFiles"][0]
    assert "sourcePath" not in artifact_packaged_file


def test_export_selected_strategy_artifact_requires_hosted_contract_for_nonstandard_import(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("GNRC", "gnrc-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "ml_walk_forward")
    _write_strategy_artifact_inputs(branch, target="GNRC", selected_inputs=["RTX"])
    (branch / "engine.py").write_text(
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        _ = RandomForestClassifier(n_estimators=2)\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is False
    assert result["skipReason"] == "hosted_paper_contract_required"
    request = json.loads(
        Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8")
    )
    assert request["kind"] == "hosted_paper_contract"
    assert any(signal["kind"] == "nonstandard_import" for signal in request["signals"])
    full_facts = json.loads(
        Path(request["factSidecars"]["fullFactsPath"]).read_text(encoding="utf-8")
    )
    imports = full_facts["imports"]
    assert {"module": "sklearn", "classification": "nonstandard"} in imports


def test_export_selected_strategy_artifact_agent_adds_stateful_paper_signal(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("GNRC", "gnrc-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "agent_stateful_ml")
    _write_strategy_artifact_inputs(branch, target="GNRC", selected_inputs=["RTX"])
    (branch / "engine.py").write_text(
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        _ = RandomForestClassifier(n_estimators=2)\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )
    promoted_dir = Path(first_result["promotionReport"]["requestPath"]).parent
    (promoted_dir / "engine.py").write_text(
        "import json\n"
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def _state_path(self):\n"
        "        return context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "    def compute_decisions(self, ctx):\n"
        "        _ = RandomForestClassifier(n_estimators=2)\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of), 'state_root': str(path.parent)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent added stateful paper signal entrypoint.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(uses_state=True, cutover_state_required=True),
                    live_readiness="uses runtime state path and returns scalar audit fields",
                ),
                "limitations": [],
                "replacements": [],
            }
        ),
        encoding="utf-8",
    )

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is True
    assert result["promotionMode"] == "agent_paper_contract"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    file_paths = [item["path"] for item in manifest["files"]]
    assert "runtime/initial-state/strategy/paper_state.json" in file_paths
    assert "edge/paper-contract-report.json" in file_paths


def test_export_selected_strategy_artifact_ignores_legacy_state_intent(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "legacy_state_intent")
    _write_strategy_artifact_inputs(branch)
    runtime_state = branch / ".abel-runtime" / "state" / "model" / "debug.json"
    runtime_state.parent.mkdir(parents=True)
    runtime_state.write_text(json.dumps({"debug": True}), encoding="utf-8")
    (branch / "state_intent.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.state-intent/v1",
                "selfCheck": {
                    "status": "no_durable_state",
                    "summary": "debug state is not required for paper startup",
                },
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is False
    assert result["skipReason"] == "hosted_paper_contract_required"
    request = json.loads(
        Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8")
    )
    assert request["kind"] == "hosted_paper_contract"
    assert "stateIntentPath" not in request
    assert "requiredStateIntentTemplate" not in request


def test_export_selected_strategy_artifact_normalizes_relative_python_bin(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    commands_seen = []

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        commands_seen.append(command)
        assert Path(command[0]).is_absolute()
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,0,0,backfill,0\n"
                "2020-01-02,0,0,1,0,backfill,1\n",
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
                        "fileCount": 9,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin=".venv/bin/python",
        runner=fake_runner,
    )

    assert commands_seen[0][0] == str((Path.cwd() / ".venv/bin/python").absolute())


def test_export_selected_strategy_artifact_rejects_full_compute_paper_signal(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "full_compute_paper_signal")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from pathlib import Path\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = Path(\"model/latest.joblib\")\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "evaluate" in command:
            raise AssertionError("promotion must not full-replay the strategy")
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,0,0,backfill,0\n"
                "2020-01-02,0,0,1,0,backfill,1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert first_result["artifactExported"] is False
    request_path = Path(first_result["promotionReport"]["requestPath"])
    promoted_dir = request_path.parent
    (promoted_dir / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"strategy/model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        compiled = self.compute_runtime_output(end=as_of)\n"
        "        return {'next_position': float(compiled.next_position[-1])}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent rewrote state path for hosted paper.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": "model/latest.joblib",
                            "purpose": "model seed required for hosted paper",
                        }
                    ],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(
                        uses_state=True,
                        cutover_state_required=True,
                    ),
                ),
                "limitations": [],
                "replacements": [],
            }
        ),
        encoding="utf-8",
    )

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is False
    assert result["skipReason"] == "hosted_paper_contract_required"
    assert "gatePath" in result["promotionReport"]
    gate = json.loads(Path(result["promotionReport"]["gatePath"]).read_text(encoding="utf-8"))
    paper_gate = next(item for item in gate["gates"] if item["name"] == "paper_dry_run")
    assert paper_gate["method"] == "paper_signal_contract_static"
    assert "compute_runtime_output" in paper_gate["details"]["reason"]


def test_export_selected_strategy_artifact_rejects_tail_signal_mismatch(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "tail_signal_mismatch")
    _write_strategy_artifact_inputs(branch)
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        return ctx.decisions(0)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,0,0,backfill,0\n"
                "2020-01-02,0,0,0,0,backfill,0\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
                stderr="",
            )
        if "export-artifact" in command:
            raise AssertionError("tail mismatch must block artifact export")
        raise AssertionError(f"unexpected command: {command}")

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )
    promoted_dir = Path(first_result["promotionReport"]["requestPath"]).parent
    (promoted_dir / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        return ctx.decisions(0)\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent added a paper signal that drifts from oracle.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("source_bug_fix"),
                "paths": {"packagedFiles": []},
                "paperSignal": _paper_signal(
                    live_readiness="intentionally mismatched for gate coverage",
                ),
                "limitations": [],
                "replacements": [],
            }
        ),
        encoding="utf-8",
    )

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is False
    assert result["promotionMode"] == "hosted_paper_contract_required"
    gate = json.loads(Path(result["promotionReport"]["gatePath"]).read_text(encoding="utf-8"))
    paper_gate = next(item for item in gate["gates"] if item["name"] == "paper_dry_run")
    assert paper_gate["status"] == "failed"
    assert paper_gate["method"] == "edge_paper_run_one_tail_smoke"
    assert "diverged" in paper_gate["details"]["reason"]
    tail_summary = paper_gate["details"]["smoke"]["tailConsistency"]
    assert "comparisons" not in tail_summary
    assert tail_summary["mismatchCount"] == 1
    assert tail_summary["firstMismatch"]["expectedNextPosition"] == 0.0
    assert tail_summary["firstMismatch"]["actualNextPosition"] == 1.0
    trace_path = Path(result["promotionReport"]["gatePath"]).with_name(
        "promotion-tail-trace.json"
    )
    assert trace_path.is_file()
    request = json.loads(Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8"))
    assert request["signals"][-1]["kind"] == "promotion_gate_failed"
    assert request["validation"]["lastGateFailure"]["failedGates"][0]["name"] == "paper_dry_run"
    request_tail = request["validation"]["lastGateFailure"]["failedGates"][0]["smoke"][
        "tailConsistency"
    ]
    assert request_tail["status"] == "failed"
    assert "comparisons" not in request_tail
    assert request_tail["firstMismatch"]["asOf"] == "2020-01-02"
    assert request_tail["firstMismatch"]["expectedNextPosition"] == 0.0
    assert request_tail["firstMismatch"]["actualNextPosition"] == 1.0
    assert request_tail["tracePath"] == "edge/promotion-tail-trace.json"
    assert request_tail["selectedRoundCutoverEnd"] == "2020-12-31"
    assert request_tail["firstMismatchIsSelectedRoundEnd"] is False
    assert "stateEnd" in " ".join(request_tail["immutableContractFacts"])


def test_export_selected_strategy_artifact_records_slow_training_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setitem(
        promotion_helpers._run_edge_paper_run_one_smoke.__globals__,
        "PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS",
        0.0,
    )
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "training_without_warm_start")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model = type('Model', (), {'fit': lambda self: None})()\n"
        "        model.fit()\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,1,0,backfill,1\n"
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
                        "fileCount": 12,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )
    promoted_dir = Path(first_result["promotionReport"]["requestPath"]).parent
    (promoted_dir / "engine.py").write_text(
        "import json\n"
        "import time\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model = type('Model', (), {'fit': lambda self: None})()\n"
        "        model.fit()\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        time.sleep(0.001)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of), 'state_root': str(path.parent)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent added a matching but cold-start paper signal.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": "model/latest.joblib",
                            "purpose": "latest fitted model checkpoint seed",
                        }
                    ],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(
                        uses_state=True,
                        cutover_state_required=True,
                    ),
                    live_readiness="tail output matches but no reusable warm-start state",
                ),
                "limitations": [],
                "replacements": [],
            }
        ),
        encoding="utf-8",
    )

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    assert result["promotionMode"] == "agent_paper_contract"
    gate = json.loads((output_dir / "promotion-gate.json").read_text(encoding="utf-8"))
    paper_gate = next(item for item in gate["gates"] if item["name"] == "paper_dry_run")
    assert paper_gate["status"] == "passed"
    warm_start = paper_gate["details"]["smoke"]["warmStart"]
    assert warm_start["slowDistinctCallCount"] >= 2
    assert warm_start["sampleSize"] == 2


def test_contract_report_rejects_same_source_as_asset_and_initial_state(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    source = branch / "trade-log.csv"
    source.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {
        "paths": {
            "packagedFiles": [
                {
                    "artifactPath": "strategy/assets/trade-log.csv",
                    "sourcePath": "trade-log.csv",
                    "purpose": "read-only replay input",
                }
            ],
            "initialStateFiles": [
                {
                    "artifactPath": "runtime/initial-state/strategy/trade-log.csv",
                    "sourcePath": "trade-log.csv",
                    "purpose": "incorrect duplicate state seed",
                }
            ],
        }
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="both immutable strategy asset and mutable initial state seed",
    ):
        promotion_helpers._report_packaged_files(
            report,
            branch=branch,
            is_denylisted_source=lambda path: False,
        )


def test_contract_report_rejects_research_evidence_as_live_asset(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    evidence = branch / "promotions" / "round-001" / "trade-log.csv"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="strategy/assets/trade-log.csv",
            source_path=evidence,
            purpose="selected round trade log",
            role="base_asset",
        ),
    )

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="generated research evidence",
    ):
        promotion_helpers._validate_packaged_research_evidence_sources(
            packaged,
            branch=branch,
            report=report,
        )


def test_contract_report_rejects_temp_generated_asset_as_live_asset(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    generated = tmp_path / "tmp" / "hosted-paper" / "next_positions.csv"
    generated.parent.mkdir(parents=True)
    generated.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="strategy/assets/next_positions.csv",
            source_path=generated,
            purpose="derived selected-round lookup",
            role="base_asset",
        ),
    )

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="generated research evidence",
    ):
        promotion_helpers._validate_packaged_research_evidence_sources(
            packaged,
            branch=branch,
            report=report,
        )


def test_contract_report_rejects_export_trade_log_as_live_asset(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    destination = tmp_path / "paper-ready-artifact"
    destination.mkdir()
    generated = destination / "trade-log.csv"
    generated.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="strategy/assets/trade-log.csv",
            source_path=generated,
            purpose="dated paper replay source",
            role="base_asset",
        ),
    )

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="generated research evidence or export output",
    ):
        promotion_helpers._validate_packaged_research_evidence_sources(
            packaged,
            branch=branch,
            destination=destination,
            report=report,
        )


def test_contract_report_allows_external_trade_log_named_asset(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    destination = tmp_path / "paper-ready-artifact"
    destination.mkdir()
    external = tmp_path / "trading-internal" / "data" / "trade-log.csv"
    external.parent.mkdir(parents=True)
    external.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="strategy/assets/trade-log.csv",
            source_path=external,
            purpose="original external signal dependency",
            role="base_asset",
        ),
    )

    promotion_helpers._validate_packaged_research_evidence_sources(
        packaged,
        branch=branch,
        destination=destination,
        report=report,
    )


def test_contract_report_rejects_oracle_answers_as_initial_state(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    state = branch / "runtime" / "initial-state" / "strategy" / "paper-seed.json"
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps(
            {
                "schema": "paper-seed/v1",
                "seed_source": "selected_round_tail_override",
                "tail_overrides": {"2026-05-18": 0.0},
            }
        ),
        encoding="utf-8",
    )
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="runtime/initial-state/strategy/paper-seed.json",
            source_path=state,
            purpose="startup cursor seed",
            role="initial_state",
        ),
    )

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="validation oracle answers",
    ):
        promotion_helpers._validate_packaged_research_evidence_sources(
            packaged,
            branch=branch,
            report=report,
        )


def test_contract_report_allows_strategy_owned_initial_state(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    state = branch / "runtime" / "initial-state" / "strategy" / "paper-state.json"
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps(
            {
                "schema": "paper-state/v1",
                "calendar_origin": "2023-03-08",
                "last_model_refit_ordinal": 800,
                "state_end": "2026-05-18",
            }
        ),
        encoding="utf-8",
    )
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="runtime/initial-state/strategy/paper-state.json",
            source_path=state,
            purpose="strategy-owned cutover metadata",
            role="initial_state",
        ),
    )

    promotion_helpers._validate_packaged_research_evidence_sources(
        packaged,
        branch=branch,
        report=report,
    )


def test_contract_report_rejects_incremental_ready_contradiction() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": _paper_signal(
            live_readiness="finite replay after the packaged log returns neutral",
        ),
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="incrementalReady=true conflicts",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_allows_negated_replay_language() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": _paper_signal(
            design=_paper_design(uses_state=True),
            live_readiness=(
                "get_paper_signal reads live feeds and persisted state for future "
                "paper days; this is not a replay of research evidence."
            ),
        ),
        "limitations": [],
    }

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
    )


def test_contract_report_requires_paper_signal_design_contract() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "continuation": _paper_continuation(),
            "evidence": _paper_evidence(),
            "liveReadiness": "continuing paper signal from bounded live history",
        },
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="paperSignal.design",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_requires_continuation_contract() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "design": _paper_design(),
            "evidence": _paper_evidence(),
            "liveReadiness": "continuing paper signal from bounded live history",
        },
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="paperSignal.continuation",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_requires_evidence_contract() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "continuation": _paper_continuation(),
            "design": _paper_design(),
            "liveReadiness": "continuing paper signal from bounded live history",
        },
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="paperSignal.evidence",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_allows_stateless_without_get_paper_signal() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        close = ctx.target.series('close')\n"
        "        return ctx.decisions((close > close.shift(1)).fillna(0.0))\n"
    )
    report = {
        "paperSignal": _paper_signal(method="stateless_recompute"),
        "limitations": [],
    }

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
    )

    profile = promotion_helpers._report_paper_execution_profile(report)
    assert profile == {
        "schema": "abel.paper-execution-profile/v1",
        "history": {
            "boundary": "fixed_lookback",
            "lookbackBars": 1,
            "feeds": ["TSLA"],
            "reason": "test strategy needs a bounded paper history declaration",
        },
    }


def test_hosted_paper_request_is_actionable_for_training_like_source(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    promoted_dir = branch / "promoted"
    promoted_dir.mkdir(parents=True)
    source = promoted_dir / "engine.py"
    source.write_text("# promoted\n", encoding="utf-8")
    scan = {
        "sourceScan": {
            "positiveFindings": {"observedFitCalls": ["model.fit"]},
        },
        "paperSignal": {
            "implemented": False,
            "sourceTrainingCalls": ["model.fit"],
        },
        "backtestWindow": {
            "effectiveWindow": {"start": "2020-01-01", "end": "2020-12-31"}
        },
    }

    request_path = promotion_helpers._write_hosted_paper_contract_request(
        promoted_dir,
        branch=branch,
        source_path=source,
        dependency_scan=scan,
        signals=[
            {
                "kind": "missing_paper_signal",
                "value": "get_paper_signal",
                "reason": "missing",
            }
        ],
    )

    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert "workOrder" not in request
    assert "mission" not in request
    assert "runtimeApiFacts" not in request
    assert "reportContract" not in request
    assert "gateContract" not in request
    assert request["requirements"]["statefulContinuationRequired"] is True
    assert request["requirements"]["continuationMethod"] == "stateful_continuation"
    assert request["requirements"]["observedTrainingCalls"] == ["model.fit"]
    assert request["contractGuide"]["relativePath"] == "references/hosted-paper-contract.md"
    assert request["facts"]["strategyProfile"]["observedTrainingCalls"] == ["model.fit"]
    assert request["facts"]["sourceScan"]["observedFitCalls"] == [
        "model.fit"
    ]
    assert request["validation"]["attemptPolicy"]["liveContractFailures"] == 0
    assert "acceptanceCriteria" not in request
    assert "agentQuestions" not in request


def test_hosted_paper_request_opens_full_replay_fallback_after_failures(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    promoted_dir = branch / "promoted"
    promoted_dir.mkdir(parents=True)
    source = promoted_dir / "engine.py"
    source.write_text("# promoted\n", encoding="utf-8")
    scan = {
        "paperSignal": {"implemented": True},
        "backtestWindow": {
            "effectiveWindow": {"start": "2020-01-01", "end": "2020-12-31"}
        },
    }
    failure = {"status": "failed", "failedGates": [{"name": "paper_dry_run"}]}

    for _ in range(3):
        request_path = promotion_helpers._write_hosted_paper_contract_request(
            promoted_dir,
            branch=branch,
            source_path=source,
            dependency_scan=scan,
            signals=[],
            validation_failure=failure,
        )

    request = json.loads(request_path.read_text(encoding="utf-8"))
    policy = request["attemptPolicy"]
    assert policy["liveContractFailures"] == 3
    assert policy["fullReplayFallbackEligible"] is True
    assert policy["notHostableAllowed"] is True


def test_contract_report_rejects_full_replay_fallback_before_policy_allows() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    design = _paper_design()
    design["history"]["boundary"] = "full_replay"
    design["cutover"]["mode"] = "full_replay"
    report = {
        "paperSignal": _paper_signal(
            method="full_replay_fallback",
            design=design,
            live_readiness="continuing paper signal via fallback path under hosted limits",
        ),
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="fullReplayFallbackEligible=true",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
        full_replay_fallback_allowed=True,
    )

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
        full_replay_fallback_allowed=True,
        source_dependency_scan={
            "sourceScan": {"positiveFindings": {"observedFitCalls": ["model.fit"]}}
        },
    )


def test_training_scan_reports_observed_calls_without_false_trainy_match() -> None:
    source = (
        "class BranchEngine:\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        train_y = self.history['target']\n"
        "        if train_y.notna().any():\n"
        "            self.model.fit(self.features, train_y)\n"
        "        return {'next_position': 1.0}\n"
    )

    facts = promotion_helpers._paper_signal_design_facts(source)

    assert facts["trainingCalls"] == ["self.model.fit"]
    assert "train_y.notna" not in facts["sourceTrainingCalls"]


def test_contract_report_rejects_stateless_recompute_with_fit_in_signal_path() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        self.model.fit(self.features, self.target)\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": _paper_signal(method="stateless_recompute"),
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="stateless_recompute conflicts with observed ML training",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_rejects_stateless_override_for_fit_observation() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        self.model.fit(self.features, self.target)\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": _paper_signal(method="stateless_recompute"),
        "limitations": [],
    }
    report["paperSignal"]["evidence"]["agentOverrides"] = [
        {
            "scanObservation": "source contains self.model.fit in get_paper_signal",
            "agentFinding": (
                "the fit result is unused in the returned exposure and does not affect "
                "the paper signal"
            ),
        }
    ]

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="stateful_continuation",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_trade_log_oracle_facts_withhold_expected_values(tmp_path: Path) -> None:
    trade_log = tmp_path / "trade-log.csv"
    trade_log.write_text(
        "date,next_position\n"
        "2026-05-14,0\n"
        "2026-05-15,0.35\n"
        "2026-05-18,0\n",
        encoding="utf-8",
    )

    facts = promotion_helpers._trade_log_oracle_facts(trade_log)

    assert facts["tailSample"]
    assert facts["canonicalDecisionTimeline"]["first"]["decisionIndex"] == 0
    assert facts["canonicalDecisionTimeline"]["last"]["asOf"] == "2026-05-18"
    assert all("expectedNextPosition" not in item for item in facts["tailSample"])
    assert "withheld" in facts["diagnosticPolicy"]


def test_contract_report_allows_cutover_state_without_initial_state_files() -> None:
    source = (
        "import json\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paths": {"packagedFiles": [], "initialStateFiles": []},
        "paperSignal": _paper_signal(
            method="stateful_continuation",
            design=_paper_design(
                uses_state=True,
                cutover_state_required=True,
            ),
            live_readiness="continuing paper signal from startup state",
        ),
        "limitations": [],
    }

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
    )


def test_contract_report_rejects_cutover_state_before_selected_round_end() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    design = _paper_design(
        uses_state=True,
        cutover_state_required=True,
    )
    design["cutover"]["stateEnd"] = "2020-01-02"
    report = {
        "paths": {
            "initialStateFiles": [
                {
                    "artifactPath": "runtime/initial-state/strategy/paper-state.json",
                    "sourcePath": "paper-state.json",
                }
            ]
        },
        "paperSignal": _paper_signal(
            method="stateful_continuation",
            design=design,
            live_readiness="continuing paper signal from startup state",
        ),
        "limitations": [],
    }
    candidate = Namespace(edge_result={"effective_window": {"end": "2020-12-31"}})

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="selected round cutover end 2020-12-31",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
            candidate=candidate,
        )


def test_contract_report_rejects_full_replay_cutover_mode() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    design = _paper_design(
        uses_state=True,
        cutover_state_required=True,
    )
    design["cutover"]["mode"] = "full_replay"
    report = {
        "paths": {
            "initialStateFiles": [
                {
                    "artifactPath": "runtime/initial-state/strategy/paper-state.json",
                    "sourcePath": "paper-state.json",
                }
            ]
        },
        "paperSignal": _paper_signal(
            method="stateful_continuation",
            design=design,
            live_readiness="continuing paper signal from startup state",
        ),
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="full_replay",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_paper_smoke_bootstraps_state_before_holdout_tail(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "stateful_holdout")
    _write_strategy_artifact_inputs(branch)
    promoted_dir = branch / "promoted"
    promoted_dir.mkdir()
    seed_state = branch / "paper-state.json"
    seed_state.write_text("{}", encoding="utf-8")
    promoted_source = promoted_dir / "engine.py"
    promoted_source.write_text(
        "import json\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def _state_path(self):\n"
        "        from pathlib import Path\n"
        "        return Path(self.context['_runtime_paths']['state']) / 'strategy/paper-state.json'\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        state = {'cutover': str(cutover_as_of), 'seen': []}\n"
        "        path.write_text(json.dumps(state), encoding='utf-8')\n"
        "        return state\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = self._state_path()\n"
        "        state = json.loads(path.read_text(encoding='utf-8'))\n"
        "        if str(as_of) not in state['seen']:\n"
        "            state['seen'].append(str(as_of))\n"
        "            path.write_text(json.dumps(state), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    destination = tmp_path / "artifact"
    destination.mkdir()
    (destination / "trade-log.csv").write_text(
        "date,next_position\n"
        "2020-01-01,0\n"
        "2020-01-02,1\n"
        "2020-01-03,1\n"
        "2020-01-04,1\n",
        encoding="utf-8",
    )
    candidate = Namespace(
        branch=branch,
        strategy_source_path=branch / "engine.py",
        branch_id="stateful_holdout",
        ticker="TSLA",
        edge_result={"effective_window": {"end": "2020-01-04"}},
    )
    report = {
        "paths": {
            "initialStateFiles": [
                {
                    "artifactPath": "runtime/initial-state/strategy/paper-state.json",
                    "sourcePath": str(seed_state),
                    "purpose": "production startup state seed",
                }
            ]
        },
        "paperSignal": {
            "continuation": _paper_continuation("stateful_continuation"),
            "design": _paper_design(
                uses_state=True,
                cutover_state_required=True,
            ),
        },
    }
    report["paperSignal"]["design"]["cutover"][
        "stateEnd"
    ] = "2020-01-04"

    smoke = promotion_helpers._run_edge_paper_run_one_smoke(
        candidate,
        strategy_source_path=promoted_source,
        packaged_files=(
            promotion_helpers.PromotionPackagedFile(
                artifact_path="runtime/initial-state/strategy/paper-state.json",
                source_path=seed_state,
                purpose="production startup state seed",
                role="initial_state",
            ),
        ),
        destination=destination,
        strategy_entrypoint="strategy.py",
        runtime_env={},
        is_denylisted_source=lambda path: False,
        report=report,
    )

    assert smoke["status"] == "passed"
    assert smoke["validationBootstrap"]["status"] == "passed"
    assert smoke["validationBootstrap"]["cutoverAsOf"] == "2020-01-01"
    assert smoke["tailConsistency"]["validationCutoverAsOf"] == "2020-01-01"
    assert smoke["tailConsistency"]["sampleSize"] == 3
    assert smoke["stateChangedFirstCall"] is True
    assert smoke["stateChangedSecondCall"] is False


def test_paper_smoke_timeout_returns_compact_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import time as _time

    def slow_smoke(*args, **kwargs):
        _time.sleep(1)
        return {"status": "passed"}

    monkeypatch.setitem(
        promotion_helpers._run_edge_paper_run_one_smoke.__globals__,
        "_run_edge_paper_run_one_smoke_unbounded",
        slow_smoke,
    )
    monkeypatch.setitem(
        promotion_helpers._run_edge_paper_run_one_smoke.__globals__,
        "PROMOTION_HOSTED_PAPER_TIMEOUT_SECONDS",
        0.01,
    )

    smoke = promotion_helpers._run_edge_paper_run_one_smoke(
        object(),
        strategy_source_path=tmp_path / "engine.py",
        packaged_files=(),
        destination=tmp_path,
        strategy_entrypoint="strategy.py",
        runtime_env={},
        is_denylisted_source=lambda path: False,
        report={},
    )

    assert smoke["status"] == "failed"
    assert smoke["timeoutSeconds"] == 0.01
    assert "timed out" in smoke["reason"]
    assert "compute_runtime_output" in smoke["diagnosis"]["check"]


def test_paper_signal_design_facts_detects_runtime_path_helper_state() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        paths = context_runtime_paths(self.context)\n"
        "        state_root = paths.state / 'strategy'\n"
        "        return {'next_position': 1.0, 'state': str(state_root)}\n"
    )

    facts = promotion_helpers._paper_signal_design_facts(source)

    assert facts["usesStateDir"] is True


def test_paper_signal_design_facts_detects_helper_state_writes() -> None:
    source = (
        "import pickle\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "def _save_paper_state(path, state):\n"
        "    with path.open('wb') as fh:\n"
        "        pickle.dump(state, fh)\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        paths = context_runtime_paths(self.context)\n"
        "        state_path = paths.state / 'strategy' / 'paper_state.pkl'\n"
        "        _save_paper_state(state_path, {'as_of': str(as_of)})\n"
        "        return {'next_position': 1.0}\n"
    )

    facts = promotion_helpers._paper_signal_design_facts(source)

    assert facts["usesStateDir"] is True
    assert facts["writesState"] is True


def test_temporal_dependency_facts_surface_lookback_and_calendar_hints() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "TRAIN_WINDOW = 360\n"
        "REFIT_EVERY = 20\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        close = ctx.target.series('close')\n"
        "        features = close.pct_change(60).shift(1).rolling(window=20).mean()\n"
        "        for row_idx in range(180, len(close) - 1):\n"
        "            if row_idx % REFIT_EVERY == 0:\n"
        "                train_x = features.iloc[row_idx - TRAIN_WINDOW:row_idx]\n"
        "        return ctx.decisions(0)\n"
    )
    tree = ast.parse(source)

    facts = promotion_helpers._source_temporal_dependency_facts(source, tree)

    lookbacks = " ".join(item["expression"] for item in facts["lookbackHints"])
    calendar = " ".join(item["expression"] for item in facts["calendarHints"])
    constants = {item["name"]: item["value"] for item in facts["constantHints"]}
    assert "pct_change(60)" in lookbacks
    assert "rolling(window=20)" in lookbacks
    assert "row_idx % REFIT_EVERY" in calendar
    assert "range(180, len(close) - 1)" in calendar
    assert constants["TRAIN_WINDOW"] == "360"
    assert constants["REFIT_EVERY"] == "20"


def test_export_selected_strategy_artifact_requires_hosted_contract_for_stateful_branch(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "state_aware")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is False
    assert result["skipReason"] == "hosted_paper_contract_required"
    request = json.loads(
        Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8")
    )
    assert request["kind"] == "hosted_paper_contract"
    assert any(signal["kind"] == "state_like_file" for signal in request["signals"])


def test_export_selected_strategy_artifact_uses_local_runtime_state_source(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "runtime_state_source")
    _write_strategy_artifact_inputs(branch)
    state_file = branch / ".abel-runtime" / "state" / "model" / "latest.joblib"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("runtime state\n", encoding="utf-8")
    (branch / ".abel-runtime" / "state" / "model" / "scratch.joblib").write_text(
        "undeclared state\n",
        encoding="utf-8",
    )
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        evaluated = _fake_evaluate_command(command)
        if evaluated is not None:
            return evaluated
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,1,0,backfill,1\n"
                "2020-01-02,0,0,1,0,backfill,1\n"
                "2020-01-03,0,0,1,0,backfill,1\n"
                "2020-01-04,0,0,1,0,backfill,1\n",
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

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert first_result["artifactExported"] is False
    promoted_dir = Path(first_result["promotionReport"]["requestPath"]).parent
    (promoted_dir / "engine.py").write_text(
        "import json\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"strategy/model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent packaged runtime state seed.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": str(state_file),
                            "purpose": "latest runtime model seed",
                        }
                    ],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(
                        uses_state=True,
                        cutover_state_required=True,
                    ),
                ),
                "limitations": [],
                "replacements": [],
            }
        ),
        encoding="utf-8",
    )

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    file_paths = [item["path"] for item in manifest["files"]]
    assert result["promotionMode"] == "agent_paper_contract"
    assert "runtime/initial-state/strategy/model/latest.joblib" in file_paths
    assert "runtime/initial-state/strategy/paper_state.json" in file_paths
    assert not any(path.startswith("strategy/.abel-runtime/") for path in file_paths)


def test_export_selected_strategy_artifact_agent_paper_contracts_dynamic_state_path(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "ambiguous_state")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "model" / "feature_scaler.json").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from pathlib import Path\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = Path(\"model/latest.joblib\")\n"
        "        scaler_path = Path(\"model\") / \"feature_scaler.json\"\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        evaluated = _fake_evaluate_command(command)
        if evaluated is not None:
            return evaluated
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,1,0,backfill,1\n"
                "2020-01-02,0,0,1,0,backfill,1\n"
                "2020-01-03,0,0,1,0,backfill,1\n"
                "2020-01-04,0,0,1,0,backfill,1\n",
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
                        "fileCount": 12,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    output_dir = tmp_path / "exported-artifact"
    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert first_result["artifactExported"] is False
    assert first_result["skipReason"] == "hosted_paper_contract_required"
    request_path = Path(first_result["promotionReport"]["requestPath"])
    assert request_path.exists()

    promoted_dir = request_path.parent
    promoted_engine = promoted_dir / "engine.py"
    promoted_engine.write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "import json\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def _state_path(self):\n"
        "        return context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"strategy/model/latest.joblib\"\n"
        "        scaler_path = ctx.state_dir / \"strategy/model/feature_scaler.json\"\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent moved model paths onto ctx.state_dir.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": "model/latest.joblib",
                            "purpose": "latest model seed",
                        },
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/feature_scaler.json",
                            "sourcePath": "model/feature_scaler.json",
                            "purpose": "feature scaler seed",
                        },
                    ],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(
                        uses_state=True,
                        cutover_state_required=True,
                    ),
                ),
                "limitations": [],
                "replacements": [
                    {
                        "path": "model/latest.joblib",
                        "replacement": "ctx.state_dir / \"strategy/model/latest.joblib\"",
                    },
                    {
                        "path": "model/feature_scaler.json",
                        "replacement": "ctx.state_dir / \"strategy/model/feature_scaler.json\"",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    assert result["skipReason"] == ""
    assert result["promotionMode"] == "agent_paper_contract"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["promotion"]["mode"] == "agent_paper_contract"
    assert manifest["promotion"]["contract"]["kind"] == "hosted_paper_contract"
    assert manifest["promotion"]["gate"] == {
        "status": "passed",
        "evidencePath": "edge/promotion-gate.json",
    }
    file_paths = [item["path"] for item in manifest["files"]]
    assert "edge/promotion-gate.json" in file_paths
    assert "edge/promotion.patch" in file_paths
    assert "edge/paper-contract-report.json" in file_paths
    assert "runtime/initial-state/strategy/model/latest.joblib" in file_paths
    assert "runtime/initial-state/strategy/model/feature_scaler.json" in file_paths
    assert "runtime/initial-state/strategy/paper_state.json" in file_paths
    promoted_engine = output_dir / "promoted" / "engine.py"
    promoted_source = promoted_engine.read_text(encoding="utf-8")
    assert 'ctx.state_dir / "strategy/model/latest.joblib"' in promoted_source
    assert 'ctx.state_dir / "strategy/model/feature_scaler.json"' in promoted_source


def test_promotion_state_dependency_scan_records_state_like_facts(tmp_path: Path) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    runtime_state = branch / ".abel-runtime" / "state" / "strategy" / "model.joblib"
    runtime_state.parent.mkdir(parents=True)
    runtime_state.write_text("state\n", encoding="utf-8")
    source_path = branch / "engine.py"
    source_path.write_text(
        "MODEL_PATH = 'models/AAPL/registry.json'\n"
        "class BranchEngine:\n"
        "    def compute_decisions(self, ctx):\n"
        "        return MODEL_PATH\n",
        encoding="utf-8",
    )

    scan = promotion_helpers._collect_hosted_paper_dependency_scan(
        branch,
        strategy_source_path=source_path,
        is_denylisted_source=lambda path: False,
    )

    signals = scan["stateDependencies"]
    assert any(signal["kind"] == "runtime_state_file" for signal in signals)
    assert any(signal["kind"] == "source_state_reference" for signal in signals)


def test_export_selected_strategy_artifact_regenerates_missing_metric_input(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    output_dir = tmp_path / "exported-artifact"
    _seed_promoted_stateless_paper_artifact(output_dir)
    commands_seen = []

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        commands_seen.append(command)
        if "evaluate" in command:
            result_path = Path(command[command.index("--output-json") + 1])
            report_path = Path(command[command.index("--output-md") + 1])
            metric_input_path = Path(command[command.index("--output-csv") + 1])
            payload = _candidate_result_payload()
            payload["implementation_contract"] = "decision_context"
            payload["metrics"]["sharpe"] = 0.967
            payload["metrics"]["lo_adjusted"] = 1.056
            payload["metrics"]["max_dd"] = -0.1278
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            report_path.write_text("# validation\n", encoding="utf-8")
            metric_input_path.write_text(
                "date,asset_return,pnl,position,gross_pnl,turnover,execution_cost,next_position\n"
                "2020-01-01,0,0,0,0,0,0,0\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,0,0,backfill,0\n"
                "2020-01-02,0,0,1,0,backfill,1\n",
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
                        "fileCount": 8,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    assert any("evaluate" in command for command in commands_seen)
    assert (output_dir / "metric-input.csv").exists()


def test_export_selected_strategy_artifact_skips_without_validation(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-001",
        verdict="ERROR",
        sharpe=0.1,
        lo_adj=0.2,
        max_dd=-0.3,
    )

    def unexpected_runner(*args, **kwargs):
        raise AssertionError("unexpected")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=unexpected_runner,
    )

    assert result == {
        "artifactExported": False,
        "artifactUploadSkipped": True,
        "skipReason": "no_validation_strategy",
        "selectedBranchId": None,
        "selectedRoundId": None,
    }


def test_post_strategy_artifact_upload_sends_multipart_request(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.zip"
    artifact_path.write_bytes(b"zip-bytes")
    calls = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"data": {"artifactUploadId": "upload_1", "admissionStatus": "queued"}}'

    def fake_opener(request, timeout):
        calls.append((request, timeout))
        return _Response()

    result = ni.post_strategy_artifact_upload(
        base_url="https://router.example/",
        api_key="secret-key",
        hosted_session_id="sess_1",
        manifest={"schema": "abel-invest.strategy-artifact/v1"},
        artifact_path=artifact_path,
        source_upload_id="upload_narrative",
        client_request_id="client_1",
        opener=fake_opener,
    )

    request, timeout = calls[0]
    body = request.data
    assert result["data"]["artifactUploadId"] == "upload_1"
    assert request.full_url == (
        "https://router.example/web/skill-dashboard/sessions/sess_1/strategy-artifacts"
    )
    assert request.get_header("Api-key") == "secret-key"
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'name="manifest"' in body
    assert b'name="artifact"; filename="artifact.zip"' in body
    assert b"name=\"sourceUploadId\"" in body
    assert b"name=\"clientRequestId\"" in body
    assert timeout == 60


def test_upload_strategy_artifact_for_session_returns_upload_summary(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    _seed_promoted_stateless_paper_artifact(tmp_path / "exported-artifact")

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,0,0,backfill,0\n"
                "2020-01-02,0,0,1,0,backfill,1\n",
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
                        "fileCount": 8,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                b'{"data": {"artifactUploadId": "upload_1", "status": "uploaded", '
                b'"admissionStatus": "queued", "strategyId": null}}'
            )

    result = ni.upload_strategy_artifact_for_session(
        local_session=session,
        narrative_result={"data": {"sessionId": "sess_1", "uploadId": "narrative_1"}},
        base_url="https://router.example",
        api_key="secret-key",
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        opener=lambda request, timeout: _Response(),
        runner=fake_runner,
    )

    assert result["artifactUploadFailed"] is False
    assert result["artifactUploadId"] == "upload_1"
    assert result["admissionStatus"] == "queued"
    assert result["selectedBranchId"] == "momentum_lead"


def test_visualize_session_uploads_narrative_only_with_without_strategy_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    artifact_calls = []

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "resolve_skill_dashboard_base_url",
        lambda: "https://router.example",
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "post_skill_dashboard_session",
        lambda **kwargs: {
            "data": {"sessionId": "sess_1", "openUrl": "https://app.example/sess_1"}
        },
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "export_selected_strategy_artifact",
        lambda *args, **kwargs: artifact_calls.append((args, kwargs)),
    )

    ni.upload_skill_dashboard_session(
        Namespace(
            session=str(session),
            api_key="secret-key",
            output_json=None,
            dry_run=False,
            without_strategy_artifact=True,
            artifact_output_dir=None,
            python_bin=None,
        )
    )

    assert artifact_calls == []
    assert "Online session view" in capsys.readouterr().out


def test_visualize_session_uploads_strategy_artifact_by_default(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    calls = []

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "resolve_skill_dashboard_base_url",
        lambda: "https://router.example",
    )

    def fake_export(*args, **kwargs):
        calls.append("export")
        return {
            "artifactExported": True,
            "artifactUploadSkipped": False,
            "manifestPath": str(tmp_path / "manifest.json"),
            "artifactPath": str(tmp_path / "artifact.zip"),
            "selectedBranchId": "momentum_lead",
            "selectedRoundId": "round-006",
        }

    def fake_post_session(**kwargs):
        calls.append("post_session")
        return {
            "data": {"sessionId": "sess_1", "openUrl": "https://app.example/sess_1"}
        }

    def fake_prepared_upload(**kwargs):
        calls.append("upload_artifact")
        assert kwargs["export_result"]["artifactExported"] is True
        return {"artifactUploadId": "upload_1", "admissionStatus": "queued"}

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "export_selected_strategy_artifact",
        fake_export,
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "post_skill_dashboard_session",
        fake_post_session,
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "upload_prepared_strategy_artifact_for_session",
        fake_prepared_upload,
    )

    ni.upload_skill_dashboard_session(
        Namespace(
            session=str(session),
            api_key="secret-key",
            output_json=None,
            dry_run=False,
            without_strategy_artifact=False,
            artifact_output_dir=None,
            python_bin=None,
        )
    )

    assert calls == ["export", "post_session", "upload_artifact"]
    output = capsys.readouterr().out
    assert "Strategy artifact uploaded: upload_1" in output
    assert "admission=queued" in output
    assert "router admission continues asynchronously" in output


def test_visualize_session_aborts_before_upload_when_agent_paper_contract_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    calls = []

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "resolve_skill_dashboard_base_url",
        lambda: "https://router.example",
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "export_selected_strategy_artifact",
        lambda *args, **kwargs: {
            "artifactExported": False,
            "artifactUploadSkipped": True,
            "skipReason": "hosted_paper_contract_required",
            "promotionMode": "hosted_paper_contract_required",
            "promotionReport": {
                "mode": "hosted_paper_contract_required",
                "reason": "dynamic state path requires paper contract",
                "requestPath": str(tmp_path / "paper-contract-request.json"),
            },
        },
    )

    def unexpected_post_session(**kwargs):
        calls.append("post_session")
        raise AssertionError("narrative upload should not start")

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "post_skill_dashboard_session",
        unexpected_post_session,
    )

    with pytest.raises(RuntimeError, match="hosted paper contract"):
        ni.upload_skill_dashboard_session(
            Namespace(
                session=str(session),
                api_key="secret-key",
                output_json=None,
                dry_run=False,
                without_strategy_artifact=False,
                artifact_output_dir=None,
                python_bin=None,
            )
        )

    assert calls == []


def test_render_strategy_artifact_upload_result_lines() -> None:
    rendered = ni.render_skill_dashboard_session_upload_result(
        {
            "data": {
                "sessionId": "sess_1",
                "openUrl": "https://app.example/sess_1",
            }
        },
        artifact_result={
            "artifactUploadId": "upload_1",
            "admissionStatus": "queued",
            "selectedBranchId": "momentum_lead",
            "selectedRoundId": "round-006",
        },
    )

    assert "Online session view: [Open sess_1](https://app.example/sess_1)" in rendered
    assert "Strategy artifact uploaded: upload_1" in rendered
    assert "admission=queued" in rendered
    assert "router admission continues asynchronously" in rendered


def test_render_skill_dashboard_session_upload_result_returns_markdown_link() -> None:
    rendered = ni.render_skill_dashboard_session_upload_result(
        {
            "code": 200,
            "data": {
                "sessionId": "s1",
                "openUrl": "https://app.abel.ai/abel-invest/s1",
            },
        }
    )

    assert rendered == "Online session view: [Open s1](https://app.abel.ai/abel-invest/s1)"


def test_resolve_skill_dashboard_base_url_defaults_to_abel_router() -> None:
    assert ni.resolve_skill_dashboard_base_url("") == "https://api.abel.ai/router/"


def test_load_discovery_falls_back_to_legacy_discovery_json(tmp_path: Path) -> None:
    session = tmp_path / "research" / "tsla" / "legacy-session"
    session.mkdir(parents=True)
    discovery = {
        "ticker": "TSLA",
        "source": "legacy_discovery",
        "parents": [{"ticker": "AAPL", "node_id": "AAPL.price"}],
        "blanket_new": [],
        "children": [],
        "K_discovery": 1,
    }
    (session / "discovery.json").write_text(json.dumps(discovery), encoding="utf-8")

    assert ni.load_discovery(session)["source"] == "legacy_discovery"
