"""Hosted strategy artifact selection helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
from typing import Any

from abel_invest.narrative_core.contracts.branch_spec import (
    branch_selected_graph_nodes,
    branch_selected_inputs,
    default_graph_node_id,
    load_branch_spec,
)
from abel_invest.narrative_core.contracts.paths import (
    branch_spec_path,
    data_manifest_path,
    dependencies_path,
    runtime_profile_path,
)
from abel_invest.narrative_core.io import _now, read_tsv_rows
from abel_invest.narrative_core.session_lifecycle import resolve_workspace_arg_path


STRATEGY_ARTIFACT_SCHEMA = "abel-invest.strategy-artifact/v1"
STRATEGY_ARTIFACT_ENTRYPOINT = "strategy/strategy.py"
STRATEGY_ARTIFACT_CLASS_NAME = "BranchEngine"
STRATEGY_ARTIFACT_PAPER_MODE = "paper_signal"
STRATEGY_ARTIFACT_WORKSPACE_KIND = "abel-invest"
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


def build_strategy_artifact_manifest(
    candidate: StrategyArtifactCandidate,
    *,
    trade_log_path: Path,
    created_at: str | None = None,
    abel_edge_version: str | None = None,
    abel_invest_version: str | None = None,
) -> dict[str, Any]:
    """Build the router upload manifest for one selected PASS strategy."""

    branch_spec = load_branch_spec(candidate.branch)
    runtime_profile = _load_json_object(runtime_profile_path(candidate.branch))
    metrics = candidate.edge_result.get("metrics")
    if not isinstance(metrics, dict):
        raise RuntimeError("selected strategy edge result is missing metrics")

    source_files = _required_artifact_source_files(
        candidate,
        trade_log_path=trade_log_path,
    )
    target_asset = _target_asset(candidate, branch_spec)
    selected_inputs = branch_selected_inputs(branch_spec)
    selected_graph_nodes = branch_selected_graph_nodes(branch_spec)
    if selected_inputs and not selected_graph_nodes:
        selected_graph_nodes = [
            default_graph_node_id(asset) for asset in selected_inputs
        ]

    effective_window = (
        candidate.edge_result.get("effective_window")
        if isinstance(candidate.edge_result.get("effective_window"), dict)
        else {}
    )
    start_at = _required_timestamptz(
        effective_window.get("start"),
        field_name="backtest.effective_window.start",
    )
    end_at = _required_timestamptz(
        effective_window.get("end"),
        field_name="backtest.effective_window.end",
    )

    return {
        "schema": STRATEGY_ARTIFACT_SCHEMA,
        "createdAt": created_at or _now(),
        "source": {
            "workspaceKind": STRATEGY_ARTIFACT_WORKSPACE_KIND,
            "sourceSessionId": candidate.source_session_id,
            "ticker": _clean(candidate.ticker).upper(),
            "branchId": candidate.branch_id,
            "roundId": candidate.round_id,
            "selectionMode": SELECTION_MODE_AUTO_BEST_PASS,
            "selectionScope": SELECTION_SCOPE_SESSION,
            "selectionMetricOrder": list(SELECTION_METRIC_ORDER),
            "selectionMetricValues": candidate.selection_metric_values,
            "selectionRank": candidate.selection_rank,
        },
        "runtime": {
            "profile": _clean(candidate.edge_result.get("profile"))
            or _clean(runtime_profile.get("profile"))
            or "unknown",
            "timeframe": _runtime_timeframe(branch_spec),
            "decisionEvent": _clean(runtime_profile.get("decision_event")) or "bar_close",
            "executionDelayBars": int(runtime_profile.get("execution_delay_bars") or 1),
            "returnBasis": _clean(runtime_profile.get("return_basis"))
            or "close_to_close",
            "implementationContract": _clean(
                candidate.edge_result.get("implementation_contract")
            )
            or "unknown",
            "abelEdgeVersion": abel_edge_version or _package_version("abel-edge"),
            "abelInvestVersion": abel_invest_version or _package_version("abel-invest"),
        },
        "strategy": {
            "entrypoint": STRATEGY_ARTIFACT_ENTRYPOINT,
            "className": STRATEGY_ARTIFACT_CLASS_NAME,
            "targetAsset": target_asset,
            "targetNode": _clean(branch_spec.get("target_node"))
            or default_graph_node_id(target_asset),
            "selectedInputs": selected_inputs,
            "selectedGraphNodes": selected_graph_nodes,
            "paperMode": STRATEGY_ARTIFACT_PAPER_MODE,
        },
        "files": [
            _artifact_file_entry(artifact_path=artifact_path, source_path=source_path)
            for artifact_path, source_path in source_files
        ],
        "backtest": {
            "verdict": _clean(candidate.edge_result.get("verdict")).upper(),
            "startAt": start_at,
            "endAt": end_at,
            "metrics": {
                "sharpe": _required_float(
                    metrics.get("sharpe"),
                    field_name="metrics.sharpe",
                ),
                "loAdjusted": _required_float(
                    metrics.get("lo_adjusted", metrics.get("lo_adj")),
                    field_name="metrics.lo_adjusted",
                ),
                "maxDrawdown": _required_float(
                    metrics.get("max_dd", metrics.get("max_drawdown")),
                    field_name="metrics.max_dd",
                ),
                "totalReturn": _required_float(
                    metrics.get("total_return"),
                    field_name="metrics.total_return",
                ),
            },
        },
    }


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


def _required_artifact_source_files(
    candidate: StrategyArtifactCandidate,
    *,
    trade_log_path: Path,
) -> list[tuple[str, Path]]:
    files = [
        (STRATEGY_ARTIFACT_ENTRYPOINT, candidate.strategy_source_path),
        ("edge/edge-result.json", candidate.edge_result_path),
        ("edge/trade-log.csv", trade_log_path),
    ]
    if candidate.edge_report_path is not None:
        files.append(("edge/edge-validation.md", candidate.edge_report_path))
    files.extend(
        [
            ("runtime/strategy.yaml", branch_spec_path(candidate.branch)),
            ("runtime/dependencies.json", dependencies_path(candidate.branch)),
            ("runtime/data_manifest.json", data_manifest_path(candidate.branch)),
        ]
    )

    for artifact_path, source_path in files:
        if not source_path.is_file():
            raise RuntimeError(
                f"strategy artifact source file is missing for {artifact_path}: {source_path}"
            )
    return files


def _artifact_file_entry(*, artifact_path: str, source_path: Path) -> dict[str, Any]:
    return {
        "path": artifact_path,
        "sha256": _sha256_file(source_path),
        "bytes": source_path.stat().st_size,
    }


def _target_asset(candidate: StrategyArtifactCandidate, branch_spec: dict[str, Any]) -> str:
    return _clean(
        branch_spec.get("target") or branch_spec.get("target_asset") or candidate.ticker
    ).upper()


def _runtime_timeframe(branch_spec: dict[str, Any]) -> str:
    data_requirements = branch_spec.get("data_requirements")
    if isinstance(data_requirements, dict):
        timeframe = _clean(data_requirements.get("timeframe"))
        if timeframe:
            return timeframe
    return "1d"


def _required_timestamptz(value: Any, *, field_name: str) -> str:
    normalized = _clean(value)
    if not normalized:
        raise RuntimeError(f"{field_name} is required")
    return _as_utc_iso(normalized)


def _as_utc_iso(value: str) -> str:
    normalized = value.strip()
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        return f"{normalized}T00:00:00Z"
    parseable = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError:
        return normalized
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_float(value: Any, *, field_name: str) -> float:
    parsed = _to_float(value)
    if parsed is None:
        raise RuntimeError(f"{field_name} is required")
    return parsed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "unknown"


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
