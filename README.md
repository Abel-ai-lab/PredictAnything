# Abel Strategy Research Skills

AI agent skills for strategy discovery with Abel: explore market ideas, analyze causal drivers, and develop investment strategies.

![Abel Strategy Research Skills — AI agent skills for strategy discovery with Abel: explore market ideas, analyze causal drivers, and develop investment strategies.](docs/assets/social-preview.png)

Abel Strategy Research Skills help Claude Code, OpenAI Codex, OpenCode, and ClawHub agents explore market ideas, analyze causal drivers, and develop investment strategies.

These skills support investment research and strategy discovery. They are not a trading bot, automated trade execution system, or backtesting engine.

## What You Can Do

- Explore strategy ideas from natural-language market questions
- Analyze causal drivers across companies, sectors, and market themes
- Develop investment strategy hypotheses
- Compare drivers, risks, and evidence behind a strategy
- Set up or repair Abel authentication for agent-based research workflows

## Example Workflows

Ask your AI agent to:

- "Discover AI infrastructure investment strategies with Abel."
- "Find a TSLA strategy thesis."
- "Analyze causal drivers for mortgage-rate-sensitive homebuilder stocks."
- "Develop semiconductor demand strategies using Abel."
- "Explore investment strategies related to power demand and data centers."
- "Check my Abel auth setup before running strategy research."

## Strategy Discovery, Not Trade Execution

Abel Strategy Research Skills focus on research workflows: exploring market themes, analyzing causal drivers, developing investment strategies, and comparing hypotheses, risks, candidates, and evidence.

They do not place trades, automate execution, or provide a backtesting engine.

Learn more: [Abel Strategy Research](docs/strategy-research.md)

## Main Skills

- `abel`: main entrypoint for Abel strategy research workflows
- `abel-invest`: core strategy discovery and investment research skill
- `abel-ask`: graph-native analysis of causal drivers and market decisions
- `abel-auth`: connect or repair Abel auth

## Supported Agent Platforms

- OpenAI Codex
- Claude Code
- OpenCode
- ClawHub / OpenClaw

## Installation

Installation differs by platform.

### Codex

Tell Codex:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-causality/abel-strategy-research-skills/refs/heads/main/.codex/INSTALL.md
```

**Detailed docs:** [docs/README.codex.md](docs/README.codex.md)

Supports:
- Global install
- Project-level install via `.agents/skills/`

### Claude Code

Tell Claude Code:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-causality/abel-strategy-research-skills/refs/heads/main/.claude/INSTALL.md
```

**Detailed docs:** [docs/README.claude.md](docs/README.claude.md)

Supports:
- Global install
- Project-level install via `.claude/skills/`

### OpenCode

Tell OpenCode:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-causality/abel-strategy-research-skills/refs/heads/main/.opencode/INSTALL.md
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

## Existing Installs And Migration

Existing installs under paths like `~/.claude/abel-skills`, `~/.codex/abel-skills`, `.claude/abel-skills`, or `.agents/abel-skills` can keep their local folder names. To migrate an existing checkout, update its git remote:

```bash
git remote set-url origin https://github.com/Abel-ai-causality/abel-strategy-research-skills.git
```

New install examples use `abel-strategy-research-skills`.

## For Maintainers

- Release documentation: [docs/releases.md](docs/releases.md)
- Branching and repository policy: `AGENTS.md`
- Maintainer endpoint rendering workflow: [maintainers/README.md](maintainers/README.md)
- Social preview source: [docs/assets/social-preview.svg](docs/assets/social-preview.svg)

Release builds publish from collection source into `dist/`. Do not commit generated ClawHub artifacts into the repository.
