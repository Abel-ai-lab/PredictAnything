# Abel Skills

Abel Skills is the collection repository for Abel agent skills. Users should install the collection and start from `Abel`, which routes to the right internal skill for causal reads, strategy discovery, or auth recovery.

## Main Skills

- `abel`: main entrypoint
- `abel-ask`: graph-native and proxy-routed causal reads
- `abel-auth`: connect or repair Abel auth
- `abel-invest`: workspace-first strategy discovery

## Abel-Invest Capability Snapshot

A June 1, 2026 directional benchmark compared the Abel workflow against an isolated LLM-only selection path over `1,000` tickers from `2020-01-01` to `2026-05-28`. The no-skill isolation audit passed, and the comparable both-OK set covered `960` tickers. This benchmark is useful capability evidence, but not the strict academic incremental-value claim because it was later superseded by an identical-prompt protocol.

| Measure | Abel skill | LLM-only | Readout |
| --- | ---: | ---: | --- |
| OK coverage | `997 / 1000` (`99.7%`) | `962 / 1000` (`96.2%`) | Abel covers `35` more tickers |
| Mean Sharpe | `0.8245` | `0.2308` | `3.57x` higher |
| Median Sharpe | `0.8139` | `0.2336` | `3.48x` higher |
| Mean total return | `1.5221` | `0.6084` | `2.50x` higher |
| Median total return | `1.0170` | `0.1393` | `7.30x` higher |
| Median max drawdown | `-0.1911` | `-0.3306` | smaller typical drawdown |
| Mean return/drawdown | `7.4754` | `1.9765` | `3.78x` higher |
| Median return/drawdown | `5.7227` | `0.5066` | `11.29x` higher |

Paired win rates on the both-OK set favored Abel on Sharpe (`98.3%`), total return (`84.7%`), max drawdown (`79.3%`, less negative is better), and return/drawdown (`92.0%`). Lower-tail behavior also improved: Abel's 10th percentile Sharpe stayed positive at `0.5174`, while the LLM-only arm's was `-0.2719`.

Backtests and benchmark comparisons are research artifacts, not investment advice.

## Installation

Installation differs by platform.

### Codex

Tell Codex:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-causality/Abel-skills/refs/heads/main/.codex/INSTALL.md
```

**Detailed docs:** [docs/README.codex.md](docs/README.codex.md)

Supports:
- Global install
- Project-level install via `.agents/skills/`

### Claude Code

Tell Claude Code:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-causality/Abel-skills/refs/heads/main/.claude/INSTALL.md
```

**Detailed docs:** [docs/README.claude.md](docs/README.claude.md)

Supports:
- Global install
- Project-level install via `.claude/skills/`

### OpenCode

Tell OpenCode:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-causality/Abel-skills/refs/heads/main/.opencode/INSTALL.md
```

**Detailed docs:** [docs/README.opencode.md](docs/README.opencode.md)

Supports:
- Global install
- Project-level install via project `opencode.json`

### ClawHub / OpenClaw

Install from the published ClawHub package after release publication.

Install-time auth note:
- If you already have an Abel API key, write it to the OpenClaw skill config path `skills.entries.abel.apiKey` before restart.
- If you do not, make `abel-auth` your first action after restart so the key is persisted before normal live use.
- After auth is ready, bootstrap the default strategy workspace before normal strategy use: `abel-invest workspace bootstrap --path ./abel-invest-workspace`

## Try These Questions

- Help me search for a TSLA strategy.
- Find a few Abel-discovered candidates around semiconductor demand.
- Continue my TSLA strategy workspace.
- Give me an Abel read on what drives mortgage-rate-sensitive homebuilder stocks.

## For Maintainers

- Release documentation: [docs/releases.md](docs/releases.md)
- Branching and repository policy: `AGENTS.md`
- Maintainer endpoint rendering workflow: `maintainers/abel-ask/README.md`

Release builds publish from collection source into `dist/`. Do not commit generated ClawHub artifacts into the repository.
