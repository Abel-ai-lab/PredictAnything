"""Strategy artifact upload helpers for Abel Invest dashboard publishing."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from abel_invest.narrative_core.strategy_artifacts import export_selected_strategy_artifact
from abel_invest.narrative_core.upload_transport import build_multipart_form_data


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
        "Strategy artifact publish requires a hosted paper contract before "
        f"upload: {skip_reason}"
    )
    if reason:
        message += f"; reason={reason}"
    if request_path:
        message += f"; requestPath={request_path}"
    request_details = _contract_request_error_details(request_path)
    if request_details:
        message += "; " + "; ".join(request_details)
    return message


def _contract_request_error_details(request_path: str) -> list[str]:
    if not request_path:
        return []
    path = Path(request_path)
    if not path.is_file():
        return []
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(request, dict):
        return []
    requirements = (
        request.get("requirements")
        if isinstance(request.get("requirements"), dict)
        else {}
    )
    validation = (
        request.get("validation")
        if isinstance(request.get("validation"), dict)
        else {}
    )
    attempt_policy = (
        validation.get("attemptPolicy")
        if isinstance(validation.get("attemptPolicy"), dict)
        else {}
    )
    details: list[str] = []
    expected_action = _contract_request_scalar(requirements.get("expectedAction"))
    if expected_action:
        details.append(f"expectedAction={expected_action}")
    continuation_method = _contract_request_scalar(
        requirements.get("continuationMethod")
    )
    if continuation_method:
        details.append(f"continuationMethod={continuation_method}")
    policy_details = _attempt_policy_error_details(attempt_policy)
    if policy_details:
        details.append(f"attemptPolicy({', '.join(policy_details)})")
    gate_details = _last_gate_failure_error_details(validation.get("lastGateFailure"))
    if gate_details:
        details.append(gate_details)
    details.append(
        "nextAction=write_or_repair_paper_contract_report_and_rerun_same_command"
    )
    return details


def _attempt_policy_error_details(attempt_policy: dict) -> list[str]:
    details: list[str] = []
    for key in (
        "contractRequestRefreshes",
        "liveContractFailures",
        "fullReplayFallbackEligible",
    ):
        value = _contract_request_scalar(attempt_policy.get(key))
        if value:
            details.append(f"{key}={value}")
    return details


def _last_gate_failure_error_details(last_gate_failure: object) -> str:
    if not isinstance(last_gate_failure, dict):
        return ""
    failed_gates = last_gate_failure.get("failedGates")
    if not isinstance(failed_gates, list):
        return ""
    compact: list[str] = []
    for gate in failed_gates:
        if not isinstance(gate, dict):
            continue
        name = _contract_request_scalar(gate.get("name"))
        reason = _contract_request_scalar(gate.get("reason"))
        if name and reason:
            compact.append(f"{name}:{reason}")
        elif name:
            compact.append(name)
    if not compact:
        return ""
    return f"lastGateFailure={','.join(compact[:3])}"


def _contract_request_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def upload_prepared_strategy_artifact_for_session(
    *,
    local_session: Path,
    narrative_result: dict,
    base_url: str,
    api_key: str,
    export_result: dict,
    opener=urlopen,
) -> dict:
    del local_session
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


def render_strategy_artifact_upload_lines(artifact_result: dict | None) -> list[str]:
    if not artifact_result:
        return []
    if artifact_result.get("artifactUploadSkipped"):
        return [_strategy_artifact_skip_line(artifact_result)]
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


def _strategy_artifact_skip_line(artifact_result: dict) -> str:
    reason = str(artifact_result.get("skipReason") or "unknown").strip()
    reason_text = {
        "hosted_session_id_missing": "the hosted session id was not returned",
        "no_validation_strategy": "no recorded validation round is available yet",
        "no_hostable_validation_strategy": (
            "recorded validation rounds exist, but none currently has the files "
            "needed for a hostable strategy artifact"
        ),
        "artifact_metric_input_unavailable": (
            "the selected validation round is missing metric-input evidence needed "
            "for artifact export"
        ),
    }.get(reason, reason)
    return f"Session view created without a strategy artifact: {reason_text}"


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
