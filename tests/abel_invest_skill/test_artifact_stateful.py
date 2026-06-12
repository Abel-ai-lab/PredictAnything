from __future__ import annotations

from ._memory_helpers import *  # noqa: F401,F403

def test_export_selected_strategy_artifact_requires_hosted_contract_for_stateful_branch(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "state_aware")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
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

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is False
    assert result["skipReason"] == "hosted_paper_contract_required"
    request = json.loads(
        Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8")
    )
    assert request["kind"] == "hosted_paper_contract"
    assert any(signal["kind"] == "state_like_file" for signal in request["signals"])


def test_export_selected_strategy_artifact_uses_local_runtime_state_source(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "runtime_state_source")
    _write_strategy_artifact_inputs(branch)
    state_file = branch / ".abel-runtime" / "state" / "model" / "latest.joblib"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("runtime state\n", encoding="utf-8")
    (branch / ".abel-runtime" / "state" / "model" / "scratch.joblib").write_text(
        "undeclared state\n",
        encoding="utf-8",
    )
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
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
    output_dir = tmp_path / "exported-artifact"

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        evaluated = _fake_evaluate_command(command)
        if evaluated is not None:
            return evaluated
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,1,0,backfill,1\n"
                "2020-01-02,0,0,1,0,backfill,1\n"
                "2020-01-03,0,0,1,0,backfill,1\n"
                "2020-01-04,0,0,1,0,backfill,1\n",
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
                        "fileCount": 10,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert first_result["artifactExported"] is False
    promoted_dir = Path(first_result["promotionReport"]["requestPath"]).parent
    (promoted_dir / "engine.py").write_text(
        "import json\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"strategy/model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent packaged runtime state seed.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": str(state_file),
                            "purpose": "latest runtime model seed",
                        }
                    ],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(
                        uses_state=True,
                        cutover_state_required=True,
                    ),
                ),
                "limitations": [],
                "replacements": [],
            }
        ),
        encoding="utf-8",
    )

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    file_paths = [item["path"] for item in manifest["files"]]
    assert result["promotionMode"] == "agent_paper_contract"
    assert "runtime/initial-state/strategy/model/latest.joblib" in file_paths
    assert "runtime/initial-state/strategy/paper_state.json" in file_paths
    assert not any(path.startswith("strategy/.abel-runtime/") for path in file_paths)


def test_export_selected_strategy_artifact_agent_paper_contracts_dynamic_state_path(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "ambiguous_state")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "model" / "feature_scaler.json").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from pathlib import Path\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = Path(\"model/latest.joblib\")\n"
        "        scaler_path = Path(\"model\") / \"feature_scaler.json\"\n"
        "        return ctx.decisions(1)\n",
        encoding="utf-8",
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

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        evaluated = _fake_evaluate_command(command)
        if evaluated is not None:
            return evaluated
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,1,0,backfill,1\n"
                "2020-01-02,0,0,1,0,backfill,1\n"
                "2020-01-03,0,0,1,0,backfill,1\n"
                "2020-01-04,0,0,1,0,backfill,1\n",
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
                        "fileCount": 12,
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    output_dir = tmp_path / "exported-artifact"
    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert first_result["artifactExported"] is False
    assert first_result["skipReason"] == "hosted_paper_contract_required"
    request_path = Path(first_result["promotionReport"]["requestPath"])
    assert request_path.exists()

    promoted_dir = request_path.parent
    promoted_engine = promoted_dir / "engine.py"
    promoted_engine.write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "import json\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def _state_path(self):\n"
        "        return context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"strategy/model/latest.joblib\"\n"
        "        scaler_path = ctx.state_dir / \"strategy/model/feature_scaler.json\"\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent moved model paths onto ctx.state_dir.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": "model/latest.joblib",
                            "purpose": "latest model seed",
                        },
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/feature_scaler.json",
                            "sourcePath": "model/feature_scaler.json",
                            "purpose": "feature scaler seed",
                        },
                    ],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(
                        uses_state=True,
                        cutover_state_required=True,
                    ),
                ),
                "limitations": [],
                "replacements": [
                    {
                        "path": "model/latest.joblib",
                        "replacement": "ctx.state_dir / \"strategy/model/latest.joblib\"",
                    },
                    {
                        "path": "model/feature_scaler.json",
                        "replacement": "ctx.state_dir / \"strategy/model/feature_scaler.json\"",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert result["artifactExported"] is True
    assert result["skipReason"] == ""
    assert result["promotionMode"] == "agent_paper_contract"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["promotion"]["mode"] == "agent_paper_contract"
    assert manifest["promotion"]["contract"]["kind"] == "hosted_paper_contract"
    assert manifest["promotion"]["gate"] == {
        "status": "passed",
        "evidencePath": "edge/promotion-gate.json",
    }
    file_paths = [item["path"] for item in manifest["files"]]
    assert "edge/promotion-gate.json" in file_paths
    assert "edge/promotion.patch" in file_paths
    assert "edge/paper-contract-report.json" in file_paths
    assert "runtime/initial-state/strategy/model/latest.joblib" in file_paths
    assert "runtime/initial-state/strategy/model/feature_scaler.json" in file_paths
    assert "runtime/initial-state/strategy/paper_state.json" in file_paths
    promoted_engine = output_dir / "promoted" / "engine.py"
    promoted_source = promoted_engine.read_text(encoding="utf-8")
    assert 'ctx.state_dir / "strategy/model/latest.joblib"' in promoted_source
    assert 'ctx.state_dir / "strategy/model/feature_scaler.json"' in promoted_source


def test_promotion_state_dependency_scan_records_state_like_facts(tmp_path: Path) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    runtime_state = branch / ".abel-runtime" / "state" / "strategy" / "model.joblib"
    runtime_state.parent.mkdir(parents=True)
    runtime_state.write_text("state\n", encoding="utf-8")
    source_path = branch / "engine.py"
    source_path.write_text(
        "MODEL_PATH = 'models/AAPL/registry.json'\n"
        "class BranchEngine:\n"
        "    def compute_decisions(self, ctx):\n"
        "        return MODEL_PATH\n",
        encoding="utf-8",
    )

    scan = promotion_helpers._collect_hosted_paper_dependency_scan(
        branch,
        strategy_source_path=source_path,
        is_denylisted_source=lambda path: False,
    )

    signals = scan["stateDependencies"]
    assert any(signal["kind"] == "runtime_state_file" for signal in signals)
    assert any(signal["kind"] == "source_state_reference" for signal in signals)


def test_export_selected_strategy_artifact_regenerates_missing_metric_input(
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
    output_dir = tmp_path / "exported-artifact"
    _seed_promoted_stateless_paper_artifact(output_dir)
    commands_seen = []

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        commands_seen.append(command)
        if "evaluate" in command:
            result_path = Path(command[command.index("--output-json") + 1])
            report_path = Path(command[command.index("--output-md") + 1])
            metric_input_path = Path(command[command.index("--output-csv") + 1])
            payload = _candidate_result_payload()
            payload["implementation_contract"] = "decision_context"
            payload["metrics"]["sharpe"] = 0.967
            payload["metrics"]["lo_adjusted"] = 1.056
            payload["metrics"]["max_dd"] = -0.1278
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            report_path.write_text("# validation\n", encoding="utf-8")
            metric_input_path.write_text(
                "date,asset_return,pnl,position,gross_pnl,turnover,execution_cost,next_position\n"
                "2020-01-01,0,0,0,0,0,0,0\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
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
    assert any("evaluate" in command for command in commands_seen)
    assert (output_dir / "metric-input.csv").exists()


def test_export_selected_strategy_artifact_skips_without_validation(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    _write_strategy_result_row(
        session,
        branch,
        round_id="round-001",
        verdict="ERROR",
        sharpe=0.1,
        lo_adj=0.2,
        max_dd=-0.3,
    )

    def unexpected_runner(*args, **kwargs):
        raise AssertionError("unexpected")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=unexpected_runner,
    )

    assert result == {
        "artifactExported": False,
        "artifactUploadSkipped": True,
        "skipReason": "no_validation_strategy",
        "selectedBranchId": None,
        "selectedRoundId": None,
    }


def test_prepared_strategy_artifact_upload_returns_upload_summary(
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
    _seed_promoted_stateless_paper_artifact(tmp_path / "exported-artifact")

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

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                b'{"data": {"artifactUploadId": "upload_1", "status": "uploaded", '
                b'"admissionStatus": "queued", "strategyId": null}}'
            )

    export_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin="python-test",
        runner=fake_runner,
    )
    result = ni.upload_prepared_strategy_artifact_for_session(
        narrative_result={"data": {"sessionId": "sess_1", "uploadId": "narrative_1"}},
        base_url="https://router.example",
        api_key="secret-key",
        export_result=export_result,
        opener=lambda request, timeout: _Response(),
    )

    assert result["artifactUploadFailed"] is False
    assert result["artifactUploadId"] == "upload_1"
    assert result["admissionStatus"] == "queued"
    assert result["selectedBranchId"] == "momentum_lead"
