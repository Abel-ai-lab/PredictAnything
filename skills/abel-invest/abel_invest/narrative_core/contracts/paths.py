"""Path helpers for Abel strategy-discovery session artifacts."""

from __future__ import annotations

from pathlib import Path

from abel_invest.narrative_core.contracts.constants import (
    BRANCH_SPEC_FILENAME,
    BRANCH_STATE_FILENAME,
    CONTEXT_GUIDE_FILENAME,
    DATA_MANIFEST_FILENAME,
    DEPENDENCIES_FILENAME,
    EXECUTION_CONSTRAINTS_FILENAME,
    PROBE_SAMPLES_FILENAME,
    RUNTIME_PROFILE_FILENAME,
    SESSION_STATE_FILENAME,
)


def branch_spec_path(branch: Path) -> Path:
    return branch / BRANCH_SPEC_FILENAME


def dependencies_path(branch: Path) -> Path:
    return branch / "inputs" / DEPENDENCIES_FILENAME


def runtime_profile_path(branch: Path) -> Path:
    return branch / "inputs" / RUNTIME_PROFILE_FILENAME


def execution_constraints_path(branch: Path) -> Path:
    return branch / "inputs" / EXECUTION_CONSTRAINTS_FILENAME


def data_manifest_path(branch: Path) -> Path:
    return branch / "inputs" / DATA_MANIFEST_FILENAME


def context_guide_path(branch: Path) -> Path:
    return branch / "inputs" / CONTEXT_GUIDE_FILENAME


def probe_samples_path(branch: Path) -> Path:
    return branch / "inputs" / PROBE_SAMPLES_FILENAME


def branch_state_path(branch: Path) -> Path:
    return branch / BRANCH_STATE_FILENAME


def session_state_path(session: Path) -> Path:
    return session / SESSION_STATE_FILENAME
