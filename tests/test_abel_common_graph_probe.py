from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PROBE_PATH = (
    REPO_ROOT
    / "skills"
    / "abel-common"
    / "python"
    / "abel_common"
    / "cap"
    / "graph_probe.py"
)


def _load_graph_probe_module():
    spec = importlib.util.spec_from_file_location(
        "abel_common_graph_probe",
        GRAPH_PROBE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paths_command_preserves_macro_canonical_node_ids(monkeypatch) -> None:
    graph_probe = _load_graph_probe_module()

    captured: dict[str, object] = {}

    def _fake_call_verb(args, verb: str, params: dict[str, object] | None = None) -> dict[str, object]:
        captured["verb"] = verb
        captured["params"] = params or {}
        return {"ok": True}

    monkeypatch.setattr(graph_probe, "_call_verb", _fake_call_verb)

    args = argparse.Namespace(
        source_node_id="CPI",
        target_node_id="NVDA.price",
        max_paths=3,
        include_edge_signs=False,
        default_suffix="price",
    )

    result = graph_probe._cmd_paths(args)

    assert result == {"ok": True}
    assert captured["verb"] == "graph.paths"
    assert captured["params"] == {
        "source_node_id": "CPI",
        "target_node_id": "NVDA.price",
        "max_paths": 3,
    }


def test_paths_command_accepts_lowercase_macro_alias_as_canonical(monkeypatch) -> None:
    graph_probe = _load_graph_probe_module()

    captured: dict[str, object] = {}

    def _fake_call_verb(args, verb: str, params: dict[str, object] | None = None) -> dict[str, object]:
        captured["params"] = params or {}
        return {"ok": True}

    monkeypatch.setattr(graph_probe, "_call_verb", _fake_call_verb)

    args = argparse.Namespace(
        source_node_id="cpi",
        target_node_id="treasuryrateyear10",
        max_paths=2,
        include_edge_signs=False,
        default_suffix="price",
    )

    graph_probe._cmd_paths(args)

    assert captured["params"] == {
        "source_node_id": "CPI",
        "target_node_id": "treasuryRateYear10",
        "max_paths": 2,
    }


def test_paths_command_keeps_asset_normalization_for_tickers(monkeypatch) -> None:
    graph_probe = _load_graph_probe_module()

    captured: dict[str, object] = {}

    def _fake_call_verb(args, verb: str, params: dict[str, object] | None = None) -> dict[str, object]:
        captured["params"] = params or {}
        return {"ok": True}

    monkeypatch.setattr(graph_probe, "_call_verb", _fake_call_verb)

    args = argparse.Namespace(
        source_node_id="NVDA",
        target_node_id="AMD",
        max_paths=4,
        include_edge_signs=True,
        default_suffix="price",
    )

    graph_probe._cmd_paths(args)

    assert captured["params"] == {
        "source_node_id": "NVDA.price",
        "target_node_id": "AMD.price",
        "max_paths": 4,
        "include_edge_signs": True,
    }


def test_validate_connectivity_shortcut_is_not_registered() -> None:
    graph_probe = _load_graph_probe_module()

    assert "validate-connectivity" not in graph_probe.COMMANDS
    assert not hasattr(graph_probe, "_cmd_validate_connectivity")

    parser = graph_probe._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["validate-connectivity", "CPI", "NVDA"])


def test_resolve_cap_endpoint_uses_cap_suffix_for_router_and_echo_bases() -> None:
    graph_probe = _load_graph_probe_module()

    assert (
        graph_probe.resolve_cap_endpoint("https://api.abel.ai/router")
        == "https://api.abel.ai/router/cap"
    )
    assert (
        graph_probe.resolve_cap_endpoint("https://api.abel.ai/echo")
        == "https://api.abel.ai/echo/cap"
    )


@pytest.mark.parametrize(
    ("argv", "command_name", "handler_name"),
    [
        (["graph.neighbors", "NVDA", "--scope", "children"], "graph.neighbors", "_cmd_neighbors"),
        (["graph.paths", "NVDA", "AMD"], "graph.paths", "_cmd_paths"),
        (["graph.markov_blanket", "NVDA"], "graph.markov_blanket", "_cmd_markov_blanket"),
    ],
)
def test_graph_command_aliases_dispatch_to_existing_handlers(
    argv: list[str], command_name: str, handler_name: str
) -> None:
    graph_probe = _load_graph_probe_module()

    parser = graph_probe._build_parser()
    args = parser.parse_args(graph_probe._normalize_argv(argv))

    assert command_name in graph_probe.COMMANDS
    assert args.command == command_name
    assert args.func is getattr(graph_probe, handler_name)


def test_normalize_node_command_preserves_macro_canonical_node_id() -> None:
    graph_probe = _load_graph_probe_module()

    args = argparse.Namespace(
        input_value="CPI",
        default_suffix="price",
    )

    result = graph_probe._cmd_normalize_node(args)

    assert result == {
        "ok": True,
        "status_code": 0,
        "input": "CPI",
        "normalized_node_id": "CPI",
        "default_suffix": "price",
    }


def test_normalize_node_command_accepts_lowercase_macro_alias() -> None:
    graph_probe = _load_graph_probe_module()

    args = argparse.Namespace(
        input_value="cpi",
        default_suffix="price",
    )

    result = graph_probe._cmd_normalize_node(args)

    assert result == {
        "ok": True,
        "status_code": 0,
        "input": "cpi",
        "normalized_node_id": "CPI",
        "default_suffix": "price",
    }


def test_load_env_file_falls_back_to_dot_env_when_skill_env_missing(
    monkeypatch, tmp_path
) -> None:
    graph_probe = _load_graph_probe_module()

    monkeypatch.delenv("ABEL_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)

    env_path = tmp_path / ".env"
    env_path.write_text("ABEL_API_KEY=abel-from-dot-env\n", encoding="utf-8")

    graph_probe._load_env_file(str(tmp_path / ".env.skill"))

    assert os.getenv("ABEL_API_KEY") == "abel-from-dot-env"


def test_load_env_file_prefers_skill_env_over_dot_env(monkeypatch, tmp_path) -> None:
    graph_probe = _load_graph_probe_module()

    monkeypatch.delenv("ABEL_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)

    (tmp_path / ".env.skill").write_text(
        "ABEL_API_KEY=abel-from-dot-env-skill\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("ABEL_API_KEY=abel-from-dot-env\n", encoding="utf-8")

    graph_probe._load_env_file(str(tmp_path / ".env.skill"))

    assert os.getenv("ABEL_API_KEY") == "abel-from-dot-env-skill"


def test_load_env_file_falls_back_to_collection_auth_file(monkeypatch, tmp_path) -> None:
    graph_probe = _load_graph_probe_module()

    monkeypatch.delenv("ABEL_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)

    skill_root = tmp_path / "skills" / "abel-ask"
    skill_root.mkdir(parents=True)
    auth_root = tmp_path / "skills" / "abel-auth"
    auth_root.mkdir(parents=True)
    (auth_root / ".env.skill").write_text(
        "ABEL_API_KEY=abel-from-collection-auth\n",
        encoding="utf-8",
    )

    graph_probe._load_env_file(str(skill_root / ".env.skill"))

    assert os.getenv("ABEL_API_KEY") == "abel-from-collection-auth"


def test_auth_status_reports_skill_env_source(monkeypatch, tmp_path) -> None:
    graph_probe = _load_graph_probe_module()

    monkeypatch.delenv("ABEL_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)

    env_file = tmp_path / ".env.skill"
    env_file.write_text("ABEL_API_KEY=abel-from-dot-env-skill\n", encoding="utf-8")

    args = argparse.Namespace(
        api_key="",
        env_file=str(env_file),
    )

    result = graph_probe._cmd_auth_status(args)

    assert result == {
        "ok": True,
        "status_code": 0,
        "auth_ready": True,
        "auth_source": ".env.skill",
        "oauth_required": False,
    }


def test_auth_status_reports_collection_auth_source(monkeypatch, tmp_path) -> None:
    graph_probe = _load_graph_probe_module()

    monkeypatch.delenv("ABEL_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)

    skill_root = tmp_path / "skills" / "abel-ask"
    skill_root.mkdir(parents=True)
    auth_root = tmp_path / "skills" / "abel-auth"
    auth_root.mkdir(parents=True)
    (auth_root / ".env.skill").write_text(
        "ABEL_API_KEY=abel-from-collection-auth\n",
        encoding="utf-8",
    )

    args = argparse.Namespace(
        api_key="",
        env_file=str(skill_root / ".env.skill"),
    )

    result = graph_probe._cmd_auth_status(args)

    assert result == {
        "ok": True,
        "status_code": 0,
        "auth_ready": True,
        "auth_source": ".env.skill",
        "oauth_required": False,
    }


def test_auth_status_reports_missing_and_requires_oauth(monkeypatch, tmp_path) -> None:
    graph_probe = _load_graph_probe_module()

    monkeypatch.delenv("ABEL_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)

    args = argparse.Namespace(
        api_key="",
        env_file=str(tmp_path / ".env.skill"),
    )

    result = graph_probe._cmd_auth_status(args)

    assert result == {
        "ok": True,
        "status_code": 0,
        "auth_ready": False,
        "auth_source": "missing",
        "oauth_required": True,
    }


def test_build_payload_includes_default_v3_graph_context_for_non_meta_verbs() -> None:
    graph_probe = _load_graph_probe_module()

    payload = graph_probe._build_payload(
        "observe.predict",
        {"target_node": "BTCUSD.volume"},
    )

    assert payload["context"] == {
        "graph_ref": {
            "graph_id": "abel-main",
            "graph_version": "CausalNodeV3",
        }
    }


def test_build_payload_omits_default_graph_context_for_meta_verbs() -> None:
    graph_probe = _load_graph_probe_module()

    payload = graph_probe._build_payload("meta.capabilities")

    assert "context" not in payload


def test_build_payload_merges_context_json_with_default_graph_context() -> None:
    graph_probe = _load_graph_probe_module()

    payload = graph_probe._build_payload(
        "graph.paths",
        {"source_node_id": "CPI", "target_node_id": "NVDA.price"},
        context={"trace": {"source": "pytest"}},
    )

    assert payload["context"] == {
        "trace": {"source": "pytest"},
        "graph_ref": {
            "graph_id": "abel-main",
            "graph_version": "CausalNodeV3",
        },
    }


def test_build_payload_respects_explicit_graph_version_override() -> None:
    graph_probe = _load_graph_probe_module()

    payload = graph_probe._build_payload(
        "observe.predict",
        {"target_node": "BTCUSD.volume"},
        graph_version="CausalNodeV2",
    )

    assert payload["context"] == {
        "graph_ref": {
            "graph_id": "abel-main",
            "graph_version": "CausalNodeV2",
        }
    }


def test_build_payload_rejects_conflicting_graph_version_between_flag_and_context() -> None:
    graph_probe = _load_graph_probe_module()

    with pytest.raises(ValueError, match="Conflicting graph_version values"):
        graph_probe._build_payload(
            "observe.predict",
            {"target_node": "BTCUSD.volume"},
            graph_version="CausalNodeV2",
            context={"graph_ref": {"graph_version": "CausalNodeV3"}},
        )


def test_parser_accepts_global_graph_version_after_command() -> None:
    graph_probe = _load_graph_probe_module()

    parser = graph_probe._build_parser()
    args = parser.parse_args(
        graph_probe._normalize_argv(
            ["observe", "BTCUSD.volume", "--graph-version", "CausalNodeV2"]
        )
    )

    assert args.command == "observe"
    assert args.graph_version == "CausalNodeV2"


def test_parser_accepts_global_context_json_after_command() -> None:
    graph_probe = _load_graph_probe_module()

    parser = graph_probe._build_parser()
    args = parser.parse_args(
        graph_probe._normalize_argv(
            [
                "verb",
                "observe.predict",
                "--params-json",
                '{"target_node":"BTCUSD.volume"}',
                "--context-json",
                '{"trace":{"source":"pytest"}}',
            ]
        )
    )

    assert args.command == "verb"
    assert args.context_json == '{"trace":{"source":"pytest"}}'


@pytest.mark.parametrize("argv", [["observe", "--help"], ["paths", "--help"]])
def test_common_subcommand_help_mentions_global_envelope_flags(
    monkeypatch, capsys, argv: list[str]
) -> None:
    graph_probe = _load_graph_probe_module()

    monkeypatch.setattr(sys, "argv", ["graph_probe.py", *argv])

    with pytest.raises(SystemExit) as exc_info:
        graph_probe.main()

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "--graph-version" in help_text
    assert "--context-json" in help_text


def test_main_appends_v2_retry_hint_for_v3_prediction_unavailable(
    monkeypatch, capsys
) -> None:
    graph_probe = _load_graph_probe_module()

    def _fake_observe(args):
        return {
            "ok": False,
            "status_code": 400,
            "verb": "observe.predict",
            "message": "Prediction is temporarily unavailable for this node.",
            "error": {
                "code": "invalid_request",
                "message": "Prediction is temporarily unavailable for this node.",
                "details": {
                    "reason": "prediction_temporarily_unavailable",
                    "target_node": "NVDA.price",
                    "graph_version": "CausalNodeV3",
                },
            },
            "response_payload": {},
        }

    monkeypatch.setattr(graph_probe, "_cmd_observe", _fake_observe)
    monkeypatch.setattr(sys, "argv", ["graph_probe.py", "observe", "NVDA.price"])

    exit_code = graph_probe.main()

    assert exit_code == 1
    payload = capsys.readouterr().out
    assert "Prediction is temporarily unavailable for this node." in payload
    assert "--graph-version CausalNodeV2" in payload


def test_retry_hint_uses_response_payload_verb_when_top_level_verb_missing() -> None:
    graph_probe = _load_graph_probe_module()

    enriched = graph_probe._maybe_add_graph_version_retry_hint(
        {
            "ok": False,
            "status_code": 400,
            "message": "Prediction is temporarily unavailable for this node.",
            "error": {
                "code": "invalid_request",
                "message": "Prediction is temporarily unavailable for this node.",
                "details": {
                    "reason": "prediction_temporarily_unavailable",
                    "target_node": "NVDA.price",
                    "graph_version": "CausalNodeV3",
                },
            },
            "response_payload": {
                "verb": "observe.predict",
            },
        }
    )

    assert "--graph-version CausalNodeV2" in enriched["hint"]
