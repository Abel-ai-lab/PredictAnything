"""Dashboard upload CLI glue and compatibility exports."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from abel_invest.narrative_core.contracts.constants import DEFAULT_ABEL_ROUTER_BASE_URL
from abel_invest.narrative_core.dashboard_payload import (
    _first_branch_event_time,
    _first_session_event_time,
    _normalize_dashboard_locale,
    build_skill_dashboard_bundle,
    build_skill_dashboard_exploration_map,
    build_skill_dashboard_session_bundle,
    dashboard_branch_target_asset,
    dashboard_branch_target_node,
    dashboard_latest_evidence_label,
    dashboard_route_status,
    dashboard_round_is_candidate,
    dashboard_session_status,
    dashboard_session_target_node,
    exploration_path_block_summary,
    exploration_path_entry_blocks,
    first_round_id_from_refs,
    indexed_skill_dashboard_rounds,
    path_reference_matches_branch,
    require_timezone_aware_iso,
    resolve_dashboard_session_path,
    session_round_order,
    skill_dashboard_branch_insights,
    skill_dashboard_branch_payload,
    skill_dashboard_episodes,
    skill_dashboard_rounds,
    skill_dashboard_session_episodes,
    skill_dashboard_session_insights,
)
from abel_invest.narrative_core.io import read_env_file_values
from abel_invest.narrative_core.session_lifecycle import resolve_workspace_arg_path
from abel_invest.narrative_core.strategy_artifact_upload import (
    _strategy_artifact_preupload_error,
    post_strategy_artifact_upload,
    render_strategy_artifact_upload_lines,
    strategy_artifact_client_request_id,
    upload_prepared_strategy_artifact_for_session,
    upload_strategy_artifact_for_session,
)
from abel_invest.narrative_core.strategy_artifacts import export_selected_strategy_artifact
from abel_invest.workspace_core.edge_runtime import resolve_runtime_auth_env_file
from abel_invest.workspace_core.workspace import find_workspace_root


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
    del session_root
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


def upload_skill_dashboard_session(args: argparse.Namespace) -> int:
    session = resolve_dashboard_session_path(resolve_workspace_arg_path(args.session).resolve())
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
    artifact_export_result = export_selected_strategy_artifact(
        session,
        output_dir=Path(args.artifact_output_dir)
        if getattr(args, "artifact_output_dir", None)
        else None,
        python_bin=getattr(args, "python_bin", None),
    )
    skipped = artifact_export_result.get("artifactUploadSkipped")
    skip_reason = artifact_export_result.get("skipReason")
    if skipped and skip_reason == "hosted_paper_contract_required":
        raise RuntimeError(_strategy_artifact_preupload_error(artifact_export_result))
    result = post_skill_dashboard_session(
        base_url=base_url,
        api_key=api_key,
        bundle=bundle,
        session_root=session,
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
