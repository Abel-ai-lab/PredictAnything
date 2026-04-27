from pathlib import Path


def test_abel_router_skill_has_explicit_three_way_routing() -> None:
    text = Path("skills/abel/SKILL.md").read_text(encoding="utf-8").lower()
    assert "main entrypoint" in text
    assert "starts an abel workflow" in text
    assert "initialize abel if needed" in text
    assert "python ../abel-common/python/abel_common/cap/graph_probe.py auth-status" in text
    assert "abel-strategy-discovery" in text
    assert "abel-ask" in text
    assert "abel-auth" in text
    assert "original request" in text
    assert "references/setup-guide.md" in text


def test_strategy_discovery_skill_explains_workspace_first_boundary() -> None:
    text = Path("skills/abel-strategy-discovery/SKILL.md").read_text(encoding="utf-8").lower()
    assert "workspace-first" in text
    assert "reuse the default workspace" in text
    assert "bootstrap the workspace" in text
    assert "abel-auth" in text
