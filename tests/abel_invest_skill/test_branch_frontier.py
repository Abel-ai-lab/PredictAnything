from __future__ import annotations

from ._branch_runtime_helpers import *  # noqa: F401,F403

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
