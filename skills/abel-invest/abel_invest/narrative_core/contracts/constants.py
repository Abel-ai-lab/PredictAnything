"""Constants for the Abel strategy-discovery narrative surface."""

from __future__ import annotations

import re

EVENTS_HEADER = [
    "timestamp",
    "event",
    "branch_id",
    "round_id",
    "mode",
    "verdict",
    "decision",
    "description",
    "artifact_path",
]

DEFAULT_BACKTEST_START = "2020-01-01"
DEFAULT_ABEL_ROUTER_BASE_URL = "https://api.abel.ai/router/"
SESSION_STATE_FILENAME = "session_state.json"
BRANCH_STATE_FILENAME = "branch_state.json"
READINESS_FILENAME = "readiness.json"
BRANCH_SPEC_FILENAME = "branch.yaml"
DEPENDENCIES_FILENAME = "dependencies.json"
RUNTIME_PROFILE_FILENAME = "runtime_profile.json"
EXECUTION_CONSTRAINTS_FILENAME = "execution_constraints.json"
DATA_MANIFEST_FILENAME = "data_manifest.json"
CONTEXT_GUIDE_FILENAME = "context_guide.md"
PROBE_SAMPLES_FILENAME = "probe_samples.json"
AGENT_CONTEXT_FILENAME = "agent_context.md"
RESEARCH_JOURNAL_FILENAME = "research_journal.md"
EVIDENCE_LEDGER_FILENAME = "evidence_ledger.json"
GRAPH_FRONTIER_FILENAME = "graph_frontier.json"
FRONTIER_JSON_FILENAME = "frontier.json"
FRONTIER_MARKDOWN_FILENAME = "frontier.md"

EVIDENCE_INTENTS = {"candidate", "control", "diagnostic", "draft"}
INPUT_CLAIMS = {"graph_supported", "target_only", "supplement", "mixed"}
GRAPH_INPUT_CLAIMS = {"graph_supported", "supplement", "mixed"}
DECLARATION_PLACEHOLDER_VALUES = {"", "unspecified", "unknown", "draft", "todo", "tbd"}
DECLARATION_REQUIRED_FIELDS = [
    "hypothesis",
    "evidence_intent",
    "input_claim",
    "mechanism_family",
    "invalidation_condition",
    "requested_start",
]
MODEL_FAMILIES = {
    "rule_signal",
    "linear_model",
    "tree_model",
    "learned_model",
    "ensemble",
    "hybrid",
    "unspecified",
}
COMPLEXITY_CLASSES = {
    "simple_signal",
    "interaction",
    "regime",
    "portfolio",
    "learned_model",
    "hybrid",
    "unspecified",
}
EXPLORATION_ROLES = {
    "candidate",
    "control",
    "ablation",
    "expansion_probe",
    "refinement",
    "diagnostic",
    "unspecified",
}
CHANGED_DIMENSIONS = {
    "drivers",
    "mechanism",
    "model_family",
    "complexity",
    "sizing",
    "thresholds",
    "filters",
    "window",
    "implementation",
}
BROAD_CHANGED_DIMENSIONS = {"drivers", "mechanism", "model_family", "complexity"}
LOCAL_CHANGED_DIMENSIONS = {"sizing", "thresholds", "filters", "window", "implementation"}
INPUT_BREADTH_ROUND_THRESHOLD = 8
GRAPH_PRIORITY_ROUND_MINIMUM = 3
JOURNAL_GENERATED_HEADER_END = "<!-- ABEL_GENERATED_HEADER_END -->"
JOURNAL_REFERENCE_RE = re.compile(
    r"(ledger:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+|"
    r"frontier:[A-Za-z0-9_.-]+|"
    r"frontier\.md|"
    r"evidence_ledger\.json|"
    r"artifact:[^\s)]+|"
    r"branches/[^\s)]+)"
)

EXPERIMENT_METADATA_ENV = {
    "protocol_id": "ABEL_EXPERIMENT_PROTOCOL_ID",
    "experiment_mode": "ABEL_EXPERIMENT_MODE",
    "round_budget": "ABEL_EXPERIMENT_ROUND_BUDGET",
    "abel_skills_commit": "ABEL_SKILLS_COMMIT",
    "abel_edge_commit": "ABEL_EDGE_COMMIT",
}

RESULTS_HEADER = [
    "exp_id",
    "ticker",
    "branch_id",
    "round_id",
    "decision",
    "lo_adj",
    "ic",
    "omega",
    "sharpe",
    "max_dd",
    "pnl",
    "K",
    "score",
    "verdict",
    "mode",
    "description",
    "result_path",
    "report_path",
    "handoff_path",
]
