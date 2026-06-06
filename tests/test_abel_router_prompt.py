from pathlib import Path


def test_abel_router_skill_has_explicit_three_way_routing() -> None:
    text = Path("skills/abel/SKILL.md").read_text(encoding="utf-8").lower()
    assert "main entrypoint" in text
    assert "starts an abel workflow" in text
    assert "initialize abel if needed" in text
    assert (
        "python3 <abel-skill-root>/../abel-common/python/abel_common/cap/graph_probe.py auth-status"
        in text
    )
    assert "do not use a current-working-directory relative" in text
    assert "abel-invest" in text
    assert "abel-ask" in text
    assert "abel-auth" in text
    assert "original request" in text
    assert "references/setup-guide.md" in text
    assert "stock options" in text
    assert "dedicated options-strategy workflow" in text
    assert "underlying-stock" in text
    assert "trading strategy" in text
    assert "candidate discovery" in text
    assert "life-investment decisions" in text


def test_abel_ask_boundary_uses_discovery_and_life_decision_not_model_effects() -> None:
    text = Path("skills/abel-ask/SKILL.md").read_text(encoding="utf-8").lower()
    assert "candidate discovery" in text
    assert "life/business" in text
    assert "product intent" in text
    assert "execution route" in text
    assert "handoff" in text
    assert "abel-invest" in text
    assert "buy/sell" in text
    assert "backtesting" in text
    assert "observe_predict_resolved_time" not in text
    assert "intervene_time_lag" not in text
    assert "observe-dual" not in text


def test_abel_ask_narrative_usage_keeps_search_prepare_as_scout_only() -> None:
    text = Path("skills/abel-ask/references/narrative-probe-usage.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "search-prepare" in text
    assert "richer scout" in text
    assert "mapping status" in text
    assert "return to graph cap" in text
    assert "scoring or simulation" in text
    assert "explain-outcome" not in text
    assert "out-of-scope" not in text


def test_abel_ask_public_market_candidate_boundary_allows_tickers_and_invest_offer() -> None:
    text = Path("skills/abel-ask/references/intents/candidate-discovery.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "candidate list" in text
    assert "named tickers is allowed" in text
    assert "upstream/downstream watchlist" in text
    assert "default to ending" in text
    assert "$abel-invest" in text
    assert "tradable strategy discovery" in text
    report = Path("skills/abel-ask/assets/report-guide.md").read_text(
        encoding="utf-8"
    )
    report_lower = report.lower()
    assert "explicit offer to continue in `$abel-invest`" in report_lower
    assert "tradable strategy discovery" in report_lower
    probe_usage = Path("skills/abel-ask/references/probe-usage.md").read_text(
        encoding="utf-8"
    ).lower()
    ask_text = "\n".join(
        [
            text,
            report_lower,
            probe_usage,
            Path("skills/abel-ask/references/routes/proxy-routed.md")
            .read_text(encoding="utf-8")
            .lower(),
            Path("skills/abel-ask/references/narrative-probe-usage.md")
            .read_text(encoding="utf-8")
            .lower(),
        ]
    )
    assert "observe-dual" not in ask_text
    assert "node_price" not in ask_text
    assert "node_volume" not in ask_text


def test_strategy_discovery_skill_explains_workspace_first_boundary() -> None:
    text = Path("skills/abel-invest/SKILL.md").read_text(encoding="utf-8").lower()
    assert "workspace-first" in text
    assert "reuse the default workspace" in text
    assert "bootstrap the workspace" in text
    assert "abel-auth" in text
    assert "references/data-driven-construction.md" in text
    assert "first serious recorded alpha" in text
    assert "first-look data scout" in text
    assert "prepare-branch" in text
    assert "sharpe > 2" in text
    assert "research/<ticker>/<session_id>/scratch/" in text
    assert "flat/no-signal branch" in text
    assert "diagnostic table" in text
    assert "scored candidate-shaped variants" in text
    assert "gates estimate reliability" in text
    assert "hand-written single-mechanism branches are diagnostics" in text
    assert "gauntlet" not in text
    assert "survivor" not in text
