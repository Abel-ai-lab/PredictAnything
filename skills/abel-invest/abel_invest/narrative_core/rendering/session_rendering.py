"""Session rendering, status, and integrity checks."""

from __future__ import annotations

from pathlib import Path

from abel_invest.narrative_core.contracts.branch_spec import has_explicit_hypothesis
from abel_invest.narrative_core.contracts.constants import (
    AGENT_CONTEXT_FILENAME,
    EVIDENCE_LEDGER_FILENAME,
    EXPLORATION_PATH_FILENAME,
    FRONTIER_JSON_FILENAME,
    FRONTIER_MARKDOWN_FILENAME,
)
from abel_invest.narrative_core.runtime.context import validate_edge_handoff
from abel_invest.narrative_core.evidence.evidence import load_json_object, write_evidence_ledger
from abel_invest.narrative_core.evidence.frontier import build_frontier, render_frontier_markdown
from abel_invest.narrative_core.io import write_json_file
from abel_invest.narrative_core.evidence.exploration_path import (
    build_exploration_path_status,
    ensure_exploration_path,
)
from abel_invest.narrative_core.readiness import (
    build_readiness_warning,
    format_data_readiness_summary,
    readiness_coverage_hint_lines,
)
from abel_invest.narrative_core.rendering.renderers import (
    build_branch_readme,
    build_session_readme,
    build_thesis,
    render_agent_context,
)
from abel_invest.narrative_core.state import (
    current_branch_hypothesis,
    latest_debug_snapshot,
    load_branches,
    load_discovery,
    load_readiness,
    read_round_note,
)


def render_session(session: Path) -> None:
    ensure_exploration_path(session)
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    branches = load_branches(session)
    ledger = write_evidence_ledger(session, discovery, branches)
    frontier = write_frontier(session, ledger)
    render_agent_context(session=session, ledger=ledger, frontier=frontier)
    for branch in branches:
        render_branch(branch, discovery, readiness, session.name)
    session_readme = build_session_readme(session, discovery, readiness, branches)
    (session / "README.md").write_text(session_readme, encoding="utf-8")


def render_branch(
    branch: dict,
    discovery: dict,
    readiness: dict,
    exp_id: str,
) -> None:
    branch_dir = branch["branch_dir"]
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    latest_note = (
        read_round_note(branch_dir, latest.get("round_id", "")) if latest else {}
    )

    (branch_dir / "README.md").write_text(
        build_branch_readme(branch, latest_note, exp_id), encoding="utf-8"
    )
    (branch_dir / "thesis.md").write_text(
        build_thesis(branch, discovery, readiness), encoding="utf-8"
    )


def print_status(session: Path) -> None:
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    branches = load_branches(session)
    ledger = load_json_object(session / EVIDENCE_LEDGER_FILENAME)
    frontier = load_json_object(session / FRONTIER_JSON_FILENAME)
    path_status = build_exploration_path_status(session, ledger=ledger, frontier=frontier)
    print(
        f"Session: {session.name} ({discovery.get('ticker', session.parent.name.upper())})"
    )
    print(f"Branches: {len(branches)}")
    print(f"Total rounds: {sum(len(branch['rows']) for branch in branches)}")
    print(
        "Exploration path: "
        f"{path_status.get('resolved_evidence_reference_count', 0)} evidence-linked refs"
    )
    readiness_summary = format_data_readiness_summary(readiness)
    if readiness_summary:
        print(f"Discovery readiness: {readiness_summary}")
        warning = build_readiness_warning(readiness)
        if warning:
            print(f"Readiness warning: {warning}")
        for line in readiness_coverage_hint_lines(readiness):
            print(f"Coverage hint: {line}")
    if frontier:
        labels = frontier.get("evidence_label_counts") or {}
        candidate_universe = frontier.get("candidate_universe") or {}
        path_coverage = frontier.get("path_coverage") or {}
        print(
            "Evidence frontier: "
            f"rows={frontier.get('row_count', 0)} "
            f"candidate_causal={labels.get('candidate_causal_evidence', 0)} "
            f"candidate_strategy={labels.get('candidate_strategy_evidence', 0)} "
            f"target_control={labels.get('target_control_evidence', 0)} "
            f"workflow_blockers={frontier.get('workflow_blockers', 0)} "
            f"graph_candidates_available={str(candidate_universe.get('graph_candidates_available', False)).lower()} "
            f"path_coverage_complete={str(path_coverage.get('path_coverage_complete', False)).lower()}"
        )
    for branch in branches:
        latest = branch["rows"][-1] if branch["rows"] else {}
        latest_note = (
            read_round_note(branch["branch_dir"], latest.get("round_id", "")) if latest else {}
        )
        if not latest_note:
            latest_note = latest_debug_snapshot(branch["branch_dir"])
        branch_hypothesis = current_branch_hypothesis(branch["branch_dir"], branch["rows"])
        keep_count = sum(1 for row in branch["rows"] if row.get("decision") == "keep")
        discard_count = sum(
            1 for row in branch["rows"] if row.get("decision") == "discard"
        )
        print(
            f"  {branch['branch_id']:20s} rounds={len(branch['rows']):2d} keep={keep_count:2d} "
            f"discard={discard_count:2d} latest={latest.get('round_id', 'none')} {latest.get('decision', 'pending')} "
            f"{latest.get('verdict', 'n/a')} {latest.get('score', '?/?')} "
            f"{latest_note.get('failure_signature', 'unknown')} "
            f"active={latest_note.get('signal_activity', 'n/a')} "
            f"candidate_note={'yes' if has_explicit_hypothesis(branch_hypothesis) else 'no'}"
        )


def check_session(session: Path, *, strict: bool) -> int:
    failures: list[str] = []
    if not (session / "events.tsv").exists():
        failures.append("Missing events.tsv")
    if not (session / "README.md").exists():
        failures.append("Missing session README.md")
    for required in (
        EVIDENCE_LEDGER_FILENAME,
        FRONTIER_JSON_FILENAME,
        FRONTIER_MARKDOWN_FILENAME,
        AGENT_CONTEXT_FILENAME,
        EXPLORATION_PATH_FILENAME,
    ):
        if not (session / required).exists():
            failures.append(f"Missing {required}")

    branches = load_branches(session)
    if not branches:
        failures.append("No branches found")

    for branch in branches:
        branch_dir = branch["branch_dir"]
        rows = branch["rows"]
        for required in (
            "README.md",
            "thesis.md",
            "engine.py",
            "results.tsv",
        ):
            if not (branch_dir / required).exists():
                failures.append(f"{branch_dir.name}: missing {required}")
        for row in rows:
            round_id = row.get("round_id", "")
            if not round_id:
                failures.append(f"{branch_dir.name}: row missing round_id")
                continue
            round_note_path = branch_dir / "rounds" / f"{round_id}.md"
            if not round_note_path.exists():
                failures.append(f"{branch_dir.name}: missing round note {round_id}.md")
                note = {}
            else:
                note = read_round_note(branch_dir, round_id)
            if not (session / row.get("result_path", "")).exists():
                failures.append(
                    f"{branch_dir.name}: missing edge result {row.get('result_path', '')}"
                )
            if not (session / row.get("report_path", "")).exists():
                failures.append(
                    f"{branch_dir.name}: missing edge report {row.get('report_path', '')}"
                )
            if not (session / row.get("handoff_path", "")).exists():
                failures.append(
                    f"{branch_dir.name}: missing edge handoff {row.get('handoff_path', '')}"
                )
            context_rel = note.get("context_path", "")
            expected_context = branch_dir / "outputs" / f"{round_id}-alpha-context.json"
            if context_rel:
                if not (session / context_rel).exists():
                    failures.append(
                        f"{branch_dir.name}: missing alpha context {context_rel}"
                    )
            elif strict and expected_context.exists():
                failures.append(
                    f"{branch_dir.name}: round note missing context_path for {round_id}"
                )
            if strict and row.get("decision") != "blocked":
                validate_edge_handoff(session, branch_dir.name, row, failures)
        if strict:
            for text_path in (
                branch_dir / "README.md",
                branch_dir / "thesis.md",
                session / AGENT_CONTEXT_FILENAME,
            ):
                if not text_path.exists():
                    continue
                text = text_path.read_text(encoding="utf-8")
                if "Fill in" in text or "{{" in text or "}}" in text:
                    failures.append(
                        f"{branch_dir.name}: unresolved placeholder in {text_path.name}"
                    )

    if strict:
        validate_exploration_protocol(session, failures)

    if failures:
        print("Narrative check failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"Narrative check passed for {session}")
    return 0


def validate_exploration_protocol(session: Path, failures: list[str]) -> None:
    frontier = load_json_object(session / FRONTIER_JSON_FILENAME)
    path_coverage = (
        frontier.get("path_coverage")
        if isinstance(frontier.get("path_coverage"), dict)
        else {}
    )
    missing_rounds = list(path_coverage.get("missing_path_rounds") or [])
    if missing_rounds:
        failures.append(
            "exploration path coverage incomplete: "
            f"missing_path_rounds={', '.join(str(item) for item in missing_rounds)}"
        )


def path_coverage_missing_rounds(session: Path) -> list[str]:
    frontier = load_json_object(session / FRONTIER_JSON_FILENAME)
    path_coverage = (
        frontier.get("path_coverage")
        if isinstance(frontier.get("path_coverage"), dict)
        else {}
    )
    return [str(item) for item in path_coverage.get("missing_path_rounds") or []]


def path_coverage_warning_lines(session: Path) -> list[str]:
    missing_rounds = path_coverage_missing_rounds(session)
    if not missing_rounds:
        return []
    return [
        "path_coverage_complete=false "
        f"missing_path_rounds={', '.join(missing_rounds)} "
        f"required_action=update_{EXPLORATION_PATH_FILENAME}_with_path_why_and_edge_feedback"
    ]


def write_frontier(session: Path, ledger: dict) -> dict:
    path_status = build_exploration_path_status(session, ledger=ledger, frontier={})
    frontier = build_frontier(
        ledger,
        exploration_path_status=path_status,
    )
    write_json_file(session / FRONTIER_JSON_FILENAME, frontier)
    (session / FRONTIER_MARKDOWN_FILENAME).write_text(
        render_frontier_markdown(frontier),
        encoding="utf-8",
    )
    return frontier


def render_section(title: str, lines: list[str]) -> None:
    if not lines:
        return
    print(f"{title}:")
    for line in lines:
        print(f"  {line}")
