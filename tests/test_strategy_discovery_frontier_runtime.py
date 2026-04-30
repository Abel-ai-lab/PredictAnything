from __future__ import annotations

import json
import sys
from pathlib import Path

from abel_invest import narrative_impl as ni


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
    ni.write_graph_frontier_from_discovery_payload(session, _seed_discovery())

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


def test_frontier_expand_cli_updates_graph_frontier(tmp_path: Path, monkeypatch, capsys) -> None:
    session = ni.init_session_dir("TSLA", "frontier-expand", tmp_path / "research")

    def fake_fetch_live_graph_expansion(anchor_node: str, *, mode: str, limit: int) -> dict:
        assert anchor_node == "TSLA.price"
        assert mode == "all"
        assert limit == 20
        return {
            "ticker": "TSLA",
            "target_asset": "TSLA",
            "target_node": "TSLA.price",
            "source": "abel_live",
            "parents": [{"node_id": "AAPL.price", "ticker": "AAPL", "field": "price"}],
            "blanket_new": [
                {
                    "node_id": "MSFT.volume",
                    "ticker": "MSFT",
                    "field": "volume",
                    "roles": ["spouse"],
                }
            ],
            "children": [],
            "created_at": "2026-04-29T00:00:00+00:00",
        }

    monkeypatch.setattr(ni, "fetch_live_graph_expansion", fake_fetch_live_graph_expansion)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abel-invest",
            "frontier",
            "expand",
            "--session",
            str(session),
            "--anchor",
            "TSLA.price",
            "--mode",
            "all",
            "--limit",
            "20",
        ],
    )

    assert ni.main() == 0
    out = capsys.readouterr().out
    graph_frontier = json.loads((session / ni.GRAPH_FRONTIER_FILENAME).read_text(encoding="utf-8"))
    node_ids = [node["node_id"] for node in graph_frontier["nodes"]]
    events = (session / "events.tsv").read_text(encoding="utf-8")

    assert node_ids == ["AAPL.price", "MSFT.volume", "TSLA.price"]
    assert graph_frontier["nodes"][2]["last_expanded_at"] == "2026-04-29T00:00:00+00:00"
    assert graph_frontier["expansions"][-1]["new_nodes"] == ["AAPL.price", "MSFT.volume"]
    assert "event\tbranch_id\tround_id" in events
    assert "frontier_expanded" in events
    assert "new_nodes: 2" in out
    assert "Fields: price=2, volume=1" in out


def test_failed_live_discovery_attempt_surfaces_as_auth_or_runtime_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def _raise_discovery(*_args, **_kwargs):
        raise RuntimeError("auth missing for test")

    monkeypatch.setattr(ni, "fetch_live_graph_frontier", _raise_discovery)

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

    monkeypatch.setattr(ni, "fetch_live_graph_frontier", _raise_discovery)

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
