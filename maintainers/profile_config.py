#!/usr/bin/env python3
"""Shared endpoint profile configuration for maintainer-side rendering."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

MAINTAINERS_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = MAINTAINERS_ROOT / "endpoints.json"
LEGACY_CONFIG_PATH = MAINTAINERS_ROOT / "abel-ask" / "endpoints.json"
LOCAL_CONFIG_CANDIDATES = (
    MAINTAINERS_ROOT / "endpoints.local.json",
)
AUTHORIZE_PATH = "web/credentials/oauth/google/authorize/agent"
RESULT_PATH_TEMPLATE = (
    "web/credentials/oauth/google/result?pollToken=POLL_TOKEN"
)
CALLBACK_PATH = "web/credentials/oauth/google/callback"


def _default_config_path() -> Path:
    if CONFIG_PATH.exists():
        return CONFIG_PATH
    return LEGACY_CONFIG_PATH


def _default_local_config_path() -> Path:
    for path in LOCAL_CONFIG_CANDIDATES:
        if path.exists():
            return path
    return LOCAL_CONFIG_CANDIDATES[0]


def _read_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_config(base: dict, override: dict) -> dict:
    merged = dict(base)

    if "active_profile" in override:
        merged["active_profile"] = override["active_profile"]

    base_profiles = base.get("profiles", {})
    override_profiles = override.get("profiles", {})
    profiles = {name: dict(profile) for name, profile in base_profiles.items()}
    for name, profile in override_profiles.items():
        existing = profiles.get(name, {})
        profiles[name] = {**existing, **profile}
    merged["profiles"] = profiles
    return merged


def load_endpoint_config(
    *,
    include_local: bool = False,
    config_path: Path | None = None,
    local_config_path: Path | None = None,
) -> dict:
    config = _read_config((config_path or _default_config_path()).resolve())
    local_path = (local_config_path or _default_local_config_path()).resolve()
    if include_local and local_path.exists():
        config = _merge_config(config, _read_config(local_path))
    return config


def resolve_cap_endpoint(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid base URL: {base_url!r}")
    path = parsed.path.rstrip("/")
    endpoint_path = f"{path}/cap"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, endpoint_path, "", "")
    )


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


def join_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(normalize_base_url(base_url), path)


def _profile_label(name: str) -> str:
    labels = {"prod": "production", "sit": "SIT"}
    return labels.get(name, name)


def build_profile(name: str, profile: dict) -> dict[str, str]:
    cap_base_url = profile["cap_base_url"].rstrip("/")
    oauth_base_url = normalize_base_url(profile["oauth_base_url"])
    built = {
        "name": name,
        "label": _profile_label(name),
        "cap_base_url": cap_base_url,
        "cap_endpoint_url": resolve_cap_endpoint(cap_base_url),
        "oauth_base_url": oauth_base_url,
        "authorize_agent_url": join_url(oauth_base_url, AUTHORIZE_PATH),
        "result_url_template": join_url(oauth_base_url, RESULT_PATH_TEMPLATE),
        "callback_url": join_url(oauth_base_url, CALLBACK_PATH),
        "callback_example_url": join_url(
            oauth_base_url, f"{CALLBACK_PATH}?code=GOOGLE_CODE&format=json"
        ),
    }
    for optional_key in (
        "narrative_cap_base_url",
        "narrative_cap_api_key_env",
    ):
        value = profile.get(optional_key)
        if value not in (None, ""):
            built[optional_key] = str(value)
    narrative_cap_base_url = built.get("narrative_cap_base_url")
    if narrative_cap_base_url:
        built["narrative_cap_endpoint_url"] = resolve_cap_endpoint(
            narrative_cap_base_url
        )
    return built


def get_profiles(
    config: dict | None = None, *, include_local: bool = False
) -> dict[str, dict[str, str]]:
    config = config or load_endpoint_config(include_local=include_local)
    return {
        name: build_profile(name, profile)
        for name, profile in config["profiles"].items()
    }


def get_template_values(
    config: dict | None = None,
    *,
    include_local: bool = False,
    profile_name: str | None = None,
) -> dict[str, str]:
    config = config or load_endpoint_config(include_local=include_local)
    profiles = get_profiles(config)
    selected_name = profile_name or config["active_profile"]
    active = profiles[selected_name]
    values = {
        "ACTIVE_PROFILE": active["name"],
        "ACTIVE_PROFILE_LABEL": active["label"],
        "ACTIVE_CAP_BASE_URL": active["cap_base_url"],
        "ACTIVE_CAP_ENDPOINT_URL": active["cap_endpoint_url"],
        "ACTIVE_OAUTH_BASE_URL": active["oauth_base_url"],
        "ACTIVE_AUTHORIZE_AGENT_URL": active["authorize_agent_url"],
        "ACTIVE_RESULT_URL_TEMPLATE": active["result_url_template"],
        "ACTIVE_CALLBACK_URL": active["callback_url"],
        "ACTIVE_CALLBACK_EXAMPLE_URL": active["callback_example_url"],
    }
    if "narrative_cap_base_url" in active:
        values["ACTIVE_NARRATIVE_CAP_BASE_URL"] = active[
            "narrative_cap_base_url"
        ]
    if "narrative_cap_endpoint_url" in active:
        values["ACTIVE_NARRATIVE_CAP_ENDPOINT_URL"] = active[
            "narrative_cap_endpoint_url"
        ]
    if "narrative_cap_api_key_env" in active:
        values["ACTIVE_NARRATIVE_CAP_API_KEY_ENV"] = active[
            "narrative_cap_api_key_env"
        ]
    for name, profile in profiles.items():
        prefix = name.upper()
        values[f"{prefix}_PROFILE_LABEL"] = profile["label"]
        values[f"{prefix}_CAP_BASE_URL"] = profile["cap_base_url"]
        values[f"{prefix}_CAP_ENDPOINT_URL"] = profile["cap_endpoint_url"]
        values[f"{prefix}_OAUTH_BASE_URL"] = profile["oauth_base_url"]
        values[f"{prefix}_AUTHORIZE_AGENT_URL"] = profile["authorize_agent_url"]
        values[f"{prefix}_RESULT_URL_TEMPLATE"] = profile["result_url_template"]
        values[f"{prefix}_CALLBACK_URL"] = profile["callback_url"]
        values[f"{prefix}_CALLBACK_EXAMPLE_URL"] = profile[
            "callback_example_url"
        ]
        if "narrative_cap_base_url" in profile:
            values[f"{prefix}_NARRATIVE_CAP_BASE_URL"] = profile[
                "narrative_cap_base_url"
            ]
        if "narrative_cap_endpoint_url" in profile:
            values[f"{prefix}_NARRATIVE_CAP_ENDPOINT_URL"] = profile[
                "narrative_cap_endpoint_url"
            ]
        if "narrative_cap_api_key_env" in profile:
            values[f"{prefix}_NARRATIVE_CAP_API_KEY_ENV"] = profile[
                "narrative_cap_api_key_env"
            ]
    return values
