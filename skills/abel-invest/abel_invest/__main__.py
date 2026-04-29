"""Allow `python -m abel_invest`."""

from __future__ import annotations

from abel_invest.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
