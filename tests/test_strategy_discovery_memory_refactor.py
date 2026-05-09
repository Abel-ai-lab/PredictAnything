from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import strategy_discovery_api as ni
from abel_invest.narrative_core.dashboard_adapters.primary_strategy_selector import position_action


def _candidate_result_payload() -> dict:
    return {
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
            frame_path.write_text(
                "date,pnl,position,next_position,close\n"
                "2026-04-30,0.01,0.25,0.50,101.0\n"
                "2026-05-01,0.02,0.50,0.75,102.0\n",
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
                "- hypothesis: `AAPL driver strength leads TSLA next-day risk appetite.`",
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
        (round_item["branchId"], round_item["roundId"], round_item["sessionRoundIndex"])
        for round_item in bundle["payload"]["rounds"]
    ] == [
        ("target-control", "round-001", 1),
        ("graph-v1", "round-001", 2),
    ]


def test_build_skill_dashboard_session_bundle_selects_primary_strategy_from_results_tsv(
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

    primary = bundle["payload"]["primaryStrategy"]
    assert primary["branchId"] == "graph-v3"
    assert primary["roundId"] == "round-001"
    assert primary["selectionRule"] == "score_desc_total_return_desc_lo_adjusted_desc_sharpe_desc_latest_v1"
    assert primary["metrics"]["score"] == "9/9"
    assert primary["metrics"]["totalReturn"] == 0.55
    assert primary["metrics"]["loAdjusted"] == 1.3
    assert primary["metrics"]["positionIcStability"] == 0.6
    assert primary["metrics"]["dsr"] == 0.99
    assert primary["metrics"]["lossYears"] == 1
    assert primary["latestDecision"] == {
        "tradingDate": "2026-05-05",
        "previousPosition": 0.75,
        "currentPosition": 0.3,
        "position": 0.3,
        "nextPosition": 0.6,
        "delta": -0.15,
        "action": "reduce",
        "close": 17.06,
        "source": "abel_invest_edge_frame_csv",
    }
    assert primary["backtestTradeLog"] == {
        "source": "abel_invest_trade_log_csv",
        "tradeLogRef": "branches/graph-v3/outputs/round-001-trade-log.csv",
    }
    trade_log_path = session / primary["backtestTradeLog"]["tradeLogRef"]
    assert trade_log_path.read_text(encoding="utf-8").splitlines() == [
        "date,asset_return,pnl,position,source,decision_time,effective_time,next_position,gross_pnl,turnover,execution_cost,cum_return",
        "2026-05-04,,0.01,0.75,backfill,,,0.30,,,,0.010000000000000009",
        "2026-05-05,,0.02,0.30,backfill,,,0.60,,,,0.030200000000000005",
    ]


def test_primary_strategy_position_action_maps_previous_to_next_position() -> None:
    assert position_action(0, 0.3) == "buy/open_long"
    assert position_action(0.3, 0) == "sell/close"
    assert position_action(0.3, 0.6) == "increase"
    assert position_action(0.75, 0.6) == "reduce"
    assert position_action(0.3, 0.3) == "hold"


def test_primary_strategy_selector_uses_only_recorded_kept_pass_rounds(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-primary-filter-dashboard", tmp_path / "research")
    kept_branch = ni.init_branch_dir(session, "kept-branch")
    discarded_branch = ni.init_branch_dir(session, "discarded-branch")
    unrecorded_branch = ni.init_branch_dir(session, "unrecorded-branch")
    rows = [
        (kept_branch, "round-001", "keep", "PASS", "9/9", "20.0", True),
        (discarded_branch, "round-001", "discard", "PASS", "9/9", "90.0", True),
        (unrecorded_branch, "round-001", "keep", "PASS", "9/9", "95.0", False),
    ]
    for branch, round_id, decision, verdict, score, pnl, recorded in rows:
        result_ref = f"branches/{branch.name}/outputs/{round_id}-edge-result.json"
        ni.append_tsv_row(
            branch / "results.tsv",
            ni.RESULTS_HEADER,
            {
                "exp_id": session.name,
                "ticker": "TSLA",
                "branch_id": branch.name,
                "round_id": round_id,
                "decision": decision,
                "lo_adj": "1.000",
                "ic": "0.0100",
                "omega": "1.100",
                "sharpe": "1.000",
                "max_dd": "-0.1000",
                "pnl": pnl,
                "K": "3",
                "score": score,
                "verdict": verdict,
                "mode": "explore",
                "description": f"{branch.name} {round_id}",
                "result_path": result_ref,
                "report_path": f"branches/{branch.name}/outputs/{round_id}-edge-validation.md",
                "handoff_path": f"branches/{branch.name}/outputs/{round_id}-edge-handoff.json",
            },
        )
        if recorded:
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
                    "description": f"{branch.name} {round_id}",
                    "artifact_path": result_ref,
                },
            )

    bundle = ni.build_skill_dashboard_session_bundle(
        session,
        uploaded_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )

    assert bundle["payload"]["primaryStrategy"]["branchId"] == "kept-branch"
    assert bundle["payload"]["primaryStrategy"]["metrics"]["totalReturn"] == 0.2


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


def test_post_skill_dashboard_session_uploads_trade_log_as_multipart(tmp_path: Path) -> None:
    calls = []
    trade_log = tmp_path / "branches" / "b1" / "outputs" / "round-001-trade-log.csv"
    trade_log.parent.mkdir(parents=True)
    trade_log.write_text("date,pnl,cum_return\n2026-05-05,0.1,0.1\n", encoding="utf-8")

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
        bundle={
            "sessionId": "s1",
            "payload": {
                "session": {},
                "branches": [],
                "rounds": [],
                "primaryStrategy": {
                    "backtestTradeLog": {
                        "tradeLogRef": "branches/b1/outputs/round-001-trade-log.csv"
                    }
                },
            },
        },
        session_root=tmp_path,
        opener=fake_opener,
    )

    request, _timeout = calls[0]
    body = request.data
    assert result["data"]["sessionId"] == "s1"
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'name="payload"' in body
    assert b'name="backtestTradeLog"; filename="round-001-trade-log.csv"' in body
    assert b"date,pnl,cum_return" in body


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
