"""Argparse construction for the Abel strategy-discovery CLI."""

from __future__ import annotations

import argparse

from abel_invest.narrative_core.contracts.constants import CHANGED_DIMENSIONS, DEFAULT_BACKTEST_START
from abel_invest.workspace_core.workspace import DEFAULT_WORKSPACE_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Abel strategy discovery workspace CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    workspace = sub.add_parser("workspace", help="Create or inspect an Abel strategy discovery workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)

    workspace_init = workspace_sub.add_parser(
        "init",
        help="Create a new workspace scaffold without preparing the runtime",
    )
    workspace_init.add_argument("name", help="Workspace directory name")
    workspace_init.add_argument(
        "--path",
        required=True,
        help="Explicit workspace directory path",
    )

    workspace_bootstrap = workspace_sub.add_parser(
        "bootstrap",
        help="Create or reuse a workspace, prepare its runtime, and run doctor",
    )
    workspace_bootstrap.add_argument(
        "--path",
        required=True,
        help="Explicit workspace directory path",
    )
    workspace_bootstrap.add_argument(
        "--name",
        default=DEFAULT_WORKSPACE_NAME,
        help=f"Workspace name recorded in the manifest (defaults to {DEFAULT_WORKSPACE_NAME})",
    )
    workspace_bootstrap.add_argument(
        "--python",
        dest="base_python",
        default=None,
        help="Base interpreter used to create the workspace venv",
    )
    workspace_bootstrap.add_argument(
        "--alpha-source",
        default=None,
        help="Local Abel strategy discovery source tree used for installation",
    )
    workspace_bootstrap.add_argument(
        "--edge-spec",
        default=None,
        help="Pip-installable Abel-edge target (defaults to the workspace GitHub main spec)",
    )
    workspace_bootstrap.add_argument(
        "--edge-source",
        default=None,
        help="Optional local Abel-edge source tree override for development",
    )
    workspace_bootstrap.add_argument(
        "--runtime-python",
        default=None,
        help="Use an existing interpreter instead of creating the workspace venv",
    )
    workspace_bootstrap.add_argument(
        "--no-editable",
        action="store_true",
        help="Install Abel strategy discovery from local source in regular mode instead of editable mode",
    )

    workspace_status = workspace_sub.add_parser("status", help="Show current workspace status")
    workspace_status.add_argument(
        "--path",
        default=".",
        help="Directory to inspect for the nearest workspace root",
    )
    workspace_context = workspace_sub.add_parser(
        "context",
        help="Show resolved workspace context for agent re-entry",
    )
    workspace_context.add_argument(
        "--path",
        default=".",
        help="Directory to inspect for the nearest workspace root",
    )
    workspace_context.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output",
    )

    env_parser = sub.add_parser("env", help="Manage the local workspace Python environment")
    env_sub = env_parser.add_subparsers(dest="env_command", required=True)
    env_init = env_sub.add_parser("init", help="Create the workspace venv and install dependencies")
    env_init.add_argument(
        "--path",
        default=".",
        help="Directory inside the target workspace",
    )
    env_init.add_argument(
        "--python",
        dest="base_python",
        default=None,
        help="Base interpreter used to create the workspace venv",
    )
    env_init.add_argument(
        "--alpha-source",
        default=None,
        help="Local Abel strategy discovery source tree used for installation",
    )
    env_init.add_argument(
        "--edge-spec",
        default=None,
        help="Pip-installable Abel-edge target (defaults to the workspace GitHub main spec)",
    )
    env_init.add_argument(
        "--edge-source",
        default=None,
        help="Optional local Abel-edge source tree override for development",
    )
    env_init.add_argument(
        "--runtime-python",
        default=None,
        help="Use an existing interpreter instead of creating the workspace venv",
    )
    env_init.add_argument(
        "--no-editable",
        action="store_true",
        help="Install Abel strategy discovery from local source in regular mode instead of editable mode",
    )

    doctor = sub.add_parser("doctor", help="Check workspace readiness")
    doctor.add_argument(
        "--path",
        default=".",
        help="Directory inside the target workspace",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output",
    )

    init_session = sub.add_parser("init-session", help="Create a narrative session")
    init_session.add_argument("--ticker", required=True)
    init_session.add_argument("--exp-id", required=True)
    init_session.add_argument("--root", default=None)
    init_session.add_argument(
        "--allow-outside-workspace",
        action="store_true",
        help="Allow explicit --root session creation outside an Abel workspace",
    )
    init_session.add_argument(
        "--backtest-start",
        default=DEFAULT_BACKTEST_START,
        help="Session-level backtest start date passed to abel-edge evaluate",
    )
    discovery_group = init_session.add_mutually_exclusive_group()
    discovery_group.add_argument(
        "--discover",
        dest="discover",
        action="store_true",
        default=True,
        help="Run live Abel discovery and persist it into graph_frontier.json (default)",
    )
    discovery_group.add_argument(
        "--no-discover",
        dest="discover",
        action="store_false",
        help="Create an explicit pending/offline session without live graph discovery",
    )
    init_session.add_argument(
        "--discover-limit",
        type=int,
        default=10,
        help="Maximum Abel nodes to record per discovery call",
    )

    set_backtest_start = sub.add_parser(
        "set-backtest-start",
        help="Update the session-level backtest start and refresh readiness",
    )
    set_backtest_start.add_argument("--session", required=True)
    start_group = set_backtest_start.add_mutually_exclusive_group(required=True)
    start_group.add_argument(
        "--date",
        default=None,
        help="Explicit YYYY-MM-DD backtest start",
    )
    start_group.add_argument(
        "--target-safe",
        action="store_true",
        help="Use the target-safe start hint from readiness",
    )
    start_group.add_argument(
        "--coverage-hint",
        action="store_true",
        help="Use the dense-overlap coverage hint from readiness",
    )

    set_hypothesis = sub.add_parser(
        "set-hypothesis",
        help="Persist a branch-level hypothesis without recording a round",
    )
    set_hypothesis.add_argument("--branch", required=True)
    set_hypothesis.add_argument("--text", required=True)

    init_branch = sub.add_parser("init-branch", help="Create a branch under a session")
    init_branch.add_argument("--session", required=True)
    init_branch.add_argument("--branch-id", required=True)

    frontier = sub.add_parser("frontier", help="Inspect or expand the session graph frontier")
    frontier_sub = frontier.add_subparsers(dest="frontier_command", required=True)
    frontier_status = frontier_sub.add_parser("status", help="Show graph frontier status")
    frontier_status.add_argument("--session", required=True)
    frontier_expand = frontier_sub.add_parser("expand", help="Expand a graph frontier node")
    frontier_expand.add_argument("--session", required=True)
    frontier_expand.add_argument("--node", "--anchor", dest="node", required=True)
    frontier_expand.add_argument(
        "--mode",
        default="all",
        choices=["all", "parents", "children", "blanket"],
        help="Graph expansion mode",
    )
    frontier_expand.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum Abel nodes to record for the expansion",
    )

    prepare_branch = sub.add_parser(
        "prepare-branch",
        help="Resolve branch data dependencies and warm the edge cache before evaluation",
    )
    prepare_branch.add_argument("--branch", required=True)
    prepare_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run abel-edge warm-cache (defaults to the workspace python when available)",
    )
    prepare_branch.add_argument(
        "--cache-limit",
        type=int,
        default=5000,
        help="Warm-cache fetch limit used for each requested symbol",
    )

    run_branch = sub.add_parser(
        "run-branch", help="Run edge evaluate and record a branch round"
    )
    run_branch.add_argument("--branch", required=True)
    run_branch.add_argument("--mode", default="explore", choices=["explore", "exploit"])
    run_branch.add_argument("-d", "--description", required=True)
    run_branch.add_argument("--input-note", default="")
    run_branch.add_argument("--hypothesis", default="")
    run_branch.add_argument("--expected-signal", default="")
    run_branch.add_argument("--summary", default="")
    run_branch.add_argument("--next-step", default="")
    run_branch.add_argument("--trigger", default="")
    run_branch.add_argument("--change-summary", default="")
    run_branch.add_argument("--time-spent-min", default="")
    run_branch.add_argument("--action", action="append", default=[])
    run_branch.add_argument(
        "--changed-dimension",
        action="append",
        default=[],
        choices=sorted(CHANGED_DIMENSIONS),
        help="Factual dimension changed in this round; repeat for multiple dimensions",
    )
    run_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run abel-edge evaluate (defaults to the workspace python when available)",
    )
    promote_branch = sub.add_parser(
        "promote-branch",
        help="Create a promotion bundle from a prepared research branch",
    )
    promote_branch.add_argument("--branch", required=True)
    promote_branch.add_argument(
        "--output-dir",
        default=None,
        help="Optional destination directory (defaults to <session>/promotions/<branch-id>)",
    )

    upload_dashboard = sub.add_parser(
        "upload-dashboard-bundle",
        help="Upload branch evidence to the Abel router skill dashboard",
    )
    upload_dashboard.add_argument("--branch", required=True)
    upload_dashboard.add_argument(
        "--api-key",
        default="",
        help="API key. Defaults to ABEL_API_KEY/CAP_API_KEY from env or shared Abel auth.",
    )
    upload_dashboard.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write the upload payload before sending.",
    )
    upload_dashboard.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the payload without sending it.",
    )

    visualize_session = sub.add_parser(
        "visualize-session",
        help="Create an online Abel skill dashboard view for a session",
    )
    visualize_session.add_argument("--session", required=True)
    visualize_session.add_argument(
        "--api-key",
        default="",
        help="API key. Defaults to ABEL_API_KEY/CAP_API_KEY from env or shared Abel auth.",
    )
    visualize_session.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write the upload payload before sending.",
    )
    visualize_session.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the payload without sending it.",
    )

    debug_branch = sub.add_parser(
        "debug-branch",
        help="Run edge debug-evaluate without recording a narrative round",
    )
    debug_branch.add_argument("--branch", required=True)
    debug_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run abel-edge debug-evaluate (defaults to the workspace python when available)",
    )

    render = sub.add_parser("render", help="Render summaries for a session")
    render.add_argument("--session", required=True)

    status = sub.add_parser("status", help="Print session status")
    status.add_argument("--session", required=True)

    check = sub.add_parser("check", help="Check narrative completeness")
    check.add_argument("--session", required=True)
    check.add_argument("--strict", action="store_true")
    return parser
