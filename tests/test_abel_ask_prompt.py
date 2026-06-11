from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_abel_ask_mentions_data_api_reference_and_wrapper():
    skill_text = (REPO_ROOT / "skills" / "abel-ask" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "references/data-api-usage.md" in skill_text
    assert "scripts/data_api.py" in skill_text


def test_data_api_reference_uses_gateway_authorization_contract():
    reference_text = (
        REPO_ROOT / "skills" / "abel-ask" / "references" / "data-api-usage.md"
    ).read_text(encoding="utf-8")

    assert "Authorization: Bearer <api-key>" in reference_text
    assert "Do not send `api-key`, `user-tier`, or `fee-level`" in reference_text


def test_data_api_reference_describes_when_to_use_structured_data():
    reference_text = (
        REPO_ROOT / "skills" / "abel-ask" / "references" / "data-api-usage.md"
    ).read_text(encoding="utf-8")

    assert "concrete structured facts" in reference_text
    assert "historical" in reference_text
    assert "Do not use the data API for pure concept explanations" in reference_text


def test_data_api_reference_includes_operational_guardrails():
    reference_text = (
        REPO_ROOT / "skills" / "abel-ask" / "references" / "data-api-usage.md"
    ).read_text(encoding="utf-8")

    assert "auth-status" in reference_text
    assert "`ok`" in reference_text
    assert "`status_code`" in reference_text
    assert "`message`" in reference_text
    assert "--compact" in reference_text
    assert "--pick-fields" in reference_text
    assert "--cursor <nextCursor>" in reference_text
