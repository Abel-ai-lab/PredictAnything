from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from abel_invest import cli
import strategy_discovery_api as ni


def _run_cli(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["abel-invest", *argv])
    return cli.main()


def test_public_cli_session_branch_render_status_check_smoke(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "research"

    assert _run_cli(
        monkeypatch,
        [
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "cli-smoke",
            "--root",
            str(root),
            "--no-discover",
        ],
    ) == 0
    session = root / "tsla" / "cli-smoke"
    assert (session / ni.GRAPH_FRONTIER_FILENAME).exists()
    assert not (session / "discovery.json").exists()

    assert _run_cli(
        monkeypatch,
        [
            "init-branch",
            "--session",
            str(session),
            "--branch-id",
            "graph-v1",
        ],
    ) == 0
    branch = session / "branches" / "graph-v1"
    assert (branch / "branch.yaml").exists()

    assert _run_cli(monkeypatch, ["render", "--session", str(session)]) == 0
    assert _run_cli(monkeypatch, ["status", "--session", str(session)]) == 0
    assert _run_cli(monkeypatch, ["check", "--session", str(session)]) == 0

    output = capsys.readouterr().out
    assert "Created Abel strategy discovery session" in output
    assert "Created Abel strategy discovery branch" in output
    assert "Session:" in output
    assert "Narrative check passed for" in output


def test_public_cli_prepare_branch_smoke(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "prepare-smoke", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")

    def fake_run(command, cwd=None, capture_output=None, text=None, env=None, check=False):
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
                            "row_count": 20,
                            "available_range": {
                                "start": "2020-01-01",
                                "end": "2020-02-01",
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ni.subprocess, "run", fake_run)

    assert _run_cli(monkeypatch, ["prepare-branch", "--branch", str(branch)]) == 0
    assert ni.branch_inputs_ready(branch)
    assert "Prepared branch inputs:" in capsys.readouterr().out


def test_public_cli_debug_branch_blocker_smoke(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "debug-smoke", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")

    def fake_run(command, cwd=None, capture_output=None, text=None, env=None, check=False):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="semantic preflight failed for smoke",
        )

    monkeypatch.setattr(ni.subprocess, "run", fake_run)

    assert _run_cli(monkeypatch, ["debug-branch", "--branch", str(branch)]) == 1
    assert (branch / "outputs" / "debug-alpha-context.json").exists()
    assert "No narrative round was recorded." in capsys.readouterr().out


def test_public_cli_dashboard_bundle_dry_run_smoke(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "dashboard-smoke", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-v1")
    output_json = tmp_path / "bundle.json"

    assert _run_cli(
        monkeypatch,
        [
            "upload-dashboard-bundle",
            "--branch",
            str(branch),
            "--dry-run",
            "--output-json",
            str(output_json),
        ],
    ) == 0

    bundle = json.loads(output_json.read_text(encoding="utf-8"))
    assert bundle["branchId"] == "graph-v1"
    assert '"branchId": "graph-v1"' in capsys.readouterr().out
