from __future__ import annotations

from abel_invest import cli, narrative, narrative_impl


def test_packaged_cli_entrypoints_share_main() -> None:
    assert cli.narrative_main is narrative_impl.main
    assert callable(cli.main)
    assert callable(narrative.main)
    assert callable(narrative_impl.main)
