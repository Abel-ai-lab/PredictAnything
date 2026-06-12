from __future__ import annotations

import io
import json
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

import pytest
from . import api as ni
from abel_invest.narrative_core.dashboard_payload import (
    build_skill_dashboard_session_bundle,
    require_timezone_aware_iso,
)
from abel_invest.narrative_core.strategy_artifact_upload import (
    post_strategy_artifact_upload,
    strategy_artifact_client_request_id,
    upload_prepared_strategy_artifact_for_session,
)


class _JsonResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


def test_dashboard_payload_requires_timezone_aware_iso() -> None:
    with pytest.raises(RuntimeError, match="endAt must include timezone"):
        require_timezone_aware_iso("2026-05-01T00:00:00", field_name="endAt")


def test_dashboard_payload_session_bundle_omits_primary_strategy(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-no-pass-dashboard", tmp_path / "research")
    branch = ni.init_branch_dir(session, "graph-fail")
    ni.append_tsv_row(
        branch / "results.tsv",
        ni.RESULTS_HEADER,
        {
            "exp_id": session.name,
            "ticker": "TSLA",
            "branch_id": branch.name,
            "round_id": "round-001",
            "decision": "discard",
            "lo_adj": "0.500",
            "ic": "0.0000",
            "omega": "0.900",
            "sharpe": "0.400",
            "max_dd": "-0.1000",
            "pnl": "5.0",
            "K": "1",
            "score": "4/9",
            "verdict": "FAIL",
            "mode": "explore",
            "description": "failed graph branch",
            "result_path": "",
            "report_path": "",
            "handoff_path": "",
        },
    )
    ni.append_tsv_row(
        session / "events.tsv",
        ni.EVENTS_HEADER,
        {
            "timestamp": "2026-04-24T01:20:00+00:00",
            "event": "round_recorded",
            "branch_id": branch.name,
            "round_id": "round-001",
            "mode": "explore",
            "verdict": "FAIL",
            "decision": "discard",
            "description": "failed graph branch",
            "artifact_path": "",
        },
    )

    bundle = build_skill_dashboard_session_bundle(
        session,
        uploaded_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )

    assert "primaryStrategy" not in bundle["payload"]
    assert bundle["payload"]["session"]["id"] == "tsla-no-pass-dashboard"
    assert bundle["payload"]["rounds"][0]["branchId"] == "graph-fail"


def test_dashboard_payload_accepts_ticker_directory_with_one_session(
    tmp_path: Path,
) -> None:
    session = ni.init_session_dir("ORCL", "orcl-r10", tmp_path / "research")

    bundle = build_skill_dashboard_session_bundle(
        session.parent,
        uploaded_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )

    assert bundle["sessionId"] == "orcl-r10"
    assert bundle["payload"]["session"]["ticker"] == "ORCL"


def test_post_skill_dashboard_session_sends_to_session_endpoint() -> None:
    calls = []

    def fake_opener(request, timeout):
        calls.append((request, timeout))
        return _JsonResponse(b'{"code": 200, "data": {"sessionId": "s1"}}')

    result = ni.post_skill_dashboard_session(
        base_url="https://router.example",
        api_key="secret-key",
        bundle={"sessionId": "s1", "payload": {"session": {}, "branches": [], "rounds": []}},
        opener=fake_opener,
    )

    request, timeout = calls[0]
    assert result["data"]["sessionId"] == "s1"
    assert request.full_url == "https://router.example/web/skill-dashboard/sessions"
    assert request.get_header("Api-key") == "secret-key"
    assert request.get_header("Content-type") == "application/json"
    assert timeout == 60


def test_prepared_strategy_artifact_upload_skips_without_hosted_session_id(
    tmp_path: Path,
) -> None:
    result = upload_prepared_strategy_artifact_for_session(
        narrative_result={"data": {}},
        base_url="https://router.example",
        api_key="secret-key",
        export_result={
            "artifactExported": True,
            "artifactUploadSkipped": False,
            "manifestPath": str(tmp_path / "manifest.json"),
            "artifactPath": str(tmp_path / "artifact.zip"),
        },
    )

    assert result == {
        "artifactExported": False,
        "artifactUploadSkipped": True,
        "manifestPath": str(tmp_path / "manifest.json"),
        "artifactPath": str(tmp_path / "artifact.zip"),
        "skipReason": "hosted_session_id_missing",
    }


def test_strategy_artifact_upload_failure_keeps_export_context(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    artifact_path = tmp_path / "artifact.zip"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "abel-invest.strategy-artifact/v1",
                "source": {
                    "sourceSessionId": "local-s1",
                    "branchId": "b1",
                    "roundId": "round-001",
                },
            }
        ),
        encoding="utf-8",
    )
    artifact_path.write_bytes(b"artifact zip")

    def failing_opener(request, timeout):
        raise OSError("network down")

    result = upload_prepared_strategy_artifact_for_session(
        narrative_result={"data": {"sessionId": "sess_1", "uploadId": "narrative_1"}},
        base_url="https://router.example",
        api_key="secret-key",
        export_result={
            "artifactExported": True,
            "artifactUploadSkipped": False,
            "manifestPath": str(manifest_path),
            "artifactPath": str(artifact_path),
            "selectedBranchId": "b1",
            "selectedRoundId": "round-001",
        },
        opener=failing_opener,
    )

    assert result["artifactUploadFailed"] is True
    assert result["artifactUploadError"] == "network down"
    assert result["selectedBranchId"] == "b1"


def test_post_strategy_artifact_upload_sends_multipart_request(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.zip"
    artifact_path.write_bytes(b"zip-bytes")
    calls = []

    def fake_opener(request, timeout):
        calls.append((request, timeout))
        return _JsonResponse(
            b'{"data": {"artifactUploadId": "upload_1", "admissionStatus": "queued"}}'
        )

    result = post_strategy_artifact_upload(
        base_url="https://router.example/",
        api_key="secret-key",
        hosted_session_id="sess_1",
        manifest={"schema": "abel-invest.strategy-artifact/v1"},
        artifact_path=artifact_path,
        source_upload_id="upload_narrative",
        client_request_id="client_1",
        opener=fake_opener,
    )

    request, timeout = calls[0]
    body = request.data
    assert result["data"]["artifactUploadId"] == "upload_1"
    assert request.full_url == (
        "https://router.example/web/skill-dashboard/sessions/sess_1/strategy-artifacts"
    )
    assert request.get_header("Api-key") == "secret-key"
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'name="manifest"' in body
    assert b'name="artifact"; filename="artifact.zip"' in body
    assert b"name=\"sourceUploadId\"" in body
    assert b"name=\"clientRequestId\"" in body
    assert timeout == 60


def test_post_strategy_artifact_upload_preserves_router_error_detail(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "artifact.zip"
    artifact_path.write_bytes(b"artifact zip")

    def failing_opener(request, timeout):
        raise HTTPError(
            request.full_url,
            400,
            "Bad Request",
            {},
            io.BytesIO(b"router detail"),
        )

    with pytest.raises(RuntimeError, match="router detail"):
        post_strategy_artifact_upload(
            base_url="https://router.example",
            api_key="secret-key",
            hosted_session_id="sess_1",
            manifest={"schema": "abel-invest.strategy-artifact/v1"},
            artifact_path=artifact_path,
            opener=failing_opener,
        )


def test_strategy_artifact_client_request_id_is_deterministic() -> None:
    manifest = {
        "schema": "abel-invest.strategy-artifact/v1",
        "source": {
            "sourceSessionId": "local-s1",
            "branchId": "b1",
            "roundId": "round-001",
        },
    }

    first = strategy_artifact_client_request_id(manifest)
    second = strategy_artifact_client_request_id(dict(reversed(list(manifest.items()))))

    assert first == second
    assert first.startswith("local-s1:b1:round-001:")
    assert len(first.rsplit(":", 1)[1]) == 16


def test_visualize_session_uploads_strategy_artifact_by_default(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    calls = []
    export_kwargs = []

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "resolve_skill_dashboard_base_url",
        lambda: "https://router.example",
    )

    def fake_export(*args, **kwargs):
        calls.append("export")
        export_kwargs.append(kwargs)
        return {
            "artifactExported": True,
            "artifactUploadSkipped": False,
            "manifestPath": str(tmp_path / "manifest.json"),
            "artifactPath": str(tmp_path / "artifact.zip"),
            "selectedBranchId": "momentum_lead",
            "selectedRoundId": "round-006",
        }

    def fake_post_session(**kwargs):
        calls.append("post_session")
        return {
            "data": {"sessionId": "sess_1", "openUrl": "https://app.example/sess_1"}
        }

    def fake_prepared_upload(**kwargs):
        calls.append("upload_artifact")
        assert kwargs["export_result"]["artifactExported"] is True
        return {"artifactUploadId": "upload_1", "admissionStatus": "queued"}

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "export_selected_strategy_artifact",
        fake_export,
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "post_skill_dashboard_session",
        fake_post_session,
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "upload_prepared_strategy_artifact_for_session",
        fake_prepared_upload,
    )

    ni.upload_skill_dashboard_session(
        Namespace(
            session=str(session),
            api_key="secret-key",
            output_json=None,
            dry_run=False,
            artifact_output_dir=None,
            python_bin=None,
        )
    )

    assert calls == ["export", "post_session", "upload_artifact"]
    assert export_kwargs[0]["strategy"] is None
    assert export_kwargs[0]["round_id"] is None
    assert (
        export_kwargs[0]["rerun_command"]
        == f"abel-invest visualize-session --session {session.resolve()}"
    )
    output = capsys.readouterr().out
    assert "Strategy artifact uploaded: upload_1" in output
    assert "admission=queued" in output
    assert "router admission continues asynchronously" in output
    assert "Session strategies near the bottom" in output


def test_visualize_session_uploads_explicit_strategy_artifact_after_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    branch = ni.init_branch_dir(session, "momentum_lead")
    captured = {}

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "resolve_skill_dashboard_base_url",
        lambda: "https://router.example",
    )

    def fake_export(session_arg, **kwargs):
        captured["session"] = session_arg
        captured["kwargs"] = kwargs
        return {
            "artifactExported": True,
            "artifactUploadSkipped": False,
            "manifestPath": str(tmp_path / "manifest.json"),
            "artifactPath": str(tmp_path / "artifact.zip"),
            "selectedBranchId": branch.name,
            "selectedRoundId": "round-006",
        }

    def fake_post_session(**kwargs):
        return {
            "data": {
                "sessionId": "sess_1",
                "uploadId": "upload_1",
                "openUrl": "https://app.example/sess_1",
            }
        }

    def fake_prepared_upload(**kwargs):
        assert kwargs["export_result"]["selectedBranchId"] == branch.name
        return {"artifactUploadId": "artifact_1", "admissionStatus": "queued"}

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "export_selected_strategy_artifact",
        fake_export,
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "post_skill_dashboard_session",
        fake_post_session,
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "upload_prepared_strategy_artifact_for_session",
        fake_prepared_upload,
    )

    ni.upload_skill_dashboard_session(
        Namespace(
            session=str(session),
            api_key="secret-key",
            output_json=None,
            dry_run=False,
            artifact_output_dir=None,
            python_bin=None,
            strategy=str(branch),
            round="round-006",
        )
    )

    assert captured["session"] == session.resolve()
    assert captured["kwargs"]["strategy"] == str(branch)
    assert captured["kwargs"]["round_id"] == "round-006"
    expected_rerun_command = (
        f"abel-invest visualize-session --session {session.resolve()} "
        f"--strategy {branch} --round round-006"
    )
    assert (
        captured["kwargs"]["rerun_command"]
        == expected_rerun_command
    )


def test_visualize_session_aborts_before_upload_when_agent_paper_contract_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = ni.init_session_dir("TSLA", "tsla-v1", tmp_path / "research")
    calls = []

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "resolve_skill_dashboard_base_url",
        lambda: "https://router.example",
    )
    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "export_selected_strategy_artifact",
        lambda *args, **kwargs: {
            "artifactExported": False,
            "artifactUploadSkipped": True,
            "skipReason": "hosted_paper_contract_required",
            "promotionMode": "hosted_paper_contract_required",
            "promotionReport": {
                "mode": "hosted_paper_contract_required",
                "reason": "dynamic state path requires paper contract",
                "requestPath": str(tmp_path / "paper-contract-request.json"),
            },
        },
    )

    def unexpected_post_session(**kwargs):
        calls.append("post_session")
        raise AssertionError("narrative upload should not start")

    monkeypatch.setitem(
        ni.upload_skill_dashboard_session.__globals__,
        "post_skill_dashboard_session",
        unexpected_post_session,
    )

    with pytest.raises(RuntimeError, match="hosted paper contract"):
        ni.upload_skill_dashboard_session(
            Namespace(
                session=str(session),
                api_key="secret-key",
                output_json=None,
                dry_run=False,
                artifact_output_dir=None,
                python_bin=None,
            )
        )

    assert calls == []


def test_render_strategy_artifact_upload_result_lines() -> None:
    rendered = ni.render_skill_dashboard_session_upload_result(
        {
            "data": {
                "sessionId": "sess_1",
                "openUrl": "https://app.example/sess_1",
            }
        },
        artifact_result={
            "artifactUploadId": "upload_1",
            "admissionStatus": "queued",
            "selectedBranchId": "momentum_lead",
            "selectedRoundId": "round-006",
        },
    )

    assert "Online session view: [Open sess_1](https://app.example/sess_1)" in rendered
    assert "Strategy artifact uploaded: upload_1" in rendered
    assert "admission=queued" in rendered
    assert "router admission continues asynchronously" in rendered
    assert "Session strategies near the bottom" in rendered


def test_render_skill_dashboard_session_upload_result_returns_markdown_link() -> None:
    rendered = ni.render_skill_dashboard_session_upload_result(
        {
            "code": 200,
            "data": {
                "sessionId": "s1",
                "openUrl": "https://app.abel.ai/abel-invest/s1",
            },
        }
    )

    assert rendered == "Online session view: [Open s1](https://app.abel.ai/abel-invest/s1)"


def test_resolve_skill_dashboard_base_url_defaults_to_abel_router() -> None:
    assert ni.resolve_skill_dashboard_base_url("") == "https://api.abel.ai/router/"
