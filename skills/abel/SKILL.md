---
name: abel
version: 1.4.0
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
    homepage: https://github.com/Abel-ai-causality/Abel-skills
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
2. If the user wants quant strategy search, backtesting, candidate discovery, a research workspace,
   session continuation, branch preparation, branch debugging, or branch runs,
   use `abel-invest`.
3. For other graph-native or decision-oriented Abel reads, use `abel-ask`.

## Good First Questions

- Help me search for a TSLA trading strategy.
- Should I still invest in a MBA degree?
