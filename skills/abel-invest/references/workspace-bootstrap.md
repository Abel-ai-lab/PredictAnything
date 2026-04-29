# Workspace Bootstrap

`abel-invest` is workspace-first. Do not start strategy research
until you know which workspace root owns the run.

## Preflight

From the user's current directory:

1. If `alpha.workspace.yaml` exists here, this directory is the workspace root.
2. Else if `abel-invest-workspace/alpha.workspace.yaml` exists here,
   reuse that child workspace.
3. Else run:

```bash
abel-invest workspace bootstrap --path abel-invest-workspace
```

4. Then run:

```bash
abel-invest doctor --path <workspace-root>
```

Only move into session or branch work when doctor reports `Status: ready`.

## Auth

Reuse existing Abel auth first. If doctor reports `auth_missing`, do not start
live discovery yet. Use `abel-auth`, then rerun doctor.

Do not invent a separate auth flow from this skill. `abel-auth` owns explicit
auth handoff and credential setup.

If the user explicitly asks for offline inspection, you may inspect existing
artifacts without auth, but mark live discovery/evaluation as blocked until
doctor is ready.

## Workspace Rules

- Keep research under the workspace `research/` directory.
- Do not create a nested workspace when `alpha.workspace.yaml` already exists.
- Do not create a standalone `abel-edge init` sidecar for this flow.
- Use `workspace status` and `doctor` to inspect setup instead of guessing from
  directory names.
- Bootstrap creates the workspace and runtime base; branch-specific market data
  is resolved later by `prepare-branch`.

## Common Commands

```bash
abel-invest workspace status --path <workspace-root>
abel-invest doctor --path <workspace-root>
abel-invest env init
```

Use `env init` only when doctor reports an environment or edge-runtime setup
problem.
