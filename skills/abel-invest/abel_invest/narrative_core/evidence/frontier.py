"""Evidence frontier aggregation and markdown rendering."""

from __future__ import annotations

from abel_invest.narrative_core.contracts.branch_spec import ordered_unique_upper
from abel_invest.narrative_core.contracts.constants import (
    GRAPH_PRIORITY_ROUND_MINIMUM,
    INPUT_BREADTH_ROUND_THRESHOLD,
)
from abel_invest.narrative_core.io import _now
from abel_invest.narrative_core.evidence.journal import build_journal_coverage, compact_research_journal_status


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
