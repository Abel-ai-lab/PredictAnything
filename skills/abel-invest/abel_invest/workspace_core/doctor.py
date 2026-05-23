"""Readiness checks for Abel strategy discovery workspaces."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tomllib
from pathlib import Path

from abel_invest.workspace_core.edge_runtime import (
    probe_abel_auth,
    probe_abel_edge_cli,
    probe_abel_edge_import,
    probe_edge_context_json,
    probe_edge_discovery_payload,
)
from abel_invest.workspace_core.workspace import (
    default_workspace_path,
    load_workspace_manifest,
    resolve_workspace_entry,
    resolve_workspace_env_file,
    resolve_runtime_python,
)


SUCCESS_STATUSES = {"ready"}
WORKSPACE_MODE = "alpha-managed strategy search"
PACKAGE_CHECK = "package_freshness"


def build_auth_recovery_instruction(root: Path | str) -> str:
    """Return the agent-facing recovery instruction when reusable auth is missing."""
    root_path = Path(root)
    return (
        "Use abel-auth, then rerun "
        f"{workspace_command(root_path, None, 'doctor', '--path', str(root_path))}."
    )


def shell_join(parts: list[str]) -> str:
    """Return a shell-safe single command string."""
    return " ".join(shlex.quote(str(part)) for part in parts)


def workspace_command(root: Path, manifest: dict | None, *args: str) -> str:
    """Build an agent-facing command that prefers the workspace-local CLI."""
    try:
        python_path = resolve_runtime_python(root, manifest)
    except Exception:
        prefix = ["abel-invest"]
    else:
        cli_name = "abel-invest.exe" if os.name == "nt" else "abel-invest"
        cli_path = python_path.with_name(cli_name)
        if cli_path.exists():
            prefix = [str(cli_path)]
        elif python_path.exists():
            prefix = [str(python_path), "-m", "abel_invest"]
        else:
            prefix = ["abel-invest"]
    return shell_join([*prefix, *args])


def run_doctor(start: Path | None = None) -> dict[str, object]:
    """Run workspace, environment, edge, and auth readiness checks."""
    start_path = (start or Path.cwd()).resolve()
    root, resolution_mode = resolve_workspace_entry(start_path)
    if root is None:
        return {
            "status": "workspace_missing",
            "workspace_root": None,
            "summary": (
                "No Abel strategy discovery workspace found from the current entry path and no "
                f"default child workspace exists at {default_workspace_path(start_path)}"
            ),
            "entry_path": str(start_path),
            "default_workspace_path": str(default_workspace_path(start_path)),
            "workspace_resolution": resolution_mode,
            "checks": {
                "workspace_manifest": "fail",
                "python_env": "not_run",
                PACKAGE_CHECK: "not_run",
                "abel_edge_import": "not_run",
                "abel_edge_cli": "not_run",
                "edge_discovery_payload": "not_run",
                "edge_context_json": "not_run",
                "auth": "not_run",
            },
            "next_step": (
                "abel-invest workspace bootstrap --path "
                f"{default_workspace_path(start_path)}"
            ),
        }

    try:
        manifest = load_workspace_manifest(root)
    except Exception as exc:
        return {
            "status": "workspace_invalid",
            "workspace_root": str(root),
            "summary": f"Failed to load workspace manifest: {exc}",
            "checks": {
                "workspace_manifest": "fail",
                "python_env": "not_run",
                PACKAGE_CHECK: "not_run",
                "abel_edge_import": "not_run",
                "abel_edge_cli": "not_run",
                "edge_discovery_payload": "not_run",
                "edge_context_json": "not_run",
                "auth": "not_run",
            },
            "next_step": "fix alpha.workspace.yaml",
        }

    python_path = resolve_runtime_python(root, manifest)
    cli_name = "abel-invest.exe" if os.name == "nt" else "abel-invest"
    cli_path = python_path.with_name(cli_name)
    command_prefix = workspace_command(root, manifest)
    checks: dict[str, object] = {
        "workspace_manifest": "pass",
        "python_env": "pass" if python_path.exists() else "fail",
        PACKAGE_CHECK: "not_run",
        "abel_edge_import": "not_run",
        "abel_edge_cli": "not_run",
        "edge_discovery_payload": "not_run",
        "edge_context_json": "not_run",
        "auth": "not_run",
    }

    result: dict[str, object] = {
        "entry_path": str(start_path),
        "workspace_resolution": resolution_mode,
        "workspace_root": str(root),
        "workspace_mode": WORKSPACE_MODE,
        "python_path": str(python_path),
        "cli_path": str(cli_path),
        "command_prefix": command_prefix,
        "workspace_env_file": str(resolve_workspace_env_file(root)),
        "checks": checks,
    }

    if not python_path.exists():
        result.update(
            {
                "status": "env_missing",
                "summary": f"Workspace python does not exist at {python_path}",
                "next_step": (
                    f"{workspace_command(root, manifest, 'env', 'init', '--path', str(root))} "
                    "# or use --runtime-python /path/to/python"
                ),
            }
        )
        return result

    freshness = probe_package_freshness(python_path)
    checks[PACKAGE_CHECK] = "pass" if freshness.get("ok") else "fail"
    result["package_freshness"] = freshness
    if not freshness.get("ok"):
        result.update(
            {
                "status": "runtime_stale",
                "summary": str(
                    freshness.get("summary")
                    or "Workspace runtime package metadata is stale for this Abel Invest skill."
                ),
                "next_step": workspace_command(root, manifest, "env", "refresh", "--path", str(root)),
            }
        )
        return result

    import_check = probe_abel_edge_import(python_path, root)
    checks["abel_edge_import"] = "pass" if import_check.get("ok") else "fail"
    if not import_check.get("ok"):
        result.update(
            {
                "status": "edge_missing",
                "summary": f"Workspace python cannot import abel_edge: {import_check.get('error', 'unknown error')}",
                "next_step": (
                    f"{workspace_command(root, manifest, 'env', 'refresh', '--path', str(root))} "
                    "# or use --runtime-python /path/to/python"
                ),
            }
        )
        return result

    cli_check = probe_abel_edge_cli(python_path, root)
    checks["abel_edge_cli"] = "pass" if cli_check.get("ok") else "fail"

    discovery_contract_ok = probe_edge_discovery_payload(python_path, root)
    checks["edge_discovery_payload"] = "pass" if discovery_contract_ok else "fail"

    context_contract_ok = probe_edge_context_json(python_path, root)
    checks["edge_context_json"] = "pass" if context_contract_ok else "fail"

    auth_check = probe_abel_auth(python_path, root)
    checks["auth"] = "pass" if auth_check.get("ok") else "fail"
    result["auth"] = auth_check
    result["auth_scope"] = classify_auth_scope(root, auth_check)

    if discovery_contract_ok is not True or context_contract_ok is not True:
        result.update(
            {
                "status": "edge_contract_missing",
                "summary": (
                    "Workspace Python can import Abel-edge, but the installed runtime is missing "
                    "required alpha contracts such as structured discovery or `--context-json`."
                ),
                "next_step": (
                    f"{workspace_command(root, manifest, 'env', 'refresh', '--path', str(root))} "
                    "# reinstall the workspace runtime dependencies"
                ),
            }
        )
        return result

    if not auth_check.get("ok"):
        auth_instruction = build_auth_recovery_instruction(root)
        result.update(
            {
                "status": "auth_missing",
                "summary": (
                    "Workspace environment is ready, but no reusable Abel auth was detected. "
                    "Use abel-auth before live discovery or evaluation."
                ),
                "auth_action": auth_instruction,
                "next_step": auth_instruction,
            }
        )
        return result

    result.update(
        {
            "status": "ready",
            "summary": (
                "Workspace, Python environment, abel-edge, and Abel auth are ready "
                "for alpha-managed strategy search."
            ),
            "next_step": (
                f"{workspace_command(root, manifest, 'init-session')} --ticker <TICKER> --exp-id <session-id>  "
                "# runs live graph discovery; then init a narrow scout/candidate branch -> prepare-branch -> first-look scout before any broad run"
            ),
        }
    )
    return result


def doctor_exit_code(result: dict[str, object]) -> int:
    """Return the CLI exit code for a doctor result."""
    status = str(result.get("status") or "").strip()
    return 0 if status in SUCCESS_STATUSES else 1


def classify_auth_scope(root: Path, auth_result: dict[str, object]) -> str:
    """Classify whether the resolved auth came from the workspace or a shared source."""
    if not auth_result.get("ok"):
        return "missing"
    source = str(auth_result.get("source") or "").strip()
    path_value = auth_result.get("path")
    if source == "workspace_env":
        return "workspace_local"
    if source == "env_var":
        return "process_env"
    if source == "shared_auth_file" and isinstance(path_value, str) and path_value.strip():
        auth_path = Path(path_value).expanduser().resolve()
        try:
            auth_path.relative_to(root)
        except ValueError:
            return "shared_external"
        return "workspace_local"
    return "unknown"


def probe_package_freshness(python_path: Path) -> dict[str, object]:
    """Check whether the workspace runtime satisfies this skill's package contract."""
    contract = load_current_package_contract()
    probe = probe_installed_package_versions(python_path)
    if not probe.get("ok"):
        return {
            "ok": False,
            "summary": f"Could not inspect workspace package versions: {probe.get('error', 'unknown error')}",
            "contract": contract,
            "installed": probe.get("installed", {}),
        }

    installed = probe.get("installed", {})
    if not isinstance(installed, dict):
        installed = {}

    installed_invest = str(installed.get("abel-invest") or "").strip()
    required_invest = str(contract.get("abel-invest") or "").strip()
    if required_invest and installed_invest != required_invest:
        return {
            "ok": False,
            "summary": (
                "Workspace runtime has abel-invest "
                f"{installed_invest or '<missing>'}, but this skill declares {required_invest}."
            ),
            "contract": contract,
            "installed": installed,
        }

    installed_edge = str(installed.get("abel-edge") or "").strip()
    required_edge_min = str(contract.get("abel-edge-min") or "").strip()
    if required_edge_min and not version_at_least(installed_edge, required_edge_min):
        return {
            "ok": False,
            "summary": (
                "Workspace runtime has abel-edge "
                f"{installed_edge or '<missing>'}, below this skill's required >= {required_edge_min}."
            ),
            "contract": contract,
            "installed": installed,
        }

    return {
        "ok": True,
        "summary": "Workspace runtime package metadata satisfies this Abel Invest skill.",
        "contract": contract,
        "installed": installed,
    }


def load_current_package_contract() -> dict[str, str]:
    """Load the Abel Invest package version and Abel Edge lower bound from pyproject."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project") or {}
    dependencies = project.get("dependencies") or []
    return {
        "abel-invest": str(project.get("version") or ""),
        "abel-edge-min": extract_min_version(dependencies, "abel-edge"),
    }


def extract_min_version(dependencies: list[object], package: str) -> str:
    """Return the first >= lower bound for a package dependency string."""
    normalized = package.lower().replace("_", "-")
    for dependency in dependencies:
        spec = str(dependency)
        name = spec.split(";", 1)[0].strip().lower().replace("_", "-")
        if not name.startswith(normalized):
            continue
        match = re.search(r">=\s*([0-9][A-Za-z0-9.!\-+_]*)", spec)
        if match:
            return match.group(1)
    return ""


def probe_installed_package_versions(python_path: Path) -> dict[str, object]:
    """Ask the workspace Python which package versions are installed."""
    code = """
import importlib.metadata as metadata
import json

installed = {}
for name in ("abel-invest", "abel-edge"):
    try:
        installed[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        installed[name] = None
print(json.dumps({"installed": installed}, sort_keys=True))
""".strip()
    try:
        completed = subprocess.run(
            [str(python_path), "-c", code],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"ok": False, "error": str(exc), "installed": {}}

    output_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        payload = json.loads(output_lines[-1] if output_lines else "")
    except (IndexError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"invalid version probe output: {exc}", "installed": {}}
    installed = payload.get("installed", {})
    return {"ok": True, "installed": installed if isinstance(installed, dict) else {}}


def version_at_least(installed: str, required: str) -> bool:
    """Compare simple public versions without requiring packaging in stale runtimes."""
    if not installed:
        return False
    return version_key(installed) >= version_key(required)


def version_key(value: str) -> tuple[int, ...]:
    """Build a conservative comparison key from leading numeric version parts."""
    parts = re.split(r"[.\-+_!]", value)
    numbers: list[int] = []
    for part in parts:
        match = re.match(r"(\d+)", part)
        if match is None:
            break
        numbers.append(int(match.group(1)))
    return tuple(numbers)


def render_doctor_report(result: dict[str, object]) -> str:
    """Render a human-readable doctor report."""
    lines = [
        f"Status: {result.get('status', 'unknown')}",
        f"Summary: {result.get('summary', '')}",
    ]
    workspace_root = result.get("workspace_root")
    if workspace_root:
        lines.append(f"Workspace root: {workspace_root}")
    entry_path = result.get("entry_path")
    if entry_path:
        lines.append(f"Entry path: {entry_path}")
    workspace_resolution = result.get("workspace_resolution")
    if workspace_resolution:
        lines.append(f"Workspace resolution: {workspace_resolution}")
    default_workspace = result.get("default_workspace_path")
    if default_workspace:
        lines.append(f"Default workspace path: {default_workspace}")
    workspace_mode = result.get("workspace_mode")
    if workspace_mode:
        lines.append(f"Workspace mode: {workspace_mode}")
    python_path = result.get("python_path")
    if python_path:
        lines.append(f"Python path: {python_path}")
    cli_path = result.get("cli_path")
    if cli_path:
        lines.append(f"CLI path: {cli_path}")
    command_prefix = result.get("command_prefix")
    if command_prefix:
        lines.append(f"Command prefix: {command_prefix}")
    workspace_env_file = result.get("workspace_env_file")
    if workspace_env_file:
        lines.append(f"Workspace env file: {workspace_env_file}")
    lines.append("Checks:")
    checks = result.get("checks", {})
    if isinstance(checks, dict):
        for key, value in checks.items():
            lines.append(f"  - {key}: {value}")
    package_freshness = result.get("package_freshness")
    if isinstance(package_freshness, dict):
        lines.append(f"Package freshness: {package_freshness.get('summary', '')}")
    auth = result.get("auth")
    if isinstance(auth, dict):
        lines.append(
            "Auth source: "
            f"{auth.get('source', 'unknown')}"
            + (f" ({auth.get('path')})" if auth.get("path") else "")
        )
    auth_scope = result.get("auth_scope")
    if auth_scope:
        lines.append(f"Auth scope: {auth_scope}")
    auth_action = result.get("auth_action")
    if auth_action:
        lines.append(f"Auth action: {auth_action}")
    lines.append(f"Next step: {result.get('next_step', '')}")
    return "\n".join(lines)
