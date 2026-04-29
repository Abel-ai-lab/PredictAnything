from pathlib import Path

from abel_common.cap.auth import (
    candidate_env_files,
    has_auth_token,
    preferred_auth_files,
    read_env_file_values,
    resolve_auth_env_file,
)


def test_preferred_auth_files_include_skill_local_and_shared_paths(tmp_path: Path) -> None:
    files = preferred_auth_files(tmp_path / "skills" / "abel-ask")
    rendered = [str(item) for item in files]
    assert any(path.endswith(".env.skill") for path in rendered)
    assert any("abel-ask" in path for path in rendered)


def test_candidate_env_files_include_collection_shared_locations(tmp_path: Path) -> None:
    env_file = tmp_path / "skills" / "abel-ask" / ".env.skill"
    rendered = [str(item) for item in candidate_env_files(env_file)]

    assert str(tmp_path / "skills" / ".env.skill") in rendered
    assert str(tmp_path / "skills" / "abel-auth" / ".env.skill") in rendered
    assert str(tmp_path / "skills" / "abel" / ".env.skill") in rendered


def test_resolve_auth_env_file_prefers_first_candidate_with_token(tmp_path: Path) -> None:
    env_file = tmp_path / "skills" / "abel-ask" / ".env.skill"
    auth_file = tmp_path / "skills" / "abel-auth" / ".env.skill"
    auth_file.parent.mkdir(parents=True)
    auth_file.write_text("ABEL_API_KEY=abel-from-auth-skill\n", encoding="utf-8")

    assert resolve_auth_env_file(env_file) == auth_file.resolve()


def test_read_env_file_values_and_has_auth_token_parse_abel_api_key(tmp_path: Path) -> None:
    auth_file = tmp_path / ".env.skill"
    auth_file.write_text("ABEL_API_KEY=abel_xxx\n", encoding="utf-8")

    assert read_env_file_values(auth_file)["ABEL_API_KEY"] == "abel_xxx"
    assert has_auth_token(auth_file) is True


def test_resolve_auth_env_file_reads_openclaw_skill_api_key(
    monkeypatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "workspace" / "skills" / "abel-ask" / ".env.skill"
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        '{"skills":{"entries":{"abel":{"apiKey":"abel-from-openclaw"}}}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(config_path))

    assert resolve_auth_env_file(env_file) == config_path.resolve()
    assert read_env_file_values(config_path)["ABEL_API_KEY"] == "abel-from-openclaw"


def test_resolve_auth_env_file_reads_legacy_causal_abel_api_key(
    monkeypatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "workspace" / "skills" / "abel-ask" / ".env.skill"
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        '{"skills":{"entries":{"causal-abel":{"apiKey":"abel-from-legacy-openclaw"}}}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(config_path))

    assert resolve_auth_env_file(env_file) == config_path.resolve()
    assert read_env_file_values(config_path)["ABEL_API_KEY"] == "abel-from-legacy-openclaw"
