from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from abel_strategy_discovery import narrative_impl as ni


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
                "selected_drivers": ["AAPL", "MSFT"],
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
) -> dict:
    return {
        "verdict": verdict,
        "score": "7/7" if verdict == "PASS" else "3/7",
        "failures": [item.get("message", "") for item in (metric_failures or []) if item.get("message")],
        "warnings": [],
        "profile": "equity_daily",
        "K": 1,
        "metrics": {
            "sharpe": sharpe,
            "lo_adjusted": 1.5,
            "position_ic": 0.02,
            "omega": 1.3,
            "total_return": 0.22,
            "max_dd": -0.08,
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
            "contract": "causal-edge.runtime-facts/v1",
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
    continuation_rationale: str = "",
    single_branch_rationale: str = "",
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
            continuation_rationale=continuation_rationale,
            single_branch_rationale=single_branch_rationale,
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
    selected_drivers: list[str] | None = None,
    mechanism_family: str = "driver_momentum",
    model_family: str = "rule_signal",
    complexity_class: str = "simple_signal",
    exploration_role: str = "candidate",
) -> dict:
    selected = selected_drivers or ["AAPL"]
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
            "selected_drivers": selected,
        }
    )
    return spec


def test_evidence_runtime_facts_prefers_edge_contract() -> None:
    result = _edge_result(traced_inputs=[])
    result["runtime_facts"] = {
        "contract": "causal-edge.runtime-facts/v1",
        "verdict": "PASS",
        "semantic_verdict": "PASS",
        "runtime_stage": "validation",
        "workflow_status": "evaluation_completed",
        "read_summary": {
            "target_reads": ["primary"],
            "auxiliary_reads": ["AAPL"],
            "read_count": 4,
            "decision_count": 120,
        },
        "prepared_inputs": {
            "selected_inputs": ["AAPL"],
            "traced_inputs": ["AAPL"],
            "effective_window": {"start": "2020-01-01", "end": "2020-12-31"},
            "issues": [],
        },
        "temporal_visibility": {"issue_kinds": [], "has_error": False},
    }

    facts = ni.evidence_runtime_facts(result)

    assert facts["workflow_status"] == "evaluation_completed"
    assert facts["auxiliary_reads"] == ["AAPL"]
    assert facts["read_count"] == 4


def test_prepare_branch_inputs_writes_runtime_contract_artifacts(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")

    spec = ni.load_branch_spec(branch)
    spec["target"] = "TSLA"
    spec["requested_start"] = "2020-01-01"
    spec["selected_drivers"] = ["AAPL", "MSFT", "AAPL", "msft"]
    spec["position_bounds"] = [-1.0, 1.0]
    ni.write_branch_spec(branch, spec)

    calls = []

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None):
        calls.append(list(command))
        output_path = Path(command[command.index("--output-json") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "adapter": "abel",
                    "timeframe": "1d",
                    "profile": "daily",
                    "results": [
                        {
                            "symbol": "TSLA",
                            "ok": True,
                            "row_count": 150,
                            "available_range": {"start": "2020-01-01", "end": "2020-12-31"},
                        },
                        {
                            "symbol": "AAPL",
                            "ok": True,
                            "row_count": 150,
                            "available_range": {"start": "2020-01-01", "end": "2020-12-31"},
                        },
                        {
                            "symbol": "MSFT",
                            "ok": True,
                            "row_count": 110,
                            "available_range": {"start": "2020-03-01", "end": "2020-12-31"},
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)

    result = ni.prepare_branch_inputs(
        Namespace(
            branch=str(branch),
            python_bin=sys.executable,
            cache_limit=400,
        )
    )

    assert result == 0
    assert calls and "warm-cache" in calls[0]
    assert ni.branch_inputs_ready(branch)

    runtime_profile = json.loads(ni.runtime_profile_path(branch).read_text(encoding="utf-8"))
    branch_spec = ni.load_branch_spec(branch)
    dependencies = json.loads(ni.dependencies_path(branch).read_text(encoding="utf-8"))
    data_manifest = json.loads(ni.data_manifest_path(branch).read_text(encoding="utf-8"))
    probe_samples = json.loads(ni.probe_samples_path(branch).read_text(encoding="utf-8"))
    context_guide = ni.context_guide_path(branch).read_text(encoding="utf-8")

    assert runtime_profile["target"] == "TSLA"
    assert branch_spec["selected_inputs"] == ["AAPL", "MSFT"]
    assert branch_spec["selected_drivers"] == ["AAPL", "MSFT"]
    assert dependencies["selected_inputs"] == ["AAPL", "MSFT"]
    assert dependencies["selected_drivers"] == ["AAPL", "MSFT"]
    assert data_manifest["selected_inputs"] == ["AAPL", "MSFT"]
    assert data_manifest["selected_drivers"] == ["AAPL", "MSFT"]
    assert [feed["name"] for feed in data_manifest["feeds"]] == ["primary", "AAPL", "MSFT"]
    assert probe_samples["target"] == "TSLA"
    assert len(probe_samples["sample_decision_dates"]) >= 2
    assert "DecisionContext" in context_guide


def test_default_branch_spec_starts_as_graph_first_draft_declaration(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-decl", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")

    spec = ni.load_branch_spec(branch)
    status = ni.branch_declaration_status(spec)

    assert spec["evidence_intent"] == "draft"
    assert spec["input_claim"] == "graph_supported"
    assert "source_type" not in spec
    assert "method_family" not in spec
    assert spec["model_family"] == "unspecified"
    assert spec["complexity_class"] == "unspecified"
    assert spec["exploration_role"] == "candidate"
    assert spec["overlap_mode"] == "target_only"
    assert spec["selected_inputs"] == ["AAPL", "MSFT"]
    assert spec["selected_drivers"] == ["AAPL", "MSFT"]
    assert status["protocol_complete"] is False
    assert "hypothesis" in status["protocol_gaps"]
    assert "evidence_intent:draft" in status["protocol_gaps"]


def test_default_branch_spec_stays_target_only_when_discovery_is_pending(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-decl-pending", tmp_path / "research")
    branch = ni.init_branch_dir(session, "fallback-v1")

    spec = ni.load_branch_spec(branch)

    assert spec["evidence_intent"] == "draft"
    assert spec["input_claim"] == "target_only"
    assert "source_type" not in spec
    assert "method_family" not in spec
    assert spec["selected_inputs"] == []
    assert spec["selected_drivers"] == []


def test_init_session_cli_runs_live_discovery_by_default(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    calls: list[tuple[str, int]] = []

    def fake_fetch_live_discovery(ticker: str, *, limit: int) -> dict:
        calls.append((ticker, limit))
        return _sample_discovery()

    monkeypatch.setattr(ni, "fetch_live_discovery", fake_fetch_live_discovery)
    monkeypatch.setattr(ni, "refresh_data_readiness", lambda **_kwargs: _sample_readiness())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abel-strategy-discovery",
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "tsla-cli-default",
            "--root",
            str(tmp_path / "research"),
        ],
    )

    assert ni.main() == 0
    out = capsys.readouterr().out
    discovery = json.loads(
        (tmp_path / "research" / "tsla" / "tsla-cli-default" / "discovery.json").read_text(
            encoding="utf-8"
        )
    )

    assert calls == [("TSLA", 10)]
    assert discovery["source"] == "abel_live"
    assert discovery["K_discovery"] == 2
    assert "discovery_source: abel_live (K=2)" in out


def test_init_session_cli_no_discover_is_explicit_pending_fallback(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    def fail_fetch_live_discovery(*_args, **_kwargs) -> dict:
        raise AssertionError("live discovery should not run with --no-discover")

    monkeypatch.setattr(ni, "fetch_live_discovery", fail_fetch_live_discovery)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abel-strategy-discovery",
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "tsla-cli-pending",
            "--root",
            str(tmp_path / "research"),
            "--no-discover",
        ],
    )

    assert ni.main() == 0
    out = capsys.readouterr().out
    discovery = json.loads(
        (tmp_path / "research" / "tsla" / "tsla-cli-pending" / "discovery.json").read_text(
            encoding="utf-8"
        )
    )

    assert discovery["source"] == "pending"
    assert discovery["K_discovery"] == 0
    assert "discovery_source: pending (live discovery not run)" in out


def test_complete_branch_declaration_accepts_legacy_selected_drivers(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-decl-complete", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL and MSFT driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "No non-primary driver reads or negative out-of-sample IC.",
            "selected_drivers": ["AAPL", "MSFT"],
        }
    )

    status = ni.branch_declaration_status(spec)

    assert status["protocol_complete"] is True
    assert status["selected_inputs"] == ["AAPL", "MSFT"]


def test_legacy_source_type_and_method_family_do_not_complete_declaration() -> None:
    spec = {
        "source_type": "causal",
        "method_family": "graph",
        "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
        "invalidation_condition": "AAPL reads disappear or validation fails repeatedly.",
        "requested_start": "2020-01-01",
        "selected_drivers": ["AAPL"],
    }

    status = ni.branch_declaration_status(spec)

    assert status["protocol_complete"] is False
    assert status["evidence_intent"] == ""
    assert status["input_claim"] == ""
    assert status["mechanism_family"] == ""
    assert "evidence_intent" in status["protocol_gaps"]
    assert "input_claim" in status["protocol_gaps"]
    assert "mechanism_family" in status["protocol_gaps"]


def test_evidence_ledger_marks_missing_hypothesis_as_protocol_incomplete(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-ledger-missing", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "selected_drivers": ["AAPL", "MSFT"],
        }
    )
    _record_synthetic_round(session, branch, spec=spec, result=_edge_result())

    ni.render_session(session)
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))

    row = ledger["rows"][-1]
    assert row["evidence_label"] == "protocol_incomplete"
    assert "hypothesis" in row["declaration_gaps"]


def test_evidence_ledger_classifies_complete_target_control(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-ledger-control", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "control-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "TSLA target momentum persists over the next daily bar.",
            "evidence_intent": "control",
            "input_claim": "target_only",
            "mechanism_family": "target_momentum",
            "invalidation_condition": "Target-only validation loses positive IC.",
        }
    )
    _record_synthetic_round(session, branch, spec=spec, result=_edge_result())

    ni.render_session(session)
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))

    row = ledger["rows"][-1]
    assert row["evidence_label"] == "target_control_evidence"
    assert row["comparable"] is True
    assert row["workflow_status"] == "evaluation_completed"


def test_evidence_ledger_classifies_missing_edge_result_as_workflow_blocker(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-ledger-blocker", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "control-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "TSLA target momentum persists over the next daily bar.",
            "evidence_intent": "control",
            "input_claim": "target_only",
            "mechanism_family": "target_momentum",
            "invalidation_condition": "Target-only validation loses positive IC.",
        }
    )
    _record_synthetic_round(
        session,
        branch,
        spec=spec,
        result=_edge_result(verdict="ERROR"),
        result_path_override="branches/control-v1/outputs/missing-edge-result.json",
    )

    ni.render_session(session)
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))

    row = ledger["rows"][-1]
    assert row["evidence_label"] == "workflow_blocker"
    assert row["workflow_status"] == "blocked"


def test_run_branch_round_records_network_failure_as_workflow_blocker(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-network-blocker", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    _write_runtime_files(branch)
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "No AAPL reads or negative holdout IC.",
            "selected_drivers": ["AAPL"],
        }
    )
    ni.write_branch_spec(branch, spec)

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="HTTPSConnectionPool remote end closed connection without response",
        )

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)

    result = ni.run_branch_round(
        Namespace(
            branch=str(branch),
            mode="explore",
            description="network failure round",
            input_note="",
            hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
            expected_signal="",
            trigger="test",
            change_summary="test",
            time_spent_min="1",
            summary="",
            next_step="",
            action=[],
            python_bin=None,
        )
    )

    assert result == 1
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    row = ledger["rows"][-1]
    assert row["evidence_label"] == "workflow_blocker"
    assert row["runtime_stage"] == "data_access"
    assert row["workflow_status"] == "not_completed"


def test_starter_scaffold_round_is_diagnostic_only_not_candidate(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-scaffold-diagnostic", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    _write_runtime_files(branch)
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "No AAPL reads or negative holdout IC.",
            "selected_drivers": ["AAPL"],
        }
    )
    ni.write_branch_spec(branch, spec)

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None):
        result_path = Path(command[command.index("--output-json") + 1])
        report_path = Path(command[command.index("--output-md") + 1])
        handoff_path = Path(command[command.index("--output-handoff") + 1])
        result_path.write_text(
            json.dumps(_edge_result(traced_inputs=["AAPL"], sharpe=2.3)),
            encoding="utf-8",
        )
        report_path.write_text("# validation\n", encoding="utf-8")
        handoff_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)

    result = ni.run_branch_round(
        Namespace(
            branch=str(branch),
            mode="explore",
            description="starter scaffold wiring check",
            input_note="",
            hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
            expected_signal="",
            trigger="test",
            change_summary="test",
            time_spent_min="1",
            summary="",
            next_step="",
            action=[],
            python_bin=None,
        )
    )

    assert result == 0
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    row = ledger["rows"][-1]
    assert row["engine_scaffold_status"] == "starter_scaffold"
    assert row["evidence_label"] == "diagnostic_only"


def test_frontier_reports_coverage_without_route_recommendation(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-frontier", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL and MSFT driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "No non-primary driver reads or negative out-of-sample IC.",
            "selected_drivers": ["AAPL", "MSFT"],
        }
    )
    _record_synthetic_round(session, branch, spec=spec, result=_edge_result(traced_inputs=["AAPL"]))

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    frontier_text = (session / ni.FRONTIER_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    session_text = (session / "README.md").read_text(encoding="utf-8")

    assert frontier["evidence_label_counts"]["candidate_causal_evidence"] == 1
    assert frontier["mechanism_family_counts"]["driver_momentum"] == 1
    assert frontier["driver_reads"] == ["AAPL"]
    forbidden = ["try next", "recommend", "open a sibling", "resume `", "threshold"]
    assert not any(term in frontier_text.lower() for term in forbidden)
    assert "## Next Step" not in session_text
    assert "candidate_causal_evidence" in session_text


def test_frontier_surfaces_candidate_failures_and_resume_facts(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-frontier-fail-facts", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL and MSFT risk appetite leads TSLA next-day returns.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "Driver reads vanish or validation stays negative.",
            "requested_start": "2020-01-01",
            "selected_drivers": ["AAPL", "MSFT", "AAPL"],
        }
    )
    metric_failure = {
        "metric": "position_ic_stability",
        "observed": 0.19,
        "threshold": 0.55,
        "comparison": "lt",
        "profile": "equity_daily",
        "message": "PositionIC stab 19% < 55%",
    }
    for index in range(6):
        _record_synthetic_round(
            session,
            branch,
            spec=spec,
            result=_edge_result(
                traced_inputs=["AAPL", "MSFT"],
                verdict="FAIL",
                sharpe=2.3,
                metric_failures=[metric_failure],
            ),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    ni.render_session(session)
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    frontier_text = (session / ni.FRONTIER_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert all(row["declared_selected_inputs"] == ["AAPL", "MSFT"] for row in ledger["rows"])
    assert frontier["evidence_label_counts"]["candidate_causal_evidence"] == 6
    assert frontier["evidence_label_verdict_counts"]["candidate_causal_evidence"]["FAIL"] == 6
    assert frontier["evidence_label_decision_counts"]["candidate_causal_evidence"]["discard"] == 6
    assert frontier["candidate_causal_summary"]["validation_fail"] == 6
    assert frontier["metric_failure_counts"]["position_ic_stability"] == 6
    concentration = frontier["coverage_concentration"]
    assert concentration["branch_count"] == 1
    assert concentration["max_rounds_in_one_branch"] == 6
    assert concentration["dominant_mechanism_family"] == "driver_momentum"
    assert concentration["dominant_driver_set"] == "AAPL,MSFT"
    assert concentration["target_control_evidence"] == 0
    assert concentration["agent_memory_records"] == 0
    assert "candidate_causal_evidence.FAIL: `6`" in frontier_text
    assert "## Resume State Facts" in context_text
    assert "- agent_memory_records: `0`" in context_text
    forbidden = ["try next", "recommend", "open a sibling", "switch mechanism"]
    assert not any(term in frontier_text.lower() for term in forbidden)
    assert not any(term in context_text.lower() for term in forbidden)


def test_init_session_creates_research_journal(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-journal-init", tmp_path / "research")

    journal_path = session / ni.RESEARCH_JOURNAL_FILENAME
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert journal_path.exists()
    assert "agent-owned research notes" in journal_path.read_text(encoding="utf-8")
    assert "## Research Journal" in context_text
    assert "- evidence_reference_count: `0`" in context_text
    assert "- has_evidence_linked_update: `false`" in context_text
    assert "- recent_excerpt: `none`" in context_text


def test_agent_context_reads_evidence_linked_research_journal(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-journal-linked", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "AAPL reads disappear or validation fails repeatedly.",
            "requested_start": "2020-01-01",
            "selected_drivers": ["AAPL"],
        }
    )
    _record_synthetic_round(
        session,
        branch,
        spec=spec,
        result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
    )
    (session / ni.RESEARCH_JOURNAL_FILENAME).write_text(
        "# Research Journal\n\n## Notes\n\n"
        "AAPL-only failed cleanly in ledger:graph-v1:round-001; the useful "
        "artifact is branches/graph-v1/outputs/round-001-edge-result.json.\n",
        encoding="utf-8",
    )

    ni.render_session(session)
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert "- evidence_reference_count: `2`" in context_text
    assert "- resolved_evidence_reference_count: `2`" in context_text
    assert "- has_evidence_linked_update: `true`" in context_text
    assert "AAPL-only failed cleanly" in context_text


def test_journal_prose_without_refs_is_not_evidence_linked(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-journal-prose", tmp_path / "research")
    (session / ni.RESEARCH_JOURNAL_FILENAME).write_text(
        "# Research Journal\n\n## Notes\n\nThis direction feels too narrow.\n",
        encoding="utf-8",
    )

    ni.render_session(session)
    status = ni.build_research_journal_status(
        session,
        ledger=json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8")),
        frontier=json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8")),
    )

    assert status["evidence_reference_count"] == 0
    assert status["has_evidence_linked_update"] is False
    assert status["recent_excerpt"] == "This direction feels too narrow."


def test_exploration_breadth_marks_single_branch_local_refinement(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-breadth-local", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "model_family": "rule_signal",
            "complexity_class": "simple_signal",
            "exploration_role": "candidate",
            "invalidation_condition": "AAPL reads disappear or validation fails repeatedly.",
            "requested_start": "2020-01-01",
            "selected_drivers": ["AAPL"],
        }
    )
    for index in range(6):
        _record_synthetic_round(
            session,
            branch,
            spec=spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")
    exploration = frontier["exploration_breadth"]

    assert exploration["branch_family_count"] == 1
    assert exploration["initial_breadth_incomplete"] is True
    assert exploration["same_branch_max_rounds"] == 6
    assert exploration["exploration_class_counts"]["broad_explore"] == 1
    assert exploration["exploration_class_counts"]["local_refinement"] == 5
    assert exploration["continuation_rationale_required_count"] == 1
    assert exploration["continuation_rationale_missing_count"] == 1
    assert ledger["rows"][-1]["continuation_rationale_required"] is True
    assert ledger["rows"][-1]["same_neighborhood_failed_rows"] == 5
    assert "initial_breadth_incomplete: `true`" in context_text
    assert "continuation_rationale_missing_count: `1`" in context_text


def test_single_branch_rationale_clears_initial_breadth_warning(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-breadth-rationale", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "model_family": "rule_signal",
            "complexity_class": "simple_signal",
            "invalidation_condition": "AAPL reads disappear or validation fails repeatedly.",
            "requested_start": "2020-01-01",
            "selected_drivers": ["AAPL"],
        }
    )
    for index in range(4):
        _record_synthetic_round(
            session,
            branch,
            spec=spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
            single_branch_rationale=(
                "One-branch start is intentional for isolated runtime comparison."
                if index == 3
                else ""
            ),
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    exploration = frontier["exploration_breadth"]

    assert exploration["branch_family_count"] == 1
    assert exploration["same_branch_max_rounds"] == 4
    assert exploration["single_branch_rationale_present"] is True
    assert exploration["initial_breadth_incomplete"] is False
    failures: list[str] = []
    ni.validate_exploration_protocol(session, failures)
    assert failures == []


def test_second_branch_family_clears_initial_breadth_warning(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-breadth-second-family", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    first = ni.init_branch_dir(session, "graph-v1")
    first_spec = ni.load_branch_spec(first)
    first_spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "model_family": "rule_signal",
            "complexity_class": "simple_signal",
            "invalidation_condition": "AAPL reads disappear or validation fails repeatedly.",
            "requested_start": "2020-01-01",
            "selected_drivers": ["AAPL"],
        }
    )
    second = ni.init_branch_dir(session, "model-v1")
    second_spec = ni.load_branch_spec(second)
    second_spec.update(
        {
            "hypothesis": "MSFT driver strength interacts with TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_interaction",
            "model_family": "linear_model",
            "complexity_class": "interaction",
            "invalidation_condition": "MSFT reads disappear or validation fails repeatedly.",
            "requested_start": "2020-01-01",
            "selected_drivers": ["MSFT"],
        }
    )
    for index in range(4):
        _record_synthetic_round(
            session,
            first,
            spec=first_spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )
    _record_synthetic_round(
        session,
        second,
        spec=second_spec,
        result=_edge_result(traced_inputs=["MSFT"], verdict="FAIL"),
        round_id="round-001",
        decision="discard",
        changed_dimensions=["model_family", "complexity"],
    )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))

    assert frontier["exploration_breadth"]["branch_family_count"] == 2
    assert frontier["exploration_breadth"]["initial_breadth_incomplete"] is False
    assert frontier["exploration_breadth"]["model_family_counts"]["linear_model"] == 1


def test_input_breadth_reports_candidate_driver_set_coverage(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-input-breadth", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    graph_branch = ni.init_branch_dir(session, "graph-aapl")
    graph_spec = _complete_candidate_spec(graph_branch, selected_drivers=["AAPL"])
    target_branch = ni.init_branch_dir(session, "target-control")
    target_spec = _complete_candidate_spec(
        target_branch,
        selected_drivers=[],
        mechanism_family="target_momentum",
    )
    target_spec["input_claim"] = "target_only"
    target_spec["selected_drivers"] = []
    target_spec["selected_inputs"] = []

    for index in range(2):
        _record_synthetic_round(
            session,
            graph_branch,
            spec=graph_spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )
    for index in range(3):
        _record_synthetic_round(
            session,
            target_branch,
            spec=target_spec,
            result=_edge_result(traced_inputs=[], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    frontier_text = (session / ni.FRONTIER_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")
    input_breadth = frontier["input_breadth"]

    assert input_breadth["discovered_driver_count"] == 2
    assert input_breadth["discovered_drivers"] == ["AAPL", "MSFT"]
    assert input_breadth["candidate_driver_set_count"] == 1
    assert input_breadth["candidate_driver_sets"] == ["AAPL"]
    assert input_breadth["candidate_discovered_driver_coverage_count"] == 1
    assert input_breadth["discovered_driver_coverage"] == "1/2"
    assert input_breadth["target_only_recorded_round_count"] == 3
    assert input_breadth["graph_supported_candidate_round_count"] == 2
    assert "## Input Breadth" in frontier_text
    assert "candidate_driver_set_count: `1`" in context_text
    forbidden = ["try next", "recommend", "which driver", "driver to try"]
    assert not any(term in frontier_text.lower() for term in forbidden)
    assert not any(term in context_text.lower() for term in forbidden)


def test_input_breadth_warning_marks_thin_candidate_driver_coverage(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-input-breadth-warning", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    graph_branch = ni.init_branch_dir(session, "graph-aapl")
    graph_spec = _complete_candidate_spec(graph_branch, selected_drivers=["AAPL"])
    target_branch = ni.init_branch_dir(session, "target-control")
    target_spec = _complete_candidate_spec(target_branch, selected_drivers=[])
    target_spec["input_claim"] = "target_only"
    target_spec["selected_drivers"] = []
    target_spec["selected_inputs"] = []

    for index in range(4):
        _record_synthetic_round(
            session,
            graph_branch,
            spec=graph_spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )
        _record_synthetic_round(
            session,
            target_branch,
            spec=target_spec,
            result=_edge_result(traced_inputs=[], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert frontier["input_breadth"]["input_breadth_thin"] is True
    assert frontier["graph_priority"]["graph_candidates_available"] is True
    assert "input_breadth_thin: `true`" in context_text
    assert ni.input_breadth_warning_lines(session) == [
        "input_breadth_thin=true "
        "candidate_driver_set_count=1 "
        "discovered_driver_coverage=1/2 "
        "target_only_recorded_round_count=4 "
        "graph_supported_candidate_round_count=4"
    ]

    ni.record_agent_memory(
        Namespace(
            session=str(session),
            branch="",
            scope="session",
            type="insight",
            text="AAPL-only graph candidate coverage remains thin.",
            confidence="medium",
            status="active",
            round_id="",
            evidence_ref=["frontier:input_breadth"],
        )
    )
    assert ni.input_breadth_warning_lines(session) == [
        "input_breadth_thin=true "
        "candidate_driver_set_count=1 "
        "discovered_driver_coverage=1/2 "
        "target_only_recorded_round_count=4 "
        "graph_supported_candidate_round_count=4"
    ]

    msft_branch = ni.init_branch_dir(session, "graph-msft")
    msft_spec = _complete_candidate_spec(msft_branch, selected_drivers=["MSFT"])
    _record_synthetic_round(
        session,
        msft_branch,
        spec=msft_spec,
        result=_edge_result(traced_inputs=["MSFT"], verdict="FAIL"),
        round_id="round-001",
        decision="discard",
    )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))

    assert frontier["input_breadth"]["candidate_driver_set_count"] == 2
    assert frontier["input_breadth"]["input_breadth_thin"] is False
    assert ni.input_breadth_warning_lines(session) == []


def test_graph_priority_warns_when_graph_candidates_are_uncovered(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-graph-uncovered", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    target_branch = ni.init_branch_dir(session, "target-control")
    target_spec = _complete_candidate_spec(target_branch, selected_drivers=[])
    target_spec["input_claim"] = "target_only"
    target_spec["selected_drivers"] = []
    target_spec["selected_inputs"] = []

    for index in range(3):
        _record_synthetic_round(
            session,
            target_branch,
            spec=target_spec,
            result=_edge_result(traced_inputs=[], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert frontier["graph_priority"]["graph_candidates_available"] is True
    assert frontier["graph_priority"]["graph_first_uncovered"] is True
    assert frontier["graph_priority"]["graph_discovery_missing"] is False
    assert "graph_first_uncovered: `true`" in context_text
    assert ni.graph_priority_warning_lines(session) == [
        "graph_first_uncovered=true graph_discovery_k=2 target_only_saturation=true"
    ]


def test_mixed_graph_reads_remain_supplemental_for_graph_priority(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-mixed-supplemental", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "mixed-aapl")
    spec = _complete_candidate_spec(branch, selected_drivers=["AAPL"])
    spec["input_claim"] = "mixed"

    for index in range(3):
        _record_synthetic_round(
            session,
            branch,
            spec=spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))

    assert frontier["evidence_label_counts"]["supplemental_evidence"] == 3
    assert frontier["input_breadth"]["graph_supported_candidate_round_count"] == 0
    assert frontier["graph_priority"]["graph_first_uncovered"] is True


def test_graph_priority_warns_when_discovery_is_missing_and_target_only_saturates(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-graph-missing", tmp_path / "research")
    target_branch = ni.init_branch_dir(session, "target-control")
    target_spec = _complete_candidate_spec(target_branch, selected_drivers=[])
    target_spec["input_claim"] = "target_only"
    target_spec["selected_drivers"] = []
    target_spec["selected_inputs"] = []

    for index in range(3):
        _record_synthetic_round(
            session,
            target_branch,
            spec=target_spec,
            result=_edge_result(traced_inputs=[], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))

    assert frontier["graph_priority"]["graph_candidates_available"] is False
    assert frontier["graph_priority"]["graph_discovery_missing"] is True
    assert frontier["graph_priority"]["graph_first_uncovered"] is False
    assert ni.graph_priority_warning_lines(session) == [
        "graph_discovery_missing=true "
        "graph_discovery_source=pending "
        "graph_discovery_k=0 "
        "target_only_saturation=true"
    ]


def test_memory_checkpoint_requires_agent_authored_memory_after_evidence(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-memory-checkpoint", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    first_branch: Path | None = None
    for index in range(6):
        branch = ni.init_branch_dir(session, f"graph-{index + 1}")
        first_branch = first_branch or branch
        spec = _complete_candidate_spec(branch, selected_drivers=["AAPL"])
        _record_synthetic_round(
            session,
            branch,
            spec=spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id="round-001",
            decision="discard",
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert frontier["memory_checkpoint"]["memory_checkpoint_due"] is True
    assert frontier["memory_checkpoint"]["memory_checkpoint_reason"] == "recorded_round_minimum"
    assert "memory_checkpoint_due: `true`" in context_text
    assert ni.memory_checkpoint_warning_lines(session) == [
        "memory_checkpoint_due=true "
        "agent_memory_records=0 "
        "reason=recorded_round_minimum "
        "required_action=agent_authored_memory_with_evidence_ref"
    ]

    assert first_branch is not None
    ni.record_agent_memory(
        Namespace(
            session="",
            branch=str(first_branch),
            scope="session",
            type="insight",
            text="AAPL-only graph attempts have not produced a passing candidate yet.",
            confidence="medium",
            status="active",
            round_id="round-001",
            evidence_ref=["ledger:graph-1:round-001"],
        )
    )

    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    assert frontier["memory_checkpoint"]["agent_memory_records"] == 1
    assert frontier["memory_checkpoint"]["memory_checkpoint_due"] is False
    assert frontier["memory_checkpoint"]["memory_reference_gap_count"] == 0
    assert ni.memory_checkpoint_warning_lines(session) == []

    ni.record_agent_memory(
        Namespace(
            session="",
            branch=str(first_branch),
            scope="session",
            type="insight",
            text="This note intentionally lacks a supporting evidence reference.",
            confidence="low",
            status="active",
            round_id="",
            evidence_ref=[],
        )
    )

    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    assert frontier["memory_checkpoint"]["memory_reference_gap_count"] == 1


def test_debug_rows_do_not_cross_initial_breadth_threshold(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-breadth-debug", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = _complete_candidate_spec(branch)
    ni.write_branch_spec(branch, spec)
    outputs = branch / "outputs"
    outputs.mkdir(exist_ok=True)
    debug_context = outputs / "debug-alpha-context.json"
    debug_result = outputs / "debug-edge-result.json"
    debug_context.write_text(json.dumps({"branch_spec": spec}, indent=2), encoding="utf-8")
    debug_result.write_text(
        json.dumps(_edge_result(traced_inputs=["AAPL"], verdict="PASS")),
        encoding="utf-8",
    )
    ni.persist_debug_snapshot(
        branch,
        {
            "updated_at": "2026-04-27T00:00:00+00:00",
            "context_path": str(debug_context.relative_to(session)),
            "result_path": str(debug_result.relative_to(session)),
            "report_path": "",
            "handoff_path": "",
            "backtest_start": "2020-01-01",
            "failure_signature": "healthy_signal",
            "runtime_stage": "semantic_preflight",
            "signal_activity": "120 / 252",
            "summary": "debug pass",
        },
    )
    for index in range(3):
        _record_synthetic_round(
            session,
            branch,
            spec=spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    exploration = frontier["exploration_breadth"]

    assert frontier["row_count"] == 4
    assert exploration["recorded_round_count"] == 3
    assert exploration["diagnostic_row_count"] == 1
    assert exploration["same_branch_max_rounds"] == 3
    assert exploration["branch_family_count"] == 1
    assert exploration["initial_breadth_incomplete"] is False
    assert exploration["dominant_neighborhood_rows"] == 3
    assert exploration["dominant_evidence_neighborhood_rows"] == 4


def test_pre_run_warning_before_fourth_same_branch_round(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-breadth-pre-run", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = _complete_candidate_spec(branch)
    ni.write_branch_spec(branch, spec)
    for index in range(3):
        _record_synthetic_round(
            session,
            branch,
            spec=spec,
            result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
        )

    lines = ni.initial_breadth_pre_run_warning_lines(
        session=session,
        branch=branch,
        pending_single_branch_rationale="",
    )
    quiet_lines = ni.initial_breadth_pre_run_warning_lines(
        session=session,
        branch=branch,
        pending_single_branch_rationale="Intentional narrow start for isolated protocol comparison.",
    )

    assert lines == [
        "initial_breadth_will_be_incomplete=true "
        "recorded_rounds_in_branch=3 "
        "pending_recorded_round_index=4 "
        "branch_family_count=1 "
        "single_branch_rationale_present=false "
        "protocol_exits=multiple_recorded_branch_families,single_branch_rationale_recorded"
    ]
    assert quiet_lines == []


def test_init_session_output_uses_graph_first_research_loop() -> None:
    lines = ni.render_breadth_first_start_lines(Path("research/tsla/demo"))
    rendered = "\n".join(lines)

    assert "<family-a-branch>" in rendered
    assert "<family-b-branch>" in rendered
    assert "graph-v1" not in rendered
    assert "graph-first research loop" in rendered
    assert "research_journal.md" in rendered


def test_tsla_replay_fixture_keeps_broad_failed_search_as_frontier_facts(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-third-party-replay", tmp_path / "research")
    ni.write_discovery(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())

    for index in range(6):
        branch = ni.init_branch_dir(session, f"ema-candidate-{index + 1}")
        spec = ni.load_branch_spec(branch)
        spec.update(
            {
                "evidence_intent": "candidate",
                "input_claim": "graph_supported",
                "mechanism_family": "target_ema",
                "invalidation_condition": "No auxiliary driver reads or no positive holdout IC.",
                "requested_start": "2020-01-01",
                "selected_drivers": ["AAPL"],
            }
        )
        _record_synthetic_round(
            session,
            branch,
            spec=spec,
            result=_edge_result(traced_inputs=[], sharpe=2.35),
        )

    control = ni.init_branch_dir(session, "target-ema-control")
    control_spec = ni.load_branch_spec(control)
    control_spec.update(
        {
            "hypothesis": "TSLA target EMA momentum persists over the next daily bar.",
            "evidence_intent": "control",
            "input_claim": "target_only",
            "mechanism_family": "target_ema",
            "invalidation_condition": "Target-only validation loses positive IC.",
            "requested_start": "2020-01-01",
        }
    )
    _record_synthetic_round(
        session,
        control,
        spec=control_spec,
        result=_edge_result(traced_inputs=[], sharpe=2.42),
    )

    draft = ni.init_branch_dir(session, "target-ema-draft")
    draft_spec = ni.load_branch_spec(draft)
    draft_spec.update(
        {
            "hypothesis": "TSLA target EMA momentum may persist over the next daily bar.",
            "evidence_intent": "draft",
            "input_claim": "target_only",
            "mechanism_family": "target_ema",
            "requested_start": "2020-01-01",
        }
    )
    _record_synthetic_round(
        session,
        draft,
        spec=draft_spec,
        result=_edge_result(traced_inputs=[], sharpe=2.18),
    )

    blocker = ni.init_branch_dir(session, "runtime-blocker")
    blocker_spec = ni.load_branch_spec(blocker)
    blocker_spec.update(
        {
            "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "No AAPL reads or negative holdout IC.",
            "requested_start": "2020-01-01",
            "selected_drivers": ["AAPL"],
        }
    )
    _record_synthetic_round(
        session,
        blocker,
        spec=blocker_spec,
        result=_edge_result(verdict="ERROR"),
        result_path_override="branches/runtime-blocker/outputs/missing-edge-result.json",
    )

    ni.render_session(session)
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    session_text = (session / "README.md").read_text(encoding="utf-8").lower()
    frontier_text = (session / ni.FRONTIER_MARKDOWN_FILENAME).read_text(encoding="utf-8").lower()

    labels = frontier["evidence_label_counts"]
    assert labels.get("candidate_causal_evidence", 0) == 0
    assert labels["protocol_incomplete"] == 7
    assert labels["target_control_evidence"] == 1
    assert labels["workflow_blocker"] == 1
    assert frontier["mechanism_family_counts"]["target_ema"] == 8
    assert frontier["driver_reads"] == []

    high_sharpe_rows = [row for row in ledger["rows"] if float(row["sharpe"] or 0) > 2.0]
    assert {row["evidence_label"] for row in high_sharpe_rows} == {
        "protocol_incomplete",
        "target_control_evidence",
    }
    assert all(
        row["evidence_label"] != "candidate_causal_evidence"
        for row in ledger["rows"]
        if row["declared_input_claim"] == "target_only"
    )
    forbidden = [
        "try next",
        "recommend",
        "open a sibling",
        "resume `",
        "next branch",
        "proxy",
        "threshold",
    ]
    assert not any(term in session_text for term in forbidden)
    assert not any(term in frontier_text for term in forbidden)


def test_build_branch_context_prefers_prepared_runtime_inputs(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v2", tmp_path / "research")
    discovery = _sample_discovery()
    readiness = _sample_readiness()
    ni.write_discovery(session, discovery)
    ni.write_readiness(session, readiness)
    branch = ni.init_branch_dir(session, "graph-v1")

    spec = ni.load_branch_spec(branch)
    spec["target"] = "TSLA"
    spec["selected_drivers"] = ["AAPL", "MSFT"]
    ni.write_branch_spec(branch, spec)
    _write_runtime_files(branch)

    context = ni.build_branch_context(
        branch=branch,
        session=session,
        discovery=discovery,
        readiness=readiness,
        round_id="round-001",
        backtest_start="2020-01-01",
    )

    assert context["runtime_profile"]["execution_delay_bars"] == 2
    assert context["_execution_constraints"]["position_bounds"] == [-0.5, 0.5]
    assert sorted(context["_feeds"].keys()) == ["AAPL", "MSFT", "primary"]
    assert context["_feeds"]["AAPL"]["symbol"] == "AAPL"
    assert context["data_manifest"]["selected_drivers"] == ["AAPL", "MSFT"]
    assert context["branch_declaration"]["evidence_intent"] == "draft"
