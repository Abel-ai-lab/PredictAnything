This `AGENTS.md` applies to everything under `Abel-skills/`.

Rules:

- Source skills live under `skills/`. Everything under `dist/` is build output. Do not manually update files in `dist/` unless the user explicitly asks for generated artifacts to be refreshed. `clawhub/causal-abel/` is also a generated import path. Prefer changing source files first, then regenerate when needed.
- Default day-to-day development target is `develop`, not `main`.
- Normal feature branches should be cut from `develop` and merged back into `develop`.
- Treat `main` as the release branch. Only release or hotfix PRs should target `main`.
- Do not bump source skill versions or add top-level release changelog entries in normal feature PRs to `develop`.
- Only release PRs to `main` should update source versions and `CHANGELOG.md` together.
- The ClawHub release artifact is built from the collection source into `dist/`. Do not commit generated release artifacts back into the repository.
- Everything under `dist/` is build output. Do not manually update files in `dist/` unless the user explicitly asks for generated artifacts to be refreshed.
- If user-facing skill content changes, update the source skills and supporting sources first; only rebuild generated outputs after that.
- For the full maintainer workflow, see `docs/branching-and-releases.md`.
- Refer to $skill-creator for writing proper skill prompt
