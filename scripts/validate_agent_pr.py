#!/usr/bin/env python3
"""Validate agent PR changes for structure and formatting rules."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _parse_frontmatter(text: str) -> dict | None:
    if not text.startswith("---"):
        return None
    parts = text.split("\n")
    if len(parts) < 3:
        return None
    # Find closing ---
    try:
        end_idx = parts[1:].index("---") + 1
    except ValueError:
        return None
    fm_text = "\n".join(parts[1:end_idx])
    try:
        data = yaml.safe_load(fm_text) or {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _validate_agent_yml(path: Path, folder: str, errors: list[str]) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        _error(errors, f"Cannot read {path}: {exc}")
        return

    try:
        data = yaml.safe_load(content) or {}
    except Exception as exc:
        _error(errors, f"Invalid YAML in {path}: {exc}")
        return

    if not isinstance(data, dict):
        _error(errors, f"YAML root must be a mapping in {path}")
        return

    required = ["name", "owner", "description", "repository"]
    for key in required:
        if not data.get(key):
            _error(errors, f"Missing required field '{key}' in {path}")

    owner = str(data.get("owner", "")).strip()
    if owner and owner != folder:
        _error(errors, f"owner '{owner}' does not match folder name '{folder}' in {path}")

    repo = str(data.get("repository", "")).strip()
    if repo.endswith(".git"):
        repo = repo[:-4]
    if repo:
        if "/" not in repo:
            _error(errors, f"repository '{repo}' must be in the form owner/name in {path}")
        else:
            repo_owner, repo_name = repo.split("/", 1)
            if not repo_owner or not repo_name:
                _error(errors, f"repository '{repo}' must be in the form owner/name in {path}")
            else:
                if owner and repo_owner != owner:
                    _error(errors, f"repository owner '{repo_owner}' must match owner '{owner}' in {path}")
                _check_repo_exists(repo, errors, path)

    if not content.endswith("\n"):
        _error(errors, f"File must end with newline: {path}")


def _validate_agent_prompt(path: Path, errors: list[str]) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        _error(errors, f"Cannot read {path}: {exc}")
        return

    if len(content.strip()) < 20:
        _error(errors, f"Prompt too short or empty: {path}")

    if not content.endswith("\n"):
        _error(errors, f"File must end with newline: {path}")


def _validate_builtin_prompt(path: Path, errors: list[str]) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        _error(errors, f"Cannot read {path}: {exc}")
        return

    frontmatter = _parse_frontmatter(content)
    if frontmatter is None:
        _error(errors, f"Missing or invalid YAML frontmatter in {path}")
        return

    if not frontmatter.get("agent"):
        _error(errors, f"Missing 'agent' in frontmatter: {path}")
    if not frontmatter.get("description"):
        _error(errors, f"Missing 'description' in frontmatter: {path}")

    if not content.endswith("\n"):
        _error(errors, f"File must end with newline: {path}")


def _check_repo_exists(repo: str, errors: list[str], path: Path) -> None:
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        # No token available in local runs; skip existence check.
        return

    url = f"https://api.github.com/repos/{repo}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                _error(errors, f"repository '{repo}' not found (HTTP {resp.status}) in {path}")
    except Exception as exc:
        _error(errors, f"repository '{repo}' lookup failed: {exc} in {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate agent PR changes")
    parser.add_argument("--files", required=True, help="JSON array of changed file paths")
    args = parser.parse_args()

    try:
        files = json.loads(args.files)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON for --files: {exc}", file=sys.stderr)
        return 2

    if not isinstance(files, list):
        print("--files must be a JSON array", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []

    for file in files:
        if not isinstance(file, str):
            continue
        path = repo_root / file
        parts = Path(file).parts

        if file.startswith("agents/"):
            if len(parts) < 3:
                _error(errors, f"Invalid agent file path (must be agents/<name>/agent.yml or prompt.md): {file}")
                continue
            folder = parts[1]
            filename = parts[2]
            if len(parts) == 3:
                if filename == "agent.yml":
                    _validate_agent_yml(path, folder, errors)
                    prompt_path = repo_root / "agents" / folder / "prompt.md"
                    if not prompt_path.exists():
                        _error(errors, f"Missing prompt.md for agent '{folder}'")
                elif filename == "prompt.md":
                    _validate_agent_prompt(path, errors)
                    agent_path = repo_root / "agents" / folder / "agent.yml"
                    if not agent_path.exists():
                        _error(errors, f"Missing agent.yml for agent '{folder}'")
                elif filename == ".mcp.json":
                    if not path.exists():
                        _error(errors, f"Missing MCP config: {file}")
                else:
                    _error(errors, f"Unsupported agent file: {file}")
            else:
                if filename == ".claude":
                    if not path.exists():
                        _error(errors, f"Missing agent .claude file: {file}")
                else:
                    _error(errors, f"Unsupported agent file: {file}")

        elif file.startswith("prompts/"):
            if not file.endswith(".md"):
                _error(errors, f"Prompt files must be .md: {file}")
            else:
                _validate_builtin_prompt(path, errors)
        else:
            _error(errors, f"Unsupported path outside agents/ or prompts/: {file}")

    if errors:
        print("Validation failed:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
