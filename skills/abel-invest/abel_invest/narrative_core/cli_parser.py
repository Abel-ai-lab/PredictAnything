"""Argparse construction for the Abel strategy-discovery CLI."""

from __future__ import annotations

import argparse

from abel_invest import __version__
from abel_invest.narrative_core.contracts.constants import CHANGED_DIMENSIONS, DEFAULT_BACKTEST_START
from abel_invest.workspace_core.workspace import DEFAULT_WORKSPACE_NAME


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Abel strategy discovery workspace CLI")
    parser.add_argument("--version", action="version", version=f"abel-invest {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    workspace = sub.add_parser("workspace", help="Create or inspect an Abel strategy discovery workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)

    workspace_init = workspace_sub.add_parser(
        "init",
        help="Create a new workspace scaffold without preparing the runtime",
    )
    workspace_init.add_argument("name", help="Workspace name recorded in the manifest")
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
    env_init = env_sub.add_parser("init", help="Create the workspace venv and install or upgrade dependencies")
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
        "--runtime-python",
        default=None,
        help="Use an existing interpreter instead of creating the workspace venv",
    )
    env_init.add_argument(
        "--no-editable",
        action="store_true",
        help="Install Abel strategy discovery from local source in regular mode instead of editable mode",
    )
    env_refresh = env_sub.add_parser(
        "refresh",
        help="Upgrade the existing workspace runtime to match the current Abel Invest skill",
    )
    env_refresh.add_argument(
        "--path",
        default=".",
        help="Directory inside the target workspace",
    )
    env_refresh.add_argument(
        "--python",
        dest="base_python",
        default=None,
        help="Base interpreter used if the workspace venv must be created",
    )
    env_refresh.add_argument(
        "--alpha-source",
        default=None,
        help="Local Abel strategy discovery source tree used for installation",
    )
    env_refresh.add_argument(
        "--runtime-python",
        default=None,
        help="Use an existing interpreter instead of creating the workspace venv",
    )
    env_refresh.add_argument(
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

    init_session = sub.add_parser("init-session", help="Create an Abel Invest research session")
    init_session.add_argument("--ticker", required=True, help="Target ticker for this strategy discovery session")
    init_session.add_argument("--exp-id", required=True, help="Session id written under the workspace research root")
    init_session.add_argument(
        "--root",
        default=None,
        help="Explicit research root. Omit during normal workspace-owned research.",
    )
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
    init_session.add_argument(
        "--mode",
        default=None,
        choices=["standard", "grandma"],
        help="Session strategy mode. Grandma mode routes branches to the conservative grandma_daily profile.",
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
        type=_positive_int,
        default=10,
        help="Maximum Abel nodes to record per discovery call",
    )

    set_backtest_start = sub.add_parser(
        "set-backtest-start",
        help="Update the session-level backtest start and refresh readiness",
    )
    set_backtest_start.add_argument("--session", required=True, help="Session path, workspace-relative or absolute")
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
    set_hypothesis.add_argument("--branch", required=True, help="Branch path, workspace-relative or absolute")
    set_hypothesis.add_argument("--text", required=True, help="Causal claim with expected sign and invalidation condition")

    init_branch = sub.add_parser("init-branch", help="Create a branch under a session")
    init_branch.add_argument("--session", required=True, help="Session path, workspace-relative or absolute")
    init_branch.add_argument("--branch-id", required=True, help="Short branch id describing the hypothesis family")

    frontier = sub.add_parser("frontier", help="Inspect or expand the session graph frontier")
    frontier_sub = frontier.add_subparsers(dest="frontier_command", required=True)
    frontier_status = frontier_sub.add_parser("status", help="Show graph frontier status")
    frontier_status.add_argument("--session", required=True, help="Session path, workspace-relative or absolute")
    frontier_expand = frontier_sub.add_parser("expand", help="Expand a graph frontier node")
    frontier_expand.add_argument("--session", required=True, help="Session path, workspace-relative or absolute")
    frontier_expand.add_argument("--node", "--anchor", dest="node", required=True)
    frontier_expand.add_argument(
        "--mode",
        default="all",
        choices=["all", "parents", "children", "blanket"],
        help="Graph expansion mode",
    )
    frontier_expand.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help="Maximum Abel nodes to record for the expansion",
    )

    prepare_branch = sub.add_parser(
        "prepare-branch",
        help="Resolve branch data dependencies and warm the edge cache before evaluation",
    )
    prepare_branch.add_argument("--branch", required=True, help="Branch path, workspace-relative or absolute")
    prepare_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run abel-edge warm-cache (defaults to the workspace python when available)",
    )
    prepare_branch.add_argument(
        "--cache-limit",
        type=_positive_int,
        default=5000,
        help="Warm-cache fetch limit used for each requested symbol",
    )

    run_branch = sub.add_parser(
        "run-branch", help="Run edge evaluate and record a branch round"
    )
    run_branch.add_argument("--branch", required=True, help="Branch path, workspace-relative or absolute")
    run_branch.add_argument("--mode", default="explore", choices=["explore", "exploit"])
    run_branch.add_argument("-d", "--description", required=True, help="Short factual label for this recorded round")
    run_branch.add_argument("--input-note", default="", help="Optional note about realized branch inputs")
    run_branch.add_argument("--hypothesis", default="", help="Round-specific causal claim when it differs from branch.yaml")
    run_branch.add_argument("--expected-signal", default="", help="Expected sign, lag, or behavior before seeing the result")
    run_branch.add_argument("--summary", default="", help="Agent-written result summary for the round note")
    run_branch.add_argument("--next-step", default="", help="Agent's proposed follow-up after reading this result")
    run_branch.add_argument("--trigger", default="", help="Why this round was run now")
    run_branch.add_argument("--change-summary", default="", help="What changed relative to the prior branch state")
    run_branch.add_argument("--time-spent-min", default="", help="Approximate active research time in minutes")
    run_branch.add_argument("--action", action="append", default=[], help="Repeatable audit note about actions taken before the round")
    run_branch.add_argument(
        "--changed-dimension",
        action="append",
        default=[],
        choices=sorted(CHANGED_DIMENSIONS),
        help="Factual dimension changed in this round; repeat for multiple dimensions",
    )
    run_branch.add_argument(
        "--selection-trials",
        type=_positive_int,
        default=1,
        help=(
            "Audit count for accidental or explicitly requested strategy or "
            "parameter configurations tried before this round output"
        ),
    )
    run_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run abel-edge evaluate (defaults to the workspace python when available)",
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
        "--locale",
        default="",
        help="Optional dashboard locale. Accepts en/en-US or zh/zh-CN; uploads en-US or zh-CN.",
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
    visualize_session.add_argument(
        "--with-strategy-artifact",
        action="store_true",
        help=(
            "Prepare the session's best ranked hostable strategy artifact, then upload "
            "narrative and artifact."
        ),
    )
    visualize_session.add_argument(
        "--artifact-output-dir",
        default=None,
        help="Optional local directory for generated strategy artifact files.",
    )
    visualize_session.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run Abel-edge artifact helpers (defaults to workspace python).",
    )

    export_strategy_artifact = sub.add_parser(
        "export-strategy-artifact",
        help="Export the best ranked hostable strategy artifact for a session without uploading it",
    )
    export_strategy_artifact.add_argument("--session", required=True)
    export_strategy_artifact.add_argument(
        "--output-dir",
        default=None,
        help="Destination directory for manifest.json, trade-log.csv, and artifact.zip",
    )
    export_strategy_artifact.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run Abel-edge export helpers (defaults to workspace python)",
    )

    promote_strategy = sub.add_parser(
        "promote-strategy",
        help="Promote an explicit branch/round into a paper-ready artifact",
    )
    promote_strategy.add_argument("--branch", required=True)
    promote_strategy.add_argument(
        "--round",
        default=None,
        help="Promotion source round. Required when the branch has multiple validation rounds.",
    )
    promote_strategy.add_argument(
        "--output-dir",
        default=None,
        help="Destination directory for manifest.json, trade-log.csv, and artifact.zip",
    )
    promote_strategy.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run Abel-edge export helpers (defaults to workspace python)",
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
