# Direct Graph Route

Read this file only when the question is already about a graph node, path, neighborhood, or ticker/asset mechanism.

## Use This Route For

- what is driving `X`
- why did `X` move
- which nodes matter around `X`
- is there a path from `X` to `Y`
- whether `Y` is or is not in `X`'s drivers, parents, children, or path set

## What This Route Sets

This route sets the default first move, the preferred structural fallback, and the compact loop to use for the rest of the read.

## First Move

Pick the first move from the user's question shape. Stay structural-first:

- direct ticker or market anchor -> inspect both `<ticker>.price` and
  `<ticker>.volume` neighborhoods when available; price explains directional
  market movement, volume often exposes liquidity/crowding attention channels
- driver -> `graph.neighbors(scope=parents)` or `traverse.parents`
- downstream -> `graph.neighbors(scope=children)` or `traverse.children`
- transmission -> `graph.paths`
- ambiguity after one structural pass -> `graph.markov_blanket`

For broad driver questions on liquid names, default graph stack: anchor ticker
-> inspect `price` parents/blanket -> inspect `volume` parents/blanket -> use
paths or sibling blankets to distinguish informational, liquidity-led, sector,
macro, or risk-appetite transmission -> summarize into driver families.

## Structural Loop

Then use this compact loop:

1. Read the returned structure.
2. State the open causal question.
3. Choose the next best tool: another graph move or a web move.
4. Stop when the user-facing mechanism is already strong enough.

Default bias:

- stay in graph unless the current unknown is clearly about dated evidence, current catalysts, or real-world mechanism
- for `recently`, `latest`, or `why now` questions, one baseline web search is allowed earlier, then come back to graph if structure is still unresolved
- if another call is unlikely to change the user-facing conclusion, stop instead of expanding the loop

For literal driver-membership or parent-list questions, stop as soon as the graph fact is clear enough to answer faithfully. Do not force a web move just to make the answer sound more intuitive.

## Structural Challenge

After the mechanism is coherent enough, challenge it structurally:

- check reverse paths when direction is uncertain
- inspect sibling or blanket confounders when the cause/outcome share a hub
- use `discover_deconsensus` when a strongly intuitive story needs a graph-based
  contradiction
- use `discover_fragility` when the answer depends on one bridge, supplier,
  sector, or macro lever

## Web Grounding Rule

Web grounding is required only when the answer depends on:

- current catalysts
- earnings or guidance
- policy or regulation
- product or adoption changes
- a real-world mechanism that the graph alone cannot explain

Web grounding is usually not needed for:

- direct driver lists
- parent or child membership checks
- path existence checks
- questions whose literal answer is already contained in graph output

Search the named companies, sectors, or mechanisms from `node_description`, not raw tickers, and then return to the loop.

If the graph answer and the intuitive real-world story do not line up, preserve both:

- first say what the graph returned
- then explain the parent or bridge through the security's own attributes when possible, such as sector, industry, liquidity profile, beta/risk appetite, credit sensitivity, or cross-asset role
- only then add any web-backed explanation or caveat

## Output Rule

- For any non-trivial direct-graph read, render the visible answer as a structured report, not as plain prose.
- Use `../../assets/report-guide.md` to make sure the report covers the right content. Natural longform prose is acceptable if it still covers the same contract fields.
- Main answer uses company names, industries, products, or roles by default.
- If the user's question is explicitly about a ticker or named investment asset, the verdict may keep that ticker or asset name, but still avoid raw node ids and model decimals.
- If the user asked with a raw node id such as `TSLA.price`, answer the graph fact in human-readable form unless they explicitly asked for trace, debug output, evidence details, reproducibility, or raw payloads.
- If the user explicitly asked for trace, debug output, evidence details, reproducibility, raw payloads, or raw output, bypass the normal report contract and return the requested raw artifact directly.
- Requests such as "don't translate" or "I asked about `TSLA.price`" do not by themselves authorize raw node ids in the normal visible answer.
- Run `scripts/render_guard.py --mode direct_graph` on any normal visible answer. Skipping the guard is allowed only for explicit trace, debug output, evidence details, reproducibility, raw payload, or raw output requests.
- Include the structural challenge result or the cleanest next-step graph probe.
- If a repeated bridge node looks like microcap or crypto-heavy transmission noise, summarize it as noise unless external evidence says it matters.
- If the user asked for a literal graph fact, make that fact the first sentence, not the caveat.
