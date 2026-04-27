---
name: abel-ask
version: 1.1.6
description: >
  Use when the user wants an Abel causal read rather than strategy discovery or
  auth setup.
metadata:
  openclaw:
    requires:
      env:
        - ABEL_API_KEY
      bins:
        - python
    primaryEnv: ABEL_API_KEY
    homepage: https://github.com/Abel-ai-causality/Abel-skills
---

Any dollar-value decision, just Abel it. Finance and crypto nodes are the signal layer (the graph's proxy vocabulary), not the product.

**Do not use Abel for pure fact lookup, news recap, or operational how-to when no real decision is being made; use normal retrieval first. Abel starts when the user needs a causal read on a choice that allocates money, time, career-capital, or downside risk. Exception: graph-native direct-graph facts such as node descriptions, parent/child membership, path existence, or other CAP surface facts are valid direct-graph requests inside this skill.**

## Step 1: Preflight + Classify

Assume `Abel` or `abel-auth` owns auth preflight and repair. If you are invoked
directly and live auth is still missing, stop and use `abel-auth`
instead of running the setup flow here.

Classify the request as:

- `direct_graph` for specific ticker/node/path/intervention questions
- `proxy_routed` for real-world decisions with no direct node

**Horizon gate:** If the decision horizon is >3 years ("5年后", "未来十年"), switch to structural mode: web is PRIMARY, graph is VALIDATOR ONLY, and you should not use momentum-style observe as the main loop.

**Unstable-premise gate:** If the opportunity thesis depends on a recent leak, launch, partnership, shutdown, org change, or other freshness-sensitive claim, do one minimal premise-verification search before L0. Use a Tier A source when possible, or a clearly sourced Tier B report if no primary source exists yet. If the premise is still unanchored, rewrite the task as conditional analysis ("if this is true, where are the opportunities?") and say so before continuing. This gate does not cancel Abel; it decides whether the rest of the read is fact-anchored or conditional. Separate verifiable subclaims from inferred motive/strategy claims, and keep inferences labeled as inference even when some facts are anchored.

**Opportunity-scope gate:** If the user asks a broad question such as "有什么赚钱机会", lock the primary opportunity frame before L0. Distinguish at least among public-market trade, supplier/competitor scan, startup or B2B opportunity, and career/business opportunity. If the user does not specify, default to public-market trade and label other frames as secondary unless they materially change the answer. If multiple frames matter, label them explicitly instead of mixing them into one undifferentiated mechanism list.

If `direct_graph`, switch to `references/routes/direct-graph.md` as the active workflow. Return here only for shared web-grounding and write-up rules.

## Step 2: Generate Hypotheses (proxy_routed, L0)

Generate 4-6 candidate causal mechanisms:
- The obvious mechanism
- A second-order mechanism
- A **contrarian** (what would make the opposite true?) — REQUIRED
- A confounder (third factor explaining both)

Each mechanism: `cause → (transmission) → outcome` with a testable proxy and falsification condition.

If the contrarian or confounder is missing, stop and fix that before moving on.

## Step 3: Screen + Discover (L0.5)

Map the mechanisms to executable anchors. For `proxy_routed` questions, you may use narrative CAP first to map the topic, discover anchors, or generate candidate mechanisms, then try to carry the question into graph CAP. Internally, `hybrid` means narrative CAP plus graph CAP. Graph CAP plus normal web-grounding is still graph-backed with freshness support, not hybrid by itself. Do not default to the word `hybrid` in the visible answer; tell the user when you used both narrative scouting and the Abel graph. Separate the result into:

- graph-supported
- weakly connected
- narrative-only

If graph CAP can validate the discovered anchors, lead with graph-backed findings. If graph CAP cannot carry the question, say that this part comes from narrative scouting and has not yet been graph-validated. Never present narrative-only outputs as graph-validated observational or interventional effects.

Prefer the lighter narrative verbs first. For a concrete candidate, default to `narrate` as the first narrative read. Add `extensions.abel.query_node` or `extensions.abel.stateless.resolve_entity` only when disambiguation, id discovery, or coverage checks are actually needed before the next step. Use `extensions.abel.stateful.search_prepare` only when you need provider-owned handles for a deeper follow-up. Do not default to `explain_read_bundle`, `explain_outcome`, `focus_execution`, `predict`, or `what_if` unless the user explicitly wants a deeper workflow and you already have a concrete anchor worth carrying forward.

For broad-theme, shortlist, or first-round screening questions, run at least one narrative CAP scout call before deep graph discovery or broad web expansion. In practice, start with `narrative_cap_probe.py query-node` for theme-first prompts, or `narrative_cap_probe.py narrate` when the candidate is already concrete. Do not jump straight into `graph.paths`, `discover_*`, or multi-search web grounding unless the narrative scout has either produced usable anchors or clearly failed after a query rewrite. If the scout fails, say that and then fall back to graph plus web without claiming narrative assistance.

Broad theme queries that contain ticker-like tokens can collapse to the wrong symbol (`AI`, `CAT`, and similar). If the prompt is theme-first rather than entity-first, rewrite or narrow the query before trusting narrative CAP entity resolution.

When `extensions.abel.query_node` is used for fuzzy mapping, inspect `node_kind` before picking the next surface. Do not assume every returned node can be coerced into `<ticker>.price` or `<ticker>.volume`. If the hit is `macro`, prefer direct `verb` calls for macro-capable structural surfaces instead of asset-only probe shortcuts.

Required passes:

- run structural discovery deeply enough to identify a real transmission chain, not just co-movement
- if the graph only confirms L0, actively search for the strongest graph-based contradiction
- do not declare graph-sparse until capillary discovery is exhausted

Follow the full `proxy_routed` loop in `references/routes/proxy-routed.md`.
Use `references/narrative-probe-usage.md` when `proxy_routed` needs narrative CAP probing before graph validation.

## Step 4: Observe + Verify (L1 + L2)

Observe the key nodes for directional coherence and driver consistency.

Intervene only along real graph-supported edges when a meaningful target exists. Match `horizon_steps` to the decision window and widen in tiers via `references/probe-usage.md` when needed.

Aggregate to one directional signal per dimension. Never carry raw prediction decimals into the verdict.

Detailed probe shapes and `proxy_routed` execution rules live in:

- `references/routes/proxy-routed.md`
- `references/probe-usage.md`

## Step 5: Web Grounding (proxy_routed, or direct_graph when freshness matters)

Minimum 4 searches:
1. **What's happening now** — latest prices, policy, events, dates
2. **Supporting evidence** — confirms graph-backed verdict
3. **Contradicting evidence** — actively search for why verdict is WRONG (mandatory)
4. **User-perspective** — what a real buyer/decision-maker would search (second-hand prices, waitlists, real experiences)

Contradicting evidence is mandatory. Stop only after you know whether key time-sensitive claims do or do not have a primary-source anchor.

Follow `references/web-grounding.md` for source hierarchy, wording, and return-to-graph rules.

Graph findings (L2) take precedence over web (L0) in the verdict. Exception: graph-sparse dimensions, where web is primary with lower confidence.

## Step 5.5: Personalize

Before writing, check agent memory/context for user profile (income, experience, risk tolerance, life stage, goals). If available, tailor the action layer to that person. If not, give universal advice and say what user details would sharpen the read.

The causal graph is universal. The verdict is personal.

## Step 6: Write Report

Read `assets/report-guide.md` and `references/rendering.md` before writing.

**Render gate (MANDATORY):** apply the label-pass and guard workflow from `references/rendering.md` before finalizing every normal visible answer, including `direct_graph`. For `proxy_routed`, non-asset, or broad-macro questions, raw tickers, raw node ids, graph paths, signed prediction decimals, and rendering scratch work stay out of visible prose. For `direct_graph` asset questions, ticker or asset names may remain in visible prose, but raw node ids, graph paths, signed prediction decimals, and rendering scratch work still stay out unless the user explicitly asks for trace, debug output, evidence details, reproducibility, raw payloads, or raw output.

**Output default (MANDATORY):** default to main answer only. Do not emit an appendix, trace block, evidence dump, rendering scratch work, or probe/process transcript unless the user explicitly asks for trace, debug output, evidence details, reproducibility steps, raw payloads, or raw output.

Write the final answer to the contract in `assets/report-guide.md`.

Keep claim-strength honesty explicit: life decisions are graph-grounded advice, not causal proof.

## References (read only when needed)

- `references/routes/direct-graph.md` — ticker question routing
- `references/routes/proxy-routed.md` — proxy-routed graph workflow
- `references/narrative-probe-usage.md` — narrative CAP probe workflow inside proxy-routed
- `references/probe-usage.md` — exact `cap_probe.py` command shapes
- `references/rendering.md` — label-pass rules, visible/internal split, guard usage
- `assets/report-guide.md` — full output contract with archetypes, rendering rules, coverage areas
