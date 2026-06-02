#!/usr/bin/env python3
"""Assemble a ClawHub-ready release artifact from the main Abel entry skill."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


SKILL_NAME = "abel"
SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"
SOURCE_ROOT = SKILLS_ROOT / SKILL_NAME
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "dist" / "clawhub"
RELEASE_SKILL_NAMES = ("abel", "abel-auth", "abel-ask", "abel-invest", "abel-common")
OPENCLAW_MANIFEST_SKILL_NAMES = ("abel", "abel-auth", "abel-ask", "abel-invest")
REMOVE_FRONTMATTER_KEYS = {
    "update_repo",
    "update_branch",
    "update_skill_path",
    "update_changelog_path",
}

OPENCLAW_API_KEY_PATH = "skills.entries.abel.apiKey"
LEGACY_OPENCLAW_API_KEY_PATH = "skills.entries.causal-abel.apiKey"

NEW_INSTALL_SECTION = f"""## Install And Authorization

If the user installs Abel, asks to connect Abel, or the workflow is missing live Abel access, use `abel-auth`.

- Reuse existing auth if available.
- If auth is missing or invalid, hand off to `abel-auth`.
- In OpenClaw, persist the resulting Abel API key to `{OPENCLAW_API_KEY_PATH}` so OpenClaw can inject `ABEL_API_KEY` for Abel skills.
- The bundled probes also recognize legacy `{LEGACY_OPENCLAW_API_KEY_PATH}` for older OpenClaw installs.
- Use `.env.skill` only for direct local script usage outside OpenClaw config management.
- Do not continue to live Abel work until auth is ready.
"""

CLAWHUB_OPENAI_YAML = """interface:
  display_name: "Abel Strategy Research Skills"
  short_description: "AI agent skills for strategy discovery with Abel: explore market ideas, analyze causal drivers, and develop investment strategies."
  default_prompt: "Use $abel to route this request to the right Abel skill."
"""

OPENCLAW_PLUGIN_MANIFEST = {
    "id": "abel",
    "name": "Abel Strategy Research Skills",
    "description": (
        "AI agent skills for strategy discovery with Abel: explore market ideas, "
        "analyze causal drivers, and develop investment strategies."
    ),
    "skills": [f"./skills/{skill_name}" for skill_name in OPENCLAW_MANIFEST_SKILL_NAMES],
    "configSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    },
}

PACKAGE_JSON_BASE = {
    "name": "abel",
    "description": (
        "Abel Strategy Research Skills package for OpenClaw with routing, auth, "
        "strategy discovery, and causal-driver analysis."
    ),
    "type": "module",
    "private": False,
    "openclaw": {
        "extensions": ["./index.js"],
        "compat": {
            "pluginApi": ">=2026.3.24-beta.2",
        },
        "build": {
            "openclawVersion": "2026.4.2",
        },
    },
}

OPENCLAW_EXTENSION_ENTRY = """import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

export default definePluginEntry({
  id: "abel",
  name: "Abel Strategy Research Skills",
  description: "Plugin-shipped Abel strategy research skills bundle.",
  register(_api) {},
});
"""


def ignore_copy_patterns(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if (
            name == "__pycache__"
            or name.endswith(".pyc")
            or name.endswith(".egg-info")
            or name
            in {
                ".env.skill",
                ".env.skill.example",
                ".env.skills",
                ".env.skills.example",
                ".pytest_cache",
                "build",
                "dist",
            }
        ):
            ignored.add(name)
    return ignored


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a ClawHub-ready release artifact for the main Abel skill."
    )
    parser.add_argument(
        "--source",
        default=str(SOURCE_ROOT),
        help="Path to the source skill directory.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Directory that will contain the built skill folder.",
    )
    parser.add_argument(
        "--version",
        default="",
        help="Optional version override written into the built SKILL.md.",
    )
    return parser.parse_args()


def split_frontmatter(text: str) -> tuple[list[str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md is missing YAML frontmatter.")

    frontmatter: list[str] = []
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
        frontmatter.append(line)

    if end_index is None:
        raise ValueError("SKILL.md frontmatter is not terminated.")

    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    return frontmatter, body


def build_frontmatter(lines: list[str], version_override: str) -> str:
    out: list[str] = []
    version_written = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if not line[0].isspace() and ":" in line:
            key = line.split(":", 1)[0].strip()
            if key in REMOVE_FRONTMATTER_KEYS:
                continue
            if key == "version" and version_override:
                out.append(f"version: {version_override}")
                version_written = True
                continue
        out.append(line)

    if version_override and not version_written:
        out.insert(1, f"version: {version_override}")

    return "---\n" + "\n".join(out).rstrip() + "\n---\n\n"


def remove_section_if_present(body: str, heading: str) -> str:
    section_range = find_section_range(body, heading)
    if section_range is None:
        return body
    start, end = section_range
    if end == len(body):
        return body[:start].rstrip() + "\n"
    return body[:start].rstrip() + "\n\n" + body[end:].lstrip()


def find_section_range(body: str, heading: str) -> tuple[int, int] | None:
    marker = f"## {heading}\n\n"
    start = body.find(marker)
    if start == -1:
        return None
    next_heading = body.find("\n## ", start + len(marker))
    if next_heading == -1:
        return start, len(body)
    return start, next_heading + 1


def replace_section(body: str, heading: str, new_section: str) -> str:
    section_range = find_section_range(body, heading)
    if section_range is None:
        raise ValueError(f"Could not find section `{heading}` in SKILL.md.")
    start, end = section_range
    replacement = new_section.rstrip() + "\n\n"
    return body[:start] + replacement + body[end:]


def replace_or_insert_section(
    body: str,
    headings: tuple[str, ...],
    new_section: str,
) -> str:
    for heading in headings:
        section_range = find_section_range(body, heading)
        if section_range is None:
            continue
        start, end = section_range
        replacement = new_section.rstrip() + "\n\n"
        return body[:start] + replacement + body[end:]

    first_heading = body.find("\n## ")
    replacement = new_section.rstrip() + "\n\n"
    if first_heading == -1:
        return body.rstrip() + "\n\n" + new_section.rstrip() + "\n"
    return (
        body[:first_heading].rstrip()
        + "\n\n"
        + replacement
        + body[first_heading + 1 :].lstrip()
    )


def remove_line(body: str, line: str, description: str) -> str:
    target = line.rstrip("\n")
    replacement = target + "\n"
    if replacement not in body:
        raise ValueError(f"Expected to find {description}, but it was missing.")
    return body.replace(replacement, "", 1)


def remove_line_if_present(body: str, line: str) -> str:
    target = line.rstrip("\n") + "\n"
    if target not in body:
        return body
    return body.replace(target, "", 1)


def transform_skill_md(source_text: str, version_override: str) -> str:
    frontmatter_lines, body = split_frontmatter(source_text)
    frontmatter = build_frontmatter(frontmatter_lines, version_override)
    body = remove_section_if_present(body, "First-Use Update Check")
    body = replace_or_insert_section(
        body,
        ("Install And Authorization", "Authorization Gate"),
        NEW_INSTALL_SECTION,
    )
    return frontmatter + body.rstrip() + "\n"


def transform_abel_auth_md(source_text: str) -> str:
    return source_text.replace(
        "4. Persist the resulting key to `skills/abel-auth/.env.skill` for this installed collection.\n",
        (
            f"4. In OpenClaw, persist the resulting key to `{OPENCLAW_API_KEY_PATH}`. "
            "Use `.env.skill` only for direct local script usage outside OpenClaw "
            "config management.\n"
        ),
    )


AUTH_DOC_PRIMARY_PATHS = ("SKILL.md",)
FORBIDDEN_PRIMARY_ENV_PHRASES = (
    "Persist the key to `<skill-root>/.env.skill` when local storage is available.",
    "Use `.env.skill` as the local auth file for this skill.",
    "By default, use `<skill-root>/.env.skill` as the local auth file.",
    "Persist the resulting key to `skills/abel-auth/.env.skill` for this installed collection.",
)


def validate_auth_story(rendered_docs: dict[str, str]) -> None:
    for path in AUTH_DOC_PRIMARY_PATHS:
        content = rendered_docs.get(path, "")
        if OPENCLAW_API_KEY_PATH not in content:
            raise ValueError(
                f"Rendered {path} is missing the OpenClaw primary auth path "
                f"{OPENCLAW_API_KEY_PATH!r}."
            )
        if ".env.skill" not in content:
            raise ValueError(f"Rendered {path} must still mention `.env.skill` fallback.")

    combined = "\n".join(rendered_docs.values())
    for phrase in FORBIDDEN_PRIMARY_ENV_PHRASES:
        if phrase in combined:
            raise ValueError(
                "Rendered ClawHub artifact still describes `.env.skill` as the "
                f"primary auth path: {phrase!r}"
            )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def remove_if_exists(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def frontmatter_value(lines: list[str], key: str) -> str:
    for line in lines:
        if not line or line[0].isspace() or ":" not in line:
            continue
        current_key, value = line.split(":", 1)
        if current_key.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def build_artifact(
    source_dir: Path,
    output_root: Path,
    version_override: str = "",
) -> Path:
    source_dir = source_dir.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    output_dir = output_root / SKILL_NAME

    if not source_dir.exists():
        raise ValueError(f"Source skill directory not found: {source_dir}")

    remove_if_exists(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True)
    source_skills_root = source_dir.parent
    bundle_skills_root = output_dir / "skills"
    bundle_skills_root.mkdir()
    for skill_name in RELEASE_SKILL_NAMES:
        skill_source = source_skills_root / skill_name
        if not skill_source.exists():
            raise ValueError(f"Release skill directory not found: {skill_source}")
        shutil.copytree(
            skill_source,
            bundle_skills_root / skill_name,
            ignore=ignore_copy_patterns,
        )

    skill_text = (bundle_skills_root / SKILL_NAME / "SKILL.md").read_text(
        encoding="utf-8"
    )
    frontmatter_lines, _ = split_frontmatter(skill_text)
    manifest = dict(OPENCLAW_PLUGIN_MANIFEST)
    version = version_override.strip() or frontmatter_value(frontmatter_lines, "version")
    if version:
        manifest["version"] = version
    package_json = dict(PACKAGE_JSON_BASE)
    if version:
        package_json["version"] = version
    write_text(
        output_dir / "openclaw.plugin.json",
        json.dumps(manifest, indent=2) + "\n",
    )
    write_text(output_dir / "package.json", json.dumps(package_json, indent=2) + "\n")
    write_text(output_dir / "index.js", OPENCLAW_EXTENSION_ENTRY)

    rendered_skill_md = transform_skill_md(skill_text, version_override.strip())
    validate_auth_story({"SKILL.md": rendered_skill_md})
    write_text(bundle_skills_root / SKILL_NAME / "SKILL.md", rendered_skill_md)
    write_text(bundle_skills_root / SKILL_NAME / "agents" / "openai.yaml", CLAWHUB_OPENAI_YAML)

    auth_skill_path = bundle_skills_root / "abel-auth" / "SKILL.md"
    write_text(
        auth_skill_path,
        transform_abel_auth_md(auth_skill_path.read_text(encoding="utf-8")),
    )

    for path in output_dir.glob("skills/**/.env.skill"):
        remove_if_exists(path)
    for path in output_dir.glob("skills/**/.env.skill.example"):
        remove_if_exists(path)
    for path in output_dir.glob("skills/**/.env.skills"):
        remove_if_exists(path)
    for path in output_dir.glob("skills/**/.env.skills.example"):
        remove_if_exists(path)
    remove_if_exists(output_dir / "CHANGELOG.md")
    return output_dir


def main() -> int:
    args = parse_args()
    output_dir = build_artifact(
        Path(args.source),
        Path(args.output_root),
        version_override=args.version,
    )
    print(f"Built ClawHub artifact at {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
