from __future__ import annotations

from ._memory_helpers import *  # noqa: F401,F403

def test_paper_smoke_bootstraps_state_before_holdout_tail(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "stateful_holdout")
    _write_strategy_artifact_inputs(branch)
    promoted_dir = branch / "promoted"
    promoted_dir.mkdir()
    seed_state = branch / "paper-state.json"
    seed_state.write_text("{}", encoding="utf-8")
    promoted_source = promoted_dir / "engine.py"
    promoted_source.write_text(
        "import json\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def _state_path(self):\n"
        "        from pathlib import Path\n"
        "        return Path(self.context['_runtime_paths']['state']) / 'strategy/paper-state.json'\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = self._state_path()\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        state = {'cutover': str(cutover_as_of), 'seen': []}\n"
        "        path.write_text(json.dumps(state), encoding='utf-8')\n"
        "        return state\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = self._state_path()\n"
        "        state = json.loads(path.read_text(encoding='utf-8'))\n"
        "        if str(as_of) not in state['seen']:\n"
        "            state['seen'].append(str(as_of))\n"
        "            path.write_text(json.dumps(state), encoding='utf-8')\n"
        "        return {'next_position': 1.0, 'date': str(as_of)}\n",
        encoding="utf-8",
    )
    destination = tmp_path / "artifact"
    destination.mkdir()
    (destination / "trade-log.csv").write_text(
        "date,next_position\n"
        "2020-01-01,0\n"
        "2020-01-02,1\n"
        "2020-01-03,1\n"
        "2020-01-04,1\n",
        encoding="utf-8",
    )
    candidate = Namespace(
        branch=branch,
        strategy_source_path=branch / "engine.py",
        branch_id="stateful_holdout",
        ticker="TSLA",
        edge_result={"effective_window": {"end": "2020-01-04"}},
    )
    report = {
        "paths": {
            "initialStateFiles": [
                {
                    "artifactPath": "runtime/initial-state/strategy/paper-state.json",
                    "sourcePath": str(seed_state),
                    "purpose": "production startup state seed",
                }
            ]
        },
        "paperSignal": {
            "continuation": _paper_continuation("stateful_continuation"),
            "design": _paper_design(
                uses_state=True,
                cutover_state_required=True,
            ),
        },
    }
    report["paperSignal"]["design"]["cutover"][
        "stateEnd"
    ] = "2020-01-04"

    smoke = promotion_helpers._run_edge_paper_run_one_smoke(
        candidate,
        strategy_source_path=promoted_source,
        packaged_files=(
            promotion_helpers.PromotionPackagedFile(
                artifact_path="runtime/initial-state/strategy/paper-state.json",
                source_path=seed_state,
                purpose="production startup state seed",
                role="initial_state",
            ),
        ),
        destination=destination,
        strategy_entrypoint="strategy.py",
        runtime_env={},
        is_denylisted_source=lambda path: False,
        report=report,
    )

    assert smoke["status"] == "passed"
    assert smoke["validationBootstrap"]["status"] == "passed"
    assert smoke["validationBootstrap"]["cutoverAsOf"] == "2020-01-01"
    assert smoke["tailConsistency"]["validationCutoverAsOf"] == "2020-01-01"
    assert smoke["tailConsistency"]["sampleSize"] == 2
    assert smoke["stateChangedFirstCall"] is True
    assert smoke["stateChangedSecondCall"] is False


def test_paper_smoke_timeout_returns_compact_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import time as _time

    def slow_smoke(*args, **kwargs):
        _time.sleep(1)
        return {"status": "passed"}

    monkeypatch.setitem(
        promotion_helpers._run_edge_paper_run_one_smoke.__globals__,
        "_run_edge_paper_run_one_smoke_unbounded",
        slow_smoke,
    )
    monkeypatch.setitem(
        promotion_helpers._run_edge_paper_run_one_smoke.__globals__,
        "PROMOTION_HOSTED_PAPER_TIMEOUT_SECONDS",
        0.01,
    )

    smoke = promotion_helpers._run_edge_paper_run_one_smoke(
        object(),
        strategy_source_path=tmp_path / "engine.py",
        packaged_files=(),
        destination=tmp_path,
        strategy_entrypoint="strategy.py",
        runtime_env={},
        is_denylisted_source=lambda path: False,
        report={},
    )

    assert smoke["status"] == "failed"
    assert smoke["timeoutSeconds"] == 0.01
    assert "timed out" in smoke["reason"]
    assert "compute_runtime_output" in smoke["diagnosis"]["check"]


def test_paper_signal_design_facts_detects_runtime_path_helper_state() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        paths = context_runtime_paths(self.context)\n"
        "        state_root = paths.state / 'strategy'\n"
        "        return {'next_position': 1.0, 'state': str(state_root)}\n"
    )

    facts = promotion_helpers._paper_signal_design_facts(source)

    assert facts["usesStateDir"] is True


def test_paper_signal_design_facts_detects_helper_state_writes() -> None:
    source = (
        "import pickle\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "def _save_paper_state(path, state):\n"
        "    with path.open('wb') as fh:\n"
        "        pickle.dump(state, fh)\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        paths = context_runtime_paths(self.context)\n"
        "        state_path = paths.state / 'strategy' / 'paper_state.pkl'\n"
        "        _save_paper_state(state_path, {'as_of': str(as_of)})\n"
        "        return {'next_position': 1.0}\n"
    )

    facts = promotion_helpers._paper_signal_design_facts(source)

    assert facts["usesStateDir"] is True
    assert facts["writesState"] is True


def test_temporal_dependency_facts_surface_lookback_and_calendar_hints() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "TRAIN_WINDOW = 360\n"
        "REFIT_EVERY = 20\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        close = ctx.target.series('close')\n"
        "        features = close.pct_change(60).shift(1).rolling(window=20).mean()\n"
        "        for row_idx in range(180, len(close) - 1):\n"
        "            if row_idx % REFIT_EVERY == 0:\n"
        "                train_x = features.iloc[row_idx - TRAIN_WINDOW:row_idx]\n"
        "        return ctx.decisions(0)\n"
    )
    tree = ast.parse(source)

    facts = promotion_helpers._source_temporal_dependency_facts(source, tree)

    lookbacks = " ".join(item["expression"] for item in facts["lookbackHints"])
    calendar = " ".join(item["expression"] for item in facts["calendarHints"])
    constants = {item["name"]: item["value"] for item in facts["constantHints"]}
    assert "pct_change(60)" in lookbacks
    assert "rolling(window=20)" in lookbacks
    assert "row_idx % REFIT_EVERY" in calendar
    assert "range(180, len(close) - 1)" in calendar
    assert constants["TRAIN_WINDOW"] == "360"
    assert constants["REFIT_EVERY"] == "20"
