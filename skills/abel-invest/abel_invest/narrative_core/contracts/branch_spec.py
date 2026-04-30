"""Branch declaration and prepared-input contract helpers."""

from __future__ import annotations

import yaml
from pathlib import Path

from abel_invest.narrative_core.contracts.constants import (
    COMPLEXITY_CLASSES,
    DECLARATION_PLACEHOLDER_VALUES,
    DEFAULT_BACKTEST_START,
    EVIDENCE_INTENTS,
    EXPLORATION_ROLES,
    GRAPH_INPUT_CLAIMS,
    INPUT_CLAIMS,
    MODEL_FAMILIES,
)
from abel_invest.narrative_core.io import _now
from abel_invest.narrative_core.contracts.paths import branch_spec_path
from abel_invest.narrative_core.readiness import readiness_usable_tickers


def normalize_hypothesis_text(value: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return (
        "Hypothesis missing. Before the next round, state the causal claim, "
        "expected sign, and invalidation condition explicitly."
    )


def has_explicit_hypothesis(value: str) -> bool:
    text = str(value or "").strip()
    return bool(
        text
        and text != "No hypothesis supplied."
        and not text.startswith("Hypothesis missing.")
    )


def _get_backtest_start(discovery: dict) -> str:
    backtest = discovery.get("backtest") or {}
    if isinstance(backtest, dict):
        start = backtest.get("start")
        if start:
            return str(start)
    return DEFAULT_BACKTEST_START


def branch_requested_start(branch: Path, discovery: dict) -> str:
    branch_spec = load_branch_spec(branch)
    requested = str(branch_spec.get("requested_start") or "").strip()
    if requested:
        return requested
    return _get_backtest_start(discovery)


def normalize_evidence_intent(branch_spec: dict) -> str:
    configured = str(branch_spec.get("evidence_intent") or "").strip().lower()
    if configured in EVIDENCE_INTENTS:
        return configured
    return ""


def normalize_input_claim(branch_spec: dict) -> str:
    configured = str(branch_spec.get("input_claim") or "").strip().lower()
    if configured in INPUT_CLAIMS:
        return configured
    return ""


def normalize_model_family(branch_spec: dict) -> str:
    configured = str(branch_spec.get("model_family") or "").strip().lower()
    if configured in MODEL_FAMILIES:
        return configured
    return "unspecified"


def normalize_complexity_class(branch_spec: dict) -> str:
    configured = str(branch_spec.get("complexity_class") or "").strip().lower()
    if configured in COMPLEXITY_CLASSES:
        return configured
    model_family = normalize_model_family(branch_spec)
    if model_family in {"tree_model", "learned_model", "ensemble"}:
        return "learned_model"
    if model_family == "hybrid":
        return "hybrid"
    return "unspecified"


def normalize_exploration_role(branch_spec: dict) -> str:
    configured = str(branch_spec.get("exploration_role") or "").strip().lower()
    if configured in EXPLORATION_ROLES:
        return configured
    evidence_intent = normalize_evidence_intent(branch_spec)
    if evidence_intent == "control":
        return "control"
    if evidence_intent == "diagnostic":
        return "diagnostic"
    if evidence_intent == "candidate":
        return "candidate"
    return "unspecified"


def branch_selected_inputs(branch_spec: dict) -> list[str]:
    raw = branch_spec.get("selected_inputs")
    if not isinstance(raw, list):
        return []
    return ordered_unique_upper(raw)


def ordered_unique_upper(values) -> list[str]:
    return ordered_unique_strings(str(item or "").strip().upper() for item in values)


def ordered_unique_strings(values) -> list[str]:
    selected: list[str] = []
    for item in values:
        value = str(item or "").strip()
        if value and value not in selected:
            selected.append(value)
    return selected


def canonicalize_branch_spec_inputs(payload: dict) -> dict:
    branch_spec = dict(payload)
    selected = branch_selected_inputs(branch_spec)
    if selected or "selected_inputs" in branch_spec:
        branch_spec["selected_inputs"] = selected
    branch_spec.pop("selected_drivers", None)
    return branch_spec


def branch_declaration_status(branch_spec: dict) -> dict[str, object]:
    hypothesis = str(branch_spec.get("hypothesis") or "").strip()
    evidence_intent = normalize_evidence_intent(branch_spec)
    input_claim = normalize_input_claim(branch_spec)
    mechanism_family = str(branch_spec.get("mechanism_family") or "").strip().lower()
    invalidation_condition = str(branch_spec.get("invalidation_condition") or "").strip()
    requested_start = str(branch_spec.get("requested_start") or "").strip()
    selected_inputs = branch_selected_inputs(branch_spec)

    gaps: list[str] = []
    if not has_explicit_hypothesis(hypothesis):
        gaps.append("hypothesis")
    if evidence_intent not in EVIDENCE_INTENTS:
        gaps.append("evidence_intent")
    if input_claim not in INPUT_CLAIMS:
        gaps.append("input_claim")
    if mechanism_family in DECLARATION_PLACEHOLDER_VALUES:
        gaps.append("mechanism_family")
    if not invalidation_condition:
        gaps.append("invalidation_condition")
    if not requested_start:
        gaps.append("requested_start")
    if input_claim in GRAPH_INPUT_CLAIMS and not selected_inputs:
        gaps.append("selected_inputs")
    if evidence_intent == "draft":
        gaps.append("evidence_intent:draft")

    return {
        "protocol_complete": not gaps,
        "protocol_gaps": gaps,
        "hypothesis": hypothesis,
        "evidence_intent": evidence_intent,
        "input_claim": input_claim,
        "mechanism_family": mechanism_family,
        "model_family": normalize_model_family(branch_spec),
        "complexity_class": normalize_complexity_class(branch_spec),
        "exploration_role": normalize_exploration_role(branch_spec),
        "invalidation_condition": invalidation_condition,
        "requested_start": requested_start,
        "selected_inputs": selected_inputs,
    }


def branch_declaration_status_for_branch(branch: Path) -> dict[str, object]:
    return branch_declaration_status(load_branch_spec(branch))


def load_branch_spec(branch: Path) -> dict:
    path = branch_spec_path(branch)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return canonicalize_branch_spec_inputs(payload) if isinstance(payload, dict) else {}


def write_branch_spec(branch: Path, payload: dict) -> None:
    payload = canonicalize_branch_spec_inputs(payload)
    branch_spec_path(branch).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def discovery_candidate_tickers(discovery: dict) -> list[str]:
    target = str(discovery.get("ticker") or "").strip().upper()
    ordered: list[str] = []
    for section in ("parents", "blanket_new", "children"):
        for item in discovery.get(section) or []:
            if isinstance(item, dict):
                ticker = str(item.get("ticker") or "").strip().upper()
            else:
                ticker = str(item or "").strip().upper()
            if not ticker or ticker == target or ticker in ordered:
                continue
            ordered.append(ticker)
    return ordered


def suggest_branch_drivers(discovery: dict, readiness: dict, *, limit: int = 5) -> list[str]:
    discovered = discovery_candidate_tickers(discovery)
    usable = set(readiness_usable_tickers(readiness))
    prioritized = [ticker for ticker in discovered if ticker in usable]
    fallback = [ticker for ticker in discovered if ticker not in usable]
    return (prioritized + fallback)[:limit]


def build_default_branch_spec(*, branch: Path, discovery: dict, readiness: dict) -> dict:
    suggested = suggest_branch_drivers(discovery, readiness, limit=5)
    selected = suggested[: min(3, len(suggested))]
    graph_first = bool(selected)
    return {
        "version": 2,
        "branch_id": branch.name,
        "target": discovery.get("ticker", branch.parent.parent.parent.name.upper()),
        "hypothesis": "",
        "evidence_intent": "draft",
        "input_claim": "graph_supported" if graph_first else "target_only",
        "mechanism_family": "unspecified",
        "invalidation_condition": "",
        "model_family": "unspecified",
        "complexity_class": "unspecified",
        "exploration_role": "candidate",
        "parent_branch_id": "",
        "requested_start": _get_backtest_start(discovery),
        "resolved_start_policy": "requested",
        "overlap_mode": "target_only",
        "selected_inputs": selected,
        "suggested_drivers": suggested,
        "data_requirements": {
            "timeframe": "1d",
            "fields": ["close"],
        },
    }


def branch_dependencies_payload(
    *,
    branch: Path,
    branch_spec: dict,
    target: str,
    selected_inputs: list[str],
    requested_start: str,
) -> dict:
    selected_inputs = ordered_unique_upper(selected_inputs)
    return {
        "version": 1,
        "branch_id": branch.name,
        "target": target,
        "selected_inputs": selected_inputs,
        "requested_start": requested_start,
        "overlap_mode": branch_spec.get("overlap_mode") or "target_only",
        "data_requirements": branch_spec.get("data_requirements") or {"timeframe": "1d"},
        "prepared_at": _now(),
    }


def canonicalize_dependencies_payload(payload: dict) -> dict:
    dependencies = dict(payload)
    raw = dependencies.get("selected_inputs")
    selected = ordered_unique_upper(raw if isinstance(raw, list) else [])
    if selected or "selected_inputs" in dependencies:
        dependencies["selected_inputs"] = selected
    dependencies.pop("selected_drivers", None)
    return dependencies


def build_runtime_profile_payload(*, target: str) -> dict:
    return {
        "profile": "daily",
        "target": target,
        "decision_event": "bar_close",
        "execution_delay_bars": 1,
        "return_basis": "close_to_close",
    }


def build_execution_constraints_payload(branch_spec: dict) -> dict:
    payload = {"long_only": bool(branch_spec.get("long_only", False))}
    position_bounds = branch_spec.get("position_bounds")
    if isinstance(position_bounds, (list, tuple)) and len(position_bounds) == 2:
        payload["position_bounds"] = [float(position_bounds[0]), float(position_bounds[1])]
    return payload


def build_data_manifest_payload(
    *,
    target: str,
    selected_inputs: list[str],
    cache_payload: dict,
    readiness: dict,
) -> dict:
    selected_inputs = ordered_unique_upper(selected_inputs)
    cache_results = {
        str(item.get("symbol") or "").strip().upper(): item
        for item in (cache_payload.get("results") or [])
        if isinstance(item, dict) and str(item.get("symbol") or "").strip()
    }
    readiness_results = {
        str(item.get("ticker") or "").strip().upper(): item
        for item in (readiness.get("results") or [])
        if isinstance(item, dict) and str(item.get("ticker") or "").strip()
    }
    feeds: list[dict[str, object]] = []
    ordered_symbols = [target] + [ticker for ticker in selected_inputs if ticker != target]
    adapter = str(cache_payload.get("adapter") or "abel")
    path = cache_payload.get("path")
    timeframe = str(cache_payload.get("timeframe") or "1d")
    profile = str(cache_payload.get("profile") or "daily")
    cache_root = cache_payload.get("cache_root")
    for symbol in ordered_symbols:
        cache_item = cache_results.get(symbol, {})
        readiness_item = readiness_results.get(symbol, {})
        feed_entry = {
            "name": "primary" if symbol == target else symbol,
            "symbol": symbol,
            "role": "target" if symbol == target else "driver",
            "adapter": adapter,
            "timeframe": timeframe,
            "profile": profile,
            "ok": bool(cache_item.get("ok", False)),
            "row_count": int(cache_item.get("row_count", 0) or 0),
            "available_range": cache_item.get("available_range") or {},
            "readiness_status": readiness_item.get("status", "unknown"),
            "covers_requested_start": bool(readiness_item.get("covers_requested_start", False)),
        }
        if cache_root:
            feed_entry["cache_root"] = cache_root
        if path:
            feed_entry["path"] = path
        feeds.append(feed_entry)
    return {
        "version": 1,
        "target": target,
        "selected_inputs": selected_inputs,
        "feeds": feeds,
    }


def canonicalize_data_manifest_payload(payload: dict) -> dict:
    manifest = dict(payload)
    raw_selected = manifest.get("selected_inputs")
    selected = ordered_unique_upper(raw_selected if isinstance(raw_selected, list) else [])
    feeds: list[dict[str, object]] = []
    seen_feeds: set[str] = set()
    for item in manifest.get("feeds") or []:
        if not isinstance(item, dict):
            continue
        feed = dict(item)
        symbol = str(feed.get("symbol") or "").strip().upper()
        name = str(feed.get("name") or symbol or "").strip()
        key = name or symbol
        if not key or key in seen_feeds:
            continue
        if symbol:
            feed["symbol"] = symbol
        if name:
            feed["name"] = name
        feeds.append(feed)
        seen_feeds.add(key)
    manifest["selected_inputs"] = selected
    manifest.pop("selected_drivers", None)
    manifest["feeds"] = feeds
    return manifest


def build_probe_samples_payload(
    *,
    target: str,
    requested_start: str,
    data_manifest: dict,
) -> dict:
    feeds = data_manifest.get("feeds") or []
    target_feed = next(
        (item for item in feeds if item.get("role") == "target"),
        {},
    )
    available_range = (target_feed.get("available_range") or {}) if isinstance(target_feed, dict) else {}
    start = str(available_range.get("start") or requested_start or "").strip()
    end = str(available_range.get("end") or start or "").strip()
    samples: list[str] = []
    if start and end:
        try:
            dates = pd.date_range(start=start, end=end, periods=3, tz="UTC")
            samples = [str(ts.date()) for ts in dates]
        except Exception:
            samples = [item for item in [start, end] if item]
    return {
        "version": 1,
        "target": target,
        "requested_start": requested_start,
        "sample_decision_dates": samples,
    }


def build_context_guide_markdown(
    *,
    target: str,
    runtime_profile: dict,
    execution_constraints: dict,
    data_manifest: dict,
) -> str:
    feed_names = [
        str(item.get("name"))
        for item in (data_manifest.get("feeds") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    lines = [
        f"# {target} Branch Context Guide",
        "",
        "## Runtime",
        f"- profile: `{runtime_profile.get('profile', 'daily')}`",
        f"- decision_event: `{runtime_profile.get('decision_event', 'bar_close')}`",
        f"- execution_delay_bars: `{runtime_profile.get('execution_delay_bars', 1)}`",
        f"- return_basis: `{runtime_profile.get('return_basis', 'close_to_close')}`",
        "",
        "## Execution Constraints",
        f"- long_only: `{execution_constraints.get('long_only', False)}`",
        f"- position_bounds: `{execution_constraints.get('position_bounds', 'unbounded')}`",
        "",
        "## Available Feeds",
        f"- names: `{', '.join(feed_names) or 'primary only'}`",
        "- use `ctx.target.series(\"close\")` for target history",
        "- use `ctx.feed(\"<name>\").asof_series(\"close\")` for aligned driver history",
        "- use `ctx.points()` when you need path-sensitive cross-calendar logic",
        "",
        "## Declaration Fields",
        "- `hypothesis`: concrete claim being tested",
        "- `evidence_intent`: candidate, control, diagnostic, or draft",
        "- `input_claim`: graph_supported, target_only, supplement, or mixed",
        "- `mechanism_family`: factual mechanism label",
        "- `invalidation_condition`: what would weaken the claim",
        "",
        "## Protocol Checklist",
        "1. Inspect `probe_samples.json` and `data_manifest.json`.",
        "2. Edit `engine.py` against `DecisionContext`.",
        "3. Run `abel-invest debug-branch --branch ...` first to read semantic preflight.",
        "4. Only record a round after the branch expresses a real mechanism.",
    ]
    return "\n".join(lines) + "\n"
