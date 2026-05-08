"""Session exploration path artifact helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from abel_invest.narrative_core.contracts.constants import EXPLORATION_PATH_FILENAME


def ensure_exploration_path(session: Path) -> Path:
    path = session / EXPLORATION_PATH_FILENAME
    if not path.exists():
        path.write_text(build_exploration_path_template(session), encoding="utf-8")
    return path


def build_exploration_path_template(session: Path) -> str:
    return f"""# Exploration Path

concise strategy path for session `{session.name}`

## How To Use

- Before choosing the next Edge run, read `exploration_path.md`, the latest `edge-result.json`, and the latest `edge-validation.md`.
- Use the previous strategy choice, choice reason, and Edge feedback to decide the next branch, mechanism, input set, or control.
- After Edge feedback returns, record the result here before the next strategy choice.
- Keep entries short: strategy choice, choice reason, Edge feedback, and next implication.

## Entries

"""


def build_exploration_path_status(session: Path) -> dict[str, object]:
    path = session / EXPLORATION_PATH_FILENAME
    if not path.exists():
        return {
            "path": EXPLORATION_PATH_FILENAME,
            "exists": False,
            "entry_count": 0,
            "recent_excerpt": "",
        }
    lines = path.read_text(encoding="utf-8").splitlines()
    entry_count = sum(
        1
        for line in lines
        if line.startswith("## ") and line not in {"## How To Use", "## Entries"}
    )
    entry_start = 0
    for index, line in enumerate(lines):
        if line.strip() == "## Entries":
            entry_start = index + 1
            break
    user_lines = [line.rstrip() for line in lines[entry_start:] if line.strip()]
    return {
        "path": EXPLORATION_PATH_FILENAME,
        "exists": True,
        "entry_count": entry_count,
        "recent_excerpt": "\n".join(user_lines[-10:]),
    }


def append_exploration_path_round(
    *,
    session: Path,
    branch: Path,
    round_id: str,
    mode: str,
    decision: str,
    description: str,
    result: dict[str, Any],
    result_path: Path,
    report_path: Path,
    hypothesis: str = "",
    change_summary: str = "",
    next_step: str = "",
    changed_dimensions: list[str] | None = None,
) -> Path:
    path = ensure_exploration_path(session)
    entry = render_exploration_path_round(
        session=session,
        branch=branch,
        round_id=round_id,
        mode=mode,
        decision=decision,
        description=description,
        result=result,
        result_path=result_path,
        report_path=report_path,
        hypothesis=hypothesis,
        change_summary=change_summary,
        next_step=next_step,
        changed_dimensions=changed_dimensions or [],
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    return path


def render_exploration_path_round(
    *,
    session: Path,
    branch: Path,
    round_id: str,
    mode: str,
    decision: str,
    description: str,
    result: dict[str, Any],
    result_path: Path,
    report_path: Path,
    hypothesis: str,
    change_summary: str,
    next_step: str,
    changed_dimensions: list[str],
) -> str:
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    feedback = format_edge_feedback(result)
    reason_parts = [
        compact_text(hypothesis),
        compact_text(change_summary),
        format_changed_dimensions(changed_dimensions),
    ]
    reason = "; ".join(part for part in reason_parts if part) or "not recorded"
    next_implication = compact_text(next_step) or feedback_next_implication(result)
    result_rel = safe_relative_path(result_path, session)
    report_rel = safe_relative_path(report_path, session)
    return f"""
## {branch.name} {round_id}

- ledger: `ledger:{branch.name}:{round_id}`
- mode: `{compact_text(mode) or 'unknown'}`; decision: `{compact_text(decision) or 'unknown'}`
- strategy choice: {compact_text(description) or branch.name}
- choice reason: {reason}
- Edge feedback: {feedback}
- key metrics: sharpe `{format_metric(metrics.get('sharpe'))}`, lo `{format_metric(metrics.get('lo_adjusted'))}`, ic `{format_metric(metrics.get('position_ic'))}`, omega `{format_metric(metrics.get('omega'))}`, max_dd `{format_metric(metrics.get('max_dd'))}`
- artifacts: `{result_rel}`, `{report_rel}`
- next implication: {next_implication}
"""


def format_edge_feedback(result: dict[str, Any]) -> str:
    verdict = compact_text(result.get("verdict")) or "unknown"
    score = compact_text(result.get("score")) or "?/?"
    failures = edge_failure_messages(result)
    failure_text = "; ".join(failures[:3]) if failures else "no blocking failures"
    return f"`{verdict}` score `{score}`; {failure_text}"


def edge_failure_messages(result: dict[str, Any]) -> list[str]:
    selected: list[str] = []
    for item in result.get("failures") or []:
        add_unique(selected, compact_text(item))
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    for item in diagnostics.get("metric_failures") or []:
        if isinstance(item, dict):
            add_unique(selected, compact_text(item.get("message")))
    return selected


def feedback_next_implication(result: dict[str, Any]) -> str:
    verdict = str(result.get("verdict") or "").upper()
    if verdict == "PASS":
        return "compare this PASS against prior path entries before refining or promoting."
    failures = edge_failure_messages(result)
    if failures:
        return "choose the next Edge run to address: " + "; ".join(failures[:2])
    return "review the latest Edge artifacts before selecting the next branch or mechanism."


def format_changed_dimensions(values: list[str]) -> str:
    cleaned = [compact_text(item) for item in values]
    cleaned = [item for item in cleaned if item]
    return "changed=" + ", ".join(cleaned) if cleaned else ""


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def format_metric(value: Any) -> str:
    try:
        return f"{float(value):.4g}"
    except (TypeError, ValueError):
        return "n/a"


def safe_relative_path(path: Path, parent: Path) -> str:
    try:
        return str(path.relative_to(parent))
    except ValueError:
        return str(path)


def add_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
