"""Abel strategy discovery research narrative layer.

Organizes exploration sessions, records experimental process, and renders narrative
summaries on top of raw abel-edge evaluation outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from abel_invest.branch_spec import (
    _get_backtest_start,
    branch_requested_start,
    branch_declaration_status,
    branch_declaration_status_for_branch,
    branch_dependencies_payload,
    branch_selected_inputs,
    build_context_guide_markdown,
    build_data_manifest_payload,
    build_default_branch_spec,
    build_execution_constraints_payload,
    build_probe_samples_payload,
    build_runtime_profile_payload,
    canonicalize_data_manifest_payload,
    canonicalize_dependencies_payload,
    discovery_candidate_tickers,
    has_explicit_hypothesis,
    load_branch_spec,
    normalize_complexity_class,
    normalize_evidence_intent,
    normalize_exploration_role,
    normalize_hypothesis_text,
    normalize_input_claim,
    normalize_model_family,
    suggest_branch_drivers,
    write_branch_spec,
)
from abel_invest.cli_parser import build_parser
from abel_invest.dashboard import (
    build_skill_dashboard_bundle,
    dashboard_branch_target_asset,
    dashboard_branch_target_node,
    dashboard_latest_evidence_label,
    dashboard_round_is_candidate,
    first_round_id_from_refs,
    journal_reference_matches_branch,
    post_skill_dashboard_bundle,
    require_timezone_aware_iso,
    resolve_skill_dashboard_api_key,
    resolve_skill_dashboard_base_url,
    skill_dashboard_branch_insights,
    skill_dashboard_episodes,
    skill_dashboard_rounds,
    upload_skill_dashboard_bundle,
)
from abel_invest.doctor import (
    build_auth_recovery_instruction,
    doctor_exit_code,
    render_doctor_report,
    run_doctor,
)
from abel_invest.edge_runtime import (
    build_workspace_runtime_env,
    resolve_runtime_auth_env_file,
)
from abel_invest.edge_commands import (
    resolve_default_python_bin,
    run_edge_verify_data,
)
from abel_invest.env import init_workspace_env
from abel_invest.evidence import (
    annotate_exploration_protocol,
    build_input_realization,
    derive_evidence_label,
    derive_exploration_class,
    evidence_comparability,
    evidence_runtime_facts,
    metric_string,
    normalize_optional_note,
    parse_changed_dimensions,
)
from abel_invest.frontier import (
    branch_family_key,
    build_frontier,
    canonical_driver_set_label,
    discovered_driver_tickers,
    exploration_neighborhood_key,
    fraction_pair,
    render_frontier_markdown,
    render_inline_counts,
    render_session_frontier_summary,
)
from abel_invest.workspace import (
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
from abel_invest.constants import (
    AGENT_CONTEXT_FILENAME,
    BRANCH_SPEC_FILENAME,
    BRANCH_STATE_FILENAME,
    BROAD_CHANGED_DIMENSIONS,
    CHANGED_DIMENSIONS,
    COMPLEXITY_CLASSES,
    CONTEXT_GUIDE_FILENAME,
    DATA_MANIFEST_FILENAME,
    DECLARATION_PLACEHOLDER_VALUES,
    DEFAULT_BACKTEST_START,
    DEPENDENCIES_FILENAME,
    EVIDENCE_INTENTS,
    EVIDENCE_LEDGER_FILENAME,
    EVENTS_HEADER,
    EXECUTION_CONSTRAINTS_FILENAME,
    EXPLORATION_ROLES,
    FRONTIER_JSON_FILENAME,
    FRONTIER_MARKDOWN_FILENAME,
    GRAPH_INPUT_CLAIMS,
    GRAPH_PRIORITY_ROUND_MINIMUM,
    INPUT_BREADTH_ROUND_THRESHOLD,
    INPUT_CLAIMS,
    JOURNAL_GENERATED_HEADER_END,
    JOURNAL_REFERENCE_RE,
    LOCAL_CHANGED_DIMENSIONS,
    MODEL_FAMILIES,
    PROBE_SAMPLES_FILENAME,
    READINESS_FILENAME,
    RESEARCH_JOURNAL_FILENAME,
    RESULTS_HEADER,
    RUNTIME_PROFILE_FILENAME,
    SESSION_STATE_FILENAME,
)
from abel_invest.context import (
    alpha_decision,
    alpha_decision_with_runtime,
    branch_context_summary_lines,
    branch_parent_branch_id,
    branch_runtime_advisory_lines,
    build_branch_context,
    classify_result_frame,
    format_discovery_nodes,
    format_simple_nodes,
    latest_row_by_decision,
    validate_edge_handoff,
)
from abel_invest.io import (
    SessionLock,
    _now,
    _today,
    append_tsv_row,
    read_tsv_rows,
    write_json_file,
    write_tsv_header,
    write_tsv_rows,
)
from abel_invest.journal import (
    build_journal_coverage,
    build_research_journal_status,
    build_research_journal_template,
    compact_research_journal_status,
    ensure_research_journal,
    journal_round_key,
    ledger_round_key_from_ref,
    recent_journal_excerpt,
    resolve_evidence_reference,
)
from abel_invest.paths import (
    branch_spec_path,
    branch_state_path,
    context_guide_path,
    data_manifest_path,
    dependencies_path,
    execution_constraints_path,
    probe_samples_path,
    runtime_profile_path,
    session_state_path,
)
from abel_invest.readiness import (
    build_readiness_warning,
    format_data_readiness_summary,
    readiness_results,
    readiness_coverage_hint_lines,
    readiness_start_covered_tickers,
    readiness_usable_tickers,
    render_discovery_readiness_section,
    render_readiness_guidance,
    render_target_boundary_line,
)
from abel_invest.renderers import (
    build_agent_context,
    render_agent_context,
    render_agent_context_evidence_rows,
    render_agent_context_exploration_breadth,
    render_agent_context_graph_priority,
    render_agent_context_input_breadth,
    render_agent_context_input_realization,
    render_agent_context_journal_coverage,
    render_agent_context_research_journal,
    render_agent_context_research_reflection,
    render_round_note,
)
from abel_invest.state import (
    branch_inputs_ready,
    branch_progression,
    branch_uses_default_scaffold,
    build_branch_snapshot_line,
    build_debug_snapshot,
    context_experiment_metadata,
    current_branch_hypothesis,
    current_experiment_metadata,
    format_risks,
    latest_debug_snapshot,
    latest_recorded_hypothesis,
    load_branch_state,
    load_branches,
    load_discovery,
    load_readiness,
    load_session_state,
    persist_branch_hypothesis,
    persist_debug_snapshot,
    read_round_note,
    readiness_warning_fingerprint,
    render_default_engine_template,
    resolve_backtest_start_request,
    resolve_branch_hypothesis,
    round_experiment_metadata,
    session_experiment_metadata,
    should_emit_missing_hypothesis_warning,
    should_emit_readiness_warning,
    update_backtest_start,
    write_branch_state,
    write_session_state,
)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "workspace":
        return handle_workspace_command(args)
    if args.command == "env":
        return handle_env_command(args)
    if args.command == "doctor":
        return handle_doctor_command(args)
    if args.command == "frontier":
        return handle_frontier_command(args)
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
        frontier = load_graph_frontier(session)
        print(f"Created Abel strategy discovery session at {session}")
        print(f"  ticker: {discovery.get('ticker', args.ticker.upper())}")
        print(f"  graph_frontier: {session / GRAPH_FRONTIER_FILENAME}")
        print(f"  journal: {session / RESEARCH_JOURNAL_FILENAME}")
        print(f"  events: {session / 'events.tsv'}")
        if readiness:
            print(f"  readiness: {session / READINESS_FILENAME}")
        if args.discover:
            print(
                f"  frontier_source: {frontier.get('source', 'unknown')} "
                f"(nodes={len(frontier.get('nodes') or [])})"
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
        print(f"  abel-invest status --session {session}")
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
        print(f"  abel-invest debug-branch --branch {branch}")
        print(f"  abel-invest run-branch --branch {branch} -d \"baseline\"")
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
        print(f"  abel-invest prepare-branch --branch {branch}")
        print(f"  abel-invest debug-branch --branch {branch}")
        print(f"  abel-invest run-branch --branch {branch} -d \"baseline\"")
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
    if args.command == "visualize-session":
        return upload_skill_dashboard_session(args)
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
            print(f"  abel-invest workspace status --path {related_root}")
            print(f"  abel-invest doctor --path {related_root}")
            return 1
        if target_state == "launch_root_child_workspace" and related_root is not None:
            print(f"Workspace already exists at the default child path: {related_root}")
            print("Reuse it instead of creating another workspace for the same area.")
            print("")
            print("Continue there instead:")
            print(f"  abel-invest workspace status --path {related_root}")
            print(f"  abel-invest doctor --path {related_root}")
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
        print("  abel-invest workspace status")
        print(f"  abel-invest workspace bootstrap --path {root}")
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
            print(f"  abel-invest workspace status --path {related_root}")
            print(f"  abel-invest doctor --path {related_root}")
            return 1
        if target_state == "launch_root_child_workspace" and related_root is not None:
            print(f"Workspace already exists at the default child path: {related_root}")
            print("Reuse it instead of bootstrapping another workspace for the same area.")
            print("")
            print("Continue there instead:")
            print(f"  abel-invest workspace status --path {related_root}")
            print(f"  abel-invest doctor --path {related_root}")
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
            print("  abel-invest init-session --ticker <TICKER> --exp-id <session-id>  # runs live graph discovery by default")
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
    print("  alpha_install_reason: installs the packaged abel-invest CLI into this workspace runtime")
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
        print("  Run `abel-invest doctor` and upgrade the workspace runtime before starting research.")
        print("")
    print("From here:")
    print("  abel-invest doctor")
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


def handle_frontier_command(args: argparse.Namespace) -> int:
    session = resolve_workspace_arg_path(args.session)
    if args.frontier_command == "status":
        print_graph_frontier_status(session)
        return 0
    if args.frontier_command == "expand":
        anchor = normalize_graph_node_ref(args.anchor)
        with SessionLock(session):
            frontier = load_graph_frontier(session)
            expansion_payload = fetch_live_graph_expansion(
                anchor,
                mode=args.mode,
                limit=args.limit,
            )
            updated, expansion = merge_graph_frontier_expansion(
                frontier,
                expansion_payload,
                anchor_node=anchor,
                mode=args.mode,
                limit=args.limit,
            )
            write_graph_frontier(session, updated)
            append_tsv_row(
                session / "events.tsv",
                EVENTS_HEADER,
                {
                    "timestamp": _now(),
                    "event": "frontier_expanded",
                    "branch_id": "",
                    "round_id": "",
                    "mode": args.mode,
                    "verdict": "",
                    "decision": "",
                    "description": (
                        f"Expanded graph frontier from {anchor}: "
                        f"new_nodes={len(expansion.get('new_nodes') or [])} "
                        f"updated_nodes={len(expansion.get('updated_nodes') or [])}"
                    ),
                    "artifact_path": GRAPH_FRONTIER_FILENAME,
                },
            )
            render_session(session)
        print(f"Expanded graph frontier at {session / GRAPH_FRONTIER_FILENAME}")
        print(f"  anchor: {anchor}")
        print(f"  mode: {args.mode}")
        print(f"  new_nodes: {len(expansion.get('new_nodes') or [])}")
        print(f"  updated_nodes: {len(expansion.get('updated_nodes') or [])}")
        print("")
        print("Frontier status:")
        print_graph_frontier_status(session)
        return 0
    return 1


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
        f"abel-invest init-branch --session {session} --branch-id <family-a-branch>",
        f"abel-invest init-branch --session {session} --branch-id <family-b-branch>",
        "edit each branch.yaml with graph-node hypotheses and agent-chosen mechanism-family declarations",
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
    graph_frontier = None
    readiness_report = None
    if discover:
        graph_frontier = fetch_live_graph_frontier(
            ticker,
            limit=discover_limit,
            backtest_start=backtest_start,
        )
        discovery_data = graph_frontier_to_discovery(graph_frontier)
        readiness_report = refresh_data_readiness(
            session=session,
            discovery_data=discovery_data,
            backtest_start=backtest_start,
        )
    else:
        graph_frontier = build_pending_graph_frontier(
            ticker,
            backtest_start=backtest_start,
        )
    with SessionLock(session):
        write_tsv_header(session / "events.tsv", EVENTS_HEADER)
        if not session_state_path(session).exists():
            write_session_state(session, {})
        write_graph_frontier(session, graph_frontier)
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
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "frontier_initialized",
                "branch_id": "",
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": (
                    f"Initialized graph frontier from {graph_frontier.get('source', 'unknown')} "
                    f"with {len(graph_frontier.get('nodes') or [])} nodes"
                ),
                "artifact_path": GRAPH_FRONTIER_FILENAME,
            },
        )
        if discover:
            append_tsv_row(
                session / "events.tsv",
                EVENTS_HEADER,
                {
                    "timestamp": _now(),
                    "event": "frontier_expanded",
                    "branch_id": "",
                    "round_id": "",
                    "mode": "",
                    "verdict": "",
                    "decision": "",
                    "description": (
                        f"Recorded live Abel frontier expansion with "
                        f"{len(graph_frontier.get('nodes') or [])} frontier nodes"
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


def fetch_live_graph_frontier(
    ticker: str,
    *,
    limit: int,
    backtest_start: str,
) -> dict:
    try:
        from abel_edge.plugins.abel.credentials import (
            MissingAbelApiKeyError,
            require_api_key,
        )
        from abel_edge.plugins.abel.discover import discover_graph_payload
    except ImportError as exc:
        raise RuntimeError(
            "Live Abel discovery requires abel-edge with the Abel plugin installed. "
            "Create a virtual environment, install abel-edge, then retry."
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
            "After auth is ready, retry `abel-invest init-session --ticker "
            f"{ticker.upper()} --exp-id <exp-id>`."
        ) from exc

    payload = discover_graph_payload(ticker.upper(), mode="all", limit=limit)
    return graph_frontier_from_discovery_payload(
        payload,
        backtest_start=backtest_start,
        expansion_mode="all",
        expansion_limit=limit,
    )


def fetch_live_graph_expansion(
    anchor_node: str,
    *,
    mode: str,
    limit: int,
) -> dict:
    try:
        from abel_edge.plugins.abel.credentials import (
            MissingAbelApiKeyError,
            require_api_key,
        )
        from abel_edge.plugins.abel.discover import discover_graph_payload
    except ImportError as exc:
        raise RuntimeError(
            "Live Abel frontier expansion requires abel-edge with the Abel plugin installed. "
            "Create a virtual environment, install abel-edge, then retry."
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
            "frontier expand is blocked on Abel auth. "
            "No reusable auth was found. "
            f"{build_auth_recovery_instruction(workspace_root or Path.cwd())}"
        ) from exc

    return discover_graph_payload(anchor_node, mode=mode, limit=limit)


def write_graph_frontier_from_discovery_payload(session: Path, discovery_data: dict) -> None:
    write_graph_frontier(
        session,
        graph_frontier_from_discovery_payload(
            discovery_data,
            backtest_start=_get_backtest_start(discovery_data),
            expansion_mode=str(discovery_data.get("mode") or "all"),
            expansion_limit=int(discovery_data.get("K_discovery") or 10),
        ),
    )


def graph_frontier_path(session: Path) -> Path:
    return session / GRAPH_FRONTIER_FILENAME


def load_graph_frontier(session: Path) -> dict:
    path = graph_frontier_path(session)
    if not path.exists():
        return build_pending_graph_frontier(
            session.parent.name.upper(),
            backtest_start=DEFAULT_BACKTEST_START,
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_graph_frontier(session: Path, frontier: dict) -> None:
    graph_frontier_path(session).write_text(
        json.dumps(frontier, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def print_graph_frontier_status(session: Path) -> None:
    frontier = load_graph_frontier(session)
    facts = graph_frontier_facts(frontier)
    print(f"Session: {session.name}")
    print(f"Graph frontier: {session / GRAPH_FRONTIER_FILENAME}")
    print(f"Target node: {facts['target_node']}")
    print(f"Source: {facts['source']}")
    print(f"Nodes: {facts['node_count']}")
    print(f"Expansions: {facts['expansion_count']}")
    print(f"Expanded anchors: {facts['expanded_anchor_count']}")
    print(f"Unexpanded nodes: {facts['unexpanded_node_count']}")
    print(f"Fields: {render_inline_counts(facts['field_counts'])}")
    print(f"Roles: {render_inline_counts(facts['role_counts'])}")


def graph_frontier_facts(frontier: dict) -> dict[str, object]:
    nodes = [node for node in frontier.get("nodes") or [] if isinstance(node, dict)]
    expansions = [
        item for item in frontier.get("expansions") or [] if isinstance(item, dict)
    ]
    expanded_anchors = {
        str(item.get("anchor_node") or "").strip()
        for item in expansions
        if str(item.get("anchor_node") or "").strip()
    }
    field_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for node in nodes:
        increment_count(field_counts, str(node.get("field") or "unknown"))
        roles = node.get("discovery_roles") or ["unknown"]
        for role in roles:
            increment_count(role_counts, str(role or "unknown"))
    unexpanded = [
        node
        for node in nodes
        if str(node.get("node_id") or "") not in expanded_anchors
        and "target" not in set(str(role) for role in node.get("discovery_roles") or [])
    ]
    return {
        "target_node": str(frontier.get("target_node") or "unknown"),
        "source": str(frontier.get("source") or "unknown"),
        "node_count": len(nodes),
        "expansion_count": len(expansions),
        "expanded_anchor_count": len(expanded_anchors),
        "unexpanded_node_count": len(unexpanded),
        "field_counts": dict(sorted(field_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
    }


def build_pending_graph_frontier(
    ticker: str,
    *,
    backtest_start: str,
) -> dict:
    now = _now()
    target_asset = str(ticker or "").strip().upper()
    target_node = default_graph_node_id(target_asset)
    return {
        "schema_version": 1,
        "target_asset": target_asset,
        "target_node": target_node,
        "requested_window": {"start": backtest_start, "end": None},
        "source": "pending",
        "created_at": now,
        "updated_at": now,
        "nodes": [
            build_frontier_node(
                node_id=target_node,
                roles=["target"],
                discovered_from="session",
                depth=0,
                seen_at=now,
            )
        ],
        "expansions": [],
    }


def merge_graph_frontier_expansion(
    frontier: dict,
    payload: dict,
    *,
    anchor_node: str,
    mode: str,
    limit: int,
) -> tuple[dict, dict]:
    now = str(payload.get("created_at") or _now())
    anchor_node = normalize_graph_node_ref(anchor_node)
    updated = dict(frontier)
    updated.setdefault("schema_version", 1)
    updated.setdefault("target_asset", split_graph_node_id(anchor_node)[0])
    updated.setdefault("target_node", anchor_node)
    updated.setdefault("requested_window", {"start": DEFAULT_BACKTEST_START, "end": None})
    updated["source"] = "abel_live" if updated.get("source") in {"", "pending", None} else updated.get("source")
    updated["updated_at"] = now

    node_map = {
        str(node.get("node_id") or ""): dict(node)
        for node in updated.get("nodes") or []
        if isinstance(node, dict) and str(node.get("node_id") or "")
    }
    anchor = node_map.get(anchor_node)
    if anchor is None:
        anchor = build_frontier_node(
            node_id=anchor_node,
            roles=["expansion_anchor"],
            discovered_from="agent",
            depth=0,
            seen_at=now,
        )
        node_map[anchor_node] = anchor
    anchor["last_expanded_at"] = now
    anchor_depth = int(anchor.get("depth") or 0)

    new_nodes: list[str] = []
    updated_nodes: list[str] = []
    for section, role in (
        ("parents", "parent"),
        ("blanket_new", "blanket"),
        ("children", "child"),
    ):
        for item in payload.get(section) or []:
            node_id = normalize_graph_node_ref(graph_node_id_from_item(item))
            if not node_id or node_id == anchor_node:
                continue
            roles = graph_roles_from_item(item, fallback=role)
            if node_id not in node_map:
                node_map[node_id] = build_frontier_node(
                    node_id=node_id,
                    roles=roles,
                    discovered_from=anchor_node,
                    depth=anchor_depth + 1,
                    seen_at=now,
                )
                new_nodes.append(node_id)
                continue
            existing = node_map[node_id]
            existing["discovery_roles"] = ordered_unique_strings(
                list(existing.get("discovery_roles") or []) + roles
            )
            existing["discovered_from"] = ordered_unique_strings(
                list(existing.get("discovered_from") or []) + [anchor_node]
            )
            existing["depth"] = min(
                int(existing.get("depth") or anchor_depth + 1),
                anchor_depth + 1,
            )
            updated_nodes.append(node_id)

    expansion = {
        "expansion_id": frontier_expansion_id(
            anchor_node=anchor_node,
            mode=mode,
            timestamp=now,
        ),
        "anchor_node": anchor_node,
        "mode": mode,
        "limit": limit,
        "source": str(payload.get("source") or "abel_live"),
        "new_nodes": ordered_unique_strings(new_nodes),
        "updated_nodes": ordered_unique_strings(updated_nodes),
        "created_at": now,
    }
    expansions = [item for item in updated.get("expansions") or [] if isinstance(item, dict)]
    expansions.append(expansion)
    updated["nodes"] = sorted(node_map.values(), key=lambda item: str(item.get("node_id") or ""))
    updated["expansions"] = expansions
    return updated, expansion


def graph_frontier_from_discovery_payload(
    payload: dict,
    *,
    backtest_start: str,
    expansion_mode: str,
    expansion_limit: int,
) -> dict:
    now = str(payload.get("created_at") or _now())
    target_asset = str(
        payload.get("target_asset") or payload.get("ticker") or ""
    ).strip().upper()
    target_node = str(payload.get("target_node") or "").strip() or default_graph_node_id(
        target_asset
    )
    nodes: dict[str, dict] = {}

    def remember(node: dict) -> None:
        key = str(node.get("node_id") or "").strip()
        if not key:
            return
        if key not in nodes:
            nodes[key] = node
            return
        existing = nodes[key]
        existing["discovery_roles"] = ordered_unique_strings(
            list(existing.get("discovery_roles") or [])
            + list(node.get("discovery_roles") or [])
        )
        existing["discovered_from"] = ordered_unique_strings(
            list(existing.get("discovered_from") or [])
            + list(node.get("discovered_from") or [])
        )
        existing["depth"] = min(int(existing.get("depth") or 0), int(node.get("depth") or 0))

    remember(
        build_frontier_node(
            node_id=target_node,
            roles=["target"],
            discovered_from="session",
            depth=0,
            seen_at=now,
        )
    )
    for section, role in (
        ("parents", "parent"),
        ("blanket_new", "blanket"),
        ("children", "child"),
    ):
        for item in payload.get(section) or []:
            node_id = graph_node_id_from_item(item)
            if not node_id or node_id == target_node:
                continue
            roles = graph_roles_from_item(item, fallback=role)
            remember(
                build_frontier_node(
                    node_id=node_id,
                    roles=roles,
                    discovered_from=target_node,
                    depth=1,
                    seen_at=now,
                )
            )
    expansion_nodes = [
        node_id for node_id in sorted(nodes) if node_id != target_node
    ]
    expansion_id = frontier_expansion_id(
        anchor_node=target_node,
        mode=expansion_mode,
        timestamp=now,
    )
    return {
        "schema_version": 1,
        "target_asset": target_asset,
        "target_node": target_node,
        "requested_window": {"start": backtest_start, "end": None},
        "source": str(payload.get("source") or "abel_live"),
        "created_at": now,
        "updated_at": now,
        "nodes": list(nodes.values()),
        "expansions": [
            {
                "expansion_id": expansion_id,
                "anchor_node": target_node,
                "mode": expansion_mode,
                "limit": expansion_limit,
                "source": str(payload.get("source") or "abel_live"),
                "new_nodes": expansion_nodes,
                "updated_nodes": [],
                "created_at": now,
            }
        ],
    }


def graph_frontier_to_discovery(frontier: dict) -> dict:
    target_asset = str(frontier.get("target_asset") or "").strip().upper()
    target_node = str(frontier.get("target_node") or "").strip() or default_graph_node_id(
        target_asset
    )
    discovery = {
        "ticker": target_asset,
        "target_asset": target_asset,
        "target_node": target_node,
        "source": frontier.get("source", "unknown"),
        "parents": [],
        "blanket_new": [],
        "children": [],
        "K_discovery": 0,
        "backtest": {"start": (frontier.get("requested_window") or {}).get("start", DEFAULT_BACKTEST_START)},
        "created_at": frontier.get("created_at", "unknown"),
    }
    for node in frontier.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id") or "").strip()
        if not node_id or node_id == target_node:
            continue
        item = {
            "node_id": node_id,
            "ticker": str(node.get("asset") or "").strip().upper(),
            "field": str(node.get("field") or "price").strip(),
        }
        roles = [str(role) for role in node.get("discovery_roles") or []]
        if "parent" in roles:
            discovery["parents"].append(item)
        elif "child" in roles:
            discovery["children"].append(item)
        else:
            item["roles"] = roles or ["neighbor"]
            discovery["blanket_new"].append(item)
    discovery["K_discovery"] = (
        len(discovery["parents"])
        + len(discovery["blanket_new"])
        + len(discovery["children"])
    )
    return discovery


def build_frontier_node(
    *,
    node_id: str,
    roles: list[str],
    discovered_from: str,
    depth: int,
    seen_at: str,
) -> dict:
    asset, field = split_graph_node_id(node_id)
    return {
        "node_id": node_id,
        "asset": asset,
        "field": field,
        "discovery_roles": ordered_unique_strings(roles),
        "discovered_from": ordered_unique_strings([discovered_from]),
        "depth": depth,
        "first_seen_at": seen_at,
        "last_expanded_at": None,
        "availability_summary": None,
        "branch_usage": [],
    }


def graph_node_id_from_item(item: object) -> str:
    if isinstance(item, dict):
        node_id = str(item.get("node_id") or "").strip()
        if node_id:
            return node_id
        asset = str(item.get("ticker") or item.get("symbol") or "").strip().upper()
        field = str(item.get("field") or "price").strip().lower()
        return f"{asset}.{field}" if asset else ""
    value = str(item or "").strip()
    if not value:
        return ""
    return value if "." in value else default_graph_node_id(value)


def graph_roles_from_item(item: object, *, fallback: str) -> list[str]:
    roles: list[str] = []
    if isinstance(item, dict):
        roles = [
            str(role).strip()
            for role in item.get("roles") or []
            if str(role).strip()
        ]
    return ordered_unique_strings([fallback, *roles])


def split_graph_node_id(node_id: str) -> tuple[str, str]:
    value = str(node_id or "").strip()
    if "." not in value:
        return value.upper(), "price"
    asset, field = value.split(".", 1)
    return asset.strip().upper(), field.strip().lower() or "price"


def normalize_graph_node_ref(value: str) -> str:
    asset, field = split_graph_node_id(value)
    if not asset:
        return ""
    return f"{asset}.{field}"


def default_graph_node_id(asset: str) -> str:
    return f"{str(asset or '').strip().upper()}.price"


def frontier_expansion_id(*, anchor_node: str, mode: str, timestamp: str) -> str:
    safe_anchor = re.sub(r"[^A-Za-z0-9]+", "-", anchor_node).strip("-").lower()
    safe_mode = re.sub(r"[^A-Za-z0-9]+", "-", mode).strip("-").lower()
    safe_time = re.sub(r"[^0-9A-Za-z]+", "", timestamp)[:15]
    return f"{safe_time}-{safe_anchor}-{safe_mode}".strip("-")


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
    """Compute the edge-owned data readiness report for a frontier-derived graph payload."""
    fd, temp_name = tempfile.mkstemp(dir=session, suffix="-frontier-readiness.json")
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
        graph_frontier = load_graph_frontier(session)
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
                    graph_frontier=graph_frontier,
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
    selected_input_entries = branch_selected_input_entries(branch_spec)
    selected_graph_nodes = branch_selected_graph_nodes(branch_spec)
    target_node = (
        normalize_graph_node_ref(str(branch_spec.get("target_node") or ""))
        or default_graph_node_id(target)
    )
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
        selected_graph_nodes=selected_graph_nodes,
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
        "abel_edge.cli",
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
                f"`abel-invest prepare-branch --branch {branch}`."
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
        target_node=target_node,
        selected_inputs=selected_inputs,
        selected_input_entries=selected_input_entries,
        selected_graph_nodes=selected_graph_nodes,
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
        print(f"  abel-invest prepare-branch --branch {branch}")
    else:
        print("  The branch inputs are ready; use debug preflight first, then record a round once the engine reflects the branch thesis.")
        print(f"  abel-invest debug-branch --branch {branch}")
        print(f"  abel-invest run-branch --branch {branch} -d \"baseline\"")
    return completed.returncode


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
            "Run `abel-invest prepare-branch --branch ...` before recording a round.",
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
        "abel_edge.cli",
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
    if (
        str(result.get("verdict") or "").upper() == "PASS"
        and decision == "keep"
        and dashboard_round_is_candidate(
            session=session,
            branch_id=branch.name,
            round_id=round_id,
        )
    ):
        print("")
        print("Session visualization available:")
        print(
            "  Candidate PASS recorded. Ask the user whether to create "
            "an online view of this session."
        )
        print("  If the user agrees, create it and share the returned link.")
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
                "contract": "abel-invest.workflow-blocker/v1",
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
            "contract": "abel-invest.workflow-blocker/v1",
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
        "abel_edge.cli",
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
    runtime = augment_runtime_graph_facts(
        runtime=runtime,
        declaration=declaration,
        context=context,
    )
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
        "declared_selected_graph_nodes": list(declaration["selected_graph_nodes"]),
        "changed_dimensions": changed_dimensions,
        "engine_scaffold_status": engine_scaffold_status or "unknown",
        "actual_auxiliary_reads": runtime["auxiliary_reads"],
        "actual_graph_node_reads": runtime["actual_graph_node_reads"],
        "actual_graph_node_read_source": runtime["actual_graph_node_read_source"],
        "actual_read_count": runtime["read_count"],
        "prepared_selected_inputs": runtime["prepared_selected_inputs"],
        "prepared_selected_graph_nodes": runtime["prepared_selected_graph_nodes"],
        "prepared_traced_inputs": runtime["prepared_traced_inputs"],
        "prepared_traced_graph_nodes": runtime["prepared_traced_graph_nodes"],
        "graph_node_read_gap": input_realization["graph_node_read_gap"],
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



def load_json_object(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}



def render_section(title: str, lines: list[str]) -> None:
    if not lines:
        return
    print(f"{title}:")
    for line in lines:
        print(f"  {line}")


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


if __name__ == "__main__":
    raise SystemExit(main())
