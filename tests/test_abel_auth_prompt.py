from pathlib import Path


def test_abel_auth_skill_mentions_reuse_then_oauth() -> None:
    text = Path("skills/abel-auth/SKILL.md").read_text(encoding="utf-8")
    assert "reuse existing auth" in text.lower()
    assert "oauth" in text.lower()


def test_abel_auth_skill_points_to_setup_ref_and_probe_command() -> None:
    text = Path("skills/abel-auth/SKILL.md").read_text(encoding="utf-8").lower()
    assert "python ../abel-common/python/abel_common/cap/graph_probe.py auth-status" in text
    assert "references/setup-guide.md" in text


def test_abel_ask_no_longer_owns_setup_flow() -> None:
    text = Path("skills/abel-ask/SKILL.md").read_text(encoding="utf-8").lower()
    assert "abel-auth" in text
    assert "setup-guide.md" not in text
