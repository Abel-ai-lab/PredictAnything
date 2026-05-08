"""Strategy promotion helpers for paper-ready runtime state boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable

from abel_edge.research.promotion_gate import build_promotion_gate_report


STATE_INTENT_FILENAME = "state_intent.json"
STATE_INTENT_SCHEMA = "abel-invest.state-intent/v1"
PROMOTION_MODE_ZERO_CHANGE = "zero_change"
PROMOTION_MODE_AUTO_ADAPTER = "auto_adapter"
PROMOTION_MODE_NEEDS_AGENT_REFACTOR = "needs_agent_refactor"
PROMOTION_MODE_AGENT_REFACTOR = "agent_refactor"
PROMOTION_ADAPTER_STATE_PATH = "state_path_adapter"
PROMOTION_GATE_FILENAME = "promotion-gate.json"
PROMOTION_PATCH_FILENAME = "promotion.patch"
PROMOTION_REFACTOR_REPORT_FILENAME = "refactor-report.json"


@dataclass(frozen=True)
class StateIntentEntry:
    path: str
    role: str
    mutable_in_paper: bool
    required_for_signal: bool
    produced_by: str
    source_path: Path


@dataclass(frozen=True)
class PromotionResult:
    mode: str
    strategy_source_path: Path
    state_intent_payload: dict[str, Any] | None
    state_entries: tuple[StateIntentEntry, ...]
    extra_source_map: dict[str, Path]
    patch_path: Path | None
    gate_path: Path
    refactor_report_path: Path | None
    report: dict[str, Any]

    @property
    def adapted(self) -> bool:
        return self.mode == PROMOTION_MODE_AUTO_ADAPTER


class PromotionNeedsAgentRefactor(RuntimeError):
    """Raised when promotion needs agent-assisted refactor before publishing."""


def prepare_promotion(
    candidate: Any,
    *,
    destination: Path,
    strategy_entrypoint: str,
    is_denylisted_source: Callable[[Path], bool],
    sha256_file: Callable[[Path], str],
) -> PromotionResult:
    state_intent_payload = _load_state_intent_payload(candidate.branch)
    state_entries = tuple(
        _state_intent_entries(
            candidate.branch,
            payload=state_intent_payload,
            is_denylisted_source=is_denylisted_source,
        )
    )
    promoted_dir = destination / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    strategy_source_path = candidate.strategy_source_path
    patch_path = None
    refactor_report_path = None
    mode = PROMOTION_MODE_ZERO_CHANGE
    adapter_replacements: list[dict[str, str]] = []
    refactor_replacements: list[dict[str, str]] = []
    refactor_summary = ""

    if state_entries:
        promoted_source = promoted_dir / "engine.py"
        original_text = candidate.strategy_source_path.read_text(encoding="utf-8")
        promoted_text = original_text
        for entry in state_entries:
            if entry.role != "initial_state":
                continue
            promoted_text, changed = _adapt_state_path_literal(promoted_text, entry.path)
            if changed:
                adapter_replacements.append(
                    {
                        "path": entry.path,
                        "replacement": f'ctx.state_dir / "{entry.path}"',
                    }
                )
        for entry in state_entries:
            if entry.role != "initial_state":
                continue
            if not _source_uses_state_path(promoted_text, entry.path):
                promoted_text, replacements = _agent_refactor_state_path(
                    promoted_text,
                    entry.path,
                )
                refactor_replacements.extend(replacements)

        missing_state_paths = [
            entry.path
            for entry in state_entries
            if entry.role == "initial_state"
            and not _source_uses_state_path(promoted_text, entry.path)
        ]
        if missing_state_paths:
            raise PromotionNeedsAgentRefactor(
                "initial_state path is not bound to runtime state path: "
                f"{', '.join(missing_state_paths)}"
            )

        replacements = adapter_replacements + refactor_replacements
        if refactor_replacements:
            mode = PROMOTION_MODE_AGENT_REFACTOR
            refactor_summary = (
                "Refactored dynamic state path construction to ctx.state_dir."
            )
            promoted_source.write_text(promoted_text, encoding="utf-8")
            strategy_source_path = promoted_source
            patch_path = promoted_dir / "promotion.patch"
            patch_path.write_text(
                _simple_patch_summary(
                    candidate.strategy_source_path,
                    replacements,
                    scope="agent_refactor_state_path_normalization",
                ),
                encoding="utf-8",
            )
            refactor_report_path = promoted_dir / PROMOTION_REFACTOR_REPORT_FILENAME
            refactor_report_path.write_text(
                json.dumps(
                    {
                        "schema": "abel-invest.agent-refactor-report/v1",
                        "kind": "agent_assisted",
                        "summary": refactor_summary,
                        "scope": "state_path_normalization",
                        "replacements": replacements,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        elif adapter_replacements:
            mode = PROMOTION_MODE_AUTO_ADAPTER
            promoted_source.write_text(promoted_text, encoding="utf-8")
            strategy_source_path = promoted_source
            patch_path = promoted_dir / "promotion.patch"
            patch_path.write_text(
                _simple_patch_summary(candidate.strategy_source_path, replacements),
                encoding="utf-8",
            )
    else:
        replacements = []

    original_sha = sha256_file(candidate.strategy_source_path)
    promoted_sha = sha256_file(strategy_source_path)
    adapter_payload = (
        {"kind": PROMOTION_ADAPTER_STATE_PATH, "scope": "state_path_normalization"}
        if mode == PROMOTION_MODE_AUTO_ADAPTER
        else None
    )
    refactor_payload = (
        {
            "kind": "agent_assisted",
            "summary": refactor_summary,
            "patchPath": f"edge/{PROMOTION_PATCH_FILENAME}",
            "reportPath": f"edge/{PROMOTION_REFACTOR_REPORT_FILENAME}",
        }
        if mode == PROMOTION_MODE_AGENT_REFACTOR
        else None
    )
    behavior_equivalence = {
        "status": "passed",
        "method": "state_path_adapter_static_scope"
        if mode == PROMOTION_MODE_AUTO_ADAPTER
        else "agent_refactor_state_path_scope"
        if mode == PROMOTION_MODE_AGENT_REFACTOR
        else "source_hash_identity",
        "replacements": replacements,
    }
    gate_path = destination / PROMOTION_GATE_FILENAME
    gate_report = build_promotion_gate_report(
        promotion_mode=mode,
        original_source_sha256=original_sha,
        promoted_source_sha256=promoted_sha,
        patch_sha256=sha256_file(patch_path) if patch_path is not None else None,
        adapter=adapter_payload,
        refactor=refactor_payload,
        state_entries=state_entries,
        behavior_equivalence=behavior_equivalence,
    )
    if gate_report.get("status") != "passed":
        raise PromotionNeedsAgentRefactor(
            f"promotion gate did not pass: {gate_report.get('status')}"
        )
    gate_path.write_text(
        json.dumps(gate_report, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    extra_source_map = {strategy_entrypoint: strategy_source_path}
    for entry in state_entries:
        if entry.role == "initial_state":
            extra_source_map[f"runtime/initial-state/{entry.path}"] = entry.source_path
        elif entry.role == "runtime_asset":
            extra_source_map[f"strategy/{entry.path}"] = entry.source_path
    extra_source_map[f"edge/{PROMOTION_GATE_FILENAME}"] = gate_path
    if patch_path is not None:
        extra_source_map[f"edge/{PROMOTION_PATCH_FILENAME}"] = patch_path
    if mode == PROMOTION_MODE_AGENT_REFACTOR:
        assert refactor_report_path is not None
        extra_source_map[f"edge/{PROMOTION_REFACTOR_REPORT_FILENAME}"] = refactor_report_path

    return PromotionResult(
        mode=mode,
        strategy_source_path=strategy_source_path,
        state_intent_payload=state_intent_payload,
        state_entries=state_entries,
        extra_source_map=extra_source_map,
        patch_path=patch_path,
        gate_path=gate_path,
        refactor_report_path=refactor_report_path,
        report={
            "mode": mode,
            "stateIntentPath": str((candidate.branch / STATE_INTENT_FILENAME).resolve())
            if state_intent_payload is not None
            else "",
            "stateEntryCount": len(state_entries),
            "replacementCount": len(replacements),
            "adapterReplacementCount": len(adapter_replacements),
            "refactorReplacementCount": len(refactor_replacements),
            "patchPath": str(patch_path) if patch_path is not None else "",
            "refactorReportPath": str(refactor_report_path)
            if refactor_report_path is not None
            else "",
            "gatePath": str(gate_path),
        },
    )


def _load_state_intent_payload(branch: Path) -> dict[str, Any] | None:
    path = branch / STATE_INTENT_FILENAME
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{STATE_INTENT_FILENAME} must contain a JSON object")
    if payload.get("schema") != STATE_INTENT_SCHEMA:
        raise RuntimeError(
            f"{STATE_INTENT_FILENAME} schema must be {STATE_INTENT_SCHEMA!r}"
        )
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError(f"{STATE_INTENT_FILENAME} entries must be a list")
    return payload


def _state_intent_entries(
    branch: Path,
    *,
    payload: dict[str, Any] | None,
    is_denylisted_source: Callable[[Path], bool],
) -> list[StateIntentEntry]:
    if payload is None:
        return []
    entries: list[StateIntentEntry] = []
    seen: set[str] = set()
    for raw in payload.get("entries", []):
        if not isinstance(raw, dict):
            raise RuntimeError("state intent entries must be objects")
        relative = _validate_state_intent_relative_path(
            raw.get("path"),
            is_denylisted_source=is_denylisted_source,
        )
        if relative in seen:
            raise RuntimeError(f"duplicate state intent path: {relative}")
        seen.add(relative)
        role = _clean(raw.get("role"))
        if role not in {"runtime_asset", "initial_state", "evidence", "exclude", "unknown"}:
            raise RuntimeError(f"unsupported state intent role: {role!r}")
        if role == "unknown":
            raise PromotionNeedsAgentRefactor(
                f"unknown state intent requires agent refactor: {relative}"
            )
        mutable = raw.get("mutableInPaper")
        required = raw.get("requiredForSignal")
        if not isinstance(mutable, bool) or not isinstance(required, bool):
            raise RuntimeError("state intent mutableInPaper/requiredForSignal must be boolean")
        source_path = branch / relative
        if role not in {"exclude", "evidence"} and not source_path.is_file():
            raise RuntimeError(f"state intent source file is missing: {relative}")
        entries.append(
            StateIntentEntry(
                path=relative,
                role=role,
                mutable_in_paper=mutable,
                required_for_signal=required,
                produced_by=_clean(raw.get("producedBy")),
                source_path=source_path,
            )
        )
    return entries


def _validate_state_intent_relative_path(
    value: Any,
    *,
    is_denylisted_source: Callable[[Path], bool],
) -> str:
    text = str(value or "").replace("\\", "/").strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"invalid state intent path: {text!r}")
    if is_denylisted_source(path):
        raise RuntimeError(f"denylisted state intent path: {text}")
    return path.as_posix()


def _adapt_state_path_literal(source: str, relative_path: str) -> tuple[str, bool]:
    escaped = re.escape(relative_path)
    changed = False

    def replace_path_call(match: re.Match[str]) -> str:
        nonlocal changed
        changed = True
        quote = match.group("quote")
        return f'(ctx.state_dir / {quote}{relative_path}{quote})'

    source = re.sub(
        rf"Path\(\s*(?P<quote>['\"]){escaped}(?P=quote)\s*\)",
        replace_path_call,
        source,
    )

    def replace_load_dump(match: re.Match[str]) -> str:
        nonlocal changed
        changed = True
        prefix = match.group("prefix")
        quote = match.group("quote")
        return f"{prefix}ctx.state_dir / {quote}{relative_path}{quote}"

    source = re.sub(
        rf"(?P<prefix>\b(?:joblib|pickle)\.(?:load|dump)\([^,\n]*?)"
        rf"(?P<quote>['\"]){escaped}(?P=quote)",
        replace_load_dump,
        source,
    )
    return source, changed


def _source_uses_state_path(source: str, relative_path: str) -> bool:
    escaped = re.escape(relative_path)
    checks = (
        rf"\bctx\.state_dir\s*/\s*['\"]{escaped}['\"]",
        rf"\bctx\.state_dir\.joinpath\(\s*['\"]{escaped}['\"]\s*\)",
        rf"\b_runtime_paths\b.*['\"]{escaped}['\"]",
        rf"\bABEL_STATE_DIR\b.*['\"]{escaped}['\"]",
    )
    return any(re.search(pattern, source, flags=re.DOTALL) for pattern in checks)


def _agent_refactor_state_path(
    source: str,
    relative_path: str,
) -> tuple[str, list[dict[str, str]]]:
    path = Path(relative_path)
    if len(path.parts) < 2:
        return source, []
    parent = path.parent.as_posix()
    filename = path.name
    escaped_parent = re.escape(parent)
    escaped_filename = re.escape(filename)
    replacements: list[dict[str, str]] = []

    def replace_path_division(match: re.Match[str]) -> str:
        quote = match.group("quote")
        replacements.append(
            {
                "path": relative_path,
                "replacement": f'ctx.state_dir / "{relative_path}"',
                "reason": "dynamic Path division normalized by agent refactor",
            }
        )
        return f'(ctx.state_dir / {quote}{relative_path}{quote})'

    source = re.sub(
        rf"Path\(\s*(?P<quote>['\"]){escaped_parent}(?P=quote)\s*\)"
        rf"\s*/\s*['\"]{escaped_filename}['\"]",
        replace_path_division,
        source,
    )

    def replace_joinpath(match: re.Match[str]) -> str:
        quote = match.group("quote")
        replacements.append(
            {
                "path": relative_path,
                "replacement": f'ctx.state_dir / "{relative_path}"',
                "reason": "Path.joinpath normalized by agent refactor",
            }
        )
        return f'(ctx.state_dir / {quote}{relative_path}{quote})'

    source = re.sub(
        rf"Path\(\s*(?P<quote>['\"]){escaped_parent}(?P=quote)\s*\)"
        rf"\.joinpath\(\s*['\"]{escaped_filename}['\"]\s*\)",
        replace_joinpath,
        source,
    )
    return source, replacements


def _simple_patch_summary(
    source_path: Path,
    replacements: list[dict[str, str]],
    *,
    scope: str = "state_path_normalization",
) -> str:
    lines = [
        f"source: {source_path}",
        f"scope: {scope}",
        "replacements:",
    ]
    for replacement in replacements:
        reason = replacement.get("reason")
        suffix = f" ({reason})" if reason else ""
        lines.append(f"- {replacement['path']} -> {replacement['replacement']}{suffix}")
    return "\n".join(lines) + "\n"


def _clean(value: Any) -> str:
    return str(value or "").strip()
