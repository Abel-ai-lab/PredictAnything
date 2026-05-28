"""Constants for Abel Invest strategy promotion."""

from __future__ import annotations

from pathlib import Path

from . import promotion_tail

PROMOTION_PAPER_TAIL_MAX_COUNT = promotion_tail.PROMOTION_PAPER_TAIL_MAX_COUNT
PROMOTION_PAPER_TAIL_TARGET_COUNT = promotion_tail.PROMOTION_PAPER_TAIL_TARGET_COUNT
PROMOTION_PAPER_TAIL_TOLERANCE = promotion_tail.PROMOTION_PAPER_TAIL_TOLERANCE
LOCAL_RUNTIME_STATE_DIR = Path(".abel-runtime") / "state"
PROMOTION_MODE_ZERO_CHANGE = "zero_change"
PROMOTION_STATUS_HOSTED_PAPER_CONTRACT_REQUIRED = "hosted_paper_contract_required"
PROMOTION_MODE_AGENT_PAPER_CONTRACT = "agent_paper_contract"
PROMOTION_GATE_FILENAME = "promotion-gate.json"
PROMOTION_PATCH_FILENAME = "promotion.patch"
PROMOTION_CONTRACT_REPORT_FILENAME = "paper-contract-report.json"
PROMOTION_CONTRACT_REQUEST_FILENAME = "paper-contract-request.json"
PROMOTION_CONTRACT_FACTS_FILENAME = "paper-contract-facts.json"
PROMOTION_AGENT_REPORT_SCHEMA = "abel-invest.agent-paper-contract-report/v1"
PROMOTION_AGENT_REQUEST_SCHEMA = "abel-invest.agent-paper-contract-request/v1"
PROMOTION_HOSTED_CONTRACT_SCOPE = "hosted_paper_contract"
PROMOTION_PAPER_SMOKE_WARN_SECONDS = 5.0
PROMOTION_PAPER_SMOKE_MAX_TRAINING_SECONDS = 5.0
PROMOTION_HOSTED_PAPER_TIMEOUT_SECONDS = 120.0
PROMOTION_FULL_REPLAY_FALLBACK_MAX_SECONDS = PROMOTION_HOSTED_PAPER_TIMEOUT_SECONDS
PROMOTION_LIVE_CONTRACT_FAILURES_BEFORE_FALLBACK = 3
PROMOTION_LIVE_READINESS_CONFLICT_PHRASES = (
    "after the packaged log",
    "can only replay",
    "cannot produce future",
    "can't produce future",
    "edge output",
    "finite historical",
    "finite replay",
    "historical replay",
    "no future signal",
    "not continuing",
    "not hostable",
    "not safely hostable",
    "promotion output",
    "research evidence",
)
PROMOTION_INITIAL_STATE_ORACLE_PHRASES = (
    "expectednextposition",
    "selected round",
    "selected-round",
    "selected_round",
    "tail_overrides",
    "tradelogoracle",
    "validationoracle",
    "validation oracle",
)
PROMOTION_LEGACY_PROMOTED_FILES = (
    "dependency-scan.json",
    "packaging-plan.json",
    "refactor-request.json",
    "refactor-report.json",
    "refactor-report.artifact.json",
)
PROMOTION_LEGACY_DESTINATION_DIRS = (
    "promotion-replay",
)
PROMOTION_RECONSTRUCTION_MODES = {
    "none",
    "minimal_cutover_state",
    "full_replay",
}
PROMOTION_CONTINUATION_METHODS = {
    "stateless_recompute",
    "stateful_continuation",
    "full_replay_fallback",
    "not_hostable",
}
PROMOTION_CONTRACT_REQUESTS_BEFORE_FALLBACK = 3
PROMOTION_ML_STATE_EVIDENCE_TERMS = (
    "calibrator",
    "checkpoint",
    "coef",
    "coefficient",
    "coefficients",
    "encoder",
    "estimator",
    "feature selector",
    "fit index",
    "fitted",
    "forest",
    "last fit",
    "learner",
    "model",
    "models",
    "parameter",
    "parameters",
    "rf state",
    "scaler",
    "scalers",
    "training state",
    "transformer",
    "weights",
)
STATE_SELF_CHECK_FILE_SUFFIXES = {
    ".joblib",
    ".npy",
    ".npz",
    ".onnx",
    ".pkl",
    ".pickle",
    ".pt",
    ".pth",
    ".safetensors",
}
STATE_SELF_CHECK_DIRECTORY_PARTS = {
    "cache",
    "caches",
    "checkpoint",
    "checkpoints",
    "model",
    "models",
    "registry",
    "registries",
    "scaler",
    "scalers",
    "state",
    "states",
}
STATE_SELF_CHECK_DIRECTORY_SUFFIXES = STATE_SELF_CHECK_FILE_SUFFIXES | {
    ".json",
    ".yaml",
    ".yml",
}
STATE_SELF_CHECK_SOURCE_KEYWORDS = (
    "cache",
    "checkpoint",
    "joblib",
    "model",
    "pickle",
    "registry",
    "scaler",
    "state",
)
STATE_SELF_CHECK_SOURCE_PATH_PARTS = {
    "checkpoint",
    "checkpoints",
    "model",
    "models",
    "registry",
    "registries",
    "scaler",
    "scalers",
}
PROMOTION_BRANCH_FILE_SUFFIXES = {
    ".csv",
    ".json",
    ".joblib",
    ".npy",
    ".npz",
    ".pkl",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}
