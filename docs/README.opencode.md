# Abel Skills for OpenCode

Install the whole Abel collection through the OpenCode plugin config.

Choose one install scope:

- Global install: put the plugin entry in your global OpenCode config
- Project-level install: put the plugin entry in the current repo's `opencode.json`

## Global Install

Add Abel to your global OpenCode config:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-causality/Abel-skills.git"]
}
```

## Project-Level Install

Add Abel to the current project's `opencode.json`:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-causality/Abel-skills.git"]
}
```

## Version Pinning

To pin a specific version, branch, or tag, append it after `#`:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-causality/Abel-skills.git#v1.2.0"]
}
```

Release tags are the recommended stable pin target.

## After Either Install

Restart OpenCode, ask it to initialize Abel, then complete auth and workspace setup:

```bash
abel-auth
abel-invest workspace bootstrap --path ./abel-invest-workspace
```
