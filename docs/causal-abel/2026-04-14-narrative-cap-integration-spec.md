# Narrative CAP Integration Spec

## Goal

Integrate the narrative CAP server from `abel-data-intelligence` into `skills/causal-abel` without turning it into a separate user-facing skill and without overstating its semantic strength.

The integration target is the existing `causal-abel` skill. Users should still invoke one skill. The skill may use the narrative CAP server as an internal helper when a question needs topic mapping, anchor discovery, or hybrid read bundling before graph validation.

## Confirmed Facts

- The narrative service is CAP-native, not just a custom HTTP API.
- The deployed SIT endpoints currently include:
  - `GET /.well-known/cap.json`
  - `POST /api/v1/cap`
- The capability card currently declares:
  - `conformance_level = 0.5`
  - `conformance_name = "Hybrid"`
- The core verbs exposed today include:
  - `meta.capabilities`
  - `meta.methods`
  - `narrate`
  - `observe.predict`
  - `intervene.do`
- The provider also exposes a set of `extensions.abel.*` verbs for entity resolution, read bundling, graph preparation, prediction, what-if, and graph inspection.

## Non-Goals

- Do not redesign `causal-abel` around the narrative provider.
- Do not expose the SIT endpoint in the public checked-in skill by default.
- Do not treat narrative or hybrid results as equivalent to graph-backed observational or interventional findings.
- Do not solve future production API-key injection in this change.
- Do not merge the existing graph probe and the narrative provider into one over-generalized script.

## User-Facing Product Shape

`causal-abel` remains a single skill.

The integration is internal:

- `graph CAP` remains the primary provider for graph-backed observational and interventional reads.
- `narrative CAP` becomes an optional helper provider for:
  - topic mapping
  - anchor discovery
  - candidate mechanism generation
  - hybrid read bundling
  - query-local execution preparation

Users should not need to learn a second skill name for this workflow.

## Routing Rule

Top-level routing stays simple:

- `direct_graph`
- `proxy_routed`

The narrative provider is not a third top-level user intent. It is an internal helper that may be used inside `proxy_routed` when the question still needs mapping or anchor discovery.

Recommended policy:

- `direct_graph`
  - default to graph CAP
  - only use narrative CAP when the graph-side anchor is unclear and the narrative provider can clarify it faster
- `proxy_routed`
  - narrative CAP may be used first to map the topic, discover anchors, or generate candidate mechanisms
  - if graph CAP can validate those anchors, the answer should lead with graph-backed findings
  - if graph CAP cannot carry the question, the answer may remain hybrid, but must say so

## Honesty Boundary

This is the main constraint the skill must preserve.

Allowed:

- use narrative CAP to discover anchors for a proxy-routed question
- use narrative CAP to produce an initial hybrid read
- use graph CAP to validate or reject those anchors
- present a mixed answer as long as the layers are kept separate

Not allowed:

- present `narrate` output as graph-backed causal evidence
- present hybrid outputs as graph-validated `observe.predict` or `intervene.do` findings
- blur provider-specific hybrid reasoning into graph-backed verdict language

Visible answer language should separate:

- `graph-backed`
- `hybrid-backed`
- `inference`

## Skill Prompt Changes

The skill should add only a small amount of explicit routing text.

Desired prompt behavior:

1. For `proxy_routed` questions, the skill may call narrative CAP first for mapping, anchor discovery, or candidate mechanism generation.
2. If graph CAP can validate the discovered anchors, the answer should lead with graph-backed findings.
3. If graph CAP cannot carry the question, the answer should remain hybrid and say so.
4. Narrative or hybrid outputs must never be written as graph-validated observational or interventional effects.

The prompt should avoid introducing a large provider taxonomy or a state-machine vocabulary. The rule should stay short and local to the existing Step 3 / proxy-routed language.

## Script Shape

Add a new helper script instead of expanding the current graph-biased `cap_probe.py`.

New script:

- `skills/causal-abel/scripts/narrative_cap_probe.py`

Purpose:

- interact with the narrative CAP server
- expose only the minimum verbs needed for proxy-routed mapping and hybrid reads
- keep provider-specific refs and handles intact
- avoid graph-specific ticker normalization assumptions

Initial command surface:

- `card`
- `methods`
- `narrate`
- `resolve-entity`
- `explain-read-bundle`
- `search-prepare`
- `predict`
- `what-if`

Common flags:

- `--base-url`
- `--api-key`
- `--env-file`
- `--graph-ref`
- `--response-detail`
- `--compact`

## Config and Release Boundary

The narrative provider should be wired through maintainer-local config only.

Recommended config fields:

- `narrative_cap_enabled`
- `narrative_cap_base_url`
- optional `narrative_cap_api_key_env`

Expected behavior:

- local SIT render can enable the narrative provider
- public checked-in skill stays safe by default
- future production endpoint injection can replace the local SIT value without reworking the routing model

## Validation Standard

The implementation is correct if all of the following hold:

1. The skill text explicitly allows narrative CAP inside `proxy_routed` without turning it into a separate top-level route.
2. The skill text explicitly preserves the honesty boundary between graph-backed and hybrid-backed findings.
3. A dedicated helper script can successfully call the narrative CAP provider on:
   - capability card
   - methods
   - one hybrid read verb
   - one stateful preparation verb
4. The public skill does not accidentally hardcode the SIT narrative endpoint into shipped user-facing content.

