"""Skill dashboard bundle and upload helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
import uuid
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
from abel_invest.narrative_core.strategy_artifacts import export_selected_strategy_artifact
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
    rounds = indexed_skill_dashboard_rounds(branches, events, ledger)
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


def post_strategy_artifact_upload(
    *,
    base_url: str,
    api_key: str,
    hosted_session_id: str,
    manifest: dict,
    artifact_path: Path,
    source_upload_id: str = "",
    client_request_id: str = "",
    opener=urlopen,
    timeout: int = 60,
) -> dict:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise RuntimeError("Missing Abel router base URL")
    normalized_api_key = str(api_key or "").strip()
    if not normalized_api_key:
        raise RuntimeError("Missing Abel API key")
    session_id = str(hosted_session_id or "").strip()
    if not session_id:
        raise RuntimeError("Missing hosted session id for strategy artifact upload")
    artifact_path = Path(artifact_path)
    if not artifact_path.is_file():
        raise RuntimeError(f"Strategy artifact zip not found: {artifact_path}")

    fields = {
        "manifest": json.dumps(manifest, indent=2, sort_keys=True),
    }
    if source_upload_id:
        fields["sourceUploadId"] = source_upload_id
    if client_request_id:
        fields["clientRequestId"] = client_request_id
    body, content_type = build_multipart_form_data(
        fields=fields,
        files={
            "artifact": {
                "filename": artifact_path.name,
                "content_type": "application/zip",
                "content": artifact_path.read_bytes(),
            }
        },
    )
    request = Request(
        f"{normalized_base_url}/web/skill-dashboard/sessions/{session_id}/strategy-artifacts",
        data=body,
        headers={"Content-Type": content_type, "api-key": normalized_api_key},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Strategy artifact upload failed: HTTP {exc.code}: {detail}") from exc
    return json.loads(raw)


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
    artifact_export_result = None
    if getattr(args, "with_strategy_artifact", False):
        artifact_export_result = export_selected_strategy_artifact(
            session,
            output_dir=Path(args.artifact_output_dir)
            if getattr(args, "artifact_output_dir", None)
            else None,
            python_bin=getattr(args, "python_bin", None),
            runner=subprocess.run,
        )
        skipped = artifact_export_result.get("artifactUploadSkipped")
        skip_reason = artifact_export_result.get("skipReason")
        if skipped and skip_reason != "no_pass_strategy":
            raise RuntimeError(_strategy_artifact_preupload_error(artifact_export_result))
    result = post_skill_dashboard_session(
        base_url=base_url,
        api_key=api_key,
        bundle=bundle,
    )
    artifact_result = None
    if artifact_export_result is not None:
        artifact_result = upload_prepared_strategy_artifact_for_session(
            local_session=session,
            narrative_result=result,
            base_url=base_url,
            api_key=api_key,
            export_result=artifact_export_result,
        )
    print(render_skill_dashboard_session_upload_result(result, artifact_result=artifact_result))
    return 0


def upload_strategy_artifact_for_session(
    *,
    local_session: Path,
    narrative_result: dict,
    base_url: str,
    api_key: str,
    output_dir: Path | None = None,
    python_bin: str | None = None,
    opener=urlopen,
    runner=None,
) -> dict:
    data = narrative_result.get("data") if isinstance(narrative_result.get("data"), dict) else {}
    hosted_session_id = str(data.get("sessionId") or data.get("id") or "").strip()
    if not hosted_session_id:
        return {
            "artifactExported": False,
            "artifactUploadSkipped": True,
            "skipReason": "hosted_session_id_missing",
        }
    export_result = export_selected_strategy_artifact(
        local_session,
        output_dir=output_dir,
        python_bin=python_bin,
        runner=runner or subprocess.run,
    )
    return upload_prepared_strategy_artifact_for_session(
        local_session=local_session,
        narrative_result=narrative_result,
        base_url=base_url,
        api_key=api_key,
        export_result=export_result,
        opener=opener,
    )


def _strategy_artifact_preupload_error(export_result: dict) -> str:
    skip_reason = str(export_result.get("skipReason") or "unknown").strip()
    promotion_report = (
        export_result.get("promotionReport")
        if isinstance(export_result.get("promotionReport"), dict)
        else {}
    )
    reason = str(promotion_report.get("reason") or "").strip()
    request_path = str(promotion_report.get("requestPath") or "").strip()
    message = (
        "Strategy artifact publish requires skill-level agent refactor before "
        f"upload: {skip_reason}"
    )
    if reason:
        message += f"; reason={reason}"
    if request_path:
        message += f"; requestPath={request_path}"
    return message


def upload_prepared_strategy_artifact_for_session(
    *,
    local_session: Path,
    narrative_result: dict,
    base_url: str,
    api_key: str,
    export_result: dict,
    opener=urlopen,
) -> dict:
    data = narrative_result.get("data") if isinstance(narrative_result.get("data"), dict) else {}
    hosted_session_id = str(data.get("sessionId") or data.get("id") or "").strip()
    source_upload_id = str(data.get("uploadId") or data.get("sourceUploadId") or "").strip()
    if not hosted_session_id:
        return {
            **export_result,
            "artifactExported": False,
            "artifactUploadSkipped": True,
            "skipReason": "hosted_session_id_missing",
        }
    if export_result.get("artifactUploadSkipped"):
        return export_result
    try:
        manifest_path = Path(str(export_result.get("manifestPath") or ""))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        upload_result = post_strategy_artifact_upload(
            base_url=base_url,
            api_key=api_key,
            hosted_session_id=hosted_session_id,
            manifest=manifest,
            artifact_path=Path(str(export_result.get("artifactPath") or "")),
            source_upload_id=source_upload_id,
            client_request_id=strategy_artifact_client_request_id(manifest),
            opener=opener,
        )
    except Exception as exc:
        return {
            **export_result,
            "artifactUploadFailed": True,
            "artifactUploadError": str(exc),
        }
    upload_data = (
        upload_result.get("data")
        if isinstance(upload_result.get("data"), dict)
        else upload_result
    )
    return {
        **export_result,
        "artifactUploadFailed": False,
        "artifactUploadResponse": upload_result,
        "artifactUploadId": upload_data.get("artifactUploadId", ""),
        "status": upload_data.get("status", ""),
        "admissionStatus": upload_data.get("admissionStatus", ""),
        "strategyId": upload_data.get("strategyId"),
        "openUrl": upload_data.get("openUrl", ""),
    }


def render_skill_dashboard_session_upload_result(
    result: dict,
    *,
    artifact_result: dict | None = None,
) -> str:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    session_id = str(data.get("sessionId") or data.get("id") or "session").strip()
    open_url = str(data.get("openUrl") or data.get("url") or "").strip()
    artifact_lines = render_strategy_artifact_upload_lines(artifact_result)
    if open_url:
        line = f"Online session view: [Open {session_id}]({open_url})"
        return "\n".join([line] + artifact_lines) if artifact_lines else line
    if artifact_lines:
        return (
            json.dumps(result, indent=2, ensure_ascii=False)
            + "\n"
            + "\n".join(artifact_lines)
        )
    return json.dumps(result, indent=2, ensure_ascii=False)


def render_strategy_artifact_upload_lines(artifact_result: dict | None) -> list[str]:
    if not artifact_result:
        return []
    if artifact_result.get("artifactUploadSkipped"):
        return [f"Strategy artifact skipped: {artifact_result.get('skipReason', 'unknown')}"]
    if artifact_result.get("artifactUploadFailed"):
        return [f"Strategy artifact upload failed: {artifact_result.get('artifactUploadError', '')}"]
    upload_id = str(artifact_result.get("artifactUploadId") or "").strip()
    admission = str(artifact_result.get("admissionStatus") or "").strip()
    branch_id = str(artifact_result.get("selectedBranchId") or "").strip()
    round_id = str(artifact_result.get("selectedRoundId") or "").strip()
    summary = "Strategy artifact uploaded"
    if upload_id:
        summary += f": {upload_id}"
    details = []
    if admission:
        admission_detail = f"admission={admission}"
        if admission == "queued":
            admission_detail += "; router admission continues asynchronously"
        details.append(admission_detail)
    if branch_id and round_id:
        details.append(f"selected={branch_id}/{round_id}")
    if details:
        summary += f" ({', '.join(details)})"
    return [summary]


def strategy_artifact_client_request_id(manifest: dict) -> str:
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    parts = [
        str(source.get("sourceSessionId") or "").strip(),
        str(source.get("branchId") or "").strip(),
        str(source.get("roundId") or "").strip(),
        hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()[
            :16
        ],
    ]
    return ":".join(part or "unknown" for part in parts)


def build_multipart_form_data(
    *,
    fields: dict[str, str],
    files: dict[str, dict[str, object]],
) -> tuple[bytes, str]:
    boundary = f"----abel-invest-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n'.encode("utf-8"),
                b"Content-Type: text/plain; charset=utf-8\r\n\r\n",
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, file_info in files.items():
        filename = str(file_info.get("filename") or name)
        content_type = str(file_info.get("content_type") or "application/octet-stream")
        content = file_info.get("content") or b""
        if isinstance(content, str):
            content = content.encode("utf-8")
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                bytes(content),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


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
        branch_hypothesis = current_branch_hypothesis(branch_dir, branch["rows"])
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
                    "hypothesis": branch_hypothesis,
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
