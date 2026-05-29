from __future__ import annotations

from pathlib import Path

from abel_invest.workspace_core import doctor


def test_run_doctor_ready_reports_alpha_managed_strategy_search(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    python_path = root / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        doctor,
        "resolve_workspace_entry",
        lambda start=None: (root, "current_workspace_root"),
    )
    monkeypatch.setattr(doctor, "load_workspace_manifest", lambda _root: {"runtime": {}})
    monkeypatch.setattr(doctor, "resolve_runtime_python", lambda _root, manifest=None: python_path)
    monkeypatch.setattr(doctor, "resolve_workspace_env_file", lambda _root: root / ".env")
    monkeypatch.setattr(doctor, "probe_abel_edge_import", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(doctor, "probe_abel_edge_cli", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(doctor, "probe_edge_discovery_payload", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(doctor, "probe_edge_context_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        doctor,
        "probe_package_freshness",
        lambda *_args, **_kwargs: {"ok": True, "summary": "fresh"},
    )
    monkeypatch.setattr(
        doctor,
        "probe_abel_auth",
        lambda *_args, **_kwargs: {
            "ok": True,
            "source": "workspace_env",
            "path": str(root / ".env"),
        },
    )

    result = doctor.run_doctor(root)

    assert result["status"] == "ready"
    assert result["workspace_mode"] == doctor.WORKSPACE_MODE
    assert "alpha-managed strategy search" in str(result["summary"])
    assert "init-session" in str(result["next_step"])
    assert "prepare-branch" in str(result["next_step"])

    report = doctor.render_doctor_report(result)
    assert "Workspace mode: alpha-managed strategy search" in report
    assert "Edge install target:" not in report


def test_run_doctor_auth_missing_routes_to_abel_auth(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    python_path = root / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        doctor,
        "resolve_workspace_entry",
        lambda start=None: (root, "current_workspace_root"),
    )
    monkeypatch.setattr(doctor, "load_workspace_manifest", lambda _root: {"runtime": {}})
    monkeypatch.setattr(doctor, "resolve_runtime_python", lambda _root, manifest=None: python_path)
    monkeypatch.setattr(doctor, "resolve_workspace_env_file", lambda _root: root / ".env")
    monkeypatch.setattr(doctor, "probe_abel_edge_import", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(doctor, "probe_abel_edge_cli", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(doctor, "probe_edge_discovery_payload", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(doctor, "probe_edge_context_json", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        doctor,
        "probe_package_freshness",
        lambda *_args, **_kwargs: {"ok": True, "summary": "fresh"},
    )
    monkeypatch.setattr(
        doctor,
        "probe_abel_auth",
        lambda *_args, **_kwargs: {"ok": False, "source": "missing"},
    )

    result = doctor.run_doctor(root)
    report = doctor.render_doctor_report(result)

    assert result["status"] == "auth_missing"
    assert "abel-auth" in str(result["next_step"])
    assert "abel_edge.cli login" not in str(result)
    assert "edge_login_fallback" not in str(result)
    assert "Auth action: Use abel-auth" in report


def test_run_doctor_runtime_stale_routes_to_env_refresh(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    python_path = root / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        doctor,
        "resolve_workspace_entry",
        lambda start=None: (root, "current_workspace_root"),
    )
    monkeypatch.setattr(doctor, "load_workspace_manifest", lambda _root: {"runtime": {}})
    monkeypatch.setattr(doctor, "resolve_runtime_python", lambda _root, manifest=None: python_path)
    monkeypatch.setattr(doctor, "resolve_workspace_env_file", lambda _root: root / ".env")
    monkeypatch.setattr(
        doctor,
        "probe_package_freshness",
        lambda *_args, **_kwargs: {
            "ok": False,
            "summary": "Workspace runtime has abel-edge 0.8.4, below this skill's required >= 0.8.8.",
        },
    )

    result = doctor.run_doctor(root)
    report = doctor.render_doctor_report(result)

    assert result["status"] == "runtime_stale"
    assert result["checks"]["package_freshness"] == "fail"
    assert result["next_step"] == f"{python_path} -m abel_invest env refresh --path {root}"
    assert "Package freshness: Workspace runtime has abel-edge 0.8.4" in report

