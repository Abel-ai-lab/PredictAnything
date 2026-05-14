"""Console entrypoint for Abel strategy discovery."""

from __future__ import annotations

import os
import sys

from abel_invest.narrative_core.commands import main as command_main


def main() -> int:
    """Run the Abel strategy discovery CLI."""
    try:
        return command_main()
    except KeyboardInterrupt:
        print("Error: interrupted by user", file=sys.stderr)
        return 130
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        if exc.code:
            print(exc.code, file=sys.stderr)
            return 1
        return 0
    except Exception as exc:
        if os.getenv("ABEL_INVEST_DEBUG"):
            raise
        message = str(exc).strip() or exc.__class__.__name__
        print(f"Error: {message}", file=sys.stderr)
        print(f"Next step: {_next_step_for_error(message)}", file=sys.stderr)
        return 1


def _next_step_for_error(message: str) -> str:
    """Return a concise recovery hint for public CLI errors."""
    lowered = message.lower()
    if "outside the resolved workspace root" in lowered:
        return (
            "Run without --root to use the workspace research root, or add "
            "--allow-outside-workspace only for intentional offline or legacy work."
        )
    if "workspace" in lowered and (
        "no abel strategy discovery workspace" in lowered or "bootstrap" in lowered
    ):
        return (
            "Run `abel-invest workspace context --path . --json`, then follow its "
            "next_step or bootstrap the reported default workspace."
        )
    if "auth" in lowered or "api key" in lowered:
        return "Use `abel-auth`, then rerun the failed Abel Invest command."
    if "journal" in lowered:
        return "Update research_journal.md with the missing ledger references, then rerun."
    return "Fix the reported issue, then rerun the command."
