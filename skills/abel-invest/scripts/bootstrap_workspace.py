#!/usr/bin/env python3
"""Stdlib-only first-run bootstrap for an Abel strategy discovery workspace."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from shutil import which


MANIFEST_NAME = "alpha.workspace.yaml"
DEFAULT_WORKSPACE_NAME = "abel-invest-workspace"


def main() -> int:
    args = build_parser().parse_args()
    skill_root = resolve_skill_root(args.alpha_source)
    target_root = Path(args.path).expanduser().resolve()
    root = ensure_workspace_scaffold(target_root, args.name)
    python_path = ensure_workspace_runtime(
        root=root,
        skill_root=skill_root,
        base_python=args.base_python,
        runtime_python=args.runtime_python,
        editable=not args.no_editable,
    )
    refresh_workspace_guidance(python_path=python_path, root=root, name=args.name)
    command = [str(python_path), "-m", "abel_invest", "doctor", "--path", str(root)]
    print(f"Running workspace doctor with {python_path}")
    completed = subprocess.run(command, text=True)
    cli_path = runtime_cli_path(python_path)
    print("")
    print("From here:")
    if completed.returncode == 0:
        print(f"  cd {root}")
        print(f"  {default_activate_command()}")
        print(f"  {cli_path} init-session --ticker <TICKER> --exp-id <session-id>")
    else:
        print(f"  cd {root}")
        print(f"  {cli_path} doctor")
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap an Abel strategy discovery workspace when only the skill "
            "files and python3 are available."
        )
    )
    parser.add_argument("--path", required=True, help="Workspace directory path")
    parser.add_argument(
        "--name",
        default=DEFAULT_WORKSPACE_NAME,
        help=f"Workspace name recorded in the manifest (defaults to {DEFAULT_WORKSPACE_NAME})",
    )
    parser.add_argument(
        "--python",
        dest="base_python",
        default=None,
        help="Base interpreter used to create the workspace venv",
    )
    parser.add_argument(
        "--runtime-python",
        default=None,
        help="Use an existing interpreter instead of creating the workspace venv",
    )
    parser.add_argument(
        "--alpha-source",
        default=None,
        help="Optional Abel Invest source tree override",
    )
    parser.add_argument(
        "--no-editable",
        action="store_true",
        help="Install Abel Invest in regular mode instead of editable mode",
    )
    return parser


def resolve_skill_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
    else:
        root = Path(__file__).resolve().parents[1]
    if not (root / "pyproject.toml").exists():
        raise SystemExit(f"Abel Invest source tree is missing pyproject.toml: {root}")
    return root


def ensure_workspace_scaffold(target_root: Path, name: str) -> Path:
    target_state, related_root = inspect_workspace_bootstrap_target(target_root)
    if target_state == "nested_workspace" and related_root is not None:
        raise SystemExit(
            "Refusing to bootstrap a nested Abel strategy discovery workspace at "
            f"{target_root}\nExisting workspace root for this area: {related_root}"
        )
    if target_state == "launch_root_child_workspace" and related_root is not None:
        raise SystemExit(
            f"Workspace already exists at the default child path: {related_root}\n"
            "Reuse it instead of bootstrapping another workspace for the same area."
        )

    if target_root.exists():
        if not target_root.is_dir():
            raise SystemExit(f"Path exists and is not a directory: {target_root}")
        if (target_root / MANIFEST_NAME).exists():
            print(f"Reusing Abel strategy discovery workspace at {target_root}")
            return target_root
        if any(target_root.iterdir()):
            raise SystemExit(
                "Cannot bootstrap into an existing non-workspace directory: "
                f"{target_root}"
            )
    else:
        target_root.mkdir(parents=True)

    for rel in ("docs", "research", "cache/market_data", "logs"):
        (target_root / rel).mkdir(parents=True, exist_ok=True)
    write_text(target_root / MANIFEST_NAME, render_manifest(name))
    write_text(target_root / ".gitignore", render_gitignore())
    write_text(target_root / ".env.example", render_env_example())
    write_text(target_root / ".env", "")
    write_text(target_root / "README.md", render_readme(name))
    write_text(target_root / "AGENTS.md", render_agents())
    print(f"Created Abel strategy discovery workspace at {target_root}")
    return target_root


def ensure_workspace_runtime(
    *,
    root: Path,
    skill_root: Path,
    base_python: str | None,
    runtime_python: str | None,
    editable: bool,
) -> Path:
    if runtime_python:
        python_path = Path(runtime_python).expanduser().resolve()
        if not python_path.exists():
            raise SystemExit(f"Existing runtime python does not exist: {python_path}")
        update_manifest_value(root / MANIFEST_NAME, "  python:", f"  python: {python_path}")
    else:
        python_path = root / default_python_path()
        if not python_path.exists():
            create_workspace_venv(
                interpreter=base_python or sys.executable,
                venv_path=root / ".venv",
                cwd=root,
            )

    run_command([str(python_path), "-m", "pip", "install", "--upgrade", "pip"], cwd=root)

    install_command = [
        str(python_path),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--upgrade-strategy",
        "eager",
    ]
    if editable:
        install_command.extend(["-e", str(skill_root)])
    else:
        install_command.append(str(skill_root))
    run_command(install_command, cwd=root)
    return python_path


def create_workspace_venv(*, interpreter: str, venv_path: Path, cwd: Path) -> None:
    try:
        run_command([interpreter, "-m", "venv", str(venv_path)], cwd=cwd)
        return
    except SystemExit as exc:
        first_error = str(exc)
    uv_bin = which("uv")
    if not uv_bin:
        raise SystemExit(first_error)
    command = [uv_bin, "venv", "--seed", "--python", str(interpreter), str(venv_path)]
    try:
        run_command(command, cwd=cwd)
    except SystemExit as exc:
        raise SystemExit(f"{first_error}\n\nuv fallback also failed:\n{exc}") from exc


def inspect_workspace_bootstrap_target(path: Path) -> tuple[str, Path | None]:
    if (path / MANIFEST_NAME).exists():
        return "existing_workspace_root", path
    containing_root = find_containing_workspace_root(path)
    if containing_root is not None:
        return "nested_workspace", containing_root
    child = path / DEFAULT_WORKSPACE_NAME
    if child != path and (child / MANIFEST_NAME).exists():
        return "launch_root_child_workspace", child
    return "clear", None


def find_containing_workspace_root(path: Path) -> Path | None:
    search_from = path if path.exists() else path.parent
    for candidate in (search_from, *search_from.parents):
        if (candidate / MANIFEST_NAME).exists():
            return candidate
    return None


def run_command(command: list[str], *, cwd: Path) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        message = f"Command failed with exit code {exc.returncode}: {' '.join(command)}"
        if details:
            message = f"{message}\n{details}"
        raise SystemExit(message) from exc


def update_manifest_value(path: Path, prefix: str, replacement: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = [replacement if line.startswith(prefix) else line for line in lines]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def refresh_workspace_guidance(*, python_path: Path, root: Path, name: str) -> None:
    code = (
        "from pathlib import Path\n"
        "from abel_invest.workspace_core.workspace import render_workspace_readme, render_workspace_agents\n"
        f"root = Path({str(root)!r})\n"
        f"name = {name!r}\n"
        "(root / 'README.md').write_text(render_workspace_readme(name), encoding='utf-8')\n"
        "(root / 'AGENTS.md').write_text(render_workspace_agents(), encoding='utf-8')\n"
    )
    run_command([str(python_path), "-c", code], cwd=root)


def render_manifest(name: str) -> str:
    return f"""version: 1
workspace:
  name: {name}
  kind: abel-invest
paths:
  research_root: research
  docs_root: docs
  cache_root: cache/market_data
  logs_root: logs
  venv: .venv
runtime:
  python: {default_python_path()}
  auth_strategy: reuse_abel_auth_first
defaults:
  backtest_start: '2020-01-01'
  discovery_limit: 10
"""


def render_readme(name: str) -> str:
    return f"""# {name}

This is an Abel strategy discovery workspace.

From this workspace root, use `./.venv/bin/abel-invest` as the command prefix,
or activate `.venv` first and then use `abel-invest`.

Run `./.venv/bin/abel-invest workspace context --path . --json` and
`./.venv/bin/abel-invest doctor` before creating a session. Sessions belong
under this workspace's `research/` directory unless you intentionally use an
explicit outside-workspace escape hatch.
"""


def render_agents() -> str:
    return """# AGENTS.md - Abel strategy discovery Workspace

Use this directory as the workspace root. If `alpha.workspace.yaml` is present,
do not create a child `abel-invest-workspace` here. Run
`./.venv/bin/abel-invest workspace context --path . --json` before creating a
new session.
"""


def render_gitignore() -> str:
    return """# Abel strategy discovery workspace
.venv/
.env
cache/
logs/
__pycache__/
*.pyc
"""


def render_env_example() -> str:
    return """# Optional override for standalone Abel auth fallback
# ABEL_API_KEY=

# Optional: point abel-edge at a shared auth file
# ABEL_AUTH_ENV_FILE=
"""


def default_python_path() -> str:
    if os.name == "nt":
        return ".venv/Scripts/python.exe"
    return ".venv/bin/python"


def runtime_cli_path(python_path: Path) -> Path:
    cli_name = "abel-invest.exe" if os.name == "nt" else "abel-invest"
    return python_path.with_name(cli_name)


def default_activate_command() -> str:
    if os.name == "nt":
        return ".venv\\Scripts\\Activate.ps1"
    return "source .venv/bin/activate"


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
