"""Public facade for Abel Invest strategy promotion."""

from __future__ import annotations

from .constants import *  # noqa: F403
from .models import (
    PromotionHostedPaperContractRequired,
    PromotionHostedPaperRewriteRequired,
    PromotionPackagedFile,
    PromotionResult,
)
from .facts import (
    _collect_hosted_paper_dependency_scan,
    _trade_log_oracle_facts,
)
from .orchestrator import prepare_promotion
from .packaging import (
    _report_packaged_files,
    _validate_packaged_research_evidence_sources,
)
from .paper.smoke import _paper_smoke_context, _run_edge_paper_run_one_smoke
from .paper.trace import PROMOTION_TAIL_TRACE_FILENAME
from .report import _report_paper_execution_profile
from .request import _write_hosted_paper_contract_request
from .source_scan import (
    paper_signal_design_facts as _paper_signal_design_facts,
    source_temporal_dependency_facts as _source_temporal_dependency_facts,
)
from .validation import _validate_agent_paper_signal_contract

__all__ = [
    "PromotionHostedPaperContractRequired",
    "PromotionHostedPaperRewriteRequired",
    "PromotionPackagedFile",
    "PromotionResult",
    "prepare_promotion",
    "_collect_hosted_paper_dependency_scan",
    "_paper_signal_design_facts",
    "_paper_smoke_context",
    "_report_packaged_files",
    "_report_paper_execution_profile",
    "_run_edge_paper_run_one_smoke",
    "_source_temporal_dependency_facts",
    "_trade_log_oracle_facts",
    "_validate_agent_paper_signal_contract",
    "_validate_packaged_research_evidence_sources",
    "_write_hosted_paper_contract_request",
    "PROMOTION_TAIL_TRACE_FILENAME",
    *[
        name
        for name in globals()
        if name.startswith("PROMOTION_") or name == "LOCAL_RUNTIME_STATE_DIR"
    ],
]
