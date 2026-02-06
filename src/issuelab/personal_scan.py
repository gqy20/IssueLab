"""
个人Agent扫描模块

用于fork仓库的用户，让他们的个人agent分析主仓库的issues，
选择感兴趣的话题进行参与
"""

import asyncio
import logging
import re
import subprocess
from typing import Any

import yaml

from issuelab.agents.executor import run_single_agent_text
from issuelab.tools.github import get_issue_info

logger = logging.getLogger(__name__)

# LLM智能扫描开关
USE_LLM_SCAN = True  # True=使用LLM智能分析, False=使用关键词匹配


def get_issue_content(issue_number: int, repo: str) -> dict[str, Any] | None:
    """
    获取issue内容（从主仓库）

    Args:
        issue_number: Issue编号
        repo: 仓库名称 (owner/repo)

    Returns:
        Issue数据或None
    """
    try:
        return get_issue_info(issue_number, format_comments=False, repo=repo)
    except Exception as e:
        logger.error(f"[ERROR] 获取Issue #{issue_number}失败: {e}")
        return None


def check_already_commented(issue_number: int, repo: str, username: str) -> bool:
    """
    检查用户是否已经评论过这个issue

    Args:
        issue_number: Issue编号
        repo: 仓库名称
        username: 用户名

    Returns:
        True: 已评论, False: 未评论
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"/repos/{repo}/issues/{issue_number}/comments",
                "--jq",
                f'.[] | select(.user.login=="{username}") | .id',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        # 如果有输出，说明已经评论过
        return bool(result.stdout.strip())
    except Exception as e:
        logger.warning(f"[WARNING] 检查评论状态失败: {e}")
        return False  # 默认未评论


def analyze_issue_interest(
    agent_name: str, issue_number: int, issue_title: str, issue_body: str, agent_config: dict[str, Any]
) -> dict[str, Any]:
    """
    让agent分析是否对这个issue感兴趣

    Args:
        agent_name: Agent名称
        issue_number: Issue编号
        issue_title: Issue标题
        issue_body: Issue内容
        agent_config: Agent配置

    Returns:
        {
            "interested": bool,
            "reason": str,
            "priority": int (1-10)
        }
    """
    # 获取agent的兴趣关键词
    interests = agent_config.get("interests", [])
    if isinstance(interests, str):
        interests = [interests]

    # 简单的关键词匹配（可以后续升级为LLM判断）
    text = f"{issue_title}\n{issue_body}".lower()

    interest_score = 0
    matched_keywords = []

    for keyword in interests:
        if keyword.lower() in text:
            interest_score += 1
            matched_keywords.append(keyword)

    # 判断是否感兴趣
    interested = interest_score > 0

    reason = ""
    reason = f"匹配到关键词: {', '.join(matched_keywords)}" if interested else "未匹配到感兴趣的关键词"

    return {"interested": interested, "reason": reason, "priority": min(interest_score, 10)}


def select_top_issues(candidates: list[dict[str, Any]], max_count: int = 3) -> list[dict[str, Any]]:
    """
    从候选issues中选择top N个

    Args:
        candidates: 候选issue列表
        max_count: 最大数量

    Returns:
        选中的issues
    """
    # 按priority排序
    sorted_candidates = sorted(candidates, key=lambda x: x.get("priority", 0), reverse=True)

    # 只选择interested=True的
    interested = [c for c in sorted_candidates if c.get("interested", False)]

    # 限制数量
    return interested[:max_count]


async def llm_select_issues_async(
    agent_config: dict[str, Any],
    issues_data: list[dict[str, Any]],
    max_replies: int = 3,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """使用LLM智能选择Issues（异步版本）"""
    # 构建prompt
    issues_text = "\n---\n".join(
        [f"#{i['number']}: {i.get('title', '')}\n{(i.get('body', '') or '')[:500]}" for i in issues_data]
    )

    prompt = f"""你是Issue筛选助手。根据Agent信息选择最合适的{max_replies}个Issue。

## Agent信息
- 角色: {agent_config.get("description", "N/A")}
- 简介: {agent_config.get("bio", "N/A")}
- 兴趣: {agent_config.get("interests", [])}

## 候选Issues ({len(issues_data)}个)
{issues_text}

## Output Format (required)
请严格输出以下 YAML（仅输出一个 YAML 代码块，不要附加解释）：

```yaml
selected_issues:
  - 21
selections:
  - issue_number: 21
    priority: 9
    reason: "原因"
reasoning: "说明"
```

选择标准：主题相关、价值匹配、能提供独特见解。现在开始输出："""

    # 调用智能体
    logger.info("[LLM] 调用智能体分析...")
    response_text = await run_single_agent_text(prompt, agent_name=agent_name or "personal_scan")
    if response_text.strip().startswith("[错误]") or "执行失败" in response_text:
        logger.error(f"LLM 执行失败: {response_text.strip()}")
        return {"selected_issues": [], "selections": [], "reasoning": "LLM 执行失败"}

    # 解析YAML（统一输出格式）
    match = re.search(r"```yaml(.*?)```", response_text, re.DOTALL | re.IGNORECASE)
    yaml_text = match.group(1).strip() if match else response_text.strip()

    try:
        parsed = yaml.safe_load(yaml_text)
        if not isinstance(parsed, dict):
            logger.error(f"YAML解析结果非对象: {type(parsed)}")
            return {"selected_issues": [], "selections": [], "reasoning": "解析失败"}
    except yaml.YAMLError as e:
        logger.error(f"YAML解析错误: {e}")
        return {"selected_issues": [], "selections": [], "reasoning": f"错误: {e}"}

    selected = parsed.get("selected_issues", [])
    selections = parsed.get("selections", [])
    reasoning = parsed.get("reasoning", "")

    # 规范化字段
    if isinstance(selections, list) and not selected:
        selected = [item.get("issue_number") for item in selections if isinstance(item, dict)]
    if not isinstance(selected, list):
        selected = []
    selected_numbers = []
    for item in selected:
        try:
            selected_numbers.append(int(item))
        except (TypeError, ValueError):
            continue

    if not isinstance(selections, list):
        selections = []

    result = {
        "selected_issues": selected_numbers,
        "selections": selections,
        "reasoning": reasoning if isinstance(reasoning, str) else str(reasoning),
    }
    logger.info(f"[LLM] 选择了 {len(result.get('selected_issues', []))} 个Issue (YAML)")
    return result


def llm_select_issues(
    agent_config: dict,
    issues_data: list[dict],
    max_replies: int = 3,
    agent_name: str | None = None,
) -> dict:
    """使用LLM智能选择Issues（同步版本）"""
    return asyncio.run(llm_select_issues_async(agent_config, issues_data, max_replies, agent_name=agent_name))


def scan_issues_for_personal_agent(
    agent_name: str,
    agent_config: dict[str, Any],
    issue_numbers: list[int],
    repo: str,
    max_replies: int = 3,
    username: str = "",
) -> dict[str, Any]:
    """
    使用个人agent扫描issues

    Args:
        agent_name: Agent名称
        agent_config: Agent配置
        issue_numbers: 候选issue编号列表
        repo: 主仓库名称
        max_replies: 最多回复数量
        username: 用户名（用于检查是否已评论）

    Returns:
        {
            "agent_name": str,
            "total_scanned": int,
            "candidates": list[dict],
            "selected_issues": list[int]
        }
    """
    logger.info(f"🔍 开始扫描 {len(issue_numbers)} 个issues...")

    # 收集所有候选Issues
    candidates_data = []
    for issue_num in issue_numbers:
        issue_data = get_issue_content(issue_num, repo)
        if not issue_data:
            continue

        # 检查是否已评论
        if username and check_already_commented(issue_num, repo, username):
            logger.info(f"[SKIP] Issue #{issue_num} 已评论过，跳过")
            continue

        candidates_data.append(
            {
                "number": issue_num,
                "title": issue_data.get("title", ""),
                "body": issue_data.get("body", ""),
                "labels": issue_data.get("labels", []),
            }
        )

    # 使用LLM或关键词匹配
    if USE_LLM_SCAN and candidates_data:
        logger.info("📊 使用LLM智能分析...")
        try:
            result = llm_select_issues(agent_config, candidates_data, max_replies, agent_name=agent_name)

            selected_numbers = result.get("selected_issues", [])
            selected_details = result.get("selections", [])

            logger.info(f"[LLM] 选择: {selected_numbers}")
            logger.info(f"[LLM] 理由: {result.get('reasoning', 'N/A')[:150]}...")

            return {
                "agent_name": agent_name,
                "total_scanned": len(candidates_data),
                "selected_issues": selected_numbers,
                "selected_details": selected_details,
                "reasoning": result.get("reasoning", ""),
                "method": "llm",
            }
        except Exception as e:
            logger.error(f"[ERROR] LLM分析失败: {e}，回退到关键词匹配")
            # 继续使用关键词匹配

    # 关键词匹配模式（原逻辑）
    logger.info("📊 使用关键词匹配...")
    candidates = []

    for candidate in candidates_data:
        analysis = analyze_issue_interest(
            agent_name=agent_name,
            issue_number=candidate["number"],
            issue_title=candidate["title"],
            issue_body=candidate["body"],
            agent_config=agent_config,
        )

        candidates.append(
            {
                "issue_number": candidate["number"],
                "title": candidate["title"],
                "interested": analysis["interested"],
                "reason": analysis["reason"],
                "priority": analysis["priority"],
            }
        )

        if analysis["interested"]:
            logger.info(
                f"[OK] Issue #{candidate['number']}: {candidate['title'][:50]}... (优先级: {analysis['priority']})"
            )
        else:
            logger.info(f"[SKIP] Issue #{candidate['number']}: {analysis['reason']}")

    selected = select_top_issues(candidates, max_replies)
    selected_numbers = [s["issue_number"] for s in selected]

    logger.info(f"[INFO] 总扫描: {len(candidates)}, 感兴趣: {len(selected)}")

    return {
        "agent_name": agent_name,
        "total_scanned": len(candidates),
        "candidates": candidates,
        "selected_issues": selected_numbers,
        "selected_details": selected,
        "method": "keyword",
    }
