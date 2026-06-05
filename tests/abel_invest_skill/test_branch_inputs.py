from __future__ import annotations

from ._branch_runtime_helpers import *  # noqa: F401,F403

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
