from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from pathlib import Path

from abel_strategy_discovery import narrative_impl as ni


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
            "contract": "causal-edge.runtime-facts/v1",
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
                    "contract": "causal-edge.runtime-facts/v1",
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
    assert "Dashboard upload:" in status_output
    assert "abel-strategy-discovery upload-dashboard-bundle --branch" in status_output
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
    assert bundle["payload"]["rounds"][0]["evidenceLabel"] == "candidate_causal_evidence"
    assert bundle["payload"]["rounds"][0]["inputRealization"]["realized_input_claim"] == "graph_supported"
    assert any(
        "Driver concentration matters" in item["summary"]
        for item in bundle["payload"]["branchInsights"]
    )
    assert "replaySnapshot" not in bundle["payload"]
    assert "promotion" not in bundle["payload"]


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
