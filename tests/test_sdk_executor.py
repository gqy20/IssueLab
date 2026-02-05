"""测试 SDK 执行器"""

import json
import os
import tempfile
from pathlib import Path

from unittest.mock import MagicMock, patch

import pytest

from issuelab.agents.config import SCENE_CONFIGS, AgentConfig, get_agent_config_for_scene
from issuelab.agents.discovery import discover_agents, load_prompt
from issuelab.agents.options import (
    _cached_agent_options,
    clear_agent_options_cache,
    create_agent_options,
    load_mcp_servers_for_agent,
    format_mcp_servers_for_prompt,
)
from issuelab.agents.parsers import parse_observer_response


def test_discover_agents_returns_dict():
    """discover_agents 应该返回字典"""
    agents = discover_agents()
    assert isinstance(agents, dict)
    assert len(agents) > 0


def test_create_agent_options_has_agents():
    """create_agent_options 应该包含所有定义的代理（observer除外）"""
    options = create_agent_options()
    assert hasattr(options, "agents")
    assert "moderator" in options.agents
    assert "reviewer_a" in options.agents
    assert "reviewer_b" in options.agents
    assert "summarizer" in options.agents
    # observer 不在此列表中（单独处理）
    assert "observer" not in options.agents


def test_create_agent_options_has_setting_sources():
    """create_agent_options 应该设置 setting_sources"""
    options = create_agent_options()
    assert hasattr(options, "setting_sources")
    assert "user" in options.setting_sources
    assert "project" in options.setting_sources


def test_load_prompt_moderator():
    """load_prompt 应该加载 moderator 提示词"""
    result = load_prompt("moderator")
    assert "Moderator" in result or "审核" in result
    assert len(result) > 0


def test_load_prompt_unknown_agent():
    """load_prompt 对未知代理返回空"""
    result = load_prompt("unknown_agent_that_does_not_exist")
    assert result == ""


class TestAgentConfig:
    """测试 AgentConfig dataclass"""

    def test_agent_config_defaults(self):
        """AgentConfig 应该有合理的默认值"""
        config = AgentConfig()
        assert config.max_turns == 30
        assert config.max_budget_usd == 10.00
        assert config.timeout_seconds == 180

    def test_agent_config_custom_values(self):
        """AgentConfig 应该支持自定义值"""
        config = AgentConfig(
            max_turns=5,
            max_budget_usd=1.00,
            timeout_seconds=300,
        )
        assert config.max_turns == 5
        assert config.max_budget_usd == 1.00
        assert config.timeout_seconds == 300


class TestSceneConfigs:
    """测试场景配置"""

    def test_scene_configs_has_required_scenes(self):
        """SCENE_CONFIGS 应该包含必需的场景"""
        assert "quick" in SCENE_CONFIGS
        assert "review" in SCENE_CONFIGS
        assert "deep" in SCENE_CONFIGS

    def test_quick_config_is_restrictive(self):
        """quick 配置应该更严格"""
        quick = SCENE_CONFIGS["quick"]
        review = SCENE_CONFIGS["review"]
        assert quick.max_turns <= review.max_turns
        assert quick.max_budget_usd <= review.max_budget_usd
        assert quick.timeout_seconds <= review.timeout_seconds

    def test_deep_config_is_permissive(self):
        """deep 配置应该更宽松"""
        deep = SCENE_CONFIGS["deep"]
        review = SCENE_CONFIGS["review"]
        assert deep.max_turns >= review.max_turns
        assert deep.max_budget_usd >= review.max_budget_usd
        assert deep.timeout_seconds >= review.timeout_seconds


class TestCreateAgentOptionsWithTimeout:
    """测试 create_agent_options 的超时控制"""

    def test_create_agent_options_has_max_turns(self):
        """create_agent_options 应该支持 max_turns 参数"""
        options = create_agent_options(max_turns=5)
        assert options.max_turns == 5

    def test_create_agent_options_has_max_budget_usd(self):
        """create_agent_options 应该支持 max_budget_usd 参数"""
        options = create_agent_options(max_budget_usd=1.00)
        assert options.max_budget_usd == 1.00

    def test_create_agent_options_uses_default_max_turns(self):
        """create_agent_options 应该使用默认的 max_turns"""
        options = create_agent_options()
        assert options.max_turns == 30  # 默认值

    def test_create_agent_options_uses_default_max_budget_usd(self):
        """create_agent_options 应该使用默认的 max_budget_usd"""
        options = create_agent_options()
        assert options.max_budget_usd == 10.00  # 默认值


class TestMcpConfigLoading:
    """测试 MCP 配置加载"""

    def test_load_mcp_servers_for_agent_merges(self, tmp_path: Path):
        """全局 + agent 配置应合并，agent 覆盖同名 server"""
        root_mcp = {
            "mcpServers": {
                "global": {"type": "http", "url": "https://global.example.com"},
                "shared": {"type": "http", "url": "https://root.example.com"},
            }
        }
        agent_mcp = {
            "mcpServers": {
                "agent": {"type": "http", "url": "https://agent.example.com"},
                "shared": {"type": "http", "url": "https://agent.example.com"},
            }
        }

        (tmp_path / ".mcp.json").write_text(json.dumps(root_mcp), encoding="utf-8")
        agent_dir = tmp_path / "agents" / "alice"
        agent_dir.mkdir(parents=True)
        (agent_dir / ".mcp.json").write_text(json.dumps(agent_mcp), encoding="utf-8")

        servers = load_mcp_servers_for_agent("alice", root_dir=tmp_path)
        assert servers["global"]["url"] == "https://global.example.com"
        assert servers["agent"]["url"] == "https://agent.example.com"
        assert servers["shared"]["url"] == "https://agent.example.com"

    def test_create_agent_options_includes_mcp_allowed_tools(self):
        """当存在 MCP servers 时，应包含 mcp__<server>__* 授权"""
        clear_agent_options_cache()
        with patch("issuelab.agents.options.load_mcp_servers_for_agent") as mock_load:
            mock_load.return_value = {"docs": {"type": "http", "url": "https://docs.example.com"}}
            options = create_agent_options(agent_name="moderator")
            assert "mcp__docs__*" in options.allowed_tools
            assert "Read" in options.allowed_tools
            assert "Write" in options.allowed_tools
            assert "Bash" in options.allowed_tools

    def test_format_mcp_servers_for_prompt(self, tmp_path: Path):
        """格式化 MCP 列表应包含 server 名称"""
        root_mcp = {"mcpServers": {"alpha": {"type": "http", "url": "https://a.example.com"}}}
        (tmp_path / ".mcp.json").write_text(json.dumps(root_mcp), encoding="utf-8")

        text = format_mcp_servers_for_prompt("any", root_dir=tmp_path)
        assert "- alpha [http]" in text

    def test_mcp_load_timeout_returns_empty(self):
        """MCP 读取超时应被忽略"""
        tmp_root = Path(tempfile.gettempdir()) / "issuelab_mcp_timeout"
        tmp_root.mkdir(parents=True, exist_ok=True)
        (tmp_root / ".mcp.json").write_text("{}", encoding="utf-8")
        with patch("issuelab.agents.options._read_text_with_timeout") as mock_read:
            mock_read.side_effect = TimeoutError("timeout")
            servers = load_mcp_servers_for_agent("any", root_dir=tmp_root)
            assert servers == {}

    def test_mcp_log_tools_triggers_listing(self):
        """MCP_LOG_TOOLS=1 时应触发工具列表逻辑"""
        clear_agent_options_cache()
        with patch.dict(os.environ, {"MCP_LOG_TOOLS": "1"}):
            with patch("issuelab.agents.options.load_mcp_servers_for_agent") as mock_load:
                mock_load.return_value = {"docs": {"command": "echo", "args": ["hi"]}}
                with patch("issuelab.agents.options._list_tools_for_mcp_server") as mock_list:
                    mock_list.return_value = []
                    _ = create_agent_options(agent_name="moderator")
                    mock_list.assert_called()


class TestSubagents:
    """测试 per-agent subagents 机制"""

    def test_per_agent_subagent_loaded_without_task(self, tmp_path):
        """subagent 应加载且不包含 Task 工具"""
        from issuelab.agents.options import create_agent_options

        # 创建 agents 目录结构
        agents_dir = tmp_path / "agents" / "gqy20" / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "literature-triage.md").write_text(
            "---\n"
            "agent: literature-triage\n"
            "description: test subagent\n"
            "tools:\n"
            "  - Read\n"
            "  - Task\n"
            "---\n\n"
            "# Triage\n"
            "Content",
            encoding="utf-8",
        )

        # patch AGENTS_DIR to point to tmp agents root
        with patch("issuelab.agents.options.AGENTS_DIR", tmp_path / "agents"):
            with patch("issuelab.agents.options.discover_agents") as mock_discover:
                mock_discover.return_value = {}
                options = create_agent_options(agent_name="gqy20")

        assert "literature-triage" in options.agents
        subagent = options.agents["literature-triage"]
        assert "Task" not in subagent.tools
        assert "Task" in options.allowed_tools


class TestEnvOptimization:
    """测试环境变量优化"""

    @patch("issuelab.config.Config.get_anthropic_env")
    def test_skip_version_check_env(self, mock_env):
        """应该设置跳过版本检查的环境变量"""
        mock_env.return_value = {}
        options = create_agent_options()
        assert "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK" in options.env
        assert options.env["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] == "true"


class TestCaching:
    """测试 Agent 选项缓存机制"""

    def test_clear_cache_function_exists(self):
        """clear_agent_options_cache 函数应该存在"""
        assert callable(clear_agent_options_cache)

    def test_cached_agent_options_function_exists(self):
        """_cached_agent_options 缓存字典应该存在"""
        # _cached_agent_options 是一个字典，不是函数
        assert isinstance(_cached_agent_options, dict)

    def test_cache_can_be_cleared(self):
        """应该能够清除缓存"""
        # 先调用一次
        options1 = create_agent_options()
        # 清除缓存
        clear_agent_options_cache()
        # 再次调用应该正常工作
        options2 = create_agent_options()
        assert options1 is not None
        assert options2 is not None

    def test_get_agent_config_for_scene(self):
        """get_agent_config_for_scene 应该返回正确的配置"""
        quick = get_agent_config_for_scene("quick")
        assert quick.max_turns == SCENE_CONFIGS["quick"].max_turns

        review = get_agent_config_for_scene("review")
        assert review.max_turns == SCENE_CONFIGS["review"].max_turns

    def test_get_agent_config_for_scene_defaults_to_review(self):
        """get_agent_config_for_scene 未知场景应该返回 review 配置"""
        config = get_agent_config_for_scene("unknown_scene")
        assert config.max_turns == SCENE_CONFIGS["review"].max_turns

    def test_create_agent_options_cache_skips_subagent_load(self, monkeypatch):
        """缓存命中时不应再次加载 subagents"""
        from issuelab.agents import options as options_mod

        options_mod.clear_agent_options_cache()

        monkeypatch.setattr(options_mod, "load_mcp_servers_for_agent", lambda *a, **k: {})
        monkeypatch.setattr(options_mod, "_skills_signature", lambda *a, **k: "skills-sig")

        # 第一次调用用于填充缓存
        _ = options_mod.create_agent_options(agent_name="moderator")

        # 缓存命中时不应再加载 subagents
        monkeypatch.setattr(
            options_mod,
            "_load_subagents_from_dir",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("subagents loaded on cache hit")),
        )

        _ = options_mod.create_agent_options(agent_name="moderator")

    def test_create_agent_options_uses_agent_overrides(self, monkeypatch):
        """agent.yml 的运行配置应覆盖默认值"""
        from issuelab.agents import options as options_mod

        options_mod.clear_agent_options_cache()

        monkeypatch.setattr(options_mod, "load_mcp_servers_for_agent", lambda *a, **k: {})
        monkeypatch.setattr(options_mod, "_skills_signature", lambda *a, **k: "skills-sig")
        monkeypatch.setattr(options_mod, "_subagents_signature_from_dir", lambda *a, **k: [])
        monkeypatch.setattr(
            options_mod,
            "get_agent_config",
            lambda *a, **k: {"max_turns": 7, "max_budget_usd": 1.5, "timeout_seconds": 42},
        )

        options = options_mod.create_agent_options(agent_name="alice")
        assert options.max_turns == 7
        assert options.max_budget_usd == 1.5

    def test_create_agent_options_feature_flags(self, monkeypatch):
        """agent.yml 功能开关应生效（默认启用）"""
        from issuelab.agents import options as options_mod

        options_mod.clear_agent_options_cache()

        monkeypatch.setattr(options_mod, "load_mcp_servers_for_agent", lambda *a, **k: {"docs": {"type": "http"}})
        monkeypatch.setattr(options_mod, "_skills_signature", lambda *a, **k: "skills-sig")
        monkeypatch.setattr(options_mod, "_subagents_signature_from_dir", lambda *a, **k: [("a.md", 1.0)])
        monkeypatch.setattr(
            options_mod,
            "get_agent_config",
            lambda *a, **k: {"enable_mcp": False, "enable_skills": False, "enable_subagents": False},
        )

        options = options_mod.create_agent_options(agent_name="alice")
        assert not any(t.startswith("mcp__") for t in options.allowed_tools)


class TestParseObserverResponse:
    """测试 Observer 响应解析"""

    def test_parse_yaml_block_scalar_trigger(self):
        """测试 YAML 块标量格式 - 触发场景"""
        response = """```yaml
analysis: |
  Issue #123 是一个新论文讨论，包含 arXiv 链接和论文模板

should_trigger: true

agent: moderator

comment: |
  @moderator 请审核这篇论文，它包含 arXiv 链接和模板

reason: |
  Issue #123 包含论文模板和 arXiv 链接，需要审核决定后续评审流程
```"""
        result = parse_observer_response(response, 123)
        assert result["should_trigger"] is True
        assert result["agent"] == "moderator"
        assert "@moderator" in result["comment"]
        assert "审核" in result["reason"]
        assert "arXiv" in result["analysis"]

    def test_parse_yaml_block_scalar_skip(self):
        """测试 YAML 块标量格式 - 跳过场景"""
        response = """```yaml
analysis: |
  Issue #456 是一个技术问题，已有 @reviewer_a 进行分析

should_trigger: false

reason: |
  该 Issue 已有合适的 Agent 参与，无需重复触发
```"""
        result = parse_observer_response(response, 456)
        assert result["should_trigger"] is False
        assert "已有" in result["reason"]

    def test_parse_yaml_simple_key_value(self):
        """测试 YAML 简单键值对格式（无代码块）"""
        # 注意：YAML 值包含 @ 时需要用引号包裹
        response = """analysis: 测试分析
should_trigger: true
agent: reviewer_a
comment: "@reviewer_a 评审"
reason: 测试原因"""
        result = parse_observer_response(response, 1)
        assert result["should_trigger"] is True
        assert result["agent"] == "reviewer_a"
        assert "@reviewer_a" in result["comment"]

    def test_parse_empty_response(self):
        """测试空响应"""
        result = parse_observer_response("", 1)
        assert result["should_trigger"] is False
        assert result["agent"] == ""
        assert result["comment"] == ""

    def test_parse_invalid_yaml(self):
        """测试无效 YAML（应返回默认值）"""
        result = parse_observer_response("这不是 YAML 格式", 1)
        assert result["should_trigger"] is False
        assert result["agent"] == ""

    def test_parse_default_comment(self):
        """测试默认触发评论"""
        response = """```yaml
analysis: 测试

should_trigger: true

agent: summarizer
```"""
        result = parse_observer_response(response, 1)
        assert result["should_trigger"] is True
        assert result["agent"] == "summarizer"
        assert "@summarizer" in result["comment"]


class TestStreamingOutput:
    """测试流式输出功能"""

    @pytest.mark.asyncio
    async def test_text_block_outputs_to_console_and_log(self):
        """TextBlock 应该输出到终端和日志"""
        from claude_agent_sdk import AssistantMessage, ResultMessage
        from claude_agent_sdk.types import TextBlock

        from issuelab.agents.executor import run_single_agent

        text_responses = ["Hello ", "World"]

        async def mock_query(*args, **kwargs):
            # 模拟 TextBlock
            for text in text_responses:
                msg = MagicMock(spec=AssistantMessage)
                msg.content = [TextBlock(text=text)]
                yield msg

            # 模拟 ResultMessage
            result = MagicMock(spec=ResultMessage)
            result.total_cost_usd = 0.01
            result.num_turns = 1
            result.session_id = "test-session"
            yield result

        with patch("issuelab.agents.executor.query", mock_query), patch("builtins.print") as mock_print:
            await run_single_agent("test prompt", "test_agent")
            # 验证 print 被调用（流式输出）
            assert mock_print.call_count >= len(text_responses)

    @pytest.mark.asyncio
    async def test_tool_use_block_outputs_to_console_and_log(self):
        """ToolUseBlock 应该输出到终端和日志"""
        from claude_agent_sdk import AssistantMessage, ResultMessage
        from claude_agent_sdk.types import ToolUseBlock

        from issuelab.agents.executor import run_single_agent

        async def mock_query(*args, **kwargs):
            # 模拟 ToolUseBlock
            tool_block = MagicMock(spec=ToolUseBlock)
            tool_block.name = "Read"
            tool_block.input = {"file_path": "/test/file.txt"}
            msg = MagicMock(spec=AssistantMessage)
            msg.content = [tool_block]
            yield msg

            # 模拟 ResultMessage
            result = MagicMock(spec=ResultMessage)
            result.total_cost_usd = 0.01
            result.num_turns = 1
            result.session_id = "test-session"
            yield result

        with patch("issuelab.agents.executor.query", mock_query), patch("builtins.print") as mock_print:
            await run_single_agent("test prompt", "test_agent")
            # 验证工具名被输出
            assert any("Read" in str(call) for call in mock_print.call_args_list)

    @pytest.mark.asyncio
    async def test_thinking_block_is_skipped(self):
        """ThinkingBlock 应该被跳过，不输出"""
        from claude_agent_sdk import AssistantMessage, ResultMessage
        from claude_agent_sdk.types import ThinkingBlock

        from issuelab.agents.executor import run_single_agent

        async def mock_query(*args, **kwargs):
            # 模拟 ThinkingBlock
            thinking_block = MagicMock(spec=ThinkingBlock)
            thinking_block.thinking = "This is private thinking"
            thinking_block.signature = "sig123"
            msg = MagicMock(spec=AssistantMessage)
            msg.content = [thinking_block]
            yield msg

            # 模拟 ResultMessage
            result = MagicMock(spec=ResultMessage)
            result.total_cost_usd = 0.01
            result.num_turns = 1
            result.session_id = "test-session"
            yield result

        with patch("issuelab.agents.executor.query", mock_query), patch("builtins.print") as mock_print:
            await run_single_agent("test prompt", "test_agent")
            # 验证 Thinking 内容没有被输出
            assert not any("This is private thinking" in str(call) for call in mock_print.call_args_list)

    @pytest.mark.asyncio
    async def test_tool_result_block_logs_only(self):
        """ToolResultBlock 应该只记录日志，不输出到终端"""
        from claude_agent_sdk import AssistantMessage, ResultMessage
        from claude_agent_sdk.types import ToolResultBlock

        from issuelab.agents.executor import run_single_agent

        async def mock_query(*args, **kwargs):
            # 模拟 ToolResultBlock
            result_block = MagicMock(spec=ToolResultBlock)
            result_block.tool_use_id = "tool-123"
            result_block.content = "Very long result content..." * 100
            result_block.is_error = False
            msg = MagicMock(spec=AssistantMessage)
            msg.content = [result_block]
            yield msg

            # 模拟 ResultMessage
            result = MagicMock(spec=ResultMessage)
            result.total_cost_usd = 0.01
            result.num_turns = 1
            result.session_id = "test-session"
            yield result

        with patch("issuelab.agents.executor.query", mock_query), patch("builtins.print") as mock_print:
            await run_single_agent("test prompt", "test_agent")
            # 验证工具结果内容没有被完整输出（避免刷屏）
            assert not any("Very long result" in str(call) for call in mock_print.call_args_list)

    @pytest.mark.asyncio
    async def test_result_message_usage_tokens_exposed(self):
        """ResultMessage usage 应该写入执行结果"""
        from claude_agent_sdk import AssistantMessage, ResultMessage
        from claude_agent_sdk.types import TextBlock

        from issuelab.agents.executor import run_single_agent

        async def mock_query(*args, **kwargs):
            msg = MagicMock(spec=AssistantMessage)
            msg.content = [TextBlock(text="ok")]
            yield msg

            result = MagicMock(spec=ResultMessage)
            result.total_cost_usd = 0.01
            result.num_turns = 1
            result.session_id = "test-session"
            result.usage = {
                "input_tokens": 123,
                "output_tokens": 45,
                "total_tokens": 168,
            }
            yield result

        with patch("issuelab.agents.executor.query", mock_query):
            info = await run_single_agent("test prompt", "test_agent")
            assert info["input_tokens"] == 123
            assert info["output_tokens"] == 45
            assert info["total_tokens"] == 168
