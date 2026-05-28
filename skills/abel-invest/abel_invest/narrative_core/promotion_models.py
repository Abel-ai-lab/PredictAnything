"""Data models for Abel Invest strategy promotion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .promotion_constants import PROMOTION_MODE_AGENT_PAPER_CONTRACT

@dataclass(frozen=True)
class PromotionPackagedFile:
    artifact_path: str
    source_path: Path
    purpose: str
    role: str

    @property
    def path(self) -> str:
        if self.artifact_path.startswith("runtime/initial-state/"):
            return self.artifact_path.removeprefix("runtime/initial-state/")
        if self.artifact_path.startswith("strategy/"):
            return self.artifact_path.removeprefix("strategy/")
        return self.artifact_path


@dataclass(frozen=True)
class PromotionResult:
    mode: str
    strategy_source_path: Path
    packaged_files: tuple[PromotionPackagedFile, ...]
    extra_source_map: dict[str, Path]
    patch_path: Path | None
    gate_path: Path
    contract_report_path: Path | None
    paper_execution_profile: dict[str, Any] | None
    report: dict[str, Any]

    @property
    def adapted(self) -> bool:
        return self.mode == PROMOTION_MODE_AGENT_PAPER_CONTRACT


class PromotionHostedPaperContractRequired(RuntimeError):
    """Raised when promotion needs a hosted paper contract before publishing."""


# Backward-compatible alias for older internal imports.
PromotionHostedPaperRewriteRequired = PromotionHostedPaperContractRequired
