from __future__ import annotations

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
    dependencies = {
        "version": 1,
        "branch_id": branch.name,
        "target": target,
        "target_node": f"{target}.price",
        "selected_inputs": selected_inputs,
        "selected_graph_nodes": [f"{ticker}.price" for ticker in selected_inputs],
        "requested_start": "2020-01-01",
        "data_requirements": {"timeframe": "1d"},
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

    trade_log_path = branch / "outputs" / "round-006-trade-log.csv"
    trade_log_path.parent.mkdir(parents=True, exist_ok=True)
    trade_log_path.write_text(
        "date,asset_return,pnl,position,cum_return,source\n"
        "2020-01-01,0,0,0,0,backtest\n"
        "2020-01-02,0.01,0.01,1,0.01,backtest\n",
        encoding="utf-8",
    )
    return trade_log_path


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
            "date,asset_return,pnl,position,cum_return,source\n"
            "2020-01-01,0,0,0,0,backfill\n",
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
    assert "research_journal.md" in round_output
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
    session = ni.init_session_dir("TSLA", "tsla-primary-dashboard", tmp_path / "research")
    branch_a = ni.init_branch_dir(session, "graph-v1")
    branch_b = ni.init_branch_dir(session, "graph-v2")
    branch_c = ni.init_branch_dir(session, "graph-v3")
    for branch, round_id, score, pnl, lo_adj, sharpe in [
        (branch_a, "round-001", "8/9", "90.0", "1.8", "1.4"),
        (branch_b, "round-001", "9/9", "40.0", "1.2", "1.1"),
        (branch_b, "round-002", "9/9", "55.0", "1.1", "1.0"),
        (branch_c, "round-001", "9/9", "55.0", "1.3", "0.9"),
    ]:
        result_ref = f"branches/{branch.name}/outputs/{round_id}-edge-result.json"
        report_ref = f"branches/{branch.name}/outputs/{round_id}-edge-validation.md"
        result_path = session / result_ref
        frame_path = session / f"branches/{branch.name}/outputs/{round_id}-edge-frame.csv"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "verdict": "PASS",
                    "metrics": {
                        "sharpe": float(sharpe),
                        "lo_adjusted": float(lo_adj),
                        "max_dd": -0.1,
                        "total_return": float(pnl) / 100.0,
                        "position_hit_rate": 0.75,
                    },
                    "decision_preview": [
                        {"date": "2026-05-04", "target_close": 16.13},
                        {"date": "2026-05-05", "target_close": 17.06},
                    ]
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
                "lo_adj": lo_adj,
                "ic": "0.0500",
                "omega": "1.700",
                "sharpe": sharpe,
                "max_dd": "-0.1000",
                "pnl": pnl,
                "K": "3",
                "score": score,
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


def test_select_best_pass_strategy_sorts_validation_rounds_by_pass_rate_first(
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
    assert result.eligible_count == 3
    assert result.selected_branch_id == "regime_switch"
    assert result.selected_round_id == "round-002"
    assert result.selected is not None
    assert result.selected.selection_rank == 1
    assert result.selected.selection_metric_values == {
        "pass_rate": 11 / 13,
        "sharpe": 0.508,
        "calmar": 0.5,
        "max_dd": -0.1805,
    }


def test_select_best_pass_strategy_sorts_by_sharpe_calmar_max_dd_then_latest(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    lower_sharpe = ni.init_branch_dir(session, "lower_sharpe")
    higher_calmar = ni.init_branch_dir(session, "higher_calmar")
    lower_calmar = ni.init_branch_dir(session, "lower_calmar")
    better_drawdown = ni.init_branch_dir(session, "better_drawdown")
    later = ni.init_branch_dir(session, "later")
    for branch, sharpe, calmar, max_dd in [
        (lower_sharpe, 1.1, 9.0, -0.05),
        (higher_calmar, 1.2, 3.1, -0.12),
        (lower_calmar, 1.2, 2.9, -0.03),
        (better_drawdown, 1.2, 3.1, -0.08),
        (later, 1.2, 3.1, -0.08),
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
            calmar=calmar,
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
            "pass_rate": 1.0,
            "sharpe": 0.967,
            "calmar": 3.28,
            "max_dd": -0.1278,
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

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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
    ]
    assert manifest["source"]["selectionMode"] == "auto_best_validation_by_pass_rate"
    assert manifest["source"]["selectionScope"] == "session"
    assert manifest["promotion"]["mode"] == "zero_change"


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

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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


def test_export_selected_strategy_artifact_state_path_adapter(
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
    (branch / "state_intent.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.state-intent/v1",
                "entries": [
                    {
                        "path": "model/latest.joblib",
                        "role": "initial_state",
                        "mutableInPaper": True,
                        "requiredForSignal": True,
                        "producedBy": "pytest",
                    }
                ],
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
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert result["promotionMode"] == "auto_adapter"
    assert manifest["runtime"]["state"]["bootstrap"] == {
        "mode": "copy_from_base",
        "path": "runtime/initial-state/",
    }
    assert manifest["promotion"]["mode"] == "auto_adapter"
    assert manifest["promotion"]["adapter"] == {
        "kind": "state_path_adapter",
        "scope": "state_path_normalization",
    }
    assert manifest["promotion"]["gate"] == {
        "status": "passed",
        "evidencePath": "edge/promotion-gate.json",
    }
    file_paths = [item["path"] for item in manifest["files"]]
    assert "runtime/initial-state/model/latest.joblib" in file_paths
    assert "edge/promotion-gate.json" in file_paths
    assert "edge/promotion.patch" in file_paths
    promoted_engine = output_dir / "promoted" / "engine.py"
    assert 'ctx.state_dir / "model/latest.joblib"' in promoted_engine.read_text(
        encoding="utf-8"
    )
    export_command = next(command for command in commands_seen if "export-artifact" in command)
    assert "--extra-source-map" in export_command


def test_export_selected_strategy_artifact_requires_state_intent_self_check_for_runtime_state(
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
    assert result["skipReason"] == "needs_agent_refactor"
    report = result["promotionReport"]
    assert report["mode"] == "needs_agent_refactor"
    assert "state intent self-check required" in report["reason"]
    request = json.loads(Path(report["requestPath"]).read_text(encoding="utf-8"))
    assert request["kind"] == "state_intent_self_check"
    assert request["scope"] == "state_intent_classification"
    assert request["signals"][0]["kind"] == "runtime_state_file"
    assert request["signals"][0]["suggestedStateIntentPath"] == "model/latest.json"
    assert request["statelessStateIntentTemplate"]["entries"] == []


def test_export_selected_strategy_artifact_requires_state_intent_self_check_for_ad_hoc_paths(
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
    assert request["kind"] == "state_intent_self_check"
    assert any(signal["kind"] == "source_state_reference" for signal in request["signals"])


def test_export_selected_strategy_artifact_allows_explicit_stateless_self_check(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "stateless_after_self_check")
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

    assert result["artifactExported"] is True
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["promotion"]["mode"] == "zero_change"
    assert manifest["stateIntent"]["selfCheck"]["status"] == "no_durable_state"


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
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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


def test_export_selected_strategy_artifact_returns_gate_evidence_on_replay_failure(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "replay_failure")
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
    (branch / "state_intent.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.state-intent/v1",
                "entries": [
                    {
                        "path": "model/latest.joblib",
                        "role": "initial_state",
                        "mutableInPaper": True,
                        "requiredForSignal": True,
                        "producedBy": "pytest",
                    }
                ],
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
    output_dir = tmp_path / "exported-artifact"

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "evaluate" in command:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="synthetic promoted replay failure",
            )
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is False
    assert result["skipReason"] == "needs_agent_refactor"
    gate_path = Path(result["promotionReport"]["gatePath"])
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    assert gate["status"] == "failed"
    behavior_gate = next(
        item for item in gate["gates"] if item["name"] == "behavior_equivalence"
    )
    assert behavior_gate["status"] == "failed"
    assert "promoted replay failed" in behavior_gate["details"]["reason"]


def test_export_selected_strategy_artifact_state_aware_zero_change(
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
    (branch / "state_intent.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.state-intent/v1",
                "entries": [
                    {
                        "path": "model/latest.joblib",
                        "role": "initial_state",
                        "mutableInPaper": True,
                        "requiredForSignal": True,
                        "producedBy": "pytest",
                    }
                ],
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
    output_dir = tmp_path / "exported-artifact"

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        evaluated = _fake_evaluate_command(command)
        if evaluated is not None:
            return evaluated
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert result["promotionMode"] == "zero_change"
    assert manifest["runtime"]["state"]["bootstrap"] == {
        "mode": "copy_from_base",
        "path": "runtime/initial-state/",
    }
    assert manifest["promotion"]["mode"] == "zero_change"
    assert manifest["promotion"]["gate"]["evidencePath"] == "edge/promotion-gate.json"
    file_paths = [item["path"] for item in manifest["files"]]
    assert "runtime/initial-state/model/latest.joblib" in file_paths
    assert "edge/promotion-gate.json" in file_paths


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
    (branch / "state_intent.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.state-intent/v1",
                "entries": [
                    {
                        "path": "model/latest.joblib",
                        "role": "initial_state",
                        "mutableInPaper": True,
                        "requiredForSignal": True,
                        "producedBy": "pytest",
                    }
                ],
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
    output_dir = tmp_path / "exported-artifact"

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        evaluated = _fake_evaluate_command(command)
        if evaluated is not None:
            return evaluated
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    file_paths = [item["path"] for item in manifest["files"]]
    assert result["promotionMode"] == "zero_change"
    assert "runtime/initial-state/model/latest.joblib" in file_paths
    assert not any(path.startswith("strategy/.abel-runtime/") for path in file_paths)


def test_export_selected_strategy_artifact_agent_refactors_dynamic_state_path(
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
    (branch / "state_intent.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.state-intent/v1",
                "entries": [
                    {
                        "path": "model/latest.joblib",
                        "role": "initial_state",
                        "mutableInPaper": True,
                        "requiredForSignal": True,
                        "producedBy": "pytest",
                    },
                    {
                        "path": "model/feature_scaler.json",
                        "role": "initial_state",
                        "mutableInPaper": True,
                        "requiredForSignal": True,
                        "producedBy": "pytest",
                    }
                ],
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

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        evaluated = _fake_evaluate_command(command)
        if evaluated is not None:
            return evaluated
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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
    assert first_result["skipReason"] == "needs_agent_refactor"
    request_path = Path(first_result["promotionReport"]["requestPath"])
    assert request_path.exists()

    promoted_dir = request_path.parent
    promoted_engine = promoted_dir / "engine.py"
    promoted_engine.write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"model/latest.joblib\"\n"
        "        scaler_path = ctx.state_dir / \"model/feature_scaler.json\"\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
    )
    (promoted_dir / "refactor-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-refactor-report/v1",
                "kind": "agent_assisted",
                "summary": "Agent moved model paths onto ctx.state_dir.",
                "scope": "state_path_normalization",
                "replacements": [
                    {
                        "path": "model/latest.joblib",
                        "replacement": "ctx.state_dir / \"model/latest.joblib\"",
                    },
                    {
                        "path": "model/feature_scaler.json",
                        "replacement": "ctx.state_dir / \"model/feature_scaler.json\"",
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
    assert result["promotionMode"] == "agent_refactor"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["promotion"]["mode"] == "agent_refactor"
    assert manifest["promotion"]["refactor"]["kind"] == "agent_assisted"
    assert manifest["promotion"]["gate"] == {
        "status": "passed",
        "evidencePath": "edge/promotion-gate.json",
    }
    file_paths = [item["path"] for item in manifest["files"]]
    assert "edge/promotion-gate.json" in file_paths
    assert "edge/promotion.patch" in file_paths
    assert "edge/refactor-report.json" in file_paths
    assert "runtime/initial-state/model/latest.joblib" in file_paths
    assert "runtime/initial-state/model/feature_scaler.json" in file_paths
    promoted_engine = output_dir / "promoted" / "engine.py"
    promoted_source = promoted_engine.read_text(encoding="utf-8")
    assert 'ctx.state_dir / "model/latest.joblib"' in promoted_source
    assert 'ctx.state_dir / "model/feature_scaler.json"' in promoted_source


def test_promotion_state_path_detection_is_path_specific() -> None:
    source = (
        "model_path = ctx.state_dir / \"model/latest.joblib\"\n"
        "scaler_path = Path(\"model\") / \"feature_scaler.json\"\n"
    )

    assert promotion_helpers._source_uses_state_path(source, "model/latest.joblib")
    assert not promotion_helpers._source_uses_state_path(
        source,
        "model/feature_scaler.json",
    )
    dynamic_source = (
        "symbol = \"AAPL\"\n"
        "registry_path = ctx.state_dir / \"models\" / symbol / \"registry.json\"\n"
        "checkpoint_path = ctx.state_dir.joinpath(\"models\", symbol, \"checkpoints/regime_latest.npz\")\n"
    )
    assert promotion_helpers._source_uses_state_path(
        dynamic_source,
        "models/AAPL/registry.json",
    )
    assert promotion_helpers._source_uses_state_path(
        dynamic_source,
        "models/AAPL/checkpoints/regime_latest.npz",
    )


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
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source\n"
                "2020-01-01,0,0,0,0,backfill\n",
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


def test_visualize_session_uploads_narrative_only_by_default(
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
        "upload_strategy_artifact_for_session",
        lambda **kwargs: artifact_calls.append(kwargs),
    )

    ni.upload_skill_dashboard_session(
        Namespace(
            session=str(session),
            api_key="secret-key",
            output_json=None,
            dry_run=False,
            with_strategy_artifact=False,
            artifact_output_dir=None,
            python_bin=None,
        )
    )

    assert artifact_calls == []
    assert "Online session view" in capsys.readouterr().out


def test_visualize_session_uploads_strategy_artifact_with_flag(
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
            with_strategy_artifact=True,
            artifact_output_dir=None,
            python_bin=None,
        )
    )

    assert calls == ["export", "post_session", "upload_artifact"]
    output = capsys.readouterr().out
    assert "Strategy artifact uploaded: upload_1" in output
    assert "admission=queued" in output
    assert "router admission continues asynchronously" in output


def test_visualize_session_aborts_before_upload_when_agent_refactor_fails(
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
            "skipReason": "needs_agent_refactor",
            "promotionMode": "needs_agent_refactor",
            "promotionReport": {
                "mode": "needs_agent_refactor",
                "reason": "dynamic state path requires refactor",
                "requestPath": str(tmp_path / "refactor-request.json"),
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

    with pytest.raises(RuntimeError, match="skill-level agent refactor"):
        ni.upload_skill_dashboard_session(
            Namespace(
                session=str(session),
                api_key="secret-key",
                output_json=None,
                dry_run=False,
                with_strategy_artifact=True,
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
