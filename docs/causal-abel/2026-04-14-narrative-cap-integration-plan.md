# Narrative CAP Integration Implementation Plan

> For the current scope, this plan covers only the minimum changes needed to integrate the narrative CAP server into `causal-abel` as an internal helper for proxy-routed workflows.

## Goal

Teach `causal-abel` how to use the narrative CAP provider during proxy-routed mapping and hybrid exploration, while keeping graph CAP as the primary source for graph-validated findings.

## Planned Deliverables

1. Short skill-text update in `SKILL.md`
2. Small proxy-routed reference update
3. New `narrative_cap_probe.py` helper script
4. Local maintainer config support for the narrative provider
5. Basic smoke coverage for the new probe path

## Files To Touch

Prompt and references:

- `skills/causal-abel/SKILL.md`
- `skills/causal-abel/references/routes/proxy-routed.md`
- optional: `skills/causal-abel/references/narrative-cap-usage.md`

Scripts:

- `skills/causal-abel/scripts/narrative_cap_probe.py`

Maintainer config:

- `maintainers/causal-abel/README.md`
- `maintainers/causal-abel/endpoint_config.py`
- `maintainers/causal-abel/endpoints.local.example.json`
- local-only `maintainers/causal-abel/endpoints.local.json` when testing

Tests and smoke:

- `maintainers/causal-abel/smoke_narrative_cap_probe.py`
- optional unit tests near existing probe tests if the repo wants script-level coverage

## Implementation Steps

### 1. Update skill wording with net-minimal text growth

Edit `skills/causal-abel/SKILL.md` Step 3 so it:

- says `proxy_routed` may use narrative CAP first for mapping, anchor discovery, or candidate mechanism generation
- says graph CAP should lead if it can validate the anchors
- says hybrid answers must stay labeled as hybrid if graph CAP cannot carry the question
- forbids presenting narrative or hybrid outputs as graph-validated observational or interventional effects

Constraint:

- replace existing wording instead of adding a full new section
- keep the text short and searchable

### 2. Update proxy-routed reference language

Edit `skills/causal-abel/references/routes/proxy-routed.md` so the Step 3a screening line becomes:

- executable anchors rather than graph nodes only
- manual -> narrative CAP when helpful -> `query_node` -> capillary discovery

Also update the “no path” wording from `narrative-only` to `hybrid-only unless later graph support appears`.

Constraint:

- keep the existing route file structure
- do not add a large new flowchart

### 3. Add `narrative_cap_probe.py`

Implement a dedicated helper script at `skills/causal-abel/scripts/narrative_cap_probe.py`.

Required commands:

- `card`
- `methods`
- `narrate`
- `resolve-entity`
- `explain-read-bundle`
- `search-prepare`
- `predict`
- `what-if`

Required behavior:

- default base URL comes from config or CLI
- `card` calls `GET /.well-known/cap.json`
- other commands call `POST /api/v1/cap`
- preserve `graph_ref`, session handles, execution refs, and node refs exactly as returned by provider
- do not normalize tickers into `.price` or `.volume`
- support compact JSON output similar in spirit to the current graph probe

Suggested implementation shape:

- reuse the no-third-party-dependency style from the current `cap_probe.py` if practical
- keep helper functions small:
  - base URL normalization
  - auth header resolution
  - request envelope builder
  - response formatter

### 4. Add maintainer-local endpoint support

Extend maintainer config so local renders can enable the narrative provider without shipping the SIT endpoint in the public skill by default.

Minimum config surface:

- `narrative_cap_enabled`
- `narrative_cap_base_url`
- optional `narrative_cap_api_key_env`

Expected outcome:

- local SIT skill render can mention and use the narrative provider
- public skill render remains safe and neutral by default

### 5. Add a small usage reference

If the script surface is large enough to justify it, add a very short `references/narrative-cap-usage.md` that shows:

- when to use the new helper
- the 3 to 4 most important commands
- a reminder that graph validation still takes precedence when available

Constraint:

- keep this file short
- do not duplicate the whole skill policy there

### 6. Add smoke coverage

Create `maintainers/causal-abel/smoke_narrative_cap_probe.py`.

Minimum smoke checks:

- capability card fetch succeeds
- `meta.methods` returns at least one known core verb
- `narrate` succeeds on one fixed query
- `search-prepare` succeeds on one fixed query

This smoke runner should report provider reachability separately from query success so maintainers can tell “endpoint exists” from “backend runtime is healthy”.

## Verification Commands

Run after implementation:

```bash
cd /Users/rayz/Documents/causal-agent-protocol/Abel-skills
python3 maintainers/causal-abel/smoke_narrative_cap_probe.py
```

Script-level spot checks:

```bash
cd /Users/rayz/Documents/causal-agent-protocol/Abel-skills/skills/causal-abel
python scripts/narrative_cap_probe.py card
python scripts/narrative_cap_probe.py methods --verbs narrate
python scripts/narrative_cap_probe.py narrate --query "AI datacenter demand and NVDA"
python scripts/narrative_cap_probe.py search-prepare --query "AI datacenter demand and NVDA"
```

Manual wording check:

- read the edited `SKILL.md`
- confirm the new rule is present
- confirm there is no large new provider taxonomy
- confirm graph-vs-hybrid honesty language is explicit

## Risks

- The narrative provider may evolve its extension verbs faster than the graph skill evolves.
- The SIT runtime may be reachable but partially unhealthy.
- Prompt wording may still overfit to graph-first behavior if the new routing sentence is too weak.
- Prompt wording may overuse the narrative provider if the new routing sentence is too strong.

## Open Decisions

These do not block the current plan, but they should be revisited during implementation:

- whether to keep the helper script fully standalone or factor shared HTTP helpers with the existing graph probe
- whether the narrative provider should have a tiny dedicated reference file or rely only on script `--help`
- whether unit tests are needed immediately or if maintainer smoke coverage is enough for the first pass

