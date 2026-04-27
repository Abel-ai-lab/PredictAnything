from __future__ import annotations

from pathlib import Path
from argparse import Namespace
import json
import subprocess

from abel_strategy_discovery import narrative_impl as ni


def _seed_discovery() -> dict:
    return {
        "ticker": "TSLA",
        "target_asset": "TSLA",
        "target_node": "TSLA.price",
        "source": "abel_live",
        "parents": [
            {"node_id": "AAPL.price", "ticker": "AAPL", "field": "price", "roles": ["parent"]},
        ],
        "blanket_new": [
            {"node_id": "TSLA.volume", "ticker": "TSLA", "field": "volume", "roles": ["sibling"]},
        ],
        "children": [
            {"node_id": "BTCUSD.price", "ticker": "BTCUSD", "field": "price"},
        ],
        "K_discovery": 1,
        "backtest": {"start": "2020-01-01"},
        "created_at": "2026-04-22T00:00:00+00:00",
    }


def test_frontier_state_from_discovery_preserves_field_aware_nodes() -> None:
    frontier = ni.frontier_state_from_discovery(_seed_discovery())

    nodes = {item["node_id"]: item for item in frontier["nodes"]}

    assert frontier["target_node"] == "TSLA.price"
    assert set(nodes) == {"TSLA.price", "AAPL.price", "TSLA.volume", "BTCUSD.price"}
    assert nodes["TSLA.volume"]["depth"] == 1
    assert "sibling" in nodes["TSLA.volume"]["discovery_roles"]
    assert nodes["BTCUSD.price"]["discovered_from"] == ["TSLA.price"]


def test_init_branch_prefers_frontier_nodes_for_default_inputs(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v1", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))

    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)

    assert spec["target_node"] == "TSLA.price"
    assert spec["suggested_inputs"][0]["node_id"] == "TSLA.volume"
    assert spec["selected_inputs"][0]["node_id"] == "TSLA.volume"


def test_expand_frontier_command_merges_new_nodes_without_duplicates(tmp_path: Path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v2", tmp_path / "research")
    discovery = {
        "ticker": "TSLA",
        "target_asset": "TSLA",
        "target_node": "TSLA.price",
        "source": "abel_live",
        "parents": [{"node_id": "AAPL.price", "ticker": "AAPL", "field": "price"}],
        "blanket_new": [],
        "children": [],
        "K_discovery": 1,
        "backtest": {"start": "2020-01-01"},
        "created_at": "2026-04-22T00:00:00+00:00",
    }
    ni.write_discovery(session, discovery)
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(discovery))

    monkeypatch.setattr(
        ni,
        "fetch_live_graph_payload",
        lambda node_id, limit: {
            "ticker": "AAPL",
            "target_asset": "AAPL",
            "target_node": "AAPL.price",
            "source": "abel_live",
            "parents": [{"node_id": "MSFT.price", "ticker": "MSFT", "field": "price"}],
            "blanket_new": [
                {"node_id": "TSLA.volume", "ticker": "TSLA", "field": "volume", "roles": ["sibling"]},
            ],
            "children": [],
            "K_discovery": 1,
            "created_at": "2026-04-22T00:10:00+00:00",
        },
    )

    result = ni.expand_frontier_command(session=session, from_node="AAPL.price", limit=8)

    frontier = ni.load_frontier_state(session)
    nodes = [item["node_id"] for item in frontier["nodes"]]

    assert result == 0
    assert nodes.count("TSLA.volume") == 1
    assert "MSFT.price" in nodes
    assert len(frontier["expansions"]) == 1
    assert frontier["expansions"][0]["from_node"] == "AAPL.price"


def test_render_session_includes_graph_frontier_section(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v3", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))

    ni.render_session(session)

    readme = (session / "README.md").read_text(encoding="utf-8")
    assert "## Graph Frontier" in readme
    assert "TSLA.volume" in readme


def test_session_readme_guides_agent_into_probe_first_loop(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v3b", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))

    ni.render_session(session)

    readme = (session / "README.md").read_text(encoding="utf-8")
    assert "abel-strategy-discovery frontier-status" in readme
    assert "abel-strategy-discovery probe-nodes" in readme


def test_seed_only_session_records_explicit_discovery_state(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v3c", tmp_path / "research")

    discovery_state = ni.load_discovery_state(session)
    readme = (session / "README.md").read_text(encoding="utf-8")

    assert discovery_state["status"] == "seed_only"
    assert discovery_state["frontier_mode"] == "seed_only"
    assert "discovery_status: `seed_only`" in readme
    assert "first branch will start target-only" in readme


def test_live_discovery_session_records_ready_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ni, "fetch_live_discovery", lambda ticker, limit: _seed_discovery())
    monkeypatch.setattr(ni, "refresh_data_readiness", lambda **kwargs: None)

    session = ni.init_session_dir(
        "TSLA",
        "frontier-v3d",
        tmp_path / "research",
        discover=True,
    )

    discovery_state = ni.load_discovery_state(session)
    readme = (session / "README.md").read_text(encoding="utf-8")

    assert discovery_state["status"] == "ready"
    assert discovery_state["frontier_mode"] == "graph"
    assert "discovery_status: `ready`" in readme
    assert "frontier_mode: `graph`" in readme


def test_failed_live_discovery_attempt_stays_visible(tmp_path: Path, monkeypatch, capsys) -> None:
    def _raise_discovery(*_args, **_kwargs):
        raise RuntimeError("auth missing for test")

    monkeypatch.setattr(ni, "fetch_live_discovery", _raise_discovery)

    session = ni.init_session_dir(
        "TSLA",
        "frontier-v3e",
        tmp_path / "research",
        discover=True,
    )

    discovery_state = ni.load_discovery_state(session)
    frontier = ni.load_frontier_state(session)
    readme = (session / "README.md").read_text(encoding="utf-8")

    assert discovery_state["status"] == "failed"
    assert discovery_state["frontier_mode"] == "seed_only"
    assert [item["node_id"] for item in frontier["nodes"]] == ["TSLA.price"]
    assert "discovery_status: `failed`" in readme
    assert "last_error: `auth missing for test`" in readme

    result = ni.print_frontier_status(session=session)
    output = capsys.readouterr().out

    assert result == 0
    assert "discovery_status: failed" in output
    assert "frontier_mode: seed_only" in output
    assert "discovery_error: auth missing for test" in output


def test_unexpected_live_discovery_exception_stays_visible(tmp_path: Path, monkeypatch) -> None:
    def _raise_discovery(*_args, **_kwargs):
        raise Exception("404 Client Error: Not Found for url: https://cap.abel.ai/api/cap")

    monkeypatch.setattr(ni, "fetch_live_discovery", _raise_discovery)

    session = ni.init_session_dir(
        "NFLX",
        "frontier-v3f",
        tmp_path / "research",
        discover=True,
    )

    discovery_state = ni.load_discovery_state(session)
    readme = (session / "README.md").read_text(encoding="utf-8")

    assert discovery_state["status"] == "failed"
    assert discovery_state["frontier_mode"] == "seed_only"
    assert "404 Client Error" in discovery_state["error"]
    assert "discovery_status: `failed`" in readme


def test_probe_nodes_command_updates_frontier_availability(tmp_path: Path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v4", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))

    monkeypatch.setattr(
        ni,
        "run_edge_probe_data",
        lambda **kwargs: {
            "target": {"node_id": "TSLA.price"},
            "requested_window": {"start": "2020-01-01", "end": None},
            "basket": {"dense_overlap_start": "2020-01-03T00:00:00+00:00", "limiting_inputs": ["BTCUSD.price"]},
            "results": [
                {
                    "node_id": "BTCUSD.price",
                    "status": "partial_target_overlap",
                    "row_count": 3,
                    "native_window": {
                        "start": "2020-01-03T00:00:00+00:00",
                        "end": "2020-01-05T00:00:00+00:00",
                    },
                    "target_overlap_days": 2,
                    "target_decision_days": 3,
                    "first_usable_target_time": "2020-01-03T00:00:00+00:00",
                }
            ],
        },
    )

    result = ni.probe_nodes_command(
        session=session,
        node_ids=["BTCUSD.price"],
        start=None,
        end=None,
        limit=500,
    )

    frontier = ni.load_frontier_state(session)
    btc_entry = ni.find_frontier_entry(frontier, "BTCUSD.price")

    assert result == 0
    assert frontier["probe_history"][-1]["node_ids"] == ["BTCUSD.price"]
    assert btc_entry is not None
    assert btc_entry["availability_summary"]["status"] == "partial_target_overlap"
    assert btc_entry["availability_summary"]["target_overlap_days"] == 2


def test_select_branch_inputs_command_updates_branch_spec_from_frontier(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v5", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))
    branch = ni.init_branch_dir(session, "graph-v1")

    result = ni.select_branch_inputs_command(
        branch=branch,
        node_ids=["BTCUSD.price"],
        replace=True,
    )

    spec = ni.load_branch_spec(branch)

    assert result == 0
    assert spec["selected_inputs"] == [
        {"node_id": "BTCUSD.price", "asset": "BTCUSD", "field": "price"}
    ]


def test_probe_select_prepare_flow_supports_volume_and_crypto_inputs(tmp_path: Path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v6", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_readiness(
        session,
        {
            "results": [
                {"ticker": "TSLA", "status": "full", "usable": True, "covers_requested_start": True},
                {"ticker": "BTCUSD", "status": "partial", "usable": True, "covers_requested_start": False},
            ]
        },
    )
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))

    monkeypatch.setattr(
        ni,
        "run_edge_probe_data",
        lambda **kwargs: {
            "target": {"node_id": "TSLA.price"},
            "requested_window": {"start": "2020-01-01", "end": None},
            "basket": {"dense_overlap_start": "2020-03-02T00:00:00+00:00", "limiting_inputs": ["BTCUSD.price"]},
            "results": [
                {
                    "node_id": "TSLA.volume",
                    "status": "full_target_overlap",
                    "row_count": 200,
                    "native_window": {
                        "start": "2020-01-01T00:00:00+00:00",
                        "end": "2020-12-31T00:00:00+00:00",
                    },
                    "target_overlap_days": 200,
                    "target_decision_days": 200,
                    "first_usable_target_time": "2020-01-01T00:00:00+00:00",
                },
                {
                    "node_id": "BTCUSD.price",
                    "status": "partial_target_overlap",
                    "row_count": 180,
                    "native_window": {
                        "start": "2020-03-02T00:00:00+00:00",
                        "end": "2020-12-31T00:00:00+00:00",
                    },
                    "target_overlap_days": 160,
                    "target_decision_days": 200,
                    "first_usable_target_time": "2020-03-02T00:00:00+00:00",
                },
            ],
        },
    )
    ni.probe_nodes_command(
        session=session,
        node_ids=["TSLA.volume", "BTCUSD.price"],
        start=None,
        end=None,
        limit=500,
    )

    branch = ni.init_branch_dir(session, "graph-v1")
    ni.select_branch_inputs_command(
        branch=branch,
        node_ids=["TSLA.volume", "BTCUSD.price"],
        replace=True,
    )

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None):
        output_path = Path(command[command.index("--output-json") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "adapter": "abel",
                    "timeframe": "1d",
                    "profile": "daily",
                    "results": [
                        {
                            "symbol": "TSLA",
                            "ok": True,
                            "row_count": 220,
                            "available_range": {"start": "2020-01-01", "end": "2020-12-31"},
                        },
                        {
                            "symbol": "BTCUSD",
                            "ok": True,
                            "row_count": 250,
                            "available_range": {"start": "2020-03-02", "end": "2020-12-31"},
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)

    result = ni.prepare_branch_inputs(
        Namespace(
            branch=str(branch),
            python_bin="python3",
            cache_limit=400,
        )
    )

    window_report = json.loads(ni.window_availability_path(branch).read_text(encoding="utf-8"))
    data_manifest = json.loads(ni.data_manifest_path(branch).read_text(encoding="utf-8"))
    context_guide = ni.context_guide_path(branch).read_text(encoding="utf-8")

    assert result == 0
    assert window_report["effective_window"]["start"] == "2020-03-02T00:00:00+00:00"
    assert window_report["start_alignment"]["target_safe_start"] == "2020-01-01T00:00:00+00:00"
    assert window_report["start_alignment"]["avoidable_gap_days"] == 61
    assert "BTCUSD.price" in window_report["limiting_inputs"]
    assert any(feed["node_id"] == "TSLA.volume" for feed in data_manifest["feeds"])
    assert any(feed["node_id"] == "BTCUSD.price" for feed in data_manifest["feeds"])
    assert "avoidable_gap_days" in context_guide


def test_select_inputs_invalidates_prepared_contract(tmp_path: Path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v7", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))
    branch = ni.init_branch_dir(session, "graph-v1")

    ni.select_branch_inputs_command(
        branch=branch,
        node_ids=["TSLA.volume"],
        replace=True,
    )

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None, env=None):
        output_path = Path(command[command.index("--output-json") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "adapter": "abel",
                    "timeframe": "1d",
                    "profile": "daily",
                    "results": [
                        {
                            "symbol": "TSLA",
                            "ok": True,
                            "row_count": 220,
                            "available_range": {"start": "2020-01-01", "end": "2020-12-31"},
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ni.subprocess, "run", fake_subprocess_run)

    result = ni.prepare_branch_inputs(
        Namespace(
            branch=str(branch),
            python_bin="python3",
            cache_limit=400,
        )
    )
    status = ni.branch_prepare_status(branch, ni.load_discovery(session))
    assert result == 0
    assert status["status"] == "ready"

    ni.select_branch_inputs_command(
        branch=branch,
        node_ids=["BTCUSD.price"],
        replace=True,
    )

    status = ni.branch_prepare_status(branch, ni.load_discovery(session))
    assert status["status"] == "stale"
    assert "selected_inputs" in status["changed_fields"]
