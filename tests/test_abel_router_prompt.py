from pathlib import Path


def test_abel_router_skill_has_explicit_three_way_routing() -> None:
    text = Path("skills/abel/SKILL.md").read_text(encoding="utf-8").lower()
    assert "main entrypoint" in text
    assert "starts an abel workflow" in text
    assert "initialize abel if needed" in text
    assert (
        "python3 <abel-skill-root>/../abel-common/python/abel_common/cap/graph_probe.py auth-status"
        in text
    )
    assert "do not use a current-working-directory relative" in text
    assert "abel-invest" in text
    assert "abel-ask" in text
    assert "abel-auth" in text
    assert "original request" in text
    assert "references/setup-guide.md" in text


def test_strategy_discovery_skill_explains_workspace_first_boundary() -> None:
    text = Path("skills/abel-invest/SKILL.md").read_text(encoding="utf-8").lower()
    assert "workspace-first" in text
    assert "reuse the default workspace" in text
    assert "bootstrap the workspace" in text
    assert "abel-auth" in text
    assert "references/data-driven-construction.md" in text
    assert "first serious recorded alpha" in text
    assert "first-look data scout" in text
    assert "prepare-branch" in text
    assert "sharpe > 2" in text
    assert "research/<ticker>/<session_id>/scratch/" in text
    assert "gates estimate reliability" in text
    assert "hand-written single-mechanism branches are diagnostics" in text
    assert "gauntlet" not in text
    assert "survivor" not in text
