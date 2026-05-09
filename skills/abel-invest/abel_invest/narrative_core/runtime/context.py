"""Branch runtime context and decision helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from abel_invest.narrative_core.contracts.branch_spec import (
    _get_backtest_start,
    branch_declaration_status,
    branch_selected_inputs,
    branch_selected_graph_nodes,
    build_data_manifest_payload,
    build_execution_constraints_payload,
    build_runtime_profile_payload,
    canonicalize_data_manifest_payload,
    canonicalize_dependencies_payload,
    load_branch_spec,
)
from abel_invest.narrative_core.contracts.constants import READINESS_FILENAME
from abel_invest.narrative_core.runtime.edge_commands import validate_edge_handoff_with_runtime
from abel_invest.narrative_core.contracts.paths import (
    branch_spec_path,
    context_guide_path,
    data_manifest_path,
    dependencies_path,
    execution_constraints_path,
    probe_samples_path,
    runtime_profile_path,
)
from abel_invest.narrative_core.io import read_tsv_rows
from abel_invest.narrative_core.state import (
    branch_inputs_ready,
    branch_uses_default_scaffold,
    current_experiment_metadata,
)
from abel_invest.workspace_core.workspace import (
    find_workspace_root,
    load_workspace_manifest,
    resolve_runtime_python,
)


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
    return branch_selected_inputs(branch_spec)


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


def build_validation_context(
    *,
    session: Path,
    branch: Path,
    round_id: str,
    selection_trials: int = 1,
) -> dict:
    return {
        "dsr_trials": build_dsr_trials_context(
            session=session,
            branch=branch,
            round_id=round_id,
            selection_trials=selection_trials,
        )
    }


def build_dsr_trials_context(
    *,
    session: Path,
    branch: Path,
    round_id: str,
    selection_trials: int = 1,
) -> dict:
    branches_root = session / "branches"
    raw_recorded_rounds = 0
    prior_validation_rounds = 0
    prior_effective_trials = 0
    historical_context_fallback_rounds = 0
    validation_branch_ids: set[str] = set()
    branch_family_keys: set[str] = {_branch_family_key(branch)}
    current_round_trials = _positive_trial_count(selection_trials) or 1

    if branches_root.is_dir():
        for branch_dir in branches_root.iterdir():
            if not branch_dir.is_dir():
                continue
            rows = read_tsv_rows(branch_dir / "results.tsv")
            if not rows:
                continue
            raw_recorded_rounds += len(rows)
            completed_rows = [
                row
                for row in rows
                if str(row.get("verdict") or "").upper() in {"PASS", "FAIL"}
            ]
            if completed_rows:
                prior_validation_rounds += len(completed_rows)
                validation_branch_ids.add(branch_dir.name)
                branch_family_keys.add(_branch_family_key(branch_dir))
                for row in completed_rows:
                    row_trials, used_fallback = _historical_round_effective_trials(
                        branch_dir,
                        row,
                    )
                    prior_effective_trials += row_trials
                    if used_fallback:
                        historical_context_fallback_rounds += 1

    return {
        "count": max(prior_effective_trials + current_round_trials, 1),
        "source": "abel-invest.session/v1",
        "method": "session_effective_exploration_trials_v1",
        "scope": "ticker_session_requested_window",
        "components": {
            "prior_validation_rounds": prior_validation_rounds,
            "prior_effective_trials": prior_effective_trials,
            "current_round_trials": current_round_trials,
            "raw_recorded_rounds": raw_recorded_rounds,
            "validation_branch_count": len(validation_branch_ids),
            "unique_branch_families": len(branch_family_keys),
            "historical_context_fallback_rounds": historical_context_fallback_rounds,
        },
        "current_branch_id": branch.name,
        "current_round_id": round_id,
    }


def _historical_round_effective_trials(branch_dir: Path, row: dict[str, str]) -> tuple[int, bool]:
    round_id = str(row.get("round_id") or "").strip()
    if not round_id:
        return 1, True
    context = _read_json_object(branch_dir / "outputs" / f"{round_id}-alpha-context.json")
    validation_context = context.get("validation_context")
    if not isinstance(validation_context, dict):
        return 1, True
    dsr_trials = validation_context.get("dsr_trials")
    if not isinstance(dsr_trials, dict):
        return 1, True
    components = dsr_trials.get("components")
    if not isinstance(components, dict):
        return 1, True
    count = _positive_trial_count(components.get("current_round_trials"))
    return (count, False) if count is not None else (1, True)


def _positive_trial_count(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed >= 1 else None
    return None


def _read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _branch_family_key(branch: Path) -> str:
    declaration = branch_declaration_status(load_branch_spec(branch))
    selected_inputs = declaration.get("selected_inputs") or []
    if selected_inputs:
        driver_set = ",".join(str(item).upper() for item in selected_inputs)
    elif declaration.get("input_claim") == "target_only":
        driver_set = "target_only"
    else:
        driver_set = "none"
    return "|".join(
        [
            str(declaration.get("mechanism_family") or "unknown"),
            str(declaration.get("input_claim") or "unknown"),
            driver_set,
            str(declaration.get("model_family") or "unspecified"),
            str(declaration.get("complexity_class") or "unspecified"),
            str(declaration.get("exploration_role") or "unspecified"),
        ]
    )


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
        from abel_edge.validation.gate_logic import decide_keep_discard
        from abel_edge.validation.metrics import load_profile

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
        "from abel_edge.validation.gate_logic import decide_keep_discard\n"
        "from abel_edge.validation.metrics import load_profile\n"
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
    selection_trials: int = 1,
) -> dict:
    """Build the structured context passed into abel-edge evaluate."""
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
        selected_graph_nodes=branch_selected_graph_nodes(branch_spec),
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
        "validation_context": build_validation_context(
            session=session,
            branch=branch,
            round_id=round_id,
            selection_trials=selection_trials,
        ),
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
        from abel_edge.research.handoff import (
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
