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
- find candidate anchors for broad themes when graph anchors are not obvious

Do not use it to:

- replace graph CAP for graph-backed verdicts
- present narrative output as graph proof
- advertise full-market coverage; narrative graph coverage may be limited and
  should be treated as a scout, not a complete universe

Default progression:

1. if the entity is already clear and the user mainly wants a first read, start with `narrate`
2. add `query-node` or `resolve-entity` only when the entity is ambiguous, you need an id, or the next step needs stronger disambiguation
3. for broad theme exploration, rewrite the query first, then use `query-node` before `narrate`
4. use `search-prepare` only when steps 1-3 are too thin and you need a richer
   seed bundle or mapping status before graph validation
5. shift back to graph CAP as soon as the shortlist or anchor set is good enough for graph validation

For broad-theme, shortlist, or first-round screening prompts, steps 1-3 are the
preferred scout path when coverage is likely. If narrative coverage is thin,
rewrite once, then continue with graph plus web without claiming narrative
coverage.

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

Broad theme remains thin after query rewrite:

```bash
python scripts/narrative_cap_probe.py search-prepare \
  --query "AI datacenter demand beneficiaries" \
  --intent read \
  --max-hops 2 \
  --max-nodes 80
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

Do not put this in the default loop just because the entity is already named. Start with it only when ambiguity or coverage checks are the actual blocker.

If `resolution_status` is ambiguous or the provider locks onto the wrong symbol, rewrite the query before continuing.

### `query-node`

Use when you want raw candidate retrieval and seed visibility instead of a narrative summary.

```bash
python scripts/narrative_cap_probe.py query-node --query "NVDA"
```

Prefer this over `resolve-entity` when:

- the query is concept-heavy
- you want to inspect raw seed candidates
- the prompt is broad, theme-first, or likely to overfit to a symbol-like token

### `search-prepare`

Use only as a richer scout when `query-node` / `narrate` did not produce enough
usable anchors for graph CAP.

```bash
python scripts/narrative_cap_probe.py search-prepare \
  --query "AI datacenter demand beneficiaries" \
  --intent read \
  --max-hops 2 \
  --max-nodes 80
```

Extract only what helps the Ask workflow:

- candidate items and variables
- seed descriptions
- mapping status
- recommended graph-inspection next actions

Then return to graph CAP. Do not follow the session into scoring or simulation
workflows.

## Stop Rules

- Stop at `resolve-entity` or `narrate` if you already have a concrete shortlist to validate in graph CAP.
- Stop at `search-prepare` once you have anchor candidates, mapping status, or
  a graph-inspection next action.
- Stop and rewrite the query if the provider keeps anchoring to a wrong symbol-like token.
- Stop and say the answer is still at the narrative-scout / shortlist stage if graph CAP cannot meaningfully carry the discovered anchors.

## See Also

- `../SKILL.md` Step 3 for the dispatcher and honesty rules
- `routes/proxy-routed.md` for the main proxy-routed loop
- `probe-usage.md` for graph CAP probing
