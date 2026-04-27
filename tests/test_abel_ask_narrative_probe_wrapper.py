from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "skills" / "abel-ask" / "scripts" / "narrative_cap_probe.py"


def _load_wrapper_module():
    spec = importlib.util.spec_from_file_location(
        "abel_ask_narrative_cap_probe_wrapper",
        WRAPPER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrapper_exists() -> None:
    assert WRAPPER_PATH.exists()


def test_wrapper_exposes_default_override_constants() -> None:
    wrapper = _load_wrapper_module()

    assert hasattr(wrapper, "DEFAULT_BASE_URL")
    assert hasattr(wrapper, "DEFAULT_API_KEY_ENV")


def test_wrapper_injects_skill_local_env_file(monkeypatch) -> None:
    wrapper = _load_wrapper_module()
    captured: dict[str, object] = {}

    def fake_main(argv):
        captured["argv"] = argv
        return 0

    import sys

    monkeypatch.setitem(sys.modules, "abel_common.cap.narrative_probe", type("M", (), {"DEFAULT_BASE_URL": "", "DEFAULT_API_KEY_ENV": "", "main": staticmethod(fake_main)})())

    exit_code = wrapper.main(["card"])

    assert exit_code == 0
    assert captured["argv"][:2] == ["--env-file", str(WRAPPER_PATH.parents[1] / ".env.skill")]
