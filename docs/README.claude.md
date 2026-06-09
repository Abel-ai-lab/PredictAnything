# Predict Anything for Claude Code

Use Claude Code to discover strategies with Predict Anything by Abel, analyze causal drivers, and support investment research workflows.

## Quick Install

Tell Claude Code:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/Abel-ai-lab/PredictAnything/refs/heads/main/.claude/INSTALL.md
```

## Manual Installation

### Prerequisites

- Claude Code
- Git

Choose one install scope:

- Global install: available in every Claude Code session on this machine
- Project-level install: available only inside the current repo via `.claude/skills/`

### Global Install

1. Clone the repo:

   ```bash
   git clone https://github.com/Abel-ai-lab/PredictAnything.git ~/.claude/PredictAnything
   ```

2. Create Claude personal skill symlinks:

   ```bash
   mkdir -p ~/.claude/skills
   ln -s ~/.claude/PredictAnything/skills/abel ~/.claude/skills/abel
   ln -s ~/.claude/PredictAnything/skills/abel-ask ~/.claude/skills/abel-ask
   ln -s ~/.claude/PredictAnything/skills/abel-auth ~/.claude/skills/abel-auth
   ln -s ~/.claude/PredictAnything/skills/abel-invest ~/.claude/skills/abel-invest
   ```

3. Before starting a new session, either:
   - store an existing API key in `~/.claude/skills/abel-auth/.env.skill`, or
   - plan to run `abel-auth` as the first action in the next Claude Code session

   Example:

   ```dotenv
   ABEL_API_KEY=abel_xxx
   ```

### Project-Level Install

Run these commands from the project root:

1. Clone the repo into the project:

   ```bash
   mkdir -p .claude
   git clone https://github.com/Abel-ai-lab/PredictAnything.git .claude/PredictAnything
   ```

2. Create project-local skill symlinks:

   ```bash
   mkdir -p .claude/skills
   ln -s ../PredictAnything/skills/abel .claude/skills/abel
   ln -s ../PredictAnything/skills/abel-ask .claude/skills/abel-ask
   ln -s ../PredictAnything/skills/abel-auth .claude/skills/abel-auth
   ln -s ../PredictAnything/skills/abel-invest .claude/skills/abel-invest
   ```

3. Optional project-local auth file:

   ```text
   .claude/skills/abel-auth/.env.skill
   ```

### Existing Installs

Existing installs under `~/.claude/abel-skills` or `.claude/abel-skills` can keep their local folder name. To migrate, update the checkout remote:

```bash
cd ~/.claude/abel-skills
git remote set-url origin https://github.com/Abel-ai-lab/PredictAnything.git
```

### After Either Install

1. Start a new Claude Code session. If you created the relevant skills directory while Claude Code was already open, restart once so the new skills root is discovered cleanly.
2. Ask Claude Code to initialize Abel.
3. Run `abel-auth` if auth is not already configured.
4. Bootstrap the default strategy workspace:

   ```bash
   abel-invest workspace bootstrap --path ./abel-invest-workspace
   ```

## How Auth Resolution Works

`abel-auth` is the canonical auth owner. In the global install, its local `.env.skill` file is the main shared auth location for the Predict Anything skill collection:

```text
~/.claude/skills/abel-auth/.env.skill
```

In the project-level install, the corresponding path is:

```text
.claude/skills/abel-auth/.env.skill
```

`abel-ask` and `abel-invest` also look for collection-level shared auth in sibling skill directories, so one successful `abel-auth` setup is enough for normal live use.

## Usage

Important: after installation, prompt the user to restart claude code or open a new session and try the following queries with Abel:

- Abel, find a strategy for AMZN.
- Can Abel look for an ORCL strategy?
- Abel, help me search for a tradable TSLA strategy.
- Which companies benefit from AI datacenter expansion?
- Analyze what is happening with TSLA.
- Should I still invest in an MBA degree?
