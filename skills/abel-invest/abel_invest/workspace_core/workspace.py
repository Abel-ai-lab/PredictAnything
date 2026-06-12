"""Workspace scaffolding and discovery for Abel strategy discovery."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from abel_invest import __version__ as ABEL_INVEST_VERSION

MANIFEST_NAME = "alpha.workspace.yaml"
DEFAULT_WORKSPACE_NAME = "abel-invest-workspace"
WORKSPACE_AGENTS_GUIDE_SCHEMA = "abel-invest.workspace-agents/v1"
WORKSPACE_AGENTS_GUIDE_VERSION = ABEL_INVEST_VERSION


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


def resolve_runtime_cli(root: Path, manifest: dict | None = None) -> Path:
    """Resolve the expected Abel Invest CLI path beside the workspace Python."""
    python_path = resolve_runtime_python(root, manifest)
    cli_name = "abel-invest.exe" if os.name == "nt" else "abel-invest"
    return python_path.with_name(cli_name)


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
            "kind": "abel-invest",
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
    agents_status = workspace_agents_status(root)
    lines = [
        f"Workspace: {manifest.get('workspace', {}).get('name', root.name)}",
        f"Root: {root}",
        f"Manifest: {root / MANIFEST_NAME}",
        "Workspace mode: alpha-managed strategy search",
        f"Workspace env file: {resolve_workspace_env_file(root)}",
        f"Research root: {resolved['research_root']}",
        f"Docs root: {resolved['docs_root']}",
        f"Cache root: {resolved['cache_root']}",
        f"Logs root: {resolved['logs_root']}",
        f"Venv: {resolved['venv']}",
        f"Runtime python: {runtime_python}",
        f"Runtime python exists: {'yes' if runtime_python.exists() else 'no'}",
        (
            "Agents guide: "
            f"{agents_status['status']} "
            f"(expected abel-invest {agents_status['expectedVersion']})"
        ),
        "Edge dependency: managed by abel-invest package dependencies",
    ]
    return "\n".join(lines)


def render_workspace_readme(name: str) -> str:
    """Render the starter README for a new workspace."""
    return f"""# {name}

This is an Abel Invest alpha-search workspace.

Treat this directory as the canonical workspace for this working area.
Treat this workspace's `.venv` as the canonical runtime for daily alpha search.
From this workspace root, use `./.venv/bin/abel-invest` as the command prefix,
or activate `.venv` first and then use `abel-invest`.
If `alpha.workspace.yaml` already exists here, this directory is already the
workspace root. Do not bootstrap `./abel-invest-workspace` inside it.

The CLI commands below keep alpha search auditable inside this workspace. The
point is not to memorize a checklist. The point is to search hard while keeping
the current state legible from session setup into branch evidence.

## A Usual Path

Run these commands from the workspace root:

```bash
./.venv/bin/abel-invest workspace context --path . --json
./.venv/bin/abel-invest doctor
{default_activate_command()}
./.venv/bin/abel-invest init-session --ticker TSLA --exp-id tsla-v1
./.venv/bin/abel-invest frontier status --session research/tsla/tsla-v1
./.venv/bin/abel-invest init-branch --session research/tsla/tsla-v1 --branch-id <candidate-branch>
```

Read or edit these files before the first recorded round:

- `research/tsla/tsla-v1/branches/<candidate-branch>/branch.yaml`
- `research/tsla/tsla-v1/exploration_path.md`
- `research/tsla/tsla-v1/branches/<chosen-branch>/engine.py`

Then run the branch preflight and recorded round:

```bash
./.venv/bin/abel-invest prepare-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
./.venv/bin/abel-invest debug-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
./.venv/bin/abel-invest run-branch --branch research/tsla/tsla-v1/branches/<chosen-branch> -d "candidate search result"
```

After every recorded round, follow the `Decision checkpoint` printed by
`run-branch`: either update `exploration_path.md` with ledger ref, chosen path,
compact reason, Edge feedback, and artifact refs before continuing a concrete
exploration action, or enter final report.

When exploration enters Completed, if at least one real candidate strategy round
has been recorded, summarize the selected strategy with the read-only final
report handoff:

```bash
./.venv/bin/abel-invest best-strategy --session research/tsla/tsla-v1 --json
```

This command is read-only: it prepares the stop-report payload and report
guidance without exporting, uploading, or promoting artifacts.

Then ask the user whether to create a session review page. Only after getting
agreement, run:

```bash
./.venv/bin/abel-invest visualize-session --session research/tsla/tsla-v1
```

Use that path as orientation, not as a rigid script. The important boundary is:
- `doctor` tells you whether the workspace is actually ready
- `workspace context --json` tells you the owning workspace and `research_root`
- `branch.yaml` makes the branch inputs explicit
- `prepare-branch` resolves inputs before you treat any round as evidence
- the starter `engine.py` is only there to verify branch wiring before a branch-specific candidate exists
- new sessions default to data-led alpha search with graph-enriched context:
  use `graph_frontier.json` as the high-value expanded feature universe for
  feature factories, model/denoise lanes, node-subset search, lag/sign search,
  regimes, filters, sizing, and ensembles; do not reduce graph use to a
  full-frontier quota or a few hand-written node rules
- target-only candidates are baselines, seeds, ablations, and competitors for
  measuring graph-derived marginal contribution, not the default main lane when
  graph-derived data is live and unsearched
- every recorded round ends with a `Decision checkpoint`; continue only after
  `exploration_path.md` is covered, or enter final report with `best-strategy`
- every next Edge run should be chosen after reading `exploration_path.md` and
  the latest Edge result; `run-branch` appends a concise entry there

## Re-entry

- if `alpha.workspace.yaml` exists in the current directory, continue here and do not create `./abel-invest-workspace`
- if you open this workspace root again later, continue here
- if you open the parent launch directory later, reuse its child `abel-invest-workspace` before creating another one
- do not create a second workspace in the same area unless you want one intentionally
- create new sessions only after workspace context resolves; use `--root` only
  for intentional outside-workspace legacy/offline sessions and pass
  `--allow-outside-workspace`

## What This Workspace Makes Explicit

- session owns `graph_frontier.json` and `readiness.json`
- session owns `evidence_ledger.json`, `frontier.md`, `agent_context.md`,
  and `exploration_path.md` after rendering
- branch owns `branch.yaml`
- edge owns the market-data cache
- `prepare-branch` should run before a recorded round
- `frontier.md` reports input realization: declared graph-supported inputs only
  count as realized when the engine reads prepared graph inputs
- `best-strategy` is the read-only entrypoint for stop reports: it prepares the
  final-report handoff without exporting, uploading, or promoting artifacts
- `visualize-session` is the default composite entrypoint for session
  visualization: it creates an online session view and, when a hostable
  validation strategy is available, includes selected strategy artifact
  upload/promotion through the strategy-artifact capability. Direct artifact
  export/promotion remain independent commands. If no hostable strategy artifact
  is available, the session view can still be created without one. If a selected
  strategy emits a hosted-paper contract request, continue that loop; if it
  cannot complete, report the session as `action_required`
- session `backtest_start` is a default target; branch `requested_start` can override it explicitly
- the generated `engine.py` is a starter wiring scaffold for the first end-to-end run, not a finished strategy

## Workspace Boundary

- This workspace is for alpha-managed strategy search.
- Keep sessions and branches under `research/`.
- Do not run `abel-edge init` inside this workspace.
- If you need a standalone Abel-edge project, create it in a separate directory outside this workspace.

If the workspace runtime is missing or you want to replace it, run the env
repair command from `doctor`'s `next_step`.
If `doctor` reports `runtime_stale`, run the command from `next_step`, then
rerun `doctor`.
If your environment cannot create a new venv, point alpha at an existing
interpreter by adding `--runtime-python /path/to/python` to that env repair
command.

## Readiness Gate

Run `./.venv/bin/abel-invest workspace context --path . --json` and `./.venv/bin/abel-invest doctor`
before opening a session.

- `ready`: you can start alpha search
- `ready` means continue with `init-session -> init scout/candidate branch -> prepare-branch -> first-look data scout with roughly 5-minute expected runtime before any broad run`; let progressing scout work finish naturally
- `auth_missing`: no reusable auth was found; use `abel-auth`, then rerun `doctor`
- `runtime_stale`, `env_missing`, `edge_missing`, or `edge_contract_missing`:
  run the exact env repair command from `next_step`, then rerun `doctor`
"""


def render_workspace_agents() -> str:
    """Render the starter AGENTS guide for a new workspace."""
    return f"""<!-- {WORKSPACE_AGENTS_GUIDE_SCHEMA} version={WORKSPACE_AGENTS_GUIDE_VERSION} -->
# AGENTS.md — Abel Invest Alpha Search Workspace

Use this workspace as the default place to continue alpha search for this working
area. The CLI commands below are tools for operating inside this workspace, but
the goal is to keep the current branch state understandable rather than to
follow a rigid script.
From this workspace root, use `./.venv/bin/abel-invest` as the command prefix,
or activate `.venv` first and then use `abel-invest`.

## I want to...

### Check whether this directory is a valid workspace
```bash
./.venv/bin/abel-invest workspace context --path . --json
./.venv/bin/abel-invest workspace status
./.venv/bin/abel-invest doctor
```

If `alpha.workspace.yaml` is already present in this directory, this directory
is the workspace root. Do not create `./abel-invest-workspace` inside it.

### Start a new exploration session
Run these commands from the workspace root:

```bash
./.venv/bin/abel-invest workspace context --path . --json
./.venv/bin/abel-invest doctor
./.venv/bin/abel-invest init-session --ticker TSLA --exp-id tsla-v1
./.venv/bin/abel-invest frontier status --session research/tsla/tsla-v1
./.venv/bin/abel-invest init-branch --session research/tsla/tsla-v1 --branch-id <candidate-branch>
```

Read or edit these files before branch execution:

- `research/tsla/tsla-v1/branches/<candidate-branch>/branch.yaml`
- `research/tsla/tsla-v1/exploration_path.md`
- `research/tsla/tsla-v1/branches/<chosen-branch>/engine.py`

Then run:

```bash
./.venv/bin/abel-invest prepare-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
./.venv/bin/abel-invest debug-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
./.venv/bin/abel-invest run-branch --branch research/tsla/tsla-v1/branches/<chosen-branch> -d "candidate search result"
```

Keep `exploration_path.md` covered before another recorded round. Ask the user
before creating an online session view. If the user agrees:

```bash
./.venv/bin/abel-invest visualize-session --session research/tsla/tsla-v1
```

Run `doctor` before `init-session`. If it reports `auth_missing`, use
`abel-auth`, then rerun `doctor`.
If it reports `runtime_stale`, `env_missing`, `edge_missing`, or
`edge_contract_missing`, run the exact env repair command from
`next_step`, then rerun `doctor`. Do not refresh the runtime when `doctor` is
already ready.
Run `workspace context --path . --json` before creating a session so the
session lands under this workspace's `research/` directory. Do not pass
`--root` unless intentionally creating a legacy/offline session outside the
workspace, and then pass `--allow-outside-workspace`.
Treat `branch.yaml` as the place where target, start, selected inputs, objective,
search width, and validation scope become explicit enough to audit. Treat
`prepare-branch` as the moment that makes those inputs real. Treat the generated
`engine.py` as a starter path check; once the branch path is proven, encode the
candidate logic there. Treat session readiness as advisory context; the branch's explicit
`requested_start` is the runtime start when it is set. Treat this workspace
`.venv` as the canonical runtime for daily work. Treat branch count as a
file-organization fact, not as proof of search breadth. Use `exploration_path.md`
as the single human-facing exploration log: record each chosen path, compact
reason, Edge feedback, and ledger ref. Read `exploration_path.md` and the latest
Edge result before choosing the next Edge run; after Edge feedback, keep the
path updated. After every recorded round, follow the `Decision checkpoint`
printed by `run-branch`: either continue a concrete exploration action or enter
final report. Check path coverage before starting another round. Check input
realization before claiming graph-derived contribution. Stay in Exploring until
the objective is met or the ledger supports unable-to-reach; if a concrete next
search action remains, keep Exploring. Treat Edge failures as diagnostics, not
the next objective; when return or Sharpe remain weak, do not only repair gates
into conservative branches. When either normal ending holds, enter Completed.
If interrupted or blocked, do not enter Completed or ask for visualization.
`render`, `status`, and `check` are audit actions only. Do not create
the online session view automatically; a recorded candidate strategy round makes
the session eligible for visualization, but visualization is not a required step
after every round. When exploration enters Completed, use
`best-strategy --session <session> --json` as the final-report handoff; it is
read-only and does not export, upload, or promote artifacts. Follow its
`reportGuidance` and report its selected strategy exactly instead of manually
walking `results.tsv` or branch folders to choose the best session strategy.
Ask the user whether to create a session review page if the handoff says the
session is eligible. If the user agrees or explicitly asks to publish the
session review page, run
`visualize-session --session <session>` before inspecting Abel Invest
implementation internals. It builds the view from the session folder and, when
available, includes selected strategy artifact upload/promotion; if no hostable
strategy artifact is available, the session view can still be created without
one. If the user explicitly names a strategy branch or round to upload or
visualize, use `visualize-session --session <session> --strategy <branch>
--round <round>`. Keep `export-strategy-artifact --session <session>` and
`promote-strategy --branch <branch> --round <round>` for internal local export
or promotion validation probes. Do not run `visualize-session` or
`export-strategy-artifact` merely to compute the best strategy.
If a visualization command, or an internal export/promotion probe, emits a
hosted paper `paper-contract-request.json`, read the request first and use its
`reportTemplate`; when `contractGuide` is needed, open its `referencePath` from
the active Abel Invest skill, not from the workspace or CLI package path.
Edit only when `sourceEditPolicy` says a source edit is required or genuinely
allowed, and declare the paper history boundary in `paper-contract-report.json`.
Rerun the same command afterward. If another request appears, inspect
`validation.lastGateFailure`, `validation.attemptPolicy`, and
`requirements.fallback`, then continue until promotion succeeds, fallback is
eligible and succeeds or fails a gate, or a hard blocker remains. Promotion
converts the selected research strategy into a clean hosted daily live-paper
artifact; do not add one-off schedules or cached tail decisions merely to pass
the gate. Do not start a separate agent process. Leave contract-blocked sessions
as `action_required` unless the user explicitly asks to skip strategy artifacts.
This workspace is for alpha-managed strategy search, so do not create a
standalone `abel-edge init` project inside it. Put standalone edge work in a
separate directory.

### Report to the user
- resolved workspace root and doctor status
- current session and branch path
- live/auth blockers and the exact next command only when you are going to run it
- evidence status honestly: branch declarations are not evidence until prepared and run
- after a recorded round, say that `exploration_path.md` must be updated before another recorded round

### Run one recorded round
```bash
./.venv/bin/abel-invest debug-branch --branch research/tsla/tsla-v1/branches/<chosen-branch>
./.venv/bin/abel-invest run-branch --branch research/tsla/tsla-v1/branches/<chosen-branch> -d "candidate search result"
./.venv/bin/abel-invest visualize-session --session research/tsla/tsla-v1 --strategy research/tsla/tsla-v1/branches/<chosen-branch> --round <round-id>
```

### Understand the workspace layout
- `alpha.workspace.yaml` is the source of truth for workspace defaults
- `research/` stores sessions, branches, and evaluation outputs
- `docs/` stores plans, summaries, and iteration records
- `cache/market_data/` is the edge-owned shared cache root

### Re-enter this workspace later
- if `alpha.workspace.yaml` is in the current directory, continue here directly and do not bootstrap a child workspace
- if you are already in this workspace root, continue here directly
- if you are in the parent launch directory, reuse its `abel-invest-workspace` child before creating another one
- run `./.venv/bin/abel-invest workspace context --path . --json` before creating a session
"""


def workspace_agents_status(root: Path) -> dict[str, str]:
    """Return whether the workspace AGENTS guide matches this Abel Invest version."""
    path = root / "AGENTS.md"
    expected = render_workspace_agents()
    if not path.exists():
        return {
            "status": "missing",
            "path": str(path),
            "schema": WORKSPACE_AGENTS_GUIDE_SCHEMA,
            "expectedVersion": WORKSPACE_AGENTS_GUIDE_VERSION,
            "foundVersion": "",
        }
    actual = path.read_text(encoding="utf-8")
    found_version = _workspace_agents_found_version(actual)
    status = (
        "current"
        if _normalize_generated_text(actual) == _normalize_generated_text(expected)
        else "stale"
    )
    return {
        "status": status,
        "path": str(path),
        "schema": WORKSPACE_AGENTS_GUIDE_SCHEMA,
        "expectedVersion": WORKSPACE_AGENTS_GUIDE_VERSION,
        "foundVersion": found_version,
    }


def refresh_workspace_agents(root: Path) -> dict[str, str]:
    """Refresh the generated workspace AGENTS guide when it is missing or stale."""
    before = workspace_agents_status(root)
    if before["status"] == "current":
        return {**before, "action": "unchanged", "previousStatus": before["status"]}
    (root / "AGENTS.md").write_text(render_workspace_agents(), encoding="utf-8")
    after = workspace_agents_status(root)
    action = "created" if before["status"] == "missing" else "refreshed"
    return {**after, "action": action, "previousStatus": before["status"]}


def _workspace_agents_found_version(text: str) -> str:
    prefix = f"<!-- {WORKSPACE_AGENTS_GUIDE_SCHEMA} version="
    lines = text.splitlines()
    first_line = lines[0].strip() if lines else ""
    if not first_line.startswith(prefix) or not first_line.endswith("-->"):
        return ""
    return first_line.removeprefix(prefix).removesuffix("-->").strip()


def _normalize_generated_text(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip() + "\n"


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

# Optional: point abel-edge at a shared auth file
# ABEL_AUTH_ENV_FILE=
"""


def write_text(path: Path, content: str) -> None:
    """Write text using UTF-8 encoding."""
    path.write_text(content, encoding="utf-8")
