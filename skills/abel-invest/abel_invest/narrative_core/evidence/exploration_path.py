"""Session exploration path artifact helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from abel_invest.narrative_core.contracts.branch_spec import ordered_unique_strings
from abel_invest.narrative_core.contracts.constants import (
    EVIDENCE_LEDGER_FILENAME,
    EXPLORATION_PATH_FILENAME,
    FRONTIER_MARKDOWN_FILENAME,
    JOURNAL_REFERENCE_RE,
)


def ensure_exploration_path(session: Path) -> Path:
    path = session / EXPLORATION_PATH_FILENAME
    if not path.exists():
        path.write_text(build_exploration_path_template(session), encoding="utf-8")
    return path


def build_exploration_path_template(session: Path) -> str:
    return f"""# Exploration Path

single human-facing exploration log for session `{session.name}`

## How To Use

- Before choosing the next Edge run, read `exploration_path.md`, the latest `edge-result.json`, and the latest `edge-validation.md`.
- Use the previous chosen path, compact reason, and Edge feedback to decide the next candidate, search axis, input set, or control.
- Every recorded round needs one concise entry below with its `ledger:<branch_id>:<round_id>` reference.
- Keep entries short: ledger ref, chosen path, compact reason, Edge feedback, key result, and artifacts.
- System-owned evidence facts stay in `{EVIDENCE_LEDGER_FILENAME}` and `{FRONTIER_MARKDOWN_FILENAME}`.

## Entries

"""


def build_exploration_path_status(
    session: Path,
    *,
    ledger: dict | None = None,
    frontier: dict | None = None,
) -> dict[str, object]:
    path = session / EXPLORATION_PATH_FILENAME
    if not path.exists():
        return {
            "path": EXPLORATION_PATH_FILENAME,
            "exists": False,
            "line_count": 0,
            "entry_count": 0,
            "evidence_reference_count": 0,
            "resolved_evidence_reference_count": 0,
            "resolved_ledger_round_refs": [],
            "has_round_entries": False,
            "recent_excerpt": "",
        }
    lines = path.read_text(encoding="utf-8").splitlines()
    entry_count = sum(
        1
        for line in lines
        if (line.startswith("### ") or line.startswith("## "))
        and line not in {"## How To Use", "## Entries"}
    )
    entry_start = 0
    for index, line in enumerate(lines):
        if line.strip() == "## Entries":
            entry_start = index + 1
            break
    user_lines = [line.rstrip() for line in lines[entry_start:] if line.strip()]
    entry_text = "\n".join(line for line in lines[entry_start:])
    refs = extract_exploration_path_refs(entry_text)
    resolved_refs = [
        ref
        for ref in refs
        if resolve_exploration_path_reference(
            ref,
            session=session,
            ledger=ledger or {},
            frontier=frontier or {},
        )
    ]
    resolved_ledger_round_refs = [
        ledger_round_key_from_ref(ref)
        for ref in resolved_refs
        if ledger_round_key_from_ref(ref)
    ]
    return {
        "path": EXPLORATION_PATH_FILENAME,
        "exists": True,
        "line_count": len(lines),
        "entry_count": entry_count,
        "evidence_reference_count": len(refs),
        "resolved_evidence_reference_count": len(resolved_refs),
        "resolved_ledger_round_refs": ordered_unique_strings(resolved_ledger_round_refs),
        "has_round_entries": bool(resolved_ledger_round_refs),
        "recent_excerpt": "\n".join(user_lines[-10:]),
    }


def compact_exploration_path_status(status: dict[str, object] | None) -> dict[str, object]:
    status = status or {}
    return {
        "path": status.get("path", EXPLORATION_PATH_FILENAME),
        "exists": bool(status.get("exists")),
        "entry_count": int(status.get("entry_count") or 0),
        "evidence_reference_count": int(status.get("evidence_reference_count") or 0),
        "resolved_evidence_reference_count": int(
            status.get("resolved_evidence_reference_count") or 0
        ),
        "resolved_ledger_round_refs": list(status.get("resolved_ledger_round_refs") or []),
        "has_round_entries": bool(status.get("has_round_entries")),
    }


def build_exploration_path_coverage(
    rows: list[dict[str, object]],
    path_status: dict[str, object],
) -> dict[str, object]:
    recorded_rounds = [
        exploration_round_key(row.get("branch_id"), row.get("round_id") or row.get("run_id"))
        for row in rows
        if row.get("run_type") == "round"
    ]
    recorded_rounds = [item for item in ordered_unique_strings(recorded_rounds) if item]
    covered_rounds = sorted(
        set(recorded_rounds).intersection(
            set(str(item) for item in path_status.get("resolved_ledger_round_refs") or [])
        )
    )
    missing_rounds = sorted(set(recorded_rounds).difference(covered_rounds))
    return {
        "recorded_round_count": len(recorded_rounds),
        "covered_round_count": len(covered_rounds),
        "path_coverage_complete": not missing_rounds,
        "missing_path_rounds": missing_rounds,
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
    result_rel = safe_relative_path(result_path, session)
    report_rel = safe_relative_path(report_path, session)
    return f"""
### {branch.name} {round_id}

- ledger: `ledger:{branch.name}:{round_id}`
- mode: `{compact_text(mode) or 'unknown'}`; decision: `{compact_text(decision) or 'unknown'}`
- path: {compact_text(description) or branch.name}
- compact reason: {reason}
- Edge feedback: {feedback}
- key result: Sharpe `{format_metric(metrics.get('sharpe'))}`, Lo `{format_metric(metrics.get('lo_adjusted'))}`, return `{format_percent_metric(metrics.get('total_return'))}`, max drawdown `{format_percent_metric(metrics.get('max_dd'), absolute=True)}`, PositionIC `{format_metric(metrics.get('position_ic'))}`
- artifacts: `{result_rel}`, `{report_rel}`
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
    return "review the latest Edge artifacts before selecting the next candidate or search axis."


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


def format_percent_metric(value: Any, *, absolute: bool = False) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if absolute:
        numeric = abs(numeric)
    return f"{numeric * 100:.1f}%"


def safe_relative_path(path: Path, parent: Path) -> str:
    try:
        return str(path.relative_to(parent)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def add_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def extract_exploration_path_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in JOURNAL_REFERENCE_RE.finditer(str(text or "")):
        value = match.group(1).strip().rstrip(".,;:]")
        if value and value not in refs:
            refs.append(value)
    return refs


def resolve_exploration_path_reference(
    value: str,
    *,
    session: Path,
    ledger: dict,
    frontier: dict,
) -> bool:
    ref = str(value or "").strip()
    if not ref:
        return False
    if ref == FRONTIER_MARKDOWN_FILENAME:
        return (session / FRONTIER_MARKDOWN_FILENAME).exists()
    if ref == EVIDENCE_LEDGER_FILENAME:
        return (session / EVIDENCE_LEDGER_FILENAME).exists()
    if ref.startswith("frontier:"):
        field = ref.split(":", 1)[1].strip()
        return bool(field) and field in frontier
    if ref.startswith("ledger:"):
        parts = ref.split(":")
        if len(parts) < 3:
            return False
        branch_id = parts[1].strip()
        round_id = parts[2].strip()
        return any(
            row.get("branch_id") == branch_id and row.get("round_id") == round_id
            for row in (ledger.get("rows") or [])
            if isinstance(row, dict)
        )
    if ref.startswith("artifact:"):
        ref = ref.split(":", 1)[1].strip()
    if ref.startswith("branches/") or ref.startswith("branches\\"):
        candidate = (session / ref).resolve()
        try:
            candidate.relative_to(session.resolve())
        except ValueError:
            return False
        return candidate.exists()
    return False


def ledger_round_key_from_ref(ref: str) -> str:
    text = str(ref or "").strip()
    if not text.startswith("ledger:"):
        return ""
    parts = text.split(":")
    if len(parts) < 3:
        return ""
    return exploration_round_key(parts[1], parts[2])


def exploration_round_key(branch_id: object, round_id: object) -> str:
    branch = str(branch_id or "").strip()
    round_text = str(round_id or "").strip()
    if not branch or not round_text:
        return ""
    return f"{branch}:{round_text}"
