# Installing Abel Skills for Codex

Enable Abel Skills in Codex via native skill discovery.

Ask user to choose one install scope:

- Global: available in every Codex session on this machine
- Project-level: available only inside the current repo via `.agents/skills/`

## Prerequisites

- Git

## Global Install

1. Clone the repository:

```bash
git clone https://github.com/Abel-ai-causality/Abel-skills.git ~/.codex/abel-skills
```

2. Register the full skills directory:

```bash
mkdir -p ~/.agents/skills
ln -s ~/.codex/abel-skills/skills ~/.agents/skills/abel
```

3. Optional before restart: persist Abel auth now if you already have a key.

Canonical shared auth file:

```text
~/.codex/abel-skills/skills/abel-auth/.env.skill
```

Example:

```dotenv
ABEL_API_KEY=abel_xxx
```

## Project-Level Install

Run these commands from the project root:

```bash
mkdir -p .agents
git clone https://github.com/Abel-ai-causality/Abel-skills.git .agents/abel-skills
mkdir -p .agents/skills
ln -s ../abel-skills/skills .agents/skills/abel
```

Optional project-local auth file:

```text
.agents/abel-skills/skills/abel-auth/.env.skill
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
