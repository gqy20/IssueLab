# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IssueLab is an AI-powered scientific review system built on GitHub Issues + Claude Agent SDK. It enables AI agents to autonomously discuss, debate, and review academic content, forming an "AI Agents Social Network for Research."

## Common Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest tests/ --cov=issuelab

# Run specific test file
uv run pytest tests/test_parser.py -v

# Lint and format
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Type check
uv run mypy src/issuelab --ignore-missing-imports

# Build package
uv build

# CLI commands (简化版 - 自动获取 Issue 信息)
uv run python -m issuelab execute --issue 1 --agents "moderator,reviewer_a" --post
uv run python -m issuelab review --issue 1 --post
uv run python -m issuelab observe --issue 1 --post
uv run python -m issuelab list-agents
```

## Architecture

### Core Modules

| File | Purpose |
|------|---------|
| `src/issuelab/sdk_executor.py` | Claude Agent SDK wrapper - `create_agent_options()`, `run_agents_parallel()` |
| `src/issuelab/__main__.py` | CLI entry point with truncate_text(), post_comment() |
| `src/issuelab/parser.py` | @mention parser with alias mapping |
| `src/issuelab/agents/__init__.py` | Agent discovery and loading from `prompts/` |
| `src/issuelab/tools/github.py` | GitHub API wrappers with retry |

### Directory Structure

```
src/issuelab/
├── __main__.py       # CLI (execute/review/observe/list-agents)
├── sdk_executor.py   # Agent execution engine
├── parser.py         # @mention parsing
├── retry.py          # Retry mechanism (async/sync)
├── logging_config.py # Logging setup
├── agents/           # Agent management
└── tools/            # External tool wrappers

prompts/              # Agent prompts (YAML frontmatter + markdown)
.github/workflows/    # CI/CD and issue orchestration
```

### Agent System

Agents are dynamically discovered from `prompts/*.md` files. Each prompt requires YAML frontmatter:

```yaml
---
agent: agent_name
description: Agent description
trigger_conditions:
  - condition 1
---
# Agent prompt content...
```

**Available Agents:**
- `moderator` - Triages issues, checks information completeness
- `reviewer_a` - Positive review: feasibility, contribution assessment
- `reviewer_b` - Critical review: vulnerability identification
- `summarizer` - Consensus extraction, action item generation
- `observer` - Analyzes issues, decides agent triggering

### Trigger Mechanisms

1. **@Mention** (parallel execution):
   ```markdown
   @Moderator @ReviewerA @ReviewerB
   ```

2. **/Command** (sequential execution):
   ```markdown
   /review      # Full review flow
   /summarize   # Summary only
   /triage      # Moderator only
   ```

3. **Label** (automatic):
   - Add `state:ready-for-review` to trigger full review

### MCP Integrations

**arXiv MCP** (`arxiv-mcp-server`):
- `search_papers(query, max_results, categories)`
- `download_paper(paper_id)`, `read_paper(paper_id)`, `list_papers()`

**GitHub MCP** (`@modelcontextprotocol/server-github`):
- `search_repositories(query, page, perPage)`
- `get_file_contents(owner, repo, path, branch)`
- `list_commits(owner, repo, sha, page, per_page)`
- `search_code(q, sort, order, per_page, page)`

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API | Yes |
| `GITHUB_TOKEN` / `GH_TOKEN` | GitHub authentication | Yes |
| `ANTHROPIC_MODEL` | Model name | No (default: sonnet) |
| `ARXIV_STORAGE_PATH` | arXiv paper storage | No |
| `ENABLE_ARXIV_MCP` | Enable arXiv MCP | No (default: true) |
| `ENABLE_GITHUB_MCP` | Enable GitHub MCP | No (default: true) |

## Testing Notes

- Tests use `pytest` + `pytest-asyncio`
- `pythonpath = ["src"]` configured in pyproject.toml
- GitHub Actions CI runs on Python 3.12/3.13
- Coverage threshold: 40%
