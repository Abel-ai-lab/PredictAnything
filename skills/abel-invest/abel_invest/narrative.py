"""Public package surface for the packaged narrative CLI."""

from __future__ import annotations

from typing import Any

from abel_invest import narrative_impl as _impl


def main() -> int:
    """Run the packaged narrative CLI."""
    return _impl.main()


def __getattr__(name: str) -> Any:
    """Expose narrative helpers through the package namespace during migration."""
    try:
        return getattr(_impl, name)
    except AttributeError as exc:
        raise AttributeError(f"module 'abel_invest.narrative' has no attribute {name!r}") from exc
