from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NARRATIVE_CAP_PROBE_PATH = (
    REPO_ROOT / "skills" / "abel-common" / "python" / "abel_common" / "cap" / "narrative_probe.py"
)


def _load_narrative_cap_probe_module():
    spec = importlib.util.spec_from_file_location(
        "abel_common_narrative_cap_probe",
        NARRATIVE_CAP_PROBE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_cap_endpoint_uses_narrative_cap_route() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    assert (
        narrative_cap_probe.resolve_cap_endpoint("https://cap.abel.ai/narrative")
        == "https://cap.abel.ai/narrative/cap"
    )


def test_resolve_cap_endpoint_preserves_explicit_narrative_cap_route() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    assert (
        narrative_cap_probe.resolve_cap_endpoint("https://cap.abel.ai/narrative/cap")
        == "https://cap.abel.ai/narrative/cap"
    )


def test_resolve_card_endpoint_uses_well_known_card_route() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    assert (
        narrative_cap_probe.resolve_card_endpoint("https://cap.abel.ai/narrative")
        == "https://cap.abel.ai/.well-known/cap.json"
    )


def test_resolve_base_url_ignores_runtime_narrative_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    monkeypatch.setenv("NARRATIVE_CAP_BASE_URL", "https://override.example/narrative")

    assert narrative_cap_probe._resolve_base_url("") == "https://cap.abel.ai/narrative"


def test_build_payload_preserves_provider_graph_ref_and_response_detail() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    payload = narrative_cap_probe._build_payload(
        "narrate",
        {"query": "AI datacenter demand and NVDA"},
        graph_ref="alb:execution:exec_1",
        response_detail="full",
    )

    assert payload["verb"] == "narrate"
    assert payload["params"] == {"query": "AI datacenter demand and NVDA"}
    assert payload["context"] == {"graph_ref": {"graph_id": "alb:execution:exec_1"}}
    assert payload["options"] == {"response_detail": "full"}


def test_build_payload_does_not_inject_graph_context_for_meta_verbs() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    payload = narrative_cap_probe._build_payload("meta.methods")

    assert "context" not in payload


def test_explain_read_bundle_passes_through_optional_params() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()
    captured: dict[str, object] = {}

    def _fake_call_verb(args, verb, params=None):
        captured["verb"] = verb
        captured["params"] = params
        return {"ok": True}

    narrative_cap_probe._call_verb = _fake_call_verb
    parser = narrative_cap_probe._build_parser()
    args = parser.parse_args(
        [
            "explain-read-bundle",
            "--query",
            "NVDA",
            "--search-mode",
            "hybrid",
            "--top-k",
            "7",
            "--question-type",
            "directional",
            "--strictness",
            "exploratory",
            "--include-layer",
            "supporting_evidence",
            "--include-layer",
            "top_tailwinds",
        ]
    )

    result = args.func(args)

    assert result == {"ok": True}
    assert captured["verb"] == "extensions.abel.stateless.explain_read_bundle"
    assert captured["params"] == {
        "search": "NVDA",
        "search_mode": "hybrid",
        "top_k": 7,
        "question_type": "directional",
        "strictness": "exploratory",
        "include_layers": ["supporting_evidence", "top_tailwinds"],
    }


def test_explain_outcome_passes_through_optional_params() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()
    captured: dict[str, object] = {}

    def _fake_call_verb(args, verb, params=None):
        captured["verb"] = verb
        captured["params"] = params
        return {"ok": True}

    narrative_cap_probe._call_verb = _fake_call_verb
    parser = narrative_cap_probe._build_parser()
    args = parser.parse_args(
        [
            "explain-outcome",
            "--query",
            "AI datacenter demand and NVDA",
            "--search-mode",
            "semantic",
            "--top-k",
            "6",
            "--outcome-mode",
            "generic",
            "--focus-strategy",
            "query_local",
            "--focus-top-n",
            "9",
            "--top-driver-count",
            "4",
            "--max-paths",
            "2",
            "--max-hops",
            "5",
            "--include-bayes-evidence",
        ]
    )

    result = args.func(args)

    assert result == {"ok": True}
    assert captured["verb"] == "extensions.abel.stateless.explain_outcome"
    assert captured["params"] == {
        "search": "AI datacenter demand and NVDA",
        "search_mode": "semantic",
        "top_k": 6,
        "outcome_mode": "generic",
        "focus_strategy": "query_local",
        "focus_top_n": 9,
        "top_driver_count": 4,
        "max_paths": 2,
        "max_hops": 5,
        "include_bayes_evidence": True,
    }


def test_query_node_passes_through_advanced_json() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()
    captured: dict[str, object] = {}

    def _fake_call_verb(args, verb, params=None):
        captured["verb"] = verb
        captured["params"] = params
        return {"ok": True}

    narrative_cap_probe._call_verb = _fake_call_verb
    parser = narrative_cap_probe._build_parser()
    args = parser.parse_args(
        [
            "query-node",
            "--query",
            "NVDA",
            "--advanced-json",
            '{"symbols":["NVDA"],"claim_types":["PREDICTION"]}',
        ]
    )

    result = args.func(args)

    assert result == {"ok": True}
    assert captured["verb"] == "extensions.abel.stateless.query_node"
    assert captured["params"] == {
        "search": "NVDA",
        "advanced": {
            "symbols": ["NVDA"],
            "claim_types": ["PREDICTION"],
        },
    }


def test_resolve_api_token_uses_shared_graph_token_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    monkeypatch.setenv("ABEL_API_KEY", "shared-graph-token")
    monkeypatch.setenv("CAP_API_KEY", "shared-cap-token")
    monkeypatch.setenv("ACTIVE_NARRATIVE_CAP_API_KEY_ENV", "ABEL_DATA_INTEL_API_KEY")
    monkeypatch.setenv("ABEL_DATA_INTEL_API_KEY", "narrative-only-token")

    assert narrative_cap_probe._resolve_api_token(None) == "shared-cap-token"


def test_resolve_api_token_falls_back_to_abel_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    monkeypatch.delenv("NARRATIVE_CAP_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)
    monkeypatch.setenv("ACTIVE_NARRATIVE_CAP_API_KEY_ENV", "ABEL_DATA_INTEL_API_KEY")
    monkeypatch.setenv("ABEL_DATA_INTEL_API_KEY", "test-narrative-token")
    monkeypatch.setenv("ABEL_API_KEY", "shared-graph-token")

    assert narrative_cap_probe._resolve_api_token(None) == "shared-graph-token"


def test_resolve_auth_status_matches_graph_probe_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    monkeypatch.delenv("CAP_API_KEY", raising=False)
    monkeypatch.delenv("ABEL_API_KEY", raising=False)

    status = narrative_cap_probe._resolve_auth_status(None, ".env.skill")

    assert status == {
        "auth_ready": False,
        "auth_source": "missing",
        "oauth_required": True,
    }


def test_resolve_auth_status_reports_session_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    monkeypatch.setenv("ABEL_API_KEY", "shared-graph-token")

    status = narrative_cap_probe._resolve_auth_status(None, ".env.skill")

    assert status == {
        "auth_ready": True,
        "auth_source": "session",
        "oauth_required": False,
    }


def test_resolve_headers_match_graph_bearer_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    monkeypatch.delenv("NARRATIVE_CAP_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)
    monkeypatch.setenv("ABEL_API_KEY", "shared-graph-token")

    headers = narrative_cap_probe._resolve_headers(None)

    assert headers["Authorization"] == "Bearer shared-graph-token"
    assert "X-API-Key" not in headers


def test_capability_card_request_reuses_auth_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()
    captured: dict[str, object] = {}

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"name":"narrative"}'

    def _fake_urlopen(request, timeout=20.0):
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(
        narrative_cap_probe.urllib.request, "urlopen", _fake_urlopen
    )

    result = narrative_cap_probe._get_card(
        "https://cap.abel.ai/narrative",
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer shared-graph-token",
        },
    )

    assert result["ok"] is True
    assert captured["headers"]["Authorization"] == "Bearer shared-graph-token"


def test_core_observe_predict_and_intervene_do_pass_params() -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()
    captured: list[tuple[str, dict[str, object]]] = []

    def _fake_call_verb(args, verb, params=None):
        captured.append((verb, params or {}))
        return {"ok": True}

    narrative_cap_probe._call_verb = _fake_call_verb
    parser = narrative_cap_probe._build_parser()

    observe_args = parser.parse_args(
        [
            "observe-predict",
            "--target-node",
            "bayes:NVDA:PREDICTION:abc",
        ]
    )
    intervene_args = parser.parse_args(
        [
            "intervene-do",
            "--treatment-node",
            "bayes:MSFT:PREDICTION:def",
            "--treatment-value",
            "0.25",
            "--outcome-node",
            "bayes:NVDA:PREDICTION:abc",
        ]
    )

    assert observe_args.func(observe_args) == {"ok": True}
    assert intervene_args.func(intervene_args) == {"ok": True}
    assert captured == [
        (
            "observe.predict",
            {"target_node": "bayes:NVDA:PREDICTION:abc"},
        ),
        (
            "intervene.do",
            {
                "treatment_node": "bayes:MSFT:PREDICTION:def",
                "treatment_value": 0.25,
                "outcome_node": "bayes:NVDA:PREDICTION:abc",
            },
        ),
    ]


@pytest.mark.parametrize(
    ("argv", "command_name"),
    [
        (["auth-status"], "auth-status"),
        (["card"], "card"),
        (["methods"], "methods"),
        (["narrate", "--query", "Why is NVDA strong?"], "narrate"),
        (["query-node", "--query", "NVDA"], "query-node"),
        (["resolve-entity", "--query", "NVDA"], "resolve-entity"),
        (["explain-read-bundle", "--query", "NVDA"], "explain-read-bundle"),
        (["explain-outcome", "--query", "NVDA"], "explain-outcome"),
        (["observe-predict", "--target-node", "bayes:NVDA:PREDICTION:abc"], "observe-predict"),
        (
            [
                "intervene-do",
                "--treatment-node",
                "bayes:MSFT:PREDICTION:def",
                "--treatment-value",
                "0.1",
                "--outcome-node",
                "bayes:NVDA:PREDICTION:abc",
            ],
            "intervene-do",
        ),
        (["search-prepare", "--query", "AI datacenter demand"], "search-prepare"),
        (["predict", "--session-handle", "sess_1", "--node-ref", "bayes:NVDA:PREDICTION:abc"], "predict"),
        (
            [
                "what-if",
                "--session-handle",
                "sess_1",
                "--treatment-node-ref",
                "bayes:MSFT:PREDICTION:def",
                "--treatment-value",
                "0.1",
                "--outcome-node-ref",
                "bayes:NVDA:PREDICTION:abc",
            ],
            "what-if",
        ),
    ],
)
def test_parser_registers_supported_narrative_commands(
    argv: list[str], command_name: str
) -> None:
    narrative_cap_probe = _load_narrative_cap_probe_module()

    parser = narrative_cap_probe._build_parser()
    args = parser.parse_args(argv)

    assert command_name in narrative_cap_probe.COMMANDS
    assert args.command == command_name
