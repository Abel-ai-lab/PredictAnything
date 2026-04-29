#!/usr/bin/env python3
"""Thin wrapper around the shared graph CAP probe implementation."""

from __future__ import annotations

import sys
from pathlib import Path


DEFAULT_BASE_URL = "https://cap.abel.ai/api"


def main(argv: list[str] | None = None) -> int:
    skill_root = Path(__file__).resolve().parents[1]
    common_python_root = skill_root.parent / "abel-common" / "python"
    if str(common_python_root) not in sys.path:
        sys.path.insert(0, str(common_python_root))

    from abel_common.cap import graph_probe

    graph_probe.DEFAULT_BASE_URL = DEFAULT_BASE_URL
    effective_argv = list(argv or sys.argv[1:])
    if "--env-file" not in effective_argv:
        effective_argv = [
            "--env-file",
            str(skill_root / ".env.skill"),
            *effective_argv,
        ]
    return graph_probe.main(effective_argv)


if __name__ == "__main__":
    raise SystemExit(main())
