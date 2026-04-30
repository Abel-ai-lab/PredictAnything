"""Console entrypoint for Abel strategy discovery."""

from __future__ import annotations

from abel_invest.narrative_core.commands import main as command_main


def main() -> int:
    """Run the Abel strategy discovery CLI."""
    return command_main()
