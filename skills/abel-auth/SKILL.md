---
name: abel-auth
description: >
  Use when Abel auth is missing, expired, invalid, or needs initialization.
metadata:
  openclaw:
    requires:
      bins:
        - python3
---

Use this skill when Abel auth is missing, expired, or needs to be initialized.

1. Check whether usable Abel auth already exists by running:

   ```bash
   python3 <abel-auth-skill-root>/../abel-common/python/abel_common/cap/graph_probe.py auth-status
   ```

   Resolve `<abel-auth-skill-root>` to this installed skill directory before
   running the command. Do not use a current-working-directory relative
   `../abel-common` path.

2. Reuse existing auth if present.
3. If auth is missing or invalid, read `references/setup-guide.md` and start the OAuth handoff from there.
4. Persist the resulting key to `<abel-auth-skill-root>/.env.skill` for this installed collection.
5. Report whether Abel is ready for live use.
