from pathlib import Path


def test_strategy_discovery_bootstrap_script_exists() -> None:
    script = Path(__file__).resolve().parents[1] / "skills" / "abel-strategy-discovery" / "scripts" / "bootstrap_workspace.py"
    assert script.exists(), "bootstrap script is missing"
