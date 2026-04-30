"""Workflow blocker result and round recording helpers."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from abel_invest.constants import EVENTS_HEADER, RESULTS_HEADER
from abel_invest.io import _now, append_tsv_row
from abel_invest.renderers import render_round_note


def _narrative():
    from abel_invest import narrative_impl

    return narrative_impl


def record_workflow_blocker_round(
    *,
    session: Path,
    branch: Path,
    round_id: str,
    args: argparse.Namespace,
    completed: subprocess.CompletedProcess[str],
    context_path: Path,
    result_path: Path,
    report_path: Path,
    handoff_path: Path,
    backtest_start: str,
    effective_hypothesis: str,
    hypothesis_source: str,
    discovery: dict,
) -> None:
    detail = (completed.stderr or completed.stdout or "").strip()
    failure_signature, runtime_stage = classify_workflow_failure(detail)
    result = build_workflow_blocker_result(
        detail=detail,
        returncode=completed.returncode,
        failure_signature=failure_signature,
        runtime_stage=runtime_stage,
    )
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    report_path.write_text(
        "# Workflow Blocker\n\n"
        f"- failure_signature: `{failure_signature}`\n"
        f"- runtime_stage: `{runtime_stage}`\n"
        f"- returncode: `{completed.returncode}`\n",
        encoding="utf-8",
    )
    handoff_path.write_text(
        json.dumps(
            {
                "contract": "abel-invest.workflow-blocker/v1",
                "ok": False,
                "verdict": "ERROR",
                "failure_signature": failure_signature,
                "runtime_stage": runtime_stage,
                "edge_result_path": str(result_path.relative_to(session)),
                "edge_report_path": str(report_path.relative_to(session)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    round_note = branch / "rounds" / f"{round_id}.md"
    round_note.write_text(
        render_round_note(
            ticker=discovery.get("ticker", session.parent.name.upper()),
            exp_id=session.name,
            branch_id=branch.name,
            round_id=round_id,
            mode=args.mode,
            decision="blocked",
            description=args.description,
            result=result,
            backtest_start=backtest_start,
            input_note=args.input_note,
            hypothesis=effective_hypothesis,
            expected_signal=args.expected_signal,
            trigger=args.trigger,
            change_summary=args.change_summary,
            changed_dimensions=getattr(args, "changed_dimension", []),
            time_spent_min=args.time_spent_min,
            summary="Workflow blocker recorded before edge evaluation completed.",
            next_step="",
            actions=args.action + [f"hypothesis_source={hypothesis_source}"],
            context_mode="injected",
            context_path=str(context_path.relative_to(session)),
            result_path=str(result_path.relative_to(session)),
            report_path=str(report_path.relative_to(session)),
            handoff_path=str(handoff_path.relative_to(session)),
        ),
        encoding="utf-8",
    )
    append_tsv_row(
        branch / "results.tsv",
        RESULTS_HEADER,
        {
            "exp_id": session.name,
            "ticker": discovery.get("ticker", session.parent.name.upper()),
            "branch_id": branch.name,
            "round_id": round_id,
            "decision": "blocked",
            "lo_adj": "0.000",
            "ic": "0.0000",
            "omega": "0.000",
            "sharpe": "0.000",
            "max_dd": "0.0000",
            "pnl": "0.0",
            "K": "0",
            "score": "0/0",
            "verdict": "ERROR",
            "mode": args.mode,
            "description": args.description,
            "result_path": str(result_path.relative_to(session)),
            "report_path": str(report_path.relative_to(session)),
            "handoff_path": str(handoff_path.relative_to(session)),
        },
    )
    append_tsv_row(
        session / "events.tsv",
        EVENTS_HEADER,
        {
            "timestamp": _now(),
            "event": "round_workflow_blocked",
            "branch_id": branch.name,
            "round_id": round_id,
            "mode": args.mode,
            "verdict": "ERROR",
            "decision": "blocked",
            "description": args.description,
            "artifact_path": str(result_path.relative_to(session)),
        },
    )
    _narrative().render_session(session)


def build_workflow_blocker_result(
    *,
    detail: str,
    returncode: int,
    failure_signature: str,
    runtime_stage: str,
) -> dict:
    message = detail or "Edge evaluation did not produce a result JSON."
    return {
        "verdict": "ERROR",
        "score": "0/0",
        "failures": [message],
        "warnings": [],
        "metrics": {},
        "K": 0,
        "profile": "unknown",
        "diagnostics": {
            "failure_signature": failure_signature,
            "runtime_stage": runtime_stage,
            "signal": {"active_days": 0, "total_days": 0},
            "hints": [],
            "returncode": returncode,
        },
        "runtime_facts": {
            "contract": "abel-invest.workflow-blocker/v1",
            "verdict": "ERROR",
            "semantic_verdict": "missing",
            "runtime_stage": runtime_stage,
            "workflow_status": "not_completed",
            "implementation_contract": "unknown",
            "profile": "unknown",
            "requested_window": {},
            "effective_window": {},
            "read_summary": {
                "target_reads": [],
                "auxiliary_reads": [],
                "read_count": 0,
                "decision_count": 0,
            },
            "prepared_inputs": {
                "selected_inputs": [],
                "traced_inputs": [],
                "effective_window": {},
                "issues": [],
            },
            "temporal_visibility": {"issue_kinds": [], "has_error": False},
        },
    }


def classify_workflow_failure(detail: str) -> tuple[str, str]:
    text = str(detail or "").lower()
    if "api key" in text or "auth" in text or "unauthorized" in text:
        return "auth_missing", "data_access"
    if "connection" in text or "timeout" in text or "network" in text or "remote end" in text:
        return "network_error", "data_access"
    if "cache" in text or "no usable target bars" in text or "target bars" in text:
        return "cache_missing", "data_access"
    return "edge_command_failed", "workflow"
