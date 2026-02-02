"""测试 SDK 执行器"""
import pytest
from issuelab.sdk_executor import (
    create_agent_options,
    load_prompt,
)


def test_create_agent_options_has_agents():
    """create_agent_options 应该包含所有定义的代理"""
    options = create_agent_options()
    assert hasattr(options, 'agents')
    assert 'moderator' in options.agents
    assert 'reviewer_a' in options.agents
    assert 'reviewer_b' in options.agents
    assert 'summarizer' in options.agents


def test_create_agent_options_has_setting_sources():
    """create_agent_options 应该设置 setting_sources"""
    options = create_agent_options()
    assert hasattr(options, 'setting_sources')
    assert "user" in options.setting_sources
    assert "project" in options.setting_sources


def test_load_prompt_moderator():
    """load_prompt 应该加载 moderator 提示词"""
    result = load_prompt("moderator")
    assert "Moderator" in result


def test_load_prompt_unknown_agent():
    """load_prompt 对未知代理返回空"""
    result = load_prompt("unknown_agent")
    assert result == ""
