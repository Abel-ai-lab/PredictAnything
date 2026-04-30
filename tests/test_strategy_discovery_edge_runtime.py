from __future__ import annotations

from pathlib import Path

from abel_invest import edge_runtime


def test_build_workspace_runtime_env_prefers_collection_auth_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / ".env").write_text("", encoding="utf-8")

    auth_file = tmp_path / "skills" / "abel-auth" / ".env.skill"
    auth_file.parent.mkdir(parents=True)
    auth_file.write_text("ABEL_API_KEY=abel-from-auth-skill\n", encoding="utf-8")

    monkeypatch.setattr(
        edge_runtime,
        "__file__",
        str(tmp_path / "skills" / "abel-invest" / "abel_invest" / "edge_runtime.py"),
    )
    monkeypatch.setattr(edge_runtime, "load_workspace_manifest", lambda _root: {"paths": {}})

    env = edge_runtime.build_workspace_runtime_env(workspace_root, base={})

    assert env["ABEL_AUTH_ENV_FILE"] == str(auth_file.resolve())
    assert env["ABEL_EDGE_CACHE_ROOT"] == str(
        (workspace_root / "cache" / "market_data").resolve()
    )


def test_build_workspace_runtime_env_prefers_workspace_auth_when_present(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    workspace_env = workspace_root / ".env"
    workspace_env.write_text("ABEL_API_KEY=abel-from-workspace\n", encoding="utf-8")

    monkeypatch.setattr(edge_runtime, "load_workspace_manifest", lambda _root: {"paths": {}})

    env = edge_runtime.build_workspace_runtime_env(workspace_root, base={})

    assert env["ABEL_AUTH_ENV_FILE"] == str(workspace_env.resolve())
    assert env["ABEL_EDGE_CACHE_ROOT"] == str(
        (workspace_root / "cache" / "market_data").resolve()
    )


def test_probe_abel_auth_prefers_collection_auth_file_without_runtime_probe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / ".env").write_text("", encoding="utf-8")

    auth_file = tmp_path / "skills" / "abel-auth" / ".env.skill"
    auth_file.parent.mkdir(parents=True)
    auth_file.write_text("ABEL_API_KEY=abel-from-auth-skill\n", encoding="utf-8")

    monkeypatch.setattr(
        edge_runtime,
        "__file__",
        str(tmp_path / "skills" / "abel-invest" / "abel_invest" / "edge_runtime.py"),
    )
    monkeypatch.setattr(edge_runtime, "load_workspace_manifest", lambda _root: {"paths": {}})

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("runtime probe should not run when shared auth is already resolvable")

    monkeypatch.setattr(edge_runtime, "run_python_json", fail_if_called)

    result = edge_runtime.probe_abel_auth("python", workspace_root)

    assert result == {
        "ok": True,
        "source": "shared_auth_file",
        "path": str(auth_file.resolve()),
    }
