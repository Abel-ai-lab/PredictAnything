from __future__ import annotations

import json

from abel_invest.narrative_core.contracts.constants import EVENTS_HEADER, RESULTS_HEADER
from abel_invest.narrative_core.io import write_tsv_rows
from abel_invest.narrative_core.strategy_artifacts import (
    SELECTION_METRIC_ORDER,
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
                "verdict": "PASS",
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
                "verdict": "PASS",
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
