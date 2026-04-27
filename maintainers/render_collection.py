#!/usr/bin/env python3
"""Render the full Abel skills collection from maintainer sources."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from profile_config import get_template_values

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "maintainers" / "skills"
DEFAULT_SOURCE_DIR = REPO_ROOT / "skills"
IGNORE_NAMES = {
    "__pycache__",
    ".env.skill",
    ".env.skill.example",
    ".env.skills",
    ".env.skills.example",
}
LOCAL_AUTH_BASENAMES = (
    ".env.skill",
    ".env.skills",
)


def _replace(text: str, pattern: str, replacement: str, *, count: int = 0) -> str:
    updated, matched = re.subn(
        pattern, replacement, text, count=count, flags=re.MULTILINE
    )
    if matched == 0:
        raise RuntimeError(f"Pattern not found: {pattern}")
    return updated


def _replace_if_present(
    text: str, pattern: str, replacement: str, *, count: int = 0
) -> str:
    updated, matched = re.subn(
        pattern, replacement, text, count=count, flags=re.MULTILINE
    )
    if matched == 0:
        return text
    return updated


def _ignore_copy_patterns(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORE_NAMES or name.endswith(".pyc")}


def _snapshot_local_auth_files(output_dir: Path) -> dict[Path, str]:
    snapshot: dict[Path, str] = {}
    if not output_dir.exists():
        return snapshot
    for skill_root in output_dir.iterdir():
        if not skill_root.is_dir():
            continue
        for basename in LOCAL_AUTH_BASENAMES:
            path = skill_root / basename
            if path.exists():
                snapshot[path.relative_to(output_dir)] = path.read_text(
                    encoding="utf-8"
                )
    return snapshot


def _restore_local_auth_files(output_dir: Path, snapshot: dict[Path, str]) -> None:
    for relative_path, content in snapshot.items():
        restored_path = output_dir / relative_path
        restored_path.parent.mkdir(parents=True, exist_ok=True)
        restored_path.write_text(content, encoding="utf-8")


def _copy_source_tree(source_dir: Path, output_dir: Path) -> None:
    auth_snapshot = _snapshot_local_auth_files(output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, output_dir, ignore=_ignore_copy_patterns)
    _restore_local_auth_files(output_dir, auth_snapshot)


def _current_profile_note_lines(
    values: dict[str, str],
    *,
    current_line: str,
    profile_key_suffix: str,
) -> list[str]:
    notes = [current_line]
    active_prefix = values["ACTIVE_PROFILE"].upper()
    active_line = values.get(f"{active_prefix}_{profile_key_suffix}")
    if active_line:
        notes.append(active_line)
    return notes


def render_abel_ask(skill_root: Path, values: dict[str, str]) -> None:
    path = skill_root / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    text = _replace_if_present(
        text,
        r"^- Default CAP target: `[^`]+`\.$",
        f"- Default CAP target: `{values['ACTIVE_CAP_BASE_URL']}`.",
    )
    text = _replace_if_present(
        text,
        r"^- Treat `[^`]+` as the OAuth and business API host, not the CAP probe host\.$",
        f"- Treat `{values['ACTIVE_OAUTH_BASE_URL']}` as the OAuth and business API host, not the CAP probe host.",
    )
    path.write_text(text, encoding="utf-8")

    path = skill_root / "references" / "probe-usage.md"
    text = path.read_text(encoding="utf-8")
    text = _replace(
        text,
        r'^BASE_URL="[^"]+"$',
        f'BASE_URL="{values["ACTIVE_CAP_BASE_URL"]}"',
    )
    endpoint_notes = [
        "## Endpoint Notes",
        "",
        *_current_profile_note_lines(
            values,
            current_line=(
                f"- The current default CAP surface answers on "
                f"`{values['ACTIVE_CAP_ENDPOINT_URL']}`."
            ),
            profile_key_suffix="CAP_ENDPOINT_URL",
        ),
    ]
    endpoint_notes.append(
        f"- The probe accepts base URLs such as `{values['ACTIVE_CAP_BASE_URL']}` and resolves them to `/cap`."
    )
    endpoint_notes.append(
        f"- `{values['ACTIVE_OAUTH_BASE_URL']}` is used for Abel OAuth and business API flows owned by `abel-auth`; it is not the default CAP probe base."
    )
    text = _replace(
        text,
        r"## Endpoint Notes\n\n(?:.*\n)*?(?=\n## |\Z)",
        "\n".join(endpoint_notes) + "\n",
    )
    path.write_text(text, encoding="utf-8")

    path = skill_root / "references" / "narrative-probe-usage.md"
    text = path.read_text(encoding="utf-8")
    narrative_base_url = values.get(
        "ACTIVE_NARRATIVE_CAP_BASE_URL", "https://cap.abel.ai/narrative"
    )
    narrative_endpoint_url = values.get(
        "ACTIVE_NARRATIVE_CAP_ENDPOINT_URL",
        f"{narrative_base_url.rstrip('/')}/cap",
    )
    text = _replace(
        text,
        r'^BASE_URL="[^"]+"$',
        f'BASE_URL="{narrative_base_url}"',
    )
    text = _replace(
        text,
        r"^The script accepts a narrative base URL such as `[^`]+` and resolves it to `POST [^`]+` plus `GET [^`]+`\.$",
        (
            f"The script accepts a narrative base URL such as `{narrative_base_url}` "
            "and resolves it to `POST /narrative/cap` plus `GET /.well-known/cap.json`."
        ),
    )
    endpoint_notes = [
        "## Endpoint Notes",
        "",
        *_current_profile_note_lines(
            values,
            current_line=(
                f"- The current default narrative CAP surface answers on "
                f"`{narrative_endpoint_url}`."
            ),
            profile_key_suffix="NARRATIVE_CAP_ENDPOINT_URL",
        ),
    ]
    endpoint_notes.append(
        f"- The probe accepts base URLs such as `{narrative_base_url}` and resolves them to `/cap`."
    )
    text = _replace(
        text,
        r"## Endpoint Notes\n\n(?:.*\n)*?(?=\n## |\Z)",
        "\n".join(endpoint_notes) + "\n",
    )
    path.write_text(text, encoding="utf-8")

    path = skill_root / "scripts" / "cap_probe.py"
    text = path.read_text(encoding="utf-8")
    text = _replace(
        text,
        r'^DEFAULT_BASE_URL = "[^"]+"$',
        f'DEFAULT_BASE_URL = "{values["ACTIVE_CAP_BASE_URL"]}"',
    )
    path.write_text(text, encoding="utf-8")

    path = skill_root / "scripts" / "narrative_cap_probe.py"
    text = path.read_text(encoding="utf-8")
    default_base_url = values.get("ACTIVE_NARRATIVE_CAP_BASE_URL", "")
    text = _replace(
        text,
        r'^DEFAULT_BASE_URL = "[^"]*"$',
        f'DEFAULT_BASE_URL = "{default_base_url}"',
    )
    path.write_text(text, encoding="utf-8")


def _profile_replacements(values: dict[str, str]) -> dict[str, str]:
    prod_values = get_template_values(profile_name="prod")
    replacements = {
        prod_values["ACTIVE_CAP_BASE_URL"]: values["ACTIVE_CAP_BASE_URL"],
        prod_values["ACTIVE_CAP_ENDPOINT_URL"]: values["ACTIVE_CAP_ENDPOINT_URL"],
        prod_values["ACTIVE_OAUTH_BASE_URL"]: values["ACTIVE_OAUTH_BASE_URL"],
        prod_values["ACTIVE_AUTHORIZE_AGENT_URL"]: values["ACTIVE_AUTHORIZE_AGENT_URL"],
        prod_values["ACTIVE_RESULT_URL_TEMPLATE"]: values["ACTIVE_RESULT_URL_TEMPLATE"],
        prod_values["ACTIVE_CALLBACK_URL"]: values["ACTIVE_CALLBACK_URL"],
        prod_values["ACTIVE_CALLBACK_EXAMPLE_URL"]: values["ACTIVE_CALLBACK_EXAMPLE_URL"],
    }
    prod_narrative_base = prod_values.get("ACTIVE_NARRATIVE_CAP_BASE_URL")
    active_narrative_base = values.get("ACTIVE_NARRATIVE_CAP_BASE_URL")
    if prod_narrative_base and active_narrative_base:
        replacements[prod_narrative_base] = active_narrative_base
    prod_narrative_endpoint = prod_values.get("ACTIVE_NARRATIVE_CAP_ENDPOINT_URL")
    active_narrative_endpoint = values.get("ACTIVE_NARRATIVE_CAP_ENDPOINT_URL")
    if prod_narrative_endpoint and active_narrative_endpoint:
        replacements[prod_narrative_endpoint] = active_narrative_endpoint
    return {
        source: target
        for source, target in replacements.items()
        if source != target
    }


def _apply_profile_replacements(output_dir: Path, values: dict[str, str]) -> None:
    replacements = _profile_replacements(values)
    if not replacements:
        return
    ordered = sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = text
        for source, target in ordered:
            updated = updated.replace(source, target)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def _render_profile_aware_skills(output_dir: Path, values: dict[str, str]) -> None:
    abel_ask_root = output_dir / "abel-ask"
    if abel_ask_root.exists():
        render_abel_ask(abel_ask_root, values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render the full Abel skills collection with a selected profile."
    )
    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help="Maintainer-owned source collection directory to render from.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output collection directory. Defaults to the public rendered skills root.",
    )
    parser.add_argument(
        "--profile",
        default="",
        help="Endpoint profile name to render. Defaults to active_profile.",
    )
    parser.add_argument(
        "--include-local",
        action="store_true",
        help="Allow maintainer-local endpoint overrides when resolving the profile.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    profile_name = args.profile.strip() or None

    if not source_dir.exists():
        raise SystemExit(f"Source collection directory not found: {source_dir}")

    values = get_template_values(
        include_local=args.include_local,
        profile_name=profile_name,
    )

    if output_dir != source_dir:
        _copy_source_tree(source_dir, output_dir)
    _render_profile_aware_skills(output_dir, values)
    _apply_profile_replacements(output_dir, values)

    print(f"Rendered profile `{values['ACTIVE_PROFILE']}` into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
