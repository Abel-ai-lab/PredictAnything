"""Alpha-search journal parsing and coverage helpers."""

from __future__ import annotations

from pathlib import Path

from abel_invest.narrative_core.contracts.branch_spec import ordered_unique_strings
from abel_invest.narrative_core.contracts.constants import (
    EVIDENCE_LEDGER_FILENAME,
    FRONTIER_MARKDOWN_FILENAME,
    JOURNAL_GENERATED_HEADER_END,
    JOURNAL_REFERENCE_RE,
    RESEARCH_JOURNAL_FILENAME,
)


def ensure_research_journal(session: Path) -> Path:
    path = session / RESEARCH_JOURNAL_FILENAME
    if not path.exists():
        path.write_text(build_research_journal_template(session), encoding="utf-8")
    return path


def build_research_journal_template(session: Path) -> str:
    return f"""# Alpha Search Journal

agent-owned search notes for session `{session.name}`

## Boundary

- `evidence_ledger.json` and `frontier.md` are the system-owned evidence facts.
- This journal is for the agent's candidate ideas, observations, pivots, and stop/continue reasoning.
- Every recorded round requires an agent-written note below with its ledger evidence reference.
- Capture what changed, what happened, what was learned, and what that implies for the next exploration step.
- Before a new candidate branch, record the branch basis and whether any performance-like scout influenced the choice.
- Treat Abel Ask or narrative context as candidate-generation context, not validation evidence; note when it is off-target or weak.
- The generated header above this marker never counts as journal coverage.

{JOURNAL_GENERATED_HEADER_END}

## Notes

"""


def build_research_journal_status(
    session: Path,
    *,
    ledger: dict,
    frontier: dict,
) -> dict[str, object]:
    path = session / RESEARCH_JOURNAL_FILENAME
    if not path.exists():
        return {
            "path": RESEARCH_JOURNAL_FILENAME,
            "exists": False,
            "line_count": 0,
            "evidence_reference_count": 0,
            "resolved_evidence_reference_count": 0,
            "resolved_ledger_round_refs": [],
            "has_evidence_linked_update": False,
            "last_evidence_linked_update_line": 0,
            "recent_excerpt": "",
        }
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    note_lines = journal_note_line_items(lines)
    note_text = "\n".join(line for _, line in note_lines)
    refs = extract_journal_evidence_refs(note_text)
    resolved_refs = [
        ref
        for ref in refs
        if resolve_journal_reference(ref, session=session, ledger=ledger, frontier=frontier)
    ]
    resolved_ledger_round_refs = [
        ledger_round_key_from_ref(ref)
        for ref in resolved_refs
        if ledger_round_key_from_ref(ref)
    ]
    last_line = 0
    for index, line in note_lines:
        line_refs = extract_journal_evidence_refs(line)
        if any(
            ledger_round_key_from_ref(ref)
            and resolve_journal_reference(ref, session=session, ledger=ledger, frontier=frontier)
            for ref in line_refs
        ):
            last_line = index
    return {
        "path": RESEARCH_JOURNAL_FILENAME,
        "exists": True,
        "line_count": len(lines),
        "evidence_reference_count": len(refs),
        "resolved_evidence_reference_count": len(resolved_refs),
        "resolved_ledger_round_refs": ordered_unique_strings(resolved_ledger_round_refs),
        "has_evidence_linked_update": bool(resolved_ledger_round_refs),
        "last_evidence_linked_update_line": last_line,
        "recent_excerpt": recent_journal_excerpt(lines),
    }


def compact_research_journal_status(status: dict[str, object] | None) -> dict[str, object]:
    status = status or {}
    return {
        "path": status.get("path", RESEARCH_JOURNAL_FILENAME),
        "exists": bool(status.get("exists")),
        "evidence_reference_count": int(status.get("evidence_reference_count") or 0),
        "resolved_evidence_reference_count": int(
            status.get("resolved_evidence_reference_count") or 0
        ),
        "resolved_ledger_round_refs": list(status.get("resolved_ledger_round_refs") or []),
        "has_evidence_linked_update": bool(status.get("has_evidence_linked_update")),
        "last_evidence_linked_update_line": int(
            status.get("last_evidence_linked_update_line") or 0
        ),
    }


def extract_journal_evidence_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in JOURNAL_REFERENCE_RE.finditer(str(text or "")):
        value = match.group(1).strip().rstrip(".,;:]")
        if value and value not in refs:
            refs.append(value)
    return refs


def resolve_journal_reference(
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
    if ref.startswith("branches/"):
        return resolve_evidence_reference(f"artifact:{ref}", session=session, ledger=ledger, frontier=frontier)
    return resolve_evidence_reference(ref, session=session, ledger=ledger, frontier=frontier)


def ledger_round_key_from_ref(ref: str) -> str:
    text = str(ref or "").strip()
    if not text.startswith("ledger:"):
        return ""
    parts = text.split(":")
    if len(parts) < 3:
        return ""
    return journal_round_key(parts[1], parts[2])


def recent_journal_excerpt(lines: list[str]) -> str:
    user_lines = [line.rstrip() for _, line in journal_note_line_items(lines) if line.strip()]
    return "\n".join(user_lines[-8:])


def journal_note_line_items(lines: list[str]) -> list[tuple[int, str]]:
    note_start = 0
    for index, line in enumerate(lines):
        if line.strip() == JOURNAL_GENERATED_HEADER_END:
            note_start = index + 1
            break
    else:
        note_start = 0
    if note_start == 0:
        # This fallback keeps local tests and hand-authored scratch files readable;
        # new generated journals use the explicit header marker above.
        for index, line in enumerate(lines):
            if line.strip().lower() == "## notes":
                note_start = index + 1
                break
    for index, line in enumerate(lines[note_start:], start=note_start):
        if line.strip().lower() == "## notes":
            note_start = index + 1
            break
    return [(index + 1, line) for index, line in enumerate(lines[note_start:], start=note_start)]


def resolve_evidence_reference(
    value: str,
    *,
    session: Path,
    ledger: dict,
    frontier: dict,
) -> bool:
    if value.startswith("frontier:"):
        field = value.split(":", 1)[1].strip()
        return bool(field) and field in frontier
    if value.startswith("ledger:"):
        parts = value.split(":")
        if len(parts) < 3:
            return False
        branch_id = parts[1].strip()
        round_id = parts[2].strip()
        return any(
            row.get("branch_id") == branch_id and row.get("round_id") == round_id
            for row in (ledger.get("rows") or [])
            if isinstance(row, dict)
        )
    if value.startswith("artifact:"):
        value = value.split(":", 1)[1].strip()
    if not value:
        return False
    candidate = (session / value).resolve()
    try:
        candidate.relative_to(session.resolve())
    except ValueError:
        return False
    return candidate.exists()


def build_journal_coverage(rows: list[dict[str, object]], journal_status: dict[str, object]) -> dict[str, object]:
    recorded_rounds = [
        journal_round_key(row.get("branch_id"), row.get("round_id") or row.get("run_id"))
        for row in rows
        if row.get("run_type") == "round"
    ]
    recorded_rounds = [item for item in ordered_unique_strings(recorded_rounds) if item]
    journaled_rounds = sorted(
        set(recorded_rounds).intersection(
            set(str(item) for item in journal_status.get("resolved_ledger_round_refs") or [])
        )
    )
    missing_rounds = sorted(set(recorded_rounds).difference(journaled_rounds))
    return {
        "recorded_round_count": len(recorded_rounds),
        "journaled_round_count": len(journaled_rounds),
        "journal_coverage_complete": not missing_rounds,
        "missing_journal_rounds": missing_rounds,
    }


def journal_round_key(branch_id: object, round_id: object) -> str:
    branch = str(branch_id or "").strip()
    round_text = str(round_id or "").strip()
    if not branch or not round_text:
        return ""
    return f"{branch}:{round_text}"
