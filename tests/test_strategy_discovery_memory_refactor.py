from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import strategy_discovery_api as ni


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


def _write_strategy_result_row(
    session: Path,
    branch: Path,
    *,
    round_id: str,
    verdict: str,
    sharpe: float,
    lo_adj: float,
    max_dd: float,
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
            "score": "9/9",
            "verdict": verdict,
            "mode": "explore",
            "description": f"{branch.name} {round_id}",
            "result_path": str(result_path.relative_to(session)),
            "report_path": str(report_path.relative_to(session)),
            "handoff_path": str(handoff_path.relative_to(session)),
        },
    )


def test_render_writes_agent_context_with_journal_view(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")

    assert (session / ni.EVIDENCE_LEDGER_FILENAME).exists()
    assert (session / ni.FRONTIER_MARKDOWN_FILENAME).exists()
    assert (session / ni.AGENT_CONTEXT_FILENAME).exists()
    assert not (branch / "memory.md").exists()
    assert not (session / "views").exists()

    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")
    assert "## Evidence Frontier" in context_text
    assert "## Research Journal" in context_text
    assert "## Research Reflection" in context_text
    assert "## Journal Coverage" in context_text
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
    assert "Session visualization available:" in status_output
    assert "Ask the user whether to create an online view of this session." in status_output
    assert "create it and share the returned link" in status_output
    assert "abel-invest visualize-session --session" not in status_output
    assert "--base-url" not in status_output
    assert "Research journal:" in status_output
    assert "Agent memory:" not in status_output
    assert ni.check_session(session, strict=False) == 0
    assert ni.check_session(session, strict=True) == 1

    blocked = ni.run_branch_round(
        Namespace(
            branch=str(branch),
            mode="explore",
            description="second pass",
            input_note="",
            hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
            expected_signal="",
            trigger="follow-up",
            change_summary="second pass",
            time_spent_min="10",
            summary="",
            next_step="",
            action=[],
            python_bin=None,
        )
    )
    assert blocked == 2
    assert "Journal required before next recorded round" in capsys.readouterr().err


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
    (session / ni.RESEARCH_JOURNAL_FILENAME).write_text(
        "# Research Journal\n\n"
        "## Notes\n\n"
        "- Driver concentration matters more than raw parent count. ledger:graph-v1:round-001\n",
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
    assert bundle["payload"]["session"]["journalCoverage"] == {
        "recorded_round_count": 1,
        "journaled_round_count": 1,
        "journal_coverage_complete": True,
        "missing_journal_rounds": [],
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


def test_select_best_pass_strategy_sorts_session_pass_rounds(tmp_path: Path) -> None:
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
    )
    _write_strategy_result_row(
        session,
        branch_b,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_strategy_result_row(
        session,
        branch_b,
        round_id="round-010",
        verdict="PASS",
        sharpe=0.945,
        lo_adj=1.041,
        max_dd=-0.1340,
        decision="discard",
    )
    _write_strategy_result_row(
        session,
        branch_c,
        round_id="round-002",
        verdict="FAIL",
        sharpe=0.808,
        lo_adj=0.866,
        max_dd=-0.1805,
        decision="discard",
    )

    result = ni.select_best_pass_strategy(session)

    assert result.skip_reason == ""
    assert result.pass_round_count == 3
    assert result.eligible_count == 3
    assert result.selected_branch_id == "momentum_lead"
    assert result.selected_round_id == "round-006"
    assert result.selected is not None
    assert result.selected.selection_rank == 1
    assert result.selected.selection_metric_values == {
        "sharpe": 0.967,
        "lo_adjusted": 1.056,
        "max_dd": -0.1278,
    }


def test_select_best_pass_strategy_returns_skip_when_no_pass(tmp_path: Path) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "regime_switch")
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-001",
        verdict="FAIL",
        sharpe=0.685,
        lo_adj=0.831,
        max_dd=-0.1654,
        decision="discard",
    )

    result = ni.select_best_pass_strategy(session)

    assert result.selected is None
    assert result.skip_reason == "no_pass_strategy"
    assert result.pass_round_count == 0
    assert result.eligible_count == 0


def test_select_best_pass_strategy_skips_unhostable_pass_rounds(tmp_path: Path) -> None:
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
            "verdict": "PASS",
            "mode": "explore",
            "description": "missing result",
            "result_path": "branches/momentum_lead/outputs/missing-edge-result.json",
            "report_path": "",
            "handoff_path": "",
        },
    )

    result = ni.select_best_pass_strategy(session)

    assert result.selected is None
    assert result.skip_reason == "no_hostable_pass_strategy"
    assert result.pass_round_count == 1
    assert result.eligible_count == 0


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
