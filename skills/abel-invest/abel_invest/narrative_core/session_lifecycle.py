"""Session and branch lifecycle helpers for strategy discovery."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from abel_invest.narrative_core.contracts.branch_spec import (
    build_default_branch_spec,
    write_branch_spec,
)
from abel_invest.narrative_core.contracts.constants import (
    DEFAULT_BACKTEST_START,
    EVENTS_HEADER,
    EXPLORATION_PATH_FILENAME,
    GRAPH_FRONTIER_FILENAME,
    READINESS_FILENAME,
    RESULTS_HEADER,
)
from abel_invest.workspace_core.doctor import build_auth_recovery_instruction, workspace_command
from abel_invest.narrative_core.runtime.edge_commands import run_edge_verify_data
from abel_invest.workspace_core.edge_runtime import resolve_runtime_auth_env_file
from abel_invest.narrative_core.io import (
    SessionLock,
    _now,
    append_tsv_row,
    write_tsv_header,
)
from abel_invest.narrative_core.evidence.exploration_path import ensure_exploration_path
from abel_invest.narrative_core.evidence import graph_frontier
from abel_invest.narrative_core.contracts.paths import branch_spec_path, branch_state_path, session_state_path
from abel_invest.narrative_core.readiness import format_data_readiness_summary
from abel_invest.narrative_core.rendering.session_rendering import render_session
from abel_invest.narrative_core.state import (
    load_branch_state,
    load_discovery,
    load_readiness,
    render_default_engine_template,
    write_branch_state,
    write_session_state,
)
from abel_invest.workspace_core.workspace import (
    default_workspace_path,
    find_workspace_root,
    load_workspace_manifest,
    resolve_workspace_entry,
    resolve_workspace_paths,
)


def resolve_session_root(
    root_arg: str | None,
    *,
    allow_outside_workspace: bool = False,
) -> Path:
    """Resolve the session root from an explicit argument or current workspace."""
    workspace_root, _ = resolve_workspace_entry()
    if workspace_root is not None:
        manifest = load_workspace_manifest(workspace_root)
        workspace_research_root = resolve_workspace_paths(workspace_root, manifest)[
            "research_root"
        ]
        if not root_arg:
            return workspace_research_root

        explicit_root = resolve_workspace_arg_path(root_arg)
        explicit_workspace_root = find_workspace_root(explicit_root)
        if explicit_workspace_root == workspace_root:
            return explicit_root
        if _path_is_relative_to(explicit_root.resolve(), workspace_root.resolve()):
            return explicit_root
        if allow_outside_workspace:
            return explicit_root
        command_prefix = workspace_command(workspace_root, None)
        raise RuntimeError(
            "Refusing to create an Abel strategy discovery session outside the "
            f"resolved workspace root {workspace_root}. "
            f"Use plain `{command_prefix} init-session --ticker ... --exp-id ...` to "
            f"create under {workspace_research_root}, or add "
            "`--allow-outside-workspace` when this is an intentional offline or "
            "legacy session."
        )

    if root_arg and allow_outside_workspace:
        return resolve_workspace_arg_path(root_arg)

    entry_path = Path.cwd().resolve()
    target = default_workspace_path(entry_path)
    raise RuntimeError(
        "No Abel strategy discovery workspace was resolved for session creation. "
        f"Entry path: {entry_path}. "
        f"Default workspace path: {target}. "
        "Run `abel-invest workspace context --path . --json` to inspect the "
        "current workspace if the CLI is on PATH, or bootstrap one with "
        f"`abel-invest workspace bootstrap --path {target}`. "
        "For an intentional offline or legacy session, pass both `--root` and "
        "`--allow-outside-workspace`."
    )


def render_breadth_first_start_lines(session: Path) -> list[str]:
    command_prefix = command_prefix_for_path(session)
    return [
        "graph-first research loop:",
        f"read {session / EXPLORATION_PATH_FILENAME} and latest Edge results before choosing the next branch or round",
        f"{command_prefix} init-branch --session {session} --branch-id <family-a-branch>",
        f"{command_prefix} init-branch --session {session} --branch-id <family-b-branch>",
        "edit each branch.yaml with graph/input hypotheses and agent-chosen mechanism-family declarations",
        f"after each recorded round, keep {EXPLORATION_PATH_FILENAME} updated with the path, why, Edge feedback, and ledger ref",
    ]


def command_prefix_for_path(path: Path | None = None) -> str:
    """Return the preferred Abel Invest command prefix for a workspace path."""
    workspace_root = find_workspace_root(path) if path is not None else None
    if workspace_root is None:
        workspace_root, _ = resolve_workspace_entry()
    if workspace_root is None:
        return "abel-invest"
    return workspace_command(workspace_root, None)


def resolve_workspace_arg_path(value: str) -> Path:
    """Resolve a CLI path argument relative to the current workspace when possible."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    cwd_relative = (Path.cwd() / path).resolve(strict=False)
    if cwd_relative.exists():
        return cwd_relative
    workspace_root, _ = resolve_workspace_entry()
    if workspace_root is not None:
        return workspace_root / path
    return path


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def init_session_dir(
    ticker: str,
    exp_id: str,
    root: Path,
    *,
    discover: bool = False,
    discover_limit: int = 10,
    backtest_start: str = DEFAULT_BACKTEST_START,
) -> Path:
    session = root / ticker.lower() / exp_id
    session.mkdir(parents=True, exist_ok=True)
    ensure_exploration_path(session)
    frontier_data = None
    discovery_data = None
    readiness_report = None
    if discover:
        frontier_data = graph_frontier.fetch_live_graph_frontier(
            ticker,
            limit=discover_limit,
            backtest_start=backtest_start,
        )
        discovery_data = graph_frontier.graph_frontier_to_discovery(frontier_data)
        readiness_report = refresh_data_readiness(
            session=session,
            discovery_data=discovery_data,
            backtest_start=backtest_start,
        )
    else:
        frontier_data = graph_frontier.build_pending_graph_frontier(
            ticker,
            backtest_start=backtest_start,
        )
        discovery_data = graph_frontier.graph_frontier_to_discovery(frontier_data)
    with SessionLock(session):
        write_tsv_header(session / "events.tsv", EVENTS_HEADER)
        if not session_state_path(session).exists():
            write_session_state(session, {})
        graph_frontier.write_graph_frontier(session, frontier_data)
        if readiness_report is not None:
            write_readiness(session, readiness_report)
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "session_created",
                "branch_id": "",
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": f"Initialized Abel strategy discovery narrative session (backtest start {backtest_start})",
                "artifact_path": "",
            },
        )
        if discover and discovery_data is not None:
            append_tsv_row(
                session / "events.tsv",
                EVENTS_HEADER,
                {
                    "timestamp": _now(),
                    "event": "discovery_recorded",
                    "branch_id": "",
                    "round_id": "",
                    "mode": "",
                    "verdict": "",
                    "decision": "",
                    "description": (
                        f"Recorded live Abel discovery with K={discovery_data['K_discovery']}"
                    ),
                    "artifact_path": GRAPH_FRONTIER_FILENAME,
                },
            )
            if readiness_report:
                append_tsv_row(
                    session / "events.tsv",
                    EVENTS_HEADER,
                    {
                        "timestamp": _now(),
                        "event": "data_readiness_recorded",
                        "branch_id": "",
                        "round_id": "",
                        "mode": "",
                        "verdict": "",
                        "decision": "",
                        "description": (
                            "Recorded driver data readiness: "
                            f"{format_data_readiness_summary(readiness_report)}"
                        ),
                        "artifact_path": READINESS_FILENAME,
                    },
                )
        render_session(session)
    return session


def fetch_live_discovery(ticker: str, *, limit: int) -> dict:
    try:
        from abel_edge.plugins.abel.credentials import (
            MissingAbelApiKeyError,
            require_api_key,
        )
        from abel_edge.plugins.abel.discover import discover_graph_payload
    except ImportError as exc:
        workspace_root, _ = resolve_workspace_entry()
        command_prefix = workspace_command(workspace_root, None) if workspace_root else "abel-invest"
        raise RuntimeError(
            "Live Abel discovery requires abel-edge with the Abel plugin installed. "
            f"Run `{command_prefix} doctor` in the workspace, follow its env next_step, "
            "rerun doctor, then retry."
        ) from exc
    workspace_root, _ = resolve_workspace_entry()
    if workspace_root is not None:
        auth_env = resolve_runtime_auth_env_file(workspace_root)
        if auth_env is not None:
            os.environ.setdefault("ABEL_AUTH_ENV_FILE", str(auth_env))

    try:
        require_api_key()
    except MissingAbelApiKeyError as exc:
        command_prefix = workspace_command(workspace_root, None) if workspace_root else "abel-invest"
        raise RuntimeError(
            "init-session live graph discovery is blocked on Abel auth. "
            "No reusable auth was found. "
            f"{build_auth_recovery_instruction(workspace_root or Path.cwd())}\n\n"
            f"After auth is ready, retry `{command_prefix} init-session --ticker "
            f"{ticker.upper()} --exp-id <exp-id>`."
        ) from exc

    payload = discover_graph_payload(ticker.upper(), mode="all", limit=limit)
    payload["backtest"] = {"start": DEFAULT_BACKTEST_START}
    payload.setdefault("created_at", _now())
    return payload


def write_discovery(session: Path, discovery_data: dict) -> None:
    (session / "discovery.json").write_text(
        json.dumps(discovery_data, indent=2),
        encoding="utf-8",
    )


def write_readiness(session: Path, readiness_report: dict) -> None:
    (session / READINESS_FILENAME).write_text(
        json.dumps(readiness_report, indent=2),
        encoding="utf-8",
    )


def refresh_data_readiness(
    *,
    session: Path,
    discovery_data: dict,
    backtest_start: str,
) -> dict | None:
    """Compute the edge-owned data readiness report for a live discovery payload."""
    fd, temp_name = tempfile.mkstemp(dir=session, suffix="-discovery.json")
    os.close(fd)
    discovery_path = Path(temp_name)
    discovery_path.write_text(json.dumps(discovery_data, indent=2), encoding="utf-8")
    try:
        report = run_edge_verify_data(
            session=session,
            discovery_path=discovery_path,
            backtest_start=backtest_start,
        )
    except RuntimeError:
        discovery_path.unlink(missing_ok=True)
        return None
    finally:
        discovery_path.unlink(missing_ok=True)
    return report


def init_branch_dir(session: Path, branch_id: str) -> Path:
    with SessionLock(session):
        discovery = load_discovery(session)
        readiness = load_readiness(session)
        frontier = graph_frontier.load_graph_frontier(session)
        branch = session / "branches" / branch_id
        branch.mkdir(parents=True, exist_ok=True)
        (branch / "rounds").mkdir(parents=True, exist_ok=True)
        (branch / "outputs").mkdir(parents=True, exist_ok=True)
        write_tsv_header(branch / "results.tsv", RESULTS_HEADER)
        if not branch_state_path(branch).exists():
            write_branch_state(branch, {"created_at": _now()})
        else:
            state = load_branch_state(branch)
            state.setdefault("created_at", _now())
            write_branch_state(branch, state)
        if not branch_spec_path(branch).exists():
            write_branch_spec(
                branch,
                build_default_branch_spec(
                    branch=branch,
                    discovery=discovery,
                    readiness=readiness,
                    graph_frontier=frontier,
                ),
            )
        engine = branch / "engine.py"
        if not engine.exists():
            engine.write_text(
                render_default_engine_template(discovery, readiness, session),
                encoding="utf-8",
            )
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "branch_created",
                "branch_id": branch_id,
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": "Initialized Abel strategy discovery branch",
                "artifact_path": "",
            },
        )
        render_session(session)
    return branch
