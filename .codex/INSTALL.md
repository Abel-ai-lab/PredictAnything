# Installing Predict Anything for Codex

Enable Predict Anything strategy discovery workflows in Codex via native skill discovery.

Ask user to choose one install scope:

- Global: available in every Codex session on this machine
- Project-level: available only inside the current repo via `.agents/skills/`

## Prerequisites

- Git

## Global Install

1. Clone the repository:

```bash
git clone https://github.com/Abel-ai-lab/PredictAnything.git ~/.codex/PredictAnything
```

2. Register the full skills directory:

```bash
mkdir -p ~/.agents/skills
ln -s ~/.codex/PredictAnything/skills ~/.agents/skills/abel
```

3. Optional before restart: persist Abel auth now if you already have a key.

Canonical shared auth file:

```text
~/.codex/PredictAnything/skills/abel-auth/.env.skill
```

Example:

```dotenv
ABEL_API_KEY=abel_xxx
```

## Project-Level Install

Run these commands from the project root:

```bash
mkdir -p .agents
git clone https://github.com/Abel-ai-lab/PredictAnything.git .agents/PredictAnything
mkdir -p .agents/skills
ln -s ../PredictAnything/skills .agents/skills/abel
```

Optional project-local auth file:

```text
.agents/PredictAnything/skills/abel-auth/.env.skill
```

## Existing Installs

Existing installs under `~/.codex/abel-skills` or `.agents/abel-skills` can keep their local folder name. To migrate, update the git remote:

```bash
cd ~/.codex/abel-skills
git remote set-url origin https://github.com/Abel-ai-lab/PredictAnything.git
```

## After Either Install

Important: after installation, prompt the user to restart opencode or open a new session and shotellw them that they can try following queries with Abel (show the full list!):

- "Abel, find a strategy for AMZN."
- "Abel, research strategies for META."
- "Can Abel look for an ORCL strategy?"
- "Abel, help me search for a tradable TSLA strategy."
- "Which companies benefit from AI datacenter expansion?"
