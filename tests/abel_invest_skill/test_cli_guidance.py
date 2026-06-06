from abel_invest.narrative_core.command_handlers.branch import STATE_SELF_CHECK_LINES
from abel_invest.narrative_core.evidence.frontier import (
    render_frontier_markdown,
    render_session_frontier_summary,
)


def test_run_branch_self_check_keeps_failures_diagnostic():
    joined = "\n".join(STATE_SELF_CHECK_LINES)

    assert "Edge failures as diagnostics" in joined
    assert "higher-ceiling Sharpe/return" in joined
    assert "only repairing gates" in joined


def test_frontier_markdown_says_coverage_is_not_exhaustion():
    rendered = render_frontier_markdown(
        {
            "exp_id": "session-a",
            "asset_scope": "META",
            "path_coverage": {"path_coverage_complete": True},
        }
    )

    assert "## Search Boundary" in rendered
    assert "do not prove\nexhaustion" in rendered


def test_frontier_summary_keeps_search_boundary_visible():
    rendered = render_session_frontier_summary(
        {
            "row_count": 1,
            "path_coverage": {"path_coverage_complete": True},
        }
    )

    assert "coverage is audit organization, not exhaustion" in rendered
