"""Workspace scaffolding and discovery for Abel strategy discovery."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

MANIFEST_NAME = "alpha.workspace.yaml"
DEFAULT_EDGE_SPEC = "git+https://github.com/Abel-ai-causality/Abel-edge.git@main"
DEFAULT_WORKSPACE_NAME = "abel-strategy-discovery-workspace"


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Return the nearest workspace root at or above ``start``."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / MANIFEST_NAME).exists():
            return candidate
    return None


def is_workspace_root(path: Path) -> bool:
    """Return whether ``path`` contains an Abel strategy discovery workspace manifest."""
    return (path / MANIFEST_NAME).exists()


def default_workspace_path(start: Path | None = None) -> Path:
    """Return the default child workspace path for a launch root."""
    current = (start or Path.cwd()).expanduser().resolve()
    return current / DEFAULT_WORKSPACE_NAME


def find_containing_workspace_root(path: Path) -> Path | None:
    """Return the existing workspace root containing ``path`` when it is nested inside one."""
    current = path.expanduser().resolve()
    search_from = current if current.exists() else current.parent
    candidate = find_workspace_root(search_from)
    if candidate is None or candidate == current:
        return None
    return candidate


def inspect_workspace_bootstrap_target(path: Path) -> tuple[str, Path | None]:
    """Classify whether ``path`` is safe to use as a bootstrap target."""
    current = path.expanduser().resolve()
    if is_workspace_root(current):
        return "existing_workspace_root", current

    containing_root = find_containing_workspace_root(current)
    if containing_root is not None:
        return "nested_workspace", containing_root

    child = default_workspace_path(current)
    if child != current and is_workspace_root(child):
        return "launch_root_child_workspace", child

    return "clear", None


def resolve_workspace_entry(start: Path | None = None) -> tuple[Path | None, str]:
    """Resolve workspace re-entry from a workspace root, descendant, or launch root."""
    current = (start or Path.cwd()).expanduser().resolve()
    if is_workspace_root(current):
        return current, "current_workspace_root"

    ancestor = find_workspace_root(current)
    if ancestor is not None:
        return ancestor, "workspace_ancestor"

    child = default_workspace_path(current)
    if is_workspace_root(child):
        return child, "launch_root_child"

    return None, "missing"


def load_workspace_manifest(root: Path) -> dict:
    """Load the workspace manifest from ``root``."""
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"No {MANIFEST_NAME} found under {root}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid workspace manifest at {manifest_path}")
    return data


def write_workspace_manifest(root: Path, manifest: dict) -> None:
    """Write the workspace manifest back to disk."""
    write_text(root / MANIFEST_NAME, dump_manifest(manifest))


def resolve_workspace_paths(root: Path, manifest: dict | None = None) -> dict[str, Path]:
    """Resolve well-known workspace-relative paths to absolute paths."""
    manifest = manifest or load_workspace_manifest(root)
    paths = manifest.get("paths") or {}
    return {
        "research_root": root / str(paths.get("research_root", "research")),
        "docs_root": root / str(paths.get("docs_root", "docs")),
        "cache_root": root / str(paths.get("cache_root", "cache/market_data")),
        "logs_root": root / str(paths.get("logs_root", "logs")),
        "venv": root / str(paths.get("venv", ".venv")),
    }


def resolve_workspace_env_file(root: Path) -> Path:
    """Resolve the workspace-local auth environment file path."""
    return root / ".env"


def resolve_runtime_python(root: Path, manifest: dict | None = None) -> Path:
    """Resolve the configured runtime python path to an absolute path."""
    manifest = manifest or load_workspace_manifest(root)
    runtime = manifest.get("runtime") or {}
    configured = Path(str(runtime.get("python", default_python_path())))
    if configured.is_absolute():
        return configured
    return root / configured


def resolve_edge_spec(root: Path, manifest: dict | None = None) -> str:
    """Resolve the configured Abel-edge install spec for this workspace."""
    manifest = manifest or load_workspace_manifest(root)
    runtime = manifest.get("runtime") or {}
    configured = str(runtime.get("edge_spec") or "").strip()
    return configured or DEFAULT_EDGE_SPEC


def scaffold_workspace(
    name: str,
    *,
    target_root: Path | None = None,
    allow_existing_empty: bool = False,
) -> Path:
    """Create a new Abel strategy discovery workspace directory with the standard layout."""
    root = (target_root or Path.cwd() / name).resolve()
    containing_root = find_containing_workspace_root(root)
    if containing_root is not None:
        raise RuntimeError(
            "Refusing to create a nested Abel strategy discovery workspace at "
            f"'{root}' because '{containing_root}' is already the workspace root "
            "for this working area."
        )
    if root.exists():
        if not root.is_dir():
            raise FileExistsError(
                f"Path '{root}' already exists and is not a directory."
            )
        if not allow_existing_empty or any(root.iterdir()):
            raise FileExistsError(
                f"Directory '{root}' already exists. Choose a different workspace name or path."
            )
    else:
        root.mkdir(parents=True)
    manifest = build_default_manifest(name=name)
    resolved = resolve_workspace_paths(root, manifest)
    for key in ("docs_root", "research_root", "cache_root", "logs_root"):
        resolved[key].mkdir(parents=True, exist_ok=True)

    write_text(root / MANIFEST_NAME, dump_manifest(manifest))
    write_text(root / ".gitignore", render_gitignore())
    write_text(root / ".env.example", render_env_example())
    write_text(root / ".env", "")
    write_text(root / "README.md", render_workspace_readme(name))
    write_text(root / "AGENTS.md", render_workspace_agents())

    return root


def build_default_manifest(name: str) -> dict:
    """Build the default manifest structure for a new workspace."""
    return {
        "version": 1,
        "workspace": {
            "name": name,
            "kind": "abel-strategy-discovery",
        },
        "paths": {
            "research_root": "research",
            "docs_root": "docs",
            "cache_root": "cache/market_data",
            "logs_root": "logs",
            "venv": ".venv",
        },
        "runtime": {
            "python": default_python_path(),
            "edge_package": "causal-edge",
            "edge_spec": DEFAULT_EDGE_SPEC,
            "auth_strategy": "reuse_abel_auth_first",
        },
        "defaults": {
            "backtest_start": "2020-01-01",
            "discovery_limit": 10,
        },
    }


def dump_manifest(manifest: dict) -> str:
    """Serialize the workspace manifest to YAML."""
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False)


def default_python_path() -> str:
    """Return the default interpreter path inside a local virtual environment."""
    if os.name == "nt":
        return ".venv/Scripts/python.exe"
    return ".venv/bin/python"


def default_activate_command() -> str:
    """Return the default shell command for activating the local virtualenv."""
    if os.name == "nt":
        return ".venv\\Scripts\\Activate.ps1"
    return "source .venv/bin/activate"


def render_workspace_status(root: Path, manifest: dict | None = None) -> str:
    """Render a human-readable workspace status summary."""
    manifest = manifest or load_workspace_manifest(root)
    resolved = resolve_workspace_paths(root, manifest)
    runtime_python = resolve_runtime_python(root, manifest)
    lines = [
        f"Workspace: {manifest.get('workspace', {}).get('name', root.name)}",
        f"Root: {root}",
        f"Manifest: {root / MANIFEST_NAME}",
        "Workspace mode: alpha-managed branch research",
        f"Workspace env file: {resolve_workspace_env_file(root)}",
        f"Research root: {resolved['research_root']}",
        f"Docs root: {resolved['docs_root']}",
        f"Cache root: {resolved['cache_root']}",
        f"Logs root: {resolved['logs_root']}",
        f"Venv: {resolved['venv']}",
        f"Runtime python: {runtime_python}",
        f"Runtime python exists: {'yes' if runtime_python.exists() else 'no'}",
        f"Edge install target: {resolve_edge_spec(root, manifest)}",
    ]
    return "\n".join(lines)


def render_workspace_readme(name: str) -> str:
    """Render the starter README for a new workspace."""
    return f"""# {name}

This is an Abel strategy discovery research workspace.

Treat this directory as the canonical workspace for this working area.
Treat this workspace's `.venv` as the canonical runtime for daily research.
If `alpha.workspace.yaml` already exists here, this directory is already the
workspace root. Do not bootstrap `./abel-strategy-discovery-workspace` inside it.

The CLI commands below are the tools Abel strategy discovery uses to continue research
inside this workspace. The point is not to memorize a checklist. The point is
to keep the current research state legible while you move from session setup
into branch evidence.

## A Usual Path

```bash
abel-strategy-discovery doctor
{default_activate_command()}
abel-strategy-discovery init-session --ticker TSLA --exp-id tsla-v1
abel-strategy-discovery init-branch --session research/tsla/tsla-v1 --branch-id <family-a-branch>
abel-strategy-discovery init-branch --session research/tsla/tsla-v1 --branch-id <family-b-branch>
edit research/tsla/tsla-v1/branches/<family-a-branch>/branch.yaml
edit research/tsla/tsla-v1/branches/<family-b-branch>/branch.yaml
edit research/tsla/tsla-v1/research_journal.md
edit research/tsla/tsla-v1/branches/<chosen-branch>/engine.py
abel-strategy-discovery prepare-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
abel-strategy-discovery debug-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
abel-strategy-discovery run-branch --branch research/tsla/tsla-v1/branches/<chosen-branch> -d "baseline"
edit research/tsla/tsla-v1/research_journal.md
abel-strategy-discovery upload-dashboard-bundle --branch research/tsla/tsla-v1/branches/<chosen-branch> --base-url <router-base-url>
```

Use that path as orientation, not as a rigid script. The important boundary is:
- `doctor` tells you whether the workspace is actually ready
- `branch.yaml` makes the branch inputs explicit
- `prepare-branch` resolves inputs before you treat any round as evidence
- the starter `engine.py` is only there to verify branch wiring before a branch-specific mechanism exists
- new sessions default to graph-first research: use causal graph inputs first,
  then strategy variants, then parameters
- every recorded round requires an agent-written `research_journal.md` entry
  with the round ledger ref before the next recorded round

## Re-entry

- if `alpha.workspace.yaml` exists in the current directory, continue here and do not create `./abel-strategy-discovery-workspace`
- if you open this workspace root again later, continue here
- if you open the parent launch directory later, reuse its child `abel-strategy-discovery-workspace` before creating another one
- do not create a second workspace in the same area unless you want one intentionally

## What This Workspace Makes Explicit

- session owns `discovery.json` and `readiness.json`
- session owns `evidence_ledger.json`, `frontier.md`, `agent_context.md`, and
  `research_journal.md` after rendering
- branch owns `branch.yaml`
- edge owns the market-data cache
- `prepare-branch` should run before a recorded round
- `frontier.md` reports input realization: declared graph-supported inputs only
  count as realized when the engine reads prepared auxiliary inputs
- `upload-dashboard-bundle` uploads branch evidence from the current workspace
  surfaces, not promotion or replay artifacts
- session `backtest_start` is a default target; branch `requested_start` can override it explicitly
- the generated `engine.py` is a starter baseline for the first end-to-end run, not a finished branch thesis

## Workspace Boundary

- This workspace is for alpha-managed branch research.
- Keep research sessions and branches under `research/`.
- Do not run `causal-edge init` inside this workspace.
- If you need a standalone Abel-edge project, create it in a separate directory outside this workspace.

If the workspace runtime is missing or you want to replace it, run
`abel-strategy-discovery env init` again.
If your environment cannot create a new venv, point alpha at an existing
interpreter with `abel-strategy-discovery env init --runtime-python /path/to/python`.

## Readiness Gate

Run `abel-strategy-discovery doctor` before opening a session.

- `ready`: you can start research
- `ready` means continue with `init-session -> init-branch -> branch.yaml -> prepare-branch`
- `auth_missing`: no reusable auth was found; use `abel-auth`, then rerun `doctor`
- `env_missing`, `edge_missing`, or `edge_contract_missing`: rerun `abel-strategy-discovery env init`
"""


def render_workspace_agents() -> str:
    """Render the starter AGENTS guide for a new workspace."""
    return """# AGENTS.md — Abel strategy discovery Workspace

Use this workspace as the default place to continue research for this working
area. The CLI commands below are tools for operating inside this workspace, but
the goal is to keep the current branch state understandable rather than to
follow a rigid script.

## I want to...

### Check whether this directory is a valid workspace
```bash
abel-strategy-discovery workspace status
abel-strategy-discovery doctor
```

If `alpha.workspace.yaml` is already present in this directory, this directory
is the workspace root. Do not create `./abel-strategy-discovery-workspace` inside it.

### Start a new exploration session
```bash
abel-strategy-discovery doctor
abel-strategy-discovery init-session --ticker TSLA --exp-id tsla-v1
abel-strategy-discovery init-branch --session research/tsla/tsla-v1 --branch-id <family-a-branch>
abel-strategy-discovery init-branch --session research/tsla/tsla-v1 --branch-id <family-b-branch>
edit research/tsla/tsla-v1/branches/<family-a-branch>/branch.yaml
edit research/tsla/tsla-v1/branches/<family-b-branch>/branch.yaml
edit research/tsla/tsla-v1/research_journal.md
edit research/tsla/tsla-v1/branches/<chosen-branch>/engine.py
abel-strategy-discovery prepare-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
abel-strategy-discovery debug-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
abel-strategy-discovery run-branch --branch research/tsla/tsla-v1/branches/<chosen-branch> -d "baseline"
edit research/tsla/tsla-v1/research_journal.md
abel-strategy-discovery upload-dashboard-bundle --branch research/tsla/tsla-v1/branches/<chosen-branch> --base-url <router-base-url>
```

Run `doctor` before `init-session`. If it reports `auth_missing`, use
`abel-auth`, then rerun `doctor`.
Treat `branch.yaml` as the place where target, start, drivers, and overlap
become explicit. Treat `prepare-branch` as the moment that makes those inputs
real. Treat the generated `engine.py` as a starter path check; once the branch
path is proven, encode the branch-specific mechanism there. Treat session
readiness as advisory context; the branch's explicit `requested_start` is the
runtime start when it is set. Treat this workspace `.venv` as the canonical
runtime for daily work. Treat branch count as a file-organization fact, not as
proof of graph/input breadth. Use `research_journal.md` to record your own
evidence-linked insight and continue/pivot reasoning after each recorded round.
Check journal coverage before starting another round. Check input realization before treating a
declared graph-supported branch as graph-supported evidence. When a branch has
candidate evidence worth external inspection, `upload-dashboard-bundle` sends
branch evidence from the current workspace surfaces.
This workspace is for alpha-managed branch research, so do not create a
standalone `causal-edge init` project inside it. Put standalone edge work in a
separate directory.

### Run one research round
```bash
abel-strategy-discovery debug-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
abel-strategy-discovery run-branch --branch research/tsla/tsla-v1/branches/<chosen-branch> -d "baseline"
abel-strategy-discovery promote-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
```

### Understand the workspace layout
- `alpha.workspace.yaml` is the source of truth for workspace defaults
- `research/` stores sessions, branches, and evaluation outputs
- `docs/` stores plans, summaries, and iteration records
- `cache/market_data/` is the edge-owned shared cache root

### Re-enter this workspace later
- if `alpha.workspace.yaml` is in the current directory, continue here directly and do not bootstrap a child workspace
- if you are already in this workspace root, continue here directly
- if you are in the parent launch directory, reuse its `abel-strategy-discovery-workspace` child before creating another one
"""


def render_gitignore() -> str:
    """Render the default workspace gitignore."""
    return """# Abel strategy discovery workspace
.venv/
.env
cache/
logs/
__pycache__/
*.pyc
"""


def render_env_example() -> str:
    """Render the starter environment example."""
    return """# Optional override for standalone Abel auth fallback
# ABEL_API_KEY=

# Optional: point causal-edge at a shared auth file
# ABEL_AUTH_ENV_FILE=
"""


def write_text(path: Path, content: str) -> None:
    """Write text using UTF-8 encoding."""
    path.write_text(content, encoding="utf-8")
