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
    branch_selected_graph_nodes,
    branch_selected_inputs,
    default_graph_node_id,
    load_branch_spec,
    ordered_unique_upper,
)
from abel_invest.narrative_core.contracts.constants import (
    DEFAULT_ABEL_ROUTER_BASE_URL,
    EVIDENCE_LEDGER_FILENAME,
    EXPLORATION_PATH_FILENAME,
    FRONTIER_JSON_FILENAME,
)
from abel_invest.narrative_core.dashboard_adapters.primary_strategy_selector import (
    select_primary_strategy,
)
from abel_invest.workspace_core.edge_runtime import resolve_runtime_auth_env_file
from abel_invest.narrative_core.evidence.evidence import (
    build_evidence_ledger,
    load_json_object,
    parse_changed_dimensions,
)
from abel_invest.narrative_core.evidence.frontier import build_frontier
from abel_invest.narrative_core.io import _now, read_env_file_values, read_tsv_rows
from abel_invest.narrative_core.evidence.exploration_path import (
    build_exploration_path_status,
    extract_exploration_path_refs,
    resolve_exploration_path_reference,
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
        frontier = build_frontier(
            ledger,
            exploration_path_status=build_exploration_path_status(
                session,
                ledger=ledger,
                frontier={},
            ),
        )
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
    path_coverage = frontier.get("path_coverage") if isinstance(frontier.get("path_coverage"), dict) else {}
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
                "pathCoverage": path_coverage,
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


def build_skill_dashboard_session_bundle(session: Path, *, uploaded_at: str | None = None) -> dict:
    session = resolve_workspace_arg_path(session).resolve()
    discovery = load_discovery(session)
    render_session(session)
    frontier = load_json_object(session / FRONTIER_JSON_FILENAME)
    ledger = load_json_object(session / EVIDENCE_LEDGER_FILENAME)
    branches = load_branches(session)
    events = read_tsv_rows(session / "events.tsv")
    start_at = require_timezone_aware_iso(
        _first_session_event_time(events) or _now(),
        field_name="startAt",
    )
    end_at = require_timezone_aware_iso(uploaded_at or _now(), field_name="endAt")
    if datetime.fromisoformat(end_at) <= datetime.fromisoformat(start_at):
        raise RuntimeError("skill dashboard session upload requires endAt after startAt")

    branch_payloads = [
        skill_dashboard_branch_payload(branch, discovery=discovery, ledger=ledger)
        for branch in branches
    ]
    round_order = session_round_order(events)
    rounds = indexed_skill_dashboard_rounds(branches, events, ledger)
    primary_strategy = select_primary_strategy(
        session=session,
        branches=branches,
        session_round_indexes=round_order,
    )
    return {
        "sessionId": session.name,
        "startAt": start_at,
        "endAt": end_at,
        "payload": {
            "session": {
                "id": session.name,
                "ticker": discovery.get("ticker", session.parent.name.upper()),
                "targetNode": dashboard_session_target_node(discovery),
                "status": dashboard_session_status(branch_payloads),
                "frontierRows": frontier.get("row_count", 0),
            },
            "branches": branch_payloads,
            "rounds": rounds,
            "primaryStrategy": primary_strategy,
            "explorationMap": build_skill_dashboard_exploration_map(
                discovery=discovery,
                branches=branch_payloads,
                rounds=rounds,
            ),
            "sessionInsights": skill_dashboard_session_insights(session, ledger, frontier),
            "episodes": skill_dashboard_session_episodes(events),
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


def post_skill_dashboard_session(
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
        f"{normalized_base_url}/web/skill-dashboard/sessions",
        data=body,
        headers={"Content-Type": "application/json", "api-key": normalized_api_key},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Skill dashboard session upload failed: HTTP {exc.code}: {detail}") from exc
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
    base_url = resolve_skill_dashboard_base_url()
    api_key = resolve_skill_dashboard_api_key(args.api_key, workspace_root=workspace_root)
    result = post_skill_dashboard_bundle(base_url=base_url, api_key=api_key, bundle=bundle)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def upload_skill_dashboard_session(args: argparse.Namespace) -> int:
    session = resolve_workspace_arg_path(args.session).resolve()
    bundle = build_skill_dashboard_session_bundle(session)
    if args.output_json:
        output_path = resolve_workspace_arg_path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dry_run:
        print(json.dumps(bundle, indent=2, ensure_ascii=False))
        return 0

    workspace_root = find_workspace_root(session)
    base_url = resolve_skill_dashboard_base_url()
    api_key = resolve_skill_dashboard_api_key(args.api_key, workspace_root=workspace_root)
    result = post_skill_dashboard_session(base_url=base_url, api_key=api_key, bundle=bundle)
    print(render_skill_dashboard_session_upload_result(result))
    return 0


def render_skill_dashboard_session_upload_result(result: dict) -> str:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    session_id = str(data.get("sessionId") or data.get("id") or "session").strip()
    open_url = str(data.get("openUrl") or data.get("url") or "").strip()
    if open_url:
        return f"Online session view: [Open {session_id}]({open_url})"
    return json.dumps(result, indent=2, ensure_ascii=False)


def resolve_skill_dashboard_base_url(value: str | None = None) -> str:
    base_url = (
        str(value or "").strip()
        or os.getenv("ABEL_ROUTER_BASE_URL", "").strip()
        or os.getenv("CAP_ROUTER_BASE_URL", "").strip()
        or DEFAULT_ABEL_ROUTER_BASE_URL
    )
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
    raise RuntimeError("Set --api-key or run abel-auth before creating an online session view")


def skill_dashboard_rounds(branch: Path, rows: list[dict[str, str]], ledger: dict) -> list[dict]:
    ledger_rows = {
        str(row.get("round_id") or ""): row
        for row in (ledger.get("rows") or [])
        if isinstance(row, dict) and row.get("branch_id") == branch.name
    }
    rounds = []
    for index, row in enumerate(rows, start=1):
        round_id = str(row.get("round_id") or "").strip()
        note = read_round_note(branch, round_id)
        evidence = ledger_rows.get(round_id, {})
        rounds.append(
            {
                "branchId": branch.name,
                "roundId": round_id,
                "branchRoundIndex": index,
                "sessionRoundIndex": index,
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
    path = session / EXPLORATION_PATH_FILENAME
    if not path.exists():
        return []
    insights = []
    for index, block in enumerate(exploration_path_entry_blocks(path.read_text(encoding="utf-8")), start=1):
        summary = exploration_path_block_summary(block)
        if not summary:
            continue
        refs = extract_exploration_path_refs("\n".join(block))
        matching_refs = [
            ref
            for ref in refs
            if path_reference_matches_branch(
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
                "id": f"exploration-path-entry-{index}",
                "roundId": first_round_id_from_refs(matching_refs, branch_id=branch_id),
                "kind": "exploration_path",
                "summary": summary,
                "reusableRule": "",
                "confidence": "",
                "origin": "exploration_path",
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


def indexed_skill_dashboard_rounds(
    branches: list[dict],
    events: list[dict[str, str]],
    ledger: dict,
) -> list[dict]:
    order = session_round_order(events)
    rows: list[dict] = []
    for branch in branches:
        branch_dir = branch["branch_dir"]
        ledger_rows = {
            str(row.get("round_id") or ""): row
            for row in (ledger.get("rows") or [])
            if isinstance(row, dict) and row.get("branch_id") == branch_dir.name
        }
        for row in branch["rows"]:
            round_id = str(row.get("round_id") or "").strip()
            evidence = ledger_rows.get(round_id, {})
            rows.append(
                {
                    "branchId": branch_dir.name,
                    "roundId": round_id,
                    "sessionRoundIndex": order.get((branch_dir.name, round_id), len(order) + 1),
                    "mode": row.get("mode", ""),
                    "decision": row.get("decision", ""),
                    "verdict": row.get("verdict", ""),
                    "score": row.get("score", ""),
                    "description": row.get("description", ""),
                    "evidenceLabel": evidence.get("evidence_label", ""),
                }
            )
    return sorted(rows, key=lambda item: int(item.get("sessionRoundIndex") or 0))


def session_round_order(events: list[dict[str, str]]) -> dict[tuple[str, str], int]:
    order: dict[tuple[str, str], int] = {}
    for row in events:
        if row.get("event") != "round_recorded":
            continue
        key = (str(row.get("branch_id") or ""), str(row.get("round_id") or ""))
        if key[0] and key[1] and key not in order:
            order[key] = len(order) + 1
    return order


def skill_dashboard_branch_payload(branch: dict, *, discovery: dict, ledger: dict) -> dict:
    branch_dir = branch["branch_dir"]
    spec = load_branch_spec(branch_dir)
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    return {
        "id": branch_dir.name,
        "targetAsset": dashboard_branch_target_asset(spec, discovery),
        "targetNode": dashboard_branch_target_node(spec, discovery),
        "requestedStart": branch_requested_start(branch_dir, discovery),
        "selectedInputs": branch_selected_inputs(spec),
        "selectedGraphNodes": branch_selected_graph_nodes(spec),
        "sourceType": str(spec.get("input_claim") or "unspecified"),
        "methodFamily": str(spec.get("model_family") or "").strip(),
        "mechanismFamily": str(spec.get("mechanism_family") or "").strip(),
        "complexityClass": str(spec.get("complexity_class") or "").strip(),
        "status": dashboard_route_status(str(latest.get("decision") or "")),
        "thesis": current_branch_hypothesis(branch_dir, rows),
        "latestEvidenceLabel": dashboard_latest_evidence_label(
            ledger,
            branch_id=branch_dir.name,
            round_id=str(latest.get("round_id") or ""),
        ),
    }


def build_skill_dashboard_exploration_map(
    *,
    discovery: dict,
    branches: list[dict],
    rounds: list[dict],
) -> dict:
    target_node = dashboard_session_target_node(discovery)
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def touch_node(node_id: str, *, role: str) -> None:
        node_id = str(node_id or "").strip()
        if not node_id:
            return
        nodes.setdefault(node_id, {"nodeId": node_id, "roles": []})
        if role and role not in nodes[node_id]["roles"]:
            nodes[node_id]["roles"].append(role)

    touch_node(target_node, role="target")
    for branch in branches:
        for node_id in branch.get("selectedGraphNodes") or []:
            touch_node(node_id, role="input")
            if target_node:
                edge_id = f"{node_id}->{target_node}"
                edges.setdefault(
                    edge_id,
                    {
                        "edgeId": edge_id,
                        "sourceNodeId": node_id,
                        "targetNodeId": target_node,
                        "branchIds": [],
                    },
                )
                if branch["id"] not in edges[edge_id]["branchIds"]:
                    edges[edge_id]["branchIds"].append(branch["id"])
    routes = [
        {
            "branchId": branch["id"],
            "targetNodeId": branch.get("targetNode") or target_node,
            "inputNodeIds": branch.get("selectedGraphNodes") or [],
            "status": branch.get("status") or "exploratory",
        }
        for branch in branches
    ]
    return {
        "source": "local_session_evidence",
        "confidence": "high",
        "nodes": sorted(nodes.values(), key=lambda item: item["nodeId"]),
        "edges": sorted(edges.values(), key=lambda item: item["edgeId"]),
        "routes": routes,
        "roundCount": len(rounds),
    }


def dashboard_route_status(decision: str) -> str:
    normalized = str(decision or "").strip().lower()
    if normalized == "keep":
        return "kept"
    if normalized == "discard":
        return "discarded"
    return "exploratory"


def dashboard_session_target_node(discovery: dict) -> str:
    value = str(discovery.get("target_node") or "").strip()
    if value:
        return value
    ticker = str(discovery.get("ticker") or "").strip().upper()
    return default_graph_node_id(ticker) if ticker else ""


def dashboard_session_status(branches: list[dict]) -> str:
    statuses = {str(branch.get("status") or "") for branch in branches}
    if "kept" in statuses:
        return "candidate_found"
    if "discarded" in statuses:
        return "exploring"
    return "initialized"


def skill_dashboard_session_insights(session: Path, ledger: dict, frontier: dict) -> list[dict]:
    del session, ledger, frontier
    return []


def skill_dashboard_session_episodes(rows: list[dict[str, str]]) -> list[dict]:
    return [
        {
            "timestamp": row.get("timestamp", ""),
            "event": row.get("event", ""),
            "branchId": row.get("branch_id", ""),
            "roundId": row.get("round_id", ""),
            "mode": row.get("mode", ""),
            "verdict": row.get("verdict", ""),
            "decision": row.get("decision", ""),
            "summary": row.get("description", ""),
            "artifactPath": row.get("artifact_path", ""),
        }
        for row in rows
    ]


def _first_session_event_time(rows: list[dict[str, str]]) -> str:
    for row in rows:
        if row.get("timestamp"):
            return str(row["timestamp"])
    return ""


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


def path_reference_matches_branch(
    ref: str,
    *,
    branch_id: str,
    session: Path,
    ledger: dict,
    frontier: dict,
) -> bool:
    if not resolve_exploration_path_reference(ref, session=session, ledger=ledger, frontier=frontier):
        return False
    if ref.startswith("ledger:"):
        parts = ref.split(":")
        return len(parts) >= 3 and parts[1].strip() == branch_id
    if ref.startswith("branches/") or ref.startswith("branches\\"):
        normalized = ref.replace("\\", "/")
        return normalized.split("/")[1:2] == [branch_id]
    return False


def exploration_path_entry_blocks(text: str) -> list[list[str]]:
    lines = str(text or "").splitlines()
    entry_start = 0
    for index, line in enumerate(lines):
        if line.strip() == "## Entries":
            entry_start = index + 1
            break
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines[entry_start:]:
        if line.startswith("### ") and current:
            blocks.append(current)
            current = []
        if line.strip() or current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def exploration_path_block_summary(block: list[str]) -> str:
    for prefix in ("- why:", "- path:"):
        for line in block:
            stripped = line.strip()
            if stripped.lower().startswith(prefix):
                return stripped.split(":", 1)[1].strip()
    for line in block:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return ""


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
