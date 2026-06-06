"""Graph frontier discovery and expansion helpers."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from abel_invest.narrative_core.contracts.branch_spec import (
    default_graph_node_id,
    normalize_graph_node_ref,
    ordered_unique_strings,
    split_graph_node_id,
)
from abel_invest.narrative_core.contracts.constants import (
    DEFAULT_BACKTEST_START,
    GRAPH_FRONTIER_FILENAME,
)
from abel_invest.narrative_core.evidence.frontier import increment_count, render_inline_counts
from abel_invest.narrative_core.io import _now
from abel_invest.workspace_core.doctor import build_auth_recovery_instruction, workspace_command
from abel_invest.workspace_core.edge_runtime import resolve_runtime_auth_env_file
from abel_invest.workspace_core.workspace import resolve_workspace_entry


def fetch_live_graph_frontier(
    ticker: str,
    *,
    limit: int,
    backtest_start: str,
) -> dict:
    try:
        from abel_edge.plugins.abel.credentials import (
            MissingAbelApiKeyError,
            require_api_key,
        )
        from abel_edge.plugins.abel.discover import discover_graph_payload
    except ImportError as exc:
        workspace_root, _ = resolve_workspace_entry()
        command_prefix = workspace_command(workspace_root, None) if workspace_root else "abel-invest"
        raise RuntimeError(
            "Live Abel discovery requires abel-edge with the Abel plugin installed. "
            f"Run `{command_prefix} doctor` in the workspace, follow its env next_step, "
            "rerun doctor, then retry."
        ) from exc
    workspace_root, _ = resolve_workspace_entry()
    if workspace_root is not None:
        auth_env = resolve_runtime_auth_env_file(workspace_root)
        if auth_env is not None:
            os.environ.setdefault("ABEL_AUTH_ENV_FILE", str(auth_env))

    try:
        require_api_key()
    except MissingAbelApiKeyError as exc:
        command_prefix = workspace_command(workspace_root, None) if workspace_root else "abel-invest"
        raise RuntimeError(
            "init-session live graph discovery is blocked on Abel auth. "
            "No reusable auth was found. "
            f"{build_auth_recovery_instruction(workspace_root or Path.cwd())}\n\n"
            f"After auth is ready, retry `{command_prefix} init-session --ticker "
            f"{ticker.upper()} --exp-id <exp-id>`."
        ) from exc

    payload = discover_graph_payload(ticker.upper(), mode="all", limit=limit)
    return graph_frontier_from_discovery_payload(
        payload,
        backtest_start=backtest_start,
        expansion_mode="all",
        expansion_limit=limit,
    )


def fetch_live_graph_expansion(
    anchor_node: str,
    *,
    mode: str,
    limit: int,
) -> dict:
    try:
        from abel_edge.plugins.abel.credentials import (
            MissingAbelApiKeyError,
            require_api_key,
        )
        from abel_edge.plugins.abel.discover import discover_graph_payload
    except ImportError as exc:
        workspace_root, _ = resolve_workspace_entry()
        command_prefix = workspace_command(workspace_root, None) if workspace_root else "abel-invest"
        raise RuntimeError(
            "Live Abel frontier expansion requires abel-edge with the Abel plugin installed. "
            f"Run `{command_prefix} doctor` in the workspace, follow its env next_step, "
            "rerun doctor, then retry."
        ) from exc
    workspace_root, _ = resolve_workspace_entry()
    if workspace_root is not None:
        auth_env = resolve_runtime_auth_env_file(workspace_root)
        if auth_env is not None:
            os.environ.setdefault("ABEL_AUTH_ENV_FILE", str(auth_env))

    try:
        require_api_key()
    except MissingAbelApiKeyError as exc:
        raise RuntimeError(
            "frontier expand is blocked on Abel auth. "
            "No reusable auth was found. "
            f"{build_auth_recovery_instruction(workspace_root or Path.cwd())}"
        ) from exc

    return discover_graph_payload(anchor_node, mode=mode, limit=limit)


def write_graph_frontier_from_discovery_payload(session: Path, discovery_data: dict) -> None:
    write_graph_frontier(
        session,
        graph_frontier_from_discovery_payload(
            discovery_data,
            backtest_start=(discovery_data.get("backtest") or {}).get("start", DEFAULT_BACKTEST_START),
            expansion_mode=str(discovery_data.get("mode") or "all"),
            expansion_limit=int(discovery_data.get("K_discovery") or 10),
        ),
    )


def graph_frontier_path(session: Path) -> Path:
    return session / GRAPH_FRONTIER_FILENAME


def load_graph_frontier(session: Path) -> dict:
    path = graph_frontier_path(session)
    if not path.exists():
        return build_pending_graph_frontier(
            session.parent.name.upper(),
            backtest_start=DEFAULT_BACKTEST_START,
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_graph_frontier(session: Path, frontier: dict) -> None:
    graph_frontier_path(session).write_text(
        json.dumps(frontier, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def print_graph_frontier_status(session: Path) -> None:
    frontier = load_graph_frontier(session)
    facts = graph_frontier_facts(frontier)
    print(f"Session: {session.name}")
    print(f"Graph frontier: {session / GRAPH_FRONTIER_FILENAME}")
    print(f"Target node: {facts['target_node']}")
    print(f"Source: {facts['source']}")
    print(f"Nodes: {facts['node_count']}")
    print(f"Expansions: {facts['expansion_count']}")
    print(f"Expanded anchors: {facts['expanded_anchor_count']}")
    print(f"Unexpanded nodes: {facts['unexpanded_node_count']}")
    print(f"Fields: {render_inline_counts(facts['field_counts'])}")
    print(f"Roles: {render_inline_counts(facts['role_counts'])}")
    print(
        "Search boundary: frontier coverage is context, not exhaustion; "
        "before stopping below target, check whether higher-ceiling search axes remain."
    )


def graph_frontier_facts(frontier: dict) -> dict[str, object]:
    nodes = [node for node in frontier.get("nodes") or [] if isinstance(node, dict)]
    expansions = [item for item in frontier.get("expansions") or [] if isinstance(item, dict)]
    expanded_anchors = {
        str(item.get("anchor_node") or "").strip()
        for item in expansions
        if str(item.get("anchor_node") or "").strip()
    }
    field_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for node in nodes:
        increment_count(field_counts, str(node.get("field") or "unknown"))
        roles = node.get("discovery_roles") or ["unknown"]
        for role in roles:
            increment_count(role_counts, str(role or "unknown"))
    unexpanded = [
        node
        for node in nodes
        if str(node.get("node_id") or "") not in expanded_anchors
        and "target" not in set(str(role) for role in node.get("discovery_roles") or [])
    ]
    return {
        "target_node": str(frontier.get("target_node") or "unknown"),
        "source": str(frontier.get("source") or "unknown"),
        "node_count": len(nodes),
        "expansion_count": len(expansions),
        "expanded_anchor_count": len(expanded_anchors),
        "unexpanded_node_count": len(unexpanded),
        "field_counts": dict(sorted(field_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
    }


def build_pending_graph_frontier(ticker: str, *, backtest_start: str) -> dict:
    now = _now()
    target_asset = str(ticker or "").strip().upper()
    target_node = default_graph_node_id(target_asset)
    return {
        "schema_version": 1,
        "target_asset": target_asset,
        "target_node": target_node,
        "requested_window": {"start": backtest_start, "end": None},
        "source": "pending",
        "created_at": now,
        "updated_at": now,
        "nodes": [
            build_frontier_node(
                node_id=target_node,
                roles=["target"],
                discovered_from="session",
                depth=0,
                seen_at=now,
            )
        ],
        "expansions": [],
    }


def merge_graph_frontier_expansion(
    frontier: dict,
    payload: dict,
    *,
    anchor_node: str,
    mode: str,
    limit: int,
) -> tuple[dict, dict]:
    now = str(payload.get("created_at") or _now())
    anchor_node = normalize_graph_node_ref(anchor_node)
    updated = dict(frontier)
    updated.setdefault("schema_version", 1)
    updated.setdefault("target_asset", split_graph_node_id(anchor_node)[0])
    updated.setdefault("target_node", anchor_node)
    updated.setdefault("requested_window", {"start": DEFAULT_BACKTEST_START, "end": None})
    updated["source"] = "abel_live" if updated.get("source") in {"", "pending", None} else updated.get("source")
    updated["updated_at"] = now

    node_map = {
        str(node.get("node_id") or ""): dict(node)
        for node in updated.get("nodes") or []
        if isinstance(node, dict) and str(node.get("node_id") or "")
    }
    anchor = node_map.get(anchor_node)
    if anchor is None:
        anchor = build_frontier_node(
            node_id=anchor_node,
            roles=["expansion_anchor"],
            discovered_from="agent",
            depth=0,
            seen_at=now,
        )
        node_map[anchor_node] = anchor
    anchor["last_expanded_at"] = now
    anchor_depth = int(anchor.get("depth") or 0)

    new_nodes: list[str] = []
    updated_nodes: list[str] = []
    for section, role in (("parents", "parent"), ("blanket_new", "blanket"), ("children", "child")):
        for item in payload.get(section) or []:
            node_id = normalize_graph_node_ref(graph_node_id_from_item(item))
            if not node_id or node_id == anchor_node:
                continue
            roles = graph_roles_from_item(item, fallback=role)
            if node_id not in node_map:
                node_map[node_id] = build_frontier_node(
                    node_id=node_id,
                    roles=roles,
                    discovered_from=anchor_node,
                    depth=anchor_depth + 1,
                    seen_at=now,
                )
                new_nodes.append(node_id)
                continue
            existing = node_map[node_id]
            existing["discovery_roles"] = ordered_unique_strings(
                list(existing.get("discovery_roles") or []) + roles
            )
            existing["discovered_from"] = ordered_unique_strings(
                list(existing.get("discovered_from") or []) + [anchor_node]
            )
            existing["depth"] = min(int(existing.get("depth") or anchor_depth + 1), anchor_depth + 1)
            updated_nodes.append(node_id)

    expansion = {
        "expansion_id": frontier_expansion_id(anchor_node=anchor_node, mode=mode, timestamp=now),
        "anchor_node": anchor_node,
        "mode": mode,
        "limit": limit,
        "source": str(payload.get("source") or "abel_live"),
        "new_nodes": ordered_unique_strings(new_nodes),
        "updated_nodes": ordered_unique_strings(updated_nodes),
        "created_at": now,
    }
    expansions = [item for item in updated.get("expansions") or [] if isinstance(item, dict)]
    expansions.append(expansion)
    updated["nodes"] = sorted(node_map.values(), key=lambda item: str(item.get("node_id") or ""))
    updated["expansions"] = expansions
    return updated, expansion


def graph_frontier_from_discovery_payload(
    payload: dict,
    *,
    backtest_start: str,
    expansion_mode: str,
    expansion_limit: int,
) -> dict:
    now = str(payload.get("created_at") or _now())
    target_asset = str(payload.get("target_asset") or payload.get("ticker") or "").strip().upper()
    target_node = str(payload.get("target_node") or "").strip() or default_graph_node_id(target_asset)
    nodes: dict[str, dict] = {}

    def remember(node: dict) -> None:
        key = str(node.get("node_id") or "").strip()
        if not key:
            return
        if key not in nodes:
            nodes[key] = node
            return
        existing = nodes[key]
        existing["discovery_roles"] = ordered_unique_strings(
            list(existing.get("discovery_roles") or []) + list(node.get("discovery_roles") or [])
        )
        existing["discovered_from"] = ordered_unique_strings(
            list(existing.get("discovered_from") or []) + list(node.get("discovered_from") or [])
        )
        existing["depth"] = min(int(existing.get("depth") or 0), int(node.get("depth") or 0))

    remember(
        build_frontier_node(
            node_id=target_node,
            roles=["target"],
            discovered_from="session",
            depth=0,
            seen_at=now,
        )
    )
    for section, role in (("parents", "parent"), ("blanket_new", "blanket"), ("children", "child")):
        for item in payload.get(section) or []:
            node_id = graph_node_id_from_item(item)
            if not node_id or node_id == target_node:
                continue
            remember(
                build_frontier_node(
                    node_id=node_id,
                    roles=graph_roles_from_item(item, fallback=role),
                    discovered_from=target_node,
                    depth=1,
                    seen_at=now,
                )
            )
    expansion_nodes = [node_id for node_id in sorted(nodes) if node_id != target_node]
    return {
        "schema_version": 1,
        "target_asset": target_asset,
        "target_node": target_node,
        "requested_window": {"start": backtest_start, "end": None},
        "source": str(payload.get("source") or "abel_live"),
        "created_at": now,
        "updated_at": now,
        "nodes": list(nodes.values()),
        "expansions": [
            {
                "expansion_id": frontier_expansion_id(anchor_node=target_node, mode=expansion_mode, timestamp=now),
                "anchor_node": target_node,
                "mode": expansion_mode,
                "limit": expansion_limit,
                "source": str(payload.get("source") or "abel_live"),
                "new_nodes": expansion_nodes,
                "updated_nodes": [],
                "created_at": now,
            }
        ],
    }


def graph_frontier_to_discovery(frontier: dict) -> dict:
    target_asset = str(frontier.get("target_asset") or "").strip().upper()
    target_node = str(frontier.get("target_node") or "").strip() or default_graph_node_id(target_asset)
    discovery = {
        "ticker": target_asset,
        "target_asset": target_asset,
        "target_node": target_node,
        "source": frontier.get("source", "unknown"),
        "parents": [],
        "blanket_new": [],
        "children": [],
        "K_discovery": 0,
        "backtest": {"start": (frontier.get("requested_window") or {}).get("start", DEFAULT_BACKTEST_START)},
        "created_at": frontier.get("created_at", "unknown"),
    }
    for node in frontier.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id") or "").strip()
        if not node_id or node_id == target_node:
            continue
        item = {
            "node_id": node_id,
            "ticker": str(node.get("asset") or "").strip().upper(),
            "field": str(node.get("field") or "price").strip(),
        }
        roles = [str(role) for role in node.get("discovery_roles") or []]
        if "parent" in roles:
            discovery["parents"].append(item)
        elif "child" in roles:
            discovery["children"].append(item)
        else:
            item["roles"] = roles or ["neighbor"]
            discovery["blanket_new"].append(item)
    discovery["K_discovery"] = (
        len(discovery["parents"]) + len(discovery["blanket_new"]) + len(discovery["children"])
    )
    return discovery


def build_frontier_node(
    *,
    node_id: str,
    roles: list[str],
    discovered_from: str,
    depth: int,
    seen_at: str,
) -> dict:
    asset, field = split_graph_node_id(node_id)
    return {
        "node_id": node_id,
        "asset": asset,
        "field": field,
        "discovery_roles": ordered_unique_strings(roles),
        "discovered_from": ordered_unique_strings([discovered_from]),
        "depth": depth,
        "first_seen_at": seen_at,
        "last_expanded_at": None,
        "availability_summary": None,
        "branch_usage": [],
    }


def graph_node_id_from_item(item: object) -> str:
    if isinstance(item, dict):
        node_id = str(item.get("node_id") or "").strip()
        if node_id:
            return node_id
        asset = str(item.get("ticker") or item.get("symbol") or "").strip().upper()
        field = str(item.get("field") or "price").strip().lower()
        return f"{asset}.{field}" if asset else ""
    value = str(item or "").strip()
    if not value:
        return ""
    return value if "." in value else default_graph_node_id(value)


def graph_roles_from_item(item: object, *, fallback: str) -> list[str]:
    roles: list[str] = []
    if isinstance(item, dict):
        roles = [str(role).strip() for role in item.get("roles") or [] if str(role).strip()]
    return ordered_unique_strings([fallback, *roles])


def frontier_expansion_id(*, anchor_node: str, mode: str, timestamp: str) -> str:
    safe_anchor = re.sub(r"[^A-Za-z0-9]+", "-", anchor_node).strip("-").lower()
    safe_mode = re.sub(r"[^A-Za-z0-9]+", "-", mode).strip("-").lower()
    safe_time = re.sub(r"[^0-9A-Za-z]+", "", timestamp)[:15]
    return f"{safe_time}-{safe_anchor}-{safe_mode}".strip("-")
