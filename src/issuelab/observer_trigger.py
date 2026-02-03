"""
Observer 自动触发功能

实现Observer自动触发agent的核心逻辑：
- 内置agent通过workflow dispatch触发（使用PAT_TOKEN）
- 用户agent通过repository dispatch触发（使用PAT_TOKEN）

统一使用dispatch机制，无需预创建labels，简化架构。
"""

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

# 内置agent列表
BUILTIN_AGENTS = {
    "moderator",
    "reviewer_a",
    "reviewer_b",
    "summarizer",
    "echo",
    "observer",
}


def is_builtin_agent(agent_name: str) -> bool:
    """
    判断是否是内置agent

    Args:
        agent_name: Agent名称

    Returns:
        True: 内置agent
        False: 用户agent
    """
    if not agent_name:
        return False
    return agent_name.lower() in BUILTIN_AGENTS


def trigger_builtin_agent(agent_name: str, issue_number: int) -> bool:
    """
    触发内置agent（通过workflow dispatch）

    Args:
        agent_name: Agent名称
        issue_number: Issue编号

    Returns:
        True: 触发成功
        False: 触发失败
    """
    try:
        subprocess.run(
            [
                "gh", "workflow", "run", "agent.yml",
                "-f", f"agent={agent_name.lower()}",
                "-f", f"issue_number={issue_number}"
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(f"[OK] 已触发 workflow agent.yml: agent={agent_name}, issue=#{issue_number}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"[ERROR] 触发workflow失败: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"[ERROR] 触发内置agent失败: {e}")
        return False


def trigger_user_agent(username: str, issue_number: int, issue_title: str, issue_body: str) -> bool:
    """
    触发用户agent（通过dispatch系统）

    Args:
        username: 用户名
        issue_number: Issue编号
        issue_title: Issue标题
        issue_body: Issue内容

    Returns:
        True: 触发成功
        False: 触发失败
    """
    try:
        # 调用dispatch.py的main函数
        from issuelab.cli.dispatch import main as dispatch_main

        # 获取当前仓库信息
        source_repo = os.environ.get("GITHUB_REPOSITORY", "")
        if not source_repo:
            logger.error("[ERROR] GITHUB_REPOSITORY environment variable not set")
            return False

        # 模拟命令行参数
        sys.argv = [
            "dispatch",
            "--mentions",
            username,
            "--source-repo",
            source_repo,
            "--issue-number",
            str(issue_number),
            "--issue-title",
            issue_title,
            "--issue-body",
            issue_body,
        ]

        exit_code = dispatch_main()
        if exit_code == 0:
            logger.info(f"[OK] 已触发用户agent: {username} for #{issue_number}")
            return True
        else:
            logger.error(f"[ERROR] 触发用户agent失败: {username} (exit_code={exit_code})")
            return False

    except Exception as e:
        logger.error(f"[ERROR] 触发用户agent异常: {e}")
        return False


def auto_trigger_agent(agent_name: str, issue_number: int, issue_title: str, issue_body: str) -> bool:
    """
    根据agent类型自动选择触发方式

    Args:
        agent_name: Agent名称
        issue_number: Issue编号
        issue_title: Issue标题
        issue_body: Issue内容

    Returns:
        True: 触发成功
        False: 触发失败
    """
    if is_builtin_agent(agent_name):
        return trigger_builtin_agent(agent_name, issue_number)
    else:
        return trigger_user_agent(agent_name, issue_number, issue_title, issue_body)


def process_observer_results(
    results: list[dict], issue_data: dict[int, dict], auto_trigger: bool = True
) -> int:
    """
    处理Observer批量分析结果，自动触发agent

    Args:
        results: Observer分析结果列表
        issue_data: Issue数据字典 {issue_number: {title, body}}
        auto_trigger: 是否自动触发

    Returns:
        成功触发的agent数量
    """
    if not auto_trigger:
        return 0

    triggered_count = 0

    for result in results:
        if not result.get("should_trigger", False):
            continue

        issue_number = result["issue_number"]
        agent_name = result.get("agent")

        if not agent_name:
            logger.warning(f"[WARNING] Issue #{issue_number} 缺少agent名称")
            continue

        if issue_number not in issue_data:
            logger.warning(f"[WARNING] Issue #{issue_number} 缺少数据")
            continue

        issue = issue_data[issue_number]
        success = auto_trigger_agent(
            agent_name=agent_name,
            issue_number=issue_number,
            issue_title=issue.get("title", ""),
            issue_body=issue.get("body", ""),
        )

        if success:
            triggered_count += 1

    logger.info(f"[INFO] 总计触发 {triggered_count} 个agent")
    return triggered_count
