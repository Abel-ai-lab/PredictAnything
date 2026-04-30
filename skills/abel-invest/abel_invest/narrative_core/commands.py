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
from pathlib import Path

from abel_invest.narrative_core.contracts.branch_spec import (
    _get_backtest_start,
    branch_requested_start,
    branch_dependencies_payload,
    branch_selected_inputs,
    build_context_guide_markdown,
    build_data_manifest_payload,
    build_execution_constraints_payload,
    build_probe_samples_payload,
    build_runtime_profile_payload,
    has_explicit_hypothesis,
    load_branch_spec,
)
from abel_invest.narrative_core.cli_parser import build_parser
from abel_invest.narrative_core.dashboard import (
    upload_skill_dashboard_bundle,
)
from abel_invest.doctor import (
    doctor_exit_code,
    render_doctor_report,
    run_doctor,
)
from abel_invest.edge_runtime import (
    build_workspace_runtime_env,
)
from abel_invest.narrative_core.runtime.edge_commands import (
    resolve_default_python_bin,
)
from abel_invest.env import init_workspace_env
from abel_invest.workspace import (
    build_default_manifest,
    default_workspace_path,
    default_activate_command,
    inspect_workspace_bootstrap_target,
    is_workspace_root,
    find_workspace_root,
    load_workspace_manifest,
    resolve_workspace_entry,
    resolve_workspace_env_file,
    render_workspace_status,
    resolve_workspace_paths,
    scaffold_workspace,
)
from abel_invest.narrative_core.runtime.workflow_blockers import (
    record_workflow_blocker_round,
)
from abel_invest.narrative_core.contracts.constants import (
    BRANCH_SPEC_FILENAME,
    BRANCH_STATE_FILENAME,
    CONTEXT_GUIDE_FILENAME,
    DATA_MANIFEST_FILENAME,
    DEPENDENCIES_FILENAME,
    EVENTS_HEADER,
    EXECUTION_CONSTRAINTS_FILENAME,
    PROBE_SAMPLES_FILENAME,
    READINESS_FILENAME,
    RESEARCH_JOURNAL_FILENAME,
    RESULTS_HEADER,
    RUNTIME_PROFILE_FILENAME,
)
from abel_invest.narrative_core.runtime.context import (
    alpha_decision,
    branch_context_summary_lines,
    branch_runtime_advisory_lines,
    build_branch_context,
    classify_result_frame,
)
from abel_invest.narrative_core.io import (
    SessionLock,
    _now,
    append_tsv_row,
    read_tsv_rows,
)
from abel_invest.narrative_core.contracts.paths import (
    branch_spec_path,
    context_guide_path,
    data_manifest_path,
    dependencies_path,
    execution_constraints_path,
    probe_samples_path,
    runtime_profile_path,
)
from abel_invest.narrative_core.readiness import (
    build_readiness_warning,
    format_data_readiness_summary,
    readiness_coverage_hint_lines,
)
from abel_invest.narrative_core.rendering.renderers import (
    build_promotion_bundle_readme,
    render_round_note,
)
from abel_invest.narrative_core.session_lifecycle import (
    init_branch_dir,
    init_session_dir,
    render_breadth_first_start_lines,
    resolve_session_root,
    resolve_workspace_arg_path,
)
from abel_invest.narrative_core.rendering.session_rendering import (
    check_session,
    graph_priority_warning_lines,
    journal_coverage_missing_rounds,
    journal_coverage_warning_lines,
    print_status,
    render_section,
    render_session,
)
from abel_invest.narrative_core.state import (
    branch_inputs_ready,
    branch_uses_default_scaffold,
    build_debug_snapshot,
    load_discovery,
    load_readiness,
    persist_branch_hypothesis,
    persist_debug_snapshot,
    resolve_backtest_start_request,
    resolve_branch_hypothesis,
    should_emit_missing_hypothesis_warning,
    should_emit_readiness_warning,
    update_backtest_start,
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


if __name__ == "__main__":
    raise SystemExit(main())
