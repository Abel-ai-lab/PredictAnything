"""Abel strategy discovery research narrative layer.

Organizes exploration sessions, records experimental process, and renders narrative
summaries on top of raw causal-edge evaluation outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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
AGENT_CONTEXT_FILENAME = "agent_context.md"
RESEARCH_JOURNAL_FILENAME = "research_journal.md"
EVIDENCE_LEDGER_FILENAME = "evidence_ledger.json"
FRONTIER_JSON_FILENAME = "frontier.json"
FRONTIER_MARKDOWN_FILENAME = "frontier.md"

EVIDENCE_INTENTS = {"candidate", "control", "diagnostic", "draft"}
INPUT_CLAIMS = {"graph_supported", "target_only", "supplement", "mixed"}
GRAPH_INPUT_CLAIMS = {"graph_supported", "supplement", "mixed"}
DECLARATION_PLACEHOLDER_VALUES = {"", "unspecified", "unknown", "draft", "todo", "tbd"}
DECLARATION_REQUIRED_FIELDS = [
    "hypothesis",
    "evidence_intent",
    "input_claim",
    "mechanism_family",
    "invalidation_condition",
    "requested_start",
]
MODEL_FAMILIES = {
    "rule_signal",
    "linear_model",
    "tree_model",
    "learned_model",
    "ensemble",
    "hybrid",
    "unspecified",
}
COMPLEXITY_CLASSES = {
    "simple_signal",
    "interaction",
    "regime",
    "portfolio",
    "learned_model",
    "hybrid",
    "unspecified",
}
EXPLORATION_ROLES = {
    "candidate",
    "control",
    "ablation",
    "expansion_probe",
    "refinement",
    "diagnostic",
    "unspecified",
}
CHANGED_DIMENSIONS = {
    "drivers",
    "mechanism",
    "model_family",
    "complexity",
    "sizing",
    "thresholds",
    "filters",
    "window",
    "implementation",
}
BROAD_CHANGED_DIMENSIONS = {"drivers", "mechanism", "model_family", "complexity"}
LOCAL_CHANGED_DIMENSIONS = {"sizing", "thresholds", "filters", "window", "implementation"}
INPUT_BREADTH_ROUND_THRESHOLD = 8
GRAPH_PRIORITY_ROUND_MINIMUM = 3
JOURNAL_GENERATED_HEADER_END = "<!-- ABEL_GENERATED_HEADER_END -->"
JOURNAL_REFERENCE_RE = re.compile(
    r"(ledger:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+|"
    r"frontier:[A-Za-z0-9_.-]+|"
    r"frontier\.md|"
    r"evidence_ledger\.json|"
    r"artifact:[^\s)]+|"
    r"branches/[^\s)]+)"
)

EXPERIMENT_METADATA_ENV = {
    "protocol_id": "ABEL_EXPERIMENT_PROTOCOL_ID",
    "experiment_mode": "ABEL_EXPERIMENT_MODE",
    "round_budget": "ABEL_EXPERIMENT_ROUND_BUDGET",
    "abel_skills_commit": "ABEL_SKILLS_COMMIT",
    "abel_edge_commit": "ABEL_EDGE_COMMIT",
}

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

ENGINE_TEMPLATE = '''"""Research engine for {ticker}. Replace the starter baseline when the branch thesis is ready.

Default backtest behavior should follow branch.yaml first and the injected context second.
If provided, self.context contains workspace/session/branch/discovery/readiness metadata from Abel strategy discovery.
Use branch.yaml to make the critical research choices explicit:
  - hypothesis
  - evidence_intent
  - input_claim
  - mechanism_family
  - invalidation_condition
  - target
  - requested_start
  - selected_inputs
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
    discovery_group = init_session.add_mutually_exclusive_group()
    discovery_group.add_argument(
        "--discover",
        dest="discover",
        action="store_true",
        default=True,
        help="Run live Abel discovery and persist it into discovery.json (default)",
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
        "--changed-dimension",
        action="append",
        default=[],
        choices=sorted(CHANGED_DIMENSIONS),
        help="Factual dimension changed in this round; repeat for multiple dimensions",
    )
    run_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run causal-edge evaluate (defaults to the workspace python when available)",
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
        "--base-url",
        default="",
        help="Abel router base URL. Defaults to ABEL_ROUTER_BASE_URL or CAP_ROUTER_BASE_URL.",
    )
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
        print(f"  journal: {session / RESEARCH_JOURNAL_FILENAME}")
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
            for line in readiness_coverage_hint_lines(readiness):
                print(f"  {line}")
            warning = build_readiness_warning(readiness)
            if warning:
                print(f"  warning: {warning}")
        else:
            print("  discovery_source: pending (live discovery not run)")
        print("")
        print("From here:")
        for line in render_breadth_first_start_lines(session):
            print(f"  {line}")
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
        for line in readiness_coverage_hint_lines(readiness):
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
    if args.command == "upload-dashboard-bundle":
        return upload_skill_dashboard_bundle(args)
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
            print("  abel-strategy-discovery init-session --ticker <TICKER> --exp-id <session-id>  # runs live graph discovery by default")
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
    print(
        "  # once doctor is ready: init-session -> declare branches -> "
        "use frontier facts and research_journal.md to guide pivots"
    )
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


def render_breadth_first_start_lines(session: Path) -> list[str]:
    return [
        "graph-first research loop:",
        f"edit {session / RESEARCH_JOURNAL_FILENAME}",
        f"abel-strategy-discovery init-branch --session {session} --branch-id <family-a-branch>",
        f"abel-strategy-discovery init-branch --session {session} --branch-id <family-b-branch>",
        "edit each branch.yaml with graph/input hypotheses and agent-chosen mechanism-family declarations",
        "after evidence accumulates, update research_journal.md with evidence-linked reflection before deep local refinement",
    ]


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
    ensure_research_journal(session)
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
    selected_inputs = branch_selected_inputs(branch_spec)
    symbols = [target]
    for ticker in selected_inputs:
        if ticker not in symbols:
            symbols.append(ticker)

    requested_start = str(
        branch_spec.get("requested_start") or _get_backtest_start(discovery)
    ).strip()
    data_requirements = branch_spec.get("data_requirements") or {}
    cache_adapter = str(data_requirements.get("adapter") or "abel")
    cache_path = str(data_requirements.get("path") or "").strip()
    advisory_lines = branch_runtime_advisory_lines(
        branch_requested_start=requested_start,
        discovery=discovery,
        readiness=readiness,
    )
    dependencies = branch_dependencies_payload(
        branch=branch,
        branch_spec=branch_spec,
        target=target,
        selected_inputs=selected_inputs,
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
        cache_adapter,
        "--start",
        requested_start,
        "--timeframe",
        str(data_requirements.get("timeframe") or "1d"),
        "--limit",
        str(args.cache_limit),
        "--output-json",
        str(output_path),
    ]
    if cache_path:
        command.extend(["--path", cache_path])
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
        selected_inputs=selected_inputs,
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
    print(f"  selected_inputs: {len(selected_inputs)}")
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


def build_skill_dashboard_bundle(branch: Path, *, uploaded_at: str | None = None) -> dict:
    branch = resolve_workspace_arg_path(branch).resolve()
    session = branch.parent.parent
    discovery = load_discovery(session)
    render_session(session)
    frontier = load_json_object(session / FRONTIER_JSON_FILENAME)
    ledger = load_json_object(session / EVIDENCE_LEDGER_FILENAME)
    if not ledger:
        ledger = build_evidence_ledger(session, discovery, load_branches(session))
        frontier = build_frontier(ledger, journal_status=build_research_journal_status(session, ledger=ledger, frontier={}))
    branch_spec = load_branch_spec(branch)
    branch_state = load_branch_state(branch)
    rows = read_tsv_rows(branch / "results.tsv")
    events = read_tsv_rows(session / "events.tsv")

    created_at = str(branch_state.get("created_at") or "").strip() or _first_branch_event_time(
        events,
        branch_id=branch.name,
    )
    start_at = require_timezone_aware_iso(created_at or _now(), field_name="startAt")
    end_at = require_timezone_aware_iso(uploaded_at or _now(), field_name="endAt")
    if datetime.fromisoformat(end_at) <= datetime.fromisoformat(start_at):
        raise RuntimeError("skill dashboard upload requires endAt after startAt")

    latest = rows[-1] if rows else {}
    latest_note = read_round_note(branch, latest.get("round_id", ""))
    branch_payload = {
        "id": branch.name,
        "targetAsset": dashboard_branch_target_asset(branch_spec, discovery),
        "targetNode": dashboard_branch_target_node(branch_spec, discovery),
        "requestedStart": branch_requested_start(branch, discovery),
        "selectedInputs": branch_selected_inputs(branch_spec),
        "sourceType": str(branch_spec.get("input_claim") or "unspecified"),
        "methodFamily": str(branch_spec.get("model_family") or "").strip(),
        "mechanismFamily": str(branch_spec.get("mechanism_family") or "").strip(),
        "complexityClass": str(branch_spec.get("complexity_class") or "").strip(),
        "status": str(latest.get("decision") or branch_spec.get("status") or "exploratory"),
        "thesis": current_branch_hypothesis(branch, rows) or latest_note.get("hypothesis", ""),
        "latestEvidenceLabel": dashboard_latest_evidence_label(
            ledger,
            branch_id=branch.name,
            round_id=latest.get("round_id", ""),
        ),
    }

    discovered_drivers = ordered_unique_upper(ledger.get("discovered_drivers") or [])
    graph_priority = frontier.get("graph_priority") if isinstance(frontier.get("graph_priority"), dict) else {}
    input_realization = frontier.get("input_realization") if isinstance(frontier.get("input_realization"), dict) else {}
    research_reflection = frontier.get("research_reflection") if isinstance(frontier.get("research_reflection"), dict) else {}
    journal_coverage = frontier.get("journal_coverage") if isinstance(frontier.get("journal_coverage"), dict) else {}
    return {
        "sessionId": session.name,
        "branchId": branch.name,
        "startAt": start_at,
        "endAt": end_at,
        "payload": {
            "session": {
                "id": session.name,
                "ticker": discovery.get("ticker", session.parent.name.upper()),
                "targetNode": dashboard_branch_target_node(branch_spec, discovery),
                "graphDiscoverySource": ledger.get("graph_discovery_source", discovery.get("source", "unknown")),
                "graphDiscoveryK": ledger.get("graph_discovery_k", discovery.get("K_discovery", 0)),
                "discoveredDrivers": discovered_drivers,
                "frontierRows": frontier.get("row_count", 0),
                "graphFirstUncovered": bool(graph_priority.get("graph_first_uncovered")),
                "researchReflection": research_reflection,
                "journalCoverage": journal_coverage,
                "inputRealization": input_realization,
            },
            "branch": branch_payload,
            "rounds": skill_dashboard_rounds(branch, rows, ledger),
            "branchInsights": skill_dashboard_branch_insights(
                session=session,
                ledger=ledger,
                frontier=frontier,
                branch_id=branch.name,
            ),
            "episodes": skill_dashboard_episodes(events, branch_id=branch.name),
        },
    }


def post_skill_dashboard_bundle(
    *,
    base_url: str,
    api_key: str,
    bundle: dict,
    opener=urlopen,
    timeout: int = 60,
) -> dict:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise RuntimeError("Missing Abel router base URL")
    normalized_api_key = str(api_key or "").strip()
    if not normalized_api_key:
        raise RuntimeError("Missing Abel API key")
    body = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{normalized_base_url}/web/skill-dashboard/bundles",
        data=body,
        headers={"Content-Type": "application/json", "api-key": normalized_api_key},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Skill dashboard upload failed: HTTP {exc.code}: {detail}") from exc
    return json.loads(raw)


def upload_skill_dashboard_bundle(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    bundle = build_skill_dashboard_bundle(branch)
    if args.output_json:
        output_path = resolve_workspace_arg_path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dry_run:
        print(json.dumps(bundle, indent=2, ensure_ascii=False))
        return 0

    workspace_root = find_workspace_root(branch)
    base_url = resolve_skill_dashboard_base_url(args.base_url)
    api_key = resolve_skill_dashboard_api_key(args.api_key, workspace_root=workspace_root)
    result = post_skill_dashboard_bundle(base_url=base_url, api_key=api_key, bundle=bundle)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def resolve_skill_dashboard_base_url(value: str | None) -> str:
    base_url = (
        str(value or "").strip()
        or os.getenv("ABEL_ROUTER_BASE_URL", "").strip()
        or os.getenv("CAP_ROUTER_BASE_URL", "").strip()
    )
    if not base_url:
        raise RuntimeError("Set --base-url or ABEL_ROUTER_BASE_URL before uploading dashboard bundles")
    return base_url


def resolve_skill_dashboard_api_key(value: str | None, *, workspace_root: Path | None) -> str:
    explicit = str(value or "").strip()
    if explicit:
        return explicit
    env_token = (os.getenv("ABEL_API_KEY") or os.getenv("CAP_API_KEY") or "").strip()
    if env_token:
        return env_token
    if workspace_root is not None:
        auth_env_file = resolve_runtime_auth_env_file(workspace_root)
        if auth_env_file is not None:
            env_values = read_env_file_values(auth_env_file)
            token = (env_values.get("ABEL_API_KEY") or env_values.get("CAP_API_KEY") or "").strip()
            if token:
                return token
    raise RuntimeError("Set --api-key or run abel-auth before uploading dashboard bundles")


def skill_dashboard_rounds(branch: Path, rows: list[dict[str, str]], ledger: dict) -> list[dict]:
    ledger_rows = {
        str(row.get("round_id") or ""): row
        for row in (ledger.get("rows") or [])
        if isinstance(row, dict) and row.get("branch_id") == branch.name
    }
    rounds = []
    for row in rows:
        round_id = str(row.get("round_id") or "").strip()
        note = read_round_note(branch, round_id)
        evidence = ledger_rows.get(round_id, {})
        rounds.append(
            {
                "roundId": round_id,
                "mode": row.get("mode", ""),
                "decision": row.get("decision", ""),
                "verdict": row.get("verdict", ""),
                "score": row.get("score", ""),
                "description": row.get("description", ""),
                "summary": note.get("summary", ""),
                "hypothesis": note.get("hypothesis", ""),
                "expectedSignal": note.get("expected_signal", ""),
                "changeSummary": note.get("change_summary", ""),
                "changedDimensions": parse_changed_dimensions(note.get("changed_dimensions", "")),
                "nextStep": note.get("next_step", ""),
                "evidenceLabel": evidence.get("evidence_label", ""),
                "explorationClass": evidence.get("derived_exploration_class", ""),
                "declaredInputs": evidence.get("declared_selected_inputs", []),
                "actualReads": evidence.get("actual_auxiliary_reads", []),
                "inputRealization": evidence.get("input_realization", {}),
                "contextRef": evidence.get("context_ref", ""),
                "resultRef": evidence.get("result_ref", ""),
                "reportRef": evidence.get("report_ref", ""),
            }
        )
    return rounds


def skill_dashboard_branch_insights(
    *,
    session: Path,
    ledger: dict,
    frontier: dict,
    branch_id: str,
) -> list[dict]:
    path = session / RESEARCH_JOURNAL_FILENAME
    if not path.exists():
        return []
    insights = []
    for line_no, line in journal_note_line_items(path.read_text(encoding="utf-8").splitlines()):
        summary = line.strip().lstrip("-").strip()
        if not summary:
            continue
        refs = extract_journal_evidence_refs(summary)
        matching_refs = [
            ref
            for ref in refs
            if journal_reference_matches_branch(
                ref,
                branch_id=branch_id,
                session=session,
                ledger=ledger,
                frontier=frontier,
            )
        ]
        if not matching_refs:
            continue
        insights.append(
            {
                "id": f"journal-line-{line_no}",
                "roundId": first_round_id_from_refs(matching_refs, branch_id=branch_id),
                "kind": "research_journal",
                "summary": summary,
                "reusableRule": "",
                "confidence": "",
                "origin": "research_journal",
                "evidenceRefs": matching_refs,
            }
        )
    return insights


def skill_dashboard_episodes(rows: list[dict[str, str]], *, branch_id: str) -> list[dict]:
    return [
        {
            "timestamp": row.get("timestamp", ""),
            "event": row.get("event", ""),
            "roundId": row.get("round_id", ""),
            "mode": row.get("mode", ""),
            "verdict": row.get("verdict", ""),
            "decision": row.get("decision", ""),
            "summary": row.get("description", ""),
            "artifactPath": row.get("artifact_path", ""),
        }
        for row in rows
        if row.get("branch_id") == branch_id
    ]


def dashboard_round_is_candidate(*, session: Path, branch_id: str, round_id: str) -> bool:
    ledger = load_json_object(session / EVIDENCE_LEDGER_FILENAME)
    for row in ledger.get("rows") or []:
        if (
            isinstance(row, dict)
            and row.get("branch_id") == branch_id
            and row.get("round_id") == round_id
            and row.get("evidence_label") == "candidate_causal_evidence"
        ):
            return True
    return False


def dashboard_latest_evidence_label(ledger: dict, *, branch_id: str, round_id: str) -> str:
    for row in ledger.get("rows") or []:
        if (
            isinstance(row, dict)
            and row.get("branch_id") == branch_id
            and row.get("round_id") == round_id
        ):
            return str(row.get("evidence_label") or "")
    return ""


def journal_reference_matches_branch(
    ref: str,
    *,
    branch_id: str,
    session: Path,
    ledger: dict,
    frontier: dict,
) -> bool:
    if not resolve_journal_reference(ref, session=session, ledger=ledger, frontier=frontier):
        return False
    if ref.startswith("ledger:"):
        parts = ref.split(":")
        return len(parts) >= 3 and parts[1].strip() == branch_id
    if ref.startswith("branches/"):
        return ref.split("/")[1:2] == [branch_id]
    return False


def first_round_id_from_refs(refs: list[str], *, branch_id: str) -> str:
    for ref in refs:
        if ref.startswith("ledger:"):
            parts = ref.split(":")
            if len(parts) >= 3 and parts[1].strip() == branch_id:
                return parts[2].strip()
    return ""


def dashboard_branch_target_asset(branch_spec: dict, discovery: dict) -> str:
    return str(
        branch_spec.get("target_asset")
        or discovery.get("target_asset")
        or discovery.get("ticker")
        or ""
    ).strip().upper()


def dashboard_branch_target_node(branch_spec: dict, discovery: dict) -> str:
    value = str(branch_spec.get("target_node") or discovery.get("target_node") or "").strip()
    if value:
        return value
    asset = dashboard_branch_target_asset(branch_spec, discovery)
    return f"{asset}.price" if asset else ""


def _first_branch_event_time(rows: list[dict[str, str]], *, branch_id: str) -> str:
    for row in rows:
        if row.get("branch_id") == branch_id and row.get("timestamp"):
            return str(row["timestamp"])
    return ""


def require_timezone_aware_iso(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"{field_name} must include timezone")
    return parsed.isoformat()


def read_env_file_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


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
    with SessionLock(session):
        render_session(session)
    blocking_missing_journal = journal_coverage_missing_rounds(session)
    if blocking_missing_journal:
        print(
            "Journal required before next recorded round: "
            f"missing_journal_rounds={', '.join(blocking_missing_journal)}. "
            f"Update {RESEARCH_JOURNAL_FILENAME} with evidence-linked notes for each missing ledger round.",
            file=sys.stderr,
        )
        return 2
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
    starter_scaffold = branch_uses_default_scaffold(branch, discovery, readiness, session)
    if starter_scaffold:
        print(
            "The branch is still using the untouched starter scaffold. "
            "The run can proceed, but the evidence ledger will treat it as diagnostic-only.",
            file=sys.stderr,
        )
        print(
            "Interpretation: evidence_boundary -> scaffold execution is useful for wiring, not candidate evidence.",
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
        for line in readiness_coverage_hint_lines(readiness):
            print(f"Coverage hint: {line}", file=sys.stderr)
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
        for line in readiness_coverage_hint_lines(readiness):
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
            "Recording a workflow blocker row for the evidence ledger.",
            file=sys.stderr,
        )
        if workspace_root is not None:
            print(
                f"Alpha expected workspace auth at {resolve_workspace_env_file(workspace_root)} "
                "and exported it through ABEL_AUTH_ENV_FILE for this run.",
                file=sys.stderr,
            )
        with SessionLock(session):
            record_workflow_blocker_round(
                session=session,
                branch=branch,
                round_id=round_id,
                args=args,
                completed=completed,
                context_path=context_path,
                result_path=result_path,
                report_path=report_path,
                handoff_path=handoff_path,
                backtest_start=backtest_start,
                effective_hypothesis=effective_hypothesis,
                hypothesis_source=hypothesis_source,
                discovery=discovery,
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
            changed_dimensions=getattr(args, "changed_dimension", []),
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
    for line in graph_priority_warning_lines(session):
        print(f"Exploration protocol: {line}")
    for line in journal_coverage_warning_lines(session):
        print(f"Journal required: {line}")
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
    if decision == "keep" and dashboard_round_is_candidate(
        session=session,
        branch_id=branch.name,
        round_id=round_id,
    ):
        print("")
        print("Dashboard upload:")
        print(
            "  "
            f"abel-strategy-discovery upload-dashboard-bundle --branch {branch} "
            "--base-url <router-base-url>"
        )
    return 0


def record_workflow_blocker_round(
    *,
    session: Path,
    branch: Path,
    round_id: str,
    args: argparse.Namespace,
    completed: subprocess.CompletedProcess[str],
    context_path: Path,
    result_path: Path,
    report_path: Path,
    handoff_path: Path,
    backtest_start: str,
    effective_hypothesis: str,
    hypothesis_source: str,
    discovery: dict,
) -> None:
    detail = (completed.stderr or completed.stdout or "").strip()
    failure_signature, runtime_stage = classify_workflow_failure(detail)
    result = build_workflow_blocker_result(
        detail=detail,
        returncode=completed.returncode,
        failure_signature=failure_signature,
        runtime_stage=runtime_stage,
    )
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    report_path.write_text(
        "# Workflow Blocker\n\n"
        f"- failure_signature: `{failure_signature}`\n"
        f"- runtime_stage: `{runtime_stage}`\n"
        f"- returncode: `{completed.returncode}`\n",
        encoding="utf-8",
    )
    handoff_path.write_text(
        json.dumps(
            {
                "contract": "abel-strategy-discovery.workflow-blocker/v1",
                "ok": False,
                "verdict": "ERROR",
                "failure_signature": failure_signature,
                "runtime_stage": runtime_stage,
                "edge_result_path": str(result_path.relative_to(session)),
                "edge_report_path": str(report_path.relative_to(session)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    round_note = branch / "rounds" / f"{round_id}.md"
    round_note.write_text(
        render_round_note(
            ticker=discovery.get("ticker", session.parent.name.upper()),
            exp_id=session.name,
            branch_id=branch.name,
            round_id=round_id,
            mode=args.mode,
            decision="blocked",
            description=args.description,
            result=result,
            backtest_start=backtest_start,
            input_note=args.input_note,
            hypothesis=effective_hypothesis,
            expected_signal=args.expected_signal,
            trigger=args.trigger,
            change_summary=args.change_summary,
            changed_dimensions=getattr(args, "changed_dimension", []),
            time_spent_min=args.time_spent_min,
            summary="Workflow blocker recorded before edge evaluation completed.",
            next_step="",
            actions=args.action + [f"hypothesis_source={hypothesis_source}"],
            context_mode="injected",
            context_path=str(context_path.relative_to(session)),
            result_path=str(result_path.relative_to(session)),
            report_path=str(report_path.relative_to(session)),
            handoff_path=str(handoff_path.relative_to(session)),
        ),
        encoding="utf-8",
    )
    append_tsv_row(
        branch / "results.tsv",
        RESULTS_HEADER,
        {
            "exp_id": session.name,
            "ticker": discovery.get("ticker", session.parent.name.upper()),
            "branch_id": branch.name,
            "round_id": round_id,
            "decision": "blocked",
            "lo_adj": "0.000",
            "ic": "0.0000",
            "omega": "0.000",
            "sharpe": "0.000",
            "max_dd": "0.0000",
            "pnl": "0.0",
            "K": "0",
            "score": "0/0",
            "verdict": "ERROR",
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
            "event": "round_workflow_blocked",
            "branch_id": branch.name,
            "round_id": round_id,
            "mode": args.mode,
            "verdict": "ERROR",
            "decision": "blocked",
            "description": args.description,
            "artifact_path": str(result_path.relative_to(session)),
        },
    )
    render_session(session)


def build_workflow_blocker_result(
    *,
    detail: str,
    returncode: int,
    failure_signature: str,
    runtime_stage: str,
) -> dict:
    message = detail or "Edge evaluation did not produce a result JSON."
    return {
        "verdict": "ERROR",
        "score": "0/0",
        "failures": [message],
        "warnings": [],
        "metrics": {},
        "K": 0,
        "profile": "unknown",
        "diagnostics": {
            "failure_signature": failure_signature,
            "runtime_stage": runtime_stage,
            "signal": {"active_days": 0, "total_days": 0},
            "hints": [],
            "returncode": returncode,
        },
        "runtime_facts": {
            "contract": "abel-strategy-discovery.workflow-blocker/v1",
            "verdict": "ERROR",
            "semantic_verdict": "missing",
            "runtime_stage": runtime_stage,
            "workflow_status": "not_completed",
            "implementation_contract": "unknown",
            "profile": "unknown",
            "requested_window": {},
            "effective_window": {},
            "read_summary": {
                "target_reads": [],
                "auxiliary_reads": [],
                "read_count": 0,
                "decision_count": 0,
            },
            "prepared_inputs": {
                "selected_inputs": [],
                "traced_inputs": [],
                "effective_window": {},
                "issues": [],
            },
            "temporal_visibility": {"issue_kinds": [], "has_error": False},
        },
    }


def classify_workflow_failure(detail: str) -> tuple[str, str]:
    text = str(detail or "").lower()
    if "api key" in text or "auth" in text or "unauthorized" in text:
        return "auth_missing", "data_access"
    if "connection" in text or "timeout" in text or "network" in text or "remote end" in text:
        return "network_error", "data_access"
    if "cache" in text or "no usable target bars" in text or "target bars" in text:
        return "cache_missing", "data_access"
    return "edge_command_failed", "workflow"


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
    ensure_research_journal(session)
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
    journal_status = build_research_journal_status(session, ledger=ledger, frontier=frontier)
    print(
        f"Session: {session.name} ({discovery.get('ticker', session.parent.name.upper())})"
    )
    print(f"Branches: {len(branches)}")
    print(f"Total rounds: {sum(len(branch['rows']) for branch in branches)}")
    print(
        "Research journal: "
        f"{journal_status.get('resolved_evidence_reference_count', 0)} evidence-linked refs"
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
        graph_priority = frontier.get("graph_priority") or {}
        reflection = frontier.get("research_reflection") or {}
        journal_coverage = frontier.get("journal_coverage") or {}
        print(
            "Evidence frontier: "
            f"rows={frontier.get('row_count', 0)} "
            f"candidate_causal={labels.get('candidate_causal_evidence', 0)} "
            f"target_control={labels.get('target_control_evidence', 0)} "
            f"workflow_blockers={frontier.get('workflow_blockers', 0)} "
            f"graph_first_uncovered={str(graph_priority.get('graph_first_uncovered', False)).lower()} "
            f"research_reflection_due={str(reflection.get('research_reflection_due', False)).lower()} "
            f"journal_coverage_complete={str(journal_coverage.get('journal_coverage_complete', False)).lower()}"
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
        EVIDENCE_LEDGER_FILENAME,
        FRONTIER_JSON_FILENAME,
        FRONTIER_MARKDOWN_FILENAME,
        AGENT_CONTEXT_FILENAME,
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
    journal_coverage = (
        frontier.get("journal_coverage")
        if isinstance(frontier.get("journal_coverage"), dict)
        else {}
    )
    missing_rounds = list(journal_coverage.get("missing_journal_rounds") or [])
    if missing_rounds:
        failures.append(
            "journal coverage incomplete: "
            f"missing_journal_rounds={', '.join(str(item) for item in missing_rounds)}"
        )


def graph_priority_warning_lines(session: Path) -> list[str]:
    frontier = load_json_object(session / FRONTIER_JSON_FILENAME)
    graph_priority = frontier.get("graph_priority") if isinstance(frontier.get("graph_priority"), dict) else {}
    if not graph_priority:
        return []
    lines: list[str] = []
    if graph_priority.get("graph_discovery_missing"):
        lines.append(
            "graph_discovery_missing=true "
            f"graph_discovery_source={graph_priority.get('graph_discovery_source', 'unknown')} "
            f"graph_discovery_k={graph_priority.get('graph_discovery_k', 0)} "
            f"target_only_saturation={str(graph_priority.get('target_only_saturation', False)).lower()}"
        )
    if graph_priority.get("graph_first_uncovered"):
        lines.append(
            "graph_first_uncovered=true "
            f"graph_discovery_k={graph_priority.get('graph_discovery_k', 0)} "
            f"target_only_saturation={str(graph_priority.get('target_only_saturation', False)).lower()}"
        )
    return lines


def journal_coverage_missing_rounds(session: Path) -> list[str]:
    frontier = load_json_object(session / FRONTIER_JSON_FILENAME)
    journal_coverage = (
        frontier.get("journal_coverage")
        if isinstance(frontier.get("journal_coverage"), dict)
        else {}
    )
    return [str(item) for item in journal_coverage.get("missing_journal_rounds") or []]


def journal_coverage_warning_lines(session: Path) -> list[str]:
    missing_rounds = journal_coverage_missing_rounds(session)
    if not missing_rounds:
        return []
    return [
        "journal_coverage_complete=false "
        f"missing_journal_rounds={', '.join(missing_rounds)} "
        f"required_action=update_{RESEARCH_JOURNAL_FILENAME}_with_round_insights"
    ]


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
    recorded_round_count = sum(len(branch["rows"]) for branch in branches)
    debugged_branches = [
        branch for branch in branches if latest_debug_snapshot(branch["branch_dir"])
    ]
    frontier = load_json_object(session / FRONTIER_JSON_FILENAME)
    executive = "No validated evidence rows yet."
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
            executive += " Evidence labels remain empty until a runtime result is recorded."
    elif recorded_round_count:
        executive = (
            f"Session has {len(branches)} branch(es) and {recorded_round_count} recorded round(s): "
            f"{len(keep_branches)} keep and {len(discard_branches)} discard. "
            "Evidence labels, coverage, and runtime facts are summarized below without ranking branches by metrics."
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
                            f"Why: `{current_branch_hypothesis(branch['branch_dir'], branch['rows']) or latest_debug_snapshot(branch['branch_dir']).get('summary', 'not recorded')}`."
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

## Evidence State

This session tracks {len(branches)} branch(es). Current outcomes: {len(keep_branches)} keep, {len(discard_branches)} discard, {len(branches) - len(keep_branches) - len(discard_branches)} pending.

{render_session_frontier_summary(frontier)}

## Branches

{branch_lines}

## Branch Outcome Snapshot

{snapshot_lines}

## Recent Activity

{activity_lines}
"""


def build_branch_readme(branch: dict, latest_note: dict[str, str], exp_id: str) -> str:
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    debug_note = latest_debug_snapshot(branch["branch_dir"])
    diagnostics_note = latest_note or debug_note
    keep_rows = [row for row in rows if row.get("decision") == "keep"]
    branch_hypothesis = current_branch_hypothesis(branch["branch_dir"], rows)
    parent_branch_id = branch_parent_branch_id(branch["branch_dir"])
    declaration = branch_declaration_status_for_branch(branch["branch_dir"])
    protocol_gaps = ", ".join(str(item) for item in declaration["protocol_gaps"]) or "none"
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
- evidence_intent: `{declaration["evidence_intent"] or "not_declared"}`
- input_claim: `{declaration["input_claim"] or "not_declared"}`
- mechanism_family: `{declaration["mechanism_family"] or "not_declared"}`
- declaration_protocol_complete: `{declaration["protocol_complete"]}`
- declaration_gaps: `{protocol_gaps}`
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
- evidence_label_source: `{EVIDENCE_LEDGER_FILENAME}`

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


def build_promotion_bundle_readme(
    *,
    branch: Path,
    branch_spec: dict,
    latest: dict[str, str],
) -> str:
    selected = format_simple_nodes(branch_selected_inputs(branch_spec), limit=12)
    return f"""# {branch.name} Promotion Bundle

generated by Abel strategy discovery narrative layer

## Summary

- branch_id: `{branch.name}`
- target: `{branch_spec.get("target", "unknown")}`
- requested_start: `{branch_spec.get("requested_start", "unknown")}`
- overlap_mode: `{branch_spec.get("overlap_mode", "target_only")}`
- selected_inputs: `{selected}`
- latest_round: `{latest.get("round_id", "none")}`
- latest_decision: `{latest.get("decision", "n/a")}`
- latest_verdict: `{latest.get("verdict", "n/a")}`
- latest_score: `{latest.get("score", "n/a")}`

## Included Files

- `engine.py`: branch implementation snapshot
- `{BRANCH_SPEC_FILENAME}`: explicit branch definition
- `{DEPENDENCIES_FILENAME}`: prepared input/cache dependency view when available

## Handoff

Bundle contents are ready for explicit downstream promotion review.
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
    selected = format_simple_nodes(branch_selected_inputs(branch_spec), limit=8)
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
- selected_inputs: `{selected}`
- usable_tickers: `{usable}`
- start_covered_tickers: `{start_covered}`

## Main Risks

{format_risks(latest_note.get("failures", "none"))}
"""


def write_evidence_ledger(session: Path, discovery: dict, branches: list[dict]) -> dict:
    ledger = build_evidence_ledger(session, discovery, branches)
    write_json_file(session / EVIDENCE_LEDGER_FILENAME, ledger)
    return ledger


def build_evidence_ledger(session: Path, discovery: dict, branches: list[dict]) -> dict:
    rows: list[dict[str, object]] = []
    for branch in branches:
        rows.extend(build_evidence_rows_for_branch(session, branch))
    annotate_exploration_protocol(rows)
    discovered_drivers = discovered_driver_tickers(discovery)
    return {
        "schema_version": 1,
        "exp_id": session.name,
        "asset_scope": discovery.get("ticker", session.parent.name.upper()),
        "generated_at": _now(),
        "graph_discovery_source": discovery.get("source", "unknown"),
        "graph_discovery_k": int(discovery.get("K_discovery") or len(discovered_drivers)),
        "discovered_drivers": discovered_drivers,
        "experiment": session_experiment_metadata(branches, rows),
        "rows": rows,
    }


def write_frontier(session: Path, ledger: dict) -> dict:
    journal_status = build_research_journal_status(session, ledger=ledger, frontier={})
    frontier = build_frontier(
        ledger,
        journal_status=journal_status,
    )
    write_json_file(session / FRONTIER_JSON_FILENAME, frontier)
    (session / FRONTIER_MARKDOWN_FILENAME).write_text(
        render_frontier_markdown(frontier),
        encoding="utf-8",
    )
    return frontier


def build_frontier(
    ledger: dict,
    *,
    journal_status: dict[str, object] | None = None,
) -> dict:
    rows = [row for row in (ledger.get("rows") or []) if isinstance(row, dict)]
    discovered_drivers = ordered_unique_upper(ledger.get("discovered_drivers") or [])
    graph_discovery_source = str(ledger.get("graph_discovery_source") or "unknown")
    graph_discovery_k = int(ledger.get("graph_discovery_k") or len(discovered_drivers))
    label_counts: dict[str, int] = {}
    label_verdict_counts: dict[str, dict[str, int]] = {}
    label_decision_counts: dict[str, dict[str, int]] = {}
    mechanism_counts: dict[str, int] = {}
    intent_counts: dict[str, int] = {}
    input_claim_counts: dict[str, int] = {}
    window_counts: dict[str, int] = {}
    metric_failure_counts: dict[str, int] = {}
    branch_counts: dict[str, int] = {}
    recorded_branch_counts: dict[str, int] = {}
    driver_set_counts: dict[str, int] = {}
    branch_family_counts: dict[str, int] = {}
    neighborhood_counts: dict[str, int] = {}
    recorded_neighborhood_counts: dict[str, int] = {}
    exploration_class_counts: dict[str, int] = {}
    model_family_counts: dict[str, int] = {}
    complexity_class_counts: dict[str, int] = {}
    exploration_role_counts: dict[str, int] = {}
    driver_reads: set[str] = set()
    candidate_driver_sets: set[str] = set()
    candidate_discovered_drivers: set[str] = set()
    declared_graph_supported_rounds = 0
    realized_graph_supported_rounds = 0
    graph_input_read_gap_rows: list[str] = []
    target_only_recorded_round_count = 0
    graph_supported_candidate_round_count = 0
    protocol_complete = 0
    comparable_candidates = 0
    comparable_controls = 0
    candidate_pass = 0
    candidate_fail = 0
    candidate_other = 0
    for row in rows:
        label = str(row.get("evidence_label") or "unknown")
        verdict = str(row.get("verdict") or "unknown").upper()
        decision = str(row.get("decision") or "unknown").lower()
        increment_count(label_counts, label)
        increment_nested_count(label_verdict_counts, label, verdict)
        increment_nested_count(label_decision_counts, label, decision)
        increment_count(mechanism_counts, str(row.get("declared_mechanism_family") or "unknown"))
        increment_count(intent_counts, str(row.get("declared_evidence_intent") or "unknown"))
        increment_count(input_claim_counts, str(row.get("declared_input_claim") or "unknown"))
        increment_count(branch_counts, str(row.get("branch_id") or "unknown"))
        driver_set = canonical_driver_set_label(row)
        increment_count(driver_set_counts, driver_set)
        if row.get("run_type") == "round":
            increment_count(recorded_branch_counts, str(row.get("branch_id") or "unknown"))
            increment_count(branch_family_counts, str(row.get("branch_family_key") or branch_family_key(row)))
            neighborhood = str(row.get("exploration_neighborhood_key") or exploration_neighborhood_key(row))
            increment_count(recorded_neighborhood_counts, neighborhood)
            input_realization = (
                row.get("input_realization")
                if isinstance(row.get("input_realization"), dict)
                else {}
            )
            if str(input_realization.get("declared_input_claim") or row.get("declared_input_claim") or "") == "graph_supported":
                declared_graph_supported_rounds += 1
            if str(input_realization.get("realized_input_claim") or "") == "graph_supported":
                realized_graph_supported_rounds += 1
            if input_realization.get("graph_input_read_gap"):
                graph_input_read_gap_rows.append(
                    f"{row.get('branch_id', 'unknown')}:{row.get('round_id') or row.get('run_id') or 'unknown'}"
                )
            if str(row.get("declared_input_claim") or "") == "target_only":
                target_only_recorded_round_count += 1
            if label == "candidate_causal_evidence":
                if str(row.get("declared_input_claim") or "") == "graph_supported":
                    graph_supported_candidate_round_count += 1
                selected = ordered_unique_upper(row.get("declared_selected_inputs") or [])
                if selected:
                    candidate_driver_sets.add(",".join(selected))
                    for item in selected:
                        if item in discovered_drivers:
                            candidate_discovered_drivers.add(item)
        increment_count(neighborhood_counts, str(row.get("exploration_neighborhood_key") or exploration_neighborhood_key(row)))
        increment_count(exploration_class_counts, str(row.get("derived_exploration_class") or "unknown"))
        increment_count(model_family_counts, str(row.get("declared_model_family") or "unspecified"))
        increment_count(complexity_class_counts, str(row.get("declared_complexity_class") or "unspecified"))
        increment_count(exploration_role_counts, str(row.get("declared_exploration_role") or "unspecified"))
        if row.get("declaration_protocol_complete"):
            protocol_complete += 1
        for item in row.get("actual_auxiliary_reads") or []:
            value = str(item or "").strip().upper()
            if value:
                driver_reads.add(value)
        if row.get("comparable") and label == "candidate_causal_evidence":
            comparable_candidates += 1
            if verdict == "PASS":
                candidate_pass += 1
            elif verdict == "FAIL":
                candidate_fail += 1
            else:
                candidate_other += 1
        if row.get("comparable") and label == "target_control_evidence":
            comparable_controls += 1
        for metric in row.get("metric_failure_metrics") or []:
            increment_count(metric_failure_counts, str(metric or "unknown"))
        result_ref = str(row.get("result_ref") or "").strip()
        if result_ref:
            increment_count(window_counts, str(row.get("runtime_stage") or "unknown"))
    dominant_branch, _ = dominant_count(branch_counts)
    dominant_mechanism, dominant_mechanism_count = dominant_count(mechanism_counts)
    dominant_input, dominant_input_count = dominant_count(input_claim_counts)
    dominant_driver_set, dominant_driver_set_count = dominant_count(driver_set_counts)
    dominant_neighborhood, dominant_neighborhood_count = dominant_count(neighborhood_counts)
    dominant_recorded_neighborhood, dominant_recorded_neighborhood_count = dominant_count(recorded_neighborhood_counts)
    same_branch_max_rounds = max(recorded_branch_counts.values(), default=0)
    recorded_round_count = sum(recorded_branch_counts.values())
    diagnostic_row_count = sum(1 for row in rows if row.get("run_type") != "round")
    input_breadth_thin = (
        len(discovered_drivers) >= 2
        and recorded_round_count >= INPUT_BREADTH_ROUND_THRESHOLD
        and len(candidate_driver_sets) < 2
    )
    graph_candidates_available = bool(discovered_drivers) or graph_discovery_k > 0
    target_only_saturation = (
        recorded_round_count >= GRAPH_PRIORITY_ROUND_MINIMUM
        and target_only_recorded_round_count == recorded_round_count
        and recorded_round_count > 0
    )
    graph_discovery_missing = target_only_saturation and not graph_candidates_available
    graph_first_uncovered = (
        graph_candidates_available
        and recorded_round_count >= GRAPH_PRIORITY_ROUND_MINIMUM
        and graph_supported_candidate_round_count == 0
    )
    local_refinement_count = exploration_class_counts.get("local_refinement", 0)
    control_evidence_count = label_counts.get("target_control_evidence", 0)
    ablation_evidence_count = exploration_role_counts.get("ablation", 0)
    expansion_probe_count = exploration_role_counts.get("expansion_probe", 0)
    compact_journal = compact_research_journal_status(journal_status)
    journal_coverage = build_journal_coverage(rows, compact_journal)
    research_reflection_due = not bool(journal_coverage.get("journal_coverage_complete"))
    return {
        "schema_version": 1,
        "exp_id": ledger.get("exp_id", ""),
        "asset_scope": ledger.get("asset_scope", ""),
        "generated_at": _now(),
        "row_count": len(rows),
        "evidence_label_counts": dict(sorted(label_counts.items())),
        "evidence_label_verdict_counts": sort_nested_counts(label_verdict_counts),
        "evidence_label_decision_counts": sort_nested_counts(label_decision_counts),
        "hypothesis_coverage": {
            "protocol_complete": protocol_complete,
            "protocol_incomplete": len(rows) - protocol_complete,
        },
        "mechanism_family_counts": dict(sorted(mechanism_counts.items())),
        "evidence_intent_counts": dict(sorted(intent_counts.items())),
        "input_claim_counts": dict(sorted(input_claim_counts.items())),
        "metric_failure_counts": dict(sorted(metric_failure_counts.items())),
        "candidate_causal_summary": {
            "rows": label_counts.get("candidate_causal_evidence", 0),
            "validation_pass": candidate_pass,
            "validation_fail": candidate_fail,
            "validation_other": candidate_other,
        },
        "driver_read_count": len(driver_reads),
        "driver_reads": sorted(driver_reads),
        "workflow_blockers": label_counts.get("workflow_blocker", 0),
        "runtime_invalid": label_counts.get("runtime_invalid", 0),
        "runtime_stage_counts": dict(sorted(window_counts.items())),
        "comparable_availability": {
            "candidate_causal_evidence": comparable_candidates,
            "target_control_evidence": comparable_controls,
        },
        "input_breadth": {
            "input_breadth_thin": input_breadth_thin,
            "input_breadth_round_minimum": INPUT_BREADTH_ROUND_THRESHOLD,
            "discovered_driver_count": len(discovered_drivers),
            "discovered_drivers": discovered_drivers,
            "candidate_driver_set_count": len(candidate_driver_sets),
            "candidate_driver_sets": sorted(candidate_driver_sets),
            "candidate_discovered_driver_coverage_count": len(candidate_discovered_drivers),
            "discovered_driver_coverage": fraction_pair(
                len(candidate_discovered_drivers),
                len(discovered_drivers),
            ),
            "target_only_recorded_round_count": target_only_recorded_round_count,
            "graph_supported_candidate_round_count": graph_supported_candidate_round_count,
        },
        "graph_priority": {
            "graph_discovery_source": graph_discovery_source,
            "graph_discovery_k": graph_discovery_k,
            "graph_candidates_available": graph_candidates_available,
            "graph_first_uncovered": graph_first_uncovered,
            "graph_discovery_missing": graph_discovery_missing,
            "target_only_saturation": target_only_saturation,
            "graph_priority_round_minimum": GRAPH_PRIORITY_ROUND_MINIMUM,
        },
        "research_journal": compact_journal,
        "journal_coverage": journal_coverage,
        "research_reflection": {
            "research_reflection_due": research_reflection_due,
            "recorded_round_count": recorded_round_count,
            "journal_coverage_complete": bool(journal_coverage.get("journal_coverage_complete")),
            "missing_journal_round_count": len(journal_coverage.get("missing_journal_rounds") or []),
            "evidence_linked_journal_update": bool(
                compact_journal.get("has_evidence_linked_update")
            ),
            "journal_evidence_reference_count": int(
                compact_journal.get("evidence_reference_count") or 0
            ),
            "resolved_evidence_reference_count": int(
                compact_journal.get("resolved_evidence_reference_count") or 0
            ),
        },
        "input_realization": {
            "declared_graph_supported_rounds": declared_graph_supported_rounds,
            "realized_graph_supported_rounds": realized_graph_supported_rounds,
            "graph_input_read_gap_count": len(graph_input_read_gap_rows),
            "graph_input_read_gap_rows": graph_input_read_gap_rows,
        },
        "coverage_concentration": {
            "branch_count": len(branch_counts),
            "max_rounds_in_one_branch": same_branch_max_rounds,
            "dominant_branch": dominant_branch,
            "dominant_mechanism_family": dominant_mechanism,
            "dominant_mechanism_family_count": dominant_mechanism_count,
            "dominant_mechanism_family_share": fraction_pair(dominant_mechanism_count, len(rows)),
            "dominant_input_claim": dominant_input,
            "dominant_input_claim_count": dominant_input_count,
            "dominant_input_claim_share": fraction_pair(dominant_input_count, len(rows)),
            "dominant_driver_set": dominant_driver_set,
            "dominant_driver_set_count": dominant_driver_set_count,
            "dominant_driver_set_share": fraction_pair(dominant_driver_set_count, len(rows)),
            "target_control_evidence": control_evidence_count,
            "comparable_controls": comparable_controls,
        },
        "exploration_breadth": {
            "branch_count": len(branch_counts),
            "recorded_round_count": recorded_round_count,
            "diagnostic_row_count": diagnostic_row_count,
            "branch_family_count": len(branch_family_counts),
            "same_branch_max_rounds": same_branch_max_rounds,
            "dominant_neighborhood": dominant_recorded_neighborhood,
            "dominant_neighborhood_rows": dominant_recorded_neighborhood_count,
            "dominant_evidence_neighborhood": dominant_neighborhood,
            "dominant_evidence_neighborhood_rows": dominant_neighborhood_count,
            "dominant_mechanism_family": dominant_mechanism,
            "dominant_mechanism_family_share": fraction_pair(dominant_mechanism_count, len(rows)),
            "dominant_driver_set": dominant_driver_set,
            "dominant_driver_set_share": fraction_pair(dominant_driver_set_count, len(rows)),
            "exploration_class_counts": dict(sorted(exploration_class_counts.items())),
            "model_family_counts": dict(sorted(model_family_counts.items())),
            "complexity_class_counts": dict(sorted(complexity_class_counts.items())),
            "exploration_role_counts": dict(sorted(exploration_role_counts.items())),
            "control_evidence_count": control_evidence_count,
            "ablation_evidence_count": ablation_evidence_count,
            "expansion_probe_count": expansion_probe_count,
            "local_refinement_count": local_refinement_count,
        },
    }


def increment_count(counter: dict[str, int], key: str) -> None:
    normalized = key.strip() or "unknown"
    counter[normalized] = counter.get(normalized, 0) + 1


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


def increment_nested_count(counter: dict[str, dict[str, int]], outer: str, inner: str) -> None:
    outer_key = outer.strip() or "unknown"
    inner_key = inner.strip() or "unknown"
    bucket = counter.setdefault(outer_key, {})
    bucket[inner_key] = bucket.get(inner_key, 0) + 1


def sort_nested_counts(counter: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {
        key: dict(sorted(value.items()))
        for key, value in sorted(counter.items())
    }


def dominant_count(counter: dict[str, int]) -> tuple[str, int]:
    if not counter:
        return "none", 0
    key, value = max(sorted(counter.items()), key=lambda item: item[1])
    return key, value


def fraction_pair(count: int, total: int) -> str:
    return f"{count}/{total}" if total else "0/0"


def discovered_driver_tickers(discovery: dict) -> list[str]:
    target = str(discovery.get("ticker") or discovery.get("target_asset") or "").strip().upper()
    raw_nodes: list[object] = []
    for key in ("parents", "blanket_new"):
        values = discovery.get(key) or []
        if isinstance(values, list):
            raw_nodes.extend(values)
    tickers: list[str] = []
    for node in raw_nodes:
        value = ""
        if isinstance(node, dict):
            value = str(node.get("ticker") or node.get("symbol") or "").strip()
            if not value:
                node_id = str(node.get("node_id") or "").strip()
                value = node_id.split(".", 1)[0]
        else:
            value = str(node or "").strip()
        value = value.upper()
        if value and value != target:
            tickers.append(value)
    return ordered_unique_upper(tickers)


def canonical_driver_set_label(row: dict) -> str:
    values = row.get("declared_selected_inputs") or row.get("actual_auxiliary_reads") or []
    selected = ordered_unique_upper(values if isinstance(values, list) else [])
    if selected:
        return ",".join(selected)
    if str(row.get("declared_input_claim") or "") == "target_only":
        return "target_only"
    return "none"


def render_frontier_markdown(frontier: dict) -> str:
    labels = render_count_lines(frontier.get("evidence_label_counts") or {})
    label_verdicts = render_nested_count_lines(frontier.get("evidence_label_verdict_counts") or {})
    label_decisions = render_nested_count_lines(frontier.get("evidence_label_decision_counts") or {})
    mechanisms = render_count_lines(frontier.get("mechanism_family_counts") or {})
    input_claims = render_count_lines(frontier.get("input_claim_counts") or {})
    metric_failures = render_count_lines(frontier.get("metric_failure_counts") or {})
    runtime_stages = render_count_lines(frontier.get("runtime_stage_counts") or {})
    comparable = frontier.get("comparable_availability") or {}
    hypothesis = frontier.get("hypothesis_coverage") or {}
    candidate = frontier.get("candidate_causal_summary") or {}
    concentration = frontier.get("coverage_concentration") or {}
    exploration = frontier.get("exploration_breadth") or {}
    input_breadth = frontier.get("input_breadth") or {}
    graph_priority = frontier.get("graph_priority") or {}
    research_reflection = frontier.get("research_reflection") or {}
    input_realization = frontier.get("input_realization") or {}
    journal_coverage = frontier.get("journal_coverage") or {}
    research_journal = frontier.get("research_journal") or {}
    return f"""# Evidence Frontier

generated by Abel strategy discovery narrative layer

## Scope

- exp_id: `{frontier.get("exp_id", "")}`
- asset_scope: `{frontier.get("asset_scope", "")}`
- rows: `{frontier.get("row_count", 0)}`

## Evidence Labels

{labels}

## Verdict Cross Sections

{label_verdicts}

## Decision Cross Sections

{label_decisions}

## Candidate Causal Summary

- rows: `{candidate.get("rows", 0)}`
- validation_pass: `{candidate.get("validation_pass", 0)}`
- validation_fail: `{candidate.get("validation_fail", 0)}`
- validation_other: `{candidate.get("validation_other", 0)}`

## Declaration Coverage

- protocol_complete: `{hypothesis.get("protocol_complete", 0)}`
- protocol_incomplete: `{hypothesis.get("protocol_incomplete", 0)}`

## Mechanism Families

{mechanisms}

## Input Claims

{input_claims}

## Metric Failure Facts

{metric_failures}

## Coverage Concentration

- branch_count: `{concentration.get("branch_count", 0)}`
- max_rounds_in_one_branch: `{concentration.get("max_rounds_in_one_branch", 0)}`
- dominant_branch: `{concentration.get("dominant_branch", "none")}`
- dominant_mechanism_family: `{concentration.get("dominant_mechanism_family", "none")}` (`{concentration.get("dominant_mechanism_family_share", "0/0")}`)
- dominant_input_claim: `{concentration.get("dominant_input_claim", "none")}` (`{concentration.get("dominant_input_claim_share", "0/0")}`)
- dominant_driver_set: `{concentration.get("dominant_driver_set", "none")}` (`{concentration.get("dominant_driver_set_share", "0/0")}`)
- target_control_evidence: `{concentration.get("target_control_evidence", 0)}`
- comparable_controls: `{concentration.get("comparable_controls", 0)}`

## Exploration Breadth

- branch_count: `{exploration.get("branch_count", 0)}`
- recorded_round_count: `{exploration.get("recorded_round_count", 0)}`
- diagnostic_row_count: `{exploration.get("diagnostic_row_count", 0)}`
- branch_family_count: `{exploration.get("branch_family_count", 0)}`
- same_branch_max_rounds: `{exploration.get("same_branch_max_rounds", 0)}`
- dominant_neighborhood: `{exploration.get("dominant_neighborhood", "none")}`
- dominant_neighborhood_rows: `{exploration.get("dominant_neighborhood_rows", 0)}`
- model_family_counts: `{render_inline_counts(exploration.get("model_family_counts") or {})}`
- complexity_class_counts: `{render_inline_counts(exploration.get("complexity_class_counts") or {})}`
- exploration_class_counts: `{render_inline_counts(exploration.get("exploration_class_counts") or {})}`
- control_evidence_count: `{exploration.get("control_evidence_count", 0)}`
- ablation_evidence_count: `{exploration.get("ablation_evidence_count", 0)}`
- expansion_probe_count: `{exploration.get("expansion_probe_count", 0)}`
- local_refinement_count: `{exploration.get("local_refinement_count", 0)}`

## Input Breadth

- input_breadth_thin: `{str(input_breadth.get("input_breadth_thin", False)).lower()}`
- input_breadth_round_minimum: `{input_breadth.get("input_breadth_round_minimum", 0)}`
- discovered_driver_count: `{input_breadth.get("discovered_driver_count", 0)}`
- discovered_drivers: `{", ".join(input_breadth.get("discovered_drivers") or []) or "none"}`
- candidate_driver_set_count: `{input_breadth.get("candidate_driver_set_count", 0)}`
- candidate_driver_sets: `{", ".join(input_breadth.get("candidate_driver_sets") or []) or "none"}`
- discovered_driver_coverage: `{input_breadth.get("discovered_driver_coverage", "0/0")}`
- target_only_recorded_round_count: `{input_breadth.get("target_only_recorded_round_count", 0)}`
- graph_supported_candidate_round_count: `{input_breadth.get("graph_supported_candidate_round_count", 0)}`

## Graph Priority

- graph_discovery_source: `{graph_priority.get("graph_discovery_source", "unknown")}`
- graph_discovery_k: `{graph_priority.get("graph_discovery_k", 0)}`
- graph_candidates_available: `{str(graph_priority.get("graph_candidates_available", False)).lower()}`
- graph_first_uncovered: `{str(graph_priority.get("graph_first_uncovered", False)).lower()}`
- graph_discovery_missing: `{str(graph_priority.get("graph_discovery_missing", False)).lower()}`
- target_only_saturation: `{str(graph_priority.get("target_only_saturation", False)).lower()}`
- graph_priority_round_minimum: `{graph_priority.get("graph_priority_round_minimum", 0)}`

## Research Reflection

- research_reflection_due: `{str(research_reflection.get("research_reflection_due", False)).lower()}`
- recorded_round_count: `{research_reflection.get("recorded_round_count", 0)}`
- journal_coverage_complete: `{str(research_reflection.get("journal_coverage_complete", False)).lower()}`
- missing_journal_round_count: `{research_reflection.get("missing_journal_round_count", 0)}`
- evidence_linked_journal_update: `{str(research_reflection.get("evidence_linked_journal_update", False)).lower()}`
- journal_evidence_reference_count: `{research_reflection.get("journal_evidence_reference_count", 0)}`
- resolved_evidence_reference_count: `{research_reflection.get("resolved_evidence_reference_count", 0)}`

## Journal Coverage

- recorded_round_count: `{journal_coverage.get("recorded_round_count", 0)}`
- journaled_round_count: `{journal_coverage.get("journaled_round_count", 0)}`
- journal_coverage_complete: `{str(journal_coverage.get("journal_coverage_complete", False)).lower()}`
- missing_journal_rounds: `{", ".join(journal_coverage.get("missing_journal_rounds") or []) or "none"}`

## Input Realization

- declared_graph_supported_rounds: `{input_realization.get("declared_graph_supported_rounds", 0)}`
- realized_graph_supported_rounds: `{input_realization.get("realized_graph_supported_rounds", 0)}`
- graph_input_read_gap_count: `{input_realization.get("graph_input_read_gap_count", 0)}`
- graph_input_read_gap_rows: `{", ".join(input_realization.get("graph_input_read_gap_rows") or []) or "none"}`

## Research Journal

- exists: `{str(research_journal.get("exists", False)).lower()}`
- evidence_reference_count: `{research_journal.get("evidence_reference_count", 0)}`
- resolved_evidence_reference_count: `{research_journal.get("resolved_evidence_reference_count", 0)}`
- has_evidence_linked_update: `{str(research_journal.get("has_evidence_linked_update", False)).lower()}`
- last_evidence_linked_update_line: `{research_journal.get("last_evidence_linked_update_line", 0)}`

## Runtime Reads

- driver_read_count: `{frontier.get("driver_read_count", 0)}`
- driver_reads: `{", ".join(frontier.get("driver_reads") or []) or "none"}`

## Runtime Stages

{runtime_stages}

## Comparable Availability

- candidate_causal_evidence: `{comparable.get("candidate_causal_evidence", 0)}`
- target_control_evidence: `{comparable.get("target_control_evidence", 0)}`
"""


def render_count_lines(counts: dict) -> str:
    if not counts:
        return "- none"
    return "\n".join(f"- {key}: `{value}`" for key, value in sorted(counts.items()))


def render_nested_count_lines(counts: dict) -> str:
    if not counts:
        return "- none"
    lines = []
    for outer, inner_counts in sorted(counts.items()):
        if not isinstance(inner_counts, dict) or not inner_counts:
            lines.append(f"- {outer}: `0`")
            continue
        for inner, value in sorted(inner_counts.items()):
            lines.append(f"- {outer}.{inner}: `{value}`")
    return "\n".join(lines)


def render_inline_counts(counts: dict) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def render_session_frontier_summary(frontier: dict) -> str:
    if not frontier:
        return "- evidence_frontier: `not generated`"
    labels = frontier.get("evidence_label_counts") or {}
    comparable = frontier.get("comparable_availability") or {}
    hypothesis = frontier.get("hypothesis_coverage") or {}
    candidate = frontier.get("candidate_causal_summary") or {}
    concentration = frontier.get("coverage_concentration") or {}
    exploration = frontier.get("exploration_breadth") or {}
    input_breadth = frontier.get("input_breadth") or {}
    graph_priority = frontier.get("graph_priority") or {}
    research_reflection = frontier.get("research_reflection") or {}
    input_realization = frontier.get("input_realization") or {}
    journal_coverage = frontier.get("journal_coverage") or {}
    return "\n".join(
        [
            f"- evidence_rows: `{frontier.get('row_count', 0)}`",
            f"- protocol_complete: `{hypothesis.get('protocol_complete', 0)}`",
            f"- protocol_incomplete: `{hypothesis.get('protocol_incomplete', 0)}`",
            f"- candidate_causal_evidence: `{labels.get('candidate_causal_evidence', 0)}`",
            f"- candidate_causal_pass: `{candidate.get('validation_pass', 0)}`",
            f"- candidate_causal_fail: `{candidate.get('validation_fail', 0)}`",
            f"- target_control_evidence: `{labels.get('target_control_evidence', 0)}`",
            f"- workflow_blockers: `{frontier.get('workflow_blockers', 0)}`",
            f"- comparable_candidates: `{comparable.get('candidate_causal_evidence', 0)}`",
            f"- comparable_controls: `{comparable.get('target_control_evidence', 0)}`",
            f"- dominant_mechanism_family: `{concentration.get('dominant_mechanism_family', 'none')}` (`{concentration.get('dominant_mechanism_family_share', '0/0')}`)",
            f"- dominant_driver_set: `{concentration.get('dominant_driver_set', 'none')}` (`{concentration.get('dominant_driver_set_share', '0/0')}`)",
            f"- branch_family_count: `{exploration.get('branch_family_count', 0)}`",
            f"- candidate_driver_set_count: `{input_breadth.get('candidate_driver_set_count', 0)}`",
            f"- graph_first_uncovered: `{str(graph_priority.get('graph_first_uncovered', False)).lower()}`",
            f"- graph_discovery_missing: `{str(graph_priority.get('graph_discovery_missing', False)).lower()}`",
            f"- research_reflection_due: `{str(research_reflection.get('research_reflection_due', False)).lower()}`",
            f"- journal_coverage_complete: `{str(journal_coverage.get('journal_coverage_complete', False)).lower()}`",
            f"- missing_journal_rounds: `{', '.join(journal_coverage.get('missing_journal_rounds') or []) or 'none'}`",
            f"- graph_input_read_gap_count: `{input_realization.get('graph_input_read_gap_count', 0)}`",
            f"- local_refinement_count: `{exploration.get('local_refinement_count', 0)}`",
        ]
    )


def render_agent_context(*, session: Path, ledger: dict, frontier: dict) -> None:
    (session / AGENT_CONTEXT_FILENAME).write_text(
        build_agent_context(session=session, ledger=ledger, frontier=frontier),
        encoding="utf-8",
    )


def build_agent_context(
    *,
    session: Path,
    ledger: dict,
    frontier: dict,
) -> str:
    rows = [row for row in (ledger.get("rows") or []) if isinstance(row, dict)]
    recent_rows = rows[-8:]
    journal_status = build_research_journal_status(session, ledger=ledger, frontier=frontier)
    return f"""# Agent Context Pack

generated by Abel strategy discovery narrative layer

## Evidence Frontier

{render_session_frontier_summary(frontier)}

## Research Journal

{render_agent_context_research_journal(journal_status)}

## Research Reflection

{render_agent_context_research_reflection(frontier)}

## Journal Coverage

{render_agent_context_journal_coverage(frontier)}

## Input Realization

{render_agent_context_input_realization(frontier)}

## Exploration Breadth

{render_agent_context_exploration_breadth(frontier)}

## Input Breadth

{render_agent_context_input_breadth(frontier)}

## Graph Priority

{render_agent_context_graph_priority(frontier)}

## Recent Evidence Rows

{render_agent_context_evidence_rows(recent_rows)}

## Evidence Sources

- ledger: `{EVIDENCE_LEDGER_FILENAME}`
- frontier: `{FRONTIER_MARKDOWN_FILENAME}`
- journal: `{RESEARCH_JOURNAL_FILENAME}`
- raw artifacts: branch `outputs/`
- session: `{session.name}`
"""


def render_agent_context_research_journal(journal_status: dict[str, object]) -> str:
    lines = [
        f"- path: `{journal_status.get('path', RESEARCH_JOURNAL_FILENAME)}`",
        f"- exists: `{str(journal_status.get('exists', False)).lower()}`",
        f"- evidence_reference_count: `{journal_status.get('evidence_reference_count', 0)}`",
        f"- resolved_evidence_reference_count: `{journal_status.get('resolved_evidence_reference_count', 0)}`",
        f"- has_evidence_linked_update: `{str(journal_status.get('has_evidence_linked_update', False)).lower()}`",
        f"- last_evidence_linked_update_line: `{journal_status.get('last_evidence_linked_update_line', 0)}`",
    ]
    excerpt = str(journal_status.get("recent_excerpt") or "").strip()
    if excerpt:
        lines.append("")
        lines.append("Recent excerpt:")
        lines.append("")
        lines.extend(f"> {line}" for line in excerpt.splitlines())
    else:
        lines.append("- recent_excerpt: `none`")
    return "\n".join(lines)


def render_agent_context_research_reflection(frontier: dict) -> str:
    reflection = frontier.get("research_reflection") or {}
    if not reflection:
        return "- not generated"
    return "\n".join(
        [
            f"- research_reflection_due: `{str(reflection.get('research_reflection_due', False)).lower()}`",
            f"- recorded_round_count: `{reflection.get('recorded_round_count', 0)}`",
            f"- journal_coverage_complete: `{str(reflection.get('journal_coverage_complete', False)).lower()}`",
            f"- missing_journal_round_count: `{reflection.get('missing_journal_round_count', 0)}`",
            f"- evidence_linked_journal_update: `{str(reflection.get('evidence_linked_journal_update', False)).lower()}`",
            f"- journal_evidence_reference_count: `{reflection.get('journal_evidence_reference_count', 0)}`",
        ]
    )


def render_agent_context_journal_coverage(frontier: dict) -> str:
    coverage = frontier.get("journal_coverage") or {}
    if not coverage:
        return "- not generated"
    return "\n".join(
        [
            f"- recorded_round_count: `{coverage.get('recorded_round_count', 0)}`",
            f"- journaled_round_count: `{coverage.get('journaled_round_count', 0)}`",
            f"- journal_coverage_complete: `{str(coverage.get('journal_coverage_complete', False)).lower()}`",
            f"- missing_journal_rounds: `{', '.join(coverage.get('missing_journal_rounds') or []) or 'none'}`",
        ]
    )


def render_agent_context_input_realization(frontier: dict) -> str:
    realization = frontier.get("input_realization") or {}
    if not realization:
        return "- not generated"
    return "\n".join(
        [
            f"- declared_graph_supported_rounds: `{realization.get('declared_graph_supported_rounds', 0)}`",
            f"- realized_graph_supported_rounds: `{realization.get('realized_graph_supported_rounds', 0)}`",
            f"- graph_input_read_gap_count: `{realization.get('graph_input_read_gap_count', 0)}`",
            f"- graph_input_read_gap_rows: `{', '.join(realization.get('graph_input_read_gap_rows') or []) or 'none'}`",
        ]
    )


def render_agent_context_exploration_breadth(frontier: dict) -> str:
    exploration = frontier.get("exploration_breadth") or {}
    if not exploration:
        return "- not generated"
    return "\n".join(
        [
            f"- branch_family_count: `{exploration.get('branch_family_count', 0)}`",
            f"- recorded_round_count: `{exploration.get('recorded_round_count', 0)}`",
            f"- same_branch_max_rounds: `{exploration.get('same_branch_max_rounds', 0)}`",
            f"- dominant_neighborhood_rows: `{exploration.get('dominant_neighborhood_rows', 0)}`",
            f"- model_family_counts: `{render_inline_counts(exploration.get('model_family_counts') or {})}`",
            f"- complexity_class_counts: `{render_inline_counts(exploration.get('complexity_class_counts') or {})}`",
            f"- exploration_class_counts: `{render_inline_counts(exploration.get('exploration_class_counts') or {})}`",
        ]
    )


def render_agent_context_input_breadth(frontier: dict) -> str:
    input_breadth = frontier.get("input_breadth") or {}
    if not input_breadth:
        return "- not generated"
    return "\n".join(
        [
            f"- input_breadth_thin: `{str(input_breadth.get('input_breadth_thin', False)).lower()}`",
            f"- input_breadth_round_minimum: `{input_breadth.get('input_breadth_round_minimum', 0)}`",
            f"- discovered_driver_count: `{input_breadth.get('discovered_driver_count', 0)}`",
            f"- discovered_drivers: `{', '.join(input_breadth.get('discovered_drivers') or []) or 'none'}`",
            f"- candidate_driver_set_count: `{input_breadth.get('candidate_driver_set_count', 0)}`",
            f"- candidate_driver_sets: `{', '.join(input_breadth.get('candidate_driver_sets') or []) or 'none'}`",
            f"- discovered_driver_coverage: `{input_breadth.get('discovered_driver_coverage', '0/0')}`",
            f"- target_only_recorded_round_count: `{input_breadth.get('target_only_recorded_round_count', 0)}`",
            f"- graph_supported_candidate_round_count: `{input_breadth.get('graph_supported_candidate_round_count', 0)}`",
        ]
    )


def render_agent_context_graph_priority(frontier: dict) -> str:
    graph_priority = frontier.get("graph_priority") or {}
    if not graph_priority:
        return "- not generated"
    return "\n".join(
        [
            f"- graph_discovery_source: `{graph_priority.get('graph_discovery_source', 'unknown')}`",
            f"- graph_discovery_k: `{graph_priority.get('graph_discovery_k', 0)}`",
            f"- graph_candidates_available: `{str(graph_priority.get('graph_candidates_available', False)).lower()}`",
            f"- graph_first_uncovered: `{str(graph_priority.get('graph_first_uncovered', False)).lower()}`",
            f"- graph_discovery_missing: `{str(graph_priority.get('graph_discovery_missing', False)).lower()}`",
            f"- target_only_saturation: `{str(graph_priority.get('target_only_saturation', False)).lower()}`",
            f"- graph_priority_round_minimum: `{graph_priority.get('graph_priority_round_minimum', 0)}`",
        ]
    )


def render_agent_context_evidence_rows(rows: list[dict]) -> str:
    if not rows:
        return "- none"
    lines = []
    for row in rows:
        lines.append(
            "- "
            f"`ledger:{row.get('branch_id', '')}:{row.get('round_id') or row.get('run_id', '')}` "
            f"label=`{row.get('evidence_label', 'unknown')}` "
            f"verdict=`{row.get('verdict', 'unknown')}` "
            f"decision=`{row.get('decision', 'unknown')}` "
            f"exploration=`{row.get('derived_exploration_class', 'unknown')}` "
            f"intent=`{row.get('declared_evidence_intent', 'unknown')}` "
            f"input=`{row.get('declared_input_claim', 'unknown')}` "
            f"workflow=`{row.get('workflow_status', 'unknown')}`"
        )
    return "\n".join(lines)

def build_evidence_rows_for_branch(session: Path, branch: dict) -> list[dict[str, object]]:
    branch_dir = branch["branch_dir"]
    rows: list[dict[str, object]] = []
    debug_snapshot = latest_debug_snapshot(branch_dir)
    if debug_snapshot:
        rows.append(
            build_evidence_row(
                session=session,
                branch_dir=branch_dir,
                branch_id=branch["branch_id"],
                row={},
                note=debug_snapshot,
                run_type="debug",
                run_id="debug",
            )
        )
    for result_row in branch["rows"]:
        round_id = result_row.get("round_id", "")
        rows.append(
            build_evidence_row(
                session=session,
                branch_dir=branch_dir,
                branch_id=branch["branch_id"],
                row=result_row,
                note=read_round_note(branch_dir, round_id),
                run_type="round",
                run_id=round_id,
            )
        )
    return rows


def build_evidence_row(
    *,
    session: Path,
    branch_dir: Path,
    branch_id: str,
    row: dict[str, str],
    note: dict[str, str],
    run_type: str,
    run_id: str,
) -> dict[str, object]:
    context_rel = note.get("context_path", "")
    context = load_json_object(session / context_rel) if context_rel else {}
    branch_spec = context.get("branch_spec") if isinstance(context.get("branch_spec"), dict) else None
    if branch_spec is None:
        branch_spec = load_branch_spec(branch_dir)
    declaration = branch_declaration_status(branch_spec)
    engine_scaffold_status = str(context.get("engine_scaffold_status") or "").strip()

    result_rel = note.get("result_path") or row.get("result_path", "")
    result_path = session / result_rel if result_rel else None
    result = load_json_object(result_path) if result_path is not None else {}
    runtime = evidence_runtime_facts(result)
    input_realization = build_input_realization(declaration=declaration, runtime=runtime)
    validation_completed = runtime["runtime_stage"] == "validation" and runtime["verdict"] in {"PASS", "FAIL"}
    workflow_status = str(runtime["workflow_status"]) if result else "blocked"
    comparable, comparable_reason = evidence_comparability(
        declaration=declaration,
        runtime=runtime,
        validation_completed=validation_completed,
        result=result,
    )
    label = derive_evidence_label(
        declaration=declaration,
        runtime=runtime,
        validation_completed=validation_completed,
        comparable=comparable,
        run_type=run_type,
        result_present=bool(result),
        engine_scaffold_status=engine_scaffold_status,
    )
    changed_dimensions = parse_changed_dimensions(note.get("changed_dimensions", ""))
    exploration_class = derive_exploration_class(
        run_type=run_type,
        declared_mode=row.get("mode", ""),
        evidence_label=label,
        declaration=declaration,
        changed_dimensions=changed_dimensions,
    )
    return {
        "branch_id": branch_id,
        "run_id": run_id,
        "run_type": run_type,
        "round_id": run_id if run_type == "round" else "",
        "declared_mode": row.get("mode", run_type),
        "decision": row.get("decision", ""),
        "declaration_protocol_complete": bool(declaration["protocol_complete"]),
        "declaration_gaps": list(declaration["protocol_gaps"]),
        "declared_evidence_intent": declaration["evidence_intent"],
        "declared_input_claim": declaration["input_claim"],
        "declared_mechanism_family": declaration["mechanism_family"],
        "declared_model_family": declaration["model_family"],
        "declared_complexity_class": declaration["complexity_class"],
        "declared_exploration_role": declaration["exploration_role"],
        "declared_selected_inputs": list(declaration["selected_inputs"]),
        "changed_dimensions": changed_dimensions,
        "engine_scaffold_status": engine_scaffold_status or "unknown",
        "actual_auxiliary_reads": runtime["auxiliary_reads"],
        "actual_read_count": runtime["read_count"],
        "prepared_selected_inputs": runtime["prepared_selected_inputs"],
        "prepared_traced_inputs": runtime["prepared_traced_inputs"],
        "input_realization": input_realization,
        "runtime_stage": runtime["runtime_stage"],
        "workflow_status": workflow_status,
        "validation_status": "completed" if validation_completed else "not_completed",
        "verdict": runtime["verdict"],
        "semantic_verdict": runtime["semantic_verdict"],
        "metric_failure_metrics": runtime["metric_failure_metrics"],
        "metric_failures": runtime["metric_failures"],
        "evidence_label": label,
        "derived_exploration_class": exploration_class,
        "exploration_neighborhood_key": "",
        "comparable": comparable,
        "comparable_reason": comparable_reason,
        "metrics_ref": result_rel,
        "result_ref": result_rel,
        "report_ref": note.get("report_path") or row.get("report_path", ""),
        "handoff_ref": note.get("handoff_path") or row.get("handoff_path", ""),
        "context_ref": context_rel,
        "experiment": context_experiment_metadata(context),
        "score": row.get("score", str(result.get("score") or "")),
        "sharpe": row.get("sharpe", metric_string(result, "sharpe")),
        "lo_adj": row.get("lo_adj", metric_string(result, "lo_adjusted")),
    }


def build_input_realization(
    *,
    declaration: dict[str, object],
    runtime: dict[str, object],
) -> dict[str, object]:
    declared_claim = str(declaration.get("input_claim") or "unspecified")
    declared_inputs = ordered_unique_upper(declaration.get("selected_inputs") or [])
    prepared_inputs = ordered_unique_upper(runtime.get("prepared_selected_inputs") or declared_inputs)
    actual_reads = ordered_unique_upper(runtime.get("auxiliary_reads") or [])
    prepared_set = set(prepared_inputs or declared_inputs)
    actual_set = set(actual_reads)
    selected_graph_reads = sorted(prepared_set.intersection(actual_set))

    if not actual_reads:
        realized_claim = "target_only"
    elif declared_claim == "graph_supported" and selected_graph_reads:
        realized_claim = "graph_supported"
    elif declared_claim in {"supplement", "mixed"}:
        realized_claim = declared_claim
    else:
        realized_claim = "supplemental"

    graph_input_read_gap = (
        declared_claim == "graph_supported"
        and bool(prepared_set)
        and not selected_graph_reads
    )
    return {
        "declared_input_claim": declared_claim,
        "prepared_auxiliary_inputs": prepared_inputs,
        "actual_auxiliary_reads": actual_reads,
        "realized_input_claim": realized_claim,
        "selected_graph_reads": selected_graph_reads,
        "graph_input_read_gap": graph_input_read_gap,
    }


def parse_changed_dimensions(value: object) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        text = str(value or "").strip()
        if not text or text == "none":
            return []
        raw_items = text.replace(";", ",").split(",")
    return [
        item
        for item in ordered_unique_strings(str(raw).strip().lower() for raw in raw_items)
        if item in CHANGED_DIMENSIONS
    ]


def normalize_optional_note(value: object) -> str:
    text = str(value or "").strip()
    return "" if text in {"", "not recorded", "none"} else text


def derive_exploration_class(
    *,
    run_type: str,
    declared_mode: str,
    evidence_label: str,
    declaration: dict[str, object],
    changed_dimensions: list[str],
) -> str:
    role = str(declaration.get("exploration_role") or "unspecified")
    input_claim = str(declaration.get("input_claim") or "")
    intent = str(declaration.get("evidence_intent") or "")
    if run_type == "debug" or evidence_label in {"diagnostic_only", "workflow_blocker", "runtime_invalid"}:
        return "diagnostic"
    if role == "diagnostic" or intent == "diagnostic":
        return "diagnostic"
    if role in {"control", "ablation"} or intent == "control" or input_claim == "target_only":
        return "control"
    if role == "expansion_probe" or any(item in BROAD_CHANGED_DIMENSIONS for item in changed_dimensions):
        return "broad_explore"
    if role == "refinement" or any(item in LOCAL_CHANGED_DIMENSIONS for item in changed_dimensions):
        return "local_refinement"
    if declared_mode == "exploit":
        return "local_refinement"
    return "broad_explore"


def annotate_exploration_protocol(rows: list[dict[str, object]]) -> None:
    round_rows = [row for row in rows if row.get("run_type") == "round"]
    family_keys = {
        branch_family_key(row)
        for row in round_rows
        if branch_family_key(row)
    }
    branch_seen: dict[str, int] = {}
    neighborhood_fail_seen: dict[str, int] = {}

    for row in rows:
        neighborhood = exploration_neighborhood_key(row)
        row["exploration_neighborhood_key"] = neighborhood
        row["branch_family_key"] = branch_family_key(row)
        row["branch_family_count"] = len(family_keys)
        if row.get("run_type") != "round":
            row["same_branch_round_index"] = 0
            row["same_neighborhood_failed_rows"] = 0
            continue
        branch_id = str(row.get("branch_id") or "unknown")
        branch_seen[branch_id] = branch_seen.get(branch_id, 0) + 1
        same_branch_rounds = branch_seen[branch_id]
        failed_before = neighborhood_fail_seen.get(neighborhood, 0)
        if (
            row.get("derived_exploration_class") == "broad_explore"
            and same_branch_rounds > 1
            and not row.get("changed_dimensions")
        ):
            row["derived_exploration_class"] = "local_refinement"
        row["same_branch_round_index"] = same_branch_rounds
        row["same_neighborhood_failed_rows"] = failed_before
        if row.get("comparable") and row.get("verdict") == "FAIL":
            neighborhood_fail_seen[neighborhood] = failed_before + 1


def exploration_neighborhood_key(row: dict[str, object]) -> str:
    return "|".join(
        [
            str(row.get("branch_id") or "unknown"),
            str(row.get("declared_mechanism_family") or "unknown"),
            str(row.get("declared_input_claim") or "unknown"),
            canonical_driver_set_label(row),
            str(row.get("declared_model_family") or "unspecified"),
            str(row.get("declared_complexity_class") or "unspecified"),
        ]
    )


def branch_family_key(row: dict[str, object]) -> str:
    return "|".join(
        [
            str(row.get("declared_mechanism_family") or "unknown"),
            str(row.get("declared_input_claim") or "unknown"),
            canonical_driver_set_label(row),
            str(row.get("declared_model_family") or "unspecified"),
            str(row.get("declared_complexity_class") or "unspecified"),
            str(row.get("declared_exploration_role") or "unspecified"),
        ]
    )


def load_json_object(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def metric_string(result: dict, key: str) -> str:
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    value = metrics.get(key)
    if value is None:
        return ""
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def evidence_runtime_facts(result: dict) -> dict[str, object]:
    runtime_facts = result.get("runtime_facts") if isinstance(result.get("runtime_facts"), dict) else {}
    read_summary = runtime_facts.get("read_summary") if isinstance(runtime_facts.get("read_summary"), dict) else {}
    prepared_summary = runtime_facts.get("prepared_inputs") if isinstance(runtime_facts.get("prepared_inputs"), dict) else {}
    temporal_visibility = (
        runtime_facts.get("temporal_visibility")
        if isinstance(runtime_facts.get("temporal_visibility"), dict)
        else {}
    )
    if runtime_facts:
        auxiliary_reads = sorted(
            {
                str(item).strip().upper()
                for item in (read_summary.get("auxiliary_reads") or prepared_summary.get("traced_inputs") or [])
                if str(item).strip()
            }
        )
        prepared_selected = ordered_unique_upper(prepared_summary.get("selected_inputs") or [])
        prepared_traced = ordered_unique_upper(prepared_summary.get("traced_inputs") or auxiliary_reads)
        metric_failures = [
            item
            for item in (runtime_facts.get("metric_failures") or [])
            if isinstance(item, dict)
        ]
        return {
            "verdict": str(runtime_facts.get("verdict") or "missing").upper(),
            "semantic_verdict": str(runtime_facts.get("semantic_verdict") or "missing").upper(),
            "runtime_stage": str(runtime_facts.get("runtime_stage") or "missing"),
            "workflow_status": str(runtime_facts.get("workflow_status") or "not_completed"),
            "failure_signature": str(runtime_facts.get("failure_signature") or "missing"),
            "read_count": int(read_summary.get("read_count") or 0),
            "auxiliary_reads": auxiliary_reads,
            "prepared_selected_inputs": prepared_selected,
            "prepared_traced_inputs": prepared_traced,
            "metric_failures": metric_failures,
            "metric_failure_metrics": ordered_unique_strings(
                str(item.get("metric") or "").strip()
                for item in metric_failures
                if str(item.get("metric") or "").strip()
            ),
            "prepared_issue_kinds": [
                str(item).strip()
                for item in (temporal_visibility.get("issue_kinds") or [])
                if str(item).strip()
            ],
            "has_prepared_error": bool(temporal_visibility.get("has_error", False)),
        }
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    semantic = result.get("semantic") if isinstance(result.get("semantic"), dict) else {}
    prepared = semantic.get("prepared_inputs") if isinstance(semantic.get("prepared_inputs"), dict) else {}
    auxiliary_reads = [
        str(item).strip().upper()
        for item in (prepared.get("traced_inputs") or [])
        if str(item).strip()
    ]
    issues = [
        item
        for item in (prepared.get("issues") or [])
        if isinstance(item, dict)
    ]
    verdict = str(result.get("verdict") or "missing").upper()
    runtime_stage = str(diagnostics.get("runtime_stage") or "missing")
    validation_completed = runtime_stage == "validation" and verdict in {"PASS", "FAIL"}
    metric_failures = [
        item
        for item in (result.get("metric_failures") or diagnostics.get("metric_failures") or [])
        if isinstance(item, dict)
    ]
    return {
        "verdict": verdict,
        "semantic_verdict": str(semantic.get("verdict") or "missing").upper(),
        "runtime_stage": runtime_stage,
        "workflow_status": "evaluation_completed" if validation_completed else "not_completed",
        "failure_signature": str(diagnostics.get("failure_signature") or "missing"),
        "read_count": int(semantic.get("read_count") or 0),
        "auxiliary_reads": sorted(set(auxiliary_reads)),
        "prepared_selected_inputs": ordered_unique_upper(prepared.get("selected_inputs") or []),
        "prepared_traced_inputs": ordered_unique_upper(prepared.get("traced_inputs") or auxiliary_reads),
        "metric_failures": metric_failures,
        "metric_failure_metrics": ordered_unique_strings(
            str(item.get("metric") or "").strip()
            for item in metric_failures
            if str(item.get("metric") or "").strip()
        ),
        "prepared_issue_kinds": [
            str(item.get("kind") or "").strip()
            for item in issues
            if str(item.get("kind") or "").strip()
        ],
        "has_prepared_error": any(str(item.get("severity") or "").lower() == "error" for item in issues),
    }


def evidence_comparability(
    *,
    declaration: dict[str, object],
    runtime: dict[str, object],
    validation_completed: bool,
    result: dict,
) -> tuple[bool, str]:
    if not validation_completed:
        return False, "validation_not_completed"
    if not declaration["protocol_complete"]:
        return False, "declaration_protocol_incomplete"
    effective_window = result.get("effective_window") if isinstance(result.get("effective_window"), dict) else {}
    if not effective_window.get("start") or not effective_window.get("end"):
        return False, "missing_effective_window"
    if runtime.get("has_prepared_error"):
        return False, "prepared_input_error"
    return True, "comparable"


def derive_evidence_label(
    *,
    declaration: dict[str, object],
    runtime: dict[str, object],
    validation_completed: bool,
    comparable: bool,
    run_type: str,
    result_present: bool,
    engine_scaffold_status: str = "",
) -> str:
    runtime_stage = str(runtime["runtime_stage"])
    verdict = str(runtime["verdict"])
    semantic_verdict = str(runtime["semantic_verdict"])
    auxiliary_reads = list(runtime["auxiliary_reads"])

    if not result_present:
        return "workflow_blocker"
    if verdict == "ERROR" and runtime_stage in {"context_build", "data_access", "load_engine", "compute_strategy", "missing", "workflow"}:
        return "workflow_blocker"
    if semantic_verdict == "ERROR" or runtime.get("has_prepared_error"):
        return "runtime_invalid"
    if run_type == "debug":
        return "diagnostic_only"
    if engine_scaffold_status == "starter_scaffold":
        return "diagnostic_only"
    if not declaration["protocol_complete"]:
        return "protocol_incomplete"
    if declaration["evidence_intent"] == "diagnostic":
        return "diagnostic_only"
    if not validation_completed:
        return "workflow_blocker"
    if not comparable:
        return "non_comparable"
    if not auxiliary_reads:
        return "target_control_evidence"
    if declaration["input_claim"] == "graph_supported":
        selected = set(str(item).upper() for item in declaration["selected_inputs"])
        if selected and selected.intersection(auxiliary_reads):
            return "candidate_causal_evidence"
    if declaration["input_claim"] in {"supplement", "mixed"}:
        return "supplemental_evidence"
    return "supplemental_evidence"


def branch_parent_branch_id(branch_dir: Path) -> str:
    branch_spec = load_branch_spec(branch_dir)
    return str(branch_spec.get("parent_branch_id") or "").strip()


def latest_row_by_decision(
    rows: list[dict[str, str]],
    decision: str,
) -> dict[str, str] | None:
    for row in reversed(rows):
        if row.get("decision") == decision:
            return row
    return None


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
            f"Desired start remains {requested_start}. Target-safe coverage is currently observed from "
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
            "while earlier starts remain a branch-level coverage tradeoff."
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
    for line in readiness_coverage_hint_lines(readiness):
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
            f"{requested_start}. Treat this as coverage context; branches that depend on strict "
            "overlap should inspect coverage hints."
        )
    return ""


def readiness_coverage_hint_lines(readiness: dict) -> list[str]:
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


def _branch_input_list(branch_spec: dict) -> list[str]:
    return [
        str(item).strip().upper()
        for item in (branch_spec.get("selected_inputs") or [])
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
    selected_inputs = _branch_input_list(branch_spec)
    inputs_text = ", ".join(selected_inputs) if selected_inputs else "none"
    starter_scaffold = branch_uses_default_scaffold(branch, discovery, readiness, session)
    inputs_prepared = branch_inputs_ready(branch)

    lines = [
        f"target={target}",
        f"selected_inputs={len(selected_inputs)} ({inputs_text})",
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
                "Validation ran; this result recorded a zero-information or flat signal.",
            )
        return (
            "validation_result",
            "Validation ran on the current mechanism; interpret this as research evidence rather than a workflow blocker.",
        )

    if verdict == "PASS" and str(semantic.get("verdict") or "").upper() == "PASS":
        return (
            "preflight_ready",
            "Semantic preflight passed; this debug run has not recorded validation evidence.",
        )

    return (
        "unclear_result_state",
        "The branch produced a result, but the current state still needs manual inspection.",
    )


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
    if isinstance(dependencies, dict):
        dependencies = canonicalize_dependencies_payload(dependencies)
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
        selected_inputs=branch_selected_inputs(branch_spec),
        cache_payload=(dependencies.get("cache") or {}) if isinstance(dependencies, dict) else {},
        readiness=readiness,
    )
    if data_manifest_path(branch).exists():
        data_manifest = json.loads(data_manifest_path(branch).read_text(encoding="utf-8"))
    data_manifest = canonicalize_data_manifest_payload(data_manifest)
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
    cache_path = (cache or {}).get("path")
    if cache_root:
        primary_feed["cache_root"] = cache_root
    if cache_path:
        primary_feed["path"] = cache_path
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
            **({"path": item.get("path")} if item.get("path") else {}),
        }
    return {
        "schema_version": 1,
        "workspace_root": str(workspace_root) if workspace_root is not None else None,
        "experiment": current_experiment_metadata(),
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
        "branch_declaration": branch_declaration_status(branch_spec),
        "engine_scaffold_status": (
            "starter_scaffold"
            if branch_uses_default_scaffold(branch, discovery, readiness, session)
            else "branch_specific_engine"
        ),
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


def current_experiment_metadata() -> dict[str, str]:
    return {
        key: str(os.environ.get(env_name) or "").strip()
        for key, env_name in EXPERIMENT_METADATA_ENV.items()
    }


def session_experiment_metadata(
    branches: list[dict],
    rows: list[dict[str, object]],
) -> dict[str, str]:
    del branches
    for row in reversed(rows):
        metadata = context_experiment_metadata(row)
        if any(metadata.values()):
            return metadata
    return {key: "" for key in EXPERIMENT_METADATA_ENV}


def context_experiment_metadata(payload: dict) -> dict[str, str]:
    empty = {key: "" for key in EXPERIMENT_METADATA_ENV}
    experiment = payload.get("experiment") if isinstance(payload, dict) else None
    if not isinstance(experiment, dict):
        return empty
    return {
        key: str(experiment.get(key) or "").strip()
        for key in EXPERIMENT_METADATA_ENV
    }


def round_experiment_metadata(branch_dir: Path, round_id: str) -> dict[str, str]:
    empty = {key: "" for key in EXPERIMENT_METADATA_ENV}
    if not round_id:
        return empty
    note = read_round_note(branch_dir, round_id)
    context_path_raw = note.get("context_path", "")
    if not context_path_raw:
        return empty
    session = branch_dir.parent.parent
    context_path = session / Path(context_path_raw)
    if not context_path.exists():
        return empty
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    experiment = payload.get("experiment")
    if not isinstance(experiment, dict):
        return empty
    return {
        key: str(experiment.get(key) or "").strip()
        for key in EXPERIMENT_METADATA_ENV
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


def normalize_evidence_intent(branch_spec: dict) -> str:
    configured = str(branch_spec.get("evidence_intent") or "").strip().lower()
    if configured in EVIDENCE_INTENTS:
        return configured
    return ""


def normalize_input_claim(branch_spec: dict) -> str:
    configured = str(branch_spec.get("input_claim") or "").strip().lower()
    if configured in INPUT_CLAIMS:
        return configured
    return ""


def normalize_model_family(branch_spec: dict) -> str:
    configured = str(branch_spec.get("model_family") or "").strip().lower()
    if configured in MODEL_FAMILIES:
        return configured
    return "unspecified"


def normalize_complexity_class(branch_spec: dict) -> str:
    configured = str(branch_spec.get("complexity_class") or "").strip().lower()
    if configured in COMPLEXITY_CLASSES:
        return configured
    model_family = normalize_model_family(branch_spec)
    if model_family in {"tree_model", "learned_model", "ensemble"}:
        return "learned_model"
    if model_family == "hybrid":
        return "hybrid"
    return "unspecified"


def normalize_exploration_role(branch_spec: dict) -> str:
    configured = str(branch_spec.get("exploration_role") or "").strip().lower()
    if configured in EXPLORATION_ROLES:
        return configured
    evidence_intent = normalize_evidence_intent(branch_spec)
    if evidence_intent == "control":
        return "control"
    if evidence_intent == "diagnostic":
        return "diagnostic"
    if evidence_intent == "candidate":
        return "candidate"
    return "unspecified"


def branch_selected_inputs(branch_spec: dict) -> list[str]:
    raw = branch_spec.get("selected_inputs")
    if not isinstance(raw, list):
        return []
    return ordered_unique_upper(raw)


def ordered_unique_upper(values) -> list[str]:
    return ordered_unique_strings(str(item or "").strip().upper() for item in values)


def ordered_unique_strings(values) -> list[str]:
    selected: list[str] = []
    for item in values:
        value = str(item or "").strip()
        if value and value not in selected:
            selected.append(value)
    return selected


def canonicalize_branch_spec_inputs(payload: dict) -> dict:
    branch_spec = dict(payload)
    selected = branch_selected_inputs(branch_spec)
    if selected or "selected_inputs" in branch_spec:
        branch_spec["selected_inputs"] = selected
    branch_spec.pop("selected_drivers", None)
    return branch_spec


def branch_declaration_status(branch_spec: dict) -> dict[str, object]:
    hypothesis = str(branch_spec.get("hypothesis") or "").strip()
    evidence_intent = normalize_evidence_intent(branch_spec)
    input_claim = normalize_input_claim(branch_spec)
    mechanism_family = str(branch_spec.get("mechanism_family") or "").strip().lower()
    invalidation_condition = str(branch_spec.get("invalidation_condition") or "").strip()
    requested_start = str(branch_spec.get("requested_start") or "").strip()
    selected_inputs = branch_selected_inputs(branch_spec)

    gaps: list[str] = []
    if not has_explicit_hypothesis(hypothesis):
        gaps.append("hypothesis")
    if evidence_intent not in EVIDENCE_INTENTS:
        gaps.append("evidence_intent")
    if input_claim not in INPUT_CLAIMS:
        gaps.append("input_claim")
    if mechanism_family in DECLARATION_PLACEHOLDER_VALUES:
        gaps.append("mechanism_family")
    if not invalidation_condition:
        gaps.append("invalidation_condition")
    if not requested_start:
        gaps.append("requested_start")
    if input_claim in GRAPH_INPUT_CLAIMS and not selected_inputs:
        gaps.append("selected_inputs")
    if evidence_intent == "draft":
        gaps.append("evidence_intent:draft")

    return {
        "protocol_complete": not gaps,
        "protocol_gaps": gaps,
        "hypothesis": hypothesis,
        "evidence_intent": evidence_intent,
        "input_claim": input_claim,
        "mechanism_family": mechanism_family,
        "model_family": normalize_model_family(branch_spec),
        "complexity_class": normalize_complexity_class(branch_spec),
        "exploration_role": normalize_exploration_role(branch_spec),
        "invalidation_condition": invalidation_condition,
        "requested_start": requested_start,
        "selected_inputs": selected_inputs,
    }


def branch_declaration_status_for_branch(branch: Path) -> dict[str, object]:
    return branch_declaration_status(load_branch_spec(branch))


def load_branch_spec(branch: Path) -> dict:
    path = branch_spec_path(branch)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return canonicalize_branch_spec_inputs(payload) if isinstance(payload, dict) else {}


def write_branch_spec(branch: Path, payload: dict) -> None:
    payload = canonicalize_branch_spec_inputs(payload)
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
    graph_first = bool(selected)
    return {
        "version": 2,
        "branch_id": branch.name,
        "target": discovery.get("ticker", branch.parent.parent.parent.name.upper()),
        "hypothesis": "",
        "evidence_intent": "draft",
        "input_claim": "graph_supported" if graph_first else "target_only",
        "mechanism_family": "unspecified",
        "invalidation_condition": "",
        "model_family": "unspecified",
        "complexity_class": "unspecified",
        "exploration_role": "candidate",
        "parent_branch_id": "",
        "requested_start": _get_backtest_start(discovery),
        "resolved_start_policy": "requested",
        "overlap_mode": "target_only",
        "selected_inputs": selected,
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
    selected_inputs: list[str],
    requested_start: str,
) -> dict:
    selected_inputs = ordered_unique_upper(selected_inputs)
    return {
        "version": 1,
        "branch_id": branch.name,
        "target": target,
        "selected_inputs": selected_inputs,
        "requested_start": requested_start,
        "overlap_mode": branch_spec.get("overlap_mode") or "target_only",
        "data_requirements": branch_spec.get("data_requirements") or {"timeframe": "1d"},
        "prepared_at": _now(),
    }


def canonicalize_dependencies_payload(payload: dict) -> dict:
    dependencies = dict(payload)
    raw = dependencies.get("selected_inputs")
    selected = ordered_unique_upper(raw if isinstance(raw, list) else [])
    if selected or "selected_inputs" in dependencies:
        dependencies["selected_inputs"] = selected
    dependencies.pop("selected_drivers", None)
    return dependencies


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
    selected_inputs: list[str],
    cache_payload: dict,
    readiness: dict,
) -> dict:
    selected_inputs = ordered_unique_upper(selected_inputs)
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
    ordered_symbols = [target] + [ticker for ticker in selected_inputs if ticker != target]
    adapter = str(cache_payload.get("adapter") or "abel")
    path = cache_payload.get("path")
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
        if path:
            feed_entry["path"] = path
        feeds.append(feed_entry)
    return {
        "version": 1,
        "target": target,
        "selected_inputs": selected_inputs,
        "feeds": feeds,
    }


def canonicalize_data_manifest_payload(payload: dict) -> dict:
    manifest = dict(payload)
    raw_selected = manifest.get("selected_inputs")
    selected = ordered_unique_upper(raw_selected if isinstance(raw_selected, list) else [])
    feeds: list[dict[str, object]] = []
    seen_feeds: set[str] = set()
    for item in manifest.get("feeds") or []:
        if not isinstance(item, dict):
            continue
        feed = dict(item)
        symbol = str(feed.get("symbol") or "").strip().upper()
        name = str(feed.get("name") or symbol or "").strip()
        key = name or symbol
        if not key or key in seen_feeds:
            continue
        if symbol:
            feed["symbol"] = symbol
        if name:
            feed["name"] = name
        feeds.append(feed)
        seen_feeds.add(key)
    manifest["selected_inputs"] = selected
    manifest.pop("selected_drivers", None)
    manifest["feeds"] = feeds
    return manifest


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
        "## Declaration Fields",
        "- `hypothesis`: concrete claim being tested",
        "- `evidence_intent`: candidate, control, diagnostic, or draft",
        "- `input_claim`: graph_supported, target_only, supplement, or mixed",
        "- `mechanism_family`: factual mechanism label",
        "- `invalidation_condition`: what would weaken the claim",
        "",
        "## Protocol Checklist",
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
        coverage_hints_text=", ".join(readiness_coverage_hint_lines(readiness)) or "none",
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
            "changed_dimensions",
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
    changed_dimensions = ordered_unique_strings(kwargs.get("changed_dimensions") or [])
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

## Exploration Facts

- changed_dimensions: `{", ".join(changed_dimensions) or "none"}`

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
- next_step: `{kwargs.get("next_step") or "not recorded"}`
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


def ensure_research_journal(session: Path) -> Path:
    path = session / RESEARCH_JOURNAL_FILENAME
    if not path.exists():
        path.write_text(build_research_journal_template(session), encoding="utf-8")
    return path


def build_research_journal_template(session: Path) -> str:
    return f"""# Research Journal

agent-owned research notes for session `{session.name}`

## Boundary

- `evidence_ledger.json` and `frontier.md` are the system-owned evidence facts.
- This journal is for the agent's hypotheses, observations, pivots, and stop/continue reasoning.
- Every recorded round requires an agent-written note below with its ledger evidence reference.
- Capture what changed, what happened, what was learned, and what that implies for the next exploration step.
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
