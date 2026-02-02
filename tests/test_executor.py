"""测试并行执行器"""
import pytest
from issuelab.sdk_executor import load_prompt


def test_load_prompt_unknown_agent():
    """测试加载未知代理的提示词返回空"""
    result = load_prompt("nonexistent")
    assert result == ""


def test_load_prompt_known_agent():
    """测试加载已知代理的提示词"""
    result = load_prompt("moderator")
    # 现在 prompts 目录存在，应该返回非空内容
    assert result != ""
    assert "Moderator" in result
