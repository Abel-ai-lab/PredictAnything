# Narrative Probe Usage

Use this file only after `SKILL.md` has already fixed:

- the request is `proxy_routed`
- a graph-first answer is not already obvious
- narrative CAP is being used only as a helper, not as the final honesty layer by default

This file is a command manual for `scripts/narrative_cap_probe.py`, not the main workflow.

## Authorization First

- Start every live narrative session with `python scripts/narrative_cap_probe.py auth-status`.
- Do not infer missing auth from a blank shell env alone.
- If `auth_ready` is true, continue to the chosen route.
- If `auth_source` is `missing`, stop and hand off to `abel-auth`, which owns the OAuth guide and repair flow. Do not run probes or substitute web search just because auth is missing.
- By default, use `<skill-root>/.env.skill` as the local auth file. If an agent accidentally stored `ABEL_API_KEY` in the same-directory `.env`, the bundled probe also falls back to that file.

## Role In The Workflow

Narrative CAP is the scout layer inside `proxy_routed`.

In this skill, `hybrid` is internal shorthand for narrative CAP plus graph CAP. In user-facing prose, prefer saying that you used both narrative scouting and the Abel graph, not just that the answer is `hybrid`. Do not call an answer `hybrid` just because it mixed graph CAP with normal web grounding or freshness checks.

Use it to:

- get a fast first narrative read on a concrete candidate
- disambiguate a concrete entity or ticker only when the next step actually needs it
- open a provider-owned session when a deeper narrative workflow is actually needed

Do not use it to:

- replace graph CAP for graph-backed verdicts
- present narrative output as observational or interventional proof
- keep drilling into provider-owned handles when graph CAP already gives the answer

Default progression:

1. if the entity is already clear and the user mainly wants a first read, start with `narrate`
2. add `query-node` or `resolve-entity` only when the entity is ambiguous, you need an id, or the next step needs stronger disambiguation
3. for broad theme exploration, rewrite the query first, then use `query-node` before `narrate`
4. `search-prepare` only if you need provider-owned session or graph handles for a deeper follow-up
5. shift back to graph CAP as soon as the shortlist or anchor set is good enough for graph validation

For broad-theme, shortlist, or first-round screening prompts, steps 1-3 are a hard gate, not a suggestion. Do not start deep graph discovery or a wide web evidence sweep until at least one narrative CAP scout call has either returned anchors or clearly failed.

## Broad Theme Rule

Theme-first queries can collapse into the wrong ticker if the text contains symbol-like tokens such as `AI` or `CAT`.

Before you trust narrative resolution:

- rewrite broad theme queries into a less ticker-shaped phrase
- avoid putting the theme token alone at the front if it is also a traded symbol
- prefer a clarified phrase such as `beneficiaries of AI datacenter buildout` over `AI datacenter demand beneficiaries`

If the provider still overfits to an exact symbol, treat the result as a retrieval failure and rewrite the query instead of carrying the wrong anchor forward.

If one rewrite still fails, stop calling the answer narrative-assisted. From that point on, you are doing graph plus web fallback, and the visible answer should say so implicitly by describing graph-backed versus still-exploratory parts instead of claiming a narrative scout happened.

## Authorization And Endpoint

Run these from the skill root:

```bash
BASE_URL="https://cap.abel.ai/narrative"

python scripts/narrative_cap_probe.py auth-status
python scripts/narrative_cap_probe.py card
python scripts/narrative_cap_probe.py methods --verbs narrate
```

The script accepts a narrative base URL such as `https://cap.abel.ai/narrative` and resolves it to `POST /narrative/cap` plus `GET /.well-known/cap.json`.

By default, the local rendered skill may already inject `DEFAULT_BASE_URL` from maintainer config. If not, pass `--base-url`.

Authorization uses the same shared Abel token as graph CAP. Pass `--api-key` explicitly or set `CAP_API_KEY` / `ABEL_API_KEY`. Narrative probing no longer uses a separate narrative-only API key env path.

## Endpoint Notes

- The current default narrative CAP surface answers on `https://cap.abel.ai/narrative/cap`.
- Production narrative CAP surface answers on `https://cap.abel.ai/narrative/cap`.
- The probe accepts base URLs such as `https://cap.abel.ai/narrative` and resolves them to `/cap`.

## Recommended First Pass

Concrete candidate already named:

```bash
python scripts/narrative_cap_probe.py narrate --query "NVDA and AI datacenter demand"
```

Need explicit disambiguation or an id before a deeper follow-up:

```bash
python scripts/narrative_cap_probe.py query-node --query "NVDA"
python scripts/narrative_cap_probe.py narrate --query "NVDA and AI datacenter demand"
```

Broad theme, but still early and exploratory:

```bash
python scripts/narrative_cap_probe.py query-node --query "beneficiaries of AI datacenter buildout"
python scripts/narrative_cap_probe.py narrate --query "NVDA and AI datacenter demand"
```

Need deeper provider-owned handles:

```bash
python scripts/narrative_cap_probe.py search-prepare --query "NVDA and AI datacenter demand" --intent read
```

Stop after this phase if you already have enough concrete anchors to move into graph CAP.

## Command Guide

### `narrate`

Best first read for a concrete candidate when you want one fast narrative explanation before graph validation.

```bash
python scripts/narrative_cap_probe.py narrate --query "NVDA and AI datacenter demand"
```

Use when:

- you already have a likely anchor
- you want a quick narrative read before graph validation

Do not use when:

- the query is still too broad and symbol-trappy
- you need structured candidate lists instead of one narrative

### `resolve-entity`

Use for concrete entity disambiguation and coverage checks when `query-node` is not enough or when provider-side filtering matters.

```bash
python scripts/narrative_cap_probe.py resolve-entity --query "NVDA"
python scripts/narrative_cap_probe.py resolve-entity --query "Supermicro" --search-mode hybrid --top-k 5
```

Use `--advanced-json` only when you need stronger provider-side filtering:

```bash
python scripts/narrative_cap_probe.py resolve-entity \
  --query "NVDA" \
  --advanced-json '{"symbols":["NVDA"],"claim_types":["PREDICTION"]}'
```

Do not put this in the default loop just because the entity is already named. Start with it only when ambiguity or coverage checks are the actual blocker.

If `resolution_status` is ambiguous or the provider locks onto the wrong symbol, rewrite the query before continuing.

### `query-node`

Use when you want raw candidate retrieval and seed visibility instead of a narrative summary.

```bash
python scripts/narrative_cap_probe.py query-node --query "NVDA"
python scripts/narrative_cap_probe.py query-node \
  --query "NVDA" \
  --advanced-json '{"symbols":["NVDA"],"claim_types":["PREDICTION"]}'
```

Prefer this over `resolve-entity` when:

- the query is concept-heavy
- you want to inspect raw seed candidates
- you need to confirm whether prediction claims exist before deeper workflow steps
- the prompt is broad, theme-first, or likely to overfit to a symbol-like token

### `explain-read-bundle`

Use when you want a read bundle, but still stay stateless.

```bash
python scripts/narrative_cap_probe.py explain-read-bundle \
  --query "NVDA" \
  --question-type directional \
  --strictness exploratory \
  --include-layer supporting_evidence \
  --include-layer top_tailwinds
```

Treat this as exploratory. If it only returns a skeleton or thin layers, do not force it into the final answer.

### `search-prepare`

Use only when you need a session or handle for deeper provider-owned workflow.

```bash
python scripts/narrative_cap_probe.py search-prepare \
  --query "NVDA and AI datacenter demand" \
  --intent read \
  --max-hops 2 \
  --max-nodes 120
```

This is the normal bridge into:

- `predict`
- `what-if`
- provider-owned graph handles exposed in `recommended_next_actions`

Do not default to this for every proxy-routed question.

## Advanced Follow-On Commands

These are valid tools, but not the default first pass.

### `explain-outcome`

One-shot deeper workflow that can create a session, execution handle, candidate outcome, and driver summary.

```bash
python scripts/narrative_cap_probe.py explain-outcome \
  --query "AI datacenter demand and NVDA" \
  --focus-strategy auto \
  --focus-top-n 12 \
  --top-driver-count 5 \
  --max-paths 3 \
  --max-hops 3 \
  --include-bayes-evidence
```

Use only when:

- the query is already concrete enough
- you explicitly want a deeper provider-native explanation
- you are prepared to inspect whether the chosen outcome drifted off-target

### `observe-predict`

Core CAP observational helper.

```bash
python scripts/narrative_cap_probe.py observe-predict \
  --target-node "bayes:NVDA:PREDICTION:057dc3989741c21fb4a209f9f2c6af02cabbcb3b"
```

### `intervene-do`

Core CAP interventional helper.

```bash
python scripts/narrative_cap_probe.py intervene-do \
  --treatment-node "bayes:NVDA:PREDICTION:4fd6098dd0558ec52ed360c09f13de224eddefb6" \
  --treatment-value 0.1 \
  --outcome-node "bayes:NVDA:PREDICTION:057dc3989741c21fb4a209f9f2c6af02cabbcb3b"
```

Use these only when:

- you already trust the provider-native node refs
- you understand the result is still provider-specific narrative evidence, not graph CAP validation

### `predict` and `what-if`

These depend on a prior `search-prepare` session:

```bash
python scripts/narrative_cap_probe.py predict \
  --session-handle "alb:session:..." \
  --node-ref "n78"

python scripts/narrative_cap_probe.py what-if \
  --session-handle "alb:session:..." \
  --treatment-node-ref "n104" \
  --treatment-value 0.01 \
  --outcome-node-ref "n106"
```

Do not recommend these in the default user-facing flow unless the user explicitly wants a deeper narrative workflow.

## Stop Rules

- Stop at `resolve-entity` or `narrate` if you already have a concrete shortlist to validate in graph CAP.
- Stop at `search-prepare` if the only purpose was to confirm that provider-owned handles exist.
- Stop and rewrite the query if the provider keeps anchoring to a wrong symbol-like token.
- Stop and say the answer is still at the narrative-scout / shortlist stage if graph CAP cannot meaningfully carry the discovered anchors.

## See Also

- `../SKILL.md` Step 3 for the dispatcher and honesty rules
- `routes/proxy-routed.md` for the main proxy-routed loop
- `probe-usage.md` for graph CAP probing
