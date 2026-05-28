"""Shared small helpers for promotion modules."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import sys
from typing import Any


def _date_part(value: str) -> str:
    if not value:
        return ""
    if "T" in value:
        return value.split("T", 1)[0]
    return value.split(" ", 1)[0]


def _load_smoke_strategy_class(path: Path):
    module_name = f"abel_paper_smoke_{hashlib.sha256(str(path).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import promoted strategy source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine_cls = getattr(module, "BranchEngine", None)
    if engine_cls is None:
        raise RuntimeError("promoted strategy source does not define BranchEngine")
    return engine_cls


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _snapshot_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        snapshot[path.relative_to(root).as_posix()] = _sha256_bytes(path.read_bytes())
    return snapshot


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_if_exists(source: Path, target: Path) -> None:
    if not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _is_branch_relative(source_path: Path, branch: Path) -> bool:
    try:
        source_path.resolve().relative_to(branch.resolve())
    except ValueError:
        return False
    return True


def _load_json_object_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@contextmanager
def _temporary_environ(env: dict[str, str]):
    original: dict[str, str | None] = {}
    for key, value in env.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _temporary_sys_path(paths: list[Path]):
    previous = list(sys.path)
    for path in reversed([str(item) for item in paths]):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        yield
    finally:
        sys.path[:] = previous


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _clean(value: Any) -> str:
    return str(value or "").strip()
