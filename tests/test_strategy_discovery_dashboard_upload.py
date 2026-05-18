from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

import pytest
import strategy_discovery_api as ni
from abel_invest.narrative_core.dashboard_payload import (
    build_skill_dashboard_session_bundle,
    require_timezone_aware_iso,
)
from abel_invest.narrative_core.strategy_artifact_upload import (
    post_strategy_artifact_upload,
    strategy_artifact_client_request_id,
    upload_prepared_strategy_artifact_for_session,
    upload_strategy_artifact_for_session,
)


def test_dashboard_payload_requires_timezone_aware_iso() -> None:
    with pytest.raises(RuntimeError, match="endAt must include timezone"):
        require_timezone_aware_iso("2026-05-01T00:00:00", field_name="endAt")


def test_dashboard_payload_session_bundle_keeps_primary_strategy_null_without_pass(
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

    assert bundle["payload"]["primaryStrategy"] is None
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


def test_strategy_artifact_upload_skips_without_hosted_session_id(tmp_path: Path) -> None:
    def unexpected_runner(*args, **kwargs):
        raise AssertionError("export should not run without a hosted session id")

    result = upload_strategy_artifact_for_session(
        local_session=tmp_path,
        narrative_result={"data": {}},
        base_url="https://router.example",
        api_key="secret-key",
        runner=unexpected_runner,
    )

    assert result == {
        "artifactExported": False,
        "artifactUploadSkipped": True,
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
        local_session=tmp_path,
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
