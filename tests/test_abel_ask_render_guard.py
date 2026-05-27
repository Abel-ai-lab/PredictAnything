from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPO_ROOT / "skills" / "abel-ask" / "scripts" / "render_guard.py"


def test_render_guard_rejects_tool_reference_leaks() -> None:
    result = subprocess.run(
        [
            "python",
            str(GUARD_PATH),
            "--mode",
            "direct_graph",
        ],
        input="截至我查询时，BTC 现价见 [price](turn6finance0)",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "tool_result_reference" in result.stdout
