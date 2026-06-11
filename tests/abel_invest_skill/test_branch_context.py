from __future__ import annotations

from ._branch_runtime_helpers import *  # noqa: F401,F403

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
    assert "Sharpe > 2 and all required Abel Edge gates passing" in rendered
    assert "stay in Exploring until the objective is met" in rendered
    assert "render/status/check are audit actions only" in rendered
    assert "disposable probes may live in research/tsla/demo/scratch" in rendered
    assert "equivalent heredoc/notebook/query cell" in rendered
    assert "first serious recorded alpha candidate should normally be probe-informed" in rendered
    assert "prepare a scout/candidate branch before measuring market data" in rendered
    assert "prepare-only scout branches are fine" in rendered
    assert "do not run flat/no-signal rounds" in rendered
    assert "after prepare-branch, disposable probes may live" in rendered
    assert "expect the first-look scout to take roughly 5 minutes" in rendered
    assert "score plausible target, graph, and construction shapes" in rendered
    assert "let it finish naturally before deciding what to validate" in rendered
    assert "run broad candidates only after data/cache are prepared" in rendered
    assert "simple hand-written rules are diagnostics or refinements" in rendered
    assert "validation gates estimate reliability" in rendered
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
