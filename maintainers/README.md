# Maintainer Sources

`maintainers/skills/` is the maintainer-owned source tree for the full Abel
skills collection.

`skills/` is the rendered public install tree.

`maintainers/endpoints.json` is the public-safe profile source for collection
renders.

Local profile overrides should stay outside the public collection source. The
renderer checks these paths in order and uses the first one that exists:

- `maintainers/endpoints.local.json`
- `maintainers/causal-abel/endpoints.local.json`
- `maintainers/abel-ask/endpoints.local.json`

Use `python3 maintainers/render_collection.py --profile prod` to rebuild the
public `skills/` tree from `maintainers/skills/`.

Ask-specific helpers still live under `maintainers/abel-ask/`, but they now
consume the shared maintainer profile config and mainly exist for compatibility
or focused local testing.
