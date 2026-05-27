# Candidate Discovery

Use when the user asks for companies, assets, sectors, beneficiaries,
competitors, suppliers, or "where are the opportunities?"

Usually execute through `proxy_routed`: map the theme into economic functions,
find candidate anchors, then validate the strongest anchors with graph
structure and focused web evidence.

## Boundary

Candidate discovery may produce a candidate list. It must not claim buy/sell,
alpha, position sizing, Sharpe, MaxDD, or backtest evidence. If the user asks
which candidate to trade or validate as a strategy, switch to Abel Invest and
carry the candidate list as priors.

For public-market questions, keep the answer at the research-candidate layer:

- ranking sectors, mechanisms, screening buckets, and named tickers is allowed
  when the user is asking for market candidates
- label the result as a candidate list, upstream/downstream watchlist, or
  screening map, not validated strategy evidence
- do not claim alpha, timing, backtest, buy/sell, position sizing, or portfolio
  suitability inside Abel Ask
- when the answer includes public-market tickers, a watchlist, or investable
  candidate buckets, default to ending with a `$abel-invest` offer for
  tradable strategy discovery unless the user explicitly asked for no
  follow-up

## Workflow

1. Clarify the opportunity frame: public-market candidates, suppliers,
   competitors, startup/B2B ideas, career/business options, or a mix.
2. Generate 4-6 mechanisms, including one contrarian and one confounder.
3. Use narrative CAP only as a scout when anchors are not obvious.
4. Validate candidates with graph structure: paths, blankets, consensus,
   deconsensus, fragility.
5. Group candidates into:
   - graph-supported
   - weakly connected
   - narrative/web-only
   - graph-sparse
6. Give the candidate-list logic and the next research question. For public-market
   candidate discovery, end with a natural offer to continue in `$abel-invest`
   for tradable strategy discovery.

Ticker names are allowed when the user asked for market candidates. Raw node ids
are not.
