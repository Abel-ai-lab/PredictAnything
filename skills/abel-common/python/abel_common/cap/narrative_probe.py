#!/usr/bin/env python3
"""Probe the narrative CAP provider with no third-party dependencies."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

COMMON_PYTHON_ROOT = Path(__file__).resolve().parents[2]

if str(COMMON_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_PYTHON_ROOT))

from abel_common.cap.auth import candidate_env_files, read_env_file_values


DEFAULT_BASE_URL = "https://cap.abel.ai/narrative"
CAP_VERSION = "0.3.0"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[4] / "abel-auth" / ".env.skill"
TEXT_TRUNCATE_EXACT_KEYS = {
    "description",
    "summary",
    "content",
    "message",
    "details",
    "narrative",
    "headline",
}
COMMANDS = {
    "auth-status",
    "card",
    "methods",
    "narrate",
    "observe-predict",
    "intervene-do",
    "query-node",
    "resolve-entity",
    "explain-read-bundle",
    "explain-outcome",
    "search-prepare",
    "predict",
    "what-if",
}

def _load_env_file(path: str) -> None:
    for candidate in candidate_env_files(path):
        if not candidate.exists():
            continue
        for key, value in read_env_file_values(candidate).items():
            if key and key not in os.environ:
                os.environ[key] = value
        return


def _resolve_base_url(value: str | None) -> str:
    return (value or DEFAULT_BASE_URL).strip()


def resolve_cap_endpoint(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid base URL: {base_url!r}")
    path = parsed.path.rstrip("/")
    if path.endswith("/cap"):
        endpoint_path = path
    else:
        endpoint_path = f"{path}/cap"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, endpoint_path, "", "")
    )


def resolve_card_endpoint(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid base URL: {base_url!r}")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "/.well-known/cap.json", "", "")
    )


def _resolve_api_token(api_key: str | None) -> str:
    return (
        api_key
        or os.getenv("CAP_API_KEY")
        or os.getenv("ABEL_API_KEY")
        or ""
    ).strip()


def _resolve_auth_status(api_key: str | None, env_file: str) -> dict[str, Any]:
    if (api_key or "").strip():
        return {
            "auth_ready": True,
            "auth_source": "--api-key",
            "oauth_required": False,
        }

    for env_var in ("CAP_API_KEY", "ABEL_API_KEY"):
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
            for key in ("CAP_API_KEY", "ABEL_API_KEY")
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
        "Content-Type": "application/json",
    }
    token = _resolve_api_token(api_key)
    if not token:
        return headers
    if token.lower().startswith("bearer "):
        headers["Authorization"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


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
    for key in ("ok", "status_code", "verb", "request_id"):
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


def _should_truncate_text_field(key: str) -> bool:
    normalized = key.strip().lower()
    if not normalized:
        return False
    if normalized in TEXT_TRUNCATE_EXACT_KEYS:
        return True
    return "description" in normalized


def _truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}..."


def _truncate_description_fields(obj: Any, max_chars: int) -> Any:
    if max_chars <= 0:
        return obj
    if isinstance(obj, dict):
        transformed: dict[str, Any] = {}
        for key, value in obj.items():
            if isinstance(value, str) and _should_truncate_text_field(key):
                transformed[key] = _truncate_text(value, max_chars)
            else:
                transformed[key] = _truncate_description_fields(value, max_chars)
        return transformed
    if isinstance(obj, list):
        return [_truncate_description_fields(item, max_chars) for item in obj]
    return obj


def _json_or_text(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _parse_json_arg(raw: str, *, flag_name: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{flag_name} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{flag_name} must decode to a JSON object.")
    return parsed


def _build_payload(
    verb: str,
    params: dict[str, Any] | None = None,
    *,
    graph_ref: str | None = None,
    response_detail: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "cap_version": CAP_VERSION,
        "request_id": str(uuid.uuid4()),
        "verb": verb,
    }
    if params is not None:
        payload["params"] = params
    if graph_ref and not verb.startswith("meta."):
        payload["context"] = {"graph_ref": {"graph_id": graph_ref}}
    if response_detail:
        payload["options"] = {"response_detail": response_detail}
    return payload


def _get_card(base_url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(
        resolve_card_endpoint(base_url),
        method="GET",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=240.0) as response:
            parsed = _json_or_text(response.read())
            if isinstance(parsed, dict):
                return {"ok": True, "status_code": response.status, **parsed}
            return {"ok": True, "status_code": response.status, "response": parsed}
    except urllib.error.HTTPError as exc:
        parsed = _json_or_text(exc.read())
        return {
            "ok": False,
            "status_code": exc.code,
            "message": f"HTTP {exc.code} calling capability card",
            "response_payload": parsed,
        }


def _post_cap(
    base_url: str,
    verb: str,
    params: dict[str, Any] | None,
    headers: dict[str, str],
    *,
    graph_ref: str | None = None,
    response_detail: str | None = None,
) -> dict[str, Any]:
    payload = _build_payload(
        verb,
        params,
        graph_ref=graph_ref,
        response_detail=response_detail,
    )
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        resolve_cap_endpoint(base_url),
        data=data,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as response:
            parsed = _json_or_text(response.read())
            if isinstance(parsed, dict):
                return {"ok": True, "status_code": response.status, **parsed}
            return {"ok": True, "status_code": response.status, "response": parsed}
    except urllib.error.HTTPError as exc:
        parsed = _json_or_text(exc.read())
        return {
            "ok": False,
            "status_code": exc.code,
            "message": f"HTTP {exc.code} calling {verb}",
            "response_payload": parsed,
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "status_code": -1,
            "message": f"Network error calling {verb}: {exc.reason}",
        }


def _call_verb(
    args: argparse.Namespace,
    verb: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = _resolve_base_url(getattr(args, "base_url", ""))
    headers = _resolve_headers(getattr(args, "api_key", ""))
    result = _post_cap(
        base_url,
        verb,
        params,
        headers,
        graph_ref=getattr(args, "graph_ref", ""),
        response_detail=getattr(args, "response_detail", ""),
    )
    result["verb"] = verb
    return result


def _cmd_card(args: argparse.Namespace) -> dict[str, Any]:
    base_url = _resolve_base_url(args.base_url)
    headers = _resolve_headers(args.api_key)
    result = _get_card(base_url, headers)
    result["verb"] = "meta.capabilities"
    return result


def _cmd_auth_status(args: argparse.Namespace) -> dict[str, Any]:
    result = _resolve_auth_status(args.api_key, args.env_file)
    result["verb"] = "meta.capabilities"
    return result


def _cmd_methods(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if args.verbs:
        params["verbs"] = list(args.verbs)
    return _call_verb(args, "meta.methods", params or None)


def _cmd_narrate(args: argparse.Namespace) -> dict[str, Any]:
    return _call_verb(args, "narrate", {"query": args.query})


def _cmd_observe_predict(args: argparse.Namespace) -> dict[str, Any]:
    return _call_verb(
        args,
        "observe.predict",
        {"target_node": args.target_node},
    )


def _cmd_intervene_do(args: argparse.Namespace) -> dict[str, Any]:
    return _call_verb(
        args,
        "intervene.do",
        {
            "treatment_node": args.treatment_node,
            "treatment_value": args.treatment_value,
            "outcome_node": args.outcome_node,
        },
    )


def _cmd_query_node(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"search": args.query}
    if args.search_mode:
        params["search_mode"] = args.search_mode
    if args.top_k is not None:
        params["top_k"] = args.top_k
    advanced = _parse_json_arg(args.advanced_json, flag_name="--advanced-json")
    if advanced:
        params["advanced"] = advanced
    return _call_verb(args, "extensions.abel.stateless.query_node", params)


def _cmd_resolve_entity(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"search": args.query}
    if args.search_mode:
        params["search_mode"] = args.search_mode
    if args.top_k is not None:
        params["top_k"] = args.top_k
    advanced = _parse_json_arg(args.advanced_json, flag_name="--advanced-json")
    if advanced:
        params["advanced"] = advanced
    return _call_verb(args, "extensions.abel.stateless.resolve_entity", params)


def _cmd_explain_read_bundle(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"search": args.query}
    if args.search_mode:
        params["search_mode"] = args.search_mode
    if args.top_k is not None:
        params["top_k"] = args.top_k
    if args.question_type:
        params["question_type"] = args.question_type
    if args.strictness:
        params["strictness"] = args.strictness
    if args.include_layers:
        params["include_layers"] = list(args.include_layers)
    advanced = _parse_json_arg(args.advanced_json, flag_name="--advanced-json")
    if advanced:
        params["advanced"] = advanced
    return _call_verb(args, "extensions.abel.stateless.explain_read_bundle", params)


def _cmd_explain_outcome(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"search": args.query}
    if args.search_mode:
        params["search_mode"] = args.search_mode
    if args.top_k is not None:
        params["top_k"] = args.top_k
    if args.outcome_mode:
        params["outcome_mode"] = args.outcome_mode
    if args.focus_strategy:
        params["focus_strategy"] = args.focus_strategy
    if args.focus_top_n is not None:
        params["focus_top_n"] = args.focus_top_n
    if args.top_driver_count is not None:
        params["top_driver_count"] = args.top_driver_count
    if args.max_paths is not None:
        params["max_paths"] = args.max_paths
    if args.max_hops is not None:
        params["max_hops"] = args.max_hops
    if args.include_bayes_evidence:
        params["include_bayes_evidence"] = True
    advanced = _parse_json_arg(args.advanced_json, flag_name="--advanced-json")
    if advanced:
        params["advanced"] = advanced
    return _call_verb(args, "extensions.abel.stateless.explain_outcome", params)


def _cmd_search_prepare(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {
        "search": args.query,
        "intent": args.intent,
    }
    if args.search_mode:
        params["search_mode"] = args.search_mode
    if args.top_k is not None:
        params["top_k"] = args.top_k
    advanced = _parse_json_arg(args.advanced_json, flag_name="--advanced-json")
    if advanced:
        params["advanced"] = advanced
    if args.max_hops is not None:
        params["max_hops"] = args.max_hops
    if args.max_nodes is not None:
        params["max_nodes"] = args.max_nodes
    if args.multi_snapshot_policy:
        params["multi_snapshot_policy"] = args.multi_snapshot_policy
    return _call_verb(args, "extensions.abel.stateful.search_prepare", params)


def _cmd_predict(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {
        "session_handle": args.session_handle,
        "node_ref": args.node_ref,
    }
    return _call_verb(args, "extensions.abel.stateful.predict", params)


def _cmd_what_if(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {
        "session_handle": args.session_handle,
        "treatment_node_ref": args.treatment_node_ref,
        "treatment_value": args.treatment_value,
        "outcome_node_ref": args.outcome_node_ref,
    }
    return _call_verb(args, "extensions.abel.stateful.what_if", params)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe a narrative CAP provider from the command line."
    )
    parser.add_argument("--base-url", default="", help="Narrative CAP site base URL.")
    parser.add_argument("--api-key", default="", help="Optional API key.")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Local env file to load before resolving credentials.",
    )
    parser.add_argument(
        "--pick-fields",
        default="",
        help="Comma-separated dot paths to keep in the final JSON output.",
    )
    parser.add_argument(
        "--max-description-chars",
        type=int,
        default=0,
        help="Truncate long narrative or description fields in the final JSON output.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of pretty JSON.",
    )
    parser.add_argument(
        "--graph-ref",
        default="",
        help="Optional provider graph_ref.graph_id to pass through unchanged.",
    )
    parser.add_argument(
        "--response-detail",
        default="",
        choices=("", "summary", "full", "raw"),
        help="Optional CAP options.response_detail value.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser(
        "auth-status",
        help="Report whether auth is ready and which source would be used.",
    )
    auth_parser.set_defaults(func=_cmd_auth_status)

    card_parser = subparsers.add_parser("card", help="Fetch the provider capability card.")
    card_parser.set_defaults(func=_cmd_card)

    methods_parser = subparsers.add_parser("methods", help="Call meta.methods.")
    methods_parser.add_argument("--verbs", nargs="*", default=None)
    methods_parser.set_defaults(func=_cmd_methods)

    narrate_parser = subparsers.add_parser("narrate", help="Call core narrate.")
    narrate_parser.add_argument("--query", required=True)
    narrate_parser.set_defaults(func=_cmd_narrate)

    observe_parser = subparsers.add_parser(
        "observe-predict",
        help="Call core observe.predict.",
    )
    observe_parser.add_argument("--target-node", required=True)
    observe_parser.set_defaults(func=_cmd_observe_predict)

    intervene_parser = subparsers.add_parser(
        "intervene-do",
        help="Call core intervene.do.",
    )
    intervene_parser.add_argument("--treatment-node", required=True)
    intervene_parser.add_argument("--treatment-value", required=True, type=float)
    intervene_parser.add_argument("--outcome-node", required=True)
    intervene_parser.set_defaults(func=_cmd_intervene_do)

    query_node_parser = subparsers.add_parser(
        "query-node",
        help="Call extensions.abel.stateless.query_node.",
    )
    query_node_parser.add_argument("--query", required=True)
    query_node_parser.add_argument("--search-mode", default="")
    query_node_parser.add_argument("--top-k", type=int, default=None)
    query_node_parser.add_argument("--advanced-json", default="")
    query_node_parser.set_defaults(func=_cmd_query_node)

    resolve_parser = subparsers.add_parser(
        "resolve-entity",
        help="Call extensions.abel.stateless.resolve_entity.",
    )
    resolve_parser.add_argument("--query", required=True)
    resolve_parser.add_argument("--search-mode", default="")
    resolve_parser.add_argument("--top-k", type=int, default=None)
    resolve_parser.add_argument("--advanced-json", default="")
    resolve_parser.set_defaults(func=_cmd_resolve_entity)

    bundle_parser = subparsers.add_parser(
        "explain-read-bundle",
        help="Call extensions.abel.stateless.explain_read_bundle.",
    )
    bundle_parser.add_argument("--query", required=True)
    bundle_parser.add_argument("--search-mode", default="")
    bundle_parser.add_argument("--top-k", type=int, default=None)
    bundle_parser.add_argument("--question-type", default="")
    bundle_parser.add_argument("--strictness", default="")
    bundle_parser.add_argument(
        "--include-layer",
        dest="include_layers",
        action="append",
        default=None,
    )
    bundle_parser.add_argument("--advanced-json", default="")
    bundle_parser.set_defaults(func=_cmd_explain_read_bundle)

    explain_outcome_parser = subparsers.add_parser(
        "explain-outcome",
        help="Call extensions.abel.stateless.explain_outcome.",
    )
    explain_outcome_parser.add_argument("--query", required=True)
    explain_outcome_parser.add_argument("--search-mode", default="")
    explain_outcome_parser.add_argument("--top-k", type=int, default=None)
    explain_outcome_parser.add_argument("--advanced-json", default="")
    explain_outcome_parser.add_argument("--outcome-mode", default="")
    explain_outcome_parser.add_argument("--focus-strategy", default="")
    explain_outcome_parser.add_argument("--focus-top-n", type=int, default=None)
    explain_outcome_parser.add_argument("--top-driver-count", type=int, default=None)
    explain_outcome_parser.add_argument("--max-paths", type=int, default=None)
    explain_outcome_parser.add_argument("--max-hops", type=int, default=None)
    explain_outcome_parser.add_argument(
        "--include-bayes-evidence",
        action="store_true",
    )
    explain_outcome_parser.set_defaults(func=_cmd_explain_outcome)

    prepare_parser = subparsers.add_parser(
        "search-prepare",
        help="Call extensions.abel.stateful.search_prepare.",
    )
    prepare_parser.add_argument("--query", required=True)
    prepare_parser.add_argument("--intent", default="read")
    prepare_parser.add_argument("--search-mode", default="")
    prepare_parser.add_argument("--top-k", type=int, default=None)
    prepare_parser.add_argument("--advanced-json", default="")
    prepare_parser.add_argument("--max-hops", type=int, default=None)
    prepare_parser.add_argument("--max-nodes", type=int, default=None)
    prepare_parser.add_argument("--multi-snapshot-policy", default="")
    prepare_parser.set_defaults(func=_cmd_search_prepare)

    predict_parser = subparsers.add_parser(
        "predict",
        help="Call extensions.abel.stateful.predict.",
    )
    predict_parser.add_argument("--session-handle", required=True)
    predict_parser.add_argument("--node-ref", required=True)
    predict_parser.set_defaults(func=_cmd_predict)

    what_if_parser = subparsers.add_parser(
        "what-if",
        help="Call extensions.abel.stateful.what_if.",
    )
    what_if_parser.add_argument("--session-handle", required=True)
    what_if_parser.add_argument("--treatment-node-ref", required=True)
    what_if_parser.add_argument("--treatment-value", required=True, type=float)
    what_if_parser.add_argument("--outcome-node-ref", required=True)
    what_if_parser.set_defaults(func=_cmd_what_if)

    return parser


def _finalize_result(args: argparse.Namespace, result: dict[str, Any]) -> dict[str, Any]:
    output = dict(result)
    pick_fields = (args.pick_fields or "").strip()
    if pick_fields:
        output = _apply_pick_fields(output, pick_fields)
    max_chars = int(args.max_description_chars or 0)
    if max_chars > 0:
        output = _truncate_description_fields(output, max_chars)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command != "auth-status":
        _load_env_file(args.env_file)
    result = _finalize_result(args, args.func(args))
    dump = json.dumps(result, ensure_ascii=False, separators=(",", ":")) if args.compact else json.dumps(result, ensure_ascii=False, indent=2)
    print(dump)
    return 0 if result.get("ok") is not False else 1


if __name__ == "__main__":
    sys.exit(main())
