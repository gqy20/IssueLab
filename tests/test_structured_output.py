"""Tests for structured_output 提取和处理"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import anyio
from issuelab.agents.executor import run_single_agent


class TestStructuredOutputExtraction:
    """验证 ResultMessage.structured_output 被正确提取"""

    def setup_method(self):
        """每个测试前清除缓存"""
        from issuelab.agents.options import clear_agent_options_cache
        clear_agent_options_cache()

    def _make_async_iter(self, items):
        """创建真正的异步迭代器"""
        async def async_gen():
            for item in items:
                yield item
        return async_gen()

    @pytest.mark.asyncio
    async def test_run_single_agent_returns_structured_output_field(self):
        """run_single_agent 返回的 dict 应包含 structured_output 字段"""
        from claude_agent_sdk import ResultMessage, AssistantMessage, TextBlock

        structured_data = {"summary": "test", "findings": [], "recommendations": []}
        mock_result_message = ResultMessage(
            subtype="agent",
            duration_ms=100,
            duration_api_ms=50,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            stop_reason="end_turn",
            total_cost_usd=0.01,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            result="test result",
            structured_output=structured_data,
        )

        mock_text_block = TextBlock(text="Test response")
        mock_assistant_message = AssistantMessage(
            content=[mock_text_block],
            model="test-model",
        )

        async def mock_query(*, prompt, options):
            yield mock_assistant_message
            yield mock_result_message

        with patch("issuelab.agents.executor.query", side_effect=mock_query):
            result = await run_single_agent("test prompt", "gqy20")

        assert "structured_output" in result
        assert result["structured_output"] == structured_data

    @pytest.mark.asyncio
    async def test_run_single_agent_structured_output_none_when_not_present(self):
        """当 ResultMessage 没有 structured_output 时，字段应为 None"""
        from claude_agent_sdk import ResultMessage, AssistantMessage, TextBlock

        mock_result_message = ResultMessage(
            subtype="agent",
            duration_ms=100,
            duration_api_ms=50,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            stop_reason="end_turn",
            total_cost_usd=0.01,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            result="test result",
            structured_output=None,
        )

        mock_text_block = TextBlock(text="Test response")
        mock_assistant_message = AssistantMessage(
            content=[mock_text_block],
            model="test-model",
        )

        async def mock_query(*, prompt, options):
            yield mock_assistant_message
            yield mock_result_message

        with patch("issuelab.agents.executor.query", side_effect=mock_query):
            result = await run_single_agent("test prompt", "gqy20")

        assert "structured_output" in result
        assert result["structured_output"] is None

    @pytest.mark.asyncio
    async def test_run_single_agent_accepts_schema_name_parameter(self):
        """run_single_agent 应接受 schema_name 参数并传递给 create_agent_options"""
        from claude_agent_sdk import ResultMessage, AssistantMessage, TextBlock

        mock_result_message = ResultMessage(
            subtype="agent",
            duration_ms=100,
            duration_api_ms=50,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            stop_reason="end_turn",
            total_cost_usd=0.01,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            result="test result",
            structured_output=None,
        )

        mock_text_block = TextBlock(text="Test response")
        mock_assistant_message = AssistantMessage(
            content=[mock_text_block],
            model="test-model",
        )

        async def mock_query(*, prompt, options):
            yield mock_assistant_message
            yield mock_result_message

        with patch("issuelab.agents.executor.query", side_effect=mock_query):
            with patch("issuelab.agents.executor.create_agent_options") as mock_create_opts:
                mock_create_opts.return_value = MagicMock()
                await run_single_agent("test prompt", "gqy20", schema_name="researcher")

                # 验证 create_agent_options 被调用时传入了 schema_name="researcher"
                mock_create_opts.assert_called_once()
                call_kwargs = mock_create_opts.call_args.kwargs
                assert call_kwargs.get("schema_name") == "researcher"

    @pytest.mark.asyncio
    async def test_run_single_agent_schema_name_defaults_to_none(self):
        """未指定 schema_name 时应传递 None（由 create_agent_options 默认处理）"""
        from claude_agent_sdk import ResultMessage, AssistantMessage, TextBlock

        mock_result_message = ResultMessage(
            subtype="agent",
            duration_ms=100,
            duration_api_ms=50,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            stop_reason="end_turn",
            total_cost_usd=0.01,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            result="test result",
            structured_output=None,
        )

        mock_text_block = TextBlock(text="Test response")
        mock_assistant_message = AssistantMessage(
            content=[mock_text_block],
            model="test-model",
        )

        async def mock_query(*, prompt, options):
            yield mock_assistant_message
            yield mock_result_message

        with patch("issuelab.agents.executor.query", side_effect=mock_query):
            with patch("issuelab.agents.executor.create_agent_options") as mock_create_opts:
                mock_create_opts.return_value = MagicMock()
                await run_single_agent("test prompt", "gqy20")

                call_kwargs = mock_create_opts.call_args.kwargs
                assert call_kwargs.get("schema_name") is None
