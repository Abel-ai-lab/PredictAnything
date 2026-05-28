"""Promotion gate report helpers."""

from __future__ import annotations

from typing import Any

from abel_edge.research.promotion_gate import build_promotion_gate_report

from .promotion_paper_trace import tail_parity_failure_diagnosis as _tail_parity_failure_diagnosis
from .promotion_utils import _clean, _json_safe

def _promotion_gate_failure_request_payload(
    gate_report: dict[str, Any],
    *,
    selected_round_cutover_end: str = "",
) -> dict[str, Any]:
    failed_gates: list[dict[str, Any]] = []
    gates = gate_report.get("gates") if isinstance(gate_report.get("gates"), list) else []
    for gate in gates:
        if not isinstance(gate, dict) or gate.get("status") == "passed":
            continue
        details = gate.get("details") if isinstance(gate.get("details"), dict) else {}
        failure: dict[str, Any] = {
            "name": _clean(gate.get("name")),
            "status": _clean(gate.get("status")),
            "method": _clean(gate.get("method")),
        }
        reason = _clean(details.get("reason") or gate.get("reason"))
        if reason:
            failure["reason"] = reason
        smoke = details.get("smoke")
        if isinstance(smoke, dict):
            compact_smoke: dict[str, Any] = {}
            tail = smoke.get("tailConsistency")
            if isinstance(tail, dict):
                compact_smoke["tailConsistency"] = _tail_parity_failure_diagnosis(
                    tail,
                    selected_round_cutover_end=selected_round_cutover_end,
                    trace_path=_clean(smoke.get("tracePath")),
                )
            for key in (
                "validationBootstrap",
                "warmStart",
                "elapsedSeconds",
                "firstElapsedSeconds",
                "secondElapsedSeconds",
                "warnings",
                "timeoutSeconds",
                "diagnosis",
            ):
                if key in smoke:
                    compact_smoke[key] = _json_safe(smoke[key])
            if compact_smoke:
                failure["smoke"] = _json_safe(compact_smoke)
                failure["oraclePolicy"] = (
                    "gate failures are semantic diagnostics only; exact oracle "
                    "answers are not part of the paper contract request and must not be "
                    "patched into strategy code, assets, or initial state"
                )
        failed_gates.append(failure)
    payload = {
        "status": _clean(gate_report.get("status")),
        "failedGates": failed_gates,
    }
    if selected_round_cutover_end:
        payload["selectedRoundCutoverEnd"] = selected_round_cutover_end
    return payload
def _build_contract_promotion_gate_report(
    **kwargs: Any,
) -> dict[str, Any]:
    contract = kwargs.pop("contract", None)
    return build_promotion_gate_report(contract=contract, **kwargs)
