# Probe Usage

Use this file only after `SKILL.md` and the chosen route file have already fixed:

- the mode
- the anchor set
- whether web grounding is needed

This file is a command manual, not the main workflow.

## Auth Ownership

`abel-auth` owns auth preflight and OAuth repair. This file assumes auth is
already ready by the time you use these command shapes. If live auth is still
missing, hand off to `abel-auth` instead of continuing here. If you are invoked
directly and need to confirm the current state first, run
`python scripts/cap_probe.py auth-status`. Do not infer missing auth from a
blank shell env alone. By default, use `<skill-root>/.env.skill` as the local
auth file; the bundled probe also falls back to same-directory `.env.skills`
and `.env` when present.

## Bundled Script

Prefer `scripts/cap_probe.py` over ad hoc payload construction. Default Abel
Ask work uses structural graph surfaces. The short graph helpers accept dotted
CLI aliases such as `graph.neighbors`, `graph.paths`, and
`graph.markov_blanket`; use the generic `verb` path for extension discovery
surfaces such as `query_node`, `node_description`, `discover_consensus`,
`discover_deconsensus`, and `discover_fragility`.

Envelope defaults:

- Graph-aware probes default to `context.graph_ref = {"graph_id":"abel-main","graph_version":"CausalNodeV3"}`.
- Use `--graph-version` for the common V2/V3 switch.
- Use `--context-json` only as an envelope-level escape hatch when you need more than the graph-version shortcut.
- `--params-json` is only for verb `params`; do not stuff `context` into it.

## Common Direct Calls

Run these from the skill root:

```bash
BASE_URL="https://cap.abel.ai/api"

python scripts/cap_probe.py --base-url "$BASE_URL" capabilities
python scripts/cap_probe.py auth-status
python scripts/cap_probe.py normalize-node NVDA
python scripts/cap_probe.py --base-url "$BASE_URL" methods extensions.abel.query_node extensions.abel.node_description
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.query_node --params-json '{"search":"AI datacenter beneficiaries","search_mode":"hybrid","top_k":5}'
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.node_description --params-json '{"node_id":"NVDA.price"}'
python scripts/cap_probe.py --base-url "$BASE_URL" graph.neighbors NVDA.price --scope children --max-neighbors 5
python scripts/cap_probe.py --base-url "$BASE_URL" graph.neighbors NVDA.volume --scope parents --max-neighbors 5
python scripts/cap_probe.py --base-url "$BASE_URL" graph.paths NVDA.price AMD.price --max-paths 3
python scripts/cap_probe.py --base-url "$BASE_URL" graph.markov_blanket NVDA.price --max-nodes 12
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.discover_consensus --params-json '{"seed_nodes":["NVDA.price","ANET.price"],"direction":"out","limit":10}'
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.discover_deconsensus --params-json '{"seed_nodes":["NVDA.price"],"direction":"out","contrast_level":"medium","limit":8}'
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.discover_fragility --params-json '{"node_ids":["NVDA.price","ANET.price"],"severity_level":"medium","only_fragility":true,"limit":10}'
```

## Usage Rules

- `normalize-node` is optional. Use it for bare tickers or known macro ids when you want a quick local check.
- If you already know the canonical node id, call the target verb directly.
- Manual mapping is still the first pass for obvious company and proxy anchors.
- Use `extensions.abel.query_node` for fuzzy or broad phrases; do not rely on local normalization for open-ended resolution.
- `extensions.abel.query_node` can now return typed results. Inspect `node_kind` before assuming the hit is an asset with `.price` or `.volume`.
- If the chosen node is `macro`, call macro-capable structural surfaces through `verb ... --params-json ...` instead of asset-only local shortcuts that normalize to `<ticker>.price` or `<ticker>.volume`.
- Prefer `--graph-version` when the only envelope choice is V2 versus V3.
- Use `--context-json` when you need a nonstandard envelope field in addition to, or instead of, the graph-version shortcut.
- Use `extensions.abel.node_description` on the final shortlist before writing the answer.
- For direct ticker reads, inspect both `price` and `volume` structural anchors
  when both are relevant and available.
- Search the company or industry labels from `node_description`, not raw node ids.
- Check `meta.methods` before assuming a local wrapper is current.
- Call newly added extension verbs through the generic `verb` path.

## Generic Fallbacks

```bash
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.query_node --params-json '{"search":"music streaming","search_mode":"hybrid","top_k":5}'
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.node_description --params-json '{"node_id":"SPOT.price"}'
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.node_description --params-json '{"node_id":"CPI"}'
python scripts/cap_probe.py --base-url "$BASE_URL" graph.neighbors SPOT.price --scope parents --max-neighbors 8
python scripts/cap_probe.py --base-url "$BASE_URL" graph.neighbors SPOT.volume --scope parents --max-neighbors 8
python scripts/cap_probe.py --base-url "$BASE_URL" graph.paths SPOT.price NFLX.price --max-paths 3
python scripts/cap_probe.py --base-url "$BASE_URL" graph.markov_blanket SPOT.price --max-nodes 12
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.discover_consensus --params-json '{"seed_nodes":["NVDA.price","ANET.price"],"direction":"out","limit":10}'
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.discover_deconsensus --params-json '{"seed_nodes":["NVDA.price"],"direction":"out","contrast_level":"medium","limit":8}'
python scripts/cap_probe.py --base-url "$BASE_URL" verb extensions.abel.discover_fragility --params-json '{"node_ids":["SIM.price","MOOOUSD.price"],"severity_level":"medium","only_fragility":true,"limit":10}'
```

## Validation

Probe the live surface first with:

- one `capabilities`
- one targeted `methods`
- one simple structural call

Bridge-node rule:

- repeated bridge + semantically rich neighborhood -> inspect further
- repeated bridge + microcap or crypto-heavy neighborhood -> summarize as transmission noise and move on

## Endpoint Notes

- The current default CAP surface answers on `https://cap.abel.ai/api/cap`.
- Production CAP surface answers on `https://cap.abel.ai/api/cap`.
- The probe accepts base URLs such as `https://cap.abel.ai/api` and resolves them to `/cap`.
- `https://api.abel.ai/router/` is used for OAuth and business API flows in `setup-guide.md`; it is not the default CAP probe base.

## See Also

- `../../abel-auth/SKILL.md` for auth ownership and the required `auth-status` command
- `routes/direct-graph.md` for direct graph flow
- `../SKILL.md` Step 2-4 for proxy-routed flow, screening, and validation
- `../SKILL.md` Step 5-6 for web grounding and report writing
- `web-grounding.md` for graph-grounded web search
