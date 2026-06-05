from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from abel_invest import cli
from abel_invest.workspace_core.workspace import scaffold_workspace
from . import api as ni


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
            "--allow-outside-workspace",
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


def test_init_session_grandma_mode_routes_default_branch_to_grandma_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "research"

    assert _run_cli(
        monkeypatch,
        [
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "grandma-smoke",
            "--root",
            str(root),
            "--allow-outside-workspace",
            "--no-discover",
            "--mode",
            "grandma",
        ],
    ) == 0
    session = root / "tsla" / "grandma-smoke"

    assert _run_cli(
        monkeypatch,
        [
            "init-branch",
            "--session",
            str(session),
            "--branch-id",
            "simple-return",
        ],
    ) == 0

    state = json.loads((session / "session_state.json").read_text(encoding="utf-8"))
    spec = ni.load_branch_spec(session / "branches" / "simple-return")

    assert state["mode"] == "grandma"
    assert state["validation_profile"] == "grandma_daily"
    assert spec["strategy_mode"] == "grandma"
    assert spec["validation_profile"] == "grandma_daily"
    assert spec["position_bounds"] == [-1.0, 1.0]
    assert spec["model_family"] == "rule_signal"
    assert spec["complexity_class"] == "simple_signal"
    assert spec["input_claim"] == "target_only"


def test_init_session_uses_experiment_env_for_grandma_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "research"
    monkeypatch.setenv("ABEL_EXPERIMENT_MODE", "grandma")

    assert _run_cli(
        monkeypatch,
        [
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "grandma-env",
            "--root",
            str(root),
            "--allow-outside-workspace",
            "--no-discover",
        ],
    ) == 0

    state = json.loads(
        (root / "tsla" / "grandma-env" / "session_state.json").read_text(encoding="utf-8")
    )
    assert state["mode"] == "grandma"
    assert state["validation_profile"] == "grandma_daily"


def test_init_session_preserves_existing_grandma_mode_without_explicit_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "research"
    base_args = [
        "init-session",
        "--ticker",
        "TSLA",
        "--exp-id",
        "grandma-rerun",
        "--root",
        str(root),
        "--allow-outside-workspace",
        "--no-discover",
    ]

    assert _run_cli(monkeypatch, [*base_args, "--mode", "grandma"]) == 0
    assert _run_cli(monkeypatch, base_args) == 0
    session = root / "tsla" / "grandma-rerun"

    assert _run_cli(
        monkeypatch,
        [
            "init-branch",
            "--session",
            str(session),
            "--branch-id",
            "after-rerun",
        ],
    ) == 0

    state = json.loads((session / "session_state.json").read_text(encoding="utf-8"))
    spec = ni.load_branch_spec(session / "branches" / "after-rerun")

    assert state["mode"] == "grandma"
    assert state["validation_profile"] == "grandma_daily"
    assert spec["strategy_mode"] == "grandma"
    assert spec["validation_profile"] == "grandma_daily"


def test_init_session_explicit_standard_downgrades_existing_grandma_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "research"
    base_args = [
        "init-session",
        "--ticker",
        "TSLA",
        "--exp-id",
        "grandma-standard",
        "--root",
        str(root),
        "--allow-outside-workspace",
        "--no-discover",
    ]

    assert _run_cli(monkeypatch, [*base_args, "--mode", "grandma"]) == 0
    assert _run_cli(monkeypatch, [*base_args, "--mode", "standard"]) == 0
    session = root / "tsla" / "grandma-standard"

    assert _run_cli(
        monkeypatch,
        [
            "init-branch",
            "--session",
            str(session),
            "--branch-id",
            "after-standard",
        ],
    ) == 0

    state = json.loads((session / "session_state.json").read_text(encoding="utf-8"))
    spec = ni.load_branch_spec(session / "branches" / "after-standard")

    assert state["mode"] == "standard"
    assert "validation_profile" not in state
    assert "strategy_mode" not in spec
    assert "validation_profile" not in spec


def test_public_cli_version_option(monkeypatch, capsys) -> None:
    assert _run_cli(monkeypatch, ["--version"]) == 0

    assert "abel-invest" in capsys.readouterr().out


def test_init_session_without_root_uses_current_workspace_research_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")
    monkeypatch.chdir(workspace)

    assert _run_cli(
        monkeypatch,
        [
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "workspace-owned",
            "--no-discover",
        ],
    ) == 0

    assert (workspace / "research" / "tsla" / "workspace-owned").exists()


def test_init_session_from_launch_root_uses_default_child_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = scaffold_workspace(
        "abel-invest-workspace",
        target_root=tmp_path / "abel-invest-workspace",
    )
    monkeypatch.chdir(tmp_path)

    assert _run_cli(
        monkeypatch,
        [
            "init-session",
            "--ticker",
            "MSFT",
            "--exp-id",
            "child-owned",
            "--no-discover",
        ],
    ) == 0

    assert (workspace / "research" / "msft" / "child-owned").exists()


def test_init_session_without_workspace_refuses_local_research_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = _run_cli(
        monkeypatch,
        [
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "misplaced",
            "--no-discover",
        ],
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.err
    assert "Error: No Abel strategy discovery workspace" in captured.err
    assert "Next step:" in captured.err
    assert "workspace context --path . --json" in captured.err
    assert not (tmp_path / "research").exists()


def test_init_session_explicit_outside_root_requires_escape_hatch(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")
    outside_root = tmp_path / "outside-research"
    monkeypatch.chdir(workspace)

    rc = _run_cli(
        monkeypatch,
        [
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "outside",
            "--root",
            str(outside_root),
            "--no-discover",
        ],
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.err
    assert "outside the resolved workspace root" in captured.err
    assert "--allow-outside-workspace" in captured.err

    assert _run_cli(
        monkeypatch,
        [
            "init-session",
            "--ticker",
            "TSLA",
            "--exp-id",
            "outside",
            "--root",
            str(outside_root),
            "--allow-outside-workspace",
            "--no-discover",
        ],
    ) == 0

    assert (outside_root / "tsla" / "outside").exists()


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
    output = capsys.readouterr().out
    assert "Prepared branch inputs:" in output
    assert "From here:" in output


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
    output = capsys.readouterr().out
    assert "No narrative round was recorded." in output
    assert "From here:" in output
    assert "fix the engine or prepared inputs before recording a round" in output


