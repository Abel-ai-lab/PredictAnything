from __future__ import annotations

from pathlib import Path

from abel_invest.workspace_core import doctor


def test_run_doctor_ready_reports_alpha_managed_branch_research(
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
    monkeypatch.setattr(doctor, "resolve_edge_spec", lambda _root, manifest=None: "abel-edge @ local")
    monkeypatch.setattr(doctor, "probe_abel_edge_import", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(doctor, "probe_abel_edge_cli", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(doctor, "probe_edge_discovery_payload", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(doctor, "probe_edge_context_json", lambda *_args, **_kwargs: True)
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
    assert "alpha-managed branch research" in str(result["summary"])
    assert "init-session" in str(result["next_step"])
    assert "prepare-branch" in str(result["next_step"])

    report = doctor.render_doctor_report(result)
    assert "Workspace mode: alpha-managed branch research" in report


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
    monkeypatch.setattr(doctor, "resolve_edge_spec", lambda _root, manifest=None: "abel-edge @ local")
    monkeypatch.setattr(doctor, "probe_abel_edge_import", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(doctor, "probe_abel_edge_cli", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(doctor, "probe_edge_discovery_payload", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(doctor, "probe_edge_context_json", lambda *_args, **_kwargs: True)
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

