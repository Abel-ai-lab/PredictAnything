# Workspace Bootstrap

`abel-invest` is workspace-first. Do not start strategy search
until you know which workspace root owns the run.

## Fresh Install Bootstrap

When `abel-invest` is not installed yet, do not try to import `abel_invest`
with the system interpreter. Use the stdlib first-run shim from the installed
skill files:

```bash
python3 <abel-invest-skill-root>/scripts/bootstrap_workspace.py --path abel-invest-workspace
```

The shim creates or reuses the workspace, prepares the workspace runtime,
installs `abel-invest` there, and then runs doctor from that runtime.

After the CLI is installed, use the workspace-local command prefix reported by
doctor or `workspace context`. Do not assume `abel-invest` is on the global PATH.

## Preflight

From the user's current directory:

1. If `alpha.workspace.yaml` exists here, this directory is the workspace root.
2. Else if `abel-invest-workspace/alpha.workspace.yaml` exists here,
   reuse that child workspace.
3. Else bootstrap a workspace:

```bash
abel-invest workspace bootstrap --path abel-invest-workspace
```

4. Then resolve context and run doctor. Use `abel-invest` as `<context-cli>`
   when it is on PATH. If it is not on PATH but the workspace venv exists, use
   `<workspace-root>/.venv/bin/abel-invest` as `<context-cli>` for the first
   context command.

```bash
<context-cli> workspace context --path . --json
<command_prefix> doctor --path <workspace-root>
```

Only move into session or branch work when doctor reports `Status: ready`.

If doctor reports `runtime_stale`, `env_missing`, `edge_missing`, or
`edge_contract_missing`, run the exact env repair command shown in
`next_step`, then rerun doctor. `doctor` only diagnoses workspace runtime
state; `env init` and `env refresh` are the commands that install or upgrade
packages.

## Auth

Reuse existing Abel auth first. If doctor reports `auth_missing`, do not start
live discovery yet. Use `abel-auth`, then rerun doctor.

Do not invent a separate auth flow from this skill. `abel-auth` owns explicit
auth handoff and credential setup.

If the user explicitly asks for offline inspection, you may inspect existing
artifacts without auth, but mark live discovery/evaluation as blocked until
doctor is ready.

## Workspace Rules

- Keep session and branch artifacts under the workspace `research/` directory.
- Do not create a nested workspace when `alpha.workspace.yaml` already exists.
- Do not create a standalone `abel-edge init` sidecar for this flow.
- Use `workspace context`, `workspace status`, and `doctor` to inspect setup
  instead of guessing from directory names.
- Create sessions only after the workspace context resolves. Avoid `--root`
  unless intentionally creating a legacy/offline session outside a workspace;
  then pass `--allow-outside-workspace`.
- Bootstrap creates the workspace and runtime base; branch-specific market data
  is resolved later by `prepare-branch`.

## Common Commands

```bash
<context-cli> workspace context --path . --json
<command_prefix> workspace status --path <workspace-root>
<command_prefix> doctor --path <workspace-root>
<command_prefix> env init
<command_prefix> env refresh --path <workspace-root>
```

Use `env init` or `env refresh` only when doctor reports an environment,
runtime freshness, or edge-runtime setup problem. Prefer the exact command in
doctor's `next_step`.
