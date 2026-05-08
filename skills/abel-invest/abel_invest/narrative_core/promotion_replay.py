"""Promotion replay checks for behavior-equivalence gate evidence."""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable

from abel_invest.narrative_core.promotion import (
    PROMOTION_MODE_ZERO_CHANGE,
)


def verify_promotion_replay(
    *,
    candidate: Any,
    promotion_mode: str,
    promoted_source_path: Path,
    replacements: list[dict[str, str]],
    state_entries: tuple[Any, ...],
    destination: Path,
    python_bin: str,
    runner: Callable[..., Any],
    run_edge_metric_input_export: Callable[..., dict[str, Any]],
    sha256_file: Callable[[Path], str],
    clean: Callable[[Any], str],
) -> dict[str, Any]:
    if promotion_mode == PROMOTION_MODE_ZERO_CHANGE:
        return {
            "behavior_equivalence": {
                "status": "passed",
                "method": "source_hash_identity",
                "replacements": replacements,
            },
            "paper_dry_run": {
                "status": "passed",
                "method": "source_round_edge_result",
                "sourceVerdict": clean(candidate.edge_result.get("verdict")),
                "sourceRoundId": candidate.round_id,
            },
        }

    if candidate.edge_metric_input_path is None or not candidate.edge_metric_input_path.is_file():
        return _failed("source metric input is missing", replacements=replacements)

    replay_root = destination / "promotion-replay"
    replay_root.mkdir(parents=True, exist_ok=True)
    replay_result_path = replay_root / "edge-result.json"
    replay_report_path = replay_root / "edge-validation.md"
    replay_metric_input_path = replay_root / "metric-input.csv"
    with tempfile.TemporaryDirectory(prefix="promoted-branch-", dir=replay_root) as temp_dir:
        replay_branch = Path(temp_dir) / candidate.branch.name
        shutil.copytree(
            candidate.branch,
            replay_branch,
            ignore=shutil.ignore_patterns(".abel-runtime", "promotions", "__pycache__"),
        )
        shutil.copyfile(promoted_source_path, replay_branch / "engine.py")
        _bootstrap_replay_state(replay_branch, state_entries)
        replay_candidate = replace(candidate, branch=replay_branch)
        replay_result = run_edge_metric_input_export(
            python_bin=python_bin,
            candidate=replay_candidate,
            result_path=replay_result_path,
            report_path=replay_report_path,
            metric_input_path=replay_metric_input_path,
            runner=runner,
        )

    comparison = _compare_metric_inputs(
        candidate.edge_metric_input_path,
        replay_metric_input_path,
        clean=clean,
    )
    status = "passed" if comparison["equivalent"] else "failed"
    method = "promoted_metric_input_replay"
    behavior_details = {
        "method": method,
        "status": status,
        "replacements": replacements,
        "sourceMetricInputSha256": sha256_file(candidate.edge_metric_input_path),
        "promotedMetricInputSha256": sha256_file(replay_metric_input_path)
        if replay_metric_input_path.is_file()
        else "",
        "sourceRowCount": comparison.get("sourceRowCount", 0),
        "promotedRowCount": comparison.get("promotedRowCount", 0),
        "maxAbsDiff": comparison.get("maxAbsDiff", 0.0),
        "mismatch": comparison.get("mismatch", ""),
    }
    return {
        "behavior_equivalence": behavior_details,
        "paper_dry_run": {
            "status": "passed" if clean(replay_result.get("verdict")).upper() == "PASS" else "failed",
            "method": method,
            "promotedVerdict": clean(replay_result.get("verdict")),
            "promotedMetricInputPath": str(replay_metric_input_path),
            "promotedRowCount": comparison.get("promotedRowCount", 0),
        },
    }


def _failed(reason: str, *, replacements: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "behavior_equivalence": {
            "status": "failed",
            "method": "promoted_metric_input_replay",
            "reason": reason,
            "replacements": replacements,
        },
        "paper_dry_run": {
            "status": "failed",
            "method": "promoted_metric_input_replay",
            "reason": reason,
        },
    }


def _bootstrap_replay_state(replay_branch: Path, state_entries: tuple[Any, ...]) -> None:
    state_root = replay_branch / ".abel-runtime" / "state"
    for entry in state_entries:
        if getattr(entry, "role", "") != "initial_state":
            continue
        relative = Path(getattr(entry, "path", ""))
        if not relative.as_posix():
            continue
        source = Path(getattr(entry, "source_path"))
        target = state_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _compare_metric_inputs(
    source_path: Path,
    promoted_path: Path,
    *,
    clean: Callable[[Any], str],
    tolerance: float = 1e-9,
) -> dict[str, Any]:
    source_rows = _read_csv_rows(source_path)
    promoted_rows = _read_csv_rows(promoted_path)
    result: dict[str, Any] = {
        "equivalent": False,
        "sourceRowCount": len(source_rows),
        "promotedRowCount": len(promoted_rows),
        "maxAbsDiff": 0.0,
        "mismatch": "",
    }
    if len(source_rows) != len(promoted_rows):
        result["mismatch"] = "row_count"
        return result
    numeric_columns = (
        "position",
        "next_position",
        "pnl",
        "asset_return",
        "gross_pnl",
        "turnover",
        "execution_cost",
    )
    identity_columns = ("date", "decision_time", "effective_time")
    max_abs_diff = 0.0
    for idx, (source_row, promoted_row) in enumerate(zip(source_rows, promoted_rows)):
        for column in identity_columns:
            if column in source_row or column in promoted_row:
                if clean(source_row.get(column)) != clean(promoted_row.get(column)):
                    result["mismatch"] = f"{column}@{idx}"
                    result["maxAbsDiff"] = max_abs_diff
                    return result
        for column in numeric_columns:
            if column not in source_row and column not in promoted_row:
                continue
            diff = abs(_csv_float(source_row.get(column), clean) - _csv_float(promoted_row.get(column), clean))
            max_abs_diff = max(max_abs_diff, diff)
            if diff > tolerance:
                result["mismatch"] = f"{column}@{idx}"
                result["maxAbsDiff"] = max_abs_diff
                return result
    result["equivalent"] = True
    result["maxAbsDiff"] = max_abs_diff
    return result


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _csv_float(value: Any, clean: Callable[[Any], str]) -> float:
    text = clean(value)
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
