"""Primary strategy selection for skill dashboard uploads."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SELECTION_RULE = "score_desc_total_return_desc_lo_adjusted_desc_sharpe_desc_latest_v1"


@dataclass(frozen=True)
class RoundCandidate:
    branch_id: str
    round_id: str
    session_round_index: int
    row: dict[str, str]
    session: Path

    @property
    def score_value(self) -> int:
        return _score_value(self.row.get("score", ""))

    @property
    def total_return(self) -> float:
        return _percent_to_ratio(self.row.get("pnl", ""))

    @property
    def lo_adjusted(self) -> float:
        return _float_value(self.row.get("lo_adj", ""))

    @property
    def sharpe(self) -> float:
        return _float_value(self.row.get("sharpe", ""))


def select_primary_strategy(
    *,
    session: Path,
    branches: list[dict[str, Any]],
    session_round_indexes: dict[tuple[str, str], int],
) -> dict[str, Any] | None:
    recorded_round_keys = set(session_round_indexes)
    candidates = _round_candidates(
        session=session,
        branches=branches,
        session_round_indexes=session_round_indexes,
        recorded_round_keys=recorded_round_keys,
    )
    if not candidates:
        return None
    selected = max(
        candidates,
        key=lambda item: (
            item.score_value,
            item.total_return,
            item.lo_adjusted,
            item.sharpe,
            item.session_round_index,
        ),
    )
    return _primary_strategy_payload(selected)


def _round_candidates(
    *,
    session: Path,
    branches: list[dict[str, Any]],
    session_round_indexes: dict[tuple[str, str], int],
    recorded_round_keys: set[tuple[str, str]],
) -> list[RoundCandidate]:
    candidates: list[RoundCandidate] = []
    for branch in branches:
        branch_dir = branch["branch_dir"]
        branch_id = branch_dir.name
        for row in branch["rows"]:
            round_id = str(row.get("round_id") or "").strip()
            if not round_id:
                continue
            if (branch_id, round_id) not in recorded_round_keys:
                continue
            if str(row.get("verdict") or "").strip().upper() != "PASS":
                continue
            if str(row.get("decision") or "").strip().lower() != "keep":
                continue
            if _score_value(row.get("score", "")) <= 0:
                continue
            candidates.append(
                RoundCandidate(
                    branch_id=branch_id,
                    round_id=round_id,
                    session_round_index=session_round_indexes.get(
                        (branch_id, round_id),
                        len(session_round_indexes) + 1,
                    ),
                    row=row,
                    session=session,
                )
            )
    return candidates


def _primary_strategy_payload(candidate: RoundCandidate) -> dict[str, Any]:
    result_ref = str(candidate.row.get("result_path") or "").strip()
    report_ref = str(candidate.row.get("report_path") or "").strip()
    edge_metrics = _edge_result_metrics(candidate.session, result_ref)
    return {
        "branchId": candidate.branch_id,
        "roundId": candidate.round_id,
        "strategyKey": f"{candidate.branch_id}:{candidate.round_id}",
        "selectionSource": "abel_invest_results_tsv",
        "selectionRule": SELECTION_RULE,
        "selectionReason": "highest score, then highest total return; ties use lo-adjusted, Sharpe, and latest recorded round",
        "description": str(candidate.row.get("description") or "").strip(),
        "metrics": {
            "score": str(candidate.row.get("score") or "").strip(),
            "verdict": str(candidate.row.get("verdict") or "").strip(),
            "loAdjusted": candidate.lo_adjusted,
            "positionIc": _float_value(candidate.row.get("ic", "")),
            "omega": _float_value(candidate.row.get("omega", "")),
            "sharpe": candidate.sharpe,
            "maxDd": _float_value(candidate.row.get("max_dd", "")),
            "totalReturn": candidate.total_return,
            "k": _int_value(candidate.row.get("K", "")),
            "positionIcStability": _float_value(edge_metrics.get("position_ic_stability", "")),
            "dsr": _float_value(edge_metrics.get("dsr", "")),
            "lossYears": _int_value(edge_metrics.get("loss_years", "")),
        },
        "resultRef": result_ref,
        "reportRef": report_ref,
        "latestDecision": _latest_decision_from_frame(candidate.session, result_ref),
        "backtestTradeLog": _backtest_trade_log_from_frame_csv(candidate.session, result_ref),
    }


def _edge_result_metrics(session: Path, result_ref: str) -> dict[str, Any]:
    if not result_ref:
        return {}
    result_path = session / result_ref
    if not result_path.exists():
        return {}
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    metrics = payload.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def _backtest_trade_log_from_frame_csv(session: Path, result_ref: str) -> dict[str, Any] | None:
    frame_path = _frame_path_for_result_ref(session, result_ref)
    if frame_path is None or not frame_path.exists():
        return None
    trade_log_path = frame_path.with_name(frame_path.name.replace("-edge-frame.csv", "-trade-log.csv"))
    _write_trade_log_from_frame(frame_path, trade_log_path)
    return {
        "source": "abel_invest_trade_log_csv",
        "tradeLogRef": trade_log_path.relative_to(session).as_posix(),
    }


def _write_trade_log_from_frame(frame_path: Path, trade_log_path: Path) -> None:
    fields = [
        "date",
        "asset_return",
        "pnl",
        "position",
        "source",
        "decision_time",
        "effective_time",
        "next_position",
        "gross_pnl",
        "turnover",
        "execution_cost",
        "cum_return",
    ]
    with frame_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    equity = 1.0
    trade_log_path.parent.mkdir(parents=True, exist_ok=True)
    with trade_log_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            pnl = _float_value(row.get("pnl", ""))
            equity *= 1.0 + pnl
            writer.writerow(
                {
                    "date": row.get("date", ""),
                    "asset_return": row.get("asset_return", ""),
                    "pnl": row.get("pnl", ""),
                    "position": row.get("position", ""),
                    "source": "backfill",
                    "decision_time": row.get("decision_time", ""),
                    "effective_time": row.get("effective_time", ""),
                    "next_position": row.get("next_position", ""),
                    "gross_pnl": row.get("gross_pnl", ""),
                    "turnover": row.get("turnover", ""),
                    "execution_cost": row.get("execution_cost", ""),
                    "cum_return": equity - 1.0,
                }
            )


def _latest_decision_from_frame(session: Path, result_ref: str) -> dict[str, Any] | None:
    frame_path = _frame_path_for_result_ref(session, result_ref)
    if frame_path is None or not frame_path.exists():
        return None
    with frame_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    latest = rows[-1]
    previous = rows[-2] if len(rows) > 1 else {}
    previous_position = _optional_float_value(previous.get("position", ""))
    previous_position_for_action = previous_position if previous_position is not None else 0.0
    position = _float_value(latest.get("position", ""))
    next_position = _float_value(latest.get("next_position", ""))
    trading_date = _date_text(latest.get("date", ""))
    close = _optional_float_value(latest.get("close", ""))
    if close is None:
        close = _latest_close_from_result_ref(session, result_ref, trading_date=trading_date)
    return {
        "tradingDate": trading_date,
        "previousPosition": previous_position,
        "currentPosition": position,
        "position": position,
        "nextPosition": next_position,
        "delta": round(next_position - previous_position_for_action, 10),
        "action": position_action(previous_position_for_action, next_position),
        "close": close,
        "source": "abel_invest_edge_frame_csv",
    }


def _frame_path_for_result_ref(session: Path, result_ref: str) -> Path | None:
    if not result_ref:
        return None
    result_path = session / result_ref
    name = result_path.name
    if not name.endswith("-edge-result.json"):
        return None
    return result_path.with_name(name.replace("-edge-result.json", "-edge-frame.csv"))


def _latest_close_from_result_ref(
    session: Path,
    result_ref: str,
    *,
    trading_date: str,
) -> float | None:
    if not result_ref:
        return None
    result_path = session / result_ref
    if not result_path.exists():
        return None
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    preview = payload.get("decision_preview")
    if not isinstance(preview, list):
        return None
    for item in reversed(preview):
        if not isinstance(item, dict):
            continue
        if _date_text(item.get("date", "")) != trading_date:
            continue
        return _optional_float_value(item.get("target_close", ""))
    return None


def position_action(previous_position: float, next_position: float) -> str:
    if previous_position == 0 and next_position > 0:
        return "buy/open_long"
    if next_position == 0 and previous_position > 0:
        return "sell/close"
    if next_position > previous_position:
        return "increase"
    if next_position < previous_position:
        return "reduce"
    return "hold"


def _score_value(value: str) -> int:
    text = str(value or "").strip()
    head = text.split("/", 1)[0]
    return _int_value(head)


def _percent_to_ratio(value: str) -> float:
    return _float_value(value) / 100.0


def _float_value(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    return float(text)


def _optional_float_value(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    return float(text)


def _int_value(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    return int(float(text))


def _date_text(value: str) -> str:
    text = str(value or "").strip()
    if "T" in text:
        return text.split("T", 1)[0]
    return text.split(" ", 1)[0]
