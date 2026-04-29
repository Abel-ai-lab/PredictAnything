from __future__ import annotations

import json
import os
from pathlib import Path


ENV_FILE_BASENAMES = (".env.skill", ".env.skills")
ENV_FALLBACK_BASENAME = ".env"
COLLECTION_SHARED_SKILLS = ("abel-auth", "abel", "abel-ask")
AUTH_ENV_KEYS = ("ABEL_API_KEY", "CAP_API_KEY")
OPENCLAW_SKILL_KEYS = ("abel", "causal-abel")


def preferred_auth_files(skill_root: Path) -> list[Path]:
    return [
        skill_root / ".env.skill",
        skill_root / ".env.skills",
        skill_root / ".env",
    ]


def _collection_auth_files(skill_root: Path) -> list[Path]:
    skill_root = skill_root.expanduser()
    skills_root = skill_root.parent
    if skills_root.name != "skills":
        return []

    files: list[Path] = []
    for basename in (*ENV_FILE_BASENAMES, ENV_FALLBACK_BASENAME):
        files.append(skills_root / basename)
    for sibling_name in COLLECTION_SHARED_SKILLS:
        sibling_root = skills_root / sibling_name
        if sibling_root == skill_root:
            continue
        files.extend(preferred_auth_files(sibling_root))
    return files


def _openclaw_config_files() -> list[Path]:
    files: list[Path] = []
    configured_path = (os.getenv("OPENCLAW_CONFIG_PATH") or "").strip()
    if configured_path:
        files.append(Path(configured_path).expanduser())

    home = Path.home()
    files.append(home / ".openclaw" / "openclaw.json")
    files.extend(sorted(home.glob(".openclaw-*/openclaw.json")))

    deduped: list[Path] = []
    for path in files:
        if path not in deduped:
            deduped.append(path)
    return deduped


def candidate_env_files(path: str | Path) -> list[Path]:
    env_path = Path(path).expanduser()
    candidates = [env_path]
    if env_path.name in ENV_FILE_BASENAMES:
        for basename in ENV_FILE_BASENAMES:
            candidate = env_path.with_name(basename)
            if candidate not in candidates:
                candidates.append(candidate)
        fallback_candidate = env_path.with_name(ENV_FALLBACK_BASENAME)
        if fallback_candidate not in candidates:
            candidates.append(fallback_candidate)
        for candidate in _collection_auth_files(env_path.parent):
            if candidate not in candidates:
                candidates.append(candidate)
    for candidate in _openclaw_config_files():
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _read_openclaw_config_values(path: Path) -> dict[str, str]:
    if path.name != "openclaw.json":
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("skills", {}).get("entries", {})
    if not isinstance(entries, dict):
        return {}

    for skill_key in OPENCLAW_SKILL_KEYS:
        skill_config = entries.get(skill_key)
        if not isinstance(skill_config, dict):
            continue
        api_key = skill_config.get("apiKey")
        if isinstance(api_key, str) and api_key.strip():
            return {"ABEL_API_KEY": api_key.strip()}
        if isinstance(api_key, dict) and api_key.get("source") == "env":
            env_name = str(api_key.get("id") or "").strip()
            env_value = (os.getenv(env_name) or "").strip()
            if env_name and env_value:
                return {"ABEL_API_KEY": env_value}
    return {}


def read_env_file_values(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = Path(path).expanduser()
    if not env_path.exists():
        return values
    openclaw_values = _read_openclaw_config_values(env_path)
    if openclaw_values:
        return openclaw_values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def has_auth_token(path: str | Path) -> bool:
    values = read_env_file_values(path)
    return any((values.get(name) or "").strip() for name in AUTH_ENV_KEYS)


def resolve_auth_env_file(path: str | Path) -> Path | None:
    for candidate in candidate_env_files(path):
        if has_auth_token(candidate):
            return candidate.expanduser().resolve()
    return None
