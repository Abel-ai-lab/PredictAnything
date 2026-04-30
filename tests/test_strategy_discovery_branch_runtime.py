from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from abel_invest.narrative_core import session_lifecycle
import strategy_discovery_api as ni


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


def test_evidence_runtime_facts_prefers_edge_contract() -> None:
    result = _edge_result(traced_inputs=[])
    result["runtime_facts"] = {
        "contract": "abel-edge.runtime-facts/v1",
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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")

    spec = ni.load_branch_spec(branch)
    spec["target"] = "TSLA"
    spec["requested_start"] = "2020-01-01"
    spec["selected_inputs"] = ["AAPL", "MSFT", "AAPL", "msft"]
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
    assert dependencies["selected_inputs"] == ["AAPL", "MSFT"]
    assert dependencies["selected_graph_nodes"] == ["AAPL.price", "MSFT.price"]
    assert data_manifest["selected_inputs"] == ["AAPL", "MSFT"]
    assert data_manifest["selected_graph_nodes"] == ["AAPL.price", "MSFT.price"]
    assert data_manifest["target_node"] == "TSLA.price"
    assert "selected_drivers" not in branch_spec
    assert "selected_drivers" not in dependencies
    assert "selected_drivers" not in data_manifest
    assert [feed["name"] for feed in data_manifest["feeds"]] == ["primary", "AAPL", "MSFT"]
    assert [feed["graph_node_id"] for feed in data_manifest["feeds"]] == [
        "TSLA.price",
        "AAPL.price",
        "MSFT.price",
    ]
    assert probe_samples["target"] == "TSLA"
    assert len(probe_samples["sample_decision_dates"]) >= 2
    assert "DecisionContext" in context_guide


def test_default_branch_spec_starts_as_graph_first_draft_declaration(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-decl", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
    assert spec["target_node"] == "TSLA.price"
    assert spec["selected_inputs"] == [
        {"node_id": "AAPL.price", "role": "graph_input", "source": "frontier"},
        {"node_id": "MSFT.price", "role": "graph_input", "source": "frontier"},
    ]
    assert "suggested_inputs" not in spec
    assert ni.branch_selected_inputs(spec) == ["AAPL", "MSFT"]
    assert ni.branch_selected_graph_nodes(spec) == ["AAPL.price", "MSFT.price"]
    assert "selected_drivers" not in spec
    assert status["protocol_complete"] is False
    assert "hypothesis" in status["protocol_gaps"]
    assert "evidence_intent:draft" in status["protocol_gaps"]
    assert status["selected_graph_nodes"] == ["AAPL.price", "MSFT.price"]


def test_branch_spec_preserves_structured_external_graph_inputs(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-external-input", tmp_path / "research")
    branch = ni.init_branch_dir(session, "external-v1")

    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = [
        {
            "asset": "SPY",
            "field": "volume",
            "role": "control",
            "source": "external",
            "source_reason": "agent selected a market-liquidity control outside current frontier",
        },
        {"node_id": "SPY.volume", "source": "external"},
    ]
    ni.write_branch_spec(branch, spec)

    stored = ni.load_branch_spec(branch)

    assert stored["selected_inputs"] == [
        {
            "node_id": "SPY.volume",
            "role": "control",
            "source": "external",
            "source_reason": "agent selected a market-liquidity control outside current frontier",
        }
    ]
    assert ni.branch_selected_inputs(stored) == ["SPY"]
    assert ni.branch_selected_graph_nodes(stored) == ["SPY.volume"]


def test_default_branch_spec_stays_target_only_when_discovery_is_pending(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-decl-pending", tmp_path / "research")
    branch = ni.init_branch_dir(session, "fallback-v1")

    spec = ni.load_branch_spec(branch)

    assert spec["evidence_intent"] == "draft"
    assert spec["input_claim"] == "target_only"
    assert "source_type" not in spec
    assert "method_family" not in spec
    assert spec["selected_inputs"] == []
    assert spec["selected_inputs"] == []


def test_init_session_cli_runs_live_discovery_by_default(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    calls: list[tuple[str, int]] = []

    def fake_fetch_live_graph_frontier(ticker: str, *, limit: int, backtest_start: str) -> dict:
        calls.append((ticker, limit))
        return ni.graph_frontier_from_discovery_payload(
            _sample_discovery(),
            backtest_start=backtest_start,
            expansion_mode="all",
            expansion_limit=limit,
        )

    monkeypatch.setattr(session_lifecycle, "fetch_live_discovery", fake_fetch_live_discovery)
    monkeypatch.setattr(session_lifecycle, "refresh_data_readiness", lambda **_kwargs: _sample_readiness())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abel-invest",
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
    frontier = json.loads(
        (tmp_path / "research" / "tsla" / "tsla-cli-default" / ni.GRAPH_FRONTIER_FILENAME).read_text(
            encoding="utf-8"
        )
    )

    assert calls == [("TSLA", 10)]
    assert frontier["source"] == "abel_live"
    assert len(frontier["nodes"]) == 3
    assert not (tmp_path / "research" / "tsla" / "tsla-cli-default" / "discovery.json").exists()
    assert "frontier_source: abel_live (nodes=3)" in out


def test_init_session_cli_no_discover_is_explicit_pending_fallback(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    def fail_fetch_live_graph_frontier(*_args, **_kwargs) -> dict:
        raise AssertionError("live discovery should not run with --no-discover")

    monkeypatch.setattr(session_lifecycle, "fetch_live_discovery", fail_fetch_live_discovery)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abel-invest",
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
    frontier = json.loads(
        (tmp_path / "research" / "tsla" / "tsla-cli-pending" / ni.GRAPH_FRONTIER_FILENAME).read_text(
            encoding="utf-8"
        )
    )

    assert frontier["source"] == "pending"
    assert frontier["nodes"][0]["node_id"] == "TSLA.price"
    assert not (tmp_path / "research" / "tsla" / "tsla-cli-pending" / "discovery.json").exists()
    assert "frontier_source: pending (live discovery not run)" in out


def test_complete_branch_declaration_requires_selected_inputs(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-decl-complete", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
            "selected_inputs": ["AAPL", "MSFT"],
        }
    )

    status = ni.branch_declaration_status(spec)

    assert status["protocol_complete"] is True
    assert status["selected_inputs"] == ["AAPL", "MSFT"]


def test_removed_source_type_and_method_family_do_not_complete_declaration() -> None:
    spec = {
        "source_type": "causal",
        "method_family": "graph",
        "hypothesis": "AAPL driver strength leads TSLA next-day risk appetite.",
        "invalidation_condition": "AAPL reads disappear or validation fails repeatedly.",
        "requested_start": "2020-01-01",
        "selected_inputs": ["AAPL"],
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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "selected_inputs": ["AAPL", "MSFT"],
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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
            "selected_inputs": ["AAPL"],
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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
            "selected_inputs": ["AAPL"],
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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
            "selected_inputs": ["AAPL", "MSFT"],
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


def test_evidence_rows_record_graph_node_runtime_facts(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-graph-node-runtime", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-node-v1")
    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "hypothesis": "AAPL price and MSFT volume pressure leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "invalidation_condition": "Prepared graph nodes are not read or validation fails.",
            "requested_start": "2020-01-01",
            "selected_inputs": [
                {"node_id": "AAPL.price", "role": "graph_input", "source": "frontier"},
                {"node_id": "MSFT.volume", "role": "graph_input", "source": "frontier"},
            ],
        }
    )
    _record_synthetic_round(
        session,
        branch,
        spec=spec,
        result=_edge_result(traced_inputs=["MSFT"]),
    )

    ni.render_session(session)
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    row = ledger["rows"][-1]

    assert row["evidence_label"] == "candidate_causal_evidence"
    assert row["declared_selected_inputs"] == ["AAPL", "MSFT"]
    assert row["declared_selected_graph_nodes"] == ["AAPL.price", "MSFT.volume"]
    assert row["prepared_selected_graph_nodes"] == ["AAPL.price", "MSFT.volume"]
    assert row["prepared_traced_graph_nodes"] == ["MSFT.volume"]
    assert row["actual_graph_node_reads"] == ["MSFT.volume"]
    assert row["actual_graph_node_read_source"] == "asset_read_mapping"
    assert row["graph_node_read_gap"] is False
    assert row["input_realization"]["selected_graph_node_reads"] == ["MSFT.volume"]
    assert frontier["graph_node_reads"] == ["MSFT.volume"]


def test_frontier_surfaces_candidate_failures_and_resume_facts(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-frontier-fail-facts", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
            "selected_inputs": ["AAPL", "MSFT", "AAPL"],
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
    assert "candidate_causal_evidence.FAIL: `6`" in frontier_text
    assert "## Research Journal" in context_text
    assert "## Research Reflection" in context_text
    assert "## Input Realization" in context_text
    forbidden = ["try next", "recommend", "open a sibling", "switch mechanism"]
    assert not any(term in frontier_text.lower() for term in forbidden)
    assert not any(term in context_text.lower() for term in forbidden)


def test_init_session_creates_research_journal(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-journal-init", tmp_path / "research")

    journal_path = session / ni.RESEARCH_JOURNAL_FILENAME
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert journal_path.exists()
    journal_text = journal_path.read_text(encoding="utf-8")
    assert "agent-owned research notes" in journal_text
    assert ni.JOURNAL_GENERATED_HEADER_END in journal_text
    assert "## Research Journal" in context_text
    assert "## Journal Coverage" in context_text
    assert "- evidence_reference_count: `0`" in context_text
    assert "- has_evidence_linked_update: `false`" in context_text
    assert "- recent_excerpt: `none`" in context_text


def test_agent_context_reads_evidence_linked_research_journal(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-journal-linked", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
            "selected_inputs": ["AAPL"],
            "selected_inputs": ["AAPL"],
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
    assert "- journal_coverage_complete: `true`" in context_text
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


def test_journal_coverage_required_after_recorded_evidence_without_round_entries(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-reflection-due", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    branch_a = ni.init_branch_dir(session, "momentum-parents")
    branch_b = ni.init_branch_dir(session, "regime-parents")
    spec_a = ni.load_branch_spec(branch_a)
    spec_a.update(
        {
            "hypothesis": "AAPL and MSFT driver momentum leads TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "model_family": "rule_signal",
            "complexity_class": "simple_signal",
            "exploration_role": "candidate",
            "invalidation_condition": "Driver reads disappear or validation fails repeatedly.",
            "requested_start": "2020-01-01",
            "selected_inputs": ["AAPL", "MSFT"],
        }
    )
    spec_b = ni.load_branch_spec(branch_b)
    spec_b.update(
        {
            "hypothesis": "AAPL and MSFT driver regimes lead TSLA next-day risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_regime",
            "model_family": "tree_model",
            "complexity_class": "regime",
            "exploration_role": "candidate",
            "invalidation_condition": "Driver reads disappear or validation fails repeatedly.",
            "requested_start": "2020-01-01",
            "selected_inputs": ["AAPL", "MSFT"],
        }
    )

    for index in range(5):
        _record_synthetic_round(
            session,
            branch_a,
            spec=spec_a,
            result=_edge_result(traced_inputs=["AAPL", "MSFT"], verdict="FAIL"),
            round_id=f"round-{index + 1:03d}",
            decision="discard",
            changed_dimensions=[] if index == 0 else ["window"],
        )
    _record_synthetic_round(
        session,
        branch_b,
        spec=spec_b,
        result=_edge_result(traced_inputs=["AAPL", "MSFT"], verdict="FAIL"),
        decision="discard",
    )

    ni.render_session(session)
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert frontier["graph_priority"]["graph_first_uncovered"] is False
    assert frontier["exploration_breadth"]["branch_family_count"] == 2
    reflection = frontier["research_reflection"]
    assert reflection["research_reflection_due"] is True
    assert reflection["recorded_round_count"] == 6
    assert reflection["journal_coverage_complete"] is False
    assert reflection["missing_journal_round_count"] == 6
    assert reflection["evidence_linked_journal_update"] is False
    assert frontier["journal_coverage"] == {
        "recorded_round_count": 6,
        "journaled_round_count": 0,
        "journal_coverage_complete": False,
        "missing_journal_rounds": [
            "momentum-parents:round-001",
            "momentum-parents:round-002",
            "momentum-parents:round-003",
            "momentum-parents:round-004",
            "momentum-parents:round-005",
            "regime-parents:round-001",
        ],
    }
    assert "research_reflection_due: `true`" in context_text
    assert "journal_coverage_complete: `false`" in context_text
    assert "same_driver_set_concentration" not in json.dumps(frontier)
    assert "pivot_checkpoint" not in frontier
    assert ni.journal_coverage_warning_lines(session) == [
        "journal_coverage_complete=false "
        "missing_journal_rounds=momentum-parents:round-001, momentum-parents:round-002, momentum-parents:round-003, momentum-parents:round-004, momentum-parents:round-005, regime-parents:round-001 "
        "required_action=update_research_journal.md_with_round_insights"
    ]

    (session / ni.RESEARCH_JOURNAL_FILENAME).write_text(
        "# Research Journal\n\n## Notes\n\n"
        "- The first momentum attempt failed; ledger:momentum-parents:round-001\n"
        "- Window change still failed; ledger:momentum-parents:round-002\n"
        "- Window change still failed; ledger:momentum-parents:round-003\n"
        "- Window change still failed; ledger:momentum-parents:round-004\n"
        "- Window change still failed; ledger:momentum-parents:round-005\n"
        "- Regime branch also failed; ledger:regime-parents:round-001\n",
        encoding="utf-8",
    )
    ni.render_session(session)
    updated = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))

    assert updated["research_reflection"]["research_reflection_due"] is False
    assert updated["research_reflection"]["evidence_linked_journal_update"] is True
    assert updated["journal_coverage"]["journal_coverage_complete"] is True


def test_exploration_breadth_marks_single_branch_local_refinement(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-breadth-local", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
            "selected_inputs": ["AAPL"],
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
    assert exploration["same_branch_max_rounds"] == 6
    assert exploration["exploration_class_counts"]["broad_explore"] == 1
    assert exploration["exploration_class_counts"]["local_refinement"] == 5
    assert ledger["rows"][-1]["same_neighborhood_failed_rows"] == 5
    assert "research_reflection_due: `true`" in context_text


def test_distinct_driver_sets_are_factual_not_checkpoint_reasons(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-breadth-second-family", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
            "selected_inputs": ["AAPL"],
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
            "selected_inputs": ["MSFT"],
            "selected_inputs": ["MSFT"],
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
    assert frontier["exploration_breadth"]["model_family_counts"]["linear_model"] == 1
    assert frontier["input_breadth"]["candidate_driver_set_count"] == 2
    assert frontier["research_reflection"]["research_reflection_due"] is True
    assert "pivot_checkpoint" not in frontier
    assert "same_driver_set_concentration" not in json.dumps(frontier)


def test_input_breadth_reports_candidate_driver_set_coverage(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-input-breadth", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    graph_branch = ni.init_branch_dir(session, "graph-aapl")
    graph_spec = _complete_candidate_spec(graph_branch, selected_inputs=["AAPL"])
    target_branch = ni.init_branch_dir(session, "target-control")
    target_spec = _complete_candidate_spec(
        target_branch,
        selected_inputs=[],
        mechanism_family="target_momentum",
    )
    target_spec["input_claim"] = "target_only"
    target_spec["selected_inputs"] = []
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


def test_research_reflection_and_input_realization_for_empty_workspace_9_shape(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-empty-workspace-9-shape", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())

    graph_read = ni.init_branch_dir(session, "tree-graph")
    graph_read_spec = _complete_candidate_spec(
        graph_read,
        selected_inputs=["AAPL", "MSFT"],
        mechanism_family="tree_ml_direction",
        model_family="tree_model",
        complexity_class="learned_model",
    )
    graph_gap = ni.init_branch_dir(session, "momentum-regime")
    graph_gap_spec = _complete_candidate_spec(
        graph_gap,
        selected_inputs=["AAPL", "MSFT"],
        mechanism_family="momentum_regime",
        complexity_class="regime",
    )
    target_one = ni.init_branch_dir(session, "target-momentum")
    target_one_spec = _complete_candidate_spec(
        target_one,
        selected_inputs=[],
        mechanism_family="target_momentum",
    )
    target_one_spec["input_claim"] = "target_only"
    target_one_spec["selected_inputs"] = []
    target_two = ni.init_branch_dir(session, "target-ensemble")
    target_two_spec = _complete_candidate_spec(
        target_two,
        selected_inputs=[],
        mechanism_family="target_ensemble",
        model_family="hybrid",
        complexity_class="hybrid",
    )
    target_two_spec["input_claim"] = "target_only"
    target_two_spec["selected_inputs"] = []

    _record_synthetic_round(
        session,
        graph_read,
        spec=graph_read_spec,
        result=_edge_result(traced_inputs=["AAPL", "MSFT"], verdict="FAIL"),
        decision="discard",
    )
    _record_synthetic_round(
        session,
        graph_gap,
        spec=graph_gap_spec,
        result=_edge_result(traced_inputs=[], verdict="FAIL"),
        decision="discard",
    )
    _record_synthetic_round(
        session,
        target_one,
        spec=target_one_spec,
        result=_edge_result(traced_inputs=[], verdict="FAIL"),
        decision="discard",
    )
    _record_synthetic_round(
        session,
        target_two,
        spec=target_two_spec,
        result=_edge_result(traced_inputs=[], verdict="FAIL"),
        decision="discard",
    )

    ni.render_session(session)
    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    frontier_text = (session / ni.FRONTIER_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    labels = frontier["evidence_label_counts"]
    assert labels["candidate_causal_evidence"] == 1
    assert labels["target_control_evidence"] == 3
    assert frontier["research_reflection"]["research_reflection_due"] is True
    assert frontier["research_reflection"]["recorded_round_count"] == 4
    assert frontier["input_realization"] == {
        "declared_graph_supported_rounds": 2,
        "realized_graph_supported_rounds": 1,
        "graph_input_read_gap_count": 1,
        "graph_input_read_gap_rows": ["momentum-regime:round-001"],
    }

    gap_row = next(row for row in ledger["rows"] if row["branch_id"] == "momentum-regime")
    assert gap_row["evidence_label"] == "target_control_evidence"
    assert gap_row["input_realization"]["graph_input_read_gap"] is True
    assert gap_row["input_realization"]["realized_input_claim"] == "target_only"
    assert "research_reflection_due: `true`" in frontier_text
    assert "graph_input_read_gap_count: `1`" in context_text
    assert "pivot_checkpoint" not in json.dumps(frontier)


def test_input_breadth_remains_factual_without_route_warning(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-input-breadth-warning", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    graph_branch = ni.init_branch_dir(session, "graph-aapl")
    graph_spec = _complete_candidate_spec(graph_branch, selected_inputs=["AAPL"])
    target_branch = ni.init_branch_dir(session, "target-control")
    target_spec = _complete_candidate_spec(target_branch, selected_inputs=[])
    target_spec["input_claim"] = "target_only"
    target_spec["selected_inputs"] = []
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
    assert "input_breadth_thin=true" not in "\n".join(
        ni.journal_coverage_warning_lines(session)
    )

    msft_branch = ni.init_branch_dir(session, "graph-msft")
    msft_spec = _complete_candidate_spec(msft_branch, selected_inputs=["MSFT"])
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


def test_graph_priority_warns_when_graph_candidates_are_uncovered(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-graph-uncovered", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    target_branch = ni.init_branch_dir(session, "target-control")
    target_spec = _complete_candidate_spec(target_branch, selected_inputs=[])
    target_spec["input_claim"] = "target_only"
    target_spec["selected_inputs"] = []
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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "mixed-aapl")
    spec = _complete_candidate_spec(branch, selected_inputs=["AAPL"])
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
    target_spec = _complete_candidate_spec(target_branch, selected_inputs=[])
    target_spec["input_claim"] = "target_only"
    target_spec["selected_inputs"] = []
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


def test_debug_rows_do_not_count_as_recorded_candidate_rounds(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-breadth-debug", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
    assert exploration["dominant_neighborhood_rows"] == 3
    assert exploration["dominant_evidence_neighborhood_rows"] == 4


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
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
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
                "selected_inputs": ["AAPL"],
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
            "selected_inputs": ["AAPL"],
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


def test_prepare_branch_inputs_passes_csv_adapter_and_path(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1-csv", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "baseline-v1")

    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "timestamp,symbol,close\n"
        "2020-01-01T00:00:00Z,TSLA,100\n"
        "2020-01-02T00:00:00Z,TSLA,101\n",
        encoding="utf-8",
    )

    spec = ni.load_branch_spec(branch)
    spec["target_asset"] = "TSLA"
    spec["target_node"] = "TSLA.price"
    spec["requested_start"] = "2020-01-01"
    spec["selected_inputs"] = []
    spec["source_type"] = "baseline"
    spec["method_family"] = "rule"
    spec["data_requirements"] = {
        "timeframe": "1d",
        "adapter": "csv",
        "path": str(csv_path),
    }
    ni.write_branch_spec(branch, spec)

    calls = []

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None):
        calls.append(list(command))
        output_path = Path(command[command.index("--output-json") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "adapter": "csv",
                    "path": str(csv_path),
                    "timeframe": "1d",
                    "profile": "daily",
                    "results": [
                        {
                            "symbol": "TSLA",
                            "ok": True,
                            "row_count": 150,
                            "available_range": {"start": "2020-01-01", "end": "2020-12-31"},
                        }
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
    assert "--adapter" in calls[0]
    assert calls[0][calls[0].index("--adapter") + 1] == "csv"
    assert "--path" in calls[0]
    assert calls[0][calls[0].index("--path") + 1] == str(csv_path)

    data_manifest = json.loads(ni.data_manifest_path(branch).read_text(encoding="utf-8"))
    assert data_manifest["feeds"][0]["adapter"] == "csv"
    assert data_manifest["feeds"][0]["path"] == str(csv_path)


def test_build_branch_context_prefers_prepared_runtime_inputs(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v2", tmp_path / "research")
    discovery = _sample_discovery()
    readiness = _sample_readiness()
    ni.write_graph_frontier_from_discovery_payload(session, discovery)
    ni.write_readiness(session, readiness)
    branch = ni.init_branch_dir(session, "graph-v1")

    spec = ni.load_branch_spec(branch)
    spec["target"] = "TSLA"
    spec["selected_inputs"] = ["AAPL", "MSFT"]
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
    assert context["data_manifest"]["selected_inputs"] == ["AAPL", "MSFT"]
    assert context["branch_declaration"]["evidence_intent"] == "draft"


def test_build_branch_context_preserves_csv_feed_path(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v2-csv", tmp_path / "research")
    discovery = _sample_discovery()
    readiness = _sample_readiness()
    ni.write_graph_frontier_from_discovery_payload(session, discovery)
    ni.write_readiness(session, readiness)
    branch = ni.init_branch_dir(session, "graph-v1")

    spec = ni.load_branch_spec(branch)
    spec["target"] = "TSLA"
    spec["selected_inputs"] = []
    ni.write_branch_spec(branch, spec)
    _write_runtime_files(branch)

    csv_path = str(tmp_path / "bars.csv")
    dependencies = json.loads(ni.dependencies_path(branch).read_text(encoding="utf-8"))
    dependencies["cache"]["adapter"] = "csv"
    dependencies["cache"]["path"] = csv_path
    ni.dependencies_path(branch).write_text(json.dumps(dependencies), encoding="utf-8")

    data_manifest = json.loads(ni.data_manifest_path(branch).read_text(encoding="utf-8"))
    data_manifest["feeds"] = [
        {
            **data_manifest["feeds"][0],
            "adapter": "csv",
            "path": csv_path,
        }
    ]
    ni.data_manifest_path(branch).write_text(json.dumps(data_manifest), encoding="utf-8")

    context = ni.build_branch_context(
        branch=branch,
        session=session,
        discovery=discovery,
        readiness=readiness,
        round_id="round-001",
        backtest_start="2020-01-01",
    )

    assert context["_feeds"]["primary"]["adapter"] == "csv"
    assert context["_feeds"]["primary"]["path"] == csv_path


def test_build_branch_context_includes_experiment_metadata(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v4-context", tmp_path / "research")
    discovery = _sample_discovery()
    readiness = _sample_readiness()
    ni.write_graph_frontier_from_discovery_payload(session, discovery)
    ni.write_readiness(session, readiness)
    branch = ni.init_branch_dir(session, "graph-v1")

    spec = ni.load_branch_spec(branch)
    spec["target"] = "TSLA"
    spec["requested_start"] = "2020-01-01"
    spec["selected_inputs"] = ["AAPL", "MSFT"]
    ni.write_branch_spec(branch, spec)
    _write_runtime_files(branch)

    monkeypatch.setenv("ABEL_EXPERIMENT_PROTOCOL_ID", "alpha-exec-sandbox-v1")
    monkeypatch.setenv("ABEL_EXPERIMENT_MODE", "baseline")
    monkeypatch.setenv("ABEL_EXPERIMENT_ROUND_BUDGET", "10")
    monkeypatch.setenv("ABEL_SKILLS_COMMIT", "skills-sha-123")
    monkeypatch.setenv("ABEL_EDGE_COMMIT", "edge-sha-456")

    context = ni.build_branch_context(
        branch=branch,
        session=session,
        discovery=discovery,
        readiness=readiness,
        round_id="round-001",
        backtest_start="2020-01-01",
    )

    assert context["experiment"] == {
        "protocol_id": "alpha-exec-sandbox-v1",
        "experiment_mode": "baseline",
        "round_budget": "10",
        "abel_skills_commit": "skills-sha-123",
        "abel_edge_commit": "edge-sha-456",
    }


def test_round_experiment_metadata_returns_blank_shape_when_context_is_missing(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v5-context-shape", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")

    assert ni.round_experiment_metadata(branch, "round-001") == {
        "protocol_id": "",
        "experiment_mode": "",
        "round_budget": "",
        "abel_skills_commit": "",
        "abel_edge_commit": "",
    }
