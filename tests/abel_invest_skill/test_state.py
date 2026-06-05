from __future__ import annotations

import json
from pathlib import Path

from . import api as ni


def test_load_discovery_falls_back_to_legacy_discovery_json(tmp_path: Path) -> None:
    session = tmp_path / "research" / "tsla" / "legacy-session"
    session.mkdir(parents=True)
    discovery = {
        "ticker": "TSLA",
        "source": "legacy_discovery",
        "parents": [{"ticker": "AAPL", "node_id": "AAPL.price"}],
        "blanket_new": [],
        "children": [],
        "K_discovery": 1,
    }
    (session / "discovery.json").write_text(json.dumps(discovery), encoding="utf-8")

    assert ni.load_discovery(session)["source"] == "legacy_discovery"
