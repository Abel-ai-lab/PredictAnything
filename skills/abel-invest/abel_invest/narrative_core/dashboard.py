"""Skill dashboard bundle and upload helpers."""

from __future__ import annotations

import argparse
import json
import os
import uuid
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
)
from abel_invest.narrative_core.contracts.constants import (
    DEFAULT_ABEL_ROUTER_BASE_URL,
    EVIDENCE_LEDGER_FILENAME,
    FRONTIER_JSON_FILENAME,
)
from abel_invest.narrative_core.dashboard_adapters.primary_strategy_selector import (
    select_primary_strategy,
)
from abel_invest.workspace_core.edge_runtime import resolve_runtime_auth_env_file
from abel_invest.narrative_core.evidence.evidence import (
    load_json_object,
)
from abel_invest.narrative_core.io import _now, read_env_file_values, read_tsv_rows
from abel_invest.narrative_core.session_lifecycle import resolve_workspace_arg_path
from abel_invest.narrative_core.rendering.session_rendering import render_session
from abel_invest.narrative_core.state import (
    current_branch_hypothesis,
    load_branches,
    load_discovery,
)
from abel_invest.workspace_core.workspace import find_workspace_root


def build_skill_dashboard_session_bundle(
    session: Path,
    *,
    uploaded_at: str | None = None,
    locale: str | None = None,
) -> dict:
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
        "locale": _normalize_dashboard_locale(locale),
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


def post_skill_dashboard_session(
    *,
    base_url: str,
    api_key: str,
    bundle: dict,
    session_root: Path | None = None,
    opener=urlopen,
    timeout: int = 60,
) -> dict:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise RuntimeError("Missing Abel router base URL")
    normalized_api_key = str(api_key or "").strip()
    if not normalized_api_key:
        raise RuntimeError("Missing Abel API key")
    trade_log_path = _primary_strategy_trade_log_path(bundle, session_root=session_root)
    if trade_log_path is not None and trade_log_path.is_file():
        body, content_type = build_multipart_form_data(
            fields={"payload": json.dumps(bundle, ensure_ascii=False)},
            files={
                "backtestTradeLog": {
                    "filename": trade_log_path.name,
                    "content_type": "text/csv",
                    "content": trade_log_path.read_bytes(),
                }
            },
        )
    else:
        body = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
        content_type = "application/json"
    request = Request(
        f"{normalized_base_url}/web/skill-dashboard/sessions",
        data=body,
        headers={"Content-Type": content_type, "api-key": normalized_api_key},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Skill dashboard session upload failed: HTTP {exc.code}: {detail}") from exc
    return json.loads(raw)


def _primary_strategy_trade_log_path(bundle: dict, *, session_root: Path | None = None) -> Path | None:
    payload = bundle.get("payload") if isinstance(bundle.get("payload"), dict) else {}
    primary_strategy = (
        payload.get("primaryStrategy") if isinstance(payload.get("primaryStrategy"), dict) else {}
    )
    trade_log = (
        primary_strategy.get("backtestTradeLog")
        if isinstance(primary_strategy.get("backtestTradeLog"), dict)
        else {}
    )
    trade_log_ref = str(trade_log.get("tradeLogRef") or "").strip()
    if not trade_log_ref:
        return None
    root = session_root.resolve() if session_root is not None else Path.cwd()
    return root / trade_log_ref


def build_multipart_form_data(*, fields: dict[str, str], files: dict[str, dict]) -> tuple[bytes, str]:
    boundary = f"----abel-skill-dashboard-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, file_info in files.items():
        filename = Path(str(file_info.get("filename") or name)).name
        content_type = str(file_info.get("content_type") or "application/octet-stream")
        content = file_info.get("content") or b""
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def upload_skill_dashboard_session(args: argparse.Namespace) -> int:
    session = resolve_workspace_arg_path(args.session).resolve()
    bundle = build_skill_dashboard_session_bundle(session, locale=getattr(args, "locale", None))
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
    result = post_skill_dashboard_session(
        base_url=base_url,
        api_key=api_key,
        bundle=bundle,
        session_root=session,
    )
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


def _normalize_dashboard_locale(value: str | None) -> str | None:
    locale = str(value or "").strip()
    if not locale:
        return None
    normalized = locale.replace("_", "-").lower()
    if normalized == "en":
        return "en-US"
    if normalized == "zh":
        return "zh-CN"
    if normalized == "zh-cn":
        return "zh-CN"
    if normalized == "en-us":
        return "en-US"
    return locale


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


def dashboard_latest_evidence_label(ledger: dict, *, branch_id: str, round_id: str) -> str:
    for row in ledger.get("rows") or []:
        if (
            isinstance(row, dict)
            and row.get("branch_id") == branch_id
            and row.get("round_id") == round_id
        ):
            return str(row.get("evidence_label") or "")
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


def require_timezone_aware_iso(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"{field_name} must include timezone")
    return parsed.isoformat()
