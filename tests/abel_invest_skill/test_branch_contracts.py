from __future__ import annotations

from ._branch_runtime_helpers import *  # noqa: F401,F403

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
    assert "Disposable Search" in context_guide
    assert "session `scratch/` directory" in context_guide
    assert "prepare-only" in context_guide
    assert "flat/no-signal materialization round" in context_guide
    assert "diagnostics" in context_guide
    assert "scored candidate-shaped variants" in context_guide
    assert "inline heredoc" in context_guide
    assert "not validation evidence" in context_guide


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
