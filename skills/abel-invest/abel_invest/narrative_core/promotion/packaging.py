"""Packaged file handling for strategy promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .constants import PROMOTION_INITIAL_STATE_ORACLE_PHRASES
from .models import PromotionHostedPaperContractRequired, PromotionPackagedFile
from .utils import _clean

def _report_packaged_files(
    report: dict[str, Any],
    *,
    branch: Path,
    is_denylisted_source: Callable[[Path], bool],
) -> list[PromotionPackagedFile]:
    paths = report.get("paths")
    packaged_groups: list[tuple[Any, str | None]] = []
    if isinstance(paths, dict):
        packaged_groups.append((paths.get("packagedFiles") or [], None))
        packaged_groups.append((paths.get("initialStateFiles") or [], "initial_state"))
    else:
        packaged_groups.append(([], None))
    if isinstance(report.get("packagedFiles"), list):
        packaged_groups.append((report.get("packagedFiles") or [], None))

    packaged: list[PromotionPackagedFile] = []
    seen: set[str] = set()
    for raw_files, forced_role in packaged_groups:
        if not isinstance(raw_files, list):
            raise PromotionHostedPaperContractRequired(
                "paper contract report paths packaged file fields must be lists"
            )
        for raw in raw_files:
            if not isinstance(raw, dict):
                raise PromotionHostedPaperContractRequired("packaged file entries must be objects")
            artifact_path = _normalize_report_packaged_artifact_path(
                raw.get("artifactPath") or raw.get("path"),
                forced_role=forced_role,
            )
            if artifact_path in seen:
                raise PromotionHostedPaperContractRequired(
                    f"duplicate packaged artifact path: {artifact_path}"
                )
            seen.add(artifact_path)
            role = _packaged_file_role(artifact_path)
            _validate_packaged_artifact_path(
                artifact_path,
                role=role,
                is_denylisted_source=is_denylisted_source,
            )
            source_path = _resolve_report_source_path(raw, branch=branch, artifact_path=artifact_path)
            if not source_path.is_file():
                raise PromotionHostedPaperContractRequired(
                    f"packaged source file is missing for {artifact_path}: {source_path}"
                )
            packaged.append(
                PromotionPackagedFile(
                    artifact_path=artifact_path,
                    source_path=source_path,
                    purpose=_clean(raw.get("purpose")),
                    role=role,
                )
            )
    _validate_packaged_source_roles(packaged)
    return packaged


def _validate_packaged_source_roles(packaged: list[PromotionPackagedFile]) -> None:
    roles_by_source: dict[Path, set[str]] = {}
    for item in packaged:
        roles_by_source.setdefault(item.source_path.resolve(), set()).add(item.role)
    duplicated = [
        source
        for source, roles in roles_by_source.items()
        if "base_asset" in roles and "initial_state" in roles
    ]
    if duplicated:
        sample = ", ".join(str(path) for path in duplicated[:3])
        raise PromotionHostedPaperContractRequired(
            "the same source file cannot be packaged as both immutable strategy "
            f"asset and mutable initial state seed: {sample}"
        )


def _validate_packaged_research_evidence_sources(
    packaged: tuple[PromotionPackagedFile, ...],
    *,
    branch: Path,
    destination: Path | None = None,
    report: dict[str, Any],
) -> None:
    paper_signal = report.get("paperSignal")
    incremental_ready = (
        isinstance(paper_signal, dict) and paper_signal.get("incrementalReady") is True
    )
    if not incremental_ready:
        return

    evidence_assets = [
        item
        for item in packaged
        if item.role == "base_asset"
        and _is_generated_live_asset_source(
            item.source_path,
            branch=branch,
            destination=destination,
        )
    ]
    if not evidence_assets:
        _validate_initial_state_not_oracle_answers(packaged)
        return
    sample = _packaged_file_sample(evidence_assets)
    raise PromotionHostedPaperContractRequired(
        "generated research evidence or export output cannot be packaged as a live "
        "strategy asset "
        f"while paperSignal.incrementalReady=true: {sample}. Package the original "
        "external dependency instead, or use the fallback path only "
        "when attemptPolicy allows it."
    )


def _validate_initial_state_not_oracle_answers(
    packaged: tuple[PromotionPackagedFile, ...],
) -> None:
    contaminated = [
        item
        for item in packaged
        if item.role == "initial_state"
        and _initial_state_looks_like_oracle_answers(item.source_path)
    ]
    if not contaminated:
        return
    sample = _packaged_file_sample(contaminated)
    raise PromotionHostedPaperContractRequired(
        "validation oracle answers cannot be packaged as mutable startup state "
        f"while paperSignal.incrementalReady=true: {sample}. Initial state must be "
        "strategy-owned cutover state such as model/cache/cursor/retrain metadata, "
        "not selected-round tail expected positions."
    )


def _packaged_file_sample(items: list[PromotionPackagedFile]) -> str:
    return ", ".join(
        f"{item.source_path} -> {item.artifact_path}" for item in items[:3]
    )


def _initial_state_looks_like_oracle_answers(source_path: Path) -> bool:
    try:
        text = source_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    lowered = text[:1_000_000].lower()
    return any(phrase in lowered for phrase in PROMOTION_INITIAL_STATE_ORACLE_PHRASES)


def _is_generated_live_asset_source(
    source_path: Path,
    *,
    branch: Path,
    destination: Path | None = None,
) -> bool:
    if _is_research_evidence_source(source_path, branch=branch):
        return True
    if destination is not None and _is_export_evidence_source(
        source_path,
        destination=destination,
    ):
        return True
    resolved = source_path.resolve()
    text = resolved.as_posix().lower()
    parts = {part.lower() for part in resolved.parts}
    if parts & {"promoted", "promotions", "promotion-replay", "strategy_artifacts"}:
        return True
    if "tmp" in parts and ("hosted-paper" in text or "promotion" in text):
        return True
    if "temp" in parts and ("hosted-paper" in text or "promotion" in text):
        return True
    return False


def _is_export_evidence_source(source_path: Path, *, destination: Path) -> bool:
    try:
        relative = source_path.resolve().relative_to(destination.resolve())
    except ValueError:
        return False
    if not relative.parts:
        return False
    return True


def _is_research_evidence_source(source_path: Path, *, branch: Path) -> bool:
    try:
        relative = source_path.resolve().relative_to(branch.resolve())
    except ValueError:
        return False
    if not relative.parts:
        return False
    if relative.parts[0] in {"outputs", "promotions", "strategy_artifacts"}:
        return True
    return relative.name.lower() in {
        "edge-result.json",
        "edge-validation.md",
        "promotion-gate.json",
        "promotion-tail-trace.json",
        "trade-log.csv",
    }


def _normalize_report_packaged_artifact_path(value: Any, *, forced_role: str | None) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if forced_role == "initial_state" and text and not text.startswith("runtime/initial-state/"):
        text = f"runtime/initial-state/{text.removeprefix('state/')}"
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise PromotionHostedPaperContractRequired(f"invalid packaged artifact path: {text!r}")
    return path.as_posix()


def _packaged_file_role(artifact_path: str) -> str:
    if artifact_path.startswith("runtime/initial-state/"):
        return "initial_state"
    if artifact_path.startswith("strategy/"):
        return "base_asset"
    raise PromotionHostedPaperContractRequired(
        "packaged files must use strategy/** or runtime/initial-state/** artifact paths: "
        f"{artifact_path}"
    )


def _validate_packaged_artifact_path(
    artifact_path: str,
    *,
    role: str,
    is_denylisted_source: Callable[[Path], bool],
) -> None:
    if role == "base_asset":
        relative = Path(artifact_path.removeprefix("strategy/"))
        if is_denylisted_source(relative):
            raise PromotionHostedPaperContractRequired(
                f"packaged artifact path is denylisted: {artifact_path}"
            )
        return
    if role == "initial_state":
        relative = Path(artifact_path.removeprefix("runtime/initial-state/"))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise PromotionHostedPaperContractRequired(
                f"invalid runtime initial state artifact path: {artifact_path}"
            )
        if is_denylisted_source(relative):
            raise PromotionHostedPaperContractRequired(
                f"runtime initial state artifact path is denylisted: {artifact_path}"
            )


def _resolve_report_source_path(
    raw: dict[str, Any],
    *,
    branch: Path,
    artifact_path: str,
) -> Path:
    source_text = _clean(raw.get("sourcePath") or raw.get("source"))
    if source_text:
        source = Path(source_text).expanduser()
        return source if source.is_absolute() else branch / source
    if artifact_path.startswith("strategy/"):
        return branch / artifact_path.removeprefix("strategy/")
    if artifact_path.startswith("runtime/initial-state/"):
        return branch / artifact_path.removeprefix("runtime/initial-state/")
    return branch / artifact_path
