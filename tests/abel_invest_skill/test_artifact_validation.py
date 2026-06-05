from __future__ import annotations

from ._memory_helpers import *  # noqa: F401,F403

def test_export_selected_strategy_artifact_rejects_full_compute_paper_signal(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "full_compute_paper_signal")
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

    def fake_runner(command, cwd=None, capture_output=None, text=None, env=None):
        if "evaluate" in command:
            raise AssertionError("promotion must not full-replay the strategy")
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
        raise AssertionError(f"unexpected command: {command}")

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )

    assert first_result["artifactExported"] is False
    request_path = Path(first_result["promotionReport"]["requestPath"])
    promoted_dir = request_path.parent
    (promoted_dir / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model_path = ctx.state_dir / \"strategy/model/latest.joblib\"\n"
        "        return ctx.decisions(1)\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        compiled = self.compute_runtime_output(end=as_of)\n"
        "        return {'next_position': float(compiled.next_position[-1])}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent rewrote state path for hosted paper.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": "model/latest.joblib",
                            "purpose": "model seed required for hosted paper",
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

    assert result["artifactExported"] is False
    assert result["skipReason"] == "hosted_paper_contract_required"
    assert "gatePath" in result["promotionReport"]
    gate = json.loads(Path(result["promotionReport"]["gatePath"]).read_text(encoding="utf-8"))
    paper_gate = next(item for item in gate["gates"] if item["name"] == "paper_dry_run")
    assert paper_gate["method"] == "paper_signal_contract_static"
    assert "compute_runtime_output" in paper_gate["details"]["reason"]


def test_export_selected_strategy_artifact_rejects_tail_signal_mismatch(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "tail_signal_mismatch")
    _write_strategy_artifact_inputs(branch)
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        return ctx.decisions(0)\n",
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
        if "-c" in command:
            trade_log_path = Path(command[-1])
            trade_log_path.write_text(
                "date,asset_return,pnl,position,cum_return,source,next_position\n"
                "2020-01-01,0,0,0,0,backfill,0\n"
                "2020-01-02,0,0,0,0,backfill,0\n"
                "2020-01-03,0,0,0,0,backfill,0\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"tradeLogPath": str(trade_log_path)}),
                stderr="",
            )
        if "export-artifact" in command:
            raise AssertionError("tail mismatch must block artifact export")
        raise AssertionError(f"unexpected command: {command}")

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )
    promoted_dir = Path(first_result["promotionReport"]["requestPath"]).parent
    (promoted_dir / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        return ctx.decisions(0)\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent added a paper signal that drifts from oracle.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("source_bug_fix"),
                "paths": {"packagedFiles": []},
                "paperSignal": _paper_signal(
                    live_readiness="intentionally mismatched for gate coverage",
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

    assert result["artifactExported"] is False
    assert result["promotionMode"] == "hosted_paper_contract_required"
    gate = json.loads(Path(result["promotionReport"]["gatePath"]).read_text(encoding="utf-8"))
    paper_gate = next(item for item in gate["gates"] if item["name"] == "paper_dry_run")
    assert paper_gate["status"] == "failed"
    assert paper_gate["method"] == "edge_paper_run_one_tail_smoke"
    assert "diverged" in paper_gate["details"]["reason"]
    tail_summary = paper_gate["details"]["smoke"]["tailConsistency"]
    assert "comparisons" not in tail_summary
    assert tail_summary["mismatchCount"] == 1
    assert tail_summary["firstMismatch"]["expectedNextPosition"] == 0.0
    assert tail_summary["firstMismatch"]["actualNextPosition"] == 1.0
    trace_path = Path(result["promotionReport"]["gatePath"]).with_name(
        "promotion-tail-trace.json"
    )
    assert trace_path.is_file()
    request = json.loads(Path(result["promotionReport"]["requestPath"]).read_text(encoding="utf-8"))
    assert request["signals"][-1]["kind"] == "promotion_gate_failed"
    assert request["validation"]["lastGateFailure"]["failedGates"][0]["name"] == "paper_dry_run"
    request_tail = request["validation"]["lastGateFailure"]["failedGates"][0]["smoke"][
        "tailConsistency"
    ]
    assert request_tail["status"] == "failed"
    assert "comparisons" not in request_tail
    assert request_tail["firstMismatch"]["asOf"] == "2020-01-02"
    assert request_tail["firstMismatch"]["expectedNextPosition"] == 0.0
    assert request_tail["firstMismatch"]["actualNextPosition"] == 1.0
    assert request_tail["tracePath"] == "edge/promotion-tail-trace.json"
    assert request_tail["selectedRoundCutoverEnd"] == "2020-12-31"
    assert request_tail["firstMismatchIsSelectedRoundEnd"] is False
    assert "stateEnd" in " ".join(request_tail["immutableContractFacts"])


def test_export_selected_strategy_artifact_records_slow_training_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setitem(
        promotion_helpers._run_edge_paper_run_one_smoke.__globals__,
        "PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS",
        0.0,
    )
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "training_without_warm_start")
    _write_strategy_artifact_inputs(branch)
    (branch / "model").mkdir()
    (branch / "model" / "latest.joblib").write_text("state\n", encoding="utf-8")
    (branch / "engine.py").write_text(
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model = type('Model', (), {'fit': lambda self: None})()\n"
        "        model.fit()\n"
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

    first_result = ni.export_selected_strategy_artifact(
        session,
        output_dir=output_dir,
        python_bin="python-test",
        runner=fake_runner,
    )
    promoted_dir = Path(first_result["promotionReport"]["requestPath"]).parent
    (promoted_dir / "engine.py").write_text(
        "import json\n"
        "import time\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        model = type('Model', (), {'fit': lambda self: None})()\n"
        "        model.fit()\n"
        "        return ctx.decisions(1)\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        time.sleep(0.001)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of), 'state_root': str(path.parent)}\n",
        encoding="utf-8",
    )
    (promoted_dir / "paper-contract-report.json").write_text(
        json.dumps(
            {
                "schema": "abel-invest.agent-paper-contract-report/v1",
                "kind": "hosted_paper_contract",
                "summary": "Agent added a matching but cold-start paper signal.",
                "scope": "hosted_paper_contract",
                "sourceEdit": _source_edit("stateful_continuation"),
                "paths": {
                    "packagedFiles": [],
                    "initialStateFiles": [
                        {
                            "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
                            "sourcePath": "model/latest.joblib",
                            "purpose": "latest fitted model checkpoint seed",
                        }
                    ],
                },
                "paperSignal": _paper_signal(
                    method="stateful_continuation",
                    design=_paper_design(
                        uses_state=True,
                        cutover_state_required=True,
                    ),
                    live_readiness="tail output matches but no reusable warm-start state",
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

    assert result["artifactExported"] is True
    assert result["promotionMode"] == "agent_paper_contract"
    gate = json.loads((output_dir / "promotion-gate.json").read_text(encoding="utf-8"))
    paper_gate = next(item for item in gate["gates"] if item["name"] == "paper_dry_run")
    assert paper_gate["status"] == "passed"
    warm_start = paper_gate["details"]["smoke"]["warmStart"]
    assert warm_start["slowDistinctCallCount"] >= 2
    assert warm_start["sampleSize"] == 2
