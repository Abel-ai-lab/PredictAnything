"""Hosted strategy artifact selection helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any

from abel_invest.narrative_core.io import read_tsv_rows
from abel_invest.narrative_core.session_lifecycle import resolve_workspace_arg_path


SELECTION_MODE_AUTO_BEST_PASS = "auto_best_pass_by_metric_order"
SELECTION_SCOPE_SESSION = "session"
SELECTION_METRIC_ORDER = ("sharpe", "lo_adjusted", "max_dd")


@dataclass(frozen=True)
class StrategyArtifactCandidate:
    session: Path
    branch: Path
    strategy_source_path: Path
    edge_result_path: Path
    edge_report_path: Path | None
    edge_handoff_path: Path | None
    source_session_id: str
    ticker: str
    branch_id: str
    round_id: str
    decision: str
    mode: str
    description: str
    score: str
    sharpe: float
    lo_adjusted: float
    max_dd: float
    row: dict[str, str]
    edge_result: dict[str, Any]
    selection_rank: int

    @property
    def selection_metric_values(self) -> dict[str, float]:
        return {
            "sharpe": self.sharpe,
            "lo_adjusted": self.lo_adjusted,
            "max_dd": self.max_dd,
        }


@dataclass(frozen=True)
class StrategySelectionResult:
    selected: StrategyArtifactCandidate | None
    skip_reason: str
    pass_round_count: int
    eligible_count: int

    @property
    def selected_branch_id(self) -> str | None:
        return self.selected.branch_id if self.selected is not None else None

    @property
    def selected_round_id(self) -> str | None:
        return self.selected.round_id if self.selected is not None else None


def select_best_pass_strategy(session: Path) -> StrategySelectionResult:
    """Select the best hostable PASS strategy in one Abel Invest session."""

    session = resolve_workspace_arg_path(session).resolve()
    rows = _iter_session_result_rows(session)
    pass_rows = [
        item for item in rows if _clean(item[1].get("verdict")).upper() == "PASS"
    ]
    if not pass_rows:
        return StrategySelectionResult(
            selected=None,
            skip_reason="no_pass_strategy",
            pass_round_count=0,
            eligible_count=0,
        )

    candidates: list[StrategyArtifactCandidate] = []
    for branch, row in pass_rows:
        candidate = _candidate_from_row(session=session, branch=branch, row=row)
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        return StrategySelectionResult(
            selected=None,
            skip_reason="no_hostable_pass_strategy",
            pass_round_count=len(pass_rows),
            eligible_count=0,
        )

    ranked = sorted(
        candidates,
        key=lambda item: (item.sharpe, item.lo_adjusted, item.max_dd),
        reverse=True,
    )
    selected = _with_rank(ranked[0], selection_rank=1)
    return StrategySelectionResult(
        selected=selected,
        skip_reason="",
        pass_round_count=len(pass_rows),
        eligible_count=len(candidates),
    )


def _iter_session_result_rows(session: Path) -> list[tuple[Path, dict[str, str]]]:
    branch_root = session / "branches"
    if not branch_root.exists():
        return []

    rows: list[tuple[Path, dict[str, str]]] = []
    for branch in sorted(path for path in branch_root.iterdir() if path.is_dir()):
        for row in read_tsv_rows(branch / "results.tsv"):
            rows.append((branch, row))
    return rows


def _candidate_from_row(
    *,
    session: Path,
    branch: Path,
    row: dict[str, str],
) -> StrategyArtifactCandidate | None:
    result_path = _resolve_session_relative_path(session, row.get("result_path"))
    if result_path is None or not result_path.is_file():
        return None

    strategy_source_path = branch / "engine.py"
    if not strategy_source_path.is_file():
        return None

    edge_result = _load_json_object(result_path)
    if not edge_result:
        return None
    if _clean(edge_result.get("verdict")).upper() != "PASS":
        return None

    metrics = edge_result.get("metrics") if isinstance(edge_result.get("metrics"), dict) else {}
    sharpe = _metric(row, metrics, row_key="sharpe", result_key="sharpe")
    lo_adjusted = _metric(row, metrics, row_key="lo_adj", result_key="lo_adjusted")
    max_dd = _metric(row, metrics, row_key="max_dd", result_key="max_dd")
    if sharpe is None or lo_adjusted is None or max_dd is None:
        return None

    report_path = _existing_optional_path(session, row.get("report_path"))
    handoff_path = _existing_optional_path(session, row.get("handoff_path"))
    return StrategyArtifactCandidate(
        session=session,
        branch=branch,
        strategy_source_path=strategy_source_path,
        edge_result_path=result_path,
        edge_report_path=report_path,
        edge_handoff_path=handoff_path,
        source_session_id=_clean(row.get("exp_id")) or session.name,
        ticker=_clean(row.get("ticker")) or session.parent.name.upper(),
        branch_id=_clean(row.get("branch_id")) or branch.name,
        round_id=_clean(row.get("round_id")),
        decision=_clean(row.get("decision")),
        mode=_clean(row.get("mode")),
        description=_clean(row.get("description")),
        score=_clean(row.get("score")),
        sharpe=sharpe,
        lo_adjusted=lo_adjusted,
        max_dd=max_dd,
        row=dict(row),
        edge_result=edge_result,
        selection_rank=0,
    )


def _with_rank(
    candidate: StrategyArtifactCandidate,
    *,
    selection_rank: int,
) -> StrategyArtifactCandidate:
    return replace(candidate, selection_rank=selection_rank)


def _resolve_session_relative_path(session: Path, value: str | None) -> Path | None:
    raw = _clean(value)
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return None
    resolved = (session / path).resolve()
    try:
        resolved.relative_to(session)
    except ValueError:
        return None
    return resolved


def _existing_optional_path(session: Path, value: str | None) -> Path | None:
    path = _resolve_session_relative_path(session, value)
    if path is None or not path.is_file():
        return None
    return path


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _metric(
    row: dict[str, str],
    metrics: dict[str, Any],
    *,
    row_key: str,
    result_key: str,
) -> float | None:
    row_value = _to_float(row.get(row_key))
    if row_value is not None:
        return row_value
    return _to_float(metrics.get(result_key))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str:
    return str(value or "").strip()
