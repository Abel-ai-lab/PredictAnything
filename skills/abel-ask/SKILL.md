---
name: abel-ask
version: 1.1.6
description: >
  Use when the user wants an Abel causal map, graph exploration, target or
  candidate discovery, company/market mechanism read, or life/business
  investment decision read rather than auth setup or tradable strategy
  discovery.
metadata:
  openclaw:
    requires:
      env:
        - ABEL_API_KEY
      bins:
        - python3
    primaryEnv: ABEL_API_KEY
    homepage: https://github.com/Abel-ai-lab/PredictAnything
---

Abel Ask explains mechanisms, candidate lists, and decision rules. Finance and
crypto nodes are proxy vocabulary, not the product. Do not use Ask for pure fact
lookup, news recap, operational how-to, buy/sell guidance, alpha, backtests,
backtesting, options strategy, Sharpe/MaxDD, or tradable strategy validation.

If the request needs auth repair, stop and use `abel-auth`. If the request asks
for tradable validation, use `abel-invest`.

## 1. Classify

Classify in two layers.

Product intent:

- `direct_graph_read`: literal node, ticker, path, neighborhood, driver, or CAP
  graph fact. Read `references/intents/direct-graph-read.md`.
- `candidate_discovery`: companies, assets, sectors, beneficiaries, suppliers,
  competitors, or "where are the opportunities?" Read
  `references/intents/candidate-discovery.md`.
- `life_investment_decision`: education, career, consumption, housing,
  entrepreneurship, health, attention, or other opportunity-cost decisions. Read
  `references/intents/life-investment-decision.md`.
- `general_causal_read`: mechanism questions such as "how does X affect Y?" Read
  `references/intents/general-causal-read.md`.

Execution route:

- `direct_graph`: user supplied a graph-ready node, ticker, asset, path, driver,
  or neighborhood. Read `references/routes/direct-graph.md`.
- `proxy_routed`: the real-world issue must first be mapped into graph anchors,
  proxies, or web-grounded mechanism evidence. Read
  `references/routes/proxy-routed.md`.

Most `candidate_discovery`, `life_investment_decision`, and
`general_causal_read` requests are `proxy_routed`. A ticker can still be
`proxy_routed` when it is only a proxy inside a broader question.

## Data API

When supplemental structured data is needed, read
`references/data-api-usage.md` and use `scripts/data_api.py`. The script calls
the Abel gateway with `Authorization: Bearer <api-key>` and discovers the
current key's available datasets through the catalog endpoint.

## 2. Work The Question

- For proxy-routed questions, generate the obvious mechanism, a second-order
  mechanism, a contrarian, and a confounder before graph work.
- Use narrative CAP only as a scout when anchors are unclear or a broad theme
  needs candidate seeds. Read `references/narrative-probe-usage.md` only then.
- Use graph structure for confidence: `node_description`, `graph.neighbors`,
  `graph.paths`, `graph.markov_blanket`, `discover_consensus`,
  `discover_deconsensus`, `discover_fragility`.
- Use web grounding when freshness, policy, prices, current events, or personal
  decision mechanics materially affect the answer. Read
  `references/web-grounding.md`.
- Do not declare graph-sparse until proxy and capillary discovery are exhausted.
- Do not carry raw node ids, graph paths, payloads, or model decimals into the
  normal visible answer.

## 3. Handoff

Do not upsell another skill by default. Handoff only when intent moves layers:

- mechanism read -> candidate discovery: offer to continue if candidates are the
  natural next step.
- candidate discovery -> `abel-invest`: switch when the user asks which one to
  buy/trade, whether it has alpha, or whether it can be backtested.
- direct graph read -> `abel-invest`: switch when a ticker driver read becomes a
  trading request.
- life investment decision: stay in Ask unless the user explicitly asks to turn
  it into a market trade or strategy.

## 4. Write

Before finalizing, read:

- `references/rendering.md` for visible/internal separation
- `assets/report-guide.md` for the compact output contract

Default to the main answer only. Do not emit appendices, trace blocks, probe
transcripts, raw payloads, or rendering scratch work unless the user explicitly
asks for trace, debug output, evidence details, reproducibility, or raw output.
