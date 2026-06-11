import importlib.util
import json
import sys
import urllib.error
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_API_PATH = (
    REPO_ROOT / "skills" / "abel-common" / "python" / "abel_common" / "data_api.py"
)


def _load_data_api_module():
    spec = importlib.util.spec_from_file_location("abel_common_data_api", DATA_API_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_base_url_defaults_to_prod():
    data_api = _load_data_api_module()

    assert data_api._resolve_base_url("", "") == "https://cap.abel.ai/data-infra"


def test_resolve_base_url_supports_sit():
    data_api = _load_data_api_module()

    assert data_api._resolve_base_url("", "sit") == "https://cap-sit.abel.ai/data-infra"


def test_target_env_overrides_env_base_url(monkeypatch):
    data_api = _load_data_api_module()
    monkeypatch.setenv("ABEL_DATA_API_BASE_URL", "https://custom.example/data-infra")

    assert data_api._resolve_base_url("", "sit") == "https://cap-sit.abel.ai/data-infra"


def test_resolve_headers_uses_authorization_only(monkeypatch):
    data_api = _load_data_api_module()
    monkeypatch.setenv("ABEL_API_KEY", "test-key")
    monkeypatch.delenv("CAP_API_KEY", raising=False)

    headers = data_api._resolve_headers(None)

    assert headers["Authorization"] == "Bearer test-key"
    assert "api-key" not in headers
    assert "user-tier" not in headers
    assert "fee-level" not in headers


def test_load_env_file_continues_to_shared_auth_when_local_file_has_no_token(
    monkeypatch,
    tmp_path,
):
    data_api = _load_data_api_module()
    skill_env = tmp_path / "skills" / "abel-ask" / ".env.skill"
    auth_env = tmp_path / "skills" / "abel-auth" / ".env.skill"
    skill_env.parent.mkdir(parents=True)
    auth_env.parent.mkdir(parents=True)
    skill_env.write_text("OTHER=value\n", encoding="utf-8")
    auth_env.write_text("ABEL_API_KEY=shared-token\n", encoding="utf-8")
    monkeypatch.delenv("ABEL_API_KEY", raising=False)
    monkeypatch.delenv("CAP_API_KEY", raising=False)

    data_api._load_env_file(str(skill_env))

    assert data_api._resolve_headers(None)["Authorization"] == "Bearer shared-token"


def test_catalog_builds_gateway_url_and_query(monkeypatch):
    data_api = _load_data_api_module()
    seen = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"code": 0, "data": []}).encode()

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(data_api.urllib.request, "urlopen", fake_urlopen)
    parser = data_api._build_parser()
    args = parser.parse_args(
        data_api._normalize_argv(
            [
                "--api-key",
                "abc",
                "--target-env",
                "sit",
                "catalog",
                "--domain",
                "market",
                "--q",
                "price",
            ]
        )
    )

    result = data_api._cmd_catalog(args)

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert seen["url"] == (
        "https://cap-sit.abel.ai/data-infra/api/data-tasks?domain=market&q=price"
    )
    assert seen["headers"]["Authorization"] == "Bearer abc"


def test_schema_escapes_dataset_name(monkeypatch):
    data_api = _load_data_api_module()
    seen = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"code":0,"data":{"columns":[]}}'

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        return FakeResponse()

    monkeypatch.setattr(data_api.urllib.request, "urlopen", fake_urlopen)
    parser = data_api._build_parser()
    args = parser.parse_args(["--api-key", "abc", "schema", "market.historical/day"])

    data_api._cmd_schema(args)

    assert seen["url"] == (
        "https://cap.abel.ai/data-infra/api/data-tasks/"
        "market.historical%2Fday/schema"
    )


def test_records_merges_standard_and_extra_params(monkeypatch):
    data_api = _load_data_api_module()
    seen = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"code":0,"data":{"records":[]}}'

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        return FakeResponse()

    monkeypatch.setattr(data_api.urllib.request, "urlopen", fake_urlopen)
    parser = data_api._build_parser()
    args = parser.parse_args(
        data_api._normalize_argv(
            [
                "records",
                "market.price.daily",
                "--start-date",
                "2025-01-01",
                "--end-date",
                "2025-01-31",
                "--limit",
                "100",
                "--param",
                "symbol=AAPL",
            ]
        )
    )

    data_api._cmd_records(args)

    assert seen["url"] == (
        "https://cap.abel.ai/data-infra/api/data-tasks/"
        "market.price.daily/records?"
        "symbol=AAPL&startDate=2025-01-01&endDate=2025-01-31&limit=100"
    )


def test_http_error_returns_failure_payload(monkeypatch):
    data_api = _load_data_api_module()

    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url,
            403,
            "Forbidden",
            {},
            None,
        )

    monkeypatch.setattr(data_api.urllib.request, "urlopen", fake_urlopen)

    result = data_api._get_json(
        "https://cap.abel.ai/data-infra",
        "/api/data-tasks",
        {},
    )

    assert result["ok"] is False
    assert result["status_code"] == 403
