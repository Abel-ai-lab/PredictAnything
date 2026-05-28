"""Edge paper_run_one smoke validation for strategy promotion."""

from __future__ import annotations

import csv
from contextlib import contextmanager, redirect_stdout
import json
import re
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import threading
import time
from typing import Any, Callable

import pandas as pd

from abel_edge.engine.ledger import read_trade_log
from abel_edge.engine.trader import paper_run_one

from .. import source_scan, tail_oracle
from ..constants import (
    PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS,
    PROMOTION_HOSTED_PAPER_TIMEOUT_SECONDS,
    PROMOTION_MODE_AGENT_PAPER_CONTRACT,
    PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS,
    PROMOTION_PAPER_TAIL_TOLERANCE,
)
from ..report import (
    _paper_signal_continuation_payload,
    _paper_signal_design_payload,
    _paper_signal_evidence_payload,
    _report_continuation_method,
    _report_paper_execution_profile,
)
from ..models import PromotionPackagedFile
from ..packaging import _validate_packaged_artifact_path
from ..utils import (
    _clean,
    _copy_if_exists,
    _date_part,
    _finite_float,
    _is_branch_relative,
    _json_safe,
    _load_json_object_if_exists,
    _load_smoke_strategy_class,
    _sha256_bytes,
    _snapshot_tree,
    _temporary_environ,
    _temporary_sys_path,
)

_paper_signal_design_facts = source_scan.paper_signal_design_facts
_paper_signal_full_runtime_compute_path = source_scan.paper_signal_full_runtime_compute_path
_paper_signal_uses_full_runtime_compute = source_scan.paper_signal_uses_full_runtime_compute
_source_overrides_get_paper_signal = source_scan.source_overrides_get_paper_signal
_paper_tail_oracle_rows = tail_oracle.paper_tail_oracle_rows
_tail_consistency_payload = tail_oracle.tail_consistency_payload

def _paper_smoke_max_call_elapsed(smoke: dict[str, Any]) -> float:
    values: list[float] = []
    for key in ("firstElapsedSeconds", "secondElapsedSeconds"):
        value = _finite_float(smoke.get(key))
        if value is not None:
            values.append(value)
    tail = smoke.get("tailConsistency")
    comparisons = tail.get("comparisons") if isinstance(tail, dict) else None
    if isinstance(comparisons, list):
        for item in comparisons:
            if not isinstance(item, dict):
                continue
            value = _finite_float(item.get("elapsedSeconds"))
            if value is not None:
                values.append(value)
    return max(values, default=0.0)


class _PaperSmokeTimeout(BaseException):
    pass


@contextmanager
def _paper_smoke_timeout(seconds: float):
    if (
        seconds <= 0
        or not hasattr(signal, "SIGALRM")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    def _raise_timeout(signum, frame):  # noqa: ARG001
        raise _PaperSmokeTimeout

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _run_edge_paper_run_one_smoke(
    candidate: Any,
    *,
    strategy_source_path: Path,
    packaged_files: tuple[PromotionPackagedFile, ...],
    destination: Path,
    strategy_entrypoint: str,
    runtime_env: dict[str, str] | None,
    is_denylisted_source: Callable[[Path], bool],
    report: dict[str, Any] | None,
) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        with _paper_smoke_timeout(PROMOTION_HOSTED_PAPER_TIMEOUT_SECONDS):
            return _run_edge_paper_run_one_smoke_unbounded(
                candidate,
                strategy_source_path=strategy_source_path,
                packaged_files=packaged_files,
                destination=destination,
                strategy_entrypoint=strategy_entrypoint,
                runtime_env=runtime_env,
                is_denylisted_source=is_denylisted_source,
                report=report,
            )
    except _PaperSmokeTimeout:
        return {
            "status": "failed",
            "reason": (
                "paper_run_one tail smoke timed out after "
                f"{PROMOTION_HOSTED_PAPER_TIMEOUT_SECONDS:g}s"
            ),
            "timeoutSeconds": PROMOTION_HOSTED_PAPER_TIMEOUT_SECONDS,
            "elapsedSeconds": round(time.monotonic() - started_at, 6),
            "diagnosis": {
                "likelyCause": (
                    "get_paper_signal performs full replay or repeated refit "
                    "during daily paper smoke"
                ),
                "check": (
                    "inspect the get_paper_signal call path and avoid "
                    "compute_runtime_output from the daily path"
                ),
            },
        }


def _run_edge_paper_run_one_smoke_unbounded(
    candidate: Any,
    *,
    strategy_source_path: Path,
    packaged_files: tuple[PromotionPackagedFile, ...],
    destination: Path,
    strategy_entrypoint: str,
    runtime_env: dict[str, str] | None,
    is_denylisted_source: Callable[[Path], bool],
    report: dict[str, Any] | None,
) -> dict[str, Any]:
    started_at = time.monotonic()
    oracle_rows = _paper_tail_oracle_rows(destination / "trade-log.csv")
    if not oracle_rows:
        return {
            "status": "failed",
            "reason": (
                "paper signal tail consistency oracle is unavailable; "
                "trade-log.csv must contain date and next_position columns"
            ),
        }
    try:
        with tempfile.TemporaryDirectory(prefix="abel-paper-run-one-") as temp_name:
            root = Path(temp_name)
            strategy_dir = root / "strategy"
            runtime_dir = root / "runtime"
            state_dir = root / "state"
            strategy_dir.mkdir(parents=True)
            runtime_dir.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            _stage_paper_smoke_files(
                candidate,
                strategy_source_path=strategy_source_path,
                packaged_files=packaged_files,
                strategy_dir=strategy_dir,
                runtime_dir=runtime_dir,
                state_dir=state_dir,
                strategy_entrypoint=strategy_entrypoint,
                is_denylisted_source=is_denylisted_source,
            )
            (strategy_dir / "__init__.py").touch()
            context = _paper_smoke_context(
                candidate,
                strategy_dir=strategy_dir,
                runtime_dir=runtime_dir,
                state_dir=state_dir,
                workspace_dir=root,
            )
            context["engine"] = "strategy.strategy"
            context["trade_log"] = str(root / "trade-log.csv")
            context["paper_log"] = str(state_dir / "paper-log.csv")
            validation_context = context.get("_promotion_validation")
            profile = _report_paper_execution_profile(report)
            if profile:
                context["runtime"] = {"paperExecutionProfile": profile}
            requires_validation_bootstrap = (
                _report_continuation_method(report) == "stateful_continuation"
            )
            if requires_validation_bootstrap:
                _clear_replay_initial_state(destination)
                _clear_directory(state_dir)
            seed = _seed_paper_smoke_log(
                destination / "trade-log.csv",
                oracle_rows=oracle_rows,
                trade_log_path=Path(context["trade_log"]),
                paper_log_path=Path(context["paper_log"]),
            )
            if seed.get("status") == "failed":
                return seed
            with _temporary_environ(runtime_env or {}), _temporary_sys_path(
                [strategy_dir.parent, strategy_dir]
            ):
                bootstrap = {"required": False, "status": "skipped"}
                if requires_validation_bootstrap:
                    cls = _load_smoke_strategy_class(strategy_dir / "strategy.py")
                    engine = cls(context)
                    with redirect_stdout(sys.stderr):
                        bootstrap = _run_paper_validation_state_bootstrap(
                            engine,
                            state_dir=state_dir,
                            oracle_rows=oracle_rows,
                            required=True,
                        )
                    if bootstrap.get("status") == "failed":
                        return {
                            "status": "failed",
                            "reason": _clean(bootstrap.get("reason"))
                            or "paper validation state bootstrap failed",
                            "validationBootstrap": bootstrap,
                        }
                before_first = _snapshot_tree(state_dir)
                run_started = time.monotonic()
                with redirect_stdout(sys.stderr):
                    first = paper_run_one(context, as_of=oracle_rows[-1]["asOf"])
                first_elapsed = time.monotonic() - run_started
                after_first = _snapshot_tree(state_dir)
                comparisons = _paper_run_tail_comparisons(
                    Path(context["paper_log"]),
                    oracle_rows=oracle_rows,
                    elapsed_seconds=first_elapsed,
                    state_changed=after_first != before_first,
                )
                failed = [
                    item
                    for item in comparisons
                    if item.get("absDiff") is None
                    or float(item.get("absDiff")) > PROMOTION_PAPER_TAIL_TOLERANCE
                ]
                if failed:
                    return {
                        "status": "failed",
                        "reason": (
                            "paper_run_one next_position diverged from the "
                            "selected round trade-log tail"
                        ),
                        "tailConsistency": _tail_consistency_payload(
                            oracle_rows,
                            comparisons,
                            status="failed",
                        ),
                        "validationContext": _json_safe(validation_context),
                        "result": _json_safe(first),
                    }
                before_second = after_first
                second_started = time.monotonic()
                with redirect_stdout(sys.stderr):
                    second = paper_run_one(context, as_of=oracle_rows[-1]["asOf"])
                second_elapsed = time.monotonic() - second_started
                after_second = _snapshot_tree(state_dir)
            if second.get("n_rows") != 0 or after_second != before_second:
                return {
                    "status": "failed",
                    "reason": "paper_run_one was not idempotent for the same as_of",
                    "asOf": oracle_rows[-1]["asOf"],
                    "firstResult": _json_safe(first),
                    "secondResult": _json_safe(second),
                    "validationContext": _json_safe(validation_context),
                    "tailConsistency": _tail_consistency_payload(
                        oracle_rows,
                        comparisons,
                        status="passed",
                    ),
                }
            latest_position = _finite_float(comparisons[-1].get("actualNextPosition"))
            generated_initial_state_files = []
            if requires_validation_bootstrap:
                generated_initial_state_files = _materialize_replay_initial_state(
                    state_dir,
                    destination=destination,
                )
                if not generated_initial_state_files:
                    return {
                        "status": "failed",
                        "reason": (
                            "stateful_continuation replay produced no startup "
                            "strategy state files to package"
                        ),
                        "tailConsistency": _tail_consistency_payload(
                            oracle_rows,
                            comparisons,
                            status="passed",
                        ),
                        "validationBootstrap": bootstrap,
                    }
            return {
                "status": "passed",
                "asOf": oracle_rows[-1]["asOf"],
                "nextPosition": latest_position,
                "firstElapsedSeconds": round(first_elapsed, 6),
                "secondElapsedSeconds": round(second_elapsed, 6),
                "elapsedSeconds": round(time.monotonic() - started_at, 6),
                "stateChangedFirstCall": after_first != before_first,
                "stateChangedSecondCall": False,
                "sameResult": second.get("n_rows") == 0,
                "tailConsistency": _tail_consistency_payload(
                    oracle_rows,
                    comparisons,
                    status="passed",
                ),
                "validationBootstrap": bootstrap,
                "generatedInitialStateFiles": generated_initial_state_files,
                "validationContext": _json_safe(validation_context),
                "warmStart": _warm_start_payload(
                    comparisons,
                    repeated_elapsed=second_elapsed,
                    repeated_state_changed=False,
                ),
                "warnings": [],
                "result": _json_safe(first),
            }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"{exc.__class__.__name__}: {exc}",
            "elapsedSeconds": round(time.monotonic() - started_at, 6),
        }


def _seed_paper_smoke_log(
    source_trade_log: Path,
    *,
    oracle_rows: list[dict[str, Any]],
    trade_log_path: Path,
    paper_log_path: Path,
) -> dict[str, Any]:
    cutover_as_of = _clean(oracle_rows[0].get("validationCutoverAsOf")) if oracle_rows else ""
    frame = read_trade_log(source_trade_log)
    trade_log_path.parent.mkdir(parents=True, exist_ok=True)
    paper_log_path.parent.mkdir(parents=True, exist_ok=True)
    if not cutover_as_of:
        return {
            "status": "failed",
            "reason": (
                "paper_run_one smoke requires a real selected-round cutover row "
                "before the holdout tail; refusing to synthesize a paper ledger seed"
            ),
        }
    dates = pd.to_datetime(frame["date"], utc=True, format="mixed")
    cutover = pd.to_datetime(cutover_as_of, utc=True)
    seed = frame[dates <= cutover].tail(1).copy()
    if seed.empty:
        return {
            "status": "failed",
            "reason": f"paper_run_one smoke could not find cutover row {cutover_as_of}",
        }
    seed.to_csv(trade_log_path, index=False)
    seed.to_csv(paper_log_path, index=False)
    return {"status": "passed", "cutoverAsOf": cutover_as_of}


def _paper_run_tail_comparisons(
    paper_log_path: Path,
    *,
    oracle_rows: list[dict[str, Any]],
    elapsed_seconds: float,
    state_changed: bool,
) -> list[dict[str, Any]]:
    frame = read_trade_log(paper_log_path)
    by_date: dict[str, float | None] = {}
    for _, row in frame.iterrows():
        as_of = _date_part(_clean(row.get("date") or row.get("decision_time")))
        if not as_of:
            continue
        by_date[as_of] = _finite_float(row.get("next_position"))
    per_row_elapsed = elapsed_seconds / max(len(oracle_rows), 1)
    comparisons: list[dict[str, Any]] = []
    for oracle in oracle_rows:
        actual = by_date.get(_clean(oracle.get("asOf")))
        expected = float(oracle["expectedNextPosition"])
        comparisons.append(
            {
                "asOf": oracle["asOf"],
                "decisionIndex": oracle.get("decisionIndex"),
                "expectedNextPosition": expected,
                "actualNextPosition": actual,
                "absDiff": abs(actual - expected) if actual is not None else None,
                "elapsedSeconds": round(per_row_elapsed, 6),
                "stateChanged": state_changed,
            }
        )
    return comparisons


def _fast_paper_validation(
    *,
    mode: str,
    source: str,
    report: dict[str, Any] | None,
    candidate: Any,
    strategy_source_path: Path,
    packaged_files: tuple[PromotionPackagedFile, ...],
    destination: Path,
    strategy_entrypoint: str,
    runtime_env: dict[str, str] | None,
    is_denylisted_source: Callable[[Path], bool],
) -> dict[str, Any]:
    full_compute = _paper_signal_uses_full_runtime_compute(source)
    full_compute_path = _paper_signal_full_runtime_compute_path(source)
    continuation_method = _report_continuation_method(report)
    design_facts = _paper_signal_design_facts(source)
    requires_direct_signal = continuation_method != "stateless_recompute"
    if requires_direct_signal and full_compute and continuation_method != "full_replay_fallback":
        path_text = (
            " -> ".join(full_compute_path)
            if full_compute_path
            else "get_paper_signal -> compute_runtime_output"
        )
        return {
            "status": "failed",
            "method": "paper_signal_contract_static",
            "reason": (
                "get_paper_signal reaches full historical runtime compute via "
                f"{path_text}. Move historical replay/bootstrap into "
                "build_paper_initial_state and make get_paper_signal load or "
                "advance PaperStateStore state only."
            ),
            "fullRuntimeComputePath": full_compute_path,
            **design_facts,
        }
    if requires_direct_signal and not _source_overrides_get_paper_signal(source):
        return {
            "status": "failed",
            "method": "paper_signal_contract_static",
            "reason": "promoted source does not define get_paper_signal",
            **design_facts,
        }
    source_overrides_signal = _source_overrides_get_paper_signal(source)
    details: dict[str, Any] = {
        "paperExecution": "edge_paper_run_one",
        "paperSignal": "direct_get_paper_signal"
        if source_overrides_signal
        else "edge_compiled_recompute",
        "fullRuntimeCompute": full_compute,
        "fullRuntimeComputePath": full_compute_path,
        **design_facts,
    }
    profile = _report_paper_execution_profile(report)
    if profile:
        details["paperExecutionProfile"] = _json_safe(profile)
    if mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT and report is not None:
        paper_signal = report.get("paperSignal")
        if isinstance(paper_signal, dict):
            details["incrementalReady"] = paper_signal.get("incrementalReady") is True
            live_readiness = _clean(
                paper_signal.get("liveReadiness") or paper_signal.get("notes")
            )
            if live_readiness:
                details["agentLiveReadiness"] = live_readiness
            design = _paper_signal_design_payload(paper_signal)
            if isinstance(design, dict):
                details["agentDesign"] = _json_safe(design)
            continuation = _paper_signal_continuation_payload(paper_signal)
            if isinstance(continuation, dict):
                details["agentContinuation"] = _json_safe(continuation)
            evidence = _paper_signal_evidence_payload(paper_signal)
            if isinstance(evidence, dict):
                details["agentEvidence"] = _json_safe(evidence)

    smoke = _run_edge_paper_run_one_smoke(
        candidate,
        strategy_source_path=strategy_source_path,
        packaged_files=packaged_files,
        destination=destination,
        strategy_entrypoint=strategy_entrypoint,
        runtime_env=runtime_env,
        is_denylisted_source=is_denylisted_source,
        report=report,
    )
    details["smoke"] = {
        key: value for key, value in smoke.items() if key not in {"status", "reason"}
    }
    if smoke.get("status") != "passed":
        return {
            "status": "failed",
            "method": "edge_paper_run_one_tail_smoke",
            "reason": _clean(smoke.get("reason")) or "paper_run_one smoke failed",
            **details,
        }
    if continuation_method == "full_replay_fallback":
        max_call_elapsed = _paper_smoke_max_call_elapsed(smoke)
        if max_call_elapsed > PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS:
            return {
                "status": "failed",
                "method": "full_replay_fallback_performance",
                "reason": (
                    "full_replay_fallback exceeded the hosted paper "
                    f"limit of {PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS:g}s "
                    "for a single paper signal call"
                ),
                "maxCallElapsedSeconds": round(max_call_elapsed, 6),
                **details,
            }
    return {
        "status": "passed",
        "method": "edge_paper_run_one_tail_smoke",
        **details,
    }


def _replay_initial_state_root(destination: Path) -> Path:
    return destination / "promoted" / "runtime" / "initial-state"


def _clear_replay_initial_state(destination: Path) -> None:
    root = _replay_initial_state_root(destination)
    if root.exists():
        shutil.rmtree(root)


def _materialize_replay_initial_state(
    state_dir: Path,
    *,
    destination: Path,
) -> list[dict[str, Any]]:
    target_root = _replay_initial_state_root(destination)
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    strategy_state_root = state_dir / "strategy"
    search_root = strategy_state_root if strategy_state_root.is_dir() else state_dir
    for source in sorted(path for path in search_root.rglob("*") if path.is_file()):
        relative = source.relative_to(state_dir)
        if relative.name in {"paper-log.csv", "trade-log.csv"}:
            continue
        if relative.parts and relative.parts[0] != "strategy":
            continue
        artifact_path = f"runtime/initial-state/{relative.as_posix()}"
        _validate_packaged_artifact_path(
            artifact_path,
            role="initial_state",
            is_denylisted_source=lambda _relative: False,
        )
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        data = target.read_bytes()
        entries.append(
            {
                "artifactPath": artifact_path,
                "bytes": len(data),
                "sha256": _sha256_bytes(data),
                "source": "gate_tail_replay_state",
            }
        )
    return entries


def _generated_replay_initial_state_files(
    destination: Path,
) -> tuple[PromotionPackagedFile, ...]:
    root = _replay_initial_state_root(destination)
    if not root.is_dir():
        return ()
    generated: list[PromotionPackagedFile] = []
    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = source.relative_to(root)
        artifact_path = f"runtime/initial-state/{relative.as_posix()}"
        generated.append(
            PromotionPackagedFile(
                artifact_path=artifact_path,
                source_path=source,
                purpose=(
                    "Gate-generated startup state after successful stateful "
                    "tail paper replay."
                ),
                role="initial_state",
            )
        )
    return tuple(generated)


def _stage_paper_smoke_files(
    candidate: Any,
    *,
    strategy_source_path: Path,
    packaged_files: tuple[PromotionPackagedFile, ...],
    strategy_dir: Path,
    runtime_dir: Path,
    state_dir: Path,
    strategy_entrypoint: str,
    is_denylisted_source: Callable[[Path], bool],
) -> None:
    staged_packaged_sources: set[Path] = {
        item.source_path.resolve()
        for item in packaged_files
        if _is_branch_relative(item.source_path, candidate.branch)
    }
    for source_path in sorted(path for path in candidate.branch.rglob("*") if path.is_file()):
        if source_path.resolve() == candidate.strategy_source_path.resolve():
            continue
        if source_path.resolve() in staged_packaged_sources:
            continue
        relative = source_path.relative_to(candidate.branch)
        if is_denylisted_source(relative):
            continue
        destination = strategy_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)

    shutil.copy2(strategy_source_path, strategy_dir / Path(strategy_entrypoint).name)
    _copy_if_exists(candidate.branch / "branch.yaml", runtime_dir / "strategy.yaml")
    _copy_if_exists(candidate.branch / "inputs" / "dependencies.json", runtime_dir / "dependencies.json")
    _copy_if_exists(candidate.branch / "inputs" / "data_manifest.json", runtime_dir / "data_manifest.json")

    for item in packaged_files:
        if item.role == "base_asset":
            relative = Path(item.artifact_path.removeprefix("strategy/"))
            target = strategy_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, target)
        elif item.role == "initial_state":
            relative = Path(item.artifact_path.removeprefix("runtime/initial-state/"))
            runtime_target = runtime_dir / "initial-state" / relative
            runtime_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, runtime_target)
            state_target = state_dir / relative
            state_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, state_target)


def _clear_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _run_paper_validation_state_bootstrap(
    engine: Any,
    *,
    state_dir: Path,
    oracle_rows: list[dict[str, Any]],
    required: bool,
) -> dict[str, Any]:
    if not required:
        return {"required": False, "status": "skipped"}
    cutover_as_of = _clean(oracle_rows[0].get("validationCutoverAsOf")) if oracle_rows else ""
    if not cutover_as_of:
        return {
            "required": True,
            "status": "failed",
            "reason": (
                "stateful_continuation validation needs at least one trade-log "
                "row before the holdout sample to choose cutover_as_of"
            ),
        }
    hook = getattr(engine, "build_paper_initial_state", None)
    if not callable(hook):
        return {
            "required": True,
            "status": "failed",
            "reason": (
                "stateful_continuation requires BranchEngine.build_paper_initial_state"
            ),
            "cutoverAsOf": cutover_as_of,
        }

    before = _snapshot_tree(state_dir)
    started_at = time.monotonic()
    result = hook(cutover_as_of=cutover_as_of)
    elapsed = time.monotonic() - started_at
    after = _snapshot_tree(state_dir)
    wrote_default_state = False
    if after == before and isinstance(result, dict):
        default_state = state_dir / "strategy" / "paper-state.json"
        default_state.parent.mkdir(parents=True, exist_ok=True)
        default_state.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        after = _snapshot_tree(state_dir)
        wrote_default_state = True
    return {
        "required": True,
        "status": "passed",
        "method": "build_paper_initial_state",
        "cutoverAsOf": cutover_as_of,
        "elapsedSeconds": round(elapsed, 6),
        "stateChanged": after != before,
        "wroteDefaultStateFile": wrote_default_state,
        "result": _json_safe(result),
    }


def _paper_smoke_context(
    candidate: Any,
    *,
    strategy_dir: Path,
    runtime_dir: Path,
    state_dir: Path,
    workspace_dir: Path,
) -> dict[str, Any]:
    dependencies = _load_json_object_if_exists(runtime_dir / "dependencies.json")
    runtime_profile = _load_json_object_if_exists(candidate.branch / "inputs" / "runtime_profile.json")
    requirements = dependencies.get("data_requirements")
    if not isinstance(requirements, dict):
        requirements = {}
    target_asset = _clean(dependencies.get("target") or candidate.ticker).upper()
    target_node = _clean(dependencies.get("target_node")) or f"{target_asset}.price"
    timeframe = _clean(requirements.get("timeframe")) or "1d"
    fields = [
        str(field)
        for field in (requirements.get("fields") if isinstance(requirements.get("fields"), list) else ["close"])
    ]
    selected_inputs = _selected_input_symbols(dependencies.get("selected_inputs"))
    staged_feeds = _stage_paper_smoke_market_feeds(
        dependencies,
        data_dir=workspace_dir / "data",
        target_asset=target_asset,
        selected_inputs=selected_inputs,
    )
    feeds = {
        "primary": _csv_bars_feed(
            name="primary",
            symbol=target_asset,
            timeframe=timeframe,
            fields=fields,
            path=staged_feeds[target_asset]["path"],
        )
    }
    for symbol in selected_inputs:
        feeds[symbol] = _csv_bars_feed(
            name=symbol,
            symbol=symbol,
            timeframe=timeframe,
            fields=fields,
            path=staged_feeds[symbol]["path"],
        )
    requested_start = _clean(dependencies.get("requested_start"))
    return {
        "id": _clean(candidate.branch_id) or "paper_smoke_strategy",
        "asset": target_asset,
        "ticker": target_asset,
        "branch_spec": {
            "target": target_asset,
            "target_asset": target_asset,
            "target_node": target_node,
            "selected_inputs": selected_inputs,
            "data_requirements": requirements,
            "requested_start": requested_start,
        },
        "dependencies": dependencies,
        "_research": {
            "requested_window": {
                "start": requested_start,
                "end": _clean((candidate.edge_result.get("effective_window") or {}).get("end"))
                if isinstance(candidate.edge_result.get("effective_window"), dict)
                else None,
            }
        },
        "_data_contract": {"profile": "daily"},
        "_runtime_paths": {
            "base_strategy": str(strategy_dir),
            "runtime": str(runtime_dir),
            "state": str(state_dir),
            "workspace_dir": str(workspace_dir),
            "package_dir": str(workspace_dir),
            "base_dir": str(workspace_dir),
            "strategy_dir": str(strategy_dir),
            "runtime_dir": str(runtime_dir),
            "state_dir": str(state_dir),
            "output_dir": str(workspace_dir / "output"),
            "tmp_dir": str(workspace_dir / "tmp"),
        },
        "_runtime_profile": {
            "profile": "daily",
            "target": target_asset,
            "target_asset": target_asset,
            "target_node": target_node,
            "decision_event": _clean(runtime_profile.get("decision_event")) or "bar_close",
            "execution_delay_bars": int(runtime_profile.get("execution_delay_bars") or 1),
            "return_basis": _clean(runtime_profile.get("return_basis")) or "close_to_close",
        },
        "_feeds": feeds,
        "_promotion_validation": {
            "feedMode": "prepared_cache",
            "feedSources": {
                symbol: {
                    "path": str(payload["path"]),
                    "sourcePath": str(payload["sourcePath"]),
                }
                for symbol, payload in staged_feeds.items()
            },
        },
    }


def _csv_bars_feed(
    *,
    name: str,
    symbol: str,
    timeframe: str,
    fields: list[str],
    path: Path,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "bars",
        "adapter": "csv",
        "symbol": symbol,
        "timeframe": timeframe,
        "profile": "daily",
        "fields": fields,
        "path": str(path),
    }


def _stage_paper_smoke_market_feeds(
    dependencies: dict[str, Any],
    *,
    data_dir: Path,
    target_asset: str,
    selected_inputs: list[str],
) -> dict[str, dict[str, Path]]:
    cache = dependencies.get("cache")
    results = cache.get("results") if isinstance(cache, dict) else None
    if not isinstance(results, list):
        raise ValueError(
            "paper_run_one smoke requires prepared market cache results in "
            "inputs/dependencies.json; refusing to synthesize feeds from trade-log.csv"
        )

    sources: dict[str, Path] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        if item.get("ok") is False:
            continue
        symbol = _clean(item.get("symbol") or item.get("ticker"))
        data_path = _clean(item.get("data_path") or item.get("path"))
        if not symbol or not data_path:
            continue
        source = Path(data_path)
        if source.is_file():
            sources[_market_symbol_key(symbol)] = source

    required_symbols = list(dict.fromkeys([target_asset, *selected_inputs]))
    missing = [
        symbol
        for symbol in required_symbols
        if _market_symbol_key(symbol) not in sources
    ]
    if missing:
        raise ValueError(
            "paper_run_one smoke missing prepared market data for "
            f"{', '.join(missing)}; validation must use real cache/dependencies feeds"
        )

    data_dir.mkdir(parents=True, exist_ok=True)
    staged: dict[str, dict[str, Path]] = {}
    for symbol in required_symbols:
        source = sources[_market_symbol_key(symbol)]
        _validate_market_feed_csv(source, symbol=symbol)
        path = data_dir / f"{_safe_feed_filename(symbol)}.csv"
        shutil.copy2(source, path)
        staged[symbol] = {"path": path, "sourcePath": source}
    return staged


def _market_symbol_key(symbol: str) -> str:
    value = _clean(symbol)
    if value.endswith(".price"):
        value = value.removesuffix(".price")
    return value.upper()


def _validate_market_feed_csv(path: Path, *, symbol: str) -> None:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            has_row = next(reader, None) is not None
    except OSError as exc:
        raise ValueError(
            f"paper_run_one smoke cannot read prepared feed for {symbol}: {exc}"
        ) from exc
    required = {"timestamp", "close"}
    missing = sorted(required - fields)
    if missing:
        raise ValueError(
            f"paper_run_one smoke prepared feed for {symbol} is missing columns: "
            f"{', '.join(missing)}"
        )
    if not has_row:
        raise ValueError(f"paper_run_one smoke prepared feed for {symbol} is empty")


def _safe_feed_filename(symbol: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", _clean(symbol) or "asset")
    return value.strip("._") or "asset"


def _selected_input_symbols(value: Any) -> list[str]:
    symbols: list[str] = []
    if not isinstance(value, list):
        return symbols
    for item in value:
        if isinstance(item, dict):
            raw = item.get("symbol") or item.get("ticker") or item.get("node_id")
        else:
            raw = item
        text = _clean(raw)
        if text.endswith(".price"):
            text = text.removesuffix(".price")
        if text and text not in symbols:
            symbols.append(text)
    return symbols


def _warm_start_payload(
    comparisons: list[dict[str, Any]],
    *,
    repeated_elapsed: float,
    repeated_state_changed: bool,
) -> dict[str, Any]:
    elapsed = [float(item.get("elapsedSeconds") or 0.0) for item in comparisons]
    slow_count = sum(
        1 for value in elapsed if value > PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS
    )
    max_elapsed = max(elapsed, default=0.0)
    return {
        "method": "tail_distinct_dates_plus_repeated_latest",
        "sampleSize": len(comparisons),
        "distinctDateElapsedSeconds": [round(value, 6) for value in elapsed],
        "maxDistinctDateElapsedSeconds": round(max_elapsed, 6),
        "slowDistinctCallCount": slow_count,
        "slowThresholdSeconds": PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS,
        "distinctDateStateChangedCount": sum(
            1 for item in comparisons if item.get("stateChanged") is True
        ),
        "repeatedSameAsOfElapsedSeconds": round(repeated_elapsed, 6),
        "repeatedSameAsOfStateChanged": repeated_state_changed,
    }
