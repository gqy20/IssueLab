"""
个人Agent扫描模块

用于fork仓库的用户，让他们的个人agent分析主仓库的issues，
选择感兴趣的话题进行参与
"""

import asyncio
import json
import logging
import re
import subprocess
from typing import Any

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
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "title,body,labels,comments"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
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
            ["gh", "api", f"/repos/{repo}/issues/{issue_number}/comments", "--jq", f".[] | select(.user.login==\"{username}\") | .id"],
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


def select_top_issues(
    candidates: list[dict[str, Any]], max_count: int = 3
) -> list[dict[str, Any]]:
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
    max_replies: int = 3
) -> dict[str, Any]:
    """使用LLM智能选择Issues（异步版本）"""
    from claude_agent_sdk import query
    from issuelab.agents.options import create_agent_options
    
    # 构建prompt
    issues_text = "\n---\n".join([
        f"#{i['number']}: {i.get('title', '')}\n{(i.get('body', '') or '')[:500]}"
        for i in issues_data
    ])
    
    prompt = f"""你是Issue筛选助手。根据Agent信息选择最合适的{max_replies}个Issue。

## Agent信息
- 角色: {agent_config.get('description', 'N/A')}
- 简介: {agent_config.get('bio', 'N/A')}
- 兴趣: {agent_config.get('interests', [])}

## 候选Issues ({len(issues_data)}个)
{issues_text}

## 输出要求
严格输出JSON（不要markdown代码块）：
{{"selected_issues": [21], "selections": [{{"issue_number": 21, "priority": 9, "reason": "原因"}}], "reasoning": "说明"}}

选择标准：主题相关、价值匹配、能提供独特见解。输出JSON："""

    # 调用智能体
    logger.info("[LLM] 调用智能体分析...")
    response_text = ""
    options = create_agent_options()
    
    async for message in query(prompt=prompt, options=options):
        if hasattr(message, 'content'):
            for block in message.content:
                if hasattr(block, 'text'):
                    response_text += block.text
    
    # 解析JSON
    text = re.sub(r'```(?:json)?\s*', '', response_text)  # 去除markdown
    match = re.search(r'\{.*\}', text, re.DOTALL)
    
    if not match:
        logger.error(f"未找到JSON: {text[:200]}")
        return {"selected_issues": [], "selections": [], "reasoning": "解析失败"}
    
    try:
        result = json.loads(match.group(0))
        logger.info(f"[LLM] 选择了 {len(result.get('selected_issues', []))} 个Issue")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
        return {"selected_issues": [], "selections": [], "reasoning": f"错误: {e}"}


def llm_select_issues(agent_config: dict, issues_data: list[dict], max_replies: int = 3) -> dict:
    """使用LLM智能选择Issues（同步版本）"""
    return asyncio.run(llm_select_issues_async(agent_config, issues_data, max_replies))


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
        
        candidates_data.append({
            "number": issue_num,
            "title": issue_data.get("title", ""),
            "body": issue_data.get("body", ""),
            "labels": issue_data.get("labels", []),
        })
    
    # 使用LLM或关键词匹配
    if USE_LLM_SCAN and candidates_data:
        logger.info("📊 使用LLM智能分析...")
        try:
            result = llm_select_issues(agent_config, candidates_data, max_replies)
            
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
        
        candidates.append({
            "issue_number": candidate["number"],
            "title": candidate["title"],
            "interested": analysis["interested"],
            "reason": analysis["reason"],
            "priority": analysis["priority"],
        })
        
        if analysis["interested"]:
            logger.info(f"[OK] Issue #{candidate['number']}: {candidate['title'][:50]}... (优先级: {analysis['priority']})")
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
