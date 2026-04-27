---
name: abel
version: 1.2.0
description: >
  Use when the user asks for Abel or starts an Abel workflow and you need to
  check auth state, initialize Abel if needed, and route to the right Abel
  skill before proceeding.
metadata:
  openclaw:
    requires:
      bins:
        - python
    homepage: https://github.com/Abel-ai-causality/Abel-skills
---

Use `Abel` as the main entrypoint.

Before routing, verify auth state by running:

`python ../abel-common/python/abel_common/cap/graph_probe.py auth-status`

Do not guess from shell environment alone.

1. If auth is missing or invalid, use `abel-auth`. Tell it to read
   `references/setup-guide.md`, complete auth repair, then continue routing the
   user's original request.
2. If the user wants quant strategy search, backtesting, candidate discovery, a research workspace,
   session continuation, branch preparation, branch debugging, or branch runs,
   use `abel-strategy-discovery`.
3. For other graph-native or decision-oriented Abel reads, use `abel-ask`.
