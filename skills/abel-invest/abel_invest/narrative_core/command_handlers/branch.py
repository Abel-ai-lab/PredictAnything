"""Branch preparation, execution, and debug command handlers."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from abel_invest.narrative_core.contracts.branch_spec import (
    _get_backtest_start,
    branch_requested_start,
    branch_dependencies_payload,
    branch_selected_inputs,
    branch_selected_graph_nodes,
    build_context_guide_markdown,
    build_data_manifest_payload,
    build_execution_constraints_payload,
    build_probe_samples_payload,
    build_runtime_profile_payload,
    has_explicit_hypothesis,
    load_branch_spec,
)
from abel_invest.workspace_core.edge_runtime import (
    build_workspace_runtime_env,
)
from abel_invest.narrative_core.runtime.edge_commands import (
    resolve_default_python_bin,
)
from abel_invest.narrative_core.runtime.dsr_accounting import (
    append_dsr_accounting_record,
    build_dsr_accounting_facts,
)
from abel_invest.workspace_core.workspace import (
    find_workspace_root,
    resolve_workspace_env_file,
)
from abel_invest.narrative_core.runtime.workflow_blockers import (
    record_workflow_blocker_round,
)
from abel_invest.narrative_core.contracts.constants import (
    BRANCH_SPEC_FILENAME,
    EVENTS_HEADER,
    EXPLORATION_PATH_FILENAME,
    EXECUTION_CONSTRAINTS_FILENAME,
    PROBE_SAMPLES_FILENAME,
    RESULTS_HEADER,
)
from abel_invest.narrative_core.runtime.context import (
    alpha_decision,
    branch_context_summary_lines,
    branch_runtime_advisory_lines,
    build_branch_context,
    classify_result_frame,
)
from abel_invest.narrative_core.evidence.exploration_path import append_exploration_path_round
from abel_invest.narrative_core.io import (
    SessionLock,
    _now,
    append_tsv_row,
    read_tsv_rows,
)
from abel_invest.narrative_core.contracts.paths import (
    context_guide_path,
    data_manifest_path,
    dependencies_path,
    execution_constraints_path,
    probe_samples_path,
    runtime_profile_path,
)
from abel_invest.narrative_core.readiness import (
    build_readiness_warning,
    readiness_coverage_hint_lines,
)
from abel_invest.narrative_core.rendering.renderers import (
    render_round_note,
)
from abel_invest.narrative_core.session_lifecycle import (
    command_prefix_for_path,
    resolve_workspace_arg_path,
)
from abel_invest.narrative_core.rendering.session_rendering import (
    path_coverage_missing_rounds,
    path_coverage_warning_lines,
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
    resolve_branch_hypothesis,
    should_emit_missing_hypothesis_warning,
    should_emit_readiness_warning,
)


SELECTION_TRIALS_AUDIT_WARNING = (
    "Selection-trials audit: --selection-trials records accidental or explicitly requested "
    "search width for DSR accounting; it does not by itself validate raw sweep winners. "
    "Record the branch basis and any disposable probe, scout, or optimization influence "
    f"in {EXPLORATION_PATH_FILENAME} before continuing."
)


def selection_trials_audit_warning(selection_trials: int) -> str | None:
    if selection_trials <= 1:
        return None
    return SELECTION_TRIALS_AUDIT_WARNING


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
    selected_graph_nodes = branch_selected_graph_nodes(branch_spec)
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
            command_prefix = command_prefix_for_path(branch)
            raise RuntimeError(
                "Branch preparation is blocked on Abel auth. "
                "Use abel-auth, then rerun "
                f"`{command_prefix} prepare-branch --branch {branch}`."
            )
        raise RuntimeError(
            "Abel-edge warm-cache did not produce dependencies output. "
            "Fix the runtime error above before continuing."
        )
    cache_payload = json.loads(output_path.read_text(encoding="utf-8"))
    dependencies["cache"] = cache_payload
    output_path.write_text(json.dumps(dependencies, indent=2), encoding="utf-8")
    runtime_profile = build_runtime_profile_payload(target=target, branch_spec=branch_spec)
    execution_constraints = build_execution_constraints_payload(branch_spec)
    data_manifest = build_data_manifest_payload(
        target=target,
        selected_inputs=selected_inputs,
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
    command_prefix = command_prefix_for_path(branch)
    if auth_handoff_needed:
        print("  Use abel-auth")
        print(f"  {command_prefix} prepare-branch --branch {branch}")
    elif warm_fail:
        print("  Fix cache failures before debug/run; unresolved prepared inputs should not become evidence.")
        print(f"  inspect {output_path.relative_to(session)}")
        print(f"  revise {branch / BRANCH_SPEC_FILENAME} or auth/data access if needed")
        print(f"  {command_prefix} prepare-branch --branch {branch}")
        return completed.returncode or 1
    else:
        print("  The branch inputs are ready; use debug preflight first, then record a round once the engine reflects the candidate.")
        print(f"  {command_prefix} debug-branch --branch {branch}")
        print(f"  {command_prefix} run-branch --branch {branch} -d \"baseline\"")
    return completed.returncode


def run_branch_round(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    workspace_root = find_workspace_root(branch)
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    with SessionLock(session):
        render_session(session)
    blocking_missing_path = path_coverage_missing_rounds(session)
    if blocking_missing_path:
        print(
            "Exploration path entry required before next recorded round: "
            f"missing_path_rounds={', '.join(blocking_missing_path)}. "
            f"Update {EXPLORATION_PATH_FILENAME} with ledger refs, chosen path, compact reason, Edge feedback, and artifact refs for each missing round.",
            file=sys.stderr,
        )
        return 2
    if not branch_inputs_ready(branch):
        command_prefix = command_prefix_for_path(branch)
        print(
            "Branch inputs have not been prepared yet. "
            f"Run `{command_prefix} prepare-branch --branch ...` before recording a round.",
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
    frame_path = branch / "outputs" / f"{round_id}-edge-frame.csv"
    handoff_path = branch / "outputs" / f"{round_id}-edge-handoff.json"
    context_path = branch / "outputs" / f"{round_id}-alpha-context.json"
    selection_trials = getattr(args, "selection_trials", 1)
    context = build_branch_context(
        branch=branch,
        session=session,
        discovery=discovery,
        readiness=readiness,
        round_id=round_id,
        backtest_start=backtest_start,
        selection_trials=selection_trials,
    )
    context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
    selection_warning = selection_trials_audit_warning(selection_trials)
    if selection_warning:
        print(selection_warning, file=sys.stderr)
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
        "--output-csv",
        str(frame_path),
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
    dsr_accounting = build_dsr_accounting_facts(
        session=session,
        branch_id=branch.name,
        round_id=round_id,
        run_type="round",
        context_path=context_path,
        result_path=result_path,
        context=context,
        result=result,
    )
    with SessionLock(session):
        append_dsr_accounting_record(session, dsr_accounting)
    emit_missing_hypothesis_warning = False
    if not has_explicit_hypothesis(effective_hypothesis):
        with SessionLock(session):
            emit_missing_hypothesis_warning = should_emit_missing_hypothesis_warning(branch)
    if emit_missing_hypothesis_warning:
        print(
            "Audit note: recording a round without explicit candidate metadata. "
            "Before the next round, make objective, selected inputs, search width, and validation scope clear; "
            "add graph attribution only when claiming graph-derived contribution.",
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
            dsr_accounting=dsr_accounting,
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
        append_exploration_path_round(
            session=session,
            branch=branch,
            round_id=round_id,
            mode=args.mode,
            decision=decision,
            description=args.description,
            result=result,
            result_path=result_path,
            report_path=report_path,
            hypothesis=effective_hypothesis,
            change_summary=args.change_summary,
            next_step=args.next_step,
            changed_dimensions=getattr(args, "changed_dimension", []),
        )
        render_session(session)
    for line in path_coverage_warning_lines(session):
        print(f"Exploration path required: {line}")
    print(f"Alpha context: {context_path.relative_to(session)}")
    print(f"Edge result: {result_path.relative_to(session)}")
    print(f"Edge validation: {report_path.relative_to(session)}")
    print(f"Edge handoff: {handoff_path.relative_to(session)}")
    if frame_path.exists():
        print(f"Edge frame: {frame_path.relative_to(session)}")
    print(f"Exploration path: {session / EXPLORATION_PATH_FILENAME}")
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
    print("")
    print("From here:")
    print(
        f"  update {session / EXPLORATION_PATH_FILENAME} with ledger:{branch.name}:{round_id} "
        "before another recorded round"
    )
    print(f"  read {session / EXPLORATION_PATH_FILENAME} and frontier.md before choosing continue/pivot/stop")
    print(f"  if continuing this branch, run abel-invest debug-branch --branch {branch} before the next recorded round")
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
    context = build_branch_context(
        branch=branch,
        session=session,
        discovery=discovery,
        readiness=readiness,
        round_id="debug",
        backtest_start=backtest_start,
    )
    context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
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
    debug_result: dict[str, object] = {}
    if debug_result_path.exists():
        try:
            parsed_debug_result = json.loads(debug_result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed_debug_result = {}
        if isinstance(parsed_debug_result, dict):
            debug_result = parsed_debug_result
    debug_snapshot = build_debug_snapshot(
        completed=completed,
        session=session,
        context_path=context_path,
        debug_result_path=debug_result_path,
        backtest_start=backtest_start,
    )
    dsr_accounting = build_dsr_accounting_facts(
        session=session,
        branch_id=branch.name,
        round_id="debug",
        run_type="debug",
        context_path=context_path,
        result_path=debug_result_path,
        context=context,
        result=debug_result,
    )
    with SessionLock(session):
        persist_debug_snapshot(branch, debug_snapshot)
        if debug_result_path.exists():
            append_dsr_accounting_record(session, dsr_accounting)
        render_session(session)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    for line in advisory_lines:
        print(f"Runtime context: {line}")
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
    print("")
    print("From here:")
    if completed.returncode:
        print("  inspect the debug output and fix the engine or prepared inputs before recording a round")
        print(f"  abel-invest debug-branch --branch {branch}")
    else:
        print("  confirm branch.yaml has objective, selected inputs, search width when applicable, and validation scope")
        print(f"  abel-invest run-branch --branch {branch} -d \"<round-description>\"")
    return completed.returncode
