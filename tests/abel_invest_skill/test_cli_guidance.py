from abel_invest.narrative_core.command_handlers.branch import (
    print_round_decision_checkpoint,
)
from abel_invest.narrative_core.evidence.frontier import (
    render_frontier_markdown,
    render_session_frontier_summary,
)


def test_run_branch_decision_checkpoint_has_two_normal_paths(tmp_path, capsys):
    session = tmp_path / "research" / "aapl" / "aapl-v1"
    branch = session / "branches" / "graph-v1"
    branch.mkdir(parents=True)

    print_round_decision_checkpoint(
        session=session,
        branch=branch,
        round_id="round-001",
    )

    output = capsys.readouterr().out
    assert "Decision checkpoint:" in output
    assert "Choose exactly one next action." in output
    assert "Continue exploration:" in output
    assert "Final report:" in output
    assert "best-strategy --session" in output
    assert "exploration is incomplete" in output
    assert "while also naming the next experiment" in output
    assert "continue/pivot/stop" not in output


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
