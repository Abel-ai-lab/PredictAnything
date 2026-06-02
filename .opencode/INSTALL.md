# Installing Abel Strategy Research Skills for OpenCode

Enable Abel strategy discovery workflows through the OpenCode plugin config.

Ask user to choose one install scope:

- Global: add Abel to the global OpenCode config
- Project-level: add Abel to the current project's `opencode.json`

## Global Install

Add Abel to your global OpenCode config:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-causality/abel-strategy-research-skills.git"]
}
```

## Project-Level Install

Add Abel to the `plugin` array in the current project's `opencode.json`:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-causality/abel-strategy-research-skills.git"]
}
```

To pin a specific release tag, branch, or ref, add it after `#`:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-causality/abel-strategy-research-skills.git#v1.4.2"]
}
```

Release tags are the recommended stable pin target.

## After Either Install

1. Restart OpenCode after editing the config.
2. Ask OpenCode to initialize Abel.
3. If auth is not already configured, run `abel-auth`.
4. Bootstrap the default strategy workspace:

```bash
abel-invest workspace bootstrap --path ./abel-invest-workspace
```
