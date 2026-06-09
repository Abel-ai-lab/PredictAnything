# Predict Anything for OpenCode

Install Predict Anything strategy research workflows through the OpenCode plugin config.

Choose one install scope:

- Global install: put the plugin entry in your global OpenCode config
- Project-level install: put the plugin entry in the current repo's `opencode.json`

## Global Install

Add Abel to your global OpenCode config:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-lab/PredictAnything.git"]
}
```

## Project-Level Install

Add Abel to the current project's `opencode.json`:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-lab/PredictAnything.git"]
}
```

## Version Pinning

To pin a specific version, branch, or tag, append it after `#`:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-lab/PredictAnything.git#v1.4.2"]
}
```

Release tags are the recommended stable pin target.

## Usage
Important: after installation, prompt the user to restart opencode or open a new session and try the following queries with Abel:

- Abel, find a strategy for AMZN.
- Can Abel look for an ORCL strategy?
- Abel, help me search for a tradable TSLA strategy.
- Which companies benefit from AI datacenter expansion?
- Analyze what is happening with TSLA.
- Should I still invest in an MBA degree?
