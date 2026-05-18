"""Session and branch state helpers for strategy discovery."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from abel_invest.narrative_core.contracts.branch_spec import (
    has_explicit_hypothesis,
    load_branch_spec,
    write_branch_spec,
)
from abel_invest.narrative_core.contracts.constants import (
    CONTEXT_GUIDE_FILENAME,
    DATA_MANIFEST_FILENAME,
    DEFAULT_BACKTEST_START,
    DEPENDENCIES_FILENAME,
    EVENTS_HEADER,
    EXECUTION_CONSTRAINTS_FILENAME,
    EXPERIMENT_METADATA_ENV,
    GRAPH_FRONTIER_FILENAME,
    PROBE_SAMPLES_FILENAME,
    READINESS_FILENAME,
    RUNTIME_PROFILE_FILENAME,
)
from abel_invest.narrative_core.io import (
    SessionLock,
    _now,
    append_tsv_row,
    read_tsv_rows,
)
from abel_invest.narrative_core.contracts.paths import (
    branch_state_path,
    context_guide_path,
    data_manifest_path,
    dependencies_path,
    execution_constraints_path,
    probe_samples_path,
    runtime_profile_path,
    session_state_path,
)
from abel_invest.narrative_core.readiness import (
    build_readiness_warning,
    format_data_readiness_summary,
    readiness_coverage_hint_lines,
)
from abel_invest.narrative_core.contracts.templates import ENGINE_TEMPLATE


def current_experiment_metadata() -> dict[str, str]:
    return {
        key: str(os.environ.get(env_name) or "").strip()
        for key, env_name in EXPERIMENT_METADATA_ENV.items()
    }


def session_experiment_metadata(
    branches: list[dict],
    rows: list[dict[str, object]],
) -> dict[str, str]:
    del branches
    for row in reversed(rows):
        metadata = context_experiment_metadata(row)
        if any(metadata.values()):
            return metadata
    return {key: "" for key in EXPERIMENT_METADATA_ENV}


def context_experiment_metadata(payload: dict) -> dict[str, str]:
    empty = {key: "" for key in EXPERIMENT_METADATA_ENV}
    experiment = payload.get("experiment") if isinstance(payload, dict) else None
    if not isinstance(experiment, dict):
        return empty
    return {
        key: str(experiment.get(key) or "").strip()
        for key in EXPERIMENT_METADATA_ENV
    }


def round_experiment_metadata(branch_dir: Path, round_id: str) -> dict[str, str]:
    empty = {key: "" for key in EXPERIMENT_METADATA_ENV}
    if not round_id:
        return empty
    note = read_round_note(branch_dir, round_id)
    context_path_raw = note.get("context_path", "")
    if not context_path_raw:
        return empty
    session = branch_dir.parent.parent
    context_path = session / Path(context_path_raw)
    if not context_path.exists():
        return empty
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    experiment = payload.get("experiment")
    if not isinstance(experiment, dict):
        return empty
    return {
        key: str(experiment.get(key) or "").strip()
        for key in EXPERIMENT_METADATA_ENV
    }


def branch_progression(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "`No metric progression yet.`"
    lines = []
    previous = None
    for row in rows:
        lo_adj = float(row.get("lo_adj") or 0)
        sharpe = float(row.get("sharpe") or 0)
        pnl = float(row.get("pnl") or 0)
        delta = ""
        if previous is not None:
            delta = (
                f" | dLo {lo_adj - previous['lo_adj']:+.3f}"
                f" | dSharpe {sharpe - previous['sharpe']:+.3f}"
                f" | dPnL {pnl - previous['pnl']:+.1f}%"
            )
        lines.append(
            f"1. `{row.get('round_id', '?')}` {row.get('decision', '?')} | Lo {lo_adj:.3f} | Sharpe {sharpe:.3f} | PnL {pnl:.1f}%{delta}"
        )
        previous = {"lo_adj": lo_adj, "sharpe": sharpe, "pnl": pnl}
    return "\n".join(lines)


def build_branch_snapshot_line(branch: dict) -> str:
    rows = branch["rows"]
    latest = rows[-1]
    first = rows[0]
    note = read_round_note(branch["branch_dir"], latest.get("round_id", ""))
    reason = (
        current_branch_hypothesis(branch["branch_dir"], rows)
        or note.get("failures")
        or latest.get("description", "")
    )
    return (
        f"1. `{branch['branch_id']}` -> `{latest.get('decision', 'pending')}` after {len(rows)} round(s). "
        f"Why: `{reason or 'not recorded'}`. Trend: Lo {float(first.get('lo_adj') or 0):.3f} -> {float(latest.get('lo_adj') or 0):.3f}, "
        f"Sharpe {float(first.get('sharpe') or 0):.3f} -> {float(latest.get('sharpe') or 0):.3f}, "
        f"PnL {float(first.get('pnl') or 0):.1f}% -> {float(latest.get('pnl') or 0):.1f}%, "
        f"signature `{note.get('failure_signature', 'unknown')}`, active `{note.get('signal_activity', 'n/a')}`."
    )


def latest_recorded_hypothesis(branch: dict) -> str:
    for row in reversed(branch["rows"]):
        note = read_round_note(branch["branch_dir"], row.get("round_id", ""))
        hypothesis = (note.get("hypothesis") or "").strip()
        if has_explicit_hypothesis(hypothesis):
            return hypothesis
    return ""


def format_risks(risks: str) -> str:
    cleaned = (risks or "").strip()
    if not cleaned or cleaned == "none":
        return "- no acute validation failures recorded yet"
    return "\n".join(f"- {part.strip()}" for part in cleaned.split(";") if part.strip())


def load_branches(session: Path) -> list[dict]:
    branches_dir = session / "branches"
    branches = []
    if not branches_dir.exists():
        return branches
    discovery = load_discovery(session)
    for branch_dir in sorted(
        child for child in branches_dir.iterdir() if child.is_dir()
    ):
        branches.append(
            {
                "branch_id": branch_dir.name,
                "branch_dir": branch_dir,
                "ticker": discovery.get("ticker", session.parent.name.upper()),
                "rows": read_tsv_rows(branch_dir / "results.tsv"),
            }
        )
    return branches


def load_discovery(session: Path) -> dict:
    from abel_invest.narrative_core.evidence.graph_frontier import (
        graph_frontier_path,
        graph_frontier_to_discovery,
        load_graph_frontier,
    )

    if graph_frontier_path(session).exists():
        return graph_frontier_to_discovery(load_graph_frontier(session))
    path = session / "discovery.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "ticker": session.parent.name.upper(),
        "source": "unknown",
        "parents": [],
        "blanket_new": [],
        "children": [],
        "K_discovery": 0,
        "backtest": {"start": DEFAULT_BACKTEST_START},
    }


def load_readiness(session: Path) -> dict:
    path = session / READINESS_FILENAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def branch_inputs_ready(branch: Path) -> bool:
    required = (
        dependencies_path(branch),
        runtime_profile_path(branch),
        execution_constraints_path(branch),
        data_manifest_path(branch),
        context_guide_path(branch),
        probe_samples_path(branch),
    )
    return all(path.exists() for path in required)


def load_branch_state(branch: Path) -> dict:
    path = branch_state_path(branch)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_branch_state(branch: Path, payload: dict) -> None:
    branch_state_path(branch).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_session_state(session: Path) -> dict:
    path = session_state_path(session)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_session_state(session: Path, payload: dict) -> None:
    session_state_path(session).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def readiness_warning_fingerprint(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    target_boundary = report.get("target_boundary") or {}
    coverage_hints = report.get("coverage_hints") or {}
    payload = {
        "requested_start": (report.get("requested_window") or {}).get("start"),
        "usable_count": summary.get("usable_count"),
        "start_covered_count": summary.get("start_covered_count"),
        "classification": target_boundary.get("classification"),
        "observed_first_timestamp": target_boundary.get("observed_first_timestamp"),
        "target_safe_start": coverage_hints.get("target_safe_start"),
        "dense_overlap_hint_start": coverage_hints.get("dense_overlap_hint_start"),
    }
    return json.dumps(payload, sort_keys=True)


def should_emit_readiness_warning(session: Path, readiness: dict) -> bool:
    warning = build_readiness_warning(readiness)
    if not warning:
        return False
    fingerprint = readiness_warning_fingerprint(readiness)
    if not fingerprint:
        return True
    state = load_session_state(session)
    if state.get("last_readiness_warning_fingerprint") == fingerprint:
        return False
    state["last_readiness_warning_fingerprint"] = fingerprint
    write_session_state(session, state)
    return True


def resolve_backtest_start_request(
    *,
    session: Path,
    explicit_date: str | None,
    use_target_safe: bool,
    use_coverage_hint: bool,
) -> tuple[str, str]:
    if explicit_date:
        return explicit_date, "explicit_date"
    report = load_readiness(session)
    coverage_hints = report.get("coverage_hints") or {}
    if use_target_safe:
        target_safe = coverage_hints.get("target_safe_start")
        if not target_safe:
            raise RuntimeError(
                "No target-safe readiness hint is available for this session."
            )
        return str(target_safe), "target_safe_hint"
    if use_coverage_hint:
        coverage_hint = coverage_hints.get("dense_overlap_hint_start")
        if not coverage_hint:
            raise RuntimeError(
                "No dense-overlap readiness hint is available for this session."
            )
        return str(coverage_hint), "coverage_hint"
    raise RuntimeError("A backtest start selector is required.")


def update_backtest_start(
    *,
    session: Path,
    backtest_start: str,
    source: str,
) -> tuple[dict, dict]:
    from abel_invest.narrative_core.evidence.graph_frontier import (
        graph_frontier_to_discovery,
        load_graph_frontier,
        write_graph_frontier,
    )
    from abel_invest.narrative_core.rendering.session_rendering import render_session
    from abel_invest.narrative_core.session_lifecycle import refresh_data_readiness, write_readiness

    frontier = load_graph_frontier(session)
    updated_frontier = dict(frontier)
    updated_frontier["requested_window"] = {"start": backtest_start, "end": None}
    updated_frontier["updated_at"] = _now()
    updated_discovery = graph_frontier_to_discovery(updated_frontier)
    readiness = refresh_data_readiness(
        session=session,
        discovery_data=updated_discovery,
        backtest_start=backtest_start,
    )
    with SessionLock(session):
        write_graph_frontier(session, updated_frontier)
        readiness_path = session / READINESS_FILENAME
        if readiness:
            write_readiness(session, readiness)
        else:
            readiness_path.unlink(missing_ok=True)
        state = load_session_state(session)
        state.pop("last_readiness_warning_fingerprint", None)
        write_session_state(session, state)
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "backtest_start_updated",
                "branch_id": "",
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": (
                    f"Updated session backtest start to {backtest_start} via {source}"
                ),
                "artifact_path": GRAPH_FRONTIER_FILENAME,
            },
        )
        if readiness:
            append_tsv_row(
                session / "events.tsv",
                EVENTS_HEADER,
                {
                    "timestamp": _now(),
                    "event": "data_readiness_recorded",
                    "branch_id": "",
                    "round_id": "",
                    "mode": "",
                    "verdict": "",
                    "decision": "",
                    "description": (
                        "Refreshed driver data readiness: "
                        f"{format_data_readiness_summary(readiness)}"
                    ),
                    "artifact_path": READINESS_FILENAME,
                },
            )
        render_session(session)
    return updated_discovery, readiness or {}


def current_branch_hypothesis(branch_dir: Path, rows: list[dict[str, str]] | None = None) -> str:
    branch_spec = load_branch_spec(branch_dir)
    spec_hypothesis = str(branch_spec.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(spec_hypothesis):
        return spec_hypothesis
    state = load_branch_state(branch_dir)
    hypothesis = str(state.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(hypothesis):
        return hypothesis
    if rows is None:
        rows = read_tsv_rows(branch_dir / "results.tsv")
    return latest_recorded_hypothesis({"branch_dir": branch_dir, "rows": rows})


def should_emit_missing_hypothesis_warning(branch: Path) -> bool:
    if has_explicit_hypothesis(current_branch_hypothesis(branch)):
        return False
    state = load_branch_state(branch)
    if state.get("missing_hypothesis_warning_emitted"):
        return False
    state["missing_hypothesis_warning_emitted"] = True
    write_branch_state(branch, state)
    return True


def persist_branch_hypothesis(branch: Path, hypothesis: str, *, source: str) -> None:
    branch_spec = load_branch_spec(branch)
    if branch_spec:
        branch_spec["hypothesis"] = hypothesis
        write_branch_spec(branch, branch_spec)
    state = load_branch_state(branch)
    state["hypothesis"] = hypothesis
    state["hypothesis_source"] = source
    state["hypothesis_updated_at"] = _now()
    state["missing_hypothesis_warning_emitted"] = False
    write_branch_state(branch, state)


def resolve_branch_hypothesis(
    branch: Path,
    rows: list[dict[str, str]],
    explicit_hypothesis: str,
) -> tuple[str, str]:
    hypothesis = str(explicit_hypothesis or "").strip()
    if has_explicit_hypothesis(hypothesis):
        return hypothesis, "round_argument"
    branch_spec = load_branch_spec(branch)
    spec_hypothesis = str(branch_spec.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(spec_hypothesis):
        return spec_hypothesis, "branch_yaml"
    state = load_branch_state(branch)
    stored = str(state.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(stored):
        return stored, "branch_state"
    recorded = latest_recorded_hypothesis({"branch_dir": branch, "rows": rows})
    if has_explicit_hypothesis(recorded):
        return recorded, "recorded_round"
    return "", "missing"


def latest_debug_snapshot(branch_dir: Path) -> dict[str, str]:
    state = load_branch_state(branch_dir)
    payload = state.get("last_debug")
    return dict(payload) if isinstance(payload, dict) else {}


def persist_debug_snapshot(branch: Path, payload: dict[str, str]) -> None:
    state = load_branch_state(branch)
    state["last_debug"] = payload
    write_branch_state(branch, state)


def build_debug_snapshot(
    *,
    completed: subprocess.CompletedProcess[str],
    session: Path,
    context_path: Path,
    debug_result_path: Path,
    backtest_start: str,
) -> dict[str, str]:
    result: dict[str, object] = {}
    if debug_result_path.exists():
        try:
            parsed = json.loads(debug_result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            result = parsed
    diagnostics = result.get("diagnostics") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    signal = diagnostics.get("signal") or {}
    if not isinstance(signal, dict):
        signal = {}
    failures = [
        str(item).strip()
        for item in (result.get("failures") or [])
        if str(item).strip()
    ]
    hints = [
        str(item).strip()
        for item in (diagnostics.get("hints") or [])
        if str(item).strip()
    ]
    fallback_error = (
        completed.stderr.strip()
        or completed.stdout.strip()
        or "Debug preflight did not produce a structured result."
    )
    summary = failures[0] if failures else fallback_error.splitlines()[-1]
    next_step = (
        hints[0]
        if hints
        else "Fix the semantic blocker in engine.py, then rerun debug-branch with the workspace command prefix."
    )
    return {
        "updated_at": _now(),
        "returncode": str(completed.returncode),
        "verdict": str(result.get("verdict") or ("PASS" if completed.returncode == 0 else "ERROR")),
        "summary": summary,
        "failures": "; ".join(failures) or summary,
        "failure_signature": str(diagnostics.get("failure_signature") or "debug_runtime_check"),
        "runtime_stage": str(diagnostics.get("runtime_stage") or "debug_evaluate"),
        "signal_activity": (
            f"{int(signal.get('active_days', 0) or 0)} / {int(signal.get('total_days', 0) or 0)}"
        ),
        "diagnostic_hints": "; ".join(hints) or "none",
        "next_step": next_step,
        "context_mode": "injected",
        "context_path": str(context_path.relative_to(session)),
        "result_path": str(debug_result_path.relative_to(session)) if debug_result_path.exists() else "not recorded",
        "handoff_path": "not recorded",
        "report_path": "not recorded",
        "requested_start": backtest_start,
    }


def render_default_engine_template(discovery: dict, readiness: dict, session: Path) -> str:
    return ENGINE_TEMPLATE.format(
        ticker=discovery.get("ticker", session.parent.name.upper()),
        readiness_warning=build_readiness_warning(readiness) or "none",
        coverage_hints_text=", ".join(readiness_coverage_hint_lines(readiness)) or "none",
    )


def branch_uses_default_scaffold(
    branch: Path,
    discovery: dict,
    readiness: dict,
    session: Path,
) -> bool:
    engine = branch / "engine.py"
    if not engine.exists():
        return False
    return (
        engine.read_text(encoding="utf-8")
        == render_default_engine_template(discovery, readiness, session)
    )


def read_round_note(branch_dir: Path, round_id: str) -> dict[str, str]:
    if not round_id:
        return {}
    path = branch_dir / "rounds" / f"{round_id}.md"
    if not path.exists():
        return {}
    fields: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        for key in (
            "trigger",
            "hypothesis",
            "expected_signal",
            "change_summary",
            "changed_dimensions",
            "time_spent_min",
            "failures",
            "failure_signature",
            "runtime_stage",
            "signal_activity",
            "diagnostic_hints",
            "summary",
            "next_step",
            "context_mode",
            "context_path",
            "result_path",
            "report_path",
            "handoff_path",
        ):
            prefix = f"- {key}: `"
            if line.startswith(prefix) and line.endswith("`"):
                fields[key] = line[len(prefix) : -1]
    return fields
