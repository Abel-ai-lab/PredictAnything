# Abel Strategy Research Skills

<p align="center">
  <strong>Explore market ideas, analyze causal drivers, and research trading strategies with Abel — for quant agents, alpha research, and AI-powered investment workflows. </strong>
</p>

<p align="center">
  <a href="#codex">OpenAI Codex</a> |
  <a href="#claude-code">Claude Code</a> |
  <a href="#opencode">OpenCode</a> |
  <a href="#clawhub--openclaw">ClawHub</a>
</p>


Abel Strategy Research Skills turns AI agents into causal-graph-powered trading AI researchers. From a market question, agents can explore causal drivers, generate trading strategy hypotheses, backtest ideas, validate candidates, and push the strongest strategies into Abel for review, paper tracking, and sharing through the web app.

- **Causal-graph strategy discovery**  
  Go beyond brute-force factor search. Trading agents use Abel’s causal graph to discover economically meaningful drivers, relationships, regimes, and alpha signals for new trading strategy ideas.

- **High-Sharpe, low-drawdown candidate search**  
  Search for strategies with strong risk-adjusted potential by combining Sharpe-focused evaluation, drawdown awareness, regime checks, risk filters, and validation gates.

- **Hypothesis-to-backtest workflow**  
  Turn open-ended market questions into testable strategy hypotheses across assets, features, filters, sizing rules, model variants, and ensemble approaches.

- **Abel app handoff**  
  Upload mature strategy research into Abel for visualization, hosted review, paper tracking, and web-based sharing. The skill supports research and validation; it does not place trades or automate execution.

## Example Workflows

Ask your AI agent to:

- "Abel, find a strategy for AMZN."
- "Can Abel look for an ORCL strategy?"
- "Abel, help me search for a tradable TSLA strategy."
- "Which companies benefit from AI datacenter expansion?"
- "Analyze what is happening with TSLA."
- "Should I still invest in an MBA degree?"

## Strategy Discovery, Not Trade Execution

Abel Strategy Research Skills focus on research workflows: exploring market themes, analyzing causal drivers, developing investment strategies, and comparing hypotheses, risks, candidates, and evidence.

They do not place trades, automate execution.

Learn more: [Abel Strategy Research](docs/strategy-research.md)


## Installation

Installation differs by platform.

### Codex

Tell Codex:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-lab/abel-strategy-research-skills/refs/heads/main/.codex/INSTALL.md
```

**Detailed docs:** [docs/README.codex.md](docs/README.codex.md)

Supports:
- Global install
- Project-level install via `.agents/skills/`

### Claude Code

Tell Claude Code:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-lab/abel-strategy-research-skills/refs/heads/main/.claude/INSTALL.md
```

**Detailed docs:** [docs/README.claude.md](docs/README.claude.md)

Supports:
- Global install
- Project-level install via `.claude/skills/`

### OpenCode

Tell OpenCode:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-lab/abel-strategy-research-skills/refs/heads/main/.opencode/INSTALL.md
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
git remote set-url origin https://github.com/Abel-ai-lab/abel-strategy-research-skills.git
```

New install examples use `abel-strategy-research-skills`.

## For Maintainers

- Release documentation: [docs/releases.md](docs/releases.md)
- Branching and repository policy: `AGENTS.md`
- Maintainer endpoint rendering workflow: [maintainers/README.md](maintainers/README.md)
- Social preview source: [docs/assets/social-preview.svg](docs/assets/social-preview.svg)

Release builds publish from collection source into `dist/`. Do not commit generated ClawHub artifacts into the repository.
