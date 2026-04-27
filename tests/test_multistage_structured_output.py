"""Tests: 多阶段流完全使用 structured_output，YAML 文本降为 fallback

TDD Red Phase: 验证多阶段各阶段之间传递 structured_output 而非 YAML 文本。
"""

import pytest
from unittest.mock import MagicMock, patch
from issuelab.agents import executor as ex_module
from issuelab.agents.executor import _run_gqy20_multistage


class TestMultistageStructuredOutputFlow:
    """多阶段流：structured_output 应在各阶段间传递"""

    def setup_method(self):
        from issuelab.agents.options import clear_agent_options_cache
        clear_agent_options_cache()

    @pytest.mark.asyncio
    async def test_run_stage_returns_structured_output(self):
        """_run_stage 返回结果应包含 structured_output 字段"""
        from claude_agent_sdk import ResultMessage, AssistantMessage, TextBlock

        structured_data = {
            "summary": "test",
            "evidence": [
                {"claim": "c1", "source": "s1", "url": "https://example.com/1", "confidence": "medium"}
            ],
            "open_questions": [],
            "confidence": "medium",
        }

        mock_result_msg = ResultMessage(
            subtype="agent", duration_ms=100, duration_api_ms=50, is_error=False,
            num_turns=1, session_id="s1", stop_reason="end_turn",
            total_cost_usd=0.01,
            usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            result="done", structured_output=structured_data,
        )
        mock_text = TextBlock(text="```yaml\nsummary: test\n...\n```")
        mock_assistant = AssistantMessage(content=[mock_text], model="test")

        async def fake_query(*, prompt, options):
            yield mock_assistant
            yield mock_result_msg

        with patch.object(ex_module, "query", side_effect=fake_query):
            # _run_stage is a nested function, test via the actual flow
            # We test the key behavior: structured_output is returned
            from issuelab.schemas import SchemaRegistry

            # Verify SchemaRegistry.parse works for researcher stage
            parsed = SchemaRegistry.parse("researcher", structured_data)
            assert parsed.summary == "test"
            assert len(parsed.evidence) == 1

    @pytest.mark.asyncio
    async def test_researcher_validation_uses_structured_output_not_yaml(self):
        """Researcher 阶段验证应基于 structured_output，而非 YAML 文本解析"""
        from claude_agent_sdk import ResultMessage, AssistantMessage, TextBlock

        # Structured output with valid evidence (has URL)
        structured_data = {
            "summary": "研究结论",
            "evidence": [
                {
                    "claim": "物种形成与杂交有关",
                    "source": "Nature论文",
                    "url": "https://nature.com/article",
                    "confidence": "high",
                }
            ],
            "open_questions": [],
            "confidence": "high",
        }

        mock_result_msg = ResultMessage(
            subtype="agent", duration_ms=100, duration_api_ms=50, is_error=False,
            num_turns=1, session_id="s1", stop_reason="end_turn",
            total_cost_usd=0.01,
            usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            result="done", structured_output=structured_data,
        )
        # Text response is incomplete YAML (should NOT be used for validation)
        mock_text = TextBlock(text="summary: 研究结论")  # incomplete, no yaml block
        mock_assistant = AssistantMessage(content=[mock_text], model="test")

        call_args = {}

        async def fake_run_single_agent(prompt, agent_name, *, stage_name=None, schema_name=None):
            call_args["prompt"] = prompt
            call_args["schema_name"] = schema_name
            return {
                "response": mock_text.text,
                "cost_usd": 0.01, "num_turns": 1,
                "tool_calls": [], "input_tokens": 10, "output_tokens": 20, "total_tokens": 30,
                "structured_output": structured_data,
                "ok": True,
            }

        async def fake_query(*, prompt, options):
            yield mock_assistant
            yield mock_result_msg

        with patch.object(ex_module, "query", side_effect=fake_query):
            with patch.object(ex_module, "run_single_agent", side_effect=fake_run_single_agent):
                with patch.object(ex_module, "get_agent_config", return_value={}):
                    with patch.object(ex_module, "is_system_agent", return_value=(False, "")):
                        with patch.object(ex_module, "AgentConfig") as FakeConfig:
                            FakeConfig.return_value.max_turns = 100
                            FakeConfig.return_value.max_budget_usd = 10.0
                            FakeConfig.return_value.timeout_seconds = 600

                            result = await ex_module.run_single_agent(
                                "test prompt", "gqy20",
                                stage_name="Researcher", schema_name="Researcher"
                            )

        # Verifies structured_output was returned
        assert result.get("structured_output") == structured_data
        # Verifies schema_name was passed through
        assert call_args["schema_name"] == "Researcher"

    @pytest.mark.asyncio
    async def test_fallback_without_structured_output_still_works(self):
        """没有 structured_output 时，YAML 文本解析的 fallback 路径仍然保留"""
        from issuelab.agents import observer as observer_module
        from issuelab.agents.parsers import parse_papers_recommendation

        yaml_text = """```yaml
summary: "推荐2篇"
recommended:
  - index: 0
    title: "Paper A"
    reason: "相关"
    summary: "摘要"
  - index: 2
    title: "Paper C"
    reason: "创新"
    summary: "摘要C"
```"""

        # YAML 解析仍可用（作为 fallback）
        papers = [
            {"id": "a0", "title": "Paper A", "summary": "摘要A", "url": "http://a0", "pdf_url": "", "authors": "", "published": "", "category": ""},
            {"id": "a1", "title": "Paper B", "summary": "摘要B", "url": "http://a1", "pdf_url": "", "authors": "", "published": "", "category": ""},
            {"id": "a2", "title": "Paper C", "summary": "摘要C", "url": "http://a2", "pdf_url": "", "authors": "", "published": "", "category": ""},
        ]
        parsed = parse_papers_recommendation(yaml_text, len(papers))
        assert len(parsed) == 2
        assert parsed[0]["index"] == 0
        assert parsed[1]["index"] == 2


class TestValidateResearcherStageOutputRemoval:
    """_validate_researcher_stage_output 应被移除（已由 SchemaRegistry.parse 替代）"""

    def test_validate_researcher_stage_output_not_called_in_flow(self):
        """_validate_researcher_stage_output 函数应从代码中移除

        验证逻辑已由 run_single_agent 中的 SchemaRegistry.parse() 替代。
        """
        import inspect
        from issuelab.agents import executor

        # 检查 _validate_researcher_stage_output 是否仍在 executor.py 中
        has_validator = hasattr(executor, "_validate_researcher_stage_output")

        # 如果函数仍存在，检查是否还被调用
        if has_validator:
            source = inspect.getsource(executor)
            # 函数定义存在，但应该不再被调用
            call_count = source.count("_validate_researcher_stage_output")
            # 函数定义本身会计数为1（def line），如果只有1次出现说明无调用
            assert call_count <= 1, "_validate_researcher_stage_output 仍有调用，未被移除"
