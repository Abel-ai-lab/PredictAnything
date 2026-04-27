#!/usr/bin/env python3
"""Thin system-Python entrypoint for bootstrapping an Abel strategy discovery workspace."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))

    from abel_strategy_discovery.cli import main as cli_main

    sys.argv = [sys.argv[0], "workspace", "bootstrap", *sys.argv[1:]]
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
