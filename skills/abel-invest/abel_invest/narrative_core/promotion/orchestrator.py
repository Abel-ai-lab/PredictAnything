"""Strategy promotion helpers for paper-ready runtime state boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .constants import (
    PROMOTION_CONTRACT_REPORT_FILENAME,
    PROMOTION_GATE_FILENAME,
    PROMOTION_HOSTED_CONTRACT_SCOPE,
    PROMOTION_MODE_AGENT_PAPER_CONTRACT,
    PROMOTION_MODE_ZERO_CHANGE,
    PROMOTION_PATCH_FILENAME,
)
from .cleanup import cleanup_legacy_promotion_outputs as _cleanup_legacy_promotion_outputs
from .facts import (
    _collect_hosted_paper_dependency_scan,
    _hosted_paper_contract_signals,
    _initial_hosted_paper_contract_signals,
    _scan_cutover_end,
    _validate_promoted_source_static,
)
from .gate import (
    _build_contract_promotion_gate_report,
    _promotion_gate_failure_request_payload,
)
from .models import (
    PromotionHostedPaperContractRequired,
    PromotionPackagedFile,
    PromotionResult,
)
from .packaging import (
    _report_packaged_files,
    _validate_packaged_research_evidence_sources,
)
from .paper.smoke import (
    _fast_paper_validation,
    _generated_replay_initial_state_files,
)
from .paper.trace import (
    PROMOTION_TAIL_TRACE_FILENAME,
    paper_dry_run_gate_summary as _paper_dry_run_gate_summary,
    write_paper_tail_trace as _write_paper_tail_trace,
)
from .report import (
    _load_agent_contract_report,
    _report_continuation_method,
    _report_has_hosted_paper_contract,
    _report_paper_execution_profile,
    _write_artifact_contract_report,
)
from .request import (
    _full_replay_fallback_allowed,
    _write_hosted_paper_contract_request,
)
from .utils import _clean
from .validation import _validate_agent_paper_signal_contract


def prepare_promotion(
    candidate: Any,
    *,
    destination: Path,
    strategy_entrypoint: str,
    is_denylisted_source: Callable[[Path], bool],
    sha256_file: Callable[[Path], str],
    runtime_env: dict[str, str] | None = None,
) -> PromotionResult:
    promoted_dir = destination / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_legacy_promotion_outputs(destination, promoted_dir)
    promoted_source = promoted_dir / "engine.py"
    existing_contract_report = promoted_dir / PROMOTION_CONTRACT_REPORT_FILENAME
    original_text = candidate.strategy_source_path.read_text(encoding="utf-8")
    agent_contract_ready = promoted_source.is_file() and existing_contract_report.is_file()
    dependency_scan = _collect_hosted_paper_dependency_scan(
        candidate.branch,
        strategy_source_path=candidate.strategy_source_path,
        is_denylisted_source=is_denylisted_source,
        candidate=candidate,
        destination=destination,
    )

    hosted_contract_signals = _hosted_paper_contract_signals(dependency_scan)
    if not agent_contract_ready:
        contract_signals = _initial_hosted_paper_contract_signals(
            hosted_contract_signals
        )
        promoted_source.write_text(original_text, encoding="utf-8")
        request_path = _write_hosted_paper_contract_request(
            promoted_dir,
            branch=candidate.branch,
            source_path=promoted_source,
            dependency_scan=dependency_scan,
            signals=contract_signals,
        )
        raise PromotionHostedPaperContractRequired(
            "hosted paper contract required before first artifact export; "
            f"request written to {request_path}"
        )

    strategy_source_path = candidate.strategy_source_path
    patch_path = None
    contract_report_path = None
    mode = PROMOTION_MODE_ZERO_CHANGE
    contract_summary = ""
    packaged_files: tuple[PromotionPackagedFile, ...] = ()
    contract_report: dict[str, Any] | None = None
    paper_execution_profile: dict[str, Any] | None = None
    promoted_text = original_text

    if agent_contract_ready:
        promoted_text = promoted_source.read_text(encoding="utf-8")
        contract_report = _load_agent_contract_report(existing_contract_report)
        if not _report_has_hosted_paper_contract(contract_report):
            raise PromotionHostedPaperContractRequired(
                "hosted paper contract report must use hosted_paper_contract scope"
            )
        contract_summary = _clean(contract_report.get("summary")) or (
            "Agent declared the hosted paper contract."
        )
        packaged_files = tuple(
            _report_packaged_files(
                contract_report,
                branch=candidate.branch,
                is_denylisted_source=is_denylisted_source,
            )
        )
        _validate_packaged_research_evidence_sources(
            packaged_files,
            branch=candidate.branch,
            destination=destination,
            report=contract_report,
        )
        artifact_contract_report_path = _write_artifact_contract_report(
            promoted_dir,
            contract_report,
        )
        _validate_agent_paper_signal_contract(
            contract_report,
            promoted_text,
            require_paper_signal=True,
            candidate=candidate,
            full_replay_fallback_allowed=_full_replay_fallback_allowed(promoted_dir),
            source_dependency_scan=dependency_scan,
            original_source=original_text,
        )
        paper_execution_profile = _report_paper_execution_profile(contract_report)
        mode = PROMOTION_MODE_AGENT_PAPER_CONTRACT
        strategy_source_path = promoted_source
        contract_report_path = artifact_contract_report_path

    source_changed = promoted_text != original_text
    if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT and source_changed:
        patch_path = promoted_dir / PROMOTION_PATCH_FILENAME
        patch_path.write_text(
            _source_edit_summary(
                candidate.strategy_source_path,
                scope=_clean(contract_report.get("scope"))
                if contract_report is not None
                else "agent_paper_contract",
                report=contract_report,
            ),
            encoding="utf-8",
        )
    _validate_promoted_source_static(strategy_source_path)

    original_sha = sha256_file(candidate.strategy_source_path)
    promoted_sha = sha256_file(strategy_source_path)
    if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT:
        contract_payload = {
            "kind": PROMOTION_HOSTED_CONTRACT_SCOPE,
            "summary": contract_summary,
            "reportPath": f"edge/{PROMOTION_CONTRACT_REPORT_FILENAME}",
        }
        if patch_path is not None:
            contract_payload["patchPath"] = f"edge/{PROMOTION_PATCH_FILENAME}"
    else:
        contract_payload = None
    behavior_equivalence = _default_behavior_equivalence(
        mode=mode,
        source_changed=source_changed,
    )
    paper_dry_run = _fast_paper_validation(
        mode=mode,
        source=promoted_text,
        report=contract_report,
        candidate=candidate,
        strategy_source_path=strategy_source_path,
        packaged_files=packaged_files,
        destination=destination,
        strategy_entrypoint=strategy_entrypoint,
        runtime_env=runtime_env,
        is_denylisted_source=is_denylisted_source,
    )
    tail_trace_path = _write_paper_tail_trace(destination, paper_dry_run)
    gate_paper_dry_run = _paper_dry_run_gate_summary(
        paper_dry_run,
        trace_path=tail_trace_path,
    )
    if paper_dry_run.get("status") == "passed":
        replay_state_files = _generated_replay_initial_state_files(destination)
        if replay_state_files:
            replay_artifact_paths = {
                item.artifact_path for item in replay_state_files
            }
            packaged_files = tuple(
                item
                for item in packaged_files
                if item.artifact_path not in replay_artifact_paths
            ) + replay_state_files
    gate_path = destination / PROMOTION_GATE_FILENAME
    gate_report = _build_contract_promotion_gate_report(
        promotion_mode=mode,
        original_source_sha256=original_sha,
        promoted_source_sha256=promoted_sha,
        patch_sha256=sha256_file(patch_path) if patch_path is not None else None,
        contract=contract_payload,
        state_entries=packaged_files,
        behavior_equivalence=behavior_equivalence,
        paper_dry_run=gate_paper_dry_run,
    )
    gate_path.write_text(
        json.dumps(gate_report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if gate_report.get("status") != "passed":
        request_source_path = strategy_source_path
        if request_source_path.resolve() == candidate.strategy_source_path.resolve():
            promoted_source.write_text(original_text, encoding="utf-8")
            request_source_path = promoted_source
        failure_scan = _collect_hosted_paper_dependency_scan(
            candidate.branch,
            strategy_source_path=request_source_path,
            is_denylisted_source=is_denylisted_source,
            candidate=candidate,
            destination=destination,
        )
        failure_details = _promotion_gate_failure_request_payload(
            gate_report,
            selected_round_cutover_end=_scan_cutover_end(failure_scan),
        )
        failure_signals = _hosted_paper_contract_signals(failure_scan)
        failure_signals.append(
            {
                "kind": "promotion_gate_failed",
                "value": ",".join(
                    item.get("name", "")
                    for item in failure_details.get("failedGates", [])
                    if item.get("name")
                )
                or _clean(gate_report.get("status"))
                or "unknown",
                "reason": "latest promotion gate did not pass",
            }
        )
        request_path = _write_hosted_paper_contract_request(
            promoted_dir,
            branch=candidate.branch,
            source_path=request_source_path,
            dependency_scan=failure_scan,
            signals=failure_signals,
            validation_failure=failure_details,
        )
        raise PromotionHostedPaperContractRequired(
            "promotion gate did not pass: "
            f"{gate_report.get('status')}; request updated at {request_path}"
        )

    extra_source_map = {strategy_entrypoint: strategy_source_path}
    for item in packaged_files:
        extra_source_map[item.artifact_path] = item.source_path
    extra_source_map[f"edge/{PROMOTION_GATE_FILENAME}"] = gate_path
    if patch_path is not None:
        extra_source_map[f"edge/{PROMOTION_PATCH_FILENAME}"] = patch_path
    if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT:
        assert contract_report_path is not None
        extra_source_map[f"edge/{PROMOTION_CONTRACT_REPORT_FILENAME}"] = contract_report_path
    if tail_trace_path is not None:
        extra_source_map[f"edge/{PROMOTION_TAIL_TRACE_FILENAME}"] = tail_trace_path

    return PromotionResult(
        mode=mode,
        strategy_source_path=strategy_source_path,
        packaged_files=packaged_files,
        extra_source_map=extra_source_map,
        patch_path=patch_path,
        gate_path=gate_path,
        contract_report_path=contract_report_path,
        paper_execution_profile=paper_execution_profile,
        report={
            "mode": mode,
            "continuationMethod": _report_continuation_method(contract_report),
            "paperExecutionProfile": paper_execution_profile or {},
            "initialStateFileCount": len(
                [
                    item
                    for item in packaged_files
                    if item.role == "initial_state"
                    or item.artifact_path.startswith("runtime/initial-state/")
                ]
            ),
            "packagedFileCount": len(packaged_files),
            "sourceChanged": source_changed,
            "contractSummary": contract_summary,
            "patchPath": str(patch_path) if patch_path is not None else "",
            "contractReportPath": str(contract_report_path)
            if contract_report_path is not None
            else "",
            "gatePath": str(gate_path),
        },
    )


def _default_behavior_equivalence(
    *,
    mode: str,
    source_changed: bool,
) -> dict[str, Any]:
    return {
        "status": "passed",
        "method": "agent_declared_hosted_paper_contract"
        if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT
        else "source_hash_identity",
        "sourceChanged": source_changed,
    }






def _source_edit_summary(
    source_path: Path,
    *,
    scope: str = PROMOTION_HOSTED_CONTRACT_SCOPE,
    report: dict[str, Any] | None = None,
) -> str:
    source_edit = report.get("sourceEdit") if isinstance(report, dict) else None
    paths = source_edit.get("paths") if isinstance(source_edit, dict) else []
    lines = [
        f"source: {source_path}",
        f"scope: {scope}",
        "sourceEdit:",
    ]
    if isinstance(source_edit, dict):
        lines.append(f"- reason: {_clean(source_edit.get('reason'))}")
    if isinstance(paths, list) and paths:
        for path in paths:
            lines.append(f"- path: {path}")
    else:
        lines.append("- path: engine.py")
    return "\n".join(lines) + "\n"
