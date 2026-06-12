import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "skills" / "abel-ask" / "scripts" / "data_api.py"


def _load_wrapper_module():
    spec = importlib.util.spec_from_file_location(
        "abel_ask_data_api_wrapper",
        WRAPPER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrapper_sets_default_env_file_and_base_url(monkeypatch):
    wrapper = _load_wrapper_module()
    calls = []

    def fake_main(argv):
        calls.append(argv)
        return 0

    monkeypatch.setitem(
        sys.modules,
        "abel_common.data_api",
        type(
            "M",
            (),
            {"DEFAULT_BASE_URL": "", "main": staticmethod(fake_main)},
        )(),
    )

    exit_code = wrapper.main(["catalog"])

    assert exit_code == 0
    assert calls == [
        [
            "--env-file",
            str(REPO_ROOT / "skills" / "abel-ask" / ".env.skill"),
            "catalog",
        ]
    ]
    assert sys.modules["abel_common.data_api"].DEFAULT_BASE_URL == (
        "https://cap.abel.ai/data-infra"
    )
