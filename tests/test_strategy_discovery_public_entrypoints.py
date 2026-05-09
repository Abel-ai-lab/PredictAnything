from __future__ import annotations

from abel_invest import cli
from abel_invest.narrative_core import commands


def test_packaged_cli_entrypoint_uses_command_router() -> None:
    assert cli.command_main is commands.main
    assert callable(cli.main)
