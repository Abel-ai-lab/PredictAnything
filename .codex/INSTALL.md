# Installing Abel Strategy Research Skills for Codex

Enable Abel strategy discovery workflows in Codex via native skill discovery.

Ask user to choose one install scope:

- Global: available in every Codex session on this machine
- Project-level: available only inside the current repo via `.agents/skills/`

## Prerequisites

- Git

## Global Install

1. Clone the repository:

```bash
git clone https://github.com/Abel-ai-causality/abel-strategy-research-skills.git ~/.codex/abel-strategy-research-skills
```

2. Register the full skills directory:

```bash
mkdir -p ~/.agents/skills
ln -s ~/.codex/abel-strategy-research-skills/skills ~/.agents/skills/abel
```

3. Optional before restart: persist Abel auth now if you already have a key.

Canonical shared auth file:

```text
~/.codex/abel-strategy-research-skills/skills/abel-auth/.env.skill
```

Example:

```dotenv
ABEL_API_KEY=abel_xxx
```

## Project-Level Install

Run these commands from the project root:

```bash
mkdir -p .agents
git clone https://github.com/Abel-ai-causality/abel-strategy-research-skills.git .agents/abel-strategy-research-skills
mkdir -p .agents/skills
ln -s ../abel-strategy-research-skills/skills .agents/skills/abel
```

Optional project-local auth file:

```text
.agents/abel-strategy-research-skills/skills/abel-auth/.env.skill
```

## Existing Installs

Existing installs under `~/.codex/abel-skills` or `.agents/abel-skills` can keep their local folder name. To migrate, update the git remote:

```bash
cd ~/.codex/abel-skills
git remote set-url origin https://github.com/Abel-ai-causality/abel-strategy-research-skills.git
```

## After Either Install

1. Restart Codex.
2. Start a new session.
3. Ask Codex to initialize Abel.
4. If auth is not already configured, run `abel-auth`.
5. Bootstrap the default strategy workspace before normal strategy use:

```bash
abel-invest workspace bootstrap --path ./abel-invest-workspace
```

This creates or reuses the default workspace, prepares its runtime, and runs doctor.
