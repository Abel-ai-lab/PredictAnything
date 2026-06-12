#!/usr/bin/env python3
"""Call Abel supplemental data APIs through the gateway."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

COMMON_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(COMMON_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_PYTHON_ROOT))

from abel_common.cap.auth import candidate_env_files, read_env_file_values


DEFAULT_BASE_URL = "https://cap.abel.ai/data-infra"
SIT_BASE_URL = "https://cap-sit.abel.ai/data-infra"
PROD_BASE_URL = "https://cap.abel.ai/data-infra"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[3] / "abel-auth" / ".env.skill"
AUTH_ENV_KEYS = ("ABEL_API_KEY", "CAP_API_KEY")
COMMANDS = {"auth-status", "catalog", "schema", "records"}
GLOBAL_OPTIONS = {
    "--base-url": True,
    "--target-env": True,
    "--api-key": True,
    "--env-file": True,
    "--pick-fields": True,
    "--compact": False,
}


def _load_env_file(path: str) -> None:
    for candidate in candidate_env_files(path):
        if not candidate.exists():
            continue
        values = read_env_file_values(candidate)
        for key, value in values.items():
            if key and key not in os.environ:
                os.environ[key] = value
        if any((os.getenv(key) or "").strip() for key in AUTH_ENV_KEYS):
            return


def _resolve_api_token(api_key: str | None) -> str:
    return (
        api_key
        or os.getenv("ABEL_API_KEY")
        or os.getenv("CAP_API_KEY")
        or ""
    ).strip()


def _resolve_auth_status(api_key: str | None, env_file: str) -> dict[str, Any]:
    if (api_key or "").strip():
        return {
            "auth_ready": True,
            "auth_source": "--api-key",
            "oauth_required": False,
        }

    for env_var in AUTH_ENV_KEYS:
        if (os.getenv(env_var) or "").strip():
            return {
                "auth_ready": True,
                "auth_source": "session",
                "oauth_required": False,
            }

    for candidate in candidate_env_files(env_file):
        values = read_env_file_values(candidate)
        if any(
            (values.get(key) or "").strip()
            for key in AUTH_ENV_KEYS
        ):
            return {
                "auth_ready": True,
                "auth_source": candidate.name,
                "oauth_required": False,
            }

    return {
        "auth_ready": False,
        "auth_source": "missing",
        "oauth_required": True,
    }


def _resolve_headers(api_key: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }
    token = _resolve_api_token(api_key)
    if not token:
        return headers
    if token.lower().startswith("bearer "):
        headers["Authorization"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _resolve_base_url(value: str | None, target_env: str | None = None) -> str:
    explicit = (value or "").strip()
    if explicit:
        base_url = explicit
    else:
        env_name = (target_env or os.getenv("ABEL_ENV") or "").strip().lower()
        if env_name in {"sit", "test"}:
            base_url = SIT_BASE_URL
        elif env_name in {"prod", "production", ""}:
            base_url = (
                os.getenv("ABEL_DATA_API_BASE_URL")
                or DEFAULT_BASE_URL
            ).strip()
        else:
            raise ValueError(
                "--target-env must be one of sit, test, prod, or production."
            )

    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid data API base URL: {base_url!r}")
    return base_url.rstrip("/")


def _endpoint(base_url: str, path: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    base_path = parsed.path.rstrip("/")
    suffix = "/" + path.strip("/")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, f"{base_path}{suffix}", "", "")
    )


def _json_or_text(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _public_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
    )


def _get_json(
    base_url: str,
    path: str,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {})
    url = _endpoint(base_url, path)
    if query:
        url = f"{url}?{query}"

    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            parsed = _json_or_text(response.read())
            result: dict[str, Any] = {
                "ok": True,
                "status_code": response.status,
                "url": _public_url(url),
            }
            if isinstance(parsed, dict):
                result.update(parsed)
            else:
                result["response"] = parsed
            return result
    except urllib.error.HTTPError as exc:
        try:
            parsed = _json_or_text(exc.read())
        except Exception:  # noqa: BLE001
            parsed = {}
        message = str(exc)
        if isinstance(parsed, dict):
            if isinstance(parsed.get("message"), str):
                message = parsed["message"]
            error_payload = parsed.get("error")
            if isinstance(error_payload, dict) and isinstance(
                error_payload.get("message"), str
            ):
                message = error_payload["message"]
        return {
            "ok": False,
            "status_code": exc.code,
            "url": _public_url(url),
            "message": message,
            "error": parsed.get("error") if isinstance(parsed, dict) else None,
            "response_payload": parsed,
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "status_code": -1,
            "url": _public_url(url),
            "message": str(exc.reason),
            "error": None,
            "response_payload": {},
        }


def _extract_path(obj: Any, path: str) -> tuple[bool, Any]:
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _set_path(obj: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cursor = obj
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


def _apply_pick_fields(result: dict[str, Any], pick_fields: str) -> dict[str, Any]:
    fields = [item.strip() for item in pick_fields.split(",") if item.strip()]
    if not fields:
        return result
    out: dict[str, Any] = {}
    for key in ("ok", "status_code", "url"):
        if key in result:
            out[key] = result[key]
    if result.get("ok") is False:
        for key in ("message", "error", "response_payload"):
            if key in result:
                out[key] = result[key]
    for path in fields:
        ok, value = _extract_path(result, path)
        if ok:
            _set_path(out, path, value)
    return out


def _base_url_from_args(args: argparse.Namespace) -> str:
    return _resolve_base_url(args.base_url, args.target_env)


def _cmd_auth_status(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ok": True,
        "status_code": 0,
        "base_url": _base_url_from_args(args),
        **_resolve_auth_status(args.api_key, args.env_file),
    }


def _cmd_catalog(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, str] = {}
    for key in ("domain", "frequency", "q"):
        value = getattr(args, key, "")
        if value:
            params[key] = value
    return _get_json(
        _base_url_from_args(args),
        "/api/data-tasks",
        _resolve_headers(args.api_key),
        params,
    )


def _cmd_schema(args: argparse.Namespace) -> dict[str, Any]:
    return _get_json(
        _base_url_from_args(args),
        f"/api/data-tasks/{urllib.parse.quote(args.name, safe='')}/schema",
        _resolve_headers(args.api_key),
    )


def _parse_param_pairs(items: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError("--param values must use key=value.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--param key cannot be empty.")
        params[key] = value.strip()
    return params


def _cmd_records(args: argparse.Namespace) -> dict[str, Any]:
    params = _parse_param_pairs(args.param)
    for cli_name, param_name in (
        ("start_date", "startDate"),
        ("end_date", "endDate"),
        ("limit", "limit"),
        ("cursor", "cursor"),
        ("fields", "fields"),
    ):
        value = getattr(args, cli_name)
        if value is not None and str(value).strip():
            params[param_name] = str(value).strip()
    return _get_json(
        _base_url_from_args(args),
        f"/api/data-tasks/{urllib.parse.quote(args.name, safe='')}/records",
        _resolve_headers(args.api_key),
        params,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call Abel supplemental data APIs through the gateway."
    )
    default_env = str(DEFAULT_ENV_FILE)
    parser.add_argument(
        "--base-url",
        default="",
        help=f"Gateway data-infra base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--target-env",
        choices=("sit", "test", "prod", "production"),
        default="",
        help="Resolve the gateway base URL from a known environment.",
    )
    parser.add_argument("--api-key", default="", help="Bearer token or raw API key.")
    parser.add_argument(
        "--env-file",
        default=default_env,
        help=f"Optional env file path (default: {default_env})",
    )
    parser.add_argument(
        "--pick-fields",
        default="",
        help="Comma-separated dot paths to keep from response root.",
    )
    parser.add_argument(
        "--compact", action="store_true", help="Print compact single-line JSON."
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "auth-status",
        help="Report whether auth is ready and which source would be used.",
    ).set_defaults(func=_cmd_auth_status)

    catalog = sub.add_parser("catalog", help="List visible data task datasets.")
    catalog.add_argument("--domain", default="")
    catalog.add_argument("--frequency", default="")
    catalog.add_argument("--q", default="")
    catalog.set_defaults(func=_cmd_catalog)

    schema = sub.add_parser("schema", help="Fetch one dataset schema.")
    schema.add_argument("name")
    schema.set_defaults(func=_cmd_schema)

    records = sub.add_parser("records", help="Fetch one page of dataset records.")
    records.add_argument("name")
    records.add_argument("--start-date", default="")
    records.add_argument("--end-date", default="")
    records.add_argument("--limit", type=int, default=None)
    records.add_argument("--cursor", default="")
    records.add_argument("--fields", default="")
    records.add_argument(
        "--param",
        action="append",
        default=[],
        help="Additional query parameter as key=value. Can be repeated.",
    )
    records.set_defaults(func=_cmd_records)

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv

    prefix: list[str] = []
    suffix: list[str] = []
    command_seen = False
    i = 0
    while i < len(argv):
        token = argv[i]
        if not command_seen and token in COMMANDS:
            command_seen = True
            suffix.append(token)
            i += 1
            continue

        if command_seen and token in GLOBAL_OPTIONS:
            prefix.append(token)
            if GLOBAL_OPTIONS[token]:
                if i + 1 >= len(argv):
                    raise ValueError(f"Missing value for {token}")
                prefix.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue

        if command_seen:
            suffix.append(token)
        else:
            prefix.append(token)
        i += 1

    return prefix + suffix


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv or sys.argv[1:])
    parser = _build_parser()
    try:
        argv = _normalize_argv(raw_argv)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status_code": -1,
                    "message": str(exc),
                    "error": None,
                    "response_payload": {},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    args = parser.parse_args(argv)
    if args.command != "auth-status":
        _load_env_file(args.env_file)

    try:
        result = args.func(args)
    except Exception as exc:  # noqa: BLE001
        result = {
            "ok": False,
            "status_code": -1,
            "message": str(exc),
            "error": None,
            "response_payload": {},
        }

    result = _apply_pick_fields(result, args.pick_fields)
    if args.compact:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
