"""Command router for the Abel strategy-discovery CLI."""

from __future__ import annotations

from pathlib import Path

from abel_invest.narrative_core.command_handlers.branch import (
    debug_branch_run,
    prepare_branch_inputs,
    run_branch_round,
)
from abel_invest.narrative_core.command_handlers.frontier import handle_frontier_command
from abel_invest.narrative_core.command_handlers.session import (
    handle_init_branch,
    handle_init_session,
    handle_set_backtest_start,
    handle_set_hypothesis,
)
from abel_invest.narrative_core.command_handlers.workspace import (
    handle_doctor_command,
    handle_env_command,
    handle_workspace_command,
)
from abel_invest.narrative_core.cli_parser import build_parser
from abel_invest.narrative_core.dashboard import upload_skill_dashboard_session
from abel_invest.narrative_core.rendering.session_rendering import (
    check_session,
    print_status,
    render_session,
)
from abel_invest.narrative_core.session_lifecycle import resolve_workspace_arg_path
from abel_invest.narrative_core.strategy_artifacts import (
    export_strategy_artifact_command,
    promote_strategy_command,
)
from abel_invest.workspace_core.edge_runtime import apply_workspace_env
from abel_invest.workspace_core.workspace import find_workspace_root, resolve_workspace_entry


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    hydrate_command_workspace_env(args)

    if args.command == "workspace":
        return handle_workspace_command(args)
    if args.command == "env":
        return handle_env_command(args)
    if args.command == "doctor":
        return handle_doctor_command(args)
    if args.command == "init-session":
        return handle_init_session(args)
    if args.command == "set-backtest-start":
        return handle_set_backtest_start(args)
    if args.command == "set-hypothesis":
        return handle_set_hypothesis(args)
    if args.command == "init-branch":
        return handle_init_branch(args)
    if args.command == "frontier":
        return handle_frontier_command(args)
    if args.command == "prepare-branch":
        return prepare_branch_inputs(args)
    if args.command == "run-branch":
        return run_branch_round(args)
    if args.command == "visualize-session":
        return upload_skill_dashboard_session(args)
    if args.command == "export-strategy-artifact":
        return export_strategy_artifact_command(args)
    if args.command == "promote-strategy":
        return promote_strategy_command(args)
    if args.command == "debug-branch":
        return debug_branch_run(args)
    if args.command == "render":
        render_session(resolve_workspace_arg_path(args.session))
        return 0
    if args.command == "status":
        print_status(resolve_workspace_arg_path(args.session))
        return 0
    if args.command == "check":
        return check_session(resolve_workspace_arg_path(args.session), strict=args.strict)
    return 1


def hydrate_command_workspace_env(args) -> None:
    """Load workspace-local Abel runtime env before command handlers run."""
    workspace_root = resolve_command_workspace_root(args)
    if workspace_root is not None:
        apply_workspace_env(workspace_root)


def resolve_command_workspace_root(args) -> Path | None:
    """Resolve the workspace root most relevant to a parsed command."""
    for attr in ("branch", "session", "path", "root"):
        raw = getattr(args, attr, None)
        if not raw:
            continue
        candidate = Path(str(raw)).expanduser()
        is_absolute = candidate.is_absolute()
        if not is_absolute:
            candidate = Path.cwd() / candidate
        start = candidate if candidate.exists() else candidate.parent
        workspace_root = find_workspace_root(start)
        if workspace_root is not None:
            return workspace_root
        if is_absolute:
            return None

    workspace_root, _ = resolve_workspace_entry()
    return workspace_root


if __name__ == "__main__":
    raise SystemExit(main())
