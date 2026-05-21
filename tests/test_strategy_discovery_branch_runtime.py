from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from abel_invest.narrative_core import session_lifecycle
from abel_invest.narrative_core.evidence import graph_frontier
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


def test_default_branch_spec_starts_with_graph_enriched_candidate_context(tmp_path) -> None:
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

    monkeypatch.setattr(graph_frontier, "fetch_live_graph_frontier", fake_fetch_live_graph_frontier)
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
            "--allow-outside-workspace",
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

    monkeypatch.setattr(graph_frontier, "fetch_live_graph_frontier", fail_fetch_live_graph_frontier)
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
            "--allow-outside-workspace",
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
    dsr_rows = _read_jsonl(session / "dsr_trials.jsonl")
    assert len(dsr_rows) == 1
    assert dsr_rows[0]["run_type"] == "round"
    assert dsr_rows[0]["runtime_stage"] == "data_access"
    assert dsr_rows[0]["counted_for_future_dsr"] is False
    assert dsr_rows[0]["alpha_declared_count"] == 1
    assert dsr_rows[0]["edge_k"] is None
    assert dsr_rows[0]["edge_dsr_trials_used"] is None
    assert dsr_rows[0]["edge_k_source"] == "not_available"

    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    row = ledger["rows"][-1]
    assert row["evidence_label"] == "workflow_blocker"
    assert row["runtime_stage"] == "data_access"
    assert row["workflow_status"] == "not_completed"
    path_text = (session / "exploration_path.md").read_text(encoding="utf-8")
    assert "ledger:graph-v1:round-001" in path_text
    assert "network failure round" in path_text
    assert "ERROR" in path_text


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


def test_run_branch_round_records_dsr_k_accounting(tmp_path, monkeypatch, capsys) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dsr-k-audit", tmp_path / "research")
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
            json.dumps(
                _edge_result(
                    traced_inputs=["AAPL"],
                    k=4,
                    current_round_trials=4,
                )
            ),
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
            description="parameter sweep selected output",
            input_note="",
            hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
            expected_signal="",
            trigger="test",
            change_summary="test",
            changed_dimension=["thresholds"],
            selection_trials=4,
            time_spent_min="1",
            summary="",
            next_step="",
            action=[],
            python_bin=None,
        )
    )

    assert result == 0
    captured = capsys.readouterr()
    assert "Selection-trials audit" in captured.err
    assert "does not by itself validate raw sweep winners" in captured.err

    dsr_rows = _read_jsonl(session / "dsr_trials.jsonl")
    assert len(dsr_rows) == 1
    dsr_row = dsr_rows[0]
    assert dsr_row["event"] == "edge_dsr_accounting_recorded"
    assert dsr_row["run_type"] == "round"
    assert dsr_row["branch_id"] == "graph-v1"
    assert dsr_row["round_id"] == "round-001"
    assert dsr_row["verdict"] == "PASS"
    assert dsr_row["runtime_stage"] == "validation"
    assert dsr_row["counted_for_future_dsr"] is True
    assert dsr_row["alpha_declared_count"] == 4
    assert dsr_row["alpha_current_round_trials"] == 4
    assert dsr_row["alpha_prior_effective_trials"] == 0
    assert dsr_row["edge_k"] == 4
    assert dsr_row["edge_dsr_trials_used"] == 4
    assert dsr_row["edge_k_source"] == "alpha_context"
    assert dsr_row["engine_ast_k"] == 1

    round_note = (branch / "rounds" / "round-001.md").read_text(encoding="utf-8")
    assert "- K: `4`" in round_note
    assert "- dsr_trials_used: `4`" in round_note
    assert "- K_source: `alpha_context`" in round_note
    assert "- current_round_trials: `4`" in round_note

    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    accounting = ledger["rows"][-1]["dsr_accounting"]
    assert accounting["edge_k"] == 4
    assert accounting["alpha_current_round_trials"] == 4
    assert accounting["counted_for_future_dsr"] is True


def test_run_branch_round_audits_edge_k_before_alpha_decision(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dsr-decision-audit", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    _write_runtime_files(branch)
    ni.write_branch_spec(branch, _complete_candidate_spec(branch))

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None):
        result_path = Path(command[command.index("--output-json") + 1])
        report_path = Path(command[command.index("--output-md") + 1])
        handoff_path = Path(command[command.index("--output-handoff") + 1])
        result_path.write_text(
            json.dumps(_edge_result(traced_inputs=["AAPL"], k=5, current_round_trials=5)),
            encoding="utf-8",
        )
        report_path.write_text("# validation\n", encoding="utf-8")
        handoff_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def fail_decision(rows, result, *, session=None):
        raise RuntimeError("decision failed after edge result")

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)
    monkeypatch.setitem(ni.run_branch_round.__globals__, "alpha_decision", fail_decision)

    try:
        ni.run_branch_round(
            Namespace(
                branch=str(branch),
                mode="explore",
                description="decision failure after edge result",
                input_note="",
                hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
                expected_signal="",
                trigger="test",
                change_summary="test",
                changed_dimension=["thresholds"],
                selection_trials=5,
                time_spent_min="1",
                summary="",
                next_step="",
                action=[],
                python_bin=None,
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "decision failed after edge result"
    else:
        raise AssertionError("expected alpha_decision failure")

    dsr_rows = _read_jsonl(session / "dsr_trials.jsonl")
    assert len(dsr_rows) == 1
    assert dsr_rows[0]["alpha_declared_count"] == 5
    assert dsr_rows[0]["edge_k"] == 5


def test_debug_branch_records_dsr_k_accounting_without_future_count(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dsr-debug-audit", tmp_path / "research")
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
        result_path.write_text(
            json.dumps(_edge_result(traced_inputs=["AAPL"], k=1)),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)

    result = ni.debug_branch_run(Namespace(branch=str(branch), python_bin=None))

    assert result == 0
    dsr_rows = _read_jsonl(session / "dsr_trials.jsonl")
    assert len(dsr_rows) == 1
    dsr_row = dsr_rows[0]
    assert dsr_row["run_type"] == "debug"
    assert dsr_row["round_id"] == "debug"
    assert dsr_row["verdict"] == "PASS"
    assert dsr_row["runtime_stage"] == "validation"
    assert dsr_row["counted_for_future_dsr"] is False
    assert dsr_row["alpha_declared_count"] == 1
    assert dsr_row["edge_k"] == 1


def test_failed_validation_round_counts_for_future_dsr_accounting(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dsr-fail-audit", tmp_path / "research")
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
            json.dumps(
                _edge_result(
                    traced_inputs=["AAPL"],
                    verdict="FAIL",
                    k=2,
                    current_round_trials=2,
                )
            ),
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
            description="failed parameter sweep output",
            input_note="",
            hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
            expected_signal="",
            trigger="test",
            change_summary="test",
            changed_dimension=["thresholds"],
            selection_trials=2,
            time_spent_min="1",
            summary="",
            next_step="",
            action=[],
            python_bin=None,
        )
    )

    assert result == 0
    dsr_row = _read_jsonl(session / "dsr_trials.jsonl")[0]
    assert dsr_row["verdict"] == "FAIL"
    assert dsr_row["runtime_stage"] == "validation"
    assert dsr_row["counted_for_future_dsr"] is True
    assert dsr_row["alpha_declared_count"] == 2
    assert dsr_row["edge_k"] == 2


def test_semantic_error_round_records_dsr_k_accounting_without_future_count(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dsr-semantic-audit", tmp_path / "research")
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
        payload = _edge_result(
            traced_inputs=["AAPL"],
            verdict="ERROR",
            k=3,
            current_round_trials=3,
        )
        payload["diagnostics"]["runtime_stage"] = "semantic_preflight"
        payload["runtime_facts"]["runtime_stage"] = "semantic_preflight"
        payload["runtime_facts"]["semantic_verdict"] = "ERROR"
        payload["semantic"]["verdict"] = "ERROR"
        result_path.write_text(json.dumps(payload), encoding="utf-8")
        report_path.write_text("# validation\n", encoding="utf-8")
        handoff_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)

    result = ni.run_branch_round(
        Namespace(
            branch=str(branch),
            mode="explore",
            description="semantic blocker selected output",
            input_note="",
            hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
            expected_signal="",
            trigger="test",
            change_summary="test",
            changed_dimension=["implementation"],
            selection_trials=3,
            time_spent_min="1",
            summary="",
            next_step="",
            action=[],
            python_bin=None,
        )
    )

    assert result == 0
    dsr_row = _read_jsonl(session / "dsr_trials.jsonl")[0]
    assert dsr_row["verdict"] == "ERROR"
    assert dsr_row["runtime_stage"] == "semantic_preflight"
    assert dsr_row["counted_for_future_dsr"] is False
    assert dsr_row["alpha_declared_count"] == 3
    assert dsr_row["edge_k"] == 3


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
    assert "## Exploration Path" in context_text
    assert "## Input Realization" in context_text
    forbidden = ["try next", "recommend", "open a sibling", "switch mechanism"]
    assert not any(term in frontier_text.lower() for term in forbidden)
    assert not any(term in context_text.lower() for term in forbidden)


def test_init_session_uses_exploration_path_as_only_human_log(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-path-only-init", tmp_path / "research")

    journal_path = session / ni.RESEARCH_JOURNAL_FILENAME
    path = session / "exploration_path.md"
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert not journal_path.exists()
    assert path.exists()
    path_text = path.read_text(encoding="utf-8")
    assert "single human-facing exploration log" in path_text
    assert "## Exploration Path" in context_text
    assert "## Research Journal" not in context_text
    assert "- evidence_reference_count: `0`" in context_text
    assert "- path_coverage_complete: `true`" in context_text
    assert "- recent_excerpt: `none`" in context_text


def test_init_session_creates_exploration_path_prompt(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-path-init", tmp_path / "research")

    path = session / "exploration_path.md"
    assert path.exists()
    assert not (session / ni.RESEARCH_JOURNAL_FILENAME).exists()
    text = path.read_text(encoding="utf-8")
    assert "# Exploration Path" in text
    assert "single human-facing exploration log" in text
    assert "Before choosing the next Edge run" in text
    assert "chosen path" in text
    assert "Edge feedback" in text

    agent_context = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")
    assert "exploration_path.md" in agent_context
    assert "read `exploration_path.md`" in agent_context
    assert "## Research Journal" not in agent_context


def test_run_branch_round_appends_exploration_path_edge_feedback(tmp_path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "tsla-path-update", tmp_path / "research")
    ni.write_graph_frontier_from_discovery_payload(session, _sample_discovery())
    ni.write_readiness(session, _sample_readiness())
    branch = ni.init_branch_dir(session, "graph-v1")
    _write_runtime_files(branch)
    ni.write_branch_spec(branch, _complete_candidate_spec(branch))

    metric_failures = [
        {
            "metric": "position_ic",
            "message": "PositionIC 0.000 < 0.02",
            "observed": 0.0,
            "threshold": 0.02,
        },
        {
            "metric": "max_dd",
            "message": "T15 MaxDD 28.3% > 15%",
            "observed": 0.283,
            "threshold": 0.15,
        },
    ]

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None):
        result_path = Path(command[command.index("--output-json") + 1])
        report_path = Path(command[command.index("--output-md") + 1])
        handoff_path = Path(command[command.index("--output-handoff") + 1])
        result_path.write_text(
            json.dumps(
                _edge_result(
                    verdict="FAIL",
                    traced_inputs=["AAPL"],
                    sharpe=0.72,
                    metric_failures=metric_failures,
                    k=2,
                    current_round_trials=2,
                )
            ),
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
            description="test AAPL graph momentum timing",
            input_note="",
            hypothesis="AAPL driver strength leads TSLA next-day risk appetite.",
            expected_signal="",
            trigger="test",
            change_summary="switch to graph-supported AAPL momentum timing",
            changed_dimension=["drivers", "mechanism"],
            selection_trials=2,
            time_spent_min="1",
            summary="",
            next_step="try a broader graph driver if PositionIC remains weak",
            action=[],
            python_bin=None,
        )
    )

    assert result == 0
    path_text = (session / "exploration_path.md").read_text(encoding="utf-8")
    assert "ledger:graph-v1:round-001" in path_text
    assert "path: test AAPL graph momentum timing" in path_text
    assert "compact reason: AAPL driver strength leads TSLA next-day risk appetite." in path_text
    assert "AAPL driver strength leads TSLA next-day risk appetite." in path_text
    assert "Edge feedback" in path_text
    assert "FAIL" in path_text
    assert "PositionIC 0.000 < 0.02" in path_text
    assert "next implication" not in path_text


def test_agent_context_reads_evidence_linked_exploration_path(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-path-linked", tmp_path / "research")
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
        }
    )
    _record_synthetic_round(
        session,
        branch,
        spec=spec,
        result=_edge_result(traced_inputs=["AAPL"], verdict="FAIL"),
    )
    (session / "exploration_path.md").write_text(
        "# Exploration Path\n\n## Entries\n\n"
        "### graph-v1 round-001\n\n"
        "- ledger: `ledger:graph-v1:round-001`\n"
        "- path: AAPL-only graph branch\n"
        "- why: AAPL-only failed cleanly; the useful artifact is "
        "branches/graph-v1/outputs/round-001-edge-result.json.\n",
        encoding="utf-8",
    )

    ni.render_session(session)
    context_text = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert "- evidence_reference_count: `2`" in context_text
    assert "- resolved_evidence_reference_count: `2`" in context_text
    assert "- path_coverage_complete: `true`" in context_text
    assert "AAPL-only failed cleanly" in context_text


def test_exploration_path_prose_without_refs_is_not_evidence_linked(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-path-prose", tmp_path / "research")
    (session / "exploration_path.md").write_text(
        "# Exploration Path\n\n## Entries\n\nThis direction feels too narrow.\n",
        encoding="utf-8",
    )

    ni.render_session(session)
    status = ni.build_exploration_path_status(
        session,
        ledger=json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8")),
        frontier=json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8")),
    )

    assert status["evidence_reference_count"] == 0
    assert status["has_round_entries"] is False
    assert status["recent_excerpt"] == "This direction feels too narrow."


def test_path_coverage_required_after_recorded_evidence_without_round_entries(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-path-coverage-due", tmp_path / "research")
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

    assert frontier["candidate_universe"]["graph_supported_candidate_round_count"] == 6
    assert frontier["exploration_breadth"]["branch_family_count"] == 2
    assert frontier["path_coverage"] == {
        "recorded_round_count": 6,
        "covered_round_count": 0,
        "path_coverage_complete": False,
        "missing_path_rounds": [
            "momentum-parents:round-001",
            "momentum-parents:round-002",
            "momentum-parents:round-003",
            "momentum-parents:round-004",
            "momentum-parents:round-005",
            "regime-parents:round-001",
        ],
    }
    assert "path_coverage_complete: `false`" in context_text
    assert "same_driver_set_concentration" not in json.dumps(frontier)
    assert "pivot_checkpoint" not in frontier
    assert ni.path_coverage_warning_lines(session) == [
        "path_coverage_complete=false "
        "missing_path_rounds=momentum-parents:round-001, momentum-parents:round-002, momentum-parents:round-003, momentum-parents:round-004, momentum-parents:round-005, regime-parents:round-001 "
        "required_action=update_exploration_path.md_with_path_why_and_edge_feedback"
    ]

    (session / "exploration_path.md").write_text(
        "# Exploration Path\n\n## Entries\n\n"
        "### momentum-parents round-001\n- ledger: `ledger:momentum-parents:round-001`\n- path: first momentum attempt\n- why: test\n\n"
        "### momentum-parents round-002\n- ledger: `ledger:momentum-parents:round-002`\n- path: window change\n- why: test\n\n"
        "### momentum-parents round-003\n- ledger: `ledger:momentum-parents:round-003`\n- path: window change\n- why: test\n\n"
        "### momentum-parents round-004\n- ledger: `ledger:momentum-parents:round-004`\n- path: window change\n- why: test\n\n"
        "### momentum-parents round-005\n- ledger: `ledger:momentum-parents:round-005`\n- path: window change\n- why: test\n\n"
        "### regime-parents round-001\n- ledger: `ledger:regime-parents:round-001`\n- path: regime branch\n- why: test\n",
        encoding="utf-8",
    )
    ni.render_session(session)
    updated = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))

    assert updated["path_coverage"]["path_coverage_complete"] is True
    assert updated["path_coverage"]["covered_round_count"] == 6


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
    assert "path_coverage_complete: `false`" in context_text


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
    assert frontier["path_coverage"]["path_coverage_complete"] is False
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


def test_path_coverage_and_input_realization_for_empty_workspace_9_shape(tmp_path) -> None:
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
    assert labels["candidate_strategy_evidence"] == 3
    assert labels.get("target_control_evidence", 0) == 0
    assert frontier["path_coverage"]["path_coverage_complete"] is False
    assert frontier["path_coverage"]["recorded_round_count"] == 4
    assert frontier["input_realization"] == {
        "declared_graph_supported_rounds": 2,
        "realized_graph_supported_rounds": 1,
        "graph_input_read_gap_count": 1,
        "graph_input_read_gap_rows": ["momentum-regime:round-001"],
    }

    gap_row = next(row for row in ledger["rows"] if row["branch_id"] == "momentum-regime")
    assert gap_row["evidence_label"] == "candidate_strategy_evidence"
    assert gap_row["input_realization"]["graph_input_read_gap"] is True
    assert gap_row["input_realization"]["realized_input_claim"] == "target_only"
    assert "path_coverage_complete: `false`" in frontier_text
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
    assert frontier["candidate_universe"]["graph_candidates_available"] is True
    assert "input_breadth_thin: `true`" in context_text
    assert "input_breadth_thin=true" not in "\n".join(
        ni.path_coverage_warning_lines(session)
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


def test_candidate_universe_keeps_graph_context_factual_for_target_only_search(tmp_path) -> None:
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

    assert frontier["candidate_universe"]["graph_candidates_available"] is True
    assert frontier["candidate_universe"]["graph_discovery_k"] == 2
    assert frontier["evidence_label_counts"]["candidate_strategy_evidence"] == 3
    assert "graph_candidates_available: `true`" in context_text
    assert "## Candidate Universe" in context_text


def test_mixed_graph_reads_remain_supplemental_for_candidate_universe(tmp_path) -> None:
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
    assert frontier["candidate_universe"]["graph_candidates_available"] is True


def test_missing_discovery_remains_factual_without_target_only_route_warning(tmp_path) -> None:
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

    assert frontier["candidate_universe"]["graph_candidates_available"] is False
    assert frontier["candidate_universe"]["graph_discovery_source"] == "pending"
    assert frontier["evidence_label_counts"]["candidate_strategy_evidence"] == 3


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


def test_init_session_output_uses_data_led_graph_enriched_alpha_search() -> None:
    lines = ni.render_data_led_start_lines(Path("research/tsla/demo"))
    rendered = "\n".join(lines)

    assert "<feature-factory-branch>" in rendered
    assert "<model-or-denoise-branch>" in rendered
    assert "<target-control-branch>" in rendered
    assert "graph-v1" not in rendered
    assert "data-led graph-enriched alpha search" in rendered
    assert "first serious non-grandma lane should be empirical construction" in rendered
    assert "simple hand-written rules are diagnostics or refinements" in rendered
    assert "exploration_path.md" in rendered
    assert "research_journal.md" not in rendered


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


def test_build_branch_context_routes_grandma_validation_profile(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-grandma-context", tmp_path / "research")
    discovery = _sample_discovery()
    readiness = _sample_readiness()
    ni.write_graph_frontier_from_discovery_payload(session, discovery)
    ni.write_readiness(session, readiness)
    branch = ni.init_branch_dir(session, "simple-return")

    spec = ni.load_branch_spec(branch)
    spec.update(
        {
            "target": "TSLA",
            "strategy_mode": "grandma",
            "validation_profile": "grandma_daily",
            "position_bounds": [-1.0, 1.0],
        }
    )
    ni.write_branch_spec(branch, spec)

    context = ni.build_branch_context(
        branch=branch,
        session=session,
        discovery=discovery,
        readiness=readiness,
        round_id="round-001",
        backtest_start="2020-01-01",
    )

    assert context["runtime_profile"]["validation_profile"] == "grandma_daily"
    assert context["validation_context"]["profile"] == "grandma_daily"
    assert context["_execution_constraints"]["position_bounds"] == [-1.0, 1.0]


def test_build_branch_context_declares_session_dsr_trials(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dsr-context", tmp_path / "research")
    discovery = _sample_discovery()
    readiness = _sample_readiness()
    ni.write_graph_frontier_from_discovery_payload(session, discovery)
    ni.write_readiness(session, readiness)

    prior_candidate = ni.init_branch_dir(session, "graph-v1")
    prior_control = ni.init_branch_dir(session, "target-control")
    prior_error = ni.init_branch_dir(session, "workflow-error")
    current = ni.init_branch_dir(session, "graph-v2")

    candidate_spec = ni.load_branch_spec(prior_candidate)
    candidate_spec.update(
        {
            "hypothesis": "AAPL leads TSLA risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "selected_inputs": ["AAPL"],
        }
    )
    _record_synthetic_round(
        session,
        prior_candidate,
        spec=candidate_spec,
        result=_edge_result(verdict="PASS"),
    )

    control_spec = ni.load_branch_spec(prior_control)
    control_spec.update(
        {
            "hypothesis": "TSLA target-only control.",
            "evidence_intent": "control",
            "input_claim": "target_only",
            "mechanism_family": "target_momentum",
            "selected_inputs": [],
        }
    )
    _record_synthetic_round(
        session,
        prior_control,
        spec=control_spec,
        result=_edge_result(verdict="FAIL"),
        decision="discard",
    )

    error_spec = ni.load_branch_spec(prior_error)
    error_spec.update({"hypothesis": "Workflow blocker branch."})
    _record_synthetic_round(
        session,
        prior_error,
        spec=error_spec,
        result=_edge_result(verdict="ERROR"),
        decision="blocked",
    )

    current_spec = ni.load_branch_spec(current)
    current_spec.update(
        {
            "hypothesis": "MSFT leads TSLA risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "selected_inputs": ["MSFT"],
        }
    )
    ni.write_branch_spec(current, current_spec)
    _write_runtime_files(current)

    context = ni.build_branch_context(
        branch=current,
        session=session,
        discovery=discovery,
        readiness=readiness,
        round_id="round-001",
        backtest_start="2020-01-01",
    )

    dsr_trials = context["validation_context"]["dsr_trials"]
    assert dsr_trials["count"] == 3
    assert dsr_trials["source"] == "abel-invest.session/v1"
    assert dsr_trials["method"] == "session_effective_exploration_trials_v1"
    assert dsr_trials["scope"] == "ticker_session_requested_window"
    assert dsr_trials["components"]["prior_validation_rounds"] == 2
    assert dsr_trials["components"]["prior_effective_trials"] == 2
    assert dsr_trials["components"]["current_round_trials"] == 1
    assert dsr_trials["components"]["raw_recorded_rounds"] == 3


def test_build_branch_context_accumulates_parameter_selection_trials(tmp_path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dsr-selection-trials", tmp_path / "research")
    discovery = _sample_discovery()
    readiness = _sample_readiness()
    ni.write_graph_frontier_from_discovery_payload(session, discovery)
    ni.write_readiness(session, readiness)

    prior_sweep = ni.init_branch_dir(session, "threshold-sweep")
    prior_default = ni.init_branch_dir(session, "graph-v1")
    current = ni.init_branch_dir(session, "window-sweep")

    sweep_spec = ni.load_branch_spec(prior_sweep)
    sweep_spec.update(
        {
            "hypothesis": "AAPL threshold sweep leads TSLA risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "selected_inputs": ["AAPL"],
        }
    )
    _record_synthetic_round(
        session,
        prior_sweep,
        spec=sweep_spec,
        result=_edge_result(verdict="PASS"),
    )
    (prior_sweep / "outputs" / "round-001-alpha-context.json").write_text(
        json.dumps(
            {
                "branch_spec": sweep_spec,
                "validation_context": {
                    "dsr_trials": {
                        "count": 12,
                        "source": "abel-invest.session/v1",
                        "method": "session_effective_exploration_trials_v1",
                        "components": {"current_round_trials": 12},
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    default_spec = ni.load_branch_spec(prior_default)
    default_spec.update(
        {
            "hypothesis": "MSFT leads TSLA risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "selected_inputs": ["MSFT"],
        }
    )
    _record_synthetic_round(
        session,
        prior_default,
        spec=default_spec,
        result=_edge_result(verdict="FAIL"),
        decision="discard",
    )

    current_spec = ni.load_branch_spec(current)
    current_spec.update(
        {
            "hypothesis": "NVDA window sweep leads TSLA risk appetite.",
            "evidence_intent": "candidate",
            "input_claim": "graph_supported",
            "mechanism_family": "driver_momentum",
            "selected_inputs": ["NVDA"],
        }
    )
    ni.write_branch_spec(current, current_spec)
    _write_runtime_files(current)

    context = ni.build_branch_context(
        branch=current,
        session=session,
        discovery=discovery,
        readiness=readiness,
        round_id="round-001",
        backtest_start="2020-01-01",
        selection_trials=4,
    )

    dsr_trials = context["validation_context"]["dsr_trials"]
    assert dsr_trials["count"] == 17
    assert dsr_trials["components"]["prior_validation_rounds"] == 2
    assert dsr_trials["components"]["prior_effective_trials"] == 13
    assert dsr_trials["components"]["current_round_trials"] == 4
    assert dsr_trials["components"]["historical_context_fallback_rounds"] == 1


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
