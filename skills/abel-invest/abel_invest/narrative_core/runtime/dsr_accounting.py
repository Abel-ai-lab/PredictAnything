"""DSR trial accounting helpers for alpha/edge handoffs."""

from __future__ import annotations

import json
from pathlib import Path

from abel_invest.narrative_core.contracts.constants import DSR_TRIALS_LOG_FILENAME
from abel_invest.narrative_core.io import _now, append_jsonl_row


def build_dsr_accounting_facts(
    *,
    session: Path,
    branch_id: str,
    round_id: str,
    run_type: str,
    context_path: Path | None,
    result_path: Path | None,
    context: dict | None = None,
    result: dict | None = None,
) -> dict[str, object]:
    context_payload = context if isinstance(context, dict) else _read_json_object(context_path)
    result_payload = result if isinstance(result, dict) else _read_json_object(result_path)
    dsr_trials = _context_dsr_trials(context_payload)
    components = dsr_trials.get("components") if isinstance(dsr_trials.get("components"), dict) else {}
    metrics = result_payload.get("metrics") if isinstance(result_payload.get("metrics"), dict) else {}
    k_detail = result_payload.get("K_detail") if isinstance(result_payload.get("K_detail"), dict) else {}
    diagnostics = result_payload.get("diagnostics") if isinstance(result_payload.get("diagnostics"), dict) else {}
    runtime_facts = result_payload.get("runtime_facts") if isinstance(result_payload.get("runtime_facts"), dict) else {}
    result_contract = str(runtime_facts.get("contract") or "")
    has_edge_k_facts = bool(result_payload) and result_contract != "abel-invest.workflow-blocker/v1"
    verdict = str(result_payload.get("verdict") or "missing").upper()
    runtime_stage = str(
        runtime_facts.get("runtime_stage")
        or diagnostics.get("runtime_stage")
        or "missing"
    )
    validation_completed = verdict in {"PASS", "FAIL"} and runtime_stage == "validation"
    return {
        "event": "edge_dsr_accounting_recorded",
        "branch_id": branch_id,
        "round_id": round_id,
        "run_type": run_type,
        "verdict": verdict,
        "runtime_stage": runtime_stage,
        "counted_for_future_dsr": run_type == "round" and validation_completed,
        "alpha_declared_count": _int_or_none(dsr_trials.get("count")),
        "alpha_current_round_trials": _int_or_none(components.get("current_round_trials")),
        "alpha_prior_effective_trials": _int_or_none(components.get("prior_effective_trials")),
        "edge_k": _int_or_none(result_payload.get("K")) if has_edge_k_facts else None,
        "edge_dsr_trials_used": _int_or_none(metrics.get("dsr_trials_used")) if has_edge_k_facts else None,
        "edge_k_source": str(k_detail.get("source") or ("missing" if has_edge_k_facts else "not_available")),
        "engine_ast_k": _int_or_none(k_detail.get("engine_ast_k")) if has_edge_k_facts else None,
        "context_path": _relative_path(context_path, session),
        "result_path": _relative_path(result_path, session),
    }


def append_dsr_accounting_record(session: Path, facts: dict[str, object]) -> None:
    append_jsonl_row(
        session / DSR_TRIALS_LOG_FILENAME,
        {"timestamp": _now(), **facts},
    )


def _context_dsr_trials(context: dict) -> dict:
    validation_context = context.get("validation_context") if isinstance(context.get("validation_context"), dict) else {}
    dsr_trials = validation_context.get("dsr_trials") if isinstance(validation_context.get("dsr_trials"), dict) else {}
    return dsr_trials


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _read_json_object(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _relative_path(path: Path | None, session: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(session))
    except ValueError:
        return str(path)
