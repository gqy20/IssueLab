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

# CLI commands
uv run python -m issuelab execute --issue 1 --agents "moderator,reviewer_a" --post
uv run python -m issuelab review --issue 1 --post
uv run python -m issuelab observe --issue 1 --post
uv run python -m issuelab observe-batch --issues "1,2,3" --post
uv run python -m issuelab list-agents
```

**Parameters:**
- `--post`: Post results back to the GitHub Issue
- `--issues`: Comma-separated list of issue numbers (for observe-batch)

## Architecture

### Core Modules

| File | Purpose |
|------|---------|
| `src/issuelab/__main__.py` | CLI entry point - `execute`, `review`, `observe`, `observe-batch`, `list-agents` |
| `src/issuelab/sdk_executor.py` | Agent execution engine - `create_agent_options()`, `AgentConfig`, `SCENE_CONFIGS`, `run_agents_parallel()` |
| `src/issuelab/config.py` | Environment variable management - `Config.get_anthropic_api_key()`, `Config.get_github_token()` |
| `src/issuelab/parser.py` | @mention parsing with alias mapping |
| `src/issuelab/agents/__init__.py` | Agent discovery and loading from `prompts/` and `agents/` |
| `src/issuelab/cli/dispatch.py` | Cross-repository event dispatch (Plan B) |
| `src/issuelab/tools/github.py` | GitHub API wrappers using `gh` CLI |
| `src/issuelab/retry.py` | Retry mechanism - `retry_async()`, `retry_sync()` |

### Directory Structure

```
src/issuelab/
├── __main__.py       # CLI (execute/review/observe/observe-batch/list-agents)
├── sdk_executor.py   # Agent execution engine
├── config.py         # Environment variables
├── parser.py         # @mention parsing with alias mapping
├── retry.py          # Retry mechanism (async/sync)
├── agents/           # Agent management
├── cli/              # Cross-repository dispatch
└── tools/            # External tool wrappers

prompts/              # Agent prompts (YAML frontmatter + markdown)
.github/workflows/    # CI/CD and issue orchestration
agents/_registry/     # User agent registry (Plan B)
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
- `echo` / `test` - Testing agents

**User Custom Agents:** Users can fork the repo and add their own agents in `agents/<username>/` directory with `prompt.md`. These are registered in `agents/_registry/*.yml` for cross-repository triggering.

**Agent Aliases:** `mod`, `reviewer`/`reviewera`, `reviewerb`/`revb`, `summarizer`/`summary`

### Trigger Mechanisms

1. **@Mention** (via orchestrator.yml):
   - **Built-in agents** (`@Moderator`, `@ReviewerA`, `@ReviewerB`, `@Summarizer`, `@Observer`, `@Echo`, `@Test`): Execute in main repo
   - **Registered users** (`@alice`): Dispatch to user's fork via `dispatch_agents.yml`
   - **Aliases**: `@mod` → moderator, `@reviewer`/`@reviewera` → reviewer_a, `@reviewerb`/`@revb` → reviewer_b, `@summary` → summarizer

2. **/Command** (via orchestrator.yml):
   - `/review` - Sequential flow: moderator -> reviewer_a -> reviewer_b -> summarizer
   - `/quiet` - Add `bot:quiet` label to silence the bot

3. **Label**:
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
| `ANTHROPIC_API_TOKEN` | Anthropic API | Yes |
| `GITHUB_TOKEN` / `GH_TOKEN` | GitHub authentication | Yes |
| `ANTHROPIC_MODEL` | Model name | No (default: sonnet) |
| `ANTHROPIC_BASE_URL` | API base URL (for proxies) | No |
| `ARXIV_STORAGE_PATH` | arXiv paper storage | No |
| `ENABLE_ARXIV_MCP` | Enable arXiv MCP | No (default: true) |
| `ENABLE_GITHUB_MCP` | Enable GitHub MCP | No (default: true) |
| `LOG_LEVEL` | Logging level | No (default: INFO) |
| `LOG_FILE` | Log file path | No |

### Distributed Execution (Plan B)

Cross-repository agent execution via GitHub App:
- **Registry:** `agents/_registry/*.yml` maps users to their forks
- **Dispatch modes:** `repository_dispatch` or `workflow_dispatch`
- **Tokens:** GitHub App Installation Token generated per repository
- **DISPATCH_TOKEN:** Fine-grained PAT in main repo for triggering user forks

**User fork requirements:**
- `ANTHROPIC_API_TOKEN` - User's Claude API key in fork secrets
- `.github/workflows/user_agent.yml` - Receives dispatch events
- `agents/<username>/prompt.md` - Custom agent prompt

### Timeout Control

Official Claude Agent SDK recommendations for preventing timeouts:
- `max_turns`: Limit conversation turns (default: 3) to prevent infinite loops
- `max_budget_usd`: Limit spending (default: $0.50) for cost protection
- `timeout_seconds`: Total timeout in seconds (default: 180)

**Scene Configurations:**
```python
SCENE_CONFIGS = {
    "quick": AgentConfig(max_turns=2, max_budget_usd=0.20, timeout_seconds=60),
    "review": AgentConfig(max_turns=3, max_budget_usd=0.50, timeout_seconds=180),
    "deep": AgentConfig(max_turns=5, max_budget_usd=1.00, timeout_seconds=300),
}
```

**Environment Optimizations:**
- `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK=true` - Skip version check, saves ~2s
- `CLAUDE_CODE_STREAM_CLOSE_TIMEOUT=30000` - Reduce wait time

## Testing Notes

- Tests use `pytest` + `pytest-asyncio`
- `pythonpath = ["src"]` configured in pyproject.toml
- GitHub Actions CI runs on Python 3.12/3.13
- Coverage threshold: 40%
