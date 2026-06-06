from __future__ import annotations

from ._memory_helpers import *  # noqa: F401,F403

def test_export_selected_strategy_artifact_agent_packages_initial_state(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "stateful_model")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from pathlib import Path\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = Path(\"model/latest.joblib\")\n"
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
    commands_seen = []

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        commands_seen.append(command)
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
    assert first_result["skipReason"] == "hosted_paper_contract_required"
    request_path = Path(first_result["promotionReport"]["requestPath"])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["kind"] == "hosted_paper_contract"
    assert any(signal["kind"] == "state_like_file" for signal in request["signals"])
    promoted_dir = request_path.parent
    (promoted_dir / "engine.py").write_text(
        "import json\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def _state_path(self):\n"
        "        return context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"strategy/model/latest.joblib\"\n"
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
        "        return {'next_position': 1.0, 'state_root': str(path.parent), 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent rewrote model access and packaged startup state.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": "model/latest.joblib",
                            "purpose": "model seed required by hosted paper signal",
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
                "replacements": [
                    {
                        "path": "model/latest.joblib",
                        "replacement": "ctx.state_dir / \"strategy/model/latest.joblib\"",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (promoted_dir / "dependency-scan.json").write_text("{}", encoding="utf-8")
    (promoted_dir / "packaging-plan.json").write_text("{}", encoding="utf-8")
    legacy_replay_dir = output_dir / "promotion-replay"
    legacy_replay_dir.mkdir()
    (legacy_replay_dir / "edge-result.json").write_text("{}", encoding="utf-8")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    assert result["promotionMode"] == "agent_paper_contract"
    assert manifest["runtime"]["state"]["bootstrap"] == {
        "mode": "copy_from_base",
        "path": "runtime/initial-state/",
    }
    assert manifest["promotion"]["mode"] == "agent_paper_contract"
    assert manifest["promotion"]["gate"] == {
        "status": "passed",
        "evidencePath": "edge/promotion-gate.json",
    }
    file_paths = [item["path"] for item in manifest["files"]]
    assert "runtime/initial-state/strategy/model/latest.joblib" in file_paths
    assert "runtime/initial-state/strategy/paper_state.json" in file_paths
    assert "edge/promotion-gate.json" in file_paths
    assert "edge/promotion.patch" in file_paths
    assert "edge/paper-contract-report.json" in file_paths
    promoted_engine = output_dir / "promoted" / "engine.py"
    assert 'ctx.state_dir / "strategy/model/latest.joblib"' in promoted_engine.read_text(
        encoding="utf-8"
    )
    export_command = next(command for command in commands_seen if "export-artifact" in command)
    assert "--extra-source-map" in export_command


def test_export_selected_strategy_artifact_requires_hosted_contract_for_runtime_state(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "runtime_state_without_intent")
    _write_strategy_artifact_inputs(branch)
    runtime_state = branch / ".abel-runtime" / "state" / "model" / "latest.json"
    runtime_state.parent.mkdir(parents=True)
    runtime_state.write_text(json.dumps({"model": "latest"}), encoding="utf-8")
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

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactUploadSkipped"] is True
    assert result["skipReason"] == "hosted_paper_contract_required"
    report = result["promotionReport"]
    assert report["mode"] == "hosted_paper_contract_required"
    assert "hosted paper contract required" in report["reason"]
    request = json.loads(Path(report["requestPath"]).read_text(encoding="utf-8"))
    assert request["kind"] == "hosted_paper_contract"
    assert request["scope"] == "hosted_paper_contract"
    assert any(signal["kind"] == "runtime_state_file" for signal in request["signals"])
    full_facts = json.loads(
        Path(request["factSidecars"]["fullFactsPath"]).read_text(encoding="utf-8")
    )
    assert any(
        item["kind"] == "runtime_state_file"
        for item in full_facts["stateDependencies"]
    )


def test_export_selected_strategy_artifact_requires_hosted_contract_for_ad_hoc_paths(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "ad_hoc_model_registry")
    _write_strategy_artifact_inputs(branch)
    (branch / "engine.py").write_text(
        "from pathlib import Path\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        registry = Path('models') / 'AAPL' / 'registry.json'\n"
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

    assert result["artifactUploadSkipped"] is True
    request = json.loads(
        Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8")
    )
    assert request["kind"] == "hosted_paper_contract"
    assert any(signal["kind"] == "source_state_reference" for signal in request["signals"])


def test_export_selected_strategy_artifact_requires_hosted_contract_for_absolute_asset_path(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("ETHUSD", "eth-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "absolute_asset_path")
    _write_strategy_artifact_inputs(branch, target="ETHUSD")
    external_asset = tmp_path / "trading-internal" / "data" / "trade_log_dual_resonance.csv"
    external_asset.parent.mkdir(parents=True)
    external_asset.write_text("date,position\n2020-01-01,1\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "import pandas as pd\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        f"_LOG = \"{external_asset}\"\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        df = pd.read_csv(_LOG)\n"
        "        return ctx.decisions(float(df['position'].iloc[-1]))\n",
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
    assert request["scope"] == "hosted_paper_contract"
    assert request["facts"]["strategyProfile"]["getPaperSignalImplemented"] is False
    assert any(
        signal["kind"] == "developer_local_absolute_path"
        for signal in request["signals"]
    )
    assert (Path(result["promotionReport"]["requestPath"]).parent / "engine.py").is_file()


def test_export_selected_strategy_artifact_agent_packages_external_base_asset(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("ETHUSD", "eth-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "agent_packaged_asset")
    _write_strategy_artifact_inputs(branch, target="ETHUSD")
    external_asset = tmp_path / "trading-internal" / "data" / "trade_log_dual_resonance.csv"
    external_asset.parent.mkdir(parents=True)
    external_asset.write_text("date,position\n2020-01-01,1\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "import pandas as pd\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        f"_LOG = \"{external_asset}\"\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        df = pd.read_csv(_LOG)\n"
        "        return ctx.decisions(float(df['position'].iloc[-1]))\n",
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

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )
    request_path = Path(first_result["promotionReport"]["requestPath"])
    promoted_dir = request_path.parent
    (promoted_dir / "engine.py").write_text(
        "import pandas as pd\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        log_path = ctx.paths.base_strategy / \"assets/trade_log_dual_resonance.csv\"\n"
        "        df = pd.read_csv(log_path)\n"
        "        return ctx.decisions(float(df['position'].iloc[-1]))\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        date = str(as_of) if as_of is not None else 'not-run'\n"
        "        return {'next_position': 1.0, 'date': date}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent packaged external replay log as read-only base asset.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("asset_path_normalization"),
                "paths": {
                    "packagedFiles": [
                        {
                            "artifactPath": "strategy/assets/trade_log_dual_resonance.csv",
                            "sourcePath": str(external_asset),
                            "purpose": "read-only replay log used by the promoted strategy",
                        }
                    ],
                },
                "paperSignal": _paper_signal(
                    live_readiness="simple one-row paper signal for hosted smoke coverage",
                ),
                "limitations": [],
                "replacements": [
                    {
                        "path": "external replay log",
                        "replacement": (
                            "ctx.paths.base_strategy / "
                            "\"assets/trade_log_dual_resonance.csv\""
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (promoted_dir / "dependency-scan.json").write_text("{}", encoding="utf-8")
    (promoted_dir / "packaging-plan.json").write_text("{}", encoding="utf-8")
    legacy_replay_dir = output_dir / "promotion-replay"
    legacy_replay_dir.mkdir()
    (legacy_replay_dir / "edge-result.json").write_text("{}", encoding="utf-8")

    result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is True
    assert result["promotionMode"] == "agent_paper_contract"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    file_paths = [item["path"] for item in manifest["files"]]
    assert "strategy/assets/trade_log_dual_resonance.csv" in file_paths
    assert "edge/paper-contract-report.json" in file_paths
    assert "edge/dependency-scan.json" not in file_paths
    assert "edge/packaging-plan.json" not in file_paths
    assert not (promoted_dir / "dependency-scan.json").exists()
    assert not (promoted_dir / "packaging-plan.json").exists()
    assert not legacy_replay_dir.exists()
    gate = json.loads((output_dir / "promotion-gate.json").read_text(encoding="utf-8"))
    paper_gate = next(item for item in gate["gates"] if item["name"] == "paper_dry_run")
    assert paper_gate["method"] == "edge_paper_run_one_tail_smoke"
    assert paper_gate["details"]["smoke"]["nextPosition"] == 1.0
    assert paper_gate["details"]["smoke"]["tailConsistency"]["status"] == "passed"
    assert paper_gate["details"]["smoke"]["tailConsistency"]["sampleSize"] == 1
    promoted_source = (output_dir / "promoted" / "engine.py").read_text(encoding="utf-8")
    assert str(external_asset) not in promoted_source
    artifact_report = json.loads(
        (output_dir / "promoted" / "paper-contract-report.artifact.json").read_text(
            encoding="utf-8"
        )
    )
    assert str(external_asset) not in json.dumps(artifact_report)
    artifact_packaged_file = artifact_report["paths"]["packagedFiles"][0]
    assert "sourcePath" not in artifact_packaged_file


def test_export_selected_strategy_artifact_requires_hosted_contract_for_nonstandard_import(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("GNRC", "gnrc-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "ml_walk_forward")
    _write_strategy_artifact_inputs(branch, target="GNRC", selected_inputs=["RTX"])
    (branch / "engine.py").write_text(
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        _ = RandomForestClassifier(n_estimators=2)\n"
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
    assert any(signal["kind"] == "nonstandard_import" for signal in request["signals"])
    full_facts = json.loads(
        Path(request["factSidecars"]["fullFactsPath"]).read_text(encoding="utf-8")
    )
    imports = full_facts["imports"]
    assert {"module": "sklearn", "classification": "nonstandard"} in imports


def test_export_selected_strategy_artifact_agent_adds_stateful_paper_signal(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("GNRC", "gnrc-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "agent_stateful_ml")
    _write_strategy_artifact_inputs(branch, target="GNRC", selected_inputs=["RTX"])
    (branch / "engine.py").write_text(
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        _ = RandomForestClassifier(n_estimators=2)\n"
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

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=_fake_artifact_export_runner,
    )
    promoted_dir = Path(first_result["promotionReport"]["requestPath"]).parent
    (promoted_dir / "engine.py").write_text(
        "import json\n"
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def _state_path(self):\n"
        "        return context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "    def compute_decisions(self, ctx):\n"
        "        _ = RandomForestClassifier(n_estimators=2)\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of), 'state_root': str(path.parent)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent added stateful paper signal entrypoint.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(uses_state=True, cutover_state_required=True),
                    live_readiness="uses runtime state path and returns scalar audit fields",
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
        runner=_fake_artifact_export_runner,
    )

    assert result["artifactExported"] is True
    assert result["promotionMode"] == "agent_paper_contract"
    manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
    file_paths = [item["path"] for item in manifest["files"]]
    assert "runtime/initial-state/strategy/paper_state.json" in file_paths
    assert "edge/paper-contract-report.json" in file_paths


def test_export_selected_strategy_artifact_ignores_legacy_state_intent(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "legacy_state_intent")
    _write_strategy_artifact_inputs(branch)
    runtime_state = branch / ".abel-runtime" / "state" / "model" / "debug.json"
    runtime_state.parent.mkdir(parents=True)
    runtime_state.write_text(json.dumps({"debug": True}), encoding="utf-8")
    (branch / "state_intent.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.state-intent/v1",
                "selfCheck": {
                    "status": "no_durable_state",
                    "summary": "debug state is not required for paper startup",
                },
                "entries": [],
            }
        ),
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
    assert "stateIntentPath" not in request
    assert "requiredStateIntentTemplate" not in request


def test_export_selected_strategy_artifact_normalizes_relative_python_bin(
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
    commands_seen = []

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        commands_seen.append(command)
        assert Path(command[0]).is_absolute()
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

    ni.export_selected_strategy_artifact(
        session,
        output_dir=tmp_path / "exported-artifact",
        python_bin=".venv/bin/python",
        runner=fake_runner,
    )

    assert commands_seen[0][0] == str((Path.cwd() / ".venv/bin/python").absolute())
