# Proxy-Routed Route

Read this file only after `SKILL.md` has already fixed:

- the request is `proxy_routed`
- auth is available
- the decision horizon is not in structural-only mode
- initial mechanisms already exist

This file is the active workflow for `proxy_routed` reads.

`proxy_routed` is an execution route, not a product intent. Candidate discovery,
life-investment decisions, and general causal reads often use this route because
the user did not start with a graph-ready node.

## Screen + Discover

### 3a. Structural screening

Map mechanisms to graph or market anchors in this order:

1. Write the mechanism in plain language.
2. Identify the economic function you need to represent.
3. Use narrative CAP when it helps find candidate anchors, especially for broad
   themes.
4. Use `query_node` when the anchor is fuzzy or theme-first.
5. Inspect the returned `node_kind` before choosing graph calls.

When the prompt is broad-theme, shortlist-first, or still anchor-sparse,
narrative CAP is a useful scout but its graph coverage may be limited. Run
`narrative_cap_probe.py query-node` after query rewrite, or
`narrative_cap_probe.py narrate` when the candidate is already concrete, when it
is likely to produce better anchors than guessing. If coverage is thin, say so
internally and continue with graph plus web; do not advertise narrative coverage
as complete.

If the narrative scout yields no usable anchors after one rewrite, record that as a failed scout leg and then continue with graph plus web. Do not describe the answer as narrative-assisted unless at least one real narrative CAP call happened.

If the query is theme-first and contains ticker-like tokens, rewrite it before relying on provider resolution. `AI`, `CAT`, and similar strings can overfit to exact symbols instead of the intended theme.

Anchor handling:

- `asset`: inspect structural surfaces around `price` and, when liquidity or
  attention matters, `volume`; use descriptions, neighbors, paths, and blankets
- `macro`: use the canonical macro node id directly for `node_description` and
  macro-capable structural surfaces; do not coerce it into an asset price node
- unknown or non-market concept: use narrative scout, web facts, and economic
  function mapping to choose a proxy anchor explicitly

For each structurally executable mapping:

- `graph.paths` between cause and outcome proxy
- Rank: dist <= 2 = strong, 3-4 = plausible, no path = narrative-only unless later graph support appears

Structural connection does not equal causal transmission. Many dist=2 paths are
shared macro exposure, not action-ready mechanism.

### 3b. Capillary discovery

1. If the obvious anchor is sparse, inspect neighbors, blanket, or paths around
   adjacent economic functions.
2. If no usable graph anchor appears, use `query_node` for the economic function.
3. If still nothing, use world knowledge and web evidence to identify proxy
   companies, industries, macro series, or activities.
4. All three fail -> declare sparse for this dimension

Do not declare graph-sparse before this sequence is exhausted.

### 3c. Graph-structural bias check

- Cause and outcome in the same blanket -> possible confounding
- Path runs opposite to hypothesis -> check reverse causation
- Proposed proxy is a mega-cap hub -> may be bridge noise

### 3d. Deep structural reasoning

This is where Abel's moat lives. Do not stop at a generic blanket.

Check `meta.methods` first. On the key outcome node:

- **Layer 1 blanket:** `graph.markov_blanket` to identify the immediate controlling neighborhood
- **Layer 2 blanket (REQUIRED):** run `graph.markov_blanket` on the 2 most interesting Layer 1 nodes
- **Layer 3:** if Layer 2 reveals divergence, follow the most surprising Layer 2 node one more level

Layer 1 often gives generic financial context. Layer 2 is where the question-specific mechanism usually appears. Layer 3 is for the non-obvious causal chain worth surfacing.

Also fire:

- `discover_consensus` / `discover_deconsensus` across mechanisms
- `discover_fragility` for single points of failure

### 3e. Graph-initiated discovery

Ask: "Graph, what do you see that the initial mechanisms missed?" Run
`discover_consensus` with `direction="in"` on the outcome. New upstream nodes
are graph-generated mechanisms.

### 3f. Surprise check + revision

Compare graph results against the initial mechanisms. If graph contradicts or
extends them, revise the mechanism set in one sentence. Max 2 rounds.

If the graph only confirms the obvious story, actively search for graph evidence
against the strongest conviction. If a contradiction appears, that contradiction
is the deep insight.

## Step 4: Graph Support Scoring

Rank each mechanism, candidate, or decision dimension by structural support:

- direct path strength and direction
- blanket proximity
- parent/child membership
- consensus/deconsensus support
- fragility or single-point dependency
- graph-sparse status
- freshness/web support when the graph alone cannot carry the mechanism

Bucket results into:

- `graph-supported`
- `weakly connected`
- `narrative/web-only`
- `graph-sparse`

## Stop Rules

- Stop when mechanisms are already decision-grade and another graph move is unlikely to change the visible conclusion
- Stop and mark a dimension graph-sparse only after capillary discovery fails
- Stop and red-team your own read when the graph only confirms the obvious story

## See Also

- `../../SKILL.md` for the shared dispatcher and hard gates
- `../probe-usage.md` for exact probe shapes and horizon handling
- `../web-grounding.md` for graph-grounded search
- `../../assets/report-guide.md` for output contract
- `../rendering.md` for label-pass and guard workflow
