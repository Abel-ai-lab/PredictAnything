"""Abel strategy discovery research narrative layer.

Organizes exploration sessions, records experimental process, and renders narrative
summaries on top of raw causal-edge evaluation outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from abel_strategy_discovery.doctor import (
    build_auth_recovery_instruction,
    doctor_exit_code,
    render_doctor_report,
    run_doctor,
)
from abel_strategy_discovery.edge_runtime import (
    build_workspace_runtime_env,
    resolve_runtime_auth_env_file,
)
from abel_strategy_discovery.env import init_workspace_env
from abel_strategy_discovery.workspace import (
    DEFAULT_WORKSPACE_NAME,
    build_default_manifest,
    default_workspace_path,
    default_activate_command,
    inspect_workspace_bootstrap_target,
    is_workspace_root,
    find_workspace_root,
    load_workspace_manifest,
    resolve_workspace_entry,
    resolve_workspace_env_file,
    resolve_runtime_python,
    render_workspace_status,
    resolve_workspace_paths,
    scaffold_workspace,
)

EVENTS_HEADER = [
    "timestamp",
    "event",
    "branch_id",
    "round_id",
    "mode",
    "verdict",
    "decision",
    "description",
    "artifact_path",
]

DEFAULT_BACKTEST_START = "2020-01-01"
SESSION_STATE_FILENAME = "session_state.json"
BRANCH_STATE_FILENAME = "branch_state.json"
READINESS_FILENAME = "readiness.json"
BRANCH_SPEC_FILENAME = "branch.yaml"
DEPENDENCIES_FILENAME = "dependencies.json"
RUNTIME_PROFILE_FILENAME = "runtime_profile.json"
EXECUTION_CONSTRAINTS_FILENAME = "execution_constraints.json"
DATA_MANIFEST_FILENAME = "data_manifest.json"
CONTEXT_GUIDE_FILENAME = "context_guide.md"
PROBE_SAMPLES_FILENAME = "probe_samples.json"
MEMORY_MANIFEST_FILENAME = "manifest.json"
MEMORY_BRANCHES_FILENAME = "branches.tsv"
MEMORY_ROUNDS_FILENAME = "rounds.tsv"
MEMORY_VALIDATIONS_FILENAME = "validations.tsv"
MEMORY_INSIGHTS_FILENAME = "insights.tsv"
MEMORY_LINKS_FILENAME = "links.tsv"
MEMORY_VIEWS_DIRNAME = "views"
MEMORY_OVERVIEW_FILENAME = "overview.md"
MEMORY_COMPARE_FILENAME = "compare.md"

RESULTS_HEADER = [
    "exp_id",
    "ticker",
    "branch_id",
    "round_id",
    "decision",
    "lo_adj",
    "ic",
    "omega",
    "sharpe",
    "max_dd",
    "pnl",
    "K",
    "score",
    "verdict",
    "mode",
    "description",
    "result_path",
    "report_path",
    "handoff_path",
]

MEMORY_BRANCHES_HEADER = [
    "branch_id",
    "asset_scope",
    "exp_id",
    "method_family",
    "source_type",
    "parent_branch_id",
    "status",
    "latest_round_id",
    "best_round_id",
    "best_validation_id",
    "thesis_short",
    "created_at",
]

MEMORY_ROUNDS_HEADER = [
    "round_id",
    "branch_id",
    "stage",
    "started_at",
    "ended_at",
    "trigger",
    "hypothesis",
    "change_summary",
    "action_summary",
    "decision",
    "next_step",
    "time_spent_min",
]

MEMORY_VALIDATIONS_HEADER = [
    "validation_id",
    "branch_id",
    "round_id",
    "engine",
    "verdict",
    "score",
    "sharpe",
    "lo_adj",
    "omega",
    "total_return",
    "max_dd",
    "result_ref",
    "report_ref",
]

MEMORY_INSIGHTS_HEADER = [
    "insight_id",
    "scope",
    "branch_id",
    "round_id",
    "kind",
    "statement",
    "reusable_rule",
    "confidence",
    "origin",
]

MEMORY_LINKS_HEADER = [
    "link_id",
    "from_branch_id",
    "to_branch_id",
    "link_type",
    "match_score",
    "match_basis",
    "status",
    "note",
    "origin",
]

ENGINE_TEMPLATE = '''"""Research engine for {ticker}. Replace the starter baseline when the branch thesis is ready.

Default backtest behavior should follow branch.yaml first and the injected context second.
If provided, self.context contains workspace/session/branch/discovery/readiness metadata from Abel strategy discovery.
Use branch.yaml to make the critical research choices explicit:
  - target
  - requested_start
  - selected_drivers
  - overlap_mode
Write against DecisionContext instead of raw research helpers:
  - ctx.decision_index()
  - ctx.target.series("close")
  - ctx.feed(name).asof_series("close")
  - ctx.points()
  - ctx.decisions(next_position)
If data or runtime setup is broken, let the error surface and inspect it with `abel-strategy-discovery debug-branch`;
do not hide setup failures behind synthetic outputs.
Current readiness warning: {readiness_warning}
Coverage hints: {coverage_hints_text}
"""
 
from __future__ import annotations

from causal_edge.engine.base import StrategyEngine


class BranchEngine(StrategyEngine):
    def compute_decisions(self, ctx):
        close = ctx.target.series("close")
        if close.empty:
            raise RuntimeError(
                "The default Abel strategy discovery baseline loaded no usable target bars. "
                "Confirm the requested window in branch.yaml, then rerun "
                "`abel-strategy-discovery prepare-branch`."
            )
        # Debug-safe starting point: a simple target-trend starter baseline.
        # It exists to make the first branch runnable and comparable, not to
        # pretend that discovery has already been translated into a real edge.
        slow_mean = close.rolling(window=40, min_periods=15).mean()
        next_position = (close > slow_mean).astype(float).fillna(0.0)
        if len(next_position) > 0:
            next_position.iloc[0] = 0.0
        return ctx.decisions(next_position)
'''


def main() -> int:
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
        "--backtest-start",
        default=DEFAULT_BACKTEST_START,
        help="Session-level backtest start date passed to causal-edge evaluate",
    )
    init_session.add_argument(
        "--discover",
        action="store_true",
        help="Run live Abel discovery and persist it into discovery.json",
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

    add_insight = sub.add_parser(
        "add-insight",
        help="Record a manual research insight for branch memory",
    )
    add_insight.add_argument("--branch", required=True)
    add_insight.add_argument(
        "--scope",
        default="branch",
        choices=["branch", "asset_scope", "cross_asset"],
    )
    add_insight.add_argument(
        "--kind",
        required=True,
        choices=["worked", "failed", "risk", "pattern", "next_idea"],
    )
    add_insight.add_argument("--text", required=True)
    add_insight.add_argument("--rule", default="")
    add_insight.add_argument(
        "--confidence",
        default="medium",
        choices=["low", "medium", "high"],
    )
    add_insight.add_argument("--round-id", default="")

    link_branches = sub.add_parser(
        "link-branches",
        help="Record a manual relation between two branches",
    )
    link_branches.add_argument("--from-branch", required=True)
    link_branches.add_argument("--to-branch", required=True)
    link_branches.add_argument(
        "--type",
        required=True,
        choices=[
            "derived_from",
            "alternative_to",
            "inspired_by",
            "candidate_compare",
            "final_compare",
        ],
    )
    link_branches.add_argument("--match-score", default="")
    link_branches.add_argument("--match-basis", default="")
    link_branches.add_argument(
        "--status",
        default="candidate",
        choices=["candidate", "selected", "rejected", "archived"],
    )
    link_branches.add_argument("--note", default="")

    init_branch = sub.add_parser("init-branch", help="Create a branch under a session")
    init_branch.add_argument("--session", required=True)
    init_branch.add_argument("--branch-id", required=True)

    prepare_branch = sub.add_parser(
        "prepare-branch",
        help="Resolve branch data dependencies and warm the edge cache before evaluation",
    )
    prepare_branch.add_argument("--branch", required=True)
    prepare_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run causal-edge warm-cache (defaults to the workspace python when available)",
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
        "--python-bin",
        default=None,
        help="Interpreter used to run causal-edge evaluate (defaults to the workspace python when available)",
    )
    run_branch.add_argument(
        "--allow-untouched-template",
        action="store_true",
        help="Allow recording a round from the untouched default engine scaffold",
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

    debug_branch = sub.add_parser(
        "debug-branch",
        help="Run edge debug-evaluate without recording a narrative round",
    )
    debug_branch.add_argument("--branch", required=True)
    debug_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run causal-edge debug-evaluate (defaults to the workspace python when available)",
    )

    render = sub.add_parser("render", help="Render summaries for a session")
    render.add_argument("--session", required=True)

    status = sub.add_parser("status", help="Print session status")
    status.add_argument("--session", required=True)

    check = sub.add_parser("check", help="Check narrative completeness")
    check.add_argument("--session", required=True)
    check.add_argument("--strict", action="store_true")

    args = parser.parse_args()

    if args.command == "workspace":
        return handle_workspace_command(args)
    if args.command == "env":
        return handle_env_command(args)
    if args.command == "doctor":
        return handle_doctor_command(args)
    if args.command == "init-session":
        session = init_session_dir(
            args.ticker,
            args.exp_id,
            resolve_session_root(args.root),
            discover=args.discover,
            discover_limit=args.discover_limit,
            backtest_start=args.backtest_start,
        )
        discovery = load_discovery(session)
        readiness = load_readiness(session)
        print(f"Created Abel strategy discovery session at {session}")
        print(f"  ticker: {discovery.get('ticker', args.ticker.upper())}")
        print(f"  discovery: {session / 'discovery.json'}")
        print(f"  events: {session / 'events.tsv'}")
        if readiness:
            print(f"  readiness: {session / READINESS_FILENAME}")
        if args.discover:
            print(
                f"  discovery_source: {discovery.get('source', 'unknown')} "
                f"(K={discovery.get('K_discovery', 0)})"
            )
            readiness_summary = format_data_readiness_summary(readiness)
            if readiness_summary:
                print(f"  data_readiness: {readiness_summary}")
            for line in readiness_recommendation_lines(readiness):
                print(f"  {line}")
            warning = build_readiness_warning(readiness)
            if warning:
                print(f"  warning: {warning}")
        else:
            print("  discovery_source: pending (live discovery not run)")
        print("")
        print("From here:")
        print(f"  abel-strategy-discovery init-branch --session {session} --branch-id graph-v1")
        return 0
    if args.command == "set-backtest-start":
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
        for line in readiness_recommendation_lines(readiness):
            print(f"  {line}")
        warning = build_readiness_warning(readiness)
        if warning:
            print(f"  warning: {warning}")
        print("")
        print("From here:")
        print(f"  abel-strategy-discovery status --session {session}")
        return 0
    if args.command == "set-hypothesis":
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
        print("")
        print("From here:")
        print(f"  abel-strategy-discovery debug-branch --branch {branch}")
        print(f"  abel-strategy-discovery run-branch --branch {branch} -d \"baseline\"")
        return 0
    if args.command == "add-insight":
        return record_manual_insight(args)
    if args.command == "link-branches":
        return record_branch_link(args)
    if args.command == "init-branch":
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
            for line in readiness_recommendation_lines(readiness):
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
        print("  branch.yaml is where target, start, drivers, and overlap become explicit.")
        print("  The generated engine is only a starter path check; it helps you verify the branch wiring before you encode a branch-specific mechanism.")
        print("  If you fetch bars, keep `limit=...` explicit and avoid blanket `dropna()` before confirming the target column survives.")
        print("")
        print("From here:")
        print(f"  edit {branch / BRANCH_SPEC_FILENAME}")
        print(f"  abel-strategy-discovery prepare-branch --branch {branch}")
        print(f"  abel-strategy-discovery debug-branch --branch {branch}")
        print(f"  abel-strategy-discovery run-branch --branch {branch} -d \"baseline\"")
        print(f"  edit {branch / 'engine.py'}")
        return 0
    if args.command == "prepare-branch":
        return prepare_branch_inputs(args)
    if args.command == "run-branch":
        return run_branch_round(args)
    if args.command == "promote-branch":
        return promote_branch_bundle(args)
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


def handle_workspace_command(args: argparse.Namespace) -> int:
    if args.workspace_command == "init":
        target_root = Path(args.path).expanduser()
        target_state, related_root = inspect_workspace_bootstrap_target(target_root)
        if target_state == "nested_workspace" and related_root is not None:
            print(
                "Refusing to create a nested Abel strategy discovery workspace at "
                f"{target_root.resolve()}"
            )
            print(f"Existing workspace root for this area: {related_root}")
            print("")
            print("Continue there instead:")
            print(f"  abel-strategy-discovery workspace status --path {related_root}")
            print(f"  abel-strategy-discovery doctor --path {related_root}")
            return 1
        if target_state == "launch_root_child_workspace" and related_root is not None:
            print(f"Workspace already exists at the default child path: {related_root}")
            print("Reuse it instead of creating another workspace for the same area.")
            print("")
            print("Continue there instead:")
            print(f"  abel-strategy-discovery workspace status --path {related_root}")
            print(f"  abel-strategy-discovery doctor --path {related_root}")
            return 1
        root = scaffold_workspace(args.name, target_root=target_root)
        manifest = build_default_manifest(args.name)
        resolved = resolve_workspace_paths(root, manifest)
        print(f"Created Abel strategy discovery workspace at {root}")
        print(f"  manifest: {root / 'alpha.workspace.yaml'}")
        print(f"  research: {resolved['research_root']}")
        print(f"  docs: {resolved['docs_root']}")
        print(
            "  planned_workspace_python: "
            f"{resolved['venv'] / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')}"
        )
        print("")
        print("Boundary:")
        print("  This workspace is for alpha-managed branch research.")
        print("  Keep research artifacts under `research/`.")
        print("  If you need a standalone Abel-edge project, create it outside this workspace.")
        print("")
        print("From here:")
        print(f"  cd {root}")
        print("  abel-strategy-discovery workspace status")
        print(f"  abel-strategy-discovery workspace bootstrap --path {root}")
        return 0
    if args.workspace_command == "bootstrap":
        target_root = Path(args.path).expanduser().resolve()
        target_state, related_root = inspect_workspace_bootstrap_target(target_root)
        if target_state == "nested_workspace" and related_root is not None:
            print(
                "Refusing to bootstrap a nested Abel strategy discovery workspace at "
                f"{target_root}"
            )
            print(f"Existing workspace root for this area: {related_root}")
            print("")
            print("Continue there instead:")
            print(f"  abel-strategy-discovery workspace status --path {related_root}")
            print(f"  abel-strategy-discovery doctor --path {related_root}")
            return 1
        if target_state == "launch_root_child_workspace" and related_root is not None:
            print(f"Workspace already exists at the default child path: {related_root}")
            print("Reuse it instead of bootstrapping another workspace for the same area.")
            print("")
            print("Continue there instead:")
            print(f"  abel-strategy-discovery workspace status --path {related_root}")
            print(f"  abel-strategy-discovery doctor --path {related_root}")
            return 1
        reused_workspace = False
        if target_root.exists():
            if not is_workspace_root(target_root):
                if target_root.is_dir() and not any(target_root.iterdir()):
                    root = scaffold_workspace(
                        args.name,
                        target_root=target_root,
                        allow_existing_empty=True,
                    )
                else:
                    print(
                        "Cannot bootstrap into an existing non-workspace directory: "
                        f"{target_root}"
                    )
                    print(
                        "Choose an empty path or an existing Abel strategy discovery workspace root."
                    )
                    return 1
            else:
                root = target_root
                reused_workspace = True
        else:
            root = scaffold_workspace(args.name, target_root=target_root)

        manifest = load_workspace_manifest(root)
        resolved = resolve_workspace_paths(root, manifest)
        env_result = init_workspace_env(
            start=root,
            base_python=args.base_python,
            alpha_source=args.alpha_source,
            edge_spec=args.edge_spec,
            edge_source=args.edge_source,
            runtime_python=args.runtime_python,
            alpha_editable=not args.no_editable,
        )
        doctor_result = run_doctor(root)

        print(
            ("Reusing" if reused_workspace else "Created")
            + f" Abel strategy discovery workspace at {root}"
        )
        print(f"  manifest: {root / 'alpha.workspace.yaml'}")
        print(f"  canonical_runtime_python: {env_result.python_path}")
        print(f"  activation: {default_activate_command()}")
        print(f"  runtime_mode: {env_result.runtime_mode}")
        print(f"  venv_provider: {env_result.venv_provider}")
        print(f"  edge_install_mode: {env_result.edge_install_mode}")
        print(f"  edge_install_target: {env_result.edge_install_target}")
        print(f"  alpha_install_mode: {'editable' if env_result.alpha_editable else 'regular'}")
        print(
            "  workspace_reuse: "
            + ("reused_existing_root" if reused_workspace else "created_new_root")
        )
        print(f"  research: {resolved['research_root']}")
        print(f"  docs: {resolved['docs_root']}")
        print("")
        print(render_doctor_report(doctor_result))
        print("")
        print("From here:")
        if doctor_exit_code(doctor_result) == 0:
            print(f"  cd {root}")
            print(f"  {default_activate_command()}")
            print("  abel-strategy-discovery init-session --ticker <TICKER> --exp-id <session-id>")
        else:
            print(f"  cd {root}")
            next_step = str(doctor_result.get("next_step") or "").strip()
            if next_step:
                print(f"  {next_step}")
        return doctor_exit_code(doctor_result)
    if args.workspace_command == "status":
        start = Path(args.path).expanduser().resolve()
        root, resolution_mode = resolve_workspace_entry(start)
        if root is None:
            print(f"No Abel strategy discovery workspace found from entry path {start}")
            print(f"Default workspace path for this launch root: {default_workspace_path(start)}")
            return 1
        manifest = load_workspace_manifest(root)
        if resolution_mode == "launch_root_child":
            print(f"Reusing default workspace under launch root: {root}")
            print("")
        elif resolution_mode == "workspace_ancestor":
            print(f"Continuing from workspace containing {start}: {root}")
            print("")
        print(render_workspace_status(root, manifest))
        return 0
    return 1


def handle_env_command(args: argparse.Namespace) -> int:
    if args.env_command != "init":
        return 1
    result = init_workspace_env(
        start=Path(args.path).expanduser(),
        base_python=args.base_python,
        alpha_source=args.alpha_source,
        edge_spec=args.edge_spec,
        edge_source=args.edge_source,
        runtime_python=args.runtime_python,
        alpha_editable=not args.no_editable,
    )
    print(f"Workspace environment ready at {result.workspace_root}")
    print(f"  venv: {result.venv_path}")
    print(f"  python: {result.python_path}")
    print(f"  alpha_source: {result.alpha_source}")
    print(f"  runtime_mode: {result.runtime_mode}")
    print(f"  venv_provider: {result.venv_provider}")
    print(f"  edge_install_mode: {result.edge_install_mode}")
    print(f"  edge_install_target: {result.edge_install_target}")
    print(f"  alpha_install_mode: {'editable' if result.alpha_editable else 'regular'}")
    print("  alpha_install_reason: installs the packaged abel-strategy-discovery CLI into this workspace runtime")
    print("  canonical_runtime_note: use this workspace runtime as the canonical environment for daily research work")
    if result.runtime_mode == "existing_python":
        print("  runtime_override_note: using an existing interpreter instead of creating the workspace .venv")
    if result.edge_discovery_payload_capable is not None:
        print(f"  edge_discovery_payload: {'yes' if result.edge_discovery_payload_capable else 'no'}")
    if result.edge_context_json_capable is not None:
        print(f"  edge_context_json: {'yes' if result.edge_context_json_capable else 'no'}")
    print("")
    if result.edge_discovery_payload_capable is False or result.edge_context_json_capable is False:
        print("Warning:")
        print("  Installed Abel-edge is missing required alpha contracts.")
        print("  Run `abel-strategy-discovery doctor` and upgrade the workspace runtime before starting research.")
        print("")
    print("From here:")
    print("  abel-strategy-discovery doctor")
    print(f"  {default_activate_command()}")
    print("  # once doctor is ready: init-session -> init-branch -> edit branch.yaml -> prepare-branch")
    return 0


def handle_doctor_command(args: argparse.Namespace) -> int:
    result = run_doctor(Path(args.path).expanduser())
    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(render_doctor_report(result))
    return doctor_exit_code(result)


def resolve_session_root(root_arg: str | None) -> Path:
    """Resolve the session root from an explicit argument or current workspace."""
    if root_arg:
        return resolve_workspace_arg_path(root_arg)
    workspace_root, _ = resolve_workspace_entry()
    if workspace_root is not None:
        manifest = load_workspace_manifest(workspace_root)
        return resolve_workspace_paths(workspace_root, manifest)["research_root"]
    return Path("research")


def resolve_workspace_arg_path(value: str) -> Path:
    """Resolve a CLI path argument relative to the current workspace when possible."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    workspace_root, _ = resolve_workspace_entry()
    if workspace_root is not None:
        return workspace_root / path
    return path


def resolve_default_python_bin(branch: Path) -> str:
    """Resolve the interpreter used for edge evaluation."""
    workspace_root = find_workspace_root(branch)
    if workspace_root is not None:
        manifest = load_workspace_manifest(workspace_root)
        python_path = resolve_runtime_python(workspace_root, manifest)
        if python_path.exists():
            return str(python_path)
    return sys.executable


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
    discovery_data = None
    readiness_report = None
    if discover:
        discovery_data = fetch_live_discovery(ticker, limit=discover_limit)
        discovery_data["backtest"] = {"start": backtest_start}
        readiness_report = refresh_data_readiness(
            session=session,
            discovery_data=discovery_data,
            backtest_start=backtest_start,
        )
    with SessionLock(session):
        write_tsv_header(session / "events.tsv", EVENTS_HEADER)
        if not session_state_path(session).exists():
            write_session_state(session, {})
        discovery_path = session / "discovery.json"
        if discovery_data is not None:
            write_discovery(session, discovery_data)
        elif not discovery_path.exists():
            write_discovery(
                session,
                {
                    "ticker": ticker.upper(),
                    "source": "pending",
                    "parents": [],
                    "blanket_new": [],
                    "children": [],
                    "K_discovery": 0,
                    "backtest": {"start": backtest_start},
                    "created_at": _now(),
                },
            )
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
        if discovery_data is not None:
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
                    "artifact_path": str(discovery_path.relative_to(session)),
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
        from causal_edge.plugins.abel.credentials import (
            MissingAbelApiKeyError,
            require_api_key,
        )
        from causal_edge.plugins.abel.discover import discover_graph_payload
    except ImportError as exc:
        raise RuntimeError(
            "Live Abel discovery requires causal-edge with the Abel plugin installed. "
            "Create a virtual environment, install causal-edge, then retry."
        ) from exc
    workspace_root, _ = resolve_workspace_entry()
    if workspace_root is not None:
        auth_env = resolve_runtime_auth_env_file(workspace_root)
        if auth_env is not None:
            os.environ.setdefault("ABEL_AUTH_ENV_FILE", str(auth_env))

    try:
        require_api_key()
    except MissingAbelApiKeyError as exc:
        raise RuntimeError(
            "init-session live graph discovery is blocked on Abel auth. "
            "No reusable auth was found. "
            f"{build_auth_recovery_instruction(workspace_root or Path.cwd())}\n\n"
            "After auth is ready, retry `abel-strategy-discovery init-session --ticker "
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


def run_edge_verify_data(
    *,
    session: Path,
    discovery_path: Path,
    backtest_start: str,
) -> dict | None:
    """Run edge verify-data against a discovery payload and parse the structured report."""
    python_bin = resolve_default_python_bin(session)
    workspace_root = find_workspace_root(session)
    runtime_env = (
        build_workspace_runtime_env(workspace_root)
        if workspace_root is not None
        else None
    )
    fd, temp_name = tempfile.mkstemp(suffix="-verify-data.json")
    os.close(fd)
    output_path = Path(temp_name)
    output_path.unlink(missing_ok=True)
    command = [
        python_bin,
        "-m",
        "causal_edge.cli",
        "verify-data",
        "--discovery-json",
        str(discovery_path),
        "--start",
        backtest_start,
        "--output-json",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=runtime_env,
    )
    if not output_path.exists():
        if "No module named" in (completed.stderr or "") or "No such command" in (
            completed.stderr or completed.stdout or ""
        ):
            return None
        raise RuntimeError(
            "Abel-edge verify-data did not produce a readiness report. "
            "Upgrade the workspace runtime before depending on discovery readiness."
        )
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    finally:
        output_path.unlink(missing_ok=True)


def init_branch_dir(session: Path, branch_id: str) -> Path:
    with SessionLock(session):
        discovery = load_discovery(session)
        readiness = load_readiness(session)
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


def record_manual_insight(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    branches = load_branches(session)
    branch_rows = next(
        (item["rows"] for item in branches if item["branch_id"] == branch.name),
        [],
    )
    round_id = str(args.round_id or "").strip()
    if not round_id and branch_rows:
        round_id = branch_rows[-1].get("round_id", "")
    with SessionLock(session):
        manual_rows = load_manual_memory_rows(
            session / MEMORY_INSIGHTS_FILENAME,
            MEMORY_INSIGHTS_HEADER,
        )
        manual_rows.append(
            {
                "insight_id": next_manual_memory_id(manual_rows, prefix="ins-manual"),
                "scope": args.scope,
                "branch_id": branch.name,
                "round_id": round_id,
                "kind": args.kind,
                "statement": str(args.text or "").strip(),
                "reusable_rule": str(args.rule or "").strip(),
                "confidence": args.confidence,
                "origin": "manual",
            }
        )
        write_tsv_rows(
            session / MEMORY_INSIGHTS_FILENAME,
            MEMORY_INSIGHTS_HEADER,
            manual_rows,
        )
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "memory_insight_added",
                "branch_id": branch.name,
                "round_id": round_id,
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": str(args.text or "").strip(),
                "artifact_path": MEMORY_INSIGHTS_FILENAME,
            },
        )
        render_session(session)
    print(f"Recorded manual insight for {branch.name}")
    print(f"  kind: {args.kind}")
    print(f"  round_id: {round_id or 'not linked'}")
    print(f"  text: {str(args.text or '').strip()}")
    return 0


def record_branch_link(args: argparse.Namespace) -> int:
    from_branch = resolve_workspace_arg_path(args.from_branch).resolve()
    to_branch = resolve_workspace_arg_path(args.to_branch).resolve()
    from_session = from_branch.parent.parent
    to_session = to_branch.parent.parent
    if from_session != to_session:
        raise RuntimeError("Branch links must stay within the same session.")
    session = from_session
    with SessionLock(session):
        manual_rows = load_manual_memory_rows(
            session / MEMORY_LINKS_FILENAME,
            MEMORY_LINKS_HEADER,
        )
        manual_rows.append(
            {
                "link_id": next_manual_memory_id(manual_rows, prefix="link-manual"),
                "from_branch_id": from_branch.name,
                "to_branch_id": to_branch.name,
                "link_type": args.type,
                "match_score": str(args.match_score or "").strip(),
                "match_basis": str(args.match_basis or "").strip(),
                "status": args.status,
                "note": str(args.note or "").strip(),
                "origin": "manual",
            }
        )
        write_tsv_rows(
            session / MEMORY_LINKS_FILENAME,
            MEMORY_LINKS_HEADER,
            manual_rows,
        )
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "memory_link_added",
                "branch_id": from_branch.name,
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": (
                    f"{args.type} -> {to_branch.name}"
                    + (
                        f" ({str(args.match_basis or '').strip()})"
                        if str(args.match_basis or "").strip()
                        else ""
                    )
                ),
                "artifact_path": MEMORY_LINKS_FILENAME,
            },
        )
        render_session(session)
    print(f"Recorded branch link: {from_branch.name} -> {to_branch.name}")
    print(f"  type: {args.type}")
    print(f"  status: {args.status}")
    return 0


def prepare_branch_inputs(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    workspace_root = find_workspace_root(branch)
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    branch_spec = load_branch_spec(branch)
    if not branch_spec:
        raise RuntimeError(f"Missing {BRANCH_SPEC_FILENAME} under {branch}")

    target = str(branch_spec.get("target") or discovery.get("ticker") or "").strip().upper()
    if not target:
        raise RuntimeError("Branch spec is missing a target ticker.")
    selected_drivers = [
        str(item).strip().upper()
        for item in (branch_spec.get("selected_drivers") or [])
        if str(item).strip()
    ]
    symbols = [target]
    for ticker in selected_drivers:
        if ticker not in symbols:
            symbols.append(ticker)

    requested_start = str(
        branch_spec.get("requested_start") or _get_backtest_start(discovery)
    ).strip()
    advisory_lines = branch_runtime_advisory_lines(
        branch_requested_start=requested_start,
        discovery=discovery,
        readiness=readiness,
    )
    dependencies = branch_dependencies_payload(
        branch=branch,
        branch_spec=branch_spec,
        target=target,
        selected_drivers=selected_drivers,
        requested_start=requested_start,
    )

    python_bin = args.python_bin or resolve_default_python_bin(branch)
    output_path = dependencies_path(branch)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_env = (
        build_workspace_runtime_env(workspace_root)
        if workspace_root is not None
        else None
    )
    command = [
        python_bin,
        "-m",
        "causal_edge.cli",
        "warm-cache",
        "--adapter",
        "abel",
        "--start",
        requested_start,
        "--timeframe",
        str((branch_spec.get("data_requirements") or {}).get("timeframe") or "1d"),
        "--limit",
        str(args.cache_limit),
        "--output-json",
        str(output_path),
    ]
    for symbol in symbols:
        command.extend(["--symbol", symbol])
    completed = subprocess.run(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=runtime_env,
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    if not output_path.exists():
        if completed.stdout:
            sys.stderr.write(completed.stdout)
        runtime_error_text = (completed.stderr or completed.stdout or "").strip()
        if "Abel API key not found" in runtime_error_text:
            raise RuntimeError(
                "Branch preparation is blocked on Abel auth. "
                "Use abel-auth, then rerun "
                f"`abel-strategy-discovery prepare-branch --branch {branch}`."
            )
        raise RuntimeError(
            "Abel-edge warm-cache did not produce dependencies output. "
            "Fix the runtime error above before continuing."
        )
    cache_payload = json.loads(output_path.read_text(encoding="utf-8"))
    dependencies["cache"] = cache_payload
    output_path.write_text(json.dumps(dependencies, indent=2), encoding="utf-8")
    runtime_profile = build_runtime_profile_payload(target=target)
    execution_constraints = build_execution_constraints_payload(branch_spec)
    data_manifest = build_data_manifest_payload(
        target=target,
        selected_drivers=selected_drivers,
        cache_payload=cache_payload,
        readiness=readiness,
    )
    probe_samples = build_probe_samples_payload(
        target=target,
        requested_start=requested_start,
        data_manifest=data_manifest,
    )
    runtime_profile_path(branch).write_text(
        json.dumps(runtime_profile, indent=2),
        encoding="utf-8",
    )
    execution_constraints_path(branch).write_text(
        json.dumps(execution_constraints, indent=2),
        encoding="utf-8",
    )
    data_manifest_path(branch).write_text(
        json.dumps(data_manifest, indent=2),
        encoding="utf-8",
    )
    probe_samples_path(branch).write_text(
        json.dumps(probe_samples, indent=2),
        encoding="utf-8",
    )
    context_guide_path(branch).write_text(
        build_context_guide_markdown(
            target=target,
            runtime_profile=runtime_profile,
            execution_constraints=execution_constraints,
            data_manifest=data_manifest,
        ),
        encoding="utf-8",
    )

    with SessionLock(session):
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "branch_prepared",
                "branch_id": branch.name,
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": (
                    f"Prepared branch inputs for {branch.name} with {len(symbols)} symbol(s)"
                ),
                "artifact_path": str(output_path.relative_to(session)),
            },
        )
        render_session(session)
    cache_results = [
        item for item in (cache_payload.get("results") or []) if isinstance(item, dict)
    ]
    warm_ok = [item for item in cache_results if item.get("ok")]
    warm_fail = [item for item in cache_results if not item.get("ok")]
    auth_handoff_needed = any(
        "Abel API key not found" in str(item.get("error") or "")
        for item in warm_fail
    )
    print(f"Prepared branch inputs: {output_path.relative_to(session)}")
    print(f"  runtime_profile: {runtime_profile_path(branch).relative_to(session)}")
    print(f"  execution_constraints: {execution_constraints_path(branch).relative_to(session)}")
    print(f"  data_manifest: {data_manifest_path(branch).relative_to(session)}")
    print(f"  context_guide: {context_guide_path(branch).relative_to(session)}")
    print(f"  probe_samples: {probe_samples_path(branch).relative_to(session)}")
    print(f"  target: {target}")
    print(f"  selected_drivers: {len(selected_drivers)}")
    print(f"  symbols: {', '.join(symbols)}")
    print(f"  cache_results: ok={len(warm_ok)} fail={len(warm_fail)}")
    for line in advisory_lines:
        print(f"  {line}")
    if warm_fail:
        for item in warm_fail[:5]:
            print(
                f"  cache_failure: {item.get('symbol', 'unknown')} -> {item.get('error', 'unknown')}"
            )
    render_section(
        "Prepared branch state",
        branch_context_summary_lines(
            branch=branch,
            session=session,
            discovery=discovery,
            readiness=readiness,
        ),
    )
    print("")
    print("From here:")
    if auth_handoff_needed:
        print("  Use abel-auth")
        print(f"  abel-strategy-discovery prepare-branch --branch {branch}")
    else:
        print("  The branch inputs are ready; use debug preflight first, then record a round once the engine reflects the branch thesis.")
        print(f"  abel-strategy-discovery debug-branch --branch {branch}")
        print(f"  abel-strategy-discovery run-branch --branch {branch} -d \"baseline\"")
    return completed.returncode


def branch_requested_start(branch: Path, discovery: dict) -> str:
    branch_spec = load_branch_spec(branch)
    requested = str(branch_spec.get("requested_start") or "").strip()
    if requested:
        return requested
    return _get_backtest_start(discovery)


def promote_branch_bundle(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    rows = read_tsv_rows(branch / "results.tsv")
    latest = rows[-1] if rows else {}
    branch_spec = load_branch_spec(branch)
    if not branch_spec:
        raise RuntimeError(f"Missing {BRANCH_SPEC_FILENAME} under {branch}")
    if args.output_dir:
        destination = resolve_workspace_arg_path(args.output_dir).resolve()
    else:
        destination = session / "promotions" / branch.name
    destination.mkdir(parents=True, exist_ok=True)

    shutil.copy2(branch / "engine.py", destination / "engine.py")
    shutil.copy2(branch_spec_path(branch), destination / BRANCH_SPEC_FILENAME)
    if branch_inputs_ready(branch):
        shutil.copy2(dependencies_path(branch), destination / DEPENDENCIES_FILENAME)
        shutil.copy2(runtime_profile_path(branch), destination / RUNTIME_PROFILE_FILENAME)
        shutil.copy2(execution_constraints_path(branch), destination / EXECUTION_CONSTRAINTS_FILENAME)
        shutil.copy2(data_manifest_path(branch), destination / DATA_MANIFEST_FILENAME)
        shutil.copy2(context_guide_path(branch), destination / CONTEXT_GUIDE_FILENAME)
        shutil.copy2(probe_samples_path(branch), destination / PROBE_SAMPLES_FILENAME)

    bundle_readme = build_promotion_bundle_readme(
        branch=branch,
        branch_spec=branch_spec,
        latest=latest,
    )
    (destination / "PROMOTION.md").write_text(bundle_readme, encoding="utf-8")

    with SessionLock(session):
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "branch_promoted",
                "branch_id": branch.name,
                "round_id": latest.get("round_id", ""),
                "mode": latest.get("mode", ""),
                "verdict": latest.get("verdict", ""),
                "decision": latest.get("decision", ""),
                "description": f"Created promotion bundle for {branch.name}",
                "artifact_path": str(destination.relative_to(session)),
            },
        )
        render_session(session)
    print(f"Promotion bundle: {destination}")
    print("")
    print("Included:")
    print(f"  {destination / 'engine.py'}")
    print(f"  {destination / BRANCH_SPEC_FILENAME}")
    if (destination / DEPENDENCIES_FILENAME).exists():
        print(f"  {destination / DEPENDENCIES_FILENAME}")
        print(f"  {destination / RUNTIME_PROFILE_FILENAME}")
        print(f"  {destination / EXECUTION_CONSTRAINTS_FILENAME}")
        print(f"  {destination / DATA_MANIFEST_FILENAME}")
        print(f"  {destination / CONTEXT_GUIDE_FILENAME}")
        print(f"  {destination / PROBE_SAMPLES_FILENAME}")
    print(f"  {destination / 'PROMOTION.md'}")
    return 0


def run_branch_round(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    workspace_root = find_workspace_root(branch)
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    if not branch_inputs_ready(branch):
        print(
            "Branch inputs have not been prepared yet. "
            "Run `abel-strategy-discovery prepare-branch --branch ...` before recording a round.",
            file=sys.stderr,
        )
        return 2
    backtest_start = branch_requested_start(branch, discovery)
    advisory_lines = branch_runtime_advisory_lines(
        branch_requested_start=backtest_start,
        discovery=discovery,
        readiness=readiness,
    )
    warning = build_readiness_warning(readiness)
    if branch_uses_default_scaffold(branch, discovery, readiness, session) and not args.allow_untouched_template:
        print(
            "The branch is still using the untouched starter scaffold. "
            "That starter path is useful for checking wiring, but round-001 should reflect a branch-specific mechanism.",
            file=sys.stderr,
        )
        print(
            "Interpretation: workflow_boundary -> the branch is ready for a mechanism decision, not another setup step.",
            file=sys.stderr,
        )
        for line in advisory_lines:
            print(f"Runtime context: {line}", file=sys.stderr)
        for line in branch_context_summary_lines(
            branch=branch,
            session=session,
            discovery=discovery,
            readiness=readiness,
        ):
            print(f"Branch context: {line}", file=sys.stderr)
        if warning and backtest_start == _get_backtest_start(discovery):
            print(f"Readiness warning: {warning}", file=sys.stderr)
        for line in readiness_recommendation_lines(readiness):
            print(f"Coverage hint: {line}", file=sys.stderr)
        return 2
    rows = read_tsv_rows(branch / "results.tsv")
    round_id = f"round-{len(rows) + 1:03d}"
    effective_hypothesis, hypothesis_source = resolve_branch_hypothesis(
        branch,
        rows,
        args.hypothesis,
    )
    result_path = branch / "outputs" / f"{round_id}-edge-result.json"
    report_path = branch / "outputs" / f"{round_id}-edge-validation.md"
    handoff_path = branch / "outputs" / f"{round_id}-edge-handoff.json"
    context_path = branch / "outputs" / f"{round_id}-alpha-context.json"
    context_path.write_text(
        json.dumps(
            build_branch_context(
                branch=branch,
                session=session,
                discovery=discovery,
                readiness=readiness,
                round_id=round_id,
                backtest_start=backtest_start,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    emit_readiness_warning = False
    session_start = _get_backtest_start(discovery)
    if warning and backtest_start == session_start:
        with SessionLock(session):
            emit_readiness_warning = should_emit_readiness_warning(session, readiness)
    for line in advisory_lines:
        print(f"Runtime context: {line}", file=sys.stderr)
    if warning and emit_readiness_warning:
        print(
            f"Warning: {warning}",
            file=sys.stderr,
        )
        for line in readiness_recommendation_lines(readiness):
            print(f"Coverage hint: {line}", file=sys.stderr)

    python_bin = args.python_bin or resolve_default_python_bin(branch)
    command = [
        python_bin,
        "-m",
        "causal_edge.cli",
        "evaluate",
        "--workdir",
        str(branch),
        "--output-json",
        str(result_path),
        "--output-md",
        str(report_path),
        "--output-handoff",
        str(handoff_path),
        "--start",
        backtest_start,
        "--context-json",
        str(context_path),
    ]
    runtime_env = (
        build_workspace_runtime_env(workspace_root)
        if workspace_root is not None
        else None
    )
    completed = subprocess.run(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=runtime_env,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if not result_path.exists():
        print(
            "Abel-edge did not produce the expected result JSON. "
            "Check the command output above and rerun after fixing the evaluation error.",
            file=sys.stderr,
        )
        if workspace_root is not None:
            print(
                f"Alpha expected workspace auth at {resolve_workspace_env_file(workspace_root)} "
                "and exported it through ABEL_AUTH_ENV_FILE for this run.",
                file=sys.stderr,
            )
        return completed.returncode or 1
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"Abel-edge wrote an unreadable result JSON at {result_path}: {exc}",
            file=sys.stderr,
        )
        return completed.returncode or 1
    emit_missing_hypothesis_warning = False
    if not has_explicit_hypothesis(effective_hypothesis):
        with SessionLock(session):
            emit_missing_hypothesis_warning = should_emit_missing_hypothesis_warning(branch)
    if emit_missing_hypothesis_warning:
        print(
            "Warning: recording a round without an explicit hypothesis. "
            "State the causal claim, expected sign, and invalidation condition before the next round.",
            file=sys.stderr,
        )
    decision = alpha_decision(rows, result, session=session)

    round_note = branch / "rounds" / f"{round_id}.md"
    round_note.write_text(
        render_round_note(
            ticker=discovery.get("ticker", session.parent.name.upper()),
            exp_id=session.name,
            branch_id=branch.name,
            round_id=round_id,
            mode=args.mode,
            decision=decision,
            description=args.description,
            result=result,
            backtest_start=backtest_start,
            input_note=args.input_note,
            hypothesis=effective_hypothesis,
            expected_signal=args.expected_signal,
            trigger=args.trigger,
            change_summary=args.change_summary,
            time_spent_min=args.time_spent_min,
            summary=args.summary,
            next_step=args.next_step,
            actions=args.action + [f"hypothesis_source={hypothesis_source}"],
            context_mode="injected",
            context_path=str(context_path.relative_to(session)),
            result_path=str(result_path.relative_to(session)),
            report_path=str(report_path.relative_to(session)),
            handoff_path=str(handoff_path.relative_to(session)),
        ),
        encoding="utf-8",
    )

    metrics = result.get("metrics", {})
    with SessionLock(session):
        if has_explicit_hypothesis(effective_hypothesis):
            persist_branch_hypothesis(
                branch,
                effective_hypothesis,
                source=hypothesis_source,
            )
        append_tsv_row(
            branch / "results.tsv",
            RESULTS_HEADER,
            {
                "exp_id": session.name,
                "ticker": discovery.get("ticker", session.parent.name.upper()),
                "branch_id": branch.name,
                "round_id": round_id,
                "decision": decision,
                "lo_adj": f"{metrics.get('lo_adjusted', 0):.3f}",
                "ic": f"{metrics.get('position_ic', 0):.4f}",
                "omega": f"{metrics.get('omega', 0):.3f}",
                "sharpe": f"{metrics.get('sharpe', 0):.3f}",
                "max_dd": f"{metrics.get('max_dd', 0):.4f}",
                "pnl": f"{metrics.get('total_return', 0) * 100:.1f}",
                "K": str(result.get("K", "?")),
                "score": result.get("score", "?/?"),
                "verdict": result.get("verdict", "ERROR"),
                "mode": args.mode,
                "description": args.description,
                "result_path": str(result_path.relative_to(session)),
                "report_path": str(report_path.relative_to(session)),
                "handoff_path": str(handoff_path.relative_to(session)),
            },
        )
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "round_recorded",
                "branch_id": branch.name,
                "round_id": round_id,
                "mode": args.mode,
                "verdict": result.get("verdict", "ERROR"),
                "decision": decision,
                "description": args.description,
                "artifact_path": str(result_path.relative_to(session)),
            },
        )
        render_session(session)
    print(f"Alpha context: {context_path.relative_to(session)}")
    print(f"Edge result: {result_path.relative_to(session)}")
    print(f"Edge validation: {report_path.relative_to(session)}")
    print(f"Edge handoff: {handoff_path.relative_to(session)}")
    semantic = result.get("semantic") or {}
    if isinstance(semantic, dict) and semantic:
        render_section(
            "Semantic",
            [
                f"semantic_verdict={semantic.get('verdict', 'unknown')}",
                f"decision_count={semantic.get('decision_count', 0)}",
                f"read_count={semantic.get('read_count', 0)}",
                f"output_shape={((semantic.get('output_shape') or {}).get('label', 'unknown'))}",
            ],
        )
    frame_key, frame_text = classify_result_frame(result)
    render_section(
        "Interpretation",
        [
            f"result_class={frame_key}",
            frame_text,
        ],
    )
    return 0


def debug_branch_run(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    workspace_root = find_workspace_root(branch)
    backtest_start = branch_requested_start(branch, discovery)
    advisory_lines = branch_runtime_advisory_lines(
        branch_requested_start=backtest_start,
        discovery=discovery,
        readiness=readiness,
    )
    context_path = branch / "outputs" / "debug-alpha-context.json"
    debug_result_path = branch / "outputs" / "debug-edge-result.json"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(
        json.dumps(
            build_branch_context(
                branch=branch,
                session=session,
                discovery=discovery,
                readiness=readiness,
                round_id="debug",
                backtest_start=backtest_start,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    python_bin = args.python_bin or resolve_default_python_bin(branch)
    command = [
        python_bin,
        "-m",
        "causal_edge.cli",
        "debug-evaluate",
        "--workdir",
        str(branch),
        "--start",
        backtest_start,
        "--context-json",
        str(context_path),
        "--output-json",
        str(debug_result_path),
    ]
    runtime_env = (
        build_workspace_runtime_env(workspace_root)
        if workspace_root is not None
        else None
    )
    completed = subprocess.run(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=runtime_env,
    )
    debug_snapshot = build_debug_snapshot(
        completed=completed,
        session=session,
        context_path=context_path,
        debug_result_path=debug_result_path,
        backtest_start=backtest_start,
    )
    with SessionLock(session):
        persist_debug_snapshot(branch, debug_snapshot)
        render_session(session)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    for line in advisory_lines:
        print(f"Runtime context: {line}")
    if debug_result_path.exists():
        try:
            debug_result = json.loads(debug_result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            debug_result = {}
        if isinstance(debug_result, dict) and debug_result:
            semantic = debug_result.get("semantic") or {}
            if isinstance(semantic, dict) and semantic:
                render_section(
                    "Preflight",
                    [
                        f"semantic_verdict={semantic.get('verdict', 'unknown')}",
                        f"decision_count={semantic.get('decision_count', 0)}",
                        f"read_count={semantic.get('read_count', 0)}",
                        f"output_shape={((semantic.get('output_shape') or {}).get('label', 'unknown'))}",
                    ],
                )
            frame_key, frame_text = classify_result_frame(debug_result)
            render_section(
                "Interpretation",
                [
                    f"result_class={frame_key}",
                    frame_text,
                ],
            )
    print(f"Debug context: {context_path.relative_to(session)}")
    if debug_result_path.exists():
        print(f"Debug result: {debug_result_path.relative_to(session)}")
    print("No narrative round was recorded.")
    return completed.returncode


def render_session(session: Path) -> None:
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    branches = load_branches(session)
    memory_snapshot = render_memory_snapshot(session, discovery, readiness, branches)
    for branch in branches:
        render_branch(branch, discovery, readiness, session.name, memory_snapshot)
    session_readme = build_session_readme(session, discovery, readiness, branches)
    (session / "README.md").write_text(session_readme, encoding="utf-8")


def render_branch(
    branch: dict,
    discovery: dict,
    readiness: dict,
    exp_id: str,
    memory_snapshot: dict,
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
    (branch_dir / "memory.md").write_text(
        build_memory(branch, discovery, memory_snapshot), encoding="utf-8"
    )
    (branch_dir / "thesis.md").write_text(
        build_thesis(branch, discovery, readiness), encoding="utf-8"
    )


def print_status(session: Path) -> None:
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    branches = load_branches(session)
    memory_branches = read_tsv_rows(session / MEMORY_BRANCHES_FILENAME)
    insights = read_tsv_rows(session / MEMORY_INSIGHTS_FILENAME)
    links = read_tsv_rows(session / MEMORY_LINKS_FILENAME)
    print(
        f"Session: {session.name} ({discovery.get('ticker', session.parent.name.upper())})"
    )
    print(f"Branches: {len(branches)}")
    print(f"Total rounds: {sum(len(branch['rows']) for branch in branches)}")
    print(
        f"Memory: {len(memory_branches)} branches, {len(insights)} insights, {len(links)} links"
    )
    readiness_summary = format_data_readiness_summary(readiness)
    if readiness_summary:
        print(f"Discovery readiness: {readiness_summary}")
        warning = build_readiness_warning(readiness)
        if warning:
            print(f"Readiness warning: {warning}")
        for line in readiness_recommendation_lines(readiness):
            print(f"Coverage hint: {line}")
    leader = select_leader(branches)
    if leader and leader["rows"]:
        latest = leader["rows"][-1]
        latest_note = read_round_note(leader["branch_dir"], latest.get("round_id", ""))
        print(
            "Lead: "
            f"{leader['branch_id']} {latest.get('decision', 'pending')} {latest.get('verdict', 'n/a')} "
            f"{latest.get('score', '?/?')} {latest_note.get('failure_signature', 'unknown')} "
            f"active={latest_note.get('signal_activity', 'n/a')}"
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
            f"hypothesis={'yes' if has_explicit_hypothesis(branch_hypothesis) else 'no'}"
        )


def check_session(session: Path, *, strict: bool) -> int:
    failures: list[str] = []
    if not (session / "events.tsv").exists():
        failures.append("Missing events.tsv")
    if not (session / "README.md").exists():
        failures.append("Missing session README.md")
    for required in (
        MEMORY_MANIFEST_FILENAME,
        MEMORY_BRANCHES_FILENAME,
        MEMORY_ROUNDS_FILENAME,
        MEMORY_VALIDATIONS_FILENAME,
        MEMORY_INSIGHTS_FILENAME,
        MEMORY_LINKS_FILENAME,
        f"{MEMORY_VIEWS_DIRNAME}/{MEMORY_OVERVIEW_FILENAME}",
        f"{MEMORY_VIEWS_DIRNAME}/{MEMORY_COMPARE_FILENAME}",
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
            "memory.md",
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
            if strict:
                validate_edge_handoff(session, branch_dir.name, row, failures)
        if strict:
            for text_path in (
                branch_dir / "README.md",
                branch_dir / "thesis.md",
                branch_dir / "memory.md",
                session / MEMORY_VIEWS_DIRNAME / MEMORY_OVERVIEW_FILENAME,
                session / MEMORY_VIEWS_DIRNAME / MEMORY_COMPARE_FILENAME,
            ):
                if not text_path.exists():
                    continue
                text = text_path.read_text(encoding="utf-8")
                if "Fill in" in text or "{{" in text or "}}" in text:
                    failures.append(
                        f"{branch_dir.name}: unresolved placeholder in {text_path.name}"
                    )

    if failures:
        print("Narrative check failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"Narrative check passed for {session}")
    return 0


def select_leader(branches: list[dict]) -> dict | None:
    ranked = ranked_branches(branches)
    return ranked[0] if ranked else None


def ranked_branches(branches: list[dict]) -> list[dict]:
    scored = [branch for branch in branches if branch["rows"]]
    return sorted(scored, key=branch_rank_key, reverse=True)


def branch_rank_key(branch: dict) -> tuple:
    rows = branch["rows"]
    latest = rows[-1]
    note = read_round_note(branch["branch_dir"], latest.get("round_id", ""))
    return (
        decision_rank(latest.get("decision", "")),
        verdict_rank(latest.get("verdict", "")),
        parse_score_ratio(latest.get("score", "")),
        float(latest.get("lo_adj") or 0),
        float(latest.get("sharpe") or 0),
        signal_activity_ratio(note.get("signal_activity", "")),
        len(rows),
    )


def decision_rank(decision: str) -> int:
    return {"keep": 3, "pending": 2, "discard": 1}.get(str(decision or "").strip(), 0)


def verdict_rank(verdict: str) -> int:
    return {"PASS": 3, "FAIL": 2, "ERROR": 1}.get(str(verdict or "").strip().upper(), 0)


def parse_score_ratio(score: str) -> float:
    text = str(score or "").strip()
    if "/" not in text:
        return 0.0
    left, right = text.split("/", 1)
    try:
        numerator = float(left)
        denominator = float(right)
    except ValueError:
        return 0.0
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def signal_activity_ratio(activity: str) -> float:
    text = str(activity or "").strip()
    if "/" not in text:
        return 0.0
    left, right = [part.strip() for part in text.split("/", 1)]
    try:
        active = float(left)
        total = float(right)
    except ValueError:
        return 0.0
    if total <= 0:
        return 0.0
    return active / total


def normalize_hypothesis_text(value: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return (
        "Hypothesis missing. Before the next round, state the causal claim, "
        "expected sign, and invalidation condition explicitly."
    )


def has_explicit_hypothesis(value: str) -> bool:
    text = str(value or "").strip()
    return bool(
        text
        and text != "No hypothesis supplied."
        and not text.startswith("Hypothesis missing.")
    )


def build_session_readme(
    session: Path,
    discovery: dict,
    readiness: dict,
    branches: list[dict],
) -> str:
    keep_branches = [
        branch
        for branch in branches
        if branch["rows"] and branch["rows"][-1].get("decision") == "keep"
    ]
    discard_branches = [
        branch
        for branch in branches
        if branch["rows"] and branch["rows"][-1].get("decision") == "discard"
    ]
    leader = select_leader(branches)
    debugged_branches = [
        branch for branch in branches if latest_debug_snapshot(branch["branch_dir"])
    ]
    executive = "No validated rounds yet. Start the first branch to establish the session baseline."
    if branches and not any(branch["rows"] for branch in branches):
        executive = f"{len(branches)} branch(es) have been initialized, but no validated rounds exist yet."
        if debugged_branches:
            latest_debug_branch = max(
                debugged_branches,
                key=lambda branch: latest_debug_snapshot(branch["branch_dir"]).get("updated_at", ""),
            )
            debug_note = latest_debug_snapshot(latest_debug_branch["branch_dir"])
            executive += (
                f" {len(debugged_branches)} branch(es) have already been debugged; "
                f"latest blocker is `{latest_debug_branch['branch_id']}` with signature "
                f"`{debug_note.get('failure_signature', 'unknown')}`."
            )
        else:
            executive += (
                f" Edit `{branches[0]['branch_id']}` and use `abel-strategy-discovery debug-branch` "
                "before recording the first round."
            )
    if leader and leader["rows"]:
        latest = leader["rows"][-1]
        leader_note = read_round_note(leader["branch_dir"], latest.get("round_id", ""))
        lead_label = "Current KEEP baseline"
        if latest.get("decision") != "keep":
            lead_label = "Current lead candidate (no KEEP baseline yet)"
        executive = (
            f"Session has {len(branches)} branch(es): {len(keep_branches)} keep and {len(discard_branches)} discard. "
            f"{lead_label} is `{leader['branch_id']}` at `{latest.get('round_id', 'none')}` with Lo {float(latest.get('lo_adj') or 0):.3f}, "
            f"Sharpe {float(latest.get('sharpe') or 0):.3f}, PnL {float(latest.get('pnl') or 0):.1f}%, "
            f"failure signature `{leader_note.get('failure_signature', 'unknown')}`, "
            f"active `{leader_note.get('signal_activity', 'n/a')}`."
        )

    branch_lines = (
        "\n".join(
            (
                f"1. `{branch['branch_id']}` - {len(branch['rows'])} rounds, latest "
                f"`{branch['rows'][-1].get('round_id', 'none')}` {branch['rows'][-1].get('decision', 'pending')}"
                if branch["rows"]
                else (
                    f"1. `{branch['branch_id']}` - pending, latest debug "
                    f"`{latest_debug_snapshot(branch['branch_dir']).get('failure_signature', 'not run')}`"
                    if latest_debug_snapshot(branch["branch_dir"])
                    else f"1. `{branch['branch_id']}` - scaffolded, no rounds or debug runs yet"
                )
            )
            for branch in branches
        )
        or "1. `No branches yet.`"
    )

    snapshot_lines = (
        "\n".join(
            line
            for branch in branches
            for line in (
                [build_branch_snapshot_line(branch)]
                if branch["rows"]
                else (
                    [
                        (
                            f"1. `{branch['branch_id']}` -> `debug` / "
                            f"`{latest_debug_snapshot(branch['branch_dir']).get('verdict', 'ERROR')}` / "
                            f"signature `{latest_debug_snapshot(branch['branch_dir']).get('failure_signature', 'unknown')}`. "
                            f"Why: `{current_branch_hypothesis(branch['branch_dir'], branch['rows']) or latest_debug_snapshot(branch['branch_dir']).get('summary', 'not recorded')}`. "
                            f"Next: `{latest_debug_snapshot(branch['branch_dir']).get('next_step', 'Fix the engine and rerun debug.')}`"
                        )
                    ]
                    if latest_debug_snapshot(branch["branch_dir"])
                    else []
                )
            )
        )
        or "1. `No branch outcomes yet.`"
    )
    activity_lines = (
        "\n".join(
            format_event_line(row) for row in read_tsv_rows(session / "events.tsv")[-5:]
        )
        or "1. `No events yet.`"
    )

    return f"""# {discovery.get("ticker", session.parent.name.upper())} Exploration Session {session.name}

generated by Abel strategy discovery narrative layer

## Executive Summary

{executive}

## Session Summary

- ticker: `{discovery.get("ticker", session.parent.name.upper())}`
- exp_id: `{session.name}`
- started_at: `{discovery.get("created_at", "unknown")}`
- discovery_source: `{discovery.get("source", "unknown")}`
- backtest_start: `{_get_backtest_start(discovery)}`
- current_status: `{"has_keep" if keep_branches else "active" if branches else "exploring"}`
- branch_count: `{len(branches)}`

## Session Goal

Explore {discovery.get("ticker", session.parent.name.upper())} in session `{session.name}` using discovery source `{discovery.get("source", "unknown")}` and compare candidate branches through validated rounds.

## Discovery Readiness

{render_discovery_readiness_section(readiness)}

## Selection Narrative

This session tracks {len(branches)} branch(es). Current outcomes: {len(keep_branches)} keep, {len(discard_branches)} discard, {len(branches) - len(keep_branches) - len(discard_branches)} pending.

{render_selection_narrative(branches)}

## Branches

{branch_lines}

## Branch Outcome Snapshot

{snapshot_lines}

## Recent Activity

{activity_lines}

## Next Step

{session_next_step(session, branches, discovery, readiness)}
"""


def build_branch_readme(branch: dict, latest_note: dict[str, str], exp_id: str) -> str:
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    debug_note = latest_debug_snapshot(branch["branch_dir"])
    diagnostics_note = latest_note or debug_note
    keep_rows = [row for row in rows if row.get("decision") == "keep"]
    branch_hypothesis = current_branch_hypothesis(branch["branch_dir"], rows)
    source_type = branch_source_type(branch["branch_dir"], {})
    method_family = branch_method_family(branch["branch_dir"])
    parent_branch_id = branch_parent_branch_id(branch["branch_dir"])
    ledger = (
        "\n".join(
            f"1. `{row.get('round_id', '?')}` - {row.get('description', '?')} [{row.get('score', '?')}] {row.get('decision', '?')}"
            for row in rows
        )
        or "`No rounds yet.`"
    )
    return f"""# {branch["branch_id"]}

generated by Abel strategy discovery narrative layer

## Basic Info

- branch_id: `{branch["branch_id"]}`
- ticker: `{latest.get("ticker", branch["ticker"])}`
- exp_id: `{exp_id}`
- source_type: `{source_type}`
- method_family: `{method_family}`
- parent_branch_id: `{parent_branch_id or 'none'}`
- current_status: `{latest.get("decision", "debugged" if debug_note else "scaffolded" if not rows else "exploring")}`
- total_rounds: `{len(rows)}`
- latest_round: `{latest.get("round_id", "debug" if debug_note else "none")}`
- validation_status: `{latest.get("verdict", diagnostics_note.get("verdict", "not_validated"))}`

## Branch Thesis

See `branch.yaml` for the explicit branch inputs and `thesis.md` for the branch hypothesis.

## Latest Conclusion

- decision: `{latest.get("decision", "pending")}`
- summary: `{latest.get("description", diagnostics_note.get("summary", "No rounds recorded yet."))}`
- next_step: `{diagnostics_note.get("next_step", "Edit engine.py and use `abel-strategy-discovery debug-branch` before the first recorded round.")}`

## Latest Diagnostics

- failure_signature: `{diagnostics_note.get("failure_signature", "not recorded")}`
- runtime_stage: `{diagnostics_note.get("runtime_stage", "not recorded")}`
- signal_activity: `{diagnostics_note.get("signal_activity", "not recorded")}`
- diagnostic_hints: `{diagnostics_note.get("diagnostic_hints", "not recorded")}`

## Latest Artifacts

- alpha_context_mode: `{diagnostics_note.get("context_mode", "not recorded")}`
- alpha_context: `{diagnostics_note.get("context_path", "not recorded")}`
- branch_spec: `{BRANCH_SPEC_FILENAME}`
- prepared_inputs: `{"inputs/" if branch_inputs_ready(branch["branch_dir"]) else "not prepared"}`
- runtime_profile: `{"inputs/" + RUNTIME_PROFILE_FILENAME if runtime_profile_path(branch["branch_dir"]).exists() else "not prepared"}`
- execution_constraints: `{"inputs/" + EXECUTION_CONSTRAINTS_FILENAME if execution_constraints_path(branch["branch_dir"]).exists() else "not prepared"}`
- data_manifest: `{"inputs/" + DATA_MANIFEST_FILENAME if data_manifest_path(branch["branch_dir"]).exists() else "not prepared"}`
- context_guide: `{"inputs/" + CONTEXT_GUIDE_FILENAME if context_guide_path(branch["branch_dir"]).exists() else "not prepared"}`
- probe_samples: `{"inputs/" + PROBE_SAMPLES_FILENAME if probe_samples_path(branch["branch_dir"]).exists() else "not prepared"}`
- edge_result: `{diagnostics_note.get("result_path", latest.get("result_path", "not recorded"))}`
- edge_report: `{diagnostics_note.get("report_path", latest.get("report_path", "not recorded"))}`
- edge_handoff: `{diagnostics_note.get("handoff_path", latest.get("handoff_path", "not recorded"))}`

## Decision Rationale

1. latest_hypothesis: `{branch_hypothesis or latest_note.get("hypothesis", "not recorded")}`
1. latest_summary: `{diagnostics_note.get("summary", latest.get("description", "not recorded"))}`
1. latest_failures: `{diagnostics_note.get("failures", "none")}`
1. hypothesis_status: `{"explicit" if has_explicit_hypothesis(branch_hypothesis) else "needs work"}`

## Round Ledger

{ledger}

## Metric Progression

{branch_progression(rows)}

## Baseline

- keep_rounds: `{len(keep_rows)}`
- latest_keep: `{keep_rows[-1].get("round_id", "none") if keep_rows else "none"}`
"""


def build_memory(branch: dict, discovery: dict, memory_snapshot: dict) -> str:
    branch_row = next(
        (
            row
            for row in memory_snapshot.get("branches", [])
            if row.get("branch_id") == branch["branch_id"]
        ),
        {},
    )
    insights = [
        row
        for row in memory_snapshot.get("insights", [])
        if row.get("branch_id") == branch["branch_id"]
    ]
    worked = [row for row in insights if row.get("kind") == "worked"]
    failed = [row for row in insights if row.get("kind") in {"failed", "risk"}]
    patterns = [row for row in insights if row.get("kind") == "pattern"]
    next_ideas = [row for row in insights if row.get("kind") == "next_idea"]
    compare_links = [
        row
        for row in memory_snapshot.get("links", [])
        if row.get("from_branch_id") == branch["branch_id"]
        or row.get("to_branch_id") == branch["branch_id"]
    ]

    def render_insight_lines(rows: list[dict[str, str]], *, fallback: str) -> str:
        if not rows:
            return fallback
        return "\n".join(
            f"- {row.get('round_id') or 'branch'} [{row.get('origin', 'auto')}] {row.get('statement', '')}"
            + (
                f" -> {row.get('reusable_rule', '')}"
                if row.get("reusable_rule")
                else ""
            )
            for row in rows[:5]
        )

    compare_lines = (
        "\n".join(
            f"- {row.get('link_type', 'candidate')} -> "
            f"{row.get('to_branch_id') if row.get('from_branch_id') == branch['branch_id'] else row.get('from_branch_id')}"
            + (
                f" (score {row.get('match_score')})"
                if row.get("match_score")
                else ""
            )
            + (
                f": {row.get('match_basis')}"
                if row.get("match_basis")
                else ""
            )
            for row in compare_links[:5]
        )
        or "- no compare relationships recorded yet"
    )

    return f"""# {discovery.get("ticker", branch["ticker"])} Research Memory

generated by Abel strategy discovery narrative layer

## Branch Profile

- branch_id: `{branch['branch_id']}`
- source_type: `{branch_row.get('source_type', 'unknown')}`
- method_family: `{branch_row.get('method_family', 'unknown')}`
- parent_branch_id: `{branch_row.get('parent_branch_id', 'none') or 'none'}`
- status: `{branch_row.get('status', 'exploring')}`
- thesis: `{branch_row.get('thesis_short', 'not recorded')}`

## Discovery Context

- Discovery: K={discovery.get("K_discovery", 0)} via {discovery.get("source", "unknown")}
- backtest_start: `{_get_backtest_start(discovery)}`

## What Worked

{render_insight_lines(worked, fallback='- none recorded yet')}

## What Failed

{render_insight_lines(failed, fallback='- none recorded yet')}

## Reusable Insights

{render_insight_lines(patterns, fallback='- none recorded yet')}

## Compare Candidates

{compare_lines}

## Open Questions

{render_insight_lines(next_ideas, fallback='- none recorded yet')}
"""


def build_promotion_bundle_readme(
    *,
    branch: Path,
    branch_spec: dict,
    latest: dict[str, str],
) -> str:
    selected = format_simple_nodes(branch_spec.get("selected_drivers") or [], limit=12)
    return f"""# {branch.name} Promotion Bundle

generated by Abel strategy discovery narrative layer

## Summary

- branch_id: `{branch.name}`
- target: `{branch_spec.get("target", "unknown")}`
- requested_start: `{branch_spec.get("requested_start", "unknown")}`
- overlap_mode: `{branch_spec.get("overlap_mode", "target_only")}`
- selected_drivers: `{selected}`
- latest_round: `{latest.get("round_id", "none")}`
- latest_decision: `{latest.get("decision", "n/a")}`
- latest_verdict: `{latest.get("verdict", "n/a")}`
- latest_score: `{latest.get("score", "n/a")}`

## Included Files

- `engine.py`: branch implementation snapshot
- `{BRANCH_SPEC_FILENAME}`: explicit branch definition
- `{DEPENDENCIES_FILENAME}`: prepared input/cache dependency view when available

## Next Step

Use this bundle as the handoff input for promotion into a formal strategy implementation.
"""


def build_thesis(branch: dict, discovery: dict, readiness: dict) -> str:
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    hypothesis = current_branch_hypothesis(branch["branch_dir"], rows)
    branch_spec = load_branch_spec(branch["branch_dir"])
    latest_note = (
        read_round_note(branch["branch_dir"], latest.get("round_id", ""))
        if latest
        else {}
    )
    parents = format_discovery_nodes(discovery.get("parents", []), limit=5)
    blanket = format_discovery_nodes(discovery.get("blanket_new", []), limit=5)
    usable = format_simple_nodes(readiness_usable_tickers(readiness), limit=8)
    start_covered = format_simple_nodes(readiness_start_covered_tickers(readiness), limit=8)
    selected = format_simple_nodes(branch_spec.get("selected_drivers") or [], limit=8)
    return f"""# {branch["branch_id"]} Thesis

generated by Abel strategy discovery narrative layer

## Alpha Source

Branch `{branch["branch_id"]}` currently assumes: `{hypothesis or latest.get("description", "Initial branch hypothesis not recorded yet")}`.
Latest decision is `{latest.get("decision", "pending")}` with verdict `{latest.get("verdict", "not_validated")}`.

## Hypothesis Checklist

- causal claim: `state what should drive the target and why`
- expected sign / regime: `state when the signal should be long, short, or flat`
- invalidation condition: `state what evidence would make this branch unconvincing`

## Input Universe

- target: `{discovery.get("ticker", branch["ticker"])}`
- discovery_source: `{discovery.get("source", "unknown")}`
- direct_parents: `{parents}`
- blanket_candidates: `{blanket}`
- selected_drivers: `{selected}`
- usable_tickers: `{usable}`
- start_covered_tickers: `{start_covered}`

## Main Risks

{format_risks(latest_note.get("failures", "none"))}
"""


def render_memory_snapshot(
    session: Path,
    discovery: dict,
    readiness: dict,
    branches: list[dict],
) -> dict:
    manual_insights = load_manual_memory_rows(
        session / MEMORY_INSIGHTS_FILENAME,
        MEMORY_INSIGHTS_HEADER,
    )
    manual_links = load_manual_memory_rows(
        session / MEMORY_LINKS_FILENAME,
        MEMORY_LINKS_HEADER,
    )
    events = read_tsv_rows(session / "events.tsv")
    validations_rows, validation_lookup = build_memory_validation_rows(branches)
    branch_rows = build_memory_branch_rows(
        session=session,
        discovery=discovery,
        branches=branches,
        validation_lookup=validation_lookup,
    )
    round_rows = build_memory_round_rows(branches, events)
    auto_insights = build_auto_insight_rows(branches)
    auto_links = build_auto_link_rows(branches)
    insight_rows = auto_insights + manual_insights
    link_rows = auto_links + manual_links
    manifest = build_memory_manifest(
        session=session,
        discovery=discovery,
        readiness=readiness,
        branches=branches,
        branch_rows=branch_rows,
        round_rows=round_rows,
        validation_rows=validations_rows,
        insight_rows=insight_rows,
        link_rows=link_rows,
    )
    write_json_file(session / MEMORY_MANIFEST_FILENAME, manifest)
    write_tsv_rows(session / MEMORY_BRANCHES_FILENAME, MEMORY_BRANCHES_HEADER, branch_rows)
    write_tsv_rows(session / MEMORY_ROUNDS_FILENAME, MEMORY_ROUNDS_HEADER, round_rows)
    write_tsv_rows(
        session / MEMORY_VALIDATIONS_FILENAME,
        MEMORY_VALIDATIONS_HEADER,
        validations_rows,
    )
    write_tsv_rows(
        session / MEMORY_INSIGHTS_FILENAME,
        MEMORY_INSIGHTS_HEADER,
        insight_rows,
    )
    write_tsv_rows(session / MEMORY_LINKS_FILENAME, MEMORY_LINKS_HEADER, link_rows)
    views_dir = session / MEMORY_VIEWS_DIRNAME
    views_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "manifest": manifest,
        "branches": branch_rows,
        "rounds": round_rows,
        "validations": validations_rows,
        "insights": insight_rows,
        "links": link_rows,
    }
    (views_dir / MEMORY_OVERVIEW_FILENAME).write_text(
        build_memory_overview(session, discovery, readiness, branches, snapshot),
        encoding="utf-8",
    )
    (views_dir / MEMORY_COMPARE_FILENAME).write_text(
        build_memory_compare_view(session, discovery, snapshot),
        encoding="utf-8",
    )
    return snapshot


def build_memory_manifest(
    *,
    session: Path,
    discovery: dict,
    readiness: dict,
    branches: list[dict],
    branch_rows: list[dict[str, str]],
    round_rows: list[dict[str, str]],
    validation_rows: list[dict[str, str]],
    insight_rows: list[dict[str, str]],
    link_rows: list[dict[str, str]],
) -> dict:
    source_types = {row.get("source_type", "") for row in branch_rows if row.get("source_type")}
    compare_axis = "branch_memory"
    if "causal" in source_types and "baseline" in source_types:
        compare_axis = "causal_vs_baseline"
    return {
        "schema_version": 1,
        "exp_id": session.name,
        "asset_scope": discovery.get("ticker", session.parent.name.upper()),
        "compare_axis": compare_axis,
        "discovery_source": discovery.get("source", "unknown"),
        "backtest_start": _get_backtest_start(discovery),
        "created_at": discovery.get("created_at", _now()),
        "updated_at": _now(),
        "branch_count": len(branches),
        "memory_counts": {
            "branches": len(branch_rows),
            "rounds": len(round_rows),
            "validations": len(validation_rows),
            "insights": len(insight_rows),
            "links": len(link_rows),
        },
        "readiness_summary": format_data_readiness_summary(readiness),
    }


def build_memory_branch_rows(
    *,
    session: Path,
    discovery: dict,
    branches: list[dict],
    validation_lookup: dict[tuple[str, str], str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for branch in branches:
        branch_dir = branch["branch_dir"]
        branch_rows = branch["rows"]
        latest = branch_rows[-1] if branch_rows else {}
        best = best_branch_row(branch_rows)
        best_round_id = best.get("round_id", "") if best else ""
        rows.append(
            {
                "branch_id": branch["branch_id"],
                "asset_scope": discovery.get("ticker", session.parent.name.upper()),
                "exp_id": session.name,
                "method_family": branch_method_family(branch_dir),
                "source_type": branch_source_type(branch_dir, discovery),
                "parent_branch_id": branch_parent_branch_id(branch_dir),
                "status": branch_memory_status(session, branch),
                "latest_round_id": latest.get("round_id", ""),
                "best_round_id": best_round_id,
                "best_validation_id": validation_lookup.get(
                    (branch["branch_id"], best_round_id),
                    "",
                ),
                "thesis_short": branch_thesis_short(branch),
                "created_at": branch_created_at(branch_dir),
            }
        )
    return rows


def build_memory_round_rows(
    branches: list[dict],
    events: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for branch in branches:
        for row in branch["rows"]:
            round_id = row.get("round_id", "")
            note = read_round_note(branch["branch_dir"], round_id)
            actions = read_round_actions(branch["branch_dir"], round_id)
            ended_at = round_event_timestamp(events, branch["branch_id"], round_id)
            rows.append(
                {
                    "round_id": round_id,
                    "branch_id": branch["branch_id"],
                    "stage": mode_to_stage(row.get("mode", "")),
                    "started_at": ended_at,
                    "ended_at": ended_at,
                    "trigger": note.get("trigger", row.get("description", "")),
                    "hypothesis": note.get("hypothesis", ""),
                    "change_summary": note.get(
                        "change_summary",
                        note.get("summary", row.get("description", "")),
                    ),
                    "action_summary": "; ".join(actions) or row.get("description", ""),
                    "decision": row.get("decision", ""),
                    "next_step": note.get("next_step", ""),
                    "time_spent_min": note.get("time_spent_min", ""),
                }
            )
    return rows


def build_memory_validation_rows(
    branches: list[dict],
) -> tuple[list[dict[str, str]], dict[tuple[str, str], str]]:
    rows: list[dict[str, str]] = []
    lookup: dict[tuple[str, str], str] = {}
    counter = 1
    for branch in branches:
        for row in branch["rows"]:
            validation_id = f"val-{counter:03d}"
            counter += 1
            round_id = row.get("round_id", "")
            lookup[(branch["branch_id"], round_id)] = validation_id
            rows.append(
                {
                    "validation_id": validation_id,
                    "branch_id": branch["branch_id"],
                    "round_id": round_id,
                    "engine": "Abel-edge",
                    "verdict": row.get("verdict", ""),
                    "score": row.get("score", ""),
                    "sharpe": row.get("sharpe", ""),
                    "lo_adj": row.get("lo_adj", ""),
                    "omega": row.get("omega", ""),
                    "total_return": row.get("pnl", ""),
                    "max_dd": row.get("max_dd", ""),
                    "result_ref": row.get("result_path", ""),
                    "report_ref": row.get("report_path", ""),
                }
            )
    return rows, lookup


def build_auto_insight_rows(branches: list[dict]) -> list[dict[str, str]]:
    payloads: list[dict[str, str]] = []
    for branch in branches:
        branch_id = branch["branch_id"]
        branch_dir = branch["branch_dir"]
        rows = branch["rows"]
        latest = rows[-1] if rows else {}
        latest_note = read_round_note(branch_dir, latest.get("round_id", "")) if latest else {}
        hypothesis = current_branch_hypothesis(branch_dir, rows)
        if has_explicit_hypothesis(hypothesis):
            payloads.append(
                {
                    "scope": "branch",
                    "branch_id": branch_id,
                    "round_id": latest.get("round_id", ""),
                    "kind": "pattern",
                    "statement": hypothesis,
                    "reusable_rule": "Treat this as the branch thesis until a stronger validated explanation replaces it.",
                    "confidence": "medium",
                }
            )
        latest_keep = latest_row_by_decision(rows, "keep")
        if latest_keep is not None:
            keep_note = read_round_note(branch_dir, latest_keep.get("round_id", ""))
            payloads.append(
                {
                    "scope": "branch",
                    "branch_id": branch_id,
                    "round_id": latest_keep.get("round_id", ""),
                    "kind": "worked",
                    "statement": latest_keep.get("description", "kept baseline"),
                    "reusable_rule": keep_note.get(
                        "next_step",
                        "Refine from the latest KEEP baseline before opening a sibling branch.",
                    ),
                    "confidence": "high",
                }
            )
        latest_discard = latest_row_by_decision(rows, "discard")
        if latest_discard is not None:
            discard_note = read_round_note(branch_dir, latest_discard.get("round_id", ""))
            payloads.append(
                {
                    "scope": "branch",
                    "branch_id": branch_id,
                    "round_id": latest_discard.get("round_id", ""),
                    "kind": "failed",
                    "statement": discard_note.get(
                        "failures",
                        latest_discard.get("description", "discarded direction"),
                    ),
                    "reusable_rule": "Do not retry this direction without changing the causal claim, drivers, or start window.",
                    "confidence": "high",
                }
            )
        if latest_note.get("failures") and latest.get("decision", "") != "discard":
            payloads.append(
                {
                    "scope": "branch",
                    "branch_id": branch_id,
                    "round_id": latest.get("round_id", ""),
                    "kind": "risk",
                    "statement": latest_note.get("failures", "none"),
                    "reusable_rule": "Fix this blocker before trusting the next validation result.",
                    "confidence": "medium",
                }
            )
        if latest_note.get("next_step"):
            payloads.append(
                {
                    "scope": "branch",
                    "branch_id": branch_id,
                    "round_id": latest.get("round_id", ""),
                    "kind": "next_idea",
                    "statement": latest_note.get("next_step", ""),
                    "reusable_rule": "Use this as the next experiment seed if no stronger link-based compare candidate exists.",
                    "confidence": "medium",
                }
            )
    rows: list[dict[str, str]] = []
    for index, payload in enumerate(payloads, start=1):
        rows.append(
            {
                "insight_id": f"ins-auto-{index:03d}",
                "origin": "auto",
                **payload,
            }
        )
    return rows


def build_auto_link_rows(branches: list[dict]) -> list[dict[str, str]]:
    payloads: list[dict[str, str]] = []
    branch_map = {branch["branch_id"]: branch for branch in branches}
    for branch in branches:
        parent_branch_id = branch_parent_branch_id(branch["branch_dir"])
        if parent_branch_id and parent_branch_id in branch_map:
            payloads.append(
                {
                    "from_branch_id": branch["branch_id"],
                    "to_branch_id": parent_branch_id,
                    "link_type": "derived_from",
                    "match_score": "",
                    "match_basis": "parent_branch_id recorded in branch.yaml",
                    "status": "selected",
                    "note": "auto-derived from branch metadata",
                }
            )
    validated = [branch for branch in branches if branch["rows"]]
    for branch in validated:
        left_source = branch_source_type(branch["branch_dir"], {})
        if left_source != "causal":
            continue
        for candidate in validated:
            if candidate["branch_id"] == branch["branch_id"]:
                continue
            right_source = branch_source_type(candidate["branch_dir"], {})
            if right_source != "baseline":
                continue
            payloads.append(
                {
                    "from_branch_id": branch["branch_id"],
                    "to_branch_id": candidate["branch_id"],
                    "link_type": "candidate_compare",
                    "match_score": f"{candidate_compare_score(branch, candidate):.2f}",
                    "match_basis": candidate_compare_basis(branch, candidate),
                    "status": "candidate",
                    "note": "auto-suggested compare candidate",
                }
            )
    rows: list[dict[str, str]] = []
    for index, payload in enumerate(payloads, start=1):
        rows.append(
            {
                "link_id": f"link-auto-{index:03d}",
                "origin": "auto",
                **payload,
            }
        )
    return rows


def build_memory_overview(
    session: Path,
    discovery: dict,
    readiness: dict,
    branches: list[dict],
    memory_snapshot: dict,
) -> str:
    branch_lines = (
        "\n".join(
            f"1. `{row['branch_id']}` - `{row['source_type']}` / `{row['method_family']}` / `{row['status']}` / best `{row['best_round_id'] or 'none'}`"
            for row in memory_snapshot["branches"]
        )
        or "1. `No branches yet.`"
    )
    insight_lines = (
        "\n".join(
            f"1. `{row['kind']}` `{row['branch_id'] or 'session'}` - {row['statement']}"
            for row in memory_snapshot["insights"][:8]
        )
        or "1. `No insights recorded yet.`"
    )
    compare_candidates = [
        row
        for row in memory_snapshot["links"]
        if row.get("link_type") in {"candidate_compare", "final_compare"}
    ]
    compare_lines = (
        "\n".join(
            f"1. `{row['from_branch_id']}` -> `{row['to_branch_id']}` / `{row['link_type']}` / score `{row.get('match_score') or 'n/a'}` / {row.get('match_basis') or 'not recorded'}"
            for row in compare_candidates[:8]
        )
        or "1. `No compare candidates yet.`"
    )
    return f"""# {discovery.get("ticker", session.parent.name.upper())} Memory Overview

generated by Abel strategy discovery narrative layer

## Summary

- exp_id: `{session.name}`
- asset_scope: `{discovery.get("ticker", session.parent.name.upper())}`
- discovery_source: `{discovery.get("source", "unknown")}`
- backtest_start: `{_get_backtest_start(discovery)}`
- readiness: `{format_data_readiness_summary(readiness) or 'not recorded'}`
- branches: `{len(memory_snapshot['branches'])}`
- insights: `{len(memory_snapshot['insights'])}`
- links: `{len(memory_snapshot['links'])}`

## Branches

{branch_lines}

## Reusable Insights

{insight_lines}

## Compare Candidates

{compare_lines}

## Next Step

{session_next_step(session, branches, discovery, readiness)}
"""


def build_memory_compare_view(
    session: Path,
    discovery: dict,
    memory_snapshot: dict,
) -> str:
    branch_rows = {row["branch_id"]: row for row in memory_snapshot["branches"]}
    validation_rows = {row["branch_id"]: row for row in memory_snapshot["validations"]}
    compare_rows = [
        row
        for row in memory_snapshot["links"]
        if row.get("link_type") in {"candidate_compare", "final_compare"}
    ]
    compare_rows.sort(
        key=lambda row: (
            1 if row.get("link_type") == "final_compare" else 0,
            float(row.get("match_score") or 0),
        ),
        reverse=True,
    )
    lines = []
    for row in compare_rows:
        left = validation_rows.get(row["from_branch_id"], {})
        right = validation_rows.get(row["to_branch_id"], {})
        lines.append(
            "1. "
            f"`{row['from_branch_id']}` ({branch_rows.get(row['from_branch_id'], {}).get('source_type', 'unknown')}) "
            f"vs `{row['to_branch_id']}` ({branch_rows.get(row['to_branch_id'], {}).get('source_type', 'unknown')}) "
            f"-> `{row['link_type']}` / `{row.get('status', 'candidate')}` / score `{row.get('match_score') or 'n/a'}`. "
            f"Metrics: left Sharpe `{left.get('sharpe', 'n/a')}`, right Sharpe `{right.get('sharpe', 'n/a')}`. "
            f"Basis: `{row.get('match_basis') or 'not recorded'}`"
        )
    body = "\n".join(lines) or "1. `No compare relationships recorded yet.`"
    return f"""# {discovery.get("ticker", session.parent.name.upper())} Compare View

generated by Abel strategy discovery narrative layer

## Compare Candidates

{body}
"""


def branch_source_type(branch_dir: Path, discovery: dict) -> str:
    branch_spec = load_branch_spec(branch_dir)
    configured = str(branch_spec.get("source_type") or "").strip().lower()
    if configured in {"causal", "baseline", "hybrid"}:
        return configured
    name = branch_dir.name.lower()
    if "baseline" in name or name.startswith("sma") or name.startswith("rule"):
        return "baseline"
    if "graph" in name:
        return "causal"
    if discovery.get("source") not in {None, "", "unknown", "pending"}:
        return "causal"
    return "hybrid"


def branch_method_family(branch_dir: Path) -> str:
    branch_spec = load_branch_spec(branch_dir)
    configured = str(branch_spec.get("method_family") or "").strip().lower()
    if configured in {"graph", "technical", "rule", "ml", "hybrid"}:
        return configured
    name = branch_dir.name.lower()
    if "graph" in name:
        return "graph"
    if "sma" in name or "rule" in name:
        return "rule"
    if "ml" in name:
        return "ml"
    return "hybrid"


def branch_parent_branch_id(branch_dir: Path) -> str:
    branch_spec = load_branch_spec(branch_dir)
    return str(branch_spec.get("parent_branch_id") or "").strip()


def branch_created_at(branch_dir: Path) -> str:
    state = load_branch_state(branch_dir)
    created_at = str(state.get("created_at") or "").strip()
    if created_at:
        return created_at
    return datetime.fromtimestamp(branch_dir.stat().st_mtime, tz=timezone.utc).isoformat()


def branch_memory_status(session: Path, branch: dict) -> str:
    promotions_dir = session / "promotions" / branch["branch_id"]
    if promotions_dir.exists():
        return "promoted"
    if not branch["rows"]:
        return "exploring"
    latest = branch["rows"][-1]
    if latest.get("decision") == "discard":
        return "archived"
    return "validating"


def branch_thesis_short(branch: dict) -> str:
    hypothesis = current_branch_hypothesis(branch["branch_dir"], branch["rows"])
    if has_explicit_hypothesis(hypothesis):
        return hypothesis
    latest = branch["rows"][-1] if branch["rows"] else {}
    if latest.get("description"):
        return str(latest.get("description") or "").strip()
    branch_spec = load_branch_spec(branch["branch_dir"])
    selected = format_simple_nodes(branch_spec.get("selected_drivers") or [], limit=5)
    return f"target {branch['ticker']} with drivers {selected}"


def best_branch_row(rows: list[dict[str, str]]) -> dict[str, str] | None:
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            decision_rank(row.get("decision", "")),
            verdict_rank(row.get("verdict", "")),
            parse_score_ratio(row.get("score", "")),
            float(row.get("lo_adj") or 0),
            float(row.get("sharpe") or 0),
        ),
    )


def latest_row_by_decision(
    rows: list[dict[str, str]],
    decision: str,
) -> dict[str, str] | None:
    for row in reversed(rows):
        if row.get("decision") == decision:
            return row
    return None


def mode_to_stage(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized in {"explore", "exploit"}:
        return "exploration"
    return normalized or "exploration"


def round_event_timestamp(
    events: list[dict[str, str]],
    branch_id: str,
    round_id: str,
) -> str:
    for row in reversed(events):
        if (
            row.get("event") == "round_recorded"
            and row.get("branch_id") == branch_id
            and row.get("round_id") == round_id
        ):
            return row.get("timestamp", "")
    return ""


def read_round_actions(branch_dir: Path, round_id: str) -> list[str]:
    if not round_id:
        return []
    path = branch_dir / "rounds" / f"{round_id}.md"
    if not path.exists():
        return []
    actions: list[str] = []
    in_actions = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            if in_actions:
                break
            in_actions = line.strip() == "## Actions"
            continue
        if in_actions:
            stripped = line.strip()
            if stripped.startswith("1. "):
                actions.append(stripped[3:].strip())
    return actions


def candidate_compare_basis(left: dict, right: dict) -> str:
    left_spec = load_branch_spec(left["branch_dir"])
    right_spec = load_branch_spec(right["branch_dir"])
    basis = ["same asset scope and both have validated rounds"]
    if left_spec.get("requested_start") == right_spec.get("requested_start"):
        basis.append("same requested_start")
    if left_spec.get("overlap_mode") == right_spec.get("overlap_mode"):
        basis.append("same overlap_mode")
    return "; ".join(basis)


def candidate_compare_score(left: dict, right: dict) -> float:
    left_spec = load_branch_spec(left["branch_dir"])
    right_spec = load_branch_spec(right["branch_dir"])
    score = 0.6
    if left_spec.get("requested_start") == right_spec.get("requested_start"):
        score += 0.2
    if left_spec.get("overlap_mode") == right_spec.get("overlap_mode"):
        score += 0.2
    return min(score, 1.0)


def format_discovery_nodes(items: list[object], *, limit: int = 5) -> str:
    rendered = []
    for item in items[:limit]:
        if isinstance(item, str):
            rendered.append(item)
            continue
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker", "")).strip()
        field = str(item.get("field", "")).strip()
        roles = [
            str(role).strip() for role in item.get("roles", []) if str(role).strip()
        ]
        label = ".".join(part for part in (ticker, field) if part)
        if not label:
            continue
        if roles:
            label = f"{label} ({', '.join(roles)})"
        rendered.append(label)
    return ", ".join(rendered) or "none recorded"


def format_simple_nodes(items: list[object], *, limit: int = 8) -> str:
    rendered = [str(item).strip() for item in items[:limit] if str(item).strip()]
    return ", ".join(rendered) or "none recorded"


def readiness_results(readiness: dict) -> list[dict]:
    results = readiness.get("results") or []
    return [item for item in results if isinstance(item, dict)]


def readiness_usable_tickers(readiness: dict) -> list[str]:
    return [
        str(item.get("ticker") or "").strip().upper()
        for item in readiness_results(readiness)
        if item.get("usable")
    ]


def readiness_start_covered_tickers(readiness: dict) -> list[str]:
    return [
        str(item.get("ticker") or "").strip().upper()
        for item in readiness_results(readiness)
        if item.get("covers_requested_start")
    ]


def format_data_readiness_summary(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    requested = report.get("requested_window") or {}
    probe = report.get("probe") or {}
    probe_limit = probe.get("limit")
    return (
        f"{summary.get('start_covered_count', 0)} start-covered, "
        f"{summary.get('partial_window_count', 0)} partial, "
        f"{summary.get('no_data_count', 0)} no-data, "
        f"{summary.get('error_count', 0)} error "
        f"(start {requested.get('start', 'latest')}, probe {probe_limit or 'n/a'})"
    )


def render_target_boundary_line(readiness: dict) -> str:
    report = readiness or {}
    target_boundary = report.get("target_boundary") or {}
    classification = target_boundary.get("classification")
    if not classification:
        return "not recorded"
    observed_first = target_boundary.get("observed_first_timestamp")
    observed_last = target_boundary.get("observed_last_timestamp")
    parts = [str(classification)]
    if observed_first:
        parts.append(f"observed_first={observed_first}")
    if observed_last:
        parts.append(f"observed_last={observed_last}")
    return ", ".join(parts)


def render_readiness_guidance(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    requested_start = str((report.get("requested_window") or {}).get("start") or "latest")
    coverage_hints = report.get("coverage_hints") or {}
    target_safe = coverage_hints.get("target_safe_start")
    dense_overlap = coverage_hints.get("dense_overlap_hint_start")
    if target_safe and dense_overlap and target_safe != dense_overlap:
        return (
            f"Desired start remains {requested_start}. Target-first research can begin around "
            f"{target_safe}, while denser driver overlap appears around {dense_overlap} if the branch needs it."
        )
    if target_safe and target_safe != requested_start:
        return (
            f"Desired start remains {requested_start}. Target-safe coverage is currently observed from "
            f"{target_safe}; later driver overlap is optional, not mandatory."
        )
    if dense_overlap:
        return (
            f"Desired start remains {requested_start}. Dense overlap is hinted around {dense_overlap}, "
            "but target-first branches may continue earlier if they tolerate partial driver coverage."
        )
    return (
        f"Desired start remains {requested_start}. Use readiness as a coverage profile, not as a mandatory "
        "research-design verdict."
    )


def render_discovery_readiness_section(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return "`No data readiness report recorded yet. Run live discovery again after edge verification is available.`"
    start_covered = ", ".join(readiness_start_covered_tickers(readiness)) or "none"
    usable = ", ".join(readiness_usable_tickers(readiness)) or "none"
    lines = [
        f"- summary: `{format_data_readiness_summary(readiness)}`\n"
        f"- target_boundary: `{render_target_boundary_line(readiness)}`\n"
        f"- usable_tickers: `{usable}`\n"
        f"- start_covered_tickers: `{start_covered}`"
    ]
    warning = build_readiness_warning(readiness)
    if warning:
        lines.append(f"- warning: `{warning}`")
    for line in readiness_recommendation_lines(readiness):
        lines.append(f"- coverage_hint: `{line}`")
    guidance = render_readiness_guidance(readiness)
    if guidance:
        lines.append(f"- interpretation: `{guidance}`")
    return "\n".join(lines)


def build_readiness_warning(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    if int(summary.get("usable_count", 0) or 0) == 0:
        return "No usable tickers were confirmed for the requested backtest window."
    requested_start = (report.get("requested_window") or {}).get("start", "latest")
    target_boundary = report.get("target_boundary") or {}
    classification = target_boundary.get("classification")
    observed_first = target_boundary.get("observed_first_timestamp")
    if classification == "confirmed_after_requested_start":
        return (
            "Target history begins after the session requested backtest_start "
            f"{requested_start}. Treat this as a session-level coverage note; branches may still "
            "choose narrower explicit starts intentionally."
        )
    if classification == "unknown_probe_truncated":
        observed_suffix = (
            f" The deepest observed target history begins at {observed_first}."
            if observed_first
            else ""
        )
        return (
            "Target coverage before the requested backtest_start "
            f"{requested_start} is not yet confirmed.{observed_suffix}"
        )
    if int(summary.get("start_covered_count", 0) or 0) <= 0:
        return (
            "Discovered drivers are only partially available from the session requested start "
            f"{requested_start}. Target-first research can still continue; use coverage hints only "
            "if your branch depends on strict overlap."
        )
    return ""


def readiness_recommendation_lines(readiness: dict) -> list[str]:
    report = readiness or {}
    coverage_hints = report.get("coverage_hints") or {}
    lines: list[str] = []
    target_start = coverage_hints.get("target_safe_start")
    common_start = coverage_hints.get("dense_overlap_hint_start")
    if target_start:
        lines.append(f"target_safe={target_start}")
    if common_start:
        lines.append(f"dense_overlap={common_start}")
    return lines


def branch_runtime_advisory_lines(
    *,
    branch_requested_start: str,
    discovery: dict,
    readiness: dict,
) -> list[str]:
    session_requested_start = _get_backtest_start(discovery)
    coverage_hints = (readiness or {}).get("coverage_hints") or {}
    lines = [f"branch_requested_start={branch_requested_start}"]
    if branch_requested_start != session_requested_start:
        lines.append(
            f"session_backtest_start={session_requested_start} (session-level advisory only)"
        )
    target_safe = coverage_hints.get("target_safe_start")
    if target_safe:
        lines.append(f"target_safe_hint={target_safe}")
    dense_overlap = coverage_hints.get("dense_overlap_hint_start")
    if dense_overlap:
        lines.append(
            f"dense_overlap_hint={dense_overlap} (advisory only; not required unless the branch needs strict overlap)"
        )
    return lines


def _branch_driver_list(branch_spec: dict) -> list[str]:
    return [
        str(item).strip().upper()
        for item in (branch_spec.get("selected_drivers") or [])
        if str(item).strip()
    ]


def branch_context_summary_lines(
    *,
    branch: Path,
    session: Path,
    discovery: dict,
    readiness: dict,
) -> list[str]:
    branch_spec = load_branch_spec(branch)
    target = str(
        branch_spec.get("target")
        or discovery.get("ticker")
        or session.parent.name.upper()
    ).strip().upper()
    requested_start = str(
        branch_spec.get("requested_start") or _get_backtest_start(discovery)
    ).strip()
    session_start = _get_backtest_start(discovery)
    coverage_hints = (readiness or {}).get("coverage_hints") or {}
    drivers = _branch_driver_list(branch_spec)
    drivers_text = ", ".join(drivers) if drivers else "none"
    starter_scaffold = branch_uses_default_scaffold(branch, discovery, readiness, session)
    inputs_prepared = branch_inputs_ready(branch)

    lines = [
        f"target={target}",
        f"selected_drivers={len(drivers)} ({drivers_text})",
        f"requested_start={requested_start}",
    ]
    if requested_start == session_start:
        lines.append(f"start_source=session_default ({session_start})")
    else:
        lines.append(
            f"session_backtest_start={session_start} (session-level advisory only)"
        )
    target_safe = coverage_hints.get("target_safe_start")
    if target_safe:
        lines.append(f"target_safe_hint={target_safe}")
    dense_overlap = coverage_hints.get("dense_overlap_hint_start")
    if dense_overlap:
        lines.append(f"dense_overlap_hint={dense_overlap}")
    lines.append(f"inputs_prepared={'yes' if inputs_prepared else 'no'}")
    lines.append(
        "scaffold_status="
        + ("starter_scaffold" if starter_scaffold else "branch_specific_engine")
    )
    if not inputs_prepared:
        lines.append("current_branch_boundary=prepare_branch_inputs")
    elif starter_scaffold:
        lines.append("recorded_round_boundary=branch_specific_engine_required")
    else:
        lines.append("recorded_round_boundary=branch_specific_engine_present")
    return lines


def render_section(title: str, lines: list[str]) -> None:
    if not lines:
        return
    print(f"{title}:")
    for line in lines:
        print(f"  {line}")


def classify_result_frame(result: dict[str, object]) -> tuple[str, str]:
    verdict = str(result.get("verdict") or "").upper()
    diagnostics = result.get("diagnostics") or {}
    semantic = result.get("semantic") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    if not isinstance(semantic, dict):
        semantic = {}
    failure_signature = str(diagnostics.get("failure_signature") or "")
    runtime_stage = str(diagnostics.get("runtime_stage") or "")
    failures = " ".join(str(item) for item in (result.get("failures") or []))
    failures_lower = failures.lower()

    if failure_signature == "auth_missing" or "api key not found" in failures_lower:
        return (
            "workflow_boundary",
            "The branch is still blocked on auth for a data path; use abel-auth before treating this as an engine or strategy issue.",
        )

    if verdict == "ERROR":
        if runtime_stage == "semantic_preflight":
            return (
                "preflight_blocker",
                "The branch failed semantic preflight before metric validation; fix data visibility or output-shape issues before recording a round.",
            )
        if (
            "target bars" in failures_lower
            or "no usable target bars" in failures_lower
            or "requested window" in failures_lower
        ):
            return (
                "data_or_setup_issue",
                "The branch failed before validation on data/start alignment, not on strategy quality.",
            )
        return (
            "implementation_issue",
            "The branch failed before validation; inspect engine and runtime wiring before treating this as a strategy result.",
        )

    if verdict in {"FAIL", "PASS"} and runtime_stage == "validation":
        if failure_signature in {"zero_information_signal", "signal_always_flat"}:
            return (
                "mechanism_result",
                "Validation ran, but the current mechanism did not express useful information yet.",
            )
        return (
            "validation_result",
            "Validation ran on the current mechanism; interpret this as research evidence rather than a workflow blocker.",
        )

    if verdict == "PASS" and str(semantic.get("verdict") or "").upper() == "PASS":
        return (
            "preflight_ready",
            "Semantic preflight passed; the branch is ready for further mechanism tuning or a full recorded round.",
        )

    return (
        "unclear_result_state",
        "The branch produced a result, but the current state still needs manual inspection.",
    )


def render_selection_narrative(branches: list[dict]) -> str:
    ranked = ranked_branches(branches)[:3]
    if not ranked:
        return "No branch rankings yet because no validated rounds have been recorded."
    lines = []
    for index, branch in enumerate(ranked, start=1):
        latest = branch["rows"][-1]
        note = read_round_note(branch["branch_dir"], latest.get("round_id", ""))
        reason = (
            current_branch_hypothesis(branch["branch_dir"], branch["rows"])
            or note.get("hypothesis")
            or latest.get("description", "No explicit hypothesis recorded yet.")
        )
        label = "lead" if index == 1 else "runner-up"
        lines.append(
            f"{index}. `{branch['branch_id']}` ({label}) -> "
            f"`{latest.get('decision', 'pending')}` / `{latest.get('verdict', 'n/a')}` / "
            f"`{latest.get('score', '?/?')}` / signature `{note.get('failure_signature', 'unknown')}`. "
            f"Reasoning: `{reason}`"
        )
    return "\n".join(lines)


def alpha_decision(rows: list[dict[str, str]], result: dict, *, session: Path | None = None) -> str:
    if result.get("verdict") != "PASS":
        return "discard"

    baseline = None
    for row in reversed(rows):
        if row.get("decision") == "keep":
            baseline = row
            break
    if baseline is None:
        return "keep"

    profile_name = str(result.get("profile") or "").strip()
    if not profile_name:
        raise RuntimeError(
            "edge evaluation did not provide a profile for baseline compare"
        )

    baseline_metrics = {
        "lo_adjusted": float(baseline.get("lo_adj") or 0),
        "position_ic": float(baseline.get("ic") or 0),
        "omega": float(baseline.get("omega") or 0),
        "sharpe": float(baseline.get("sharpe") or 0),
        "total_return": float(baseline.get("pnl") or 0) / 100.0,
        "max_dd": float(baseline.get("max_dd") or 0),
    }

    try:
        from causal_edge.validation.gate_logic import decide_keep_discard
        from causal_edge.validation.metrics import load_profile

        decision = decide_keep_discard(
            result.get("metrics", {}),
            baseline_metrics,
            load_profile(profile_name),
        )
    except ImportError:
        if session is None:
            raise
        decision = alpha_decision_with_runtime(
            session=session,
            current_metrics=result.get("metrics", {}),
            baseline_metrics=baseline_metrics,
            profile_name=profile_name,
        )
    return "keep" if decision == "KEEP" else "discard"


def alpha_decision_with_runtime(
    *,
    session: Path,
    current_metrics: dict,
    baseline_metrics: dict,
    profile_name: str,
) -> str:
    workspace_root = find_workspace_root(session)
    if workspace_root is None:
        raise RuntimeError(
            "Cannot resolve workspace runtime for baseline comparison."
        )
    manifest = load_workspace_manifest(workspace_root)
    python_path = resolve_runtime_python(workspace_root, manifest)
    payload = {
        "current_metrics": current_metrics,
        "baseline_metrics": baseline_metrics,
        "profile_name": profile_name,
    }
    script = (
        "import json, sys\n"
        "from causal_edge.validation.gate_logic import decide_keep_discard\n"
        "from causal_edge.validation.metrics import load_profile\n"
        "payload = json.loads(sys.stdin.read())\n"
        "decision = decide_keep_discard(\n"
        "    payload['current_metrics'],\n"
        "    payload['baseline_metrics'],\n"
        "    load_profile(payload['profile_name']),\n"
        ")\n"
        "print(decision)\n"
    )
    completed = subprocess.run(
        [str(python_path), "-c", script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip() or "unknown error"
        raise RuntimeError(
            f"Workspace runtime could not compare against the KEEP baseline: {detail}"
        )
    return completed.stdout.strip() or "DISCARD"


def build_branch_context(
    *,
    branch: Path,
    session: Path,
    discovery: dict,
    readiness: dict,
    round_id: str,
    backtest_start: str,
) -> dict:
    """Build the structured context passed into causal-edge evaluate."""
    workspace_root = find_workspace_root(branch)
    branch_spec = load_branch_spec(branch)
    dependencies = {}
    if dependencies_path(branch).exists():
        dependencies = json.loads(dependencies_path(branch).read_text(encoding="utf-8"))
    runtime_profile = build_runtime_profile_payload(
        target=str(branch_spec.get("target") or discovery.get("ticker") or "").strip().upper()
    )
    if runtime_profile_path(branch).exists():
        runtime_profile = json.loads(runtime_profile_path(branch).read_text(encoding="utf-8"))
    execution_constraints = build_execution_constraints_payload(branch_spec)
    if execution_constraints_path(branch).exists():
        execution_constraints = json.loads(
            execution_constraints_path(branch).read_text(encoding="utf-8")
        )
    data_manifest = build_data_manifest_payload(
        target=str(runtime_profile.get("target") or discovery.get("ticker") or "").strip().upper(),
        selected_drivers=[
            str(item).strip().upper()
            for item in (branch_spec.get("selected_drivers") or [])
            if str(item).strip()
        ],
        cache_payload=(dependencies.get("cache") or {}) if isinstance(dependencies, dict) else {},
        readiness=readiness,
    )
    if data_manifest_path(branch).exists():
        data_manifest = json.loads(data_manifest_path(branch).read_text(encoding="utf-8"))
    cache = dependencies.get("cache") if isinstance(dependencies, dict) else {}
    primary_feed = {
        "name": "primary",
        "kind": "bars",
        "adapter": str((cache or {}).get("adapter") or "abel"),
        "timeframe": str((cache or {}).get("timeframe") or "1d"),
        "symbol": discovery.get("ticker", session.parent.name.upper()),
        "profile": str((cache or {}).get("profile") or "daily"),
    }
    cache_root = (cache or {}).get("cache_root")
    if cache_root:
        primary_feed["cache_root"] = cache_root
    feeds = {"primary": primary_feed}
    for item in (data_manifest.get("feeds") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        symbol = str(item.get("symbol") or "").strip().upper()
        if not name or name == "primary" or not symbol:
            continue
        feeds[name] = {
            "name": name,
            "kind": "bars",
            "adapter": str(item.get("adapter") or primary_feed["adapter"]),
            "timeframe": str(item.get("timeframe") or primary_feed["timeframe"]),
            "symbol": symbol,
            "profile": str(item.get("profile") or primary_feed["profile"]),
            **({"cache_root": item.get("cache_root")} if item.get("cache_root") else {}),
        }
    return {
        "schema_version": 1,
        "workspace_root": str(workspace_root) if workspace_root is not None else None,
        "exp_id": session.name,
        "branch_id": branch.name,
        "round_id": round_id,
        "session_dir": str(session.resolve()),
        "branch_dir": str(branch.resolve()),
        "outputs_dir": str((branch / "outputs").resolve()),
        "branch_spec_path": str(branch_spec_path(branch).resolve()),
        "dependencies_path": str(dependencies_path(branch).resolve()),
        "runtime_profile_path": str(runtime_profile_path(branch).resolve()),
        "execution_constraints_path": str(execution_constraints_path(branch).resolve()),
        "data_manifest_path": str(data_manifest_path(branch).resolve()),
        "context_guide_path": str(context_guide_path(branch).resolve()),
        "probe_samples_path": str(probe_samples_path(branch).resolve()),
        "discovery_path": str((session / "discovery.json").resolve()),
        "readiness_path": str((session / READINESS_FILENAME).resolve()),
        "ticker": discovery.get("ticker", session.parent.name.upper()),
        "backtest_start": backtest_start,
        "branch_spec": branch_spec,
        "dependencies": dependencies,
        "discovery": discovery,
        "readiness": readiness,
        "runtime_profile": runtime_profile,
        "execution_constraints": execution_constraints,
        "data_manifest": data_manifest,
        "_runtime_profile": runtime_profile,
        "_execution_constraints": execution_constraints,
        "_feeds": feeds,
    }


def branch_progression(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "`No metric progression yet.`"
    lines = []
    previous = None
    for row in rows:
        lo_adj = float(row.get("lo_adj") or 0)
        sharpe = float(row.get("sharpe") or 0)
        pnl = float(row.get("pnl") or 0)
        delta = ""
        if previous is not None:
            delta = (
                f" | dLo {lo_adj - previous['lo_adj']:+.3f}"
                f" | dSharpe {sharpe - previous['sharpe']:+.3f}"
                f" | dPnL {pnl - previous['pnl']:+.1f}%"
            )
        lines.append(
            f"1. `{row.get('round_id', '?')}` {row.get('decision', '?')} | Lo {lo_adj:.3f} | Sharpe {sharpe:.3f} | PnL {pnl:.1f}%{delta}"
        )
        previous = {"lo_adj": lo_adj, "sharpe": sharpe, "pnl": pnl}
    return "\n".join(lines)


def build_branch_snapshot_line(branch: dict) -> str:
    rows = branch["rows"]
    latest = rows[-1]
    first = rows[0]
    note = read_round_note(branch["branch_dir"], latest.get("round_id", ""))
    reason = (
        current_branch_hypothesis(branch["branch_dir"], rows)
        or note.get("failures")
        or latest.get("description", "")
    )
    return (
        f"1. `{branch['branch_id']}` -> `{latest.get('decision', 'pending')}` after {len(rows)} round(s). "
        f"Why: `{reason or 'not recorded'}`. Trend: Lo {float(first.get('lo_adj') or 0):.3f} -> {float(latest.get('lo_adj') or 0):.3f}, "
        f"Sharpe {float(first.get('sharpe') or 0):.3f} -> {float(latest.get('sharpe') or 0):.3f}, "
        f"PnL {float(first.get('pnl') or 0):.1f}% -> {float(latest.get('pnl') or 0):.1f}%, "
        f"signature `{note.get('failure_signature', 'unknown')}`, active `{note.get('signal_activity', 'n/a')}`."
    )


def session_next_step(
    session: Path,
    branches: list[dict],
    discovery: dict,
    readiness: dict,
) -> str:
    if not branches:
        return (
            f"Create the first branch with "
            f"`abel-strategy-discovery init-branch --session {session} --branch-id graph-v1`, "
            "then make the branch inputs explicit in `branch.yaml`, inspect the "
            "starter path through `prepare-branch` and `debug-branch`, and turn "
            "the engine into a branch-specific mechanism before you treat the "
            "first round as evidence."
        )
    leader = select_leader(branches)
    pending = [branch for branch in branches if not branch["rows"]]
    has_historical_keep = any(
        row.get("decision") == "keep"
        for branch in branches
        for row in branch["rows"]
    )
    keep = [
        branch
        for branch in branches
        if branch["rows"] and branch["rows"][-1].get("decision") == "keep"
    ]
    discard = [
        branch
        for branch in branches
        if branch["rows"] and branch["rows"][-1].get("decision") == "discard"
    ]
    if keep and discard:
        return f"Continue improving `{keep[-1]['branch_id']}` or branch from the discarded ideas now that both keep and discard outcomes are recorded."
    if keep:
        return f"Continue improving `{keep[-1]['branch_id']}` or open a sibling branch from its latest KEEP baseline."
    if pending:
        branch = pending[-1]
        debug_note = latest_debug_snapshot(branch["branch_dir"])
        if debug_note:
            return (
                f"Fix `{branch['branch_id']}` after the latest debug blocker "
                f"`{debug_note.get('failure_signature', 'unknown')}` "
                f"({debug_note.get('summary', 'see debug result')}), then rerun "
                f"`abel-strategy-discovery debug-branch --branch {branch['branch_dir']}` before recording the first round."
            )
        warning = build_readiness_warning(readiness)
        recommendations = ", ".join(readiness_recommendation_lines(readiness))
        guidance = (
            f"Confirm `{branch['branch_id']}/branch.yaml`, then use "
            f"`abel-strategy-discovery debug-branch --branch {branch['branch_dir']}` to wire the first real signal before recording a round."
        )
        if warning:
            suffix = (
                " Also revisit `backtest_start` first with "
                f"`abel-strategy-discovery set-backtest-start --session {session} --target-safe` ({recommendations})."
                if recommendations
                else " Also revisit `backtest_start` first with "
                f"`abel-strategy-discovery set-backtest-start --session {session} --date YYYY-MM-DD`."
            )
            return guidance + suffix
        return guidance
    if leader and leader["rows"]:
        branch_hypothesis = current_branch_hypothesis(leader["branch_dir"], leader["rows"])
        if not has_explicit_hypothesis(branch_hypothesis):
            return (
                f"Before the next round, add an explicit hypothesis to "
                f"`{leader['branch_id']}/branch.yaml`, then validate the next causal claim."
            )
        if has_historical_keep:
            return (
                f"No branch is currently ending on KEEP, but `{leader['branch_id']}` still carries the strongest "
                "history. Resume it from the latest credible baseline before opening a new sibling branch."
            )
        return (
            f"No KEEP baseline exists yet. Resume `{leader['branch_id']}` first because it is currently the strongest "
            "candidate, or open a sibling branch only if you have a genuinely different causal thesis."
        )
    return (
        "Open a new branch only if you have a genuinely different causal thesis; "
        "otherwise continue refining the current working candidate."
    )


def latest_recorded_hypothesis(branch: dict) -> str:
    for row in reversed(branch["rows"]):
        note = read_round_note(branch["branch_dir"], row.get("round_id", ""))
        hypothesis = (note.get("hypothesis") or "").strip()
        if has_explicit_hypothesis(hypothesis):
            return hypothesis
    return ""


def format_risks(risks: str) -> str:
    cleaned = (risks or "").strip()
    if not cleaned or cleaned == "none":
        return "- no acute validation failures recorded yet"
    return "\n".join(f"- {part.strip()}" for part in cleaned.split(";") if part.strip())


def load_branches(session: Path) -> list[dict]:
    branches_dir = session / "branches"
    branches = []
    if not branches_dir.exists():
        return branches
    discovery = load_discovery(session)
    for branch_dir in sorted(
        child for child in branches_dir.iterdir() if child.is_dir()
    ):
        branches.append(
            {
                "branch_id": branch_dir.name,
                "branch_dir": branch_dir,
                "ticker": discovery.get("ticker", session.parent.name.upper()),
                "rows": read_tsv_rows(branch_dir / "results.tsv"),
            }
        )
    return branches


def load_discovery(session: Path) -> dict:
    path = session / "discovery.json"
    if not path.exists():
        return {
            "ticker": session.parent.name.upper(),
            "source": "unknown",
            "parents": [],
            "blanket_new": [],
            "K_discovery": 0,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def load_readiness(session: Path) -> dict:
    path = session / READINESS_FILENAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def branch_spec_path(branch: Path) -> Path:
    return branch / BRANCH_SPEC_FILENAME


def dependencies_path(branch: Path) -> Path:
    return branch / "inputs" / DEPENDENCIES_FILENAME


def runtime_profile_path(branch: Path) -> Path:
    return branch / "inputs" / RUNTIME_PROFILE_FILENAME


def execution_constraints_path(branch: Path) -> Path:
    return branch / "inputs" / EXECUTION_CONSTRAINTS_FILENAME


def data_manifest_path(branch: Path) -> Path:
    return branch / "inputs" / DATA_MANIFEST_FILENAME


def context_guide_path(branch: Path) -> Path:
    return branch / "inputs" / CONTEXT_GUIDE_FILENAME


def probe_samples_path(branch: Path) -> Path:
    return branch / "inputs" / PROBE_SAMPLES_FILENAME


def branch_inputs_ready(branch: Path) -> bool:
    required = (
        dependencies_path(branch),
        runtime_profile_path(branch),
        execution_constraints_path(branch),
        data_manifest_path(branch),
        context_guide_path(branch),
        probe_samples_path(branch),
    )
    return all(path.exists() for path in required)


def load_branch_spec(branch: Path) -> dict:
    path = branch_spec_path(branch)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def write_branch_spec(branch: Path, payload: dict) -> None:
    branch_spec_path(branch).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def discovery_candidate_tickers(discovery: dict) -> list[str]:
    target = str(discovery.get("ticker") or "").strip().upper()
    ordered: list[str] = []
    for section in ("parents", "blanket_new", "children"):
        for item in discovery.get(section) or []:
            if isinstance(item, dict):
                ticker = str(item.get("ticker") or "").strip().upper()
            else:
                ticker = str(item or "").strip().upper()
            if not ticker or ticker == target or ticker in ordered:
                continue
            ordered.append(ticker)
    return ordered


def suggest_branch_drivers(discovery: dict, readiness: dict, *, limit: int = 5) -> list[str]:
    discovered = discovery_candidate_tickers(discovery)
    usable = set(readiness_usable_tickers(readiness))
    prioritized = [ticker for ticker in discovered if ticker in usable]
    fallback = [ticker for ticker in discovered if ticker not in usable]
    return (prioritized + fallback)[:limit]


def build_default_branch_spec(*, branch: Path, discovery: dict, readiness: dict) -> dict:
    suggested = suggest_branch_drivers(discovery, readiness, limit=5)
    selected = suggested[: min(3, len(suggested))]
    return {
        "version": 1,
        "branch_id": branch.name,
        "target": discovery.get("ticker", branch.parent.parent.parent.name.upper()),
        "hypothesis": "",
        "source_type": "causal",
        "method_family": "graph",
        "parent_branch_id": "",
        "requested_start": _get_backtest_start(discovery),
        "resolved_start_policy": "requested",
        "overlap_mode": "target_only",
        "selected_drivers": selected,
        "suggested_drivers": suggested,
        "data_requirements": {
            "timeframe": "1d",
            "fields": ["close"],
        },
    }


def branch_dependencies_payload(
    *,
    branch: Path,
    branch_spec: dict,
    target: str,
    selected_drivers: list[str],
    requested_start: str,
) -> dict:
    return {
        "version": 1,
        "branch_id": branch.name,
        "target": target,
        "selected_drivers": selected_drivers,
        "requested_start": requested_start,
        "overlap_mode": branch_spec.get("overlap_mode") or "target_only",
        "data_requirements": branch_spec.get("data_requirements") or {"timeframe": "1d"},
        "prepared_at": _now(),
    }


def build_runtime_profile_payload(*, target: str) -> dict:
    return {
        "profile": "daily",
        "target": target,
        "decision_event": "bar_close",
        "execution_delay_bars": 1,
        "return_basis": "close_to_close",
    }


def build_execution_constraints_payload(branch_spec: dict) -> dict:
    payload = {"long_only": bool(branch_spec.get("long_only", False))}
    position_bounds = branch_spec.get("position_bounds")
    if isinstance(position_bounds, (list, tuple)) and len(position_bounds) == 2:
        payload["position_bounds"] = [float(position_bounds[0]), float(position_bounds[1])]
    return payload


def build_data_manifest_payload(
    *,
    target: str,
    selected_drivers: list[str],
    cache_payload: dict,
    readiness: dict,
) -> dict:
    cache_results = {
        str(item.get("symbol") or "").strip().upper(): item
        for item in (cache_payload.get("results") or [])
        if isinstance(item, dict) and str(item.get("symbol") or "").strip()
    }
    readiness_results = {
        str(item.get("ticker") or "").strip().upper(): item
        for item in (readiness.get("results") or [])
        if isinstance(item, dict) and str(item.get("ticker") or "").strip()
    }
    feeds: list[dict[str, object]] = []
    ordered_symbols = [target] + [ticker for ticker in selected_drivers if ticker != target]
    adapter = str(cache_payload.get("adapter") or "abel")
    timeframe = str(cache_payload.get("timeframe") or "1d")
    profile = str(cache_payload.get("profile") or "daily")
    cache_root = cache_payload.get("cache_root")
    for symbol in ordered_symbols:
        cache_item = cache_results.get(symbol, {})
        readiness_item = readiness_results.get(symbol, {})
        feed_entry = {
            "name": "primary" if symbol == target else symbol,
            "symbol": symbol,
            "role": "target" if symbol == target else "driver",
            "adapter": adapter,
            "timeframe": timeframe,
            "profile": profile,
            "ok": bool(cache_item.get("ok", False)),
            "row_count": int(cache_item.get("row_count", 0) or 0),
            "available_range": cache_item.get("available_range") or {},
            "readiness_status": readiness_item.get("status", "unknown"),
            "covers_requested_start": bool(readiness_item.get("covers_requested_start", False)),
        }
        if cache_root:
            feed_entry["cache_root"] = cache_root
        feeds.append(feed_entry)
    return {
        "version": 1,
        "target": target,
        "selected_drivers": selected_drivers,
        "feeds": feeds,
    }


def build_probe_samples_payload(
    *,
    target: str,
    requested_start: str,
    data_manifest: dict,
) -> dict:
    feeds = data_manifest.get("feeds") or []
    target_feed = next(
        (item for item in feeds if item.get("role") == "target"),
        {},
    )
    available_range = (target_feed.get("available_range") or {}) if isinstance(target_feed, dict) else {}
    start = str(available_range.get("start") or requested_start or "").strip()
    end = str(available_range.get("end") or start or "").strip()
    samples: list[str] = []
    if start and end:
        try:
            dates = pd.date_range(start=start, end=end, periods=3, tz="UTC")
            samples = [str(ts.date()) for ts in dates]
        except Exception:
            samples = [item for item in [start, end] if item]
    return {
        "version": 1,
        "target": target,
        "requested_start": requested_start,
        "sample_decision_dates": samples,
    }


def build_context_guide_markdown(
    *,
    target: str,
    runtime_profile: dict,
    execution_constraints: dict,
    data_manifest: dict,
) -> str:
    feed_names = [
        str(item.get("name"))
        for item in (data_manifest.get("feeds") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    lines = [
        f"# {target} Branch Context Guide",
        "",
        "## Runtime",
        f"- profile: `{runtime_profile.get('profile', 'daily')}`",
        f"- decision_event: `{runtime_profile.get('decision_event', 'bar_close')}`",
        f"- execution_delay_bars: `{runtime_profile.get('execution_delay_bars', 1)}`",
        f"- return_basis: `{runtime_profile.get('return_basis', 'close_to_close')}`",
        "",
        "## Execution Constraints",
        f"- long_only: `{execution_constraints.get('long_only', False)}`",
        f"- position_bounds: `{execution_constraints.get('position_bounds', 'unbounded')}`",
        "",
        "## Available Feeds",
        f"- names: `{', '.join(feed_names) or 'primary only'}`",
        "- use `ctx.target.series(\"close\")` for target history",
        "- use `ctx.feed(\"<name>\").asof_series(\"close\")` for aligned driver history",
        "- use `ctx.points()` when you need path-sensitive cross-calendar logic",
        "",
        "## Suggested Loop",
        "1. Inspect `probe_samples.json` and `data_manifest.json`.",
        "2. Edit `engine.py` against `DecisionContext`.",
        "3. Run `abel-strategy-discovery debug-branch --branch ...` first to read semantic preflight.",
        "4. Only record a round after the branch expresses a real mechanism.",
    ]
    return "\n".join(lines) + "\n"


def branch_state_path(branch: Path) -> Path:
    return branch / BRANCH_STATE_FILENAME


def load_branch_state(branch: Path) -> dict:
    path = branch_state_path(branch)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_branch_state(branch: Path, payload: dict) -> None:
    branch_state_path(branch).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def session_state_path(session: Path) -> Path:
    return session / SESSION_STATE_FILENAME


def load_session_state(session: Path) -> dict:
    path = session_state_path(session)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_session_state(session: Path, payload: dict) -> None:
    session_state_path(session).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def readiness_warning_fingerprint(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    target_boundary = report.get("target_boundary") or {}
    coverage_hints = report.get("coverage_hints") or {}
    payload = {
        "requested_start": (report.get("requested_window") or {}).get("start"),
        "usable_count": summary.get("usable_count"),
        "start_covered_count": summary.get("start_covered_count"),
        "classification": target_boundary.get("classification"),
        "observed_first_timestamp": target_boundary.get("observed_first_timestamp"),
        "target_safe_start": coverage_hints.get("target_safe_start"),
        "dense_overlap_hint_start": coverage_hints.get("dense_overlap_hint_start"),
    }
    return json.dumps(payload, sort_keys=True)


def should_emit_readiness_warning(session: Path, readiness: dict) -> bool:
    warning = build_readiness_warning(readiness)
    if not warning:
        return False
    fingerprint = readiness_warning_fingerprint(readiness)
    if not fingerprint:
        return True
    state = load_session_state(session)
    if state.get("last_readiness_warning_fingerprint") == fingerprint:
        return False
    state["last_readiness_warning_fingerprint"] = fingerprint
    write_session_state(session, state)
    return True


def resolve_backtest_start_request(
    *,
    session: Path,
    explicit_date: str | None,
    use_target_safe: bool,
    use_coverage_hint: bool,
) -> tuple[str, str]:
    if explicit_date:
        return explicit_date, "explicit_date"
    report = load_readiness(session)
    coverage_hints = report.get("coverage_hints") or {}
    if use_target_safe:
        target_safe = coverage_hints.get("target_safe_start")
        if not target_safe:
            raise RuntimeError(
                "No target-safe readiness hint is available for this session."
            )
        return str(target_safe), "target_safe_hint"
    if use_coverage_hint:
        coverage_hint = coverage_hints.get("dense_overlap_hint_start")
        if not coverage_hint:
            raise RuntimeError(
                "No dense-overlap readiness hint is available for this session."
            )
        return str(coverage_hint), "coverage_hint"
    raise RuntimeError("A backtest start selector is required.")


def update_backtest_start(
    *,
    session: Path,
    backtest_start: str,
    source: str,
) -> tuple[dict, dict]:
    discovery = load_discovery(session)
    updated_discovery = dict(discovery)
    updated_discovery["backtest"] = {"start": backtest_start}
    readiness = refresh_data_readiness(
        session=session,
        discovery_data=updated_discovery,
        backtest_start=backtest_start,
    )
    with SessionLock(session):
        write_discovery(session, updated_discovery)
        readiness_path = session / READINESS_FILENAME
        if readiness:
            write_readiness(session, readiness)
        else:
            readiness_path.unlink(missing_ok=True)
        state = load_session_state(session)
        state.pop("last_readiness_warning_fingerprint", None)
        write_session_state(session, state)
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "backtest_start_updated",
                "branch_id": "",
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": (
                    f"Updated session backtest start to {backtest_start} via {source}"
                ),
                "artifact_path": "discovery.json",
            },
        )
        if readiness:
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
                        "Refreshed driver data readiness: "
                        f"{format_data_readiness_summary(readiness)}"
                    ),
                    "artifact_path": READINESS_FILENAME,
                },
            )
        render_session(session)
    return updated_discovery, readiness or {}


def current_branch_hypothesis(branch_dir: Path, rows: list[dict[str, str]] | None = None) -> str:
    branch_spec = load_branch_spec(branch_dir)
    spec_hypothesis = str(branch_spec.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(spec_hypothesis):
        return spec_hypothesis
    state = load_branch_state(branch_dir)
    hypothesis = str(state.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(hypothesis):
        return hypothesis
    if rows is None:
        rows = read_tsv_rows(branch_dir / "results.tsv")
    return latest_recorded_hypothesis({"branch_dir": branch_dir, "rows": rows})


def should_emit_missing_hypothesis_warning(branch: Path) -> bool:
    if has_explicit_hypothesis(current_branch_hypothesis(branch)):
        return False
    state = load_branch_state(branch)
    if state.get("missing_hypothesis_warning_emitted"):
        return False
    state["missing_hypothesis_warning_emitted"] = True
    write_branch_state(branch, state)
    return True


def persist_branch_hypothesis(branch: Path, hypothesis: str, *, source: str) -> None:
    branch_spec = load_branch_spec(branch)
    if branch_spec:
        branch_spec["hypothesis"] = hypothesis
        write_branch_spec(branch, branch_spec)
    state = load_branch_state(branch)
    state["hypothesis"] = hypothesis
    state["hypothesis_source"] = source
    state["hypothesis_updated_at"] = _now()
    state["missing_hypothesis_warning_emitted"] = False
    write_branch_state(branch, state)


def resolve_branch_hypothesis(
    branch: Path,
    rows: list[dict[str, str]],
    explicit_hypothesis: str,
) -> tuple[str, str]:
    hypothesis = str(explicit_hypothesis or "").strip()
    if has_explicit_hypothesis(hypothesis):
        return hypothesis, "round_argument"
    branch_spec = load_branch_spec(branch)
    spec_hypothesis = str(branch_spec.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(spec_hypothesis):
        return spec_hypothesis, "branch_yaml"
    state = load_branch_state(branch)
    stored = str(state.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(stored):
        return stored, "branch_state"
    recorded = latest_recorded_hypothesis({"branch_dir": branch, "rows": rows})
    if has_explicit_hypothesis(recorded):
        return recorded, "recorded_round"
    return "", "missing"


def latest_debug_snapshot(branch_dir: Path) -> dict[str, str]:
    state = load_branch_state(branch_dir)
    payload = state.get("last_debug")
    return dict(payload) if isinstance(payload, dict) else {}


def persist_debug_snapshot(branch: Path, payload: dict[str, str]) -> None:
    state = load_branch_state(branch)
    state["last_debug"] = payload
    write_branch_state(branch, state)


def build_debug_snapshot(
    *,
    completed: subprocess.CompletedProcess[str],
    session: Path,
    context_path: Path,
    debug_result_path: Path,
    backtest_start: str,
) -> dict[str, str]:
    result: dict[str, object] = {}
    if debug_result_path.exists():
        try:
            parsed = json.loads(debug_result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            result = parsed
    diagnostics = result.get("diagnostics") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    signal = diagnostics.get("signal") or {}
    if not isinstance(signal, dict):
        signal = {}
    failures = [
        str(item).strip()
        for item in (result.get("failures") or [])
        if str(item).strip()
    ]
    hints = [
        str(item).strip()
        for item in (diagnostics.get("hints") or [])
        if str(item).strip()
    ]
    fallback_error = (
        completed.stderr.strip()
        or completed.stdout.strip()
        or "Debug preflight did not produce a structured result."
    )
    summary = failures[0] if failures else fallback_error.splitlines()[-1]
    next_step = (
        hints[0]
        if hints
        else "Fix the semantic blocker in engine.py, then rerun `abel-strategy-discovery debug-branch`."
    )
    return {
        "updated_at": _now(),
        "returncode": str(completed.returncode),
        "verdict": str(result.get("verdict") or ("PASS" if completed.returncode == 0 else "ERROR")),
        "summary": summary,
        "failures": "; ".join(failures) or summary,
        "failure_signature": str(diagnostics.get("failure_signature") or "debug_runtime_check"),
        "runtime_stage": str(diagnostics.get("runtime_stage") or "debug_evaluate"),
        "signal_activity": (
            f"{int(signal.get('active_days', 0) or 0)} / {int(signal.get('total_days', 0) or 0)}"
        ),
        "diagnostic_hints": "; ".join(hints) or "none",
        "next_step": next_step,
        "context_mode": "injected",
        "context_path": str(context_path.relative_to(session)),
        "result_path": str(debug_result_path.relative_to(session)) if debug_result_path.exists() else "not recorded",
        "handoff_path": "not recorded",
        "report_path": "not recorded",
        "requested_start": backtest_start,
    }


def render_default_engine_template(discovery: dict, readiness: dict, session: Path) -> str:
    return ENGINE_TEMPLATE.format(
        ticker=discovery.get("ticker", session.parent.name.upper()),
        readiness_warning=build_readiness_warning(readiness) or "none",
        coverage_hints_text=", ".join(readiness_recommendation_lines(readiness)) or "none",
    )


def branch_uses_default_scaffold(
    branch: Path,
    discovery: dict,
    readiness: dict,
    session: Path,
) -> bool:
    engine = branch / "engine.py"
    if not engine.exists():
        return False
    return (
        engine.read_text(encoding="utf-8")
        == render_default_engine_template(discovery, readiness, session)
    )

def read_round_note(branch_dir: Path, round_id: str) -> dict[str, str]:
    if not round_id:
        return {}
    path = branch_dir / "rounds" / f"{round_id}.md"
    if not path.exists():
        return {}
    fields: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        for key in (
            "trigger",
            "hypothesis",
            "expected_signal",
            "change_summary",
            "time_spent_min",
            "failures",
            "failure_signature",
            "runtime_stage",
            "signal_activity",
            "diagnostic_hints",
            "summary",
            "next_step",
            "context_mode",
            "context_path",
            "result_path",
            "report_path",
            "handoff_path",
        ):
            prefix = f"- {key}: `"
            if line.startswith(prefix) and line.endswith("`"):
                fields[key] = line[len(prefix) : -1]
    return fields


def render_round_note(**kwargs) -> str:
    result = kwargs["result"]
    metrics = result.get("metrics", {})
    requested_window = result.get("requested_window", {})
    effective_window = result.get("effective_window", {})
    diagnostics = result.get("diagnostics") or {}
    signal = diagnostics.get("signal") or {}
    actions = kwargs.get("actions") or ["Executed raw causal-edge evaluation"]
    action_lines = "\n".join(f"1. {action}" for action in actions)
    return f"""# {kwargs["round_id"]}

## Basic Info

- date: `{_today()}`
- ticker: `{kwargs["ticker"]}`
- exp_id: `{kwargs["exp_id"]}`
- branch_id: `{kwargs["branch_id"]}`
- mode: `{kwargs["mode"]}`
- decision: `{kwargs["decision"]}`
- score: `{result.get("score", "?/?")}`
- verdict: `{result.get("verdict", "ERROR")}`
- requested_start: `{requested_window.get("start", kwargs.get("backtest_start", DEFAULT_BACKTEST_START))}`
- requested_end: `{requested_window.get("end") or "latest"}`
- effective_window: `{effective_window.get("start", "unknown")} -> {effective_window.get("end", "unknown")}`

## Goal

`{kwargs["description"]}`

## Inputs And Hypothesis

- input: `{kwargs.get("input_note") or f"Branch {kwargs['branch_id']} entering {kwargs['round_id']}."}`
- trigger: `{kwargs.get("trigger") or kwargs["description"]}`
- hypothesis: `{normalize_hypothesis_text(kwargs.get("hypothesis", ""))}`
- expected_signal: `{kwargs.get("expected_signal") or "Improve evaluation outcome versus the current working baseline."}`

## Actions

{action_lines}

## Key Results

- lo_adjusted: `{metrics.get("lo_adjusted", 0):.3f}`
- position_ic: `{metrics.get("position_ic", 0):.4f}`
- omega: `{metrics.get("omega", 0):.3f}`
- sharpe: `{metrics.get("sharpe", 0):.3f}`
- total_return: `{metrics.get("total_return", 0) * 100:.1f}%`
- max_dd: `{metrics.get("max_dd", 0) * 100:.1f}%`
- failures: `{"; ".join(result.get("failures", [])) or "none"}`

## Diagnostics

- failure_signature: `{diagnostics.get("failure_signature", "unknown")}`
- runtime_stage: `{diagnostics.get("runtime_stage", "unknown")}`
- signal_activity: `{signal.get("active_days", 0)} / {signal.get("total_days", 0)}`
- diagnostic_hints: `{"; ".join(diagnostics.get("hints", [])) or "none"}`

## Artifacts

- context_mode: `{kwargs.get("context_mode", "injected")}`
- context_path: `{kwargs.get("context_path", "not recorded")}`
- result_path: `{kwargs.get("result_path", "not recorded")}`
- report_path: `{kwargs.get("report_path", "not recorded")}`
- handoff_path: `{kwargs.get("handoff_path", "not recorded")}`

## Conclusion

- change_summary: `{kwargs.get("change_summary") or kwargs["description"]}`
- time_spent_min: `{kwargs.get("time_spent_min") or "not recorded"}`
- summary: `{kwargs.get("summary") or f"Recorded {result.get('verdict', 'ERROR')} {result.get('score', '?/?')}."}`
- next_step: `{kwargs.get("next_step") or "Review the branch README and decide whether to keep refining or open a new branch."}`
"""


def validate_edge_handoff(
    session: Path,
    branch_name: str,
    row: dict[str, str],
    failures: list[str],
) -> None:
    handoff_rel = row.get("handoff_path", "")
    if not handoff_rel:
        failures.append(f"{branch_name}: missing edge handoff path")
        return
    handoff_path = session / handoff_rel
    if not handoff_path.exists():
        return
    workspace_root = find_workspace_root(session)
    if workspace_root is not None:
        try:
            manifest = load_workspace_manifest(workspace_root)
            python_path = resolve_runtime_python(workspace_root, manifest)
        except Exception as exc:
            failures.append(
                f"{branch_name}: unable to resolve workspace runtime for handoff validation: {exc}"
            )
            return
        if python_path.exists():
            validate_edge_handoff_with_runtime(
                python_path=python_path,
                handoff_path=handoff_path,
                branch_name=branch_name,
                failures=failures,
            )
            return
    try:
        from causal_edge.research.handoff import (
            load_strategy_handoff,
            validate_strategy_handoff,
        )
    except Exception as exc:
        failures.append(
            f"{branch_name}: unable to import edge handoff validator: {exc}"
        )
        return
    try:
        payload = load_strategy_handoff(handoff_path)
    except Exception as exc:
        failures.append(f"{branch_name}: invalid edge handoff JSON: {exc}")
        return
    for reason in validate_strategy_handoff(payload, handoff_path=handoff_path):
        failures.append(f"{branch_name}: edge handoff rejected - {reason}")


def validate_edge_handoff_with_runtime(
    *,
    python_path: Path,
    handoff_path: Path,
    branch_name: str,
    failures: list[str],
) -> None:
    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from causal_edge.research.handoff import load_strategy_handoff, validate_strategy_handoff\n"
        "handoff_path = Path(sys.argv[1])\n"
        "payload = load_strategy_handoff(handoff_path)\n"
        "reasons = list(validate_strategy_handoff(payload, handoff_path=handoff_path))\n"
        "print(json.dumps({'ok': not reasons, 'reasons': reasons}))\n"
    )
    try:
        completed = subprocess.run(
            [str(python_path), "-c", script, str(handoff_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        failures.append(
            f"{branch_name}: workspace runtime handoff validation failed: {detail}"
        )
        return
    try:
        payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        failures.append(
            f"{branch_name}: workspace runtime returned invalid handoff validation output: {exc}"
        )
        return
    for reason in payload.get("reasons") or []:
        failures.append(f"{branch_name}: edge handoff rejected - {reason}")


def read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_manual_memory_rows(
    path: Path,
    header: list[str],
) -> list[dict[str, str]]:
    rows = read_tsv_rows(path)
    manual_rows: list[dict[str, str]] = []
    for row in rows:
        if row.get("origin") != "manual":
            continue
        manual_rows.append({key: str(row.get(key, "") or "") for key in header})
    return manual_rows


def next_manual_memory_id(rows: list[dict[str, str]], *, prefix: str) -> str:
    next_index = 1
    for row in rows:
        for key in ("insight_id", "link_id"):
            value = str(row.get(key, "") or "")
            marker = f"{prefix}-"
            if not value.startswith(marker):
                continue
            suffix = value[len(marker) :]
            if suffix.isdigit():
                next_index = max(next_index, int(suffix) + 1)
    return f"{prefix}-{next_index:03d}"


def write_tsv_header(path: Path, header: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writeheader()


def write_tsv_rows(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in header})


def append_tsv_row(path: Path, header: list[str], row: dict[str, str]) -> None:
    write_tsv_header(path, header)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writerow(row)


def write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def format_event_line(row: dict[str, str]) -> str:
    tail = " ".join(
        part
        for part in (
            row.get("branch_id", ""),
            row.get("round_id", ""),
            row.get("decision", ""),
        )
        if part
    )
    return f"1. `{row.get('timestamp', '')}` {row.get('event', '')} {tail} - {row.get('description', '')}".rstrip()


def _get_backtest_start(discovery: dict) -> str:
    backtest = discovery.get("backtest") or {}
    if isinstance(backtest, dict):
        start = backtest.get("start")
        if start:
            return str(start)
    return DEFAULT_BACKTEST_START


class SessionLock:
    def __init__(self, session: Path, timeout: float = 30.0):
        self.lock_path = session / ".alpha.lock"
        self.timeout = timeout
        self.fd: int | None = None

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(
                    str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR
                )
                os.write(self.fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError:
                if time.time() >= deadline:
                    raise TimeoutError(f"Timed out waiting for lock {self.lock_path}")
                time.sleep(0.1)

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


if __name__ == "__main__":
    raise SystemExit(main())
