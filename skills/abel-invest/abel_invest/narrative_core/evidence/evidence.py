"""Evidence classification helpers for strategy discovery."""

from __future__ import annotations

import json
from pathlib import Path

from abel_invest.narrative_core.contracts.branch_spec import (
    branch_declaration_status,
    load_branch_spec,
    ordered_unique_strings,
    ordered_unique_upper,
)
from abel_invest.narrative_core.contracts.constants import (
    BROAD_CHANGED_DIMENSIONS,
    CHANGED_DIMENSIONS,
    EVIDENCE_LEDGER_FILENAME,
    LOCAL_CHANGED_DIMENSIONS,
)
from abel_invest.narrative_core.evidence.frontier import (
    branch_family_key,
    discovered_driver_tickers,
    exploration_neighborhood_key,
)
from abel_invest.narrative_core.io import _now, write_json_file
from abel_invest.narrative_core.state import (
    context_experiment_metadata,
    latest_debug_snapshot,
    read_round_note,
    session_experiment_metadata,
)


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


def load_json_object(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}
