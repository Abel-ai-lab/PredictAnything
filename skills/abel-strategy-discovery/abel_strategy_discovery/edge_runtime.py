"""Shared runtime probes for the installed Abel-edge environment."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from abel_strategy_discovery.workspace import load_workspace_manifest, resolve_workspace_paths


def common_python_root() -> Path:
    return Path(__file__).resolve().parents[2] / "abel-common" / "python"


def collection_auth_anchor() -> Path:
    return common_python_root().parent.parent / "abel-auth" / ".env.skill"


resolved_common_python_root = common_python_root()
if str(resolved_common_python_root) not in sys.path:
    sys.path.insert(0, str(resolved_common_python_root))

from abel_common.cap.auth import has_auth_token, resolve_auth_env_file


def resolve_runtime_auth_env_file(workspace_root: Path) -> Path | None:
    """Prefer workspace auth, then shared skill auth, then the workspace env file."""
    workspace_env = (workspace_root / ".env").resolve()
    if has_auth_token(workspace_env):
        return workspace_env
    shared_auth = resolve_auth_env_file(collection_auth_anchor())
    if shared_auth is not None:
        return shared_auth
    if workspace_env.exists():
        return workspace_env
    return None

def run_python_json(
    python_path: Path | str,
    cwd: Path,
    script: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Run an inline Python script and parse a JSON payload from stdout."""
    completed = subprocess.run(
        [str(python_path), "-c", script],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=None if env is None else dict(env),
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "error": completed.stderr.strip() or completed.stdout.strip() or "command failed",
        }
    payload = completed.stdout.strip()
    if not payload:
        return {"ok": False, "error": "no output"}
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON output: {exc}", "stdout": payload}


def probe_causal_edge_import(python_path: Path | str, cwd: Path) -> dict[str, object]:
    """Probe whether the workspace runtime can import causal_edge."""
    return run_python_json(
        python_path,
        cwd,
        """
import json
try:
    import causal_edge  # noqa: F401
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
else:
    print(json.dumps({"ok": True}))
""",
    )


def probe_causal_edge_cli(python_path: Path | str, cwd: Path) -> dict[str, object]:
    """Probe whether the causal-edge CLI entrypoint works in the runtime."""
    return run_python_json(
        python_path,
        cwd,
        """
import json
import subprocess
import sys

completed = subprocess.run(
    [sys.executable, "-m", "causal_edge.cli", "version"],
    capture_output=True,
    text=True,
)
print(json.dumps({
    "ok": completed.returncode == 0,
    "stdout": completed.stdout.strip(),
    "stderr": completed.stderr.strip(),
}))
""",
    )


def probe_edge_discovery_payload(python_path: Path | str, cwd: Path) -> bool | None:
    """Probe whether the installed edge runtime exposes structured discovery payloads."""
    completed = subprocess.run(
        [
            str(python_path),
            "-c",
            (
                "import inspect\n"
                "from causal_edge.plugins.abel.discover import discover_graph_payload\n"
                "print(callable(discover_graph_payload))\n"
            ),
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() == "True"


def probe_edge_context_json(python_path: Path | str, cwd: Path) -> bool | None:
    """Probe whether the installed edge runtime supports ``context_json``."""
    completed = subprocess.run(
        [
            str(python_path),
            "-c",
            (
                "import inspect\n"
                "from causal_edge.research.evaluate import run_evaluation\n"
                "print('context_json' in inspect.signature(run_evaluation).parameters)\n"
            ),
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() == "True"


def build_workspace_runtime_env(
    workspace_root: Path,
    *,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a deterministic runtime environment for Abel-edge subprocesses."""
    env = dict(os.environ if base is None else base)
    auth_env = resolve_runtime_auth_env_file(workspace_root)
    if not env.get("ABEL_AUTH_ENV_FILE") and auth_env is not None:
        env["ABEL_AUTH_ENV_FILE"] = str(auth_env)
    manifest = load_workspace_manifest(workspace_root)
    cache_root = resolve_workspace_paths(workspace_root, manifest)["cache_root"].resolve()
    env.setdefault("CAUSAL_EDGE_CACHE_ROOT", str(cache_root))
    return env


def probe_abel_auth(python_path: Path | str, cwd: Path) -> dict[str, object]:
    """Probe whether Abel auth is available to the installed runtime."""
    runtime_env = build_workspace_runtime_env(cwd, base={})
    auth_env_file = runtime_env.get("ABEL_AUTH_ENV_FILE")
    if auth_env_file and has_auth_token(auth_env_file):
        auth_path = Path(auth_env_file).expanduser().resolve()
        source = "workspace_env" if auth_path == (cwd / ".env").resolve() else "shared_auth_file"
        return {
            "ok": True,
            "source": source,
            "path": str(auth_path),
        }

    return run_python_json(
        python_path,
        cwd,
        """
import json
import os
from pathlib import Path

from causal_edge.plugins.abel.credentials import (
    _candidate_shared_auth_files,
    _read_env_file,
    normalize_api_key,
)

env_path = Path(".env").resolve()
env_values = _read_env_file(env_path)

env_token = normalize_api_key(
    os.getenv("ABEL_API_KEY")
    or os.getenv("CAP_API_KEY")
)
if env_token:
    print(json.dumps({
        "ok": True,
        "source": "env_var",
        "path": None,
    }))
    raise SystemExit(0)

project_token = normalize_api_key(
    env_values.get("ABEL_API_KEY")
    or env_values.get("CAP_API_KEY")
)
if project_token:
    print(json.dumps({
        "ok": True,
        "source": "workspace_env",
        "path": str(env_path),
    }))
    raise SystemExit(0)

for candidate in _candidate_shared_auth_files(env_path=env_path):
    candidate_values = _read_env_file(candidate)
    shared_token = normalize_api_key(
        candidate_values.get("ABEL_API_KEY") or candidate_values.get("CAP_API_KEY")
    )
    if shared_token:
        print(json.dumps({
            "ok": True,
            "source": "shared_auth_file",
            "path": str(candidate),
        }))
        raise SystemExit(0)

print(json.dumps({
    "ok": False,
    "source": "missing",
    "path": None,
}))
        """,
        env=runtime_env,
    )
