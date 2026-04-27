import pytest


def test_gqy20_multistage_toggle(monkeypatch):
    from issuelab.agents.executor import _is_gqy20_multistage_enabled

    monkeypatch.delenv("ISSUELAB_GQY20_MULTISTAGE", raising=False)
    assert _is_gqy20_multistage_enabled("gqy20") is True
    assert _is_gqy20_multistage_enabled("moderator") is False

    monkeypatch.setenv("ISSUELAB_GQY20_MULTISTAGE", "0")
    assert _is_gqy20_multistage_enabled("gqy20") is False


def test_collect_source_urls_prefers_yaml_sources():
    from issuelab.agents.executor import _collect_source_urls

    text = """```yaml
summary: "s"
findings: []
recommendations: []
sources:
  - "https://example.com/1"
  - "https://example.com/2"
confidence: "high"
```
Other link: https://ignored.example.com/x
"""
    urls = _collect_source_urls(text)
    assert urls == ["https://example.com/1", "https://example.com/2"]


@pytest.mark.asyncio
async def test_gqy20_multistage_judge_retry_then_success(monkeypatch):
    from issuelab.agents import executor as ex

    calls = {"count": 0}

    async def fake_run_single_agent(prompt: str, agent_name: str, *, stage_name: str | None = None, schema_name: str | None = None):
        calls["count"] += 1
        stage = calls["count"]
        if stage == 1:
            response = """```yaml
summary: "research"
evidence:
  - claim: "c1"
    source: "s1"
    url: "https://example.com/e1"
    confidence: "medium"
open_questions: []
confidence: "medium"
```"""
        elif stage <= 4:
            response = """```yaml
summary: "ok"
findings: []
recommendations: []
confidence: "medium"
```"""
        elif stage == 5:
            # First Judge: no sources, should trigger retry
            response = """```yaml
summary: "judge"
findings:
  - "f"
recommendations:
  - "r"
sources: []
confidence: "medium"
```"""
        else:
            response = """```yaml
summary: "judge"
findings:
  - "f"
recommendations:
  - "r"
sources:
  - "https://example.com/final"
confidence: "high"
```"""

        return {
            "response": response,
            "cost_usd": 0.01,
            "num_turns": 1,
            "tool_calls": ["Read"],
            "input_tokens": 10,
            "output_tokens": 10,
            "total_tokens": 20,
        }

    monkeypatch.setattr(ex, "run_single_agent", fake_run_single_agent)

    result = await ex._run_gqy20_multistage("base prompt", 1, "ctx")
    assert "https://example.com/final" in result["response"]
    assert calls["count"] >= 6
    assert result["cost_usd"] > 0


@pytest.mark.asyncio
async def test_gqy20_multistage_stops_when_researcher_fails(monkeypatch):
    from issuelab.agents import executor as ex

    calls = {"count": 0}

    async def fake_run_single_agent(prompt: str, agent_name: str, *, stage_name: str | None = None, schema_name: str | None = None):
        calls["count"] += 1
        return {
            "ok": False,
            "error_type": "timeout",
            "error_message": "stage timeout",
            "stage": stage_name,
            "response": "[系统护栏] timeout",
            "cost_usd": 0.01,
            "num_turns": 1,
            "tool_calls": [],
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }

    monkeypatch.setattr(ex, "run_single_agent", fake_run_single_agent)

    result = await ex._run_gqy20_multistage("base prompt", 1, "ctx")
    assert result["ok"] is False
    assert result["failed_stage"] == "Researcher"
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_gqy20_multistage_researcher_invalid_output_fallbacks_to_single_stage(monkeypatch):
    from issuelab.agents import executor as ex

    calls = {"count": 0}

    async def fake_run_single_agent(prompt: str, agent_name: str, *, stage_name: str | None = None, schema_name: str | None = None):
        calls["count"] += 1
        # First call: Researcher invalid output (missing evidence)
        if calls["count"] == 1:
            return {
                "ok": True,
                "response": """```yaml
summary: "research"
open_questions: []
confidence: "low"
```""",
                "cost_usd": 0.01,
                "num_turns": 1,
                "tool_calls": ["Read"],
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
            }

        # Second call: fallback single-stage answer
        return {
            "ok": True,
            "response": """## Summary
基于现有信息给出初步判断。

## Key Findings
- 关键证据尚不完整。

## Recommended Actions
- 补充一手来源后再下最终结论。""",
            "cost_usd": 0.02,
            "num_turns": 1,
            "tool_calls": ["Read"],
            "input_tokens": 2,
            "output_tokens": 2,
            "total_tokens": 4,
        }

    monkeypatch.setattr(ex, "run_single_agent", fake_run_single_agent)

    result = await ex._run_gqy20_multistage("base prompt", 1, "ctx")
    assert result["ok"] is True
    # Late fallback: all 5 stages run first, then fallback at end if sources missing
    # The fallback response contains "关键证据尚不完整"
    assert "关键证据尚不完整" in result["response"]
    # Late fallback doesn't set FallbackSingleStage in stages (that's early fallback)
    # Verify fallback was triggered by checking stages contain all 5 stages
    assert "Researcher" in result["stages"]
    assert "Analyst" in result["stages"]


@pytest.mark.asyncio
async def test_gqy20_multistage_judge_uses_markdown_contract(monkeypatch):
    from issuelab.agents import executor as ex

    calls: list[dict[str, object]] = []

    async def fake_run_single_agent(prompt: str, agent_name: str, *, stage_name: str | None = None, schema_name: str | None = None):
        calls.append({"prompt": prompt, "stage_name": stage_name})
        if "当前阶段：Researcher" in prompt:
            return {
                "ok": True,
                "response": """```yaml
summary: "r"
evidence:
  - claim: "c"
    source: "s"
    url: "https://example.com/r"
    confidence: "high"
open_questions:
  - "q"
confidence: "high"
```""",
                "cost_usd": 0.01,
                "num_turns": 1,
                "tool_calls": ["Read"],
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
            }
        if "当前阶段：Judge" in prompt:
            return {
                "ok": True,
                "response": """[Agent: gqy20]

## Summary
ok

## Sources
- https://example.com/final
""",
                "cost_usd": 0.01,
                "num_turns": 1,
                "tool_calls": ["Read"],
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
            }
        return {
            "ok": True,
            "response": """```yaml
summary: "ok"
findings: []
recommendations: []
confidence: "medium"
```""",
            "cost_usd": 0.01,
            "num_turns": 1,
            "tool_calls": ["Read"],
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }

    monkeypatch.setattr(ex, "run_single_agent", fake_run_single_agent)
    result = await ex._run_gqy20_multistage("agent prompt", 1, "ctx")

    assert result["ok"] is True
    judge_call = next(item for item in calls if "当前阶段：Judge" in str(item["prompt"]))
    assert judge_call["stage_name"] is None
    assert "最终输出格式：" in str(judge_call["prompt"])
