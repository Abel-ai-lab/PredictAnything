---
name: abel
version: 1.4.2
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
2. If the user asks how to invest, trade, buy or sell, find alpha, find a
   strategy, test a ticker for tradable opportunity, or continue/debug an Abel
   Invest workspace, use `abel-invest`.

   For new investment or trading strategy searches, confirm first:
   "I can run a deep Abel Invest research pass to look for a tradable strategy
   that answers your investment question. This may take a while and can use a
   lot of tokens. Should I proceed?"
   Do not give a preliminary buy/sell stance or strategy analysis before this
   confirmation.
3. For stock, company, or market analysis; graph-native causal reads; general
   decision analysis; life-decision questions; or questions that do not ask for
   buy/sell guidance, alpha, or a trading strategy, use `abel-ask`.

## Recommended Questions

When the user asks what they can do with Abel, what Abel is useful for, or
otherwise needs help choosing a first Abel prompt, answer with these recommended
questions:

- Abel, find a strategy for AMZN
- Abel, find a strategy for ORCL
- Abel, find a strategy for TSLA
- Abel, find a strategy for ETH
- Abel, find a strategy for META

These are examples only. If the user chooses one, route it normally through the
auth check and then to `abel-invest` as a new strategy-search request.
