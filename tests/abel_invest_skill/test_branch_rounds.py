from __future__ import annotations

from ._branch_runtime_helpers import *  # noqa: F401,F403

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
