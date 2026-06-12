from __future__ import annotations

import json

from ._memory_helpers import *  # noqa: F401,F403

def test_select_best_pass_strategy_prefers_full_pass_within_sharpe_near_tie(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    branch_a = ni.init_branch_dir(session, "driver_explore")
    branch_b = ni.init_branch_dir(session, "momentum_lead")
    branch_c = ni.init_branch_dir(session, "regime_switch")
    _write_strategy_result_row(
        session,
        branch_a,
        round_id="round-003",
        verdict="PASS",
        sharpe=0.674,
        lo_adj=0.695,
        max_dd=-0.1440,
        score="9/13",
        calmar=5.0,
    )
    _write_strategy_result_row(
        session,
        branch_b,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
        score="10/13",
        calmar=1.0,
    )
    _write_strategy_result_row(
        session,
        branch_b,
        round_id="round-010",
        verdict="PASS",
        sharpe=0.945,
        lo_adj=1.041,
        max_dd=-0.1340,
        score="13/13",
        calmar=9.0,
        decision="discard",
    )
    _write_strategy_result_row(
        session,
        branch_c,
        round_id="round-002",
        verdict="FAIL",
        sharpe=0.508,
        lo_adj=0.866,
        max_dd=-0.1805,
        score="11/13",
        calmar=0.5,
    )

    result = ni.select_best_pass_strategy(session)

    assert result.skip_reason == ""
    assert result.validation_round_count == 4
    assert result.pass_round_count == 4
    assert result.eligible_count == 4
    assert result.selected_branch_id == "momentum_lead"
    assert result.selected_round_id == "round-010"
    assert result.selected is not None
    assert result.selected.selection_rank == 1
    assert result.selected.selection_metric_values["sharpe"] == 0.945
    assert result.selected.selection_metric_values["annual_return"] == 0.42
    assert result.selected.selection_metric_values["max_dd_abs"] == 0.1340
    assert result.selected.selection_metric_values["pass_rate"] == 1.0


def test_select_best_pass_strategy_keeps_top_sharpe_when_gap_exceeds_tenth(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    near_pass_top = ni.init_branch_dir(session, "near_pass_top")
    full_pass_lower = ni.init_branch_dir(session, "full_pass_lower")
    _write_strategy_result_row(
        session,
        near_pass_top,
        round_id="round-001",
        verdict="FAIL",
        sharpe=2.90,
        lo_adj=2.70,
        max_dd=-0.12,
        score="8/9",
        annual_return=0.42,
    )
    _write_strategy_result_row(
        session,
        full_pass_lower,
        round_id="round-001",
        verdict="PASS",
        sharpe=2.79,
        lo_adj=2.60,
        max_dd=-0.08,
        score="9/9",
        annual_return=0.31,
    )

    result = ni.select_best_pass_strategy(session)

    assert result.selected_branch_id == "near_pass_top"
    assert result.selected is not None
    assert result.selected.selection_metric_values["sharpe"] == 2.90
    assert result.selected.selection_metric_values["pass_rate"] == 8 / 9


def test_select_best_pass_strategy_sorts_by_sharpe_return_drawdown_then_latest(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    lower_sharpe = ni.init_branch_dir(session, "lower_sharpe")
    lower_return = ni.init_branch_dir(session, "lower_return")
    worse_drawdown = ni.init_branch_dir(session, "worse_drawdown")
    earlier = ni.init_branch_dir(session, "earlier")
    later = ni.init_branch_dir(session, "later")
    for branch, sharpe, annual_return, max_dd in [
        (lower_sharpe, 1.1, 0.90, -0.05),
        (lower_return, 1.2, 0.20, -0.03),
        (worse_drawdown, 1.2, 0.30, -0.12),
        (earlier, 1.2, 0.30, -0.08),
        (later, 1.2, 0.30, -0.08),
    ]:
        _write_strategy_result_row(
            session,
            branch,
            round_id="round-001",
            verdict="PASS",
            sharpe=sharpe,
            lo_adj=1.0,
            max_dd=max_dd,
            score="9/13",
            annual_return=annual_return,
        )
        ni.append_tsv_row(
            session / "events.tsv",
            ni.EVENTS_HEADER,
            {
                "timestamp": "2026-04-24T01:20:00+00:00",
                "event": "round_recorded",
                "branch_id": branch.name,
                "round_id": "round-001",
                "mode": "explore",
                "verdict": "PASS",
                "decision": "keep",
                "description": branch.name,
                "artifact_path": (
                    f"branches/{branch.name}/outputs/round-001-edge-result.json"
                ),
            },
        )

    result = ni.select_best_pass_strategy(session)

    assert result.selected_branch_id == "later"
    assert result.selected is not None
    assert result.selected.session_round_index == 5


def test_select_best_pass_strategy_can_host_discarded_fail_validation_rounds(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("AAPL", "aapl-v1", tmp_path / "research")
    lower = ni.init_branch_dir(session, "lower_discarded_fail")
    higher = ni.init_branch_dir(session, "higher_discarded_fail")
    for index, (branch, sharpe, annual_return, max_dd) in enumerate(
        [
            (lower, 1.1, 0.10, -0.08),
            (higher, 1.4, 0.05, -0.12),
        ],
        start=1,
    ):
        _write_strategy_result_row(
            session,
            branch,
            round_id="round-001",
            verdict="FAIL",
            sharpe=sharpe,
            lo_adj=sharpe,
            max_dd=max_dd,
            score="7/9",
            annual_return=annual_return,
            decision="discard",
        )
        ni.append_tsv_row(
            session / "events.tsv",
            ni.EVENTS_HEADER,
            {
                "timestamp": f"2026-04-24T01:2{index}:00+00:00",
                "event": "round_recorded",
                "branch_id": branch.name,
                "round_id": "round-001",
                "mode": "explore",
                "verdict": "FAIL",
                "decision": "discard",
                "description": branch.name,
                "artifact_path": (
                    f"branches/{branch.name}/outputs/round-001-edge-result.json"
                ),
            },
        )

    result = ni.select_best_pass_strategy(session)

    assert result.skip_reason == ""
    assert result.validation_round_count == 2
    assert result.eligible_count == 2
    assert result.selected_branch_id == "higher_discarded_fail"
    assert result.selected_round_id == "round-001"
    assert result.selected is not None
    assert result.selected.decision == "discard"
    assert result.selected.selection_metric_values["sharpe"] == 1.4


def test_best_strategy_report_payload_is_read_only_for_stop_reports(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("AAPL", "aapl-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "risk_sized_trend")
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-001",
        verdict="FAIL",
        sharpe=1.7,
        lo_adj=1.6,
        max_dd=-0.055,
        score="6/9",
        annual_return=0.18,
        decision="discard",
    )

    payload = ni.best_strategy_report_payload(session)

    assert payload["schema"] == "abel-invest.best-strategy-report/v1"
    assert payload["status"] == "selected"
    assert payload["strategy"] == {
        "idea": "risk_sized_trend round-001",
        "branchId": "risk_sized_trend",
        "roundId": "round-001",
    }
    assert payload["metrics"]["totalReturn"] == 0.42
    assert payload["metrics"]["sharpe"] == 1.7
    assert payload["metrics"]["maxDrawdown"] == -0.055
    assert payload["backtestPeriod"] == {
        "start": "2020-01-01",
        "end": "2020-12-31",
    }
    assert payload["reportGuidance"]["sessionReviewEligible"] is True
    assert "binary outcome" in payload["reportGuidance"]["validationFraming"]
    assert "limitations" in payload["robustness"]
    payload_text = json.dumps(payload)
    for leaked_key in [
        "artifactExported",
        "artifactUploadSkipped",
        "promotionStarted",
        "selectionPolicy",
        "skipReason",
        "verdict",
        "score",
        "passRate",
        "paths",
    ]:
        assert leaked_key not in payload_text
    for leaked_term in ["PASS", "FAIL", "gate", "Edge verdict"]:
        assert leaked_term not in payload_text
    assert not (session / "strategy_artifacts").exists()
    assert not (branch / "promotions").exists()


def test_select_best_pass_strategy_returns_skip_when_no_validation(tmp_path: Path) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "regime_switch")
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-001",
        verdict="ERROR",
        sharpe=0.685,
        lo_adj=0.831,
        max_dd=-0.1654,
    )

    result = ni.select_best_pass_strategy(session)

    assert result.selected is None
    assert result.skip_reason == "no_validation_strategy"
    assert result.pass_round_count == 0
    assert result.eligible_count == 0


def test_select_best_pass_strategy_skips_unhostable_validation_rounds(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("MSFT", "msft-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    ni.append_tsv_row(
        branch / "results.tsv",
        ni.RESULTS_HEADER,
        {
            "exp_id": session.name,
            "ticker": "MSFT",
            "branch_id": branch.name,
            "round_id": "round-001",
            "decision": "keep",
            "lo_adj": "1.000",
            "ic": "0.0300",
            "omega": "1.500",
            "sharpe": "1.000",
            "max_dd": "-0.1000",
            "pnl": "42.0",
            "K": "1",
            "score": "9/9",
            "verdict": "FAIL",
            "mode": "explore",
            "description": "missing result",
            "result_path": "branches/momentum_lead/outputs/missing-edge-result.json",
            "report_path": "",
            "handoff_path": "",
        },
    )

    result = ni.select_best_pass_strategy(session)

    assert result.selected is None
    assert result.skip_reason == "no_hostable_validation_strategy"
    assert result.pass_round_count == 1
    assert result.eligible_count == 0


def test_build_strategy_artifact_manifest_uses_router_contract_fields(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    trade_log_path = _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    (branch / "outputs" / "round-006-edge-frame.csv").write_text(
        "date,pnl,position,next_position,close\n"
        "2020-12-30,0.01,0.25,0.50,16.13\n"
        "2020-12-31,0.02,0.50,0.75,\n",
        encoding="utf-8",
    )

    selection = ni.select_best_pass_strategy(session)
    assert selection.selected is not None
    manifest = ni.build_strategy_artifact_manifest(
        selection.selected,
        trade_log_path=trade_log_path,
        created_at="2026-05-07T00:00:00Z",
        abel_edge_version="0.8.test",
        abel_invest_version="3.5.test",
    )

    assert manifest["schema"] == "abel-invest.strategy-artifact/v1"
    assert manifest["createdAt"] == "2026-05-07T00:00:00Z"
    assert manifest["source"] == {
        "workspaceKind": "abel-invest",
        "sourceSessionId": "tsla-v1",
        "ticker": "TSLA",
        "branchId": "momentum_lead",
        "roundId": "round-006",
        "selectionMode": "auto_best_validation_by_pass_rate",
        "selectionScope": "session",
        "selectionMetricOrder": ["pass_rate", "sharpe", "calmar", "max_dd"],
        "selectionMetricValues": {
            "lo_adjusted": 1.056,
            "annual_return": 0.42,
            "pass_rate": 1.0,
            "sharpe": 0.967,
            "calmar": 3.28,
            "max_dd": -0.1278,
            "max_dd_abs": 0.1278,
        },
        "selectionRank": 1,
    }
    assert manifest["runtime"] == {
        "profile": "equity_daily",
        "timeframe": "1d",
        "decisionEvent": "bar_close",
        "executionDelayBars": 1,
        "returnBasis": "close_to_close",
        "implementationContract": "decision_context",
        "abelEdgeVersion": "0.8.test",
        "abelInvestVersion": "3.5.test",
        "state": {
            "schema": "abel-invest.runtime-state/v1",
            "mode": "explicit_state_dir",
            "path": "state/",
            "bootstrap": {"mode": "none", "path": None},
        },
        "resultChannel": {"mode": "return_value_first"},
    }
    assert manifest["promotion"]["mode"] == "zero_change"
    assert manifest["promotion"]["gate"] == {
        "status": "passed",
        "evidencePath": None,
    }
    assert manifest["strategy"] == {
        "entrypoint": "strategy/strategy.py",
        "className": "BranchEngine",
        "targetAsset": "TSLA",
        "targetNode": "TSLA.price",
        "selectedInputs": ["AAPL", "MSFT"],
        "selectedGraphNodes": ["AAPL.price", "MSFT.price"],
        "paperMode": "paper_signal",
    }
    assert manifest["backtest"] == {
        "verdict": "PASS",
        "startAt": "2020-01-01T00:00:00Z",
        "endAt": "2020-12-31T00:00:00Z",
        "resultRef": "edge/edge-result.json",
        "reportRef": "edge/edge-validation.md",
        "latestDecision": {
            "tradingDate": "2020-12-31",
            "previousPosition": 0.25,
            "currentPosition": 0.5,
            "position": 0.5,
            "nextPosition": 0.75,
            "delta": 0.5,
            "action": "increase",
            "close": 17.06,
            "source": "abel_invest_edge_frame_csv",
        },
        "metrics": {
            "sharpe": 0.967,
            "loAdjusted": 1.056,
            "maxDrawdown": -0.1278,
            "totalReturn": 0.42,
            "calmar": 3.28,
            "annualReturn": 0.42,
            "score": "9/9",
            "positionIc": 0.03,
            "positionIcStability": 0.61,
            "positionHitRate": 0.58,
            "omega": 1.5,
            "dsr": 0.44,
            "lossYears": 1,
            "k": 1,
        },
    }
    file_paths = [item["path"] for item in manifest["files"]]
    assert file_paths == [
        "strategy/strategy.py",
        "strategy/helper.py",
        "edge/edge-result.json",
        "edge/trade-log.csv",
        "edge/edge-validation.md",
        "runtime/strategy.yaml",
        "runtime/dependencies.json",
        "runtime/data_manifest.json",
    ]
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    assert all(item["bytes"] > 0 for item in manifest["files"])


def test_build_strategy_artifact_manifest_requires_trade_log(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )

    selection = ni.select_best_pass_strategy(session)
    assert selection.selected is not None
    with pytest.raises(RuntimeError, match="edge/trade-log.csv"):
        ni.build_strategy_artifact_manifest(
            selection.selected,
            trade_log_path=branch / "outputs" / "missing-trade-log.csv",
        )


def test_export_selected_strategy_artifact_writes_local_bundle(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"
    _seed_promoted_stateless_paper_artifact(output_dir)

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                    "2020-01-01,0,0,0,0,backfill,0\n"
                    "2020-01-02,0,0,1,0,backfill,1\n"
                    "2020-01-03,0,0,1,0,backfill,1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
                stderr="",
            )
        if "export-artifact" in command:
            artifact_path = Path(command[command.index("--output-zip") + 1])
            artifact_path.write_bytes(b"artifact zip")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "artifactSha256": "abc123",
                        "artifactBytes": artifact_path.stat().st_size,
                        "fileCount": 8,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    assert result["artifactUploadSkipped"] is False
    assert result["selectedBranchId"] == "momentum_lead"
    assert result["selectedRoundId"] == "round-006"
    assert result["artifactSha256"] == "abc123"
    assert Path(result["manifestPath"]).exists()
    assert Path(result["tradeLogPath"]).exists()
    assert Path(result["artifactPath"]).exists()
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert [item["path"] for item in manifest["files"]] == [
        "strategy/strategy.py",
        "strategy/helper.py",
        "edge/edge-result.json",
        "edge/trade-log.csv",
        "edge/edge-validation.md",
        "runtime/strategy.yaml",
        "runtime/dependencies.json",
        "runtime/data_manifest.json",
        "edge/promotion-gate.json",
        "edge/promotion.patch",
        "edge/paper-contract-report.json",
        "edge/promotion-tail-trace.json",
    ]
    assert (
        manifest["source"]["selectionMode"]
        == "auto_best_validation_by_pass_rate"
    )
    assert manifest["source"]["selectionScope"] == "session"
    assert manifest["promotion"]["mode"] == "agent_paper_contract"
    assert manifest["runtime"]["paperExecutionProfile"]["history"]["boundary"] == "fixed_lookback"
    assert manifest["runtime"]["paperExecutionProfile"]["history"]["lookbackBars"] == 1


def test_export_selected_strategy_artifact_nulls_inapplicable_metrics(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    result_path = branch / "outputs" / "round-006-edge-result.json"
    edge_result = json.loads(result_path.read_text(encoding="utf-8"))
    edge_result["metrics"].update(
        {
            "omega": 0.0,
            "omega_applicable": False,
            "position_ic": 0.0,
            "position_hit_rate": 0.0,
            "position_ic_applicable": False,
            "position_ic_stability": 0.0,
            "position_ic_monthly_mean": 0.0,
            "position_ic_stability_applicable": False,
            "loss_years": 0,
            "loss_years_applicable": False,
        }
    )
    result_path.write_text(json.dumps(edge_result), encoding="utf-8")
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "exported-artifact"
    _seed_promoted_stateless_paper_artifact(output_dir)
    captured: dict[str, object] = {}

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                    "2020-01-01,0,0,0,0,backfill,0\n"
                    "2020-01-02,0,0,1,0,backfill,1\n"
                    "2020-01-03,0,0,1,0,backfill,1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
                stderr="",
            )
        if "export-artifact" in command:
            edge_result_arg = Path(command[command.index("--edge-result") + 1])
            captured["edge_result_arg"] = edge_result_arg
            captured["edge_result"] = json.loads(edge_result_arg.read_text(encoding="utf-8"))
            artifact_path = Path(command[command.index("--output-zip") + 1])
            artifact_path.write_bytes(b"artifact zip")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "artifactSha256": "abc123",
                        "artifactBytes": artifact_path.stat().st_size,
                        "fileCount": 8,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    metrics = manifest["backtest"]["metrics"]
    assert metrics["positionIc"] is None
    assert metrics["positionIcStability"] is None
    assert metrics["positionHitRate"] is None
    assert metrics["omega"] is None
    assert metrics["lossYears"] is None
    assert Path(captured["edge_result_arg"]).name == "edge-result.artifact.json"
    artifact_edge_metrics = captured["edge_result"]["metrics"]
    assert artifact_edge_metrics["position_ic"] is None
    assert artifact_edge_metrics["position_ic_stability"] is None
    assert artifact_edge_metrics["position_hit_rate"] is None
    assert artifact_edge_metrics["position_ic_monthly_mean"] is None
    assert artifact_edge_metrics["omega"] is None
    assert artifact_edge_metrics["loss_years"] is None


def test_promote_branch_strategy_uses_explicit_branch_round(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-003",
        verdict="PASS",
        sharpe=0.850,
        lo_adj=0.910,
        max_dd=-0.1700,
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )
    _write_metric_input(branch, round_id="round-006")
    output_dir = tmp_path / "promoted-artifact"
    _seed_promoted_stateless_paper_artifact(output_dir)

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,0,0,backfill,0\n"
                "2020-01-02,0,0,1,0,backfill,1\n"
                "2020-01-03,0,0,1,0,backfill,1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
                stderr="",
            )
        if "export-artifact" in command:
            artifact_path = Path(command[command.index("--output-zip") + 1])
            artifact_path.write_bytes(b"artifact zip")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "artifactSha256": "abc123",
                        "artifactBytes": artifact_path.stat().st_size,
                        "fileCount": 9,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    result = ni.promote_branch_strategy(
        branch,
        round_id="round-006",
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    assert result["selectedBranchId"] == "momentum_lead"
    assert result["selectedRoundId"] == "round-006"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["source"]["selectionMode"] == "explicit_branch_round"
    assert manifest["source"]["selectionScope"] == "branch"
    assert manifest["source"]["selectionMetricOrder"] == []
    assert manifest["promotion"]["gate"]["evidencePath"] == "edge/promotion-gate.json"


def test_promote_branch_strategy_requires_round_when_branch_has_multiple_passes(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_artifact_inputs(branch)
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-003",
        verdict="PASS",
        sharpe=0.850,
        lo_adj=0.910,
        max_dd=-0.1700,
    )
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-006",
        verdict="PASS",
        sharpe=0.967,
        lo_adj=1.056,
        max_dd=-0.1278,
    )

    result = ni.promote_branch_strategy(branch, python_bin="python-test")

    assert result["artifactExported"] is False
    assert result["skipReason"] == "ambiguous_branch_promotion_round"
    assert result["selectedBranchId"] == "momentum_lead"
    assert result["selectedRoundId"] is None
