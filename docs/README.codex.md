# Abel Skills for Codex

Guide for using Abel Skills with OpenAI Codex via native skill discovery.

## Quick Install

Tell Codex:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-causality/Abel-skills/refs/heads/main/.codex/INSTALL.md
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
   git clone https://github.com/Abel-ai-causality/Abel-skills.git ~/.codex/abel-skills
   ```

2. Create the skills symlink:

   ```bash
   mkdir -p ~/.agents/skills
   ln -s ~/.codex/abel-skills/skills ~/.agents/skills/abel
   ```

3. Before restart, either:
   - store an existing API key in `~/.codex/abel-skills/skills/abel-auth/.env.skill`, or
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
   git clone https://github.com/Abel-ai-causality/Abel-skills.git .agents/abel-skills
   ```

2. Create the project-local skills symlink:

   ```bash
   mkdir -p .agents/skills
   ln -s ../abel-skills/skills .agents/skills/abel
   ```

3. Optional project-local auth file:

   ```text
   .agents/abel-skills/skills/abel-auth/.env.skill
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

`abel-auth` is the canonical auth owner. In the global install, its local
`.env.skill` file is the main shared auth location for the collection:

```text
~/.codex/abel-skills/skills/abel-auth/.env.skill
```

In the project-level install, the corresponding path is:

```text
.agents/abel-skills/skills/abel-auth/.env.skill
```

`abel-ask` and `abel-invest` also look for collection-level shared
auth in sibling skill directories, so one successful `abel-auth` setup is enough
for normal live use.

## Usage

After restart, start from `Abel`, complete `abel-auth` if needed, then bootstrap
the default strategy workspace before normal strategy use.

Try:

- Help me search for a TSLA strategy.
- Continue my TSLA strategy workspace.
- Give me an Abel read on what drives mortgage-rate-sensitive homebuilder stocks.
