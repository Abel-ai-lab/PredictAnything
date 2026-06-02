# Installing Abel Strategy Research Skills for Claude Code

Enable Abel strategy discovery workflows in Claude Code via skill symlinks.

Ask user to choose one install scope:

- Global: available in every Claude Code session on this machine
- Project-level: available only inside the current repo via `.claude/skills/`

## Prerequisites

- Git
- Claude Code with skills enabled

## Global Install

1. Clone the repository:

```bash
git clone https://github.com/Abel-ai-causality/abel-strategy-research-skills.git ~/.claude/abel-strategy-research-skills
```

2. Register the Abel strategy research skills in Claude's personal skills directory:

```bash
mkdir -p ~/.claude/skills
ln -s ~/.claude/abel-strategy-research-skills/skills/abel ~/.claude/skills/abel
ln -s ~/.claude/abel-strategy-research-skills/skills/abel-ask ~/.claude/skills/abel-ask
ln -s ~/.claude/abel-strategy-research-skills/skills/abel-auth ~/.claude/skills/abel-auth
ln -s ~/.claude/abel-strategy-research-skills/skills/abel-invest ~/.claude/skills/abel-invest
```

3. Optional before restart: persist Abel auth now if you already have a key.

Canonical shared auth file:

```text
~/.claude/skills/abel-auth/.env.skill
```

Example:

```dotenv
ABEL_API_KEY=abel_xxx
```

## Project-Level Install

Run these commands from the project root:

```bash
mkdir -p .claude
git clone https://github.com/Abel-ai-causality/abel-strategy-research-skills.git .claude/abel-strategy-research-skills
mkdir -p .claude/skills
ln -s ../abel-strategy-research-skills/skills/abel .claude/skills/abel
ln -s ../abel-strategy-research-skills/skills/abel-ask .claude/skills/abel-ask
ln -s ../abel-strategy-research-skills/skills/abel-auth .claude/skills/abel-auth
ln -s ../abel-strategy-research-skills/skills/abel-invest .claude/skills/abel-invest
```

Optional project-local auth file:

```text
.claude/skills/abel-auth/.env.skill
```

## Existing Installs

Existing installs under `~/.claude/abel-skills` or `.claude/abel-skills` can keep their local folder name. To migrate, update the git remote:

```bash
cd ~/.claude/abel-skills
git remote set-url origin https://github.com/Abel-ai-causality/abel-strategy-research-skills.git
```

## After Either Install

1. Start a new Claude Code session. If Claude Code was already open when you created the skills directory, restart it once.
2. Ask Claude Code to initialize Abel.
3. If auth is not already configured, run `abel-auth`.
4. Bootstrap the default strategy workspace before normal strategy use:

```bash
abel-invest workspace bootstrap --path ./abel-invest-workspace
```
