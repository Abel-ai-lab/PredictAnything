"""Console entrypoint for Abel strategy discovery."""

from __future__ import annotations

from abel_invest.narrative_impl import main as narrative_main


def main() -> int:
    """Run the Abel strategy discovery CLI."""
    return narrative_main()
