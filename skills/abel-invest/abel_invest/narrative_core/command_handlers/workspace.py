"""Workspace, environment, and doctor command handlers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from abel_invest.workspace_core.doctor import (
    doctor_exit_code,
    render_doctor_report,
    run_doctor,
    workspace_command,
)
from abel_invest.workspace_core.env import init_workspace_env
from abel_invest.workspace_core.workspace import (
    build_default_manifest,
    default_workspace_path,
    default_activate_command,
    inspect_workspace_bootstrap_target,
    is_workspace_root,
    load_workspace_manifest,
    resolve_workspace_entry,
    render_workspace_status,
    resolve_runtime_cli,
    resolve_runtime_python,
    resolve_workspace_paths,
    scaffold_workspace,
)


def handle_workspace_command(args: argparse.Namespace) -> int:
    if args.workspace_command == "init":
        target_root = Path(args.path).expanduser()
        target_state, related_root = inspect_workspace_bootstrap_target(target_root)
        if target_state == "nested_workspace" and related_root is not None:
            print(
                "Refusing to create a nested Abel strategy discovery workspace at "
                f"{target_root.resolve()}"
            )
            print(f"Existing workspace root for this area: {related_root}")
            print("")
            print("Continue there instead:")
            prefix = workspace_command(related_root, None)
            print(f"  {prefix} workspace status --path {related_root}")
            print(f"  {prefix} doctor --path {related_root}")
            return 1
        if target_state == "launch_root_child_workspace" and related_root is not None:
            print(f"Workspace already exists at the default child path: {related_root}")
            print("Reuse it instead of creating another workspace for the same area.")
            print("")
            print("Continue there instead:")
            prefix = workspace_command(related_root, None)
            print(f"  {prefix} workspace status --path {related_root}")
            print(f"  {prefix} doctor --path {related_root}")
            return 1
        root = scaffold_workspace(args.name, target_root=target_root)
        manifest = build_default_manifest(args.name)
        resolved = resolve_workspace_paths(root, manifest)
        print(f"Created Abel strategy discovery workspace at {root}")
        print(f"  manifest: {root / 'alpha.workspace.yaml'}")
        print(f"  research: {resolved['research_root']}")
        print(f"  docs: {resolved['docs_root']}")
        print(
            "  planned_workspace_python: "
            f"{resolved['venv'] / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')}"
        )
        print("")
        print("Boundary:")
        print("  This workspace is for alpha-managed strategy search.")
        print("  Keep session artifacts under `research/`.")
        print("  If you need a standalone Abel-edge project, create it outside this workspace.")
        print("")
        print("From here:")
        print(f"  cd {root}")
        print("  abel-invest workspace status")
        print(f"  abel-invest workspace bootstrap --path {root}")
        return 0
    if args.workspace_command == "bootstrap":
        target_root = Path(args.path).expanduser().resolve()
        target_state, related_root = inspect_workspace_bootstrap_target(target_root)
        if target_state == "nested_workspace" and related_root is not None:
            print(
                "Refusing to bootstrap a nested Abel strategy discovery workspace at "
                f"{target_root}"
            )
            print(f"Existing workspace root for this area: {related_root}")
            print("")
            print("Continue there instead:")
            prefix = workspace_command(related_root, None)
            print(f"  {prefix} workspace status --path {related_root}")
            print(f"  {prefix} doctor --path {related_root}")
            return 1
        if target_state == "launch_root_child_workspace" and related_root is not None:
            print(f"Workspace already exists at the default child path: {related_root}")
            print("Reuse it instead of bootstrapping another workspace for the same area.")
            print("")
            print("Continue there instead:")
            prefix = workspace_command(related_root, None)
            print(f"  {prefix} workspace status --path {related_root}")
            print(f"  {prefix} doctor --path {related_root}")
            return 1
        reused_workspace = False
        if target_root.exists():
            if not is_workspace_root(target_root):
                if target_root.is_dir() and not any(target_root.iterdir()):
                    root = scaffold_workspace(
                        args.name,
                        target_root=target_root,
                        allow_existing_empty=True,
                    )
                else:
                    print(
                        "Cannot bootstrap into an existing non-workspace directory: "
                        f"{target_root}"
                    )
                    print(
                        "Choose an empty path or an existing Abel strategy discovery workspace root."
                    )
                    return 1
            else:
                root = target_root
                reused_workspace = True
        else:
            root = scaffold_workspace(args.name, target_root=target_root)

        manifest = load_workspace_manifest(root)
        resolved = resolve_workspace_paths(root, manifest)
        env_result = init_workspace_env(
            start=root,
            base_python=args.base_python,
            alpha_source=args.alpha_source,
            runtime_python=args.runtime_python,
            alpha_editable=not args.no_editable,
        )
        doctor_result = run_doctor(root)

        print(
            ("Reusing" if reused_workspace else "Created")
            + f" Abel strategy discovery workspace at {root}"
        )
        print(f"  manifest: {root / 'alpha.workspace.yaml'}")
        print(f"  canonical_runtime_python: {env_result.python_path}")
        cli_path = resolve_runtime_cli(root, manifest)
        print(f"  canonical_cli: {cli_path}")
        print(f"  activation: {default_activate_command()}")
        print(f"  runtime_mode: {env_result.runtime_mode}")
        print(f"  venv_provider: {env_result.venv_provider}")
        print("  dependency_install_mode: abel-invest package metadata")
        print(f"  alpha_install_mode: {'editable' if env_result.alpha_editable else 'regular'}")
        print(
            "  workspace_reuse: "
            + ("reused_existing_root" if reused_workspace else "created_new_root")
        )
        print(f"  research: {resolved['research_root']}")
        print(f"  docs: {resolved['docs_root']}")
        print("")
        print(render_doctor_report(doctor_result))
        print("")
        print("From here:")
        if doctor_exit_code(doctor_result) == 0:
            print(f"  cd {root}")
            print(f"  {default_activate_command()}")
            print(f"  {cli_path} init-session --ticker <TICKER> --exp-id <session-id>  # runs live graph discovery by default")
        else:
            print(f"  cd {root}")
            next_step = str(doctor_result.get("next_step") or "").strip()
            if next_step:
                print(f"  {next_step}")
        return doctor_exit_code(doctor_result)
    if args.workspace_command == "status":
        start = Path(args.path).expanduser().resolve()
        root, resolution_mode = resolve_workspace_entry(start)
        if root is None:
            print(f"No Abel strategy discovery workspace found from entry path {start}")
            print(f"Default workspace path for this launch root: {default_workspace_path(start)}")
            return 1
        manifest = load_workspace_manifest(root)
        if resolution_mode == "launch_root_child":
            print(f"Reusing default workspace under launch root: {root}")
            print("")
        elif resolution_mode == "workspace_ancestor":
            print(f"Continuing from workspace containing {start}: {root}")
            print("")
        print(render_workspace_status(root, manifest))
        return 0
    if args.workspace_command == "context":
        context = build_workspace_context(Path(args.path).expanduser())
        if args.json_output:
            print(json.dumps(context, indent=2, sort_keys=True))
        else:
            print(render_workspace_context(context))
        return 0 if context.get("workspace_root") else 1
    return 1


def build_workspace_context(start: Path) -> dict[str, object]:
    """Build a compact workspace context payload for agent re-entry."""
    entry_path = start.resolve()
    root, resolution_mode = resolve_workspace_entry(entry_path)
    if root is None:
        default_path = default_workspace_path(entry_path)
        return {
            "entry_path": str(entry_path),
            "workspace_resolution": resolution_mode,
            "workspace_root": None,
            "research_root": None,
            "runtime_python": None,
            "cli_path": None,
            "command_prefix": None,
            "doctor_status": "workspace_missing",
            "default_workspace_path": str(default_path),
            "session_command_prefix": None,
            "next_step": f"abel-invest workspace bootstrap --path {default_path}",
        }

    manifest = load_workspace_manifest(root)
    resolved = resolve_workspace_paths(root, manifest)
    doctor_result = run_doctor(root)
    cli_path = resolve_runtime_cli(root, manifest)
    command_prefix = str(doctor_result.get("command_prefix") or workspace_command(root, manifest))
    return {
        "entry_path": str(entry_path),
        "workspace_resolution": resolution_mode,
        "workspace_root": str(root),
        "research_root": str(resolved["research_root"]),
        "runtime_python": str(resolve_runtime_python(root, manifest)),
        "cli_path": str(cli_path),
        "command_prefix": command_prefix,
        "doctor_status": str(doctor_result.get("status") or "unknown"),
        "workspace_mode": doctor_result.get("workspace_mode"),
        "default_workspace_path": str(default_workspace_path(entry_path)),
        "session_command_prefix": f"{command_prefix} init-session",
        "next_step": doctor_result.get("next_step"),
    }


def render_workspace_context(context: dict[str, object]) -> str:
    """Render workspace context for humans while preserving the JSON contract."""
    lines = [
        f"Entry path: {context.get('entry_path')}",
        f"Workspace resolution: {context.get('workspace_resolution')}",
    ]
    workspace_root = context.get("workspace_root")
    if workspace_root:
        lines.extend(
            [
                f"Workspace root: {workspace_root}",
                f"Research root: {context.get('research_root')}",
                f"Runtime python: {context.get('runtime_python')}",
                f"CLI path: {context.get('cli_path')}",
                f"Command prefix: {context.get('command_prefix')}",
                f"Doctor status: {context.get('doctor_status')}",
                f"Session command prefix: {context.get('session_command_prefix')}",
            ]
        )
    else:
        lines.extend(
            [
                "Workspace root: <missing>",
                f"Default workspace path: {context.get('default_workspace_path')}",
                f"Doctor status: {context.get('doctor_status')}",
            ]
        )
    lines.append(f"Next step: {context.get('next_step')}")
    return "\n".join(lines)


def handle_env_command(args: argparse.Namespace) -> int:
    if args.env_command not in {"init", "refresh"}:
        return 1
    result = init_workspace_env(
        start=Path(args.path).expanduser(),
        base_python=args.base_python,
        alpha_source=args.alpha_source,
        runtime_python=args.runtime_python,
        alpha_editable=not args.no_editable,
    )
    action = "refreshed" if args.env_command == "refresh" else "ready"
    print(f"Workspace environment {action} at {result.workspace_root}")
    print(f"  venv: {result.venv_path}")
    print(f"  python: {result.python_path}")
    print(f"  alpha_source: {result.alpha_source}")
    print(f"  runtime_mode: {result.runtime_mode}")
    print(f"  venv_provider: {result.venv_provider}")
    print("  dependency_install_mode: abel-invest package metadata")
    print(f"  alpha_install_mode: {'editable' if result.alpha_editable else 'regular'}")
    print("  alpha_install_reason: installs the packaged abel-invest CLI and declared dependencies into this workspace runtime")
    print("  canonical_runtime_note: use this workspace runtime as the canonical environment for daily alpha search")
    cli_path = resolve_runtime_cli(result.workspace_root)
    print(f"  canonical_cli: {cli_path}")
    if result.runtime_mode == "existing_python":
        print("  runtime_override_note: using an existing interpreter instead of creating the workspace .venv")
    if result.edge_discovery_payload_capable is not None:
        print(f"  edge_discovery_payload: {'yes' if result.edge_discovery_payload_capable else 'no'}")
    if result.edge_context_json_capable is not None:
        print(f"  edge_context_json: {'yes' if result.edge_context_json_capable else 'no'}")
    print("")
    if result.edge_discovery_payload_capable is False or result.edge_context_json_capable is False:
        print("Warning:")
        print("  Installed Abel-edge is missing required alpha contracts.")
        print(f"  Run `{cli_path} env refresh`, then rerun `{cli_path} doctor` before starting alpha search.")
        print("")
    print("From here:")
    print(f"  {cli_path} doctor")
    print(f"  {default_activate_command()}")
    print(
        "  # once doctor is ready: init-session -> init narrow scout/candidate branch -> "
        "prepare-branch -> first-look scout before run -> "
        "use frontier facts and exploration_path.md to guide pivots"
    )
    return 0


def handle_doctor_command(args: argparse.Namespace) -> int:
    result = run_doctor(Path(args.path).expanduser())
    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(render_doctor_report(result))
    return doctor_exit_code(result)
