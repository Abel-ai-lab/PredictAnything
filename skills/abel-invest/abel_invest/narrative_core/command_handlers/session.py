"""Session and branch setup command handlers."""

from __future__ import annotations

import argparse
import os

from abel_invest.narrative_core.contracts.branch_spec import has_explicit_hypothesis
from abel_invest.narrative_core.contracts.constants import (
    BRANCH_SPEC_FILENAME,
    BRANCH_STATE_FILENAME,
    EVENTS_HEADER,
    EXPLORATION_PATH_FILENAME,
    GRAPH_FRONTIER_FILENAME,
    READINESS_FILENAME,
)
from abel_invest.narrative_core.io import SessionLock, _now, append_tsv_row
from abel_invest.narrative_core.readiness import (
    build_readiness_warning,
    format_data_readiness_summary,
    readiness_coverage_hint_lines,
)
from abel_invest.narrative_core.runtime.context import branch_context_summary_lines
from abel_invest.narrative_core.rendering.session_rendering import (
    render_section,
    render_session,
)
from abel_invest.narrative_core.session_lifecycle import (
    command_prefix_for_path,
    init_branch_dir,
    init_session_dir,
    render_breadth_first_start_lines,
    resolve_session_root,
    resolve_workspace_arg_path,
)
from abel_invest.narrative_core.state import (
    load_discovery,
    load_readiness,
    persist_branch_hypothesis,
    resolve_backtest_start_request,
    update_backtest_start,
)


def handle_init_session(args: argparse.Namespace) -> int:
    mode = resolve_session_mode(getattr(args, "mode", None))
    session = init_session_dir(
        args.ticker,
        args.exp_id,
        resolve_session_root(
            args.root,
            allow_outside_workspace=args.allow_outside_workspace,
        ),
        discover=args.discover,
        discover_limit=args.discover_limit,
        backtest_start=args.backtest_start,
        mode=mode,
    )
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    print(f"Created Abel strategy discovery session at {session}")
    print(f"  ticker: {discovery.get('ticker', args.ticker.upper())}")
    print(f"  mode: {mode}")
    print(f"  graph_frontier: {session / GRAPH_FRONTIER_FILENAME}")
    print(f"  exploration_path: {session / EXPLORATION_PATH_FILENAME}")
    print(f"  events: {session / 'events.tsv'}")
    if readiness:
        print(f"  readiness: {session / READINESS_FILENAME}")
    if args.discover:
        print(
            f"  frontier_source: {discovery.get('source', 'unknown')} "
            f"(nodes={discovery.get('K_discovery', 0) + 1})"
        )
        readiness_summary = format_data_readiness_summary(readiness)
        if readiness_summary:
            print(f"  data_readiness: {readiness_summary}")
        for line in readiness_coverage_hint_lines(readiness):
            print(f"  {line}")
        warning = build_readiness_warning(readiness)
        if warning:
            print(f"  warning: {warning}")
    else:
        print("  frontier_source: pending (live discovery not run)")
    print("")
    print("From here:")
    for line in render_breadth_first_start_lines(session):
        print(f"  {line}")
    return 0

def resolve_session_mode(raw_mode: str | None) -> str:
    mode = str(
        raw_mode or os.environ.get("ABEL_EXPERIMENT_MODE") or "standard"
    ).strip().lower()
    return "grandma" if mode == "grandma" else "standard"


def handle_set_backtest_start(args: argparse.Namespace) -> int:
    session = resolve_workspace_arg_path(args.session)
    backtest_start, source = resolve_backtest_start_request(
        session=session,
        explicit_date=args.date,
        use_target_safe=args.target_safe,
        use_coverage_hint=args.coverage_hint,
    )
    discovery, readiness = update_backtest_start(
        session=session,
        backtest_start=backtest_start,
        source=source,
    )
    print(f"Updated Abel strategy discovery session at {session}")
    print(f"  backtest_start: {backtest_start}")
    print(f"  source: {source}")
    readiness_summary = format_data_readiness_summary(readiness)
    if readiness_summary:
        print(f"  data_readiness: {readiness_summary}")
    for line in readiness_coverage_hint_lines(readiness):
        print(f"  {line}")
    warning = build_readiness_warning(readiness)
    if warning:
        print(f"  warning: {warning}")
    command_prefix = command_prefix_for_path(session)
    print("")
    print("From here:")
    print(f"  {command_prefix} status --session {session}")
    return 0


def handle_set_hypothesis(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    hypothesis = str(args.text or "").strip()
    if not has_explicit_hypothesis(hypothesis):
        raise RuntimeError(
            "Hypothesis text must include a real causal claim, not an empty placeholder."
        )
    with SessionLock(session):
        persist_branch_hypothesis(branch, hypothesis, source="manual")
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "branch_hypothesis_updated",
                "branch_id": branch.name,
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": "Updated persistent branch hypothesis",
                "artifact_path": str((branch / BRANCH_STATE_FILENAME).relative_to(session)),
            },
        )
        render_session(session)
    print(f"Updated branch hypothesis for {branch}")
    print(f"  hypothesis: {hypothesis}")
    command_prefix = command_prefix_for_path(branch)
    print("")
    print("From here:")
    print(f"  {command_prefix} debug-branch --branch {branch}")
    print(f"  {command_prefix} run-branch --branch {branch} -d \"baseline\"")
    return 0


def handle_init_branch(args: argparse.Namespace) -> int:
    session = resolve_workspace_arg_path(args.session)
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    branch = init_branch_dir(session, args.branch_id)
    print(f"Created Abel strategy discovery branch at {branch}")
    print(f"  branch_spec: {branch / BRANCH_SPEC_FILENAME}")
    print(f"  engine: {branch / 'engine.py'}")
    print(f"  rounds: {branch / 'rounds'}")
    print(f"  outputs: {branch / 'outputs'}")
    print("")
    warning = build_readiness_warning(readiness)
    if warning:
        print("Readiness:")
        print(f"  warning: {warning}")
        for line in readiness_coverage_hint_lines(readiness):
            print(f"  coverage_hint: {line}")
    print("")
    render_section(
        "Branch context",
        branch_context_summary_lines(
            branch=branch,
            session=session,
            discovery=discovery,
            readiness=readiness,
        ),
    )
    print("")
    print("What matters now:")
    print(f"  Read {session / EXPLORATION_PATH_FILENAME} and latest Edge results before choosing this branch's next Edge run.")
    print("  branch.yaml is where target, start, selected inputs, graph use, and overlap become explicit.")
    print("  The generated engine is only a starter path check; it helps you verify the branch wiring before you encode a branch-specific mechanism.")
    print("  If you fetch bars, keep `limit=...` explicit and avoid blanket `dropna()` before confirming the target column survives.")
    print("")
    print("From here:")
    command_prefix = command_prefix_for_path(branch)
    print(f"  edit {branch / BRANCH_SPEC_FILENAME}")
    print(f"  {command_prefix} prepare-branch --branch {branch}")
    print(f"  {command_prefix} debug-branch --branch {branch}")
    print(f"  {command_prefix} run-branch --branch {branch} -d \"baseline\"")
    print(f"  edit {branch / 'engine.py'}")
    return 0
