"""Public package surface for the packaged narrative CLI."""

from __future__ import annotations

from abel_invest import narrative_impl as _impl


def main() -> int:
    """Run the packaged narrative CLI."""
    return _impl.main()
