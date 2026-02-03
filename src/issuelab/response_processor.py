"""
Agent Response 后处理：解析 @mentions 并触发 dispatch

解决bot评论无法触发workflow的问题：
- agent执行完成后主动解析response中的@mentions
- 自动触发被@的用户agent
"""

import logging
import os
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def extract_mentions(text: str) -> list[str]:
    """
    从文本中提取所有@mentions

    Args:
        text: 文本内容

    Returns:
        被@的用户名列表（去重）

    Examples:
        >>> extract_mentions("Hi @alice and @bob")
        ['alice', 'bob']
        >>> extract_mentions("@gqy22 please review")
        ['gqy22']
        >>> extract_mentions("No mentions here")
        []
    """
    if not text:
        return []

    # 正则匹配 @username（支持字母、数字、下划线、连字符）
    pattern = r"@([a-zA-Z0-9_-]+)"
    matches = re.findall(pattern, text)

    # 去重并返回
    return list(dict.fromkeys(matches))


def trigger_mentioned_agents(
    response: str, issue_number: int, issue_title: str, issue_body: str
) -> dict[str, bool]:
    """
    解析agent response中的@mentions并触发对应的agent

    Args:
        response: Agent的response内容
        issue_number: Issue编号
        issue_title: Issue标题
        issue_body: Issue内容

    Returns:
        触发结果字典 {username: success}
    """
    mentions = extract_mentions(response)

    if not mentions:
        logger.info("[INFO] Response中没有@mentions")
        return {}

    logger.info(f"[INFO] 发现 {len(mentions)} 个@mentions: {mentions}")

    from issuelab.observer_trigger import auto_trigger_agent

    results = {}
    for username in mentions:
        # 排除常见的非agent mentions（如GitHub bot账号）
        if username.lower() in ["github", "github-actions", "dependabot"]:
            logger.info(f"[SKIP] 跳过系统账号: {username}")
            continue

        logger.info(f"[INFO] 触发被@的agent: {username}")
        success = auto_trigger_agent(
            agent_name=username,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
        )
        results[username] = success

        if success:
            logger.info(f"[OK] 成功触发 {username}")
        else:
            logger.error(f"[ERROR] 触发 {username} 失败")

    return results


def process_agent_response(
    agent_name: str,
    response: str | dict[str, Any],
    issue_number: int,
    issue_title: str = "",
    issue_body: str = "",
    auto_dispatch: bool = True,
) -> dict[str, Any]:
    """
    处理agent response的后处理逻辑

    Args:
        agent_name: Agent名称
        response: Agent的response（字符串或dict）
        issue_number: Issue编号
        issue_title: Issue标题
        issue_body: Issue内容
        auto_dispatch: 是否自动触发@mentions

    Returns:
        处理结果 {
            "agent_name": str,
            "response": str,
            "mentions": list[str],
            "dispatch_results": dict[str, bool]
        }
    """
    # 提取response文本
    response_text = response.get("response", str(response)) if isinstance(response, dict) else str(response)

    # 解析@mentions
    mentions = extract_mentions(response_text)

    result = {
        "agent_name": agent_name,
        "response": response_text,
        "mentions": mentions,
        "dispatch_results": {},
    }

    # 自动触发被@的agents
    if auto_dispatch and mentions:
        logger.info(f"🔗 {agent_name} 的response中@了 {len(mentions)} 个用户")
        result["dispatch_results"] = trigger_mentioned_agents(
            response_text, issue_number, issue_title, issue_body
        )

    return result


def should_auto_close(response_text: str, agent_name: str) -> bool:
    """
    检查是否应该自动关闭Issue

    规则：
    - 仅限 summarizer 可触发自动关闭
    - 响应中必须包含 [CLOSE] 标记

    Args:
        response_text: Agent的response内容
        agent_name: Agent名称

    Returns:
        是否应该关闭
    """
    if agent_name != "summarizer":
        return False

    if not response_text:
        return False

    # 检测 [CLOSE] 标记
    return "[CLOSE]" in response_text


def close_issue(issue_number: int) -> bool:
    """
    关闭 Issue

    Args:
        issue_number: Issue编号

    Returns:
        是否成功关闭
    """
    try:
        result = subprocess.run(
            ["gh", "issue", "close", str(issue_number), "--repo", os.environ.get("GITHUB_REPOSITORY", ""), "--reason", "completed"],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if result.returncode == 0:
            logger.info(f"[OK] Issue #{issue_number} 已自动关闭")
            return True
        else:
            logger.error(f"[ERROR] 关闭 Issue #{issue_number} 失败: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"[ERROR] 关闭 Issue #{issue_number} 异常: {e}")
        return False
