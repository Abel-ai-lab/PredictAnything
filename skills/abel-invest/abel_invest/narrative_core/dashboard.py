"""Skill dashboard bundle and upload helpers."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from abel_invest.narrative_core.contracts.branch_spec import (
    branch_requested_start,
    branch_selected_inputs,
    load_branch_spec,
    ordered_unique_upper,
)
from abel_invest.narrative_core.contracts.constants import (
    EVIDENCE_LEDGER_FILENAME,
    FRONTIER_JSON_FILENAME,
    RESEARCH_JOURNAL_FILENAME,
)
from abel_invest.workspace_core.edge_runtime import resolve_runtime_auth_env_file
from abel_invest.narrative_core.evidence.evidence import (
    build_evidence_ledger,
    load_json_object,
    parse_changed_dimensions,
)
from abel_invest.narrative_core.evidence.frontier import build_frontier
from abel_invest.narrative_core.io import _now, read_env_file_values, read_tsv_rows
from abel_invest.narrative_core.evidence.journal import (
    build_research_journal_status,
    extract_journal_evidence_refs,
    journal_note_line_items,
    resolve_journal_reference,
)
from abel_invest.narrative_core.session_lifecycle import resolve_workspace_arg_path
from abel_invest.narrative_core.rendering.session_rendering import render_session
from abel_invest.narrative_core.state import (
    current_branch_hypothesis,
    load_branch_state,
    load_branches,
    load_discovery,
    read_round_note,
)
from abel_invest.workspace_core.workspace import find_workspace_root


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
