"""Workspace environment bootstrap helpers for Abel strategy discovery."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from abel_strategy_discovery.edge_runtime import probe_edge_context_json, probe_edge_discovery_payload
from abel_strategy_discovery.workspace import (
    default_workspace_path,
    resolve_workspace_entry,
    load_workspace_manifest,
    resolve_edge_spec,
    resolve_runtime_python,
    resolve_workspace_paths,
    write_workspace_manifest,
)


@dataclass
class EnvInitResult:
    """Structured result for `abel-strategy-discovery env init`."""

    workspace_root: Path
    venv_path: Path
    python_path: Path
    alpha_source: Path
    edge_install_target: str
    edge_install_mode: str
    edge_discovery_payload_capable: bool | None
    edge_context_json_capable: bool | None
    alpha_editable: bool
    created_venv: bool
    runtime_mode: str
    venv_provider: str


def init_workspace_env(
    *,
    start: Path | None = None,
    base_python: str | None = None,
    alpha_source: str | Path | None = None,
    edge_spec: str | None = None,
    edge_source: str | Path | None = None,
    runtime_python: str | Path | None = None,
    alpha_editable: bool = True,
) -> EnvInitResult:
    """Create the workspace venv and install Abel strategy discovery plus dependencies."""
    workspace_root, _ = resolve_workspace_entry(start)
    if workspace_root is None:
        target = default_workspace_path(start)
        raise RuntimeError(
            "No Abel strategy discovery workspace found. Run "
            f"`abel-strategy-discovery workspace bootstrap --path {target}` first."
        )

    manifest = load_workspace_manifest(workspace_root)
    paths = resolve_workspace_paths(workspace_root, manifest)
    venv_path = paths["venv"]
    created_venv = False
    runtime_mode = "managed_venv"
    venv_provider = "python -m venv"

    if runtime_python is not None:
        python_path = record_existing_runtime_python(
            workspace_root,
            manifest,
            Path(runtime_python).expanduser(),
        )
        runtime_mode = "existing_python"
    else:
        python_path = resolve_runtime_python(workspace_root, manifest)
        if not python_path.exists():
            interpreter = base_python or sys.executable
            try:
                venv_provider = create_workspace_venv(
                    interpreter=interpreter,
                    venv_path=venv_path,
                    cwd=workspace_root,
                )
            except RuntimeError as exc:
                raise RuntimeError(
                    "Failed to create the workspace virtual environment. "
                    "This usually means the selected Python cannot run `python -m venv` "
                    "(for example missing `python3-venv` or `ensurepip`). Abel strategy discovery "
                    "will automatically try `uv venv --seed` when uv is installed, "
                    "but that fallback also failed here. "
                    "In locked-down environments, create or choose an existing interpreter "
                    "and rerun `abel-strategy-discovery env init --runtime-python /path/to/python`.\n\n"
                    f"Underlying error:\n{exc}"
                ) from exc
            created_venv = True

    resolved_alpha_source = resolve_alpha_source(alpha_source)
    resolved_edge_source = resolve_edge_source(explicit=edge_source)
    resolved_edge_spec = resolve_edge_install_target(
        workspace_root,
        manifest,
        explicit=edge_spec,
    )

    run_command(
        [str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=workspace_root,
    )

    if resolved_edge_source is not None:
        run_command(
            build_local_install_command(
                python_path,
                resolved_edge_source,
                editable=True,
            ),
            cwd=workspace_root,
        )
        edge_install_target = str(resolved_edge_source)
        edge_install_mode = "local_source"
    else:
        run_command(
            [str(python_path), "-m", "pip", "install", resolved_edge_spec],
            cwd=workspace_root,
        )
        edge_install_target = resolved_edge_spec
        edge_install_mode = "pip_spec"

    run_command(
        [str(python_path), "-m", "pip", "install", "PyYAML>=6.0"],
        cwd=workspace_root,
    )
    run_command(
        build_local_install_command(
            python_path,
            resolved_alpha_source,
            editable=alpha_editable,
            no_deps=True,
        ),
        cwd=workspace_root,
    )

    record_edge_install_target(
        workspace_root,
        manifest,
        edge_install_target=edge_install_target,
        edge_install_mode=edge_install_mode,
    )

    edge_discovery_payload_capable = probe_edge_discovery_payload(python_path, workspace_root)
    edge_context_json_capable = probe_edge_context_json(python_path, workspace_root)

    return EnvInitResult(
        workspace_root=workspace_root,
        venv_path=venv_path,
        python_path=python_path,
        alpha_source=resolved_alpha_source,
        edge_install_target=edge_install_target,
        edge_install_mode=edge_install_mode,
        edge_discovery_payload_capable=edge_discovery_payload_capable,
        edge_context_json_capable=edge_context_json_capable,
        alpha_editable=alpha_editable,
        created_venv=created_venv,
        runtime_mode=runtime_mode,
        venv_provider=venv_provider,
    )


def build_local_install_command(
    python_path: Path,
    source: Path,
    *,
    editable: bool,
    no_deps: bool = False,
) -> list[str]:
    """Build the pip install command for a local source tree."""
    command = [str(python_path), "-m", "pip", "install"]
    if editable:
        command.extend(["-e", str(source)])
    else:
        command.append(str(source))
    if no_deps:
        command.append("--no-deps")
    return command


def create_workspace_venv(*, interpreter: str, venv_path: Path, cwd: Path) -> str:
    """Create the workspace venv, falling back to uv when stdlib venv is unavailable."""
    try:
        run_command([interpreter, "-m", "venv", str(venv_path)], cwd=cwd)
        return "python -m venv"
    except RuntimeError as exc:
        uv_bin = which("uv")
        if not uv_bin:
            raise exc
        command = [uv_bin, "venv", "--seed"]
        if interpreter:
            command.extend(["--python", str(interpreter)])
        command.append(str(venv_path))
        try:
            run_command(command, cwd=cwd)
        except RuntimeError as uv_exc:
            raise RuntimeError(
                f"{exc}\n\nuv fallback also failed:\n{uv_exc}"
            ) from uv_exc
        return "uv venv --seed"


def resolve_alpha_source(explicit: str | Path | None = None) -> Path:
    """Resolve the strategy-discovery skill source tree used for workspace installs."""
    if explicit is not None:
        return validate_source_tree(Path(explicit).expanduser().resolve(), "Abel strategy discovery")

    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "pyproject.toml").exists():
        return candidate

    raise RuntimeError(
        "Could not resolve a local Abel strategy discovery source tree. "
        "Pass `--alpha-source /path/to/skills/abel-strategy-discovery`."
    )


def resolve_edge_source(*, explicit: str | Path | None = None) -> Path | None:
    """Resolve an explicit local Abel-edge source tree override."""
    if explicit is not None:
        return validate_source_tree(Path(explicit).expanduser().resolve(), "Abel-edge")
    return None


def resolve_edge_install_target(
    root: Path,
    manifest: dict,
    *,
    explicit: str | None = None,
) -> str:
    """Resolve the default non-local Abel-edge install target."""
    configured = (explicit or "").strip()
    if configured:
        return configured
    return resolve_edge_spec(root, manifest)


def record_edge_install_target(
    workspace_root: Path,
    manifest: dict,
    *,
    edge_install_target: str,
    edge_install_mode: str,
) -> None:
    """Persist the selected Abel-edge install target back into the manifest."""
    runtime = manifest.setdefault("runtime", {})
    runtime["edge_spec"] = edge_install_target
    runtime["edge_install_mode"] = edge_install_mode
    write_workspace_manifest(workspace_root, manifest)


def record_existing_runtime_python(
    workspace_root: Path,
    manifest: dict,
    runtime_python: Path,
) -> Path:
    """Persist an explicit existing interpreter path into the workspace manifest."""
    expanded = runtime_python.expanduser()
    absolute = expanded if expanded.is_absolute() else (Path.cwd() / expanded)
    normalized = absolute.resolve(strict=False)
    if not normalized.exists():
        raise RuntimeError(f"Existing runtime python does not exist: {normalized}")
    runtime = manifest.setdefault("runtime", {})
    runtime["python"] = make_manifest_path(workspace_root, absolute)
    write_workspace_manifest(workspace_root, manifest)
    return absolute


def make_manifest_path(workspace_root: Path, path: Path) -> str:
    """Serialize a path into the manifest, preferring workspace-relative form."""
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


def validate_source_tree(path: Path, label: str) -> Path:
    """Validate that a local source path looks like an installable Python project."""
    if not (path / "pyproject.toml").exists():
        raise RuntimeError(f"{label} source path does not contain pyproject.toml: {path}")
    return path


def run_command(command: list[str], *, cwd: Path) -> None:
    """Run a command and raise a readable error on failure."""
    try:
        subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        rendered = " ".join(command)
        details = (exc.stderr or exc.stdout or "").strip()
        message = f"Command failed with exit code {exc.returncode}: {rendered}"
        if details:
            message = f"{message}\n{details}"
        raise RuntimeError(message) from exc
