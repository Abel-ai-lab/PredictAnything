from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from abel_invest.narrative_core.contracts.constants import EVENTS_HEADER, RESULTS_HEADER
from abel_invest.narrative_core.io import write_tsv_rows
from abel_invest.narrative_core.promotion import (
    PromotionHostedPaperRewriteRequired,
    _paper_smoke_context,
    _paper_tail_position_change_count,
    _paper_tail_selection_reason,
    _select_paper_tail_oracle_sample,
    _validate_agent_paper_signal_contract,
    _write_hosted_paper_contract_request,
)
from abel_invest.narrative_core.strategy_artifact_upload import (
    render_strategy_artifact_upload_lines,
)
from abel_invest.narrative_core.strategy_artifacts import (
    SELECTION_METRIC_ORDER,
    _cleanup_stale_strategy_artifact_outputs,
    select_best_pass_strategy,
)


def _write_candidate(
    session,
    *,
    branch_id: str,
    round_id: str,
    lo_adjusted: float,
    sharpe: float,
    annual_return: float,
    pass_score: str,
    verdict: str = "PASS",
    calmar: float = 1.0,
    max_dd: float = -0.2,
):
    branch = session / "branches" / branch_id
    result_path = branch / "outputs" / f"{round_id}-edge-result.json"
    branch.mkdir(parents=True)
    (branch / "engine.py").write_text("class BranchEngine:\n    pass\n", encoding="utf-8")
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "verdict": verdict,
                "score": pass_score,
                "metrics": {
                    "lo_adjusted": lo_adjusted,
                    "sharpe": sharpe,
                    "annual_return": annual_return,
                    "calmar": calmar,
                    "max_dd": max_dd,
                },
            }
        ),
        encoding="utf-8",
    )
    write_tsv_rows(
        branch / "results.tsv",
        RESULTS_HEADER,
        [
            {
                "exp_id": session.name,
                "ticker": "META",
                "branch_id": branch_id,
                "round_id": round_id,
                "decision": "keep",
                "lo_adj": f"{lo_adjusted:.3f}",
                "sharpe": f"{sharpe:.3f}",
                "max_dd": f"{max_dd:.4f}",
                "score": pass_score,
                "verdict": verdict,
                "result_path": str(result_path.relative_to(session)),
            }
        ],
    )


def test_select_best_pass_strategy_prioritizes_sharpe_then_annual_return(tmp_path):
    session = tmp_path / "research" / "meta" / "session-a"
    session.mkdir(parents=True)
    _write_candidate(
        session,
        branch_id="all-gates-lower-objective",
        round_id="r1",
        lo_adjusted=1.8,
        sharpe=1.5,
        annual_return=0.80,
        pass_score="4/4",
    )
    _write_candidate(
        session,
        branch_id="same-sharpe-lower-annual-return",
        round_id="r2",
        lo_adjusted=2.0,
        sharpe=2.4,
        annual_return=0.15,
        pass_score="4/4",
    )
    _write_candidate(
        session,
        branch_id="same-sharpe-higher-annual-return",
        round_id="r3",
        lo_adjusted=1.9,
        sharpe=2.4,
        annual_return=0.30,
        pass_score="3/4",
    )
    write_tsv_rows(
        session / "events.tsv",
        EVENTS_HEADER,
        [
            {
                "event": "round_recorded",
                "branch_id": "all-gates-lower-objective",
                "round_id": "r1",
            },
            {
                "event": "round_recorded",
                "branch_id": "same-sharpe-lower-annual-return",
                "round_id": "r2",
            },
            {
                "event": "round_recorded",
                "branch_id": "same-sharpe-higher-annual-return",
                "round_id": "r3",
            },
        ],
    )

    selection = select_best_pass_strategy(session)

    assert selection.selected is not None
    assert selection.selected.branch_id == "same-sharpe-higher-annual-return"
    assert tuple(SELECTION_METRIC_ORDER) == (
        "sharpe",
        "annual_return",
        "max_dd_abs",
        "pass_rate",
    )
    assert selection.selected.selection_metric_values["sharpe"] == 2.4
    assert selection.selected.selection_metric_values["annual_return"] == 0.30


def test_select_best_validation_strategy_can_select_high_sharpe_fail(tmp_path):
    session = tmp_path / "research" / "meta" / "session-b"
    session.mkdir(parents=True)
    _write_candidate(
        session,
        branch_id="lower-sharpe-pass",
        round_id="r1",
        lo_adjusted=1.8,
        sharpe=1.8,
        annual_return=0.25,
        pass_score="9/9",
        verdict="PASS",
    )
    _write_candidate(
        session,
        branch_id="higher-sharpe-near-pass",
        round_id="r2",
        lo_adjusted=2.5,
        sharpe=2.9,
        annual_return=0.40,
        pass_score="8/9",
        verdict="FAIL",
    )
    write_tsv_rows(
        session / "events.tsv",
        EVENTS_HEADER,
        [
            {
                "event": "round_recorded",
                "branch_id": "lower-sharpe-pass",
                "round_id": "r1",
            },
            {
                "event": "round_recorded",
                "branch_id": "higher-sharpe-near-pass",
                "round_id": "r2",
            },
        ],
    )

    selection = select_best_pass_strategy(session)

    assert selection.selected is not None
    assert selection.selected.branch_id == "higher-sharpe-near-pass"
    assert selection.selected.edge_result["verdict"] == "FAIL"
    assert selection.selected.selection_metric_values["pass_rate"] == 8 / 9


def test_strategy_artifact_skip_line_keeps_session_view_language():
    lines = render_strategy_artifact_upload_lines(
        {
            "artifactUploadSkipped": True,
            "skipReason": "no_hostable_validation_strategy",
        }
    )

    assert lines == [
        "Session view created without a strategy artifact: recorded validation rounds "
        "exist, but none currently has the files needed for a hostable strategy artifact"
    ]
    assert "skipped" not in lines[0].lower()


def test_artifact_export_cleanup_removes_legacy_and_completed_outputs(tmp_path):
    session = tmp_path / "research" / "meta" / "session"
    session.mkdir(parents=True)
    legacy = session / "paper_ready_artifact"
    legacy.mkdir()
    (legacy / "old.txt").write_text("old", encoding="utf-8")
    destination = tmp_path / "artifact"
    promoted = destination / "promoted"
    promoted.mkdir(parents=True)
    (destination / "artifact.zip").write_text("zip", encoding="utf-8")
    (destination / "manifest.json").write_text("{}", encoding="utf-8")
    (destination / "promotion-gate.json").write_text(
        json.dumps({"status": "passed"}),
        encoding="utf-8",
    )
    (promoted / "engine.py").write_text("class BranchEngine: pass\n", encoding="utf-8")
    (promoted / "paper-contract-report.json").write_text("{}", encoding="utf-8")

    _cleanup_stale_strategy_artifact_outputs(
        SimpleNamespace(session=session),
        destination=destination,
    )

    assert not legacy.exists()
    assert not (destination / "artifact.zip").exists()
    assert not promoted.exists()


def test_artifact_export_cleanup_preserves_active_agent_contract(tmp_path):
    session = tmp_path / "research" / "meta" / "session"
    session.mkdir(parents=True)
    destination = tmp_path / "artifact"
    promoted = destination / "promoted"
    promoted.mkdir(parents=True)
    (destination / "artifact.zip").write_text("stale", encoding="utf-8")
    (destination / "promotion-gate.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )
    (promoted / "engine.py").write_text("class BranchEngine: pass\n", encoding="utf-8")
    (promoted / "paper-contract-report.json").write_text("{}", encoding="utf-8")
    (promoted / "promotion.patch").write_text("old patch", encoding="utf-8")

    _cleanup_stale_strategy_artifact_outputs(
        SimpleNamespace(session=session),
        destination=destination,
    )

    assert not (destination / "artifact.zip").exists()
    assert (promoted / "engine.py").is_file()
    assert (promoted / "paper-contract-report.json").is_file()
    assert not (promoted / "promotion.patch").exists()


def test_contract_request_is_slim_and_marks_training_stateful(tmp_path):
    branch = tmp_path / "branch"
    promoted = tmp_path / "artifact" / "promoted"
    promoted.mkdir(parents=True)
    branch.mkdir()
    source = promoted / "engine.py"
    source.write_text("class BranchEngine: pass\n", encoding="utf-8")

    request_path = _write_hosted_paper_contract_request(
        promoted,
        branch=branch,
        source_path=source,
        dependency_scan={
            "sourceScan": {
                "positiveFindings": {
                    "observedFitCalls": ["model.fit"],
                }
            },
            "backtestWindow": {
                "effectiveWindow": {"start": "2024-01-01", "end": "2024-02-01"}
            },
        },
        signals=[],
    )

    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert payload["requirements"]["statefulContinuationRequired"] is True
    assert payload["requirements"]["continuationMethod"] == "stateful_continuation"
    assert "contractGuide" in payload
    assert "reportContract" not in payload
    assert "gateContract" not in payload
    assert "runtimeApiFacts" not in payload


def test_tail_oracle_sample_uses_dynamic_holdout_window():
    comparable = [
        {
            "decisionIndex": idx,
            "asOf": f"2024-01-{idx + 1:02d}",
            "expectedNextPosition": float(idx % 2),
        }
        for idx in range(40)
    ]

    selected = _select_paper_tail_oracle_sample(comparable)

    assert len(selected) == 20
    assert selected[0]["decisionIndex"] == 20
    assert _paper_tail_selection_reason(comparable, selected) == "target_tail_window"


def test_tail_oracle_sample_expands_to_recent_position_change():
    comparable = [
        {
            "decisionIndex": idx,
            "asOf": f"2024-03-{idx + 1:02d}",
            "expectedNextPosition": 0.0 if idx < 75 else 1.0,
        }
        for idx in range(100)
    ]

    selected = _select_paper_tail_oracle_sample(comparable)

    assert len(selected) == 25
    assert selected[0]["decisionIndex"] == 75
    assert _paper_tail_position_change_count(
        selected,
        prior=comparable[74],
    ) == 1
    assert (
        _paper_tail_selection_reason(comparable, selected)
        == "expanded_to_recent_position_change"
    )


def _write_market_feed(path, symbol: str, closes: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["timestamp,symbol,open,high,low,close,volume"]
    for idx, close in enumerate(closes, start=1):
        lines.append(
            f"2024-01-{idx:02d}T00:00:00Z,{symbol},{close},{close},{close},{close},1000"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_paper_smoke_context_uses_prepared_cache_feeds(tmp_path):
    branch = tmp_path / "branch"
    runtime = tmp_path / "runtime"
    strategy = tmp_path / "strategy"
    state = tmp_path / "state"
    source_aapl = tmp_path / "cache" / "AAPL.csv"
    source_msft = tmp_path / "cache" / "MSFT.csv"
    _write_market_feed(source_aapl, "AAPL", [10.0, 11.0])
    _write_market_feed(source_msft, "MSFT", [20.0, 21.0])
    (branch / "inputs").mkdir(parents=True)
    runtime.mkdir(parents=True)
    (runtime / "dependencies.json").write_text(
        json.dumps(
            {
                "target": "AAPL",
                "target_node": "AAPL.price",
                "selected_inputs": ["MSFT"],
                "data_requirements": {"timeframe": "1d", "fields": ["close"]},
                "requested_start": "2024-01-01",
                "cache": {
                    "results": [
                        {"symbol": "AAPL", "ok": True, "data_path": str(source_aapl)},
                        {"symbol": "MSFT", "ok": True, "data_path": str(source_msft)},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    context = _paper_smoke_context(
        SimpleNamespace(
            branch=branch,
            branch_id="candidate",
            ticker="AAPL",
            edge_result={"effective_window": {"end": "2024-01-02"}},
        ),
        strategy_dir=strategy,
        runtime_dir=runtime,
        state_dir=state,
        workspace_dir=tmp_path / "workspace",
    )

    primary = context["_feeds"]["primary"]["path"]
    msft = context["_feeds"]["MSFT"]["path"]
    primary_text = Path(primary).read_text(encoding="utf-8")
    msft_text = Path(msft).read_text(encoding="utf-8")
    assert "11.0" in primary_text
    assert "21.0" in msft_text
    assert "11.0" not in msft_text
    assert context["_promotion_validation"]["feedMode"] == "prepared_cache"


def test_paper_smoke_context_rejects_missing_prepared_feed(tmp_path):
    branch = tmp_path / "branch"
    runtime = tmp_path / "runtime"
    (branch / "inputs").mkdir(parents=True)
    runtime.mkdir(parents=True)
    (runtime / "dependencies.json").write_text(
        json.dumps(
            {
                "target": "AAPL",
                "selected_inputs": ["MSFT"],
                "cache": {
                    "results": [
                        {
                            "symbol": "AAPL",
                            "ok": True,
                            "data_path": str(tmp_path / "missing-aapl.csv"),
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing prepared market data"):
        _paper_smoke_context(
            SimpleNamespace(branch=branch, branch_id="candidate", ticker="AAPL", edge_result={}),
            strategy_dir=tmp_path / "strategy",
            runtime_dir=runtime,
            state_dir=tmp_path / "state",
            workspace_dir=tmp_path / "workspace",
        )


def test_ml_training_source_rejects_stateless_recompute_report():
    report = {
        "schema": "abel-invest.agent-paper-contract-report/v1",
        "kind": "hosted_paper_contract",
        "scope": "hosted_paper_contract",
        "summary": "paper signal",
        "paths": {"packagedFiles": [], "initialStateFiles": []},
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "continuation": {
                "method": "stateless_recompute",
                "reason": "recompute from bars",
                "futureDailyFlow": "load bars and compute signal",
            },
            "design": {
                "history": {
                    "boundary": "fixed_lookback",
                    "minBars": 10,
                    "reason": "rolling input window",
                },
                "state": {
                    "usesPersistentState": False,
                    "stateFiles": [],
                    "reason": "none",
                },
                "calendar": {
                    "usesAbsoluteDecisionOrdinal": False,
                    "reason": "none",
                },
                "cutover": {
                    "requiresStartupState": False,
                    "mode": "none",
                    "reason": "none",
                },
                "dailyStep": {"reason": "one as_of call"},
            },
            "evidence": {
                "observations": ["source read"],
                "semanticChecks": [],
                "whySufficient": "same formula",
            },
            "liveReadiness": "continues from market data",
        },
    }
    source = """
class BranchEngine:
    def get_paper_signal(self, *, as_of=None):
        return {"next_position": 0.0}
"""

    with pytest.raises(PromotionHostedPaperRewriteRequired, match="stateful_continuation"):
        _validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
            source_dependency_scan={
                "sourceScan": {
                    "positiveFindings": {
                        "observedFitCalls": ["model.fit"],
                    }
                }
            },
        )


def _stateful_training_report(*, state_reason: str) -> dict:
    return {
        "schema": "abel-invest.agent-paper-contract-report/v1",
        "kind": "hosted_paper_contract",
        "scope": "hosted_paper_contract",
        "summary": "stateful paper signal",
        "paths": {
            "packagedFiles": [],
            "initialStateFiles": [],
        },
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "continuation": {
                "method": "stateful_continuation",
                "reason": "continue fitted training state",
                "futureDailyFlow": "load state and advance one as_of",
            },
            "design": {
                "history": {
                    "boundary": "origin_anchored",
                    "minBars": 20,
                    "origin": "2024-01-01",
                    "reason": "ordinal calendar",
                },
                "state": {
                    "usesPersistentState": True,
                    "stateFiles": ["strategy/paper-state.pkl"],
                    "schema": "paper-state/v1",
                    "validThrough": "2024-02-01",
                    "reason": state_reason,
                },
                "calendar": {
                    "usesAbsoluteDecisionOrdinal": True,
                    "origin": "2024-01-01",
                    "reason": "row ordinal",
                },
                "cutover": {
                    "requiresStartupState": True,
                    "mode": "minimal_cutover_state",
                    "dataHistoryStart": "2024-01-01",
                    "stateEnd": "2024-02-01",
                    "bootstrapHook": "build_paper_initial_state",
                    "reason": "startup state is valid through cutover",
                },
                "dailyStep": {"reason": "advance from the persisted state"},
            },
            "evidence": {
                "observations": ["source read"],
                "semanticChecks": ["cutover state validity checked"],
                "whySufficient": "same state schema is used by bootstrap and paper",
            },
            "liveReadiness": "future calls load state and continue",
        },
        "limitations": [],
        "replacements": [],
    }


def _stateful_source() -> str:
    return """
from abel_edge.runtime_paths import context_runtime_paths

class BranchEngine:
    def __init__(self, context=None):
        self.context = context or {}

    def build_paper_initial_state(self, *, cutover_as_of=None):
        return {}

    def get_paper_signal(self, *, as_of=None):
        paths = context_runtime_paths(self.context)
        state_path = paths.state / "strategy" / "paper-state.pkl"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("state")
        return {"next_position": 0.0}
"""


def test_ml_training_stateful_rejects_cursor_only_state_report():
    with pytest.raises(PromotionHostedPaperRewriteRequired, match="fitted-object"):
        _validate_agent_paper_signal_contract(
            _stateful_training_report(
                state_reason=(
                    "paper state stores last as_of, last next_position, and row cursor"
                )
            ),
            _stateful_source(),
            require_paper_signal=True,
            source_dependency_scan={
                "sourceScan": {
                    "positiveFindings": {"observedFitCalls": ["model.fit"]}
                }
            },
        )


def test_ml_training_stateful_accepts_fitted_object_state_evidence():
    _validate_agent_paper_signal_contract(
        _stateful_training_report(
            state_reason=(
                "paper state stores fitted model, scaler, last fit index, and row cursor"
            )
        ),
        _stateful_source(),
        require_paper_signal=True,
        source_dependency_scan={
            "sourceScan": {"positiveFindings": {"observedFitCalls": ["model.fit"]}}
        },
    )


def test_contract_request_budget_can_open_fallback_before_third_live_failure(tmp_path):
    branch = tmp_path / "branch"
    promoted = tmp_path / "artifact" / "promoted"
    promoted.mkdir(parents=True)
    branch.mkdir()
    source = promoted / "engine.py"
    source.write_text("class BranchEngine: pass\n", encoding="utf-8")
    dependency_scan = {
        "sourceScan": {"positiveFindings": {"observedFitCalls": ["model.fit"]}},
    }
    validation_failure = {"failedGates": [{"name": "paper_dry_run"}]}

    request_path = _write_hosted_paper_contract_request(
        promoted,
        branch=branch,
        source_path=source,
        dependency_scan=dependency_scan,
        signals=[],
    )
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert payload["attemptPolicy"]["contractRequestRefreshes"] == 1
    assert payload["attemptPolicy"]["fullReplayFallbackEligible"] is False

    _write_hosted_paper_contract_request(
        promoted,
        branch=branch,
        source_path=source,
        dependency_scan=dependency_scan,
        signals=[],
        validation_failure=validation_failure,
    )
    request_path = _write_hosted_paper_contract_request(
        promoted,
        branch=branch,
        source_path=source,
        dependency_scan=dependency_scan,
        signals=[],
        validation_failure=validation_failure,
    )
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert payload["attemptPolicy"]["liveContractFailures"] == 2
    assert payload["attemptPolicy"]["contractRequestRefreshes"] == 3
    assert payload["attemptPolicy"]["fullReplayFallbackEligible"] is True
    assert payload["attemptPolicy"]["fallbackEligibilityReason"] == "contract_request_budget"
