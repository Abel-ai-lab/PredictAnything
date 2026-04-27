"""Readiness checks for Abel strategy discovery workspaces."""

from __future__ import annotations

from pathlib import Path

from abel_strategy_discovery.edge_runtime import (
    probe_abel_auth,
    probe_causal_edge_cli,
    probe_causal_edge_import,
    probe_edge_context_json,
    probe_edge_discovery_payload,
)
from abel_strategy_discovery.workspace import (
    default_workspace_path,
    load_workspace_manifest,
    resolve_workspace_entry,
    resolve_edge_spec,
    resolve_workspace_env_file,
    resolve_runtime_python,
)


SUCCESS_STATUSES = {"ready"}
WORKSPACE_MODE = "alpha-managed branch research"


def build_auth_recovery_instruction(root: Path | str) -> str:
    """Return the agent-facing recovery instruction when reusable auth is missing."""
    return (
        "Use abel-auth, then rerun "
        f"abel-strategy-discovery doctor --path {Path(root)}."
    )


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
                "causal_edge_import": "not_run",
                "causal_edge_cli": "not_run",
                "edge_discovery_payload": "not_run",
                "edge_context_json": "not_run",
                "auth": "not_run",
            },
            "next_step": (
                "abel-strategy-discovery workspace bootstrap --path "
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
                "causal_edge_import": "not_run",
                "causal_edge_cli": "not_run",
                "edge_discovery_payload": "not_run",
                "edge_context_json": "not_run",
                "auth": "not_run",
            },
            "next_step": "fix alpha.workspace.yaml",
        }

    python_path = resolve_runtime_python(root, manifest)
    checks: dict[str, object] = {
        "workspace_manifest": "pass",
        "python_env": "pass" if python_path.exists() else "fail",
        "causal_edge_import": "not_run",
        "causal_edge_cli": "not_run",
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
        "workspace_env_file": str(resolve_workspace_env_file(root)),
        "edge_install_target": resolve_edge_spec(root, manifest),
        "checks": checks,
    }

    if not python_path.exists():
        result.update(
            {
                "status": "env_missing",
                "summary": f"Workspace python does not exist at {python_path}",
                "next_step": "abel-strategy-discovery env init  # or use --runtime-python /path/to/python",
            }
        )
        return result

    import_check = probe_causal_edge_import(python_path, root)
    checks["causal_edge_import"] = "pass" if import_check.get("ok") else "fail"
    if not import_check.get("ok"):
        result.update(
            {
                "status": "edge_missing",
                "summary": f"Workspace python cannot import causal_edge: {import_check.get('error', 'unknown error')}",
                "next_step": "abel-strategy-discovery env init  # or use --runtime-python /path/to/python",
            }
        )
        return result

    cli_check = probe_causal_edge_cli(python_path, root)
    checks["causal_edge_cli"] = "pass" if cli_check.get("ok") else "fail"

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
                "next_step": "abel-strategy-discovery env init  # or install a newer Abel-edge into the workspace runtime",
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
                "Workspace, Python environment, causal-edge, and Abel auth are ready "
                "for alpha-managed branch research."
            ),
            "next_step": (
                "abel-strategy-discovery init-session --ticker <TICKER> --exp-id <session-id>  "
                "# runs live graph discovery by default, then init-branch -> edit branch.yaml -> prepare-branch"
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
    edge_install_target = result.get("edge_install_target")
    if edge_install_target:
        lines.append(f"Edge install target: {edge_install_target}")
    workspace_env_file = result.get("workspace_env_file")
    if workspace_env_file:
        lines.append(f"Workspace env file: {workspace_env_file}")
    lines.append("Checks:")
    checks = result.get("checks", {})
    if isinstance(checks, dict):
        for key, value in checks.items():
            lines.append(f"  - {key}: {value}")
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
