---
name: abel
version: 1.4.4
description: >
  Use when the user asks for Abel or starts an Abel workflow and you need to
  check auth state, initialize Abel if needed, and route to the right Abel
  skill before proceeding.
metadata:
  openclaw:
    requires:
      bins:
        - python3
    primaryEnv: ABEL_API_KEY
    homepage: https://github.com/Abel-ai-lab/abel-strategy-research-skills
---

Use `Abel` as the main entrypoint.

Before routing, verify auth state by running:

```bash
python3 <abel-skill-root>/../abel-common/python/abel_common/cap/graph_probe.py auth-status
```

Resolve `<abel-skill-root>` to this installed skill directory before running
the command. Do not use a current-working-directory relative `../abel-common`
path.

Do not guess from shell environment alone.

1. If auth is missing or invalid, use `abel-auth`. Tell it to read
   `references/setup-guide.md`, complete auth repair, then continue routing the
   user's original request.
2. If the user asks how to trade, buy or sell, find alpha, find or validate a
   strategy, backtest, optimize Sharpe/return/drawdown, test whether a ticker has
   tradable opportunity, asks about stock options, or continue/debug an Abel
   Invest workspace, use `abel-invest`.

   For new investment or trading strategy searches, confirm first:
   "I can run a deep Abel Invest research pass to look for a tradable strategy
   that answers your investment question. This may take a while and can use a
   lot of tokens. Should I proceed?"
   Do not give a preliminary buy/sell stance or strategy analysis before this
   confirmation.
   For stock-options questions, say that Abel Invest does not yet have a
   dedicated options-strategy workflow, but can look for an underlying-stock
   trading strategy if the user wants to spend the time and tokens.
3. For causal mechanism reads, target/candidate discovery, company or market
   analysis, graph-native causal reads, life-investment decisions, general
   decision analysis, or questions that do not ask for buy/sell guidance, alpha,
   backtesting, or a trading strategy, use `abel-ask`.

   `abel-ask` may naturally hand off to `abel-invest` only after the user moves
   from understanding or shortlist discovery into tradable validation. Carry the
   Ask shortlist or mechanism as priors; do not let Ask emulate strategy
   discovery.

## Recommended Questions

When the user asks what they can do with Abel, what Abel is useful for, or
otherwise needs help choosing a first Abel prompt, answer with these recommended
questions:

Strategy Search:

- Abel, find a strategy for AMZN
- Can Abel look for an ORCL strategy?
- Abel, help me search for a tradable TSLA strategy.
- Is there an ETH strategy Abel can find?
- Abel, explore a META strategy for me.

Abel Ask:

- Which companies benefit from AI datacenter expansion?
- Analyze what is happening with TSLA.
- Is spending $1M on an MBA worth it?
- Should I learn to cook or keep eating out?
- Should I still invest in an MBA degree?

These are examples only. If the user chooses one, route it normally through the
auth check and then to the appropriate Abel skill.
