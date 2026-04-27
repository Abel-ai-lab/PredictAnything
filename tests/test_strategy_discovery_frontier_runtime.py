from __future__ import annotations

import json
from pathlib import Path

from abel_strategy_discovery import narrative_impl as ni


def _seed_discovery() -> dict:
    return {
        "ticker": "TSLA",
        "target_asset": "TSLA",
        "target_node": "TSLA.price",
        "source": "abel_live",
        "parents": ["AAPL"],
        "blanket_new": ["MSFT"],
        "children": ["BTCUSD"],
        "K_discovery": 3,
        "backtest": {"start": "2020-01-01"},
        "created_at": "2026-04-22T00:00:00+00:00",
    }


def test_evidence_frontier_is_the_current_frontier_runtime_surface(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v1", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())

    ni.render_session(session)

    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    frontier_md = (session / ni.FRONTIER_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    agent_context = (session / ni.AGENT_CONTEXT_FILENAME).read_text(encoding="utf-8")

    assert ledger["graph_discovery_source"] == "abel_live"
    assert ledger["graph_discovery_k"] == 3
    assert frontier["graph_priority"]["graph_candidates_available"] is True
    assert "## Graph Priority" in frontier_md
    assert "## Evidence Frontier" in agent_context
    assert "## Research Journal" in agent_context


def test_seed_only_session_keeps_graph_first_gap_visible(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v2", tmp_path / "research")

    ledger = json.loads((session / ni.EVIDENCE_LEDGER_FILENAME).read_text(encoding="utf-8"))
    frontier = json.loads((session / ni.FRONTIER_JSON_FILENAME).read_text(encoding="utf-8"))
    readme = (session / "README.md").read_text(encoding="utf-8")

    assert ledger["graph_discovery_source"] == "pending"
    assert frontier["graph_priority"]["graph_candidates_available"] is False
    assert "discovery_source: `pending`" in readme


def test_failed_live_discovery_attempt_surfaces_as_auth_or_runtime_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def _raise_discovery(*_args, **_kwargs):
        raise RuntimeError("auth missing for test")

    monkeypatch.setattr(ni, "fetch_live_discovery", _raise_discovery)

    try:
        ni.init_session_dir(
            "TSLA",
            "frontier-v3",
            tmp_path / "research",
            discover=True,
        )
    except RuntimeError as exc:
        assert "auth missing for test" in str(exc)
    else:
        raise AssertionError("live discovery failure should remain visible")


def test_unexpected_live_discovery_exception_stays_visible(tmp_path: Path, monkeypatch) -> None:
    def _raise_discovery(*_args, **_kwargs):
        raise Exception("404 Client Error: Not Found for url: https://cap.abel.ai/api/cap")

    monkeypatch.setattr(ni, "fetch_live_discovery", _raise_discovery)

    try:
        ni.init_session_dir(
            "NFLX",
            "frontier-v3f",
            tmp_path / "research",
            discover=True,
        )
    except Exception as exc:
        assert "404 Client Error" in str(exc)
    else:
        raise AssertionError("unexpected live discovery failure should remain visible")
