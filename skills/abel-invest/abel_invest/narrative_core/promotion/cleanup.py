"""Legacy promotion output cleanup helpers."""

from __future__ import annotations

from pathlib import Path
import shutil

from .constants import (
    PROMOTION_LEGACY_DESTINATION_DIRS,
    PROMOTION_LEGACY_PROMOTED_FILES,
)


def cleanup_legacy_promotion_outputs(destination: Path, promoted_dir: Path) -> None:
    for name in PROMOTION_LEGACY_PROMOTED_FILES:
        path = promoted_dir / name
        if path.is_file() or path.is_symlink():
            path.unlink()
    for name in PROMOTION_LEGACY_DESTINATION_DIRS:
        path = destination / name
        if path.is_dir():
            shutil.rmtree(path)
