from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from pathlib import Path

from abel_strategy_discovery import narrative_impl as ni


def _sample_selected_inputs() -> list[dict]:
    return [
        {"node_id": "AAPL.price", "asset": "AAPL", "field": "price", "roles": ["selected"]},
    ]


def _semantic_result(*, traced_inputs: list[str], requested_start: str = "2020-01-01") -> dict:
    return {
        "verdict": "PASS",
        "score": "7/7",
        "metrics": {},
        "requested_window": {"start": requested_start, "end": None},
        "effective_window": {"start": requested_start, "end": "2020-12-31"},
        "semantic": {
            "verdict": "PASS",
            "prepared_inputs": {
                "selected_inputs": ["AAPL.price"],
                "traced_inputs": traced_inputs,
                "issues": [],
            },
        },
        "diagnostics": {
            "failure_signature": "clean_pass",
            "runtime_stage": "validation",
            "signal": {"active_days": 10, "total_days": 20},
            "hints": [],
        },
    }


def _record_round(
    branch: Path,
    *,
    round_id: str,
    decision: str,
    evidence_type: str,
    description: str,
    sharpe: float = 1.0,
    protocol_flags: str = "none",
    next_step: str = "",
    backtest_start: str = "2020-01-01",
    invalidation_condition: str = "AAPL lead should fail without cross-asset pressure",
) -> None:
    ni.append_tsv_row(
        branch / "results.tsv",
        ni.RESULTS_HEADER,
        {
            "exp_id": branch.parent.parent.name,
            "ticker": "TSLA",
            "branch_id": branch.name,
            "round_id": round_id,
            "decision": decision,
            "lo_adj": "2.000",
            "ic": "0.1000",
            "omega": "1.500",
            "sharpe": f"{sharpe:.3f}",
            "max_dd": "-0.0800",
            "pnl": "30.0",
            "K": "1",
            "score": "7/7",
            "verdict": "PASS",
            "mode": "explore",
            "description": description,
            "result_path": f"outputs/{round_id}-edge-result.json",
            "report_path": f"outputs/{round_id}-edge-validation.md",
            "handoff_path": f"outputs/{round_id}-edge-handoff.json",
        },
    )
    note = ni.render_round_note(
        ticker="TSLA",
        exp_id=branch.parent.parent.name,
        branch_id=branch.name,
        round_id=round_id,
        mode="explore",
        decision=decision,
        description=description,
        result=_semantic_result(
            traced_inputs=["AAPL.price"] if evidence_type == "candidate_evidence" else [],
            requested_start=backtest_start,
        ),
        backtest_start=backtest_start,
        input_note="AAPL.price is the selected graph input",
        hypothesis="AAPL price leads TSLA",
        expected_signal="positive cross-asset lead",
        invalidation_condition=invalidation_condition,
        trigger=description,
        change_summary=description,
        time_spent_min="5",
        summary=description,
        next_step=next_step,
        evidence={
            "evidence_type": evidence_type,
            "protocol_flags": protocol_flags,
            "reflection_status": "complete",
            "selected_non_target_inputs": "AAPL.price" if evidence_type == "candidate_evidence" else "none",
            "traced_inputs": "AAPL.price" if evidence_type == "candidate_evidence" else "none",
        },
    )
    (branch / "rounds" / f"{round_id}.md").write_text(note, encoding="utf-8")


def test_round_evidence_classifies_target_only_as_control(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "evidence-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "target-only")
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = []
    ni.write_branch_spec(branch, spec)

    evidence = ni.classify_round_evidence(
        branch=branch,
        discovery=ni.load_discovery(session),
        result=_semantic_result(traced_inputs=[]),
        hypothesis="target trend persistence",
        input_note="target-only control",
        expected_signal="control should expose target fit",
        change_summary="first control",
    )

    assert evidence["evidence_type"] == "control_evidence"
    assert "target_only" in evidence["protocol_flags"]


def test_round_evidence_requires_traced_non_target_input(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "evidence-v2", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-declared")
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = _sample_selected_inputs()
    ni.write_branch_spec(branch, spec)

    evidence = ni.classify_round_evidence(
        branch=branch,
        discovery=ni.load_discovery(session),
        result=_semantic_result(traced_inputs=[]),
        hypothesis="AAPL price leads TSLA",
        input_note="AAPL.price is the selected graph input",
        expected_signal="positive cross-asset lead",
        change_summary="first graph attempt",
    )

    assert evidence["evidence_type"] == "control_evidence"
    assert "declared_input_not_traced" in evidence["protocol_flags"]

    traced = ni.classify_round_evidence(
        branch=branch,
        discovery=ni.load_discovery(session),
        result=_semantic_result(traced_inputs=["AAPL.price"]),
        hypothesis="AAPL price leads TSLA",
        input_note="AAPL.price is the selected graph input",
        expected_signal="positive cross-asset lead",
        change_summary="first graph attempt",
        invalidation_condition="AAPL lead should fail when the cross-asset thesis is absent",
    )

    assert traced["evidence_type"] == "candidate_evidence"
    assert traced["traced_inputs"] == "AAPL.price"


def test_missing_reflection_blocks_candidate_evidence(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "evidence-v2b", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-incomplete-reflection")
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = _sample_selected_inputs()
    ni.write_branch_spec(branch, spec)

    evidence = ni.classify_round_evidence(
        branch=branch,
        discovery=ni.load_discovery(session),
        result=_semantic_result(traced_inputs=["AAPL.price"]),
        hypothesis="AAPL price leads TSLA",
        input_note="AAPL.price is the selected graph input",
        expected_signal="positive cross-asset lead",
        change_summary="first graph attempt",
    )

    assert evidence["evidence_type"] == "protocol_violation"
    assert "reflection_required" in evidence["protocol_flags"]
    assert ni.evidence_adjusted_decision(
        metric_decision="keep",
        evidence=evidence,
        result=_semantic_result(traced_inputs=["AAPL.price"]),
    ) == "protocol"


def test_post_hoc_requested_start_change_is_protocol_violation(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "window-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-window")
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = _sample_selected_inputs()
    spec["requested_start"] = "2020-01-01"
    ni.write_branch_spec(branch, spec)
    _record_round(
        branch,
        round_id="round-001",
        decision="discard",
        evidence_type="candidate_evidence",
        description="earlier requested window did not pass",
        backtest_start="2020-01-01",
    )

    spec["requested_start"] = "2021-01-01"
    ni.write_branch_spec(branch, spec)
    evidence = ni.classify_round_evidence(
        branch=branch,
        discovery=ni.load_discovery(session),
        result=_semantic_result(
            traced_inputs=["AAPL.price"],
            requested_start="2021-01-01",
        ),
        rows=ni.read_tsv_rows(branch / "results.tsv"),
        hypothesis="AAPL price leads TSLA",
        input_note="AAPL.price is the selected graph input",
        expected_signal="positive cross-asset lead",
        change_summary="same thesis under a later requested window",
        invalidation_condition="AAPL lead should fail when cross-asset pressure is absent",
    )

    assert evidence["evidence_type"] == "protocol_violation"
    assert "post_hoc_window_change" in evidence["protocol_flags"]


def test_initial_narrow_window_requires_study_protocol_declaration(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "window-v2", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-regime")
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = _sample_selected_inputs()
    spec["requested_start"] = "2021-01-01"
    ni.write_branch_spec(branch, spec)

    undeclared = ni.classify_round_evidence(
        branch=branch,
        discovery=ni.load_discovery(session),
        result=_semantic_result(
            traced_inputs=["AAPL.price"],
            requested_start="2021-01-01",
        ),
        rows=[],
        hypothesis="AAPL price leads TSLA in the post-2021 regime",
        input_note="AAPL.price is the selected graph input",
        expected_signal="positive cross-asset lead",
        change_summary="first regime attempt",
        invalidation_condition="AAPL lead should fail outside the claimed regime",
    )

    assert undeclared["evidence_type"] == "protocol_violation"
    assert "undeclared_initial_window" in undeclared["protocol_flags"]

    _record_round(
        branch,
        round_id="round-001",
        decision="protocol",
        evidence_type="protocol_violation",
        description="undeclared initial window was not comparable",
        protocol_flags="undeclared_initial_window",
        backtest_start="2021-01-01",
    )
    still_undeclared = ni.classify_round_evidence(
        branch=branch,
        discovery=ni.load_discovery(session),
        result=_semantic_result(
            traced_inputs=["AAPL.price"],
            requested_start="2021-01-01",
        ),
        rows=ni.read_tsv_rows(branch / "results.tsv"),
        hypothesis="AAPL price leads TSLA in the post-2021 regime",
        input_note="AAPL.price is the selected graph input",
        expected_signal="positive cross-asset lead",
        change_summary="second regime attempt",
        invalidation_condition="AAPL lead should fail outside the claimed regime",
    )

    assert still_undeclared["evidence_type"] == "protocol_violation"
    assert "undeclared_study_window" in still_undeclared["protocol_flags"]

    declared_branch = ni.init_branch_dir(session, "graph-declared-regime")
    declared_spec = ni.load_branch_spec(declared_branch)
    declared_spec["selected_inputs"] = _sample_selected_inputs()
    declared_spec["requested_start"] = "2021-01-01"
    declared_spec["study_protocol"] = "predeclared regime study"
    ni.write_branch_spec(declared_branch, declared_spec)
    declared = ni.classify_round_evidence(
        branch=declared_branch,
        discovery=ni.load_discovery(session),
        result=_semantic_result(
            traced_inputs=["AAPL.price"],
            requested_start="2021-01-01",
        ),
        rows=[],
        hypothesis="AAPL price leads TSLA in the post-2021 regime",
        input_note="AAPL.price is the selected graph input",
        expected_signal="positive cross-asset lead",
        change_summary="first regime attempt",
        invalidation_condition="AAPL lead should fail outside the claimed regime",
    )

    assert declared["evidence_type"] == "candidate_evidence"
    assert "declared_study_window" in declared["protocol_flags"]


def test_window_guidance_reports_protocol_facts_without_narrowing_tactic() -> None:
    window_report = {
        "requested_start": "2020-01-01",
        "effective_window": {
            "start": "2020-03-01T00:00:00+00:00",
            "end": "2020-12-31T00:00:00+00:00",
        },
        "start_alignment": {
            "requested_start": "2020-01-01T00:00:00+00:00",
            "target_safe_start": "2020-01-01T00:00:00+00:00",
            "prepared_effective_start": "2020-03-01T00:00:00+00:00",
            "avoidable_gap_days": 60,
        },
        "limiting_inputs": ["BTCUSD.price"],
    }
    guide = ni.build_context_guide_markdown(
        target_asset="TSLA",
        target_node="TSLA.price",
        runtime_profile={"profile": "daily"},
        execution_constraints={"long_only": True},
        data_manifest={
            "feeds": [
                {
                    "name": "BTCUSD.price",
                    "field": "price",
                    "runtime_field": "close",
                    "native_window": {"start": "2020-03-01", "end": "2020-12-31"},
                },
            ],
        },
        window_report=window_report,
    )
    advisory = "\n".join(ni.window_availability_advisory_lines(window_report))
    combined = guide + "\n" + advisory

    assert "narrowing requested_start" not in combined
    assert "replace limiting inputs" not in combined
    assert "coverage gaps are reported as facts" in combined


def test_round_note_parses_research_protocol_fields(tmp_path: Path) -> None:
    branch = tmp_path / "branch"
    rounds = branch / "rounds"
    rounds.mkdir(parents=True)
    note = ni.render_round_note(
        ticker="TSLA",
        exp_id="evidence-v3",
        branch_id="graph-v1",
        round_id="round-001",
        mode="explore",
        decision="keep",
        description="graph evidence",
        result=_semantic_result(traced_inputs=["AAPL.price"]),
        backtest_start="2020-01-01",
        input_note="AAPL.price is the selected graph input",
        hypothesis="AAPL price leads TSLA",
        expected_signal="positive cross-asset lead",
        invalidation_condition="AAPL lead should fail without cross-asset pressure",
        trigger="first graph attempt",
        change_summary="first graph attempt",
        time_spent_min="5",
        summary="recorded graph evidence",
        next_step="",
        evidence={
            "evidence_type": "candidate_evidence",
            "protocol_flags": "none",
            "reflection_status": "complete",
            "selected_non_target_inputs": "AAPL.price",
            "traced_inputs": "AAPL.price",
        },
    )
    (rounds / "round-001.md").write_text(note, encoding="utf-8")

    parsed = ni.read_round_note(branch, "round-001")

    assert parsed["evidence_type"] == "candidate_evidence"
    assert parsed["protocol_flags"] == "none"
    assert parsed["reflection_status"] == "complete"
    assert parsed["requested_start"] == "2020-01-01"
    assert parsed["input_rationale"] == "AAPL.price is the selected graph input"
    assert parsed["invalidation_condition"] == "AAPL lead should fail without cross-asset pressure"


def test_control_pass_is_not_leader_or_promotable(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "phase2-v1", tmp_path / "research")
    control = ni.init_branch_dir(session, "target-control")
    candidate = ni.init_branch_dir(session, "graph-candidate")
    control_spec = ni.load_branch_spec(control)
    control_spec["selected_inputs"] = []
    ni.write_branch_spec(control, control_spec)
    candidate_spec = ni.load_branch_spec(candidate)
    candidate_spec["selected_inputs"] = _sample_selected_inputs()
    ni.write_branch_spec(candidate, candidate_spec)

    _record_round(
        control,
        round_id="round-001",
        decision="control",
        evidence_type="control_evidence",
        description="target-only control pass",
        sharpe=4.0,
        protocol_flags="target_only",
    )
    _record_round(
        candidate,
        round_id="round-001",
        decision="keep",
        evidence_type="candidate_evidence",
        description="graph-supported candidate pass",
        sharpe=1.5,
    )

    branches = ni.load_branches(session)

    assert ni.select_leader(branches)["branch_id"] == "graph-candidate"
    assert "target-control" in ni.render_selection_narrative(branches)
    assert ni.promote_branch_bundle(
        Namespace(branch=str(control), output_dir=None)
    ) == 2


def test_memory_does_not_turn_control_next_step_into_reusable_rule(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "phase2-v2", tmp_path / "research")
    control = ni.init_branch_dir(session, "target-control")
    spec = ni.load_branch_spec(control)
    spec["selected_inputs"] = []
    ni.write_branch_spec(control, spec)
    _record_round(
        control,
        round_id="round-001",
        decision="control",
        evidence_type="control_evidence",
        description="target-only control pass",
        protocol_flags="target_only",
        next_step="continue this target-only route",
    )

    insights = ni.build_auto_insight_rows(ni.load_branches(session))

    assert not any(row["kind"] == "worked" for row in insights)
    assert not any("target-only route" in row["statement"] for row in insights)


def test_generated_surfaces_use_reflection_prompts_not_strategy_routes(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "phase4-v1", tmp_path / "research")
    readme = (session / "README.md").read_text(encoding="utf-8")

    assert "first branch will start target-only" not in readme
    assert "Continue improving" not in readme
    assert "set-backtest-start --session" not in readme
    assert "control evidence until non-target graph inputs are selected and traced" in readme

    context_path = session / "debug-context.json"
    context_path.write_text("{}", encoding="utf-8")
    debug_result_path = session / "debug-result.json"
    debug_result_path.write_text(
        json.dumps(
            {
                "verdict": "ERROR",
                "failures": ["shape mismatch"],
                "diagnostics": {
                    "failure_signature": "shape_mismatch",
                    "runtime_stage": "semantic_preflight",
                    "hints": ["try a wider threshold"],
                },
            }
        ),
        encoding="utf-8",
    )
    snapshot = ni.build_debug_snapshot(
        completed=subprocess.CompletedProcess([], 1, stdout="", stderr=""),
        session=session,
        context_path=context_path,
        debug_result_path=debug_result_path,
        backtest_start="2020-01-01",
    )

    assert "try a wider threshold" not in snapshot["next_step"]
    assert "invalidation condition" in snapshot["next_step"]

    branch = ni.init_branch_dir(session, "graph-failed")
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = _sample_selected_inputs()
    ni.write_branch_spec(branch, spec)
    _record_round(
        branch,
        round_id="round-001",
        decision="discard",
        evidence_type="candidate_evidence",
        description="graph evidence did not pass",
    )
    insights = ni.build_auto_insight_rows(ni.load_branches(session))
    rules = "\n".join(row.get("reusable_rule", "") for row in insights)

    assert "Do not retry" not in rules
    assert "Fix this blocker" not in rules
    assert "no next strategy route is implied" in rules


def test_discarded_candidate_is_recorded_but_not_lead(tmp_path: Path, capsys) -> None:
    session = ni.init_session_dir("TSLA", "phase6-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-failed")
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = _sample_selected_inputs()
    ni.write_branch_spec(branch, spec)
    _record_round(
        branch,
        round_id="round-001",
        decision="discard",
        evidence_type="candidate_evidence",
        description="graph evidence failed validation",
    )

    branches = ni.load_branches(session)
    assert ni.select_leader(branches) is None

    selection = ni.render_selection_narrative(branches)
    assert "No passing candidate evidence is currently available." in selection
    assert "Recorded candidate evidence:" in selection
    assert "(lead)" not in selection

    ni.render_session(session)
    readme = (session / "README.md").read_text(encoding="utf-8")
    assert "Current candidate lead" not in readme
    assert "Best recorded candidate evidence" in readme

    ni.print_status(session)
    status = capsys.readouterr().out
    assert "Candidate lead:" not in status
    assert "Best recorded candidate evidence:" in status


def test_coverage_alignment_display_distinguishes_alignment_from_strategy() -> None:
    spec = {
        "coverage_alignment": "target_aligned",
        "selected_inputs": _sample_selected_inputs(),
    }

    label = ni.branch_coverage_alignment_label(spec)
    assert "selected graph inputs remain evidence inputs" in label
    assert "target_only" not in label


def test_memory_scaffold_and_views(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")
    branch_spec = ni.load_branch_spec(branch)

    required_session_files = [
        ni.MEMORY_MANIFEST_FILENAME,
        ni.MEMORY_BRANCHES_FILENAME,
        ni.MEMORY_ROUNDS_FILENAME,
        ni.MEMORY_VALIDATIONS_FILENAME,
        ni.MEMORY_INSIGHTS_FILENAME,
        ni.MEMORY_LINKS_FILENAME,
        f"{ni.MEMORY_VIEWS_DIRNAME}/{ni.MEMORY_OVERVIEW_FILENAME}",
        f"{ni.MEMORY_VIEWS_DIRNAME}/{ni.MEMORY_COMPARE_FILENAME}",
    ]
    for rel in required_session_files:
        assert (session / rel).exists(), rel

    memory_text = (branch / "memory.md").read_text(encoding="utf-8")
    assert "## Branch Profile" in memory_text
    assert "## Compare Candidates" in memory_text

    branch_rows = ni.read_tsv_rows(session / ni.MEMORY_BRANCHES_FILENAME)
    assert len(branch_rows) == 1
    assert branch_rows[0]["branch_id"] == "graph-v1"
    assert branch_rows[0]["source_type"] == "causal"
    assert branch_spec["target_asset"] == "TSLA"
    assert branch_spec["target_node"] == "TSLA.price"
    assert "selected_inputs" in branch_spec


def test_manual_insight_and_link_survive_render(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v2", tmp_path / "research")
    causal = ni.init_branch_dir(session, "graph-v1")
    baseline = ni.init_branch_dir(session, "baseline-v1")

    baseline_spec = ni.load_branch_spec(baseline)
    baseline_spec["source_type"] = "baseline"
    baseline_spec["method_family"] = "rule"
    ni.write_branch_spec(baseline, baseline_spec)
    ni.render_session(session)

    ni.record_manual_insight(
        Namespace(
            branch=str(causal),
            scope="branch",
            kind="pattern",
            text="Driver concentration matters more than raw parent count.",
            rule="Prefer a tighter driver set before opening a new sibling branch.",
            confidence="high",
            round_id="",
        )
    )
    ni.record_branch_link(
        Namespace(
            from_branch=str(causal),
            to_branch=str(baseline),
            type="candidate_compare",
            match_score="0.95",
            match_basis="same ticker and same requested start",
            status="candidate",
            note="manual compare seed",
        )
    )

    insights = ni.read_tsv_rows(session / ni.MEMORY_INSIGHTS_FILENAME)
    assert any(
        row["origin"] == "manual"
        and row["statement"] == "Driver concentration matters more than raw parent count."
        for row in insights
    )

    links = ni.read_tsv_rows(session / ni.MEMORY_LINKS_FILENAME)
    assert any(
        row["origin"] == "manual"
        and row["from_branch_id"] == "graph-v1"
        and row["to_branch_id"] == "baseline-v1"
        for row in links
    )

    ni.render_session(session)

    insights = ni.read_tsv_rows(session / ni.MEMORY_INSIGHTS_FILENAME)
    links = ni.read_tsv_rows(session / ni.MEMORY_LINKS_FILENAME)
    assert any(row["origin"] == "manual" for row in insights)
    assert any(row["origin"] == "manual" for row in links)


def test_run_branch_round_updates_memory_and_status(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v3", tmp_path / "research")
    causal = ni.init_branch_dir(session, "graph-v1")
    baseline = ni.init_branch_dir(session, "baseline-v1")

    baseline_spec = ni.load_branch_spec(baseline)
    baseline_spec["source_type"] = "baseline"
    baseline_spec["method_family"] = "rule"
    ni.write_branch_spec(baseline, baseline_spec)

    for branch in (causal, baseline):
        deps_path = ni.dependencies_path(branch)
        deps_path.parent.mkdir(parents=True, exist_ok=True)
        dependencies = {
            "version": 2,
            "branch_id": branch.name,
            "target_asset": "TSLA",
            "target_node": "TSLA.price",
            "selected_inputs": _sample_selected_inputs(),
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
        runtime_profile = ni.build_runtime_profile_payload(
            target_asset="TSLA",
            target_node="TSLA.price",
        )
        execution_constraints = ni.build_execution_constraints_payload(ni.load_branch_spec(branch))
        data_manifest = ni.build_data_manifest_payload(
            target_asset="TSLA",
            target_node="TSLA.price",
            selected_inputs=ni.branch_selected_inputs(
                {"selected_inputs": _sample_selected_inputs()}
            ),
            cache_payload=dependencies["cache"],
            readiness={},
        )
        window_report = ni.build_window_availability_report(
            requested_start="2020-01-01",
            data_manifest=data_manifest,
            coverage_alignment="target_aligned",
        )
        probe_samples = ni.build_probe_samples_payload(
            target_asset="TSLA",
            requested_start="2020-01-01",
            data_manifest=data_manifest,
            window_report=window_report,
        )
        ni.runtime_profile_path(branch).write_text(
            json.dumps(runtime_profile),
            encoding="utf-8",
        )
        ni.execution_constraints_path(branch).write_text(
            json.dumps(execution_constraints),
            encoding="utf-8",
        )
        ni.data_manifest_path(branch).write_text(
            json.dumps(data_manifest),
            encoding="utf-8",
        )
        ni.window_availability_path(branch).write_text(
            json.dumps(window_report),
            encoding="utf-8",
        )
        ni.probe_samples_path(branch).write_text(
            json.dumps(probe_samples),
            encoding="utf-8",
        )
        ni.context_guide_path(branch).write_text(
            ni.build_context_guide_markdown(
                target_asset="TSLA",
                target_node="TSLA.price",
                runtime_profile=runtime_profile,
                execution_constraints=execution_constraints,
                data_manifest=data_manifest,
                window_report=window_report,
            ),
            encoding="utf-8",
        )
        ni.persist_prepared_branch_contract(branch, ni.load_discovery(session))

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None, check=False, input=None):
        if "evaluate" in command:
            workdir = Path(command[command.index("--workdir") + 1])
            result_path = Path(command[command.index("--output-json") + 1])
            report_path = Path(command[command.index("--output-md") + 1])
            handoff_path = Path(command[command.index("--output-handoff") + 1])
            if workdir.name == "baseline-v1":
                sharpe = 1.8
                lo_adj = 2.4
                total_return = 0.42
            else:
                sharpe = 2.6
                lo_adj = 3.1
                total_return = 0.63
            payload = {
                "verdict": "PASS",
                "score": "7/7",
                "failures": [],
                "warnings": [],
                "profile": "crypto_daily",
                "K": 1,
                "metrics": {
                    "sharpe": sharpe,
                    "lo_adjusted": lo_adj,
                    "position_ic": 0.0,
                    "omega": 1.5,
                    "total_return": total_return,
                    "max_dd": -0.08,
                },
                "requested_window": {"start": "2020-01-01", "end": None},
                "effective_window": {"start": "2020-01-01", "end": "2020-12-31"},
                "diagnostics": {
                    "failure_signature": "clean_pass",
                    "runtime_stage": "evaluate",
                    "signal": {"active_days": 120, "total_days": 252},
                    "hints": ["carry forward the current signal family"],
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
            branch=str(baseline),
            mode="explore",
            description="baseline momentum rule",
            input_note="",
            hypothesis="baseline trend persistence",
            expected_signal="",
            trigger="baseline seed",
            change_summary="first baseline pass",
            time_spent_min="12",
            summary="",
            next_step="compare against causal branch",
            action=[],
            python_bin=None,
            allow_untouched_template=True,
        )
    )
    ni.run_branch_round(
        Namespace(
            branch=str(causal),
            mode="explore",
            description="causal driver vote",
            input_note="",
            hypothesis="top discovered parents vote the target",
            expected_signal="",
            trigger="graph discovery seed",
            change_summary="first causal pass",
            time_spent_min="15",
            summary="",
            next_step="compare against baseline branch",
            action=[],
            python_bin=None,
            allow_untouched_template=True,
        )
    )

    validations = ni.read_tsv_rows(session / ni.MEMORY_VALIDATIONS_FILENAME)
    rounds = ni.read_tsv_rows(session / ni.MEMORY_ROUNDS_FILENAME)
    links = ni.read_tsv_rows(session / ni.MEMORY_LINKS_FILENAME)
    assert len(validations) == 2
    assert len(rounds) == 2
    assert any(
        row["link_type"] == "candidate_compare"
        and row["from_branch_id"] == "graph-v1"
        and row["to_branch_id"] == "baseline-v1"
        for row in links
    )

    compare_view = (session / ni.MEMORY_VIEWS_DIRNAME / ni.MEMORY_COMPARE_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "graph-v1" in compare_view
    assert "baseline-v1" in compare_view

    ni.print_status(session)
    status_output = capsys.readouterr().out
    assert "Memory:" in status_output

    assert ni.check_session(session, strict=False) == 0


def test_run_branch_round_prompts_dashboard_upload_for_candidate_evidence(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dashboard-upload", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = _sample_selected_inputs()
    ni.write_branch_spec(branch, spec)
    deps_path = ni.dependencies_path(branch)
    deps_path.parent.mkdir(parents=True, exist_ok=True)
    deps_path.write_text(
        json.dumps(
            {
                "version": 2,
                "branch_id": branch.name,
                "target_asset": "TSLA",
                "target_node": "TSLA.price",
                "selected_inputs": _sample_selected_inputs(),
                "requested_start": "2020-01-01",
            }
        ),
        encoding="utf-8",
    )
    ni.runtime_profile_path(branch).write_text("{}", encoding="utf-8")
    ni.execution_constraints_path(branch).write_text("{}", encoding="utf-8")
    ni.data_manifest_path(branch).write_text("{}", encoding="utf-8")
    ni.window_availability_path(branch).write_text("{}", encoding="utf-8")
    ni.context_guide_path(branch).write_text("", encoding="utf-8")
    ni.probe_samples_path(branch).write_text("{}", encoding="utf-8")
    ni.persist_prepared_branch_contract(branch, ni.load_discovery(session))

    def fake_run(*args, **kwargs):
        command = args[0]
        result_path = Path(command[command.index("--output-json") + 1])
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(_semantic_result(traced_inputs=["AAPL.price"])),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert ni.run_branch_round(
        Namespace(
            branch=str(branch),
            mode="explore",
            description="causal driver vote",
            input_note="AAPL.price selected",
            hypothesis="AAPL price leads TSLA",
            expected_signal="positive cross-asset lead",
            invalidation_condition="AAPL lead fails",
            trigger="graph discovery seed",
            change_summary="first causal pass",
            time_spent_min="15",
            summary="candidate evidence round",
            next_step="upload dashboard memory",
            action=[],
            python_bin=None,
            allow_untouched_template=True,
        )
    ) == 0

    output = capsys.readouterr().out
    assert "Dashboard upload:" in output
    assert "abel-strategy-discovery upload-dashboard-bundle --branch" in output


def test_build_skill_dashboard_bundle_uses_branch_evidence_only(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "tsla-dashboard", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")
    ni.write_branch_state(branch, {"created_at": "2026-04-24T01:00:00+00:00"})
    spec = ni.load_branch_spec(branch)
    spec["selected_inputs"] = _sample_selected_inputs()
    ni.write_branch_spec(branch, spec)
    _record_round(
        branch,
        round_id="round-001",
        decision="keep",
        evidence_type="candidate_evidence",
        description="graph-supported candidate pass",
    )
    ni.record_manual_insight(
        Namespace(
            branch=str(branch),
            scope="branch",
            kind="pattern",
            text="Driver concentration matters more than raw parent count.",
            rule="Prefer a tighter driver set before opening a sibling branch.",
            confidence="high",
            round_id="round-001",
        )
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
    assert bundle["payload"]["branch"]["selectedInputs"] == ["AAPL.price"]
    assert bundle["payload"]["rounds"][0]["roundId"] == "round-001"
    assert any(
        item["summary"] == "Driver concentration matters more than raw parent count."
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
