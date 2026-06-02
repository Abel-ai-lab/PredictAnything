# Security Policy

Please report security issues privately at `security@abel.ai`.

Do not open public issues for:

- leaked Abel API keys
- auth bypasses
- credential persistence bugs
- token handling vulnerabilities

Abel Strategy Research Skills may store local auth configuration. Never commit `.env.skill` files or API keys.

## Local Auth Files

Common local auth paths include:

- `~/.codex/abel-strategy-research-skills/skills/abel-auth/.env.skill`
- `~/.claude/skills/abel-auth/.env.skill`
- `.agents/abel-strategy-research-skills/skills/abel-auth/.env.skill`
- `.claude/skills/abel-auth/.env.skill`
