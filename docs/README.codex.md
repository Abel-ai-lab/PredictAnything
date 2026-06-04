# Abel Strategy Research Skills for Codex

Use Codex to discover strategies with Abel, analyze causal drivers, and support strategy research workflows.

## Quick Install

Tell Codex:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-lab/abel-strategy-research-skills/refs/heads/main/.codex/INSTALL.md
```

## Manual Installation

### Prerequisites

- OpenAI Codex
- Git

Choose one install scope:

- Global install: available in every Codex session on this machine
- Project-level install: available only inside the current repo via `.agents/skills/`

### Global Install

1. Clone the repo:

   ```bash
   git clone https://github.com/Abel-ai-lab/abel-strategy-research-skills.git ~/.codex/abel-strategy-research-skills
   ```

2. Create the skills symlink:

   ```bash
   mkdir -p ~/.agents/skills
   ln -s ~/.codex/abel-strategy-research-skills/skills ~/.agents/skills/abel
   ```

3. Before restart, either:
   - store an existing API key in `~/.codex/abel-strategy-research-skills/skills/abel-auth/.env.skill`, or
   - plan to run `abel-auth` as the first action after restart

   Example:

   ```dotenv
   ABEL_API_KEY=abel_xxx
   ```

### Project-Level Install

Run these commands from the project root:

1. Clone the repo into the project:

   ```bash
   mkdir -p .agents
   git clone https://github.com/Abel-ai-lab/abel-strategy-research-skills.git .agents/abel-strategy-research-skills
   ```

2. Create the project-local skills symlink:

   ```bash
   mkdir -p .agents/skills
   ln -s ../abel-strategy-research-skills/skills .agents/skills/abel
   ```

3. Optional project-local auth file:

   ```text
   .agents/abel-strategy-research-skills/skills/abel-auth/.env.skill
   ```

### Existing Installs

Existing installs under `~/.codex/abel-skills` or `.agents/abel-skills` can keep their local folder name. To migrate, update the checkout remote:

```bash
cd ~/.codex/abel-skills
git remote set-url origin https://github.com/Abel-ai-lab/abel-strategy-research-skills.git
```

### After Either Install

1. Restart Codex.
2. Ask Codex to initialize Abel.
3. Run `abel-auth` if auth is not already configured.
4. Bootstrap the default strategy workspace:

   ```bash
   abel-invest workspace bootstrap --path ./abel-invest-workspace
   ```

## How Auth Resolution Works

`abel-auth` is the canonical auth owner. In the global install, its local `.env.skill` file is the main shared auth location for the strategy research skill collection:

```text
~/.codex/abel-strategy-research-skills/skills/abel-auth/.env.skill
```

In the project-level install, the corresponding path is:

```text
.agents/abel-strategy-research-skills/skills/abel-auth/.env.skill
```

`abel-ask` and `abel-invest` also look for collection-level shared auth in sibling skill directories, so one successful `abel-auth` setup is enough for normal live use.

## Usage

After restart, start from `Abel`, complete `abel-auth` if needed, then bootstrap the default strategy workspace before normal strategy use.

Try:

- Abel, find a strategy for AMZN.
- Can Abel look for an ORCL strategy?
- Abel, help me search for a tradable TSLA strategy.
- Which companies benefit from AI datacenter expansion?
- Analyze what is happening with TSLA.
- Should I still invest in an MBA degree?
