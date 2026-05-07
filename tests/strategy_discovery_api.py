"""Test-only access to strategy-discovery owner modules.

This keeps tests off the public CLI entrypoint while preserving
compact call sites during the refactor.
"""

from __future__ import annotations

from abel_invest.narrative_core.contracts.branch_spec import (
    branch_selected_graph_nodes,
    branch_selected_inputs,
    branch_declaration_status,
    build_context_guide_markdown,
    build_data_manifest_payload,
    build_execution_constraints_payload,
    build_probe_samples_payload,
    build_runtime_profile_payload,
    load_branch_spec,
    write_branch_spec,
)
from abel_invest.narrative_core.contracts.constants import (
    AGENT_CONTEXT_FILENAME,
    EVENTS_HEADER,
    EVIDENCE_LEDGER_FILENAME,
    FRONTIER_JSON_FILENAME,
    FRONTIER_MARKDOWN_FILENAME,
    JOURNAL_GENERATED_HEADER_END,
    RESEARCH_JOURNAL_FILENAME,
    RESULTS_HEADER,
    GRAPH_FRONTIER_FILENAME,
)
from abel_invest.narrative_core.runtime.context import build_branch_context
from abel_invest.narrative_core.dashboard import (
    build_skill_dashboard_bundle,
    build_skill_dashboard_session_bundle,
    post_skill_dashboard_bundle,
    post_skill_dashboard_session,
    render_skill_dashboard_session_upload_result,
    resolve_skill_dashboard_base_url,
)
from abel_invest.narrative_core.strategy_artifacts import (
    build_strategy_artifact_manifest,
    export_selected_strategy_artifact,
    select_best_pass_strategy,
)
from abel_invest.narrative_core.evidence.evidence import evidence_runtime_facts
from abel_invest.narrative_core.io import append_tsv_row
from abel_invest.narrative_core.evidence.journal import build_research_journal_status
from abel_invest.narrative_core.command_handlers.branch import (
    debug_branch_run,
    prepare_branch_inputs,
    promote_branch_bundle,
    run_branch_round,
    subprocess,
)
from abel_invest.narrative_core.command_handlers.workspace import handle_workspace_command
from abel_invest.narrative_core.commands import main
from abel_invest.narrative_core.contracts.paths import (
    context_guide_path,
    data_manifest_path,
    dependencies_path,
    execution_constraints_path,
    probe_samples_path,
    runtime_profile_path,
)
from abel_invest.narrative_core.rendering.renderers import render_round_note
from abel_invest.narrative_core.session_lifecycle import (
    init_branch_dir,
    init_session_dir,
    refresh_data_readiness,
    render_breadth_first_start_lines,
    write_discovery,
    write_readiness,
)
from abel_invest.narrative_core.evidence.graph_frontier import (
    fetch_live_graph_expansion,
    fetch_live_graph_frontier,
    graph_frontier_from_discovery_payload,
    load_graph_frontier,
    print_graph_frontier_status,
    write_graph_frontier_from_discovery_payload,
)
from abel_invest.narrative_core.rendering.session_rendering import (
    check_session,
    graph_priority_warning_lines,
    journal_coverage_warning_lines,
    print_status,
    render_session,
)
from abel_invest.narrative_core.state import (
    branch_inputs_ready,
    load_discovery,
    persist_debug_snapshot,
    round_experiment_metadata,
    write_branch_state,
)
