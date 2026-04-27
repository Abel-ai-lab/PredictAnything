from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from pathlib import Path

from abel_strategy_discovery import narrative_impl as ni


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
    assert "## Pivot Checkpoint" in context_text


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
    assert ledger["rows"][-1]["evidence_label"] == "candidate_causal_evidence"
    assert "candidate_causal_evidence" in (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    ni.print_status(session)
    status_output = capsys.readouterr().out
    assert "Research journal:" in status_output
    assert "Agent memory:" not in status_output
    assert ni.check_session(session, strict=False) == 0
