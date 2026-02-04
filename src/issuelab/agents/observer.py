"""Observer Agent 专用执行逻辑

处理 Observer Agent 的特殊执行场景和批处理。
"""

import anyio

from issuelab.agents.discovery import discover_agents, get_agent_matrix_markdown
from issuelab.agents.executor import run_single_agent
from issuelab.agents.parsers import parse_observer_response, parse_papers_recommendation
from issuelab.collaboration import build_collaboration_guidelines
from issuelab.logging_config import get_logger

logger = get_logger(__name__)


async def run_observer(issue_number: int, issue_title: str = "", issue_body: str = "", comments: str = "") -> dict:
    """运行 Observer Agent

    Observer Agent 会分析 Issue 并决定是否需要触发其他 Agent。

    Args:
        issue_number: Issue 编号
        issue_title: Issue 标题
        issue_body: Issue 内容
        comments: 历史评论

    Returns:
        {
            "should_trigger": bool,
            "agent": str,  # 要触发的 Agent 名称
            "comment": str,  # 触发评论内容
            "reason": str,  # 触发理由
            "analysis": str,  # Issue 分析
        }
    """
    agents = discover_agents()
    observer_config = agents.get("observer", {})

    if not observer_config:
        return {
            "should_trigger": False,
            "error": "Observer agent not found",
        }

    # 获取 prompt（移除 frontmatter）
    prompt_template = observer_config["prompt"]
    lines = prompt_template.split("\n")
    content_lines = []
    in_frontmatter = False
    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if not in_frontmatter:
            content_lines.append(line)
    prompt = "\n".join(content_lines)

    # Issue 分析模式任务说明
    issue_task = """请分析以下 GitHub Issue 并决定是否需要触发其他 Agent：

**Issue 编号**: __ISSUE_NUMBER__

**Issue 标题**: __ISSUE_TITLE__

**Issue 内容**:
__ISSUE_BODY__

**历史评论**:
__COMMENTS__"""

    # 使用唯一的占位符标记替换
    prompt = prompt.replace("__TASK_SECTION__", issue_task)
    prompt = prompt.replace("__ISSUE_NUMBER__", str(issue_number))
    prompt = prompt.replace("__ISSUE_TITLE__", issue_title)
    prompt = prompt.replace("__ISSUE_BODY__", issue_body or "无内容")
    prompt = prompt.replace("__COMMENTS__", comments or "无评论")

    # 注入协作指南：Observer 不在 prompt 文件里维护专家列表，而是统一注入。
    # 这里用动态生成的 Agent Matrix 表格替代 {available_agents}，提供触发条件信息。
    collaboration_guidelines = build_collaboration_guidelines(
        agents,
        available_agents_placeholder=get_agent_matrix_markdown(),
    )
    if collaboration_guidelines and "## 协作指南" not in prompt:
        marker = "\n## 当前任务\n"
        if marker in prompt:
            prompt = prompt.replace(marker, f"\n\n{collaboration_guidelines}{marker}", 1)
        else:
            prompt = f"{prompt}\n\n{collaboration_guidelines}"

    logger.info(f"[Observer] 开始分析 Issue #{issue_number}")
    logger.debug(f"[Observer] Title: {issue_title[:50]}...")

    result = await run_single_agent(prompt, "observer")

    # 解析响应（从 dict 中提取 response 字段）
    response_text = result.get("response", "")
    logger.debug(f"[Observer] 响应长度: {len(response_text)} 字符")

    # 解析响应
    decision = parse_observer_response(response_text, issue_number)
    decision["cost_usd"] = result.get("cost_usd", 0.0)
    decision["num_turns"] = result.get("num_turns", 0)

    return decision


async def run_observer_batch(issue_data_list: list[dict]) -> list[dict]:
    """并行运行 Observer Agent 分析多个 Issues

    Args:
        issue_data_list: Issue 数据列表，每个元素包含:
            {
                "issue_number": int,
                "issue_title": str,
                "issue_body": str,
                "comments": str,
            }

    Returns:
        分析结果列表，每个元素包含 issue_number 和决策结果
    """
    logger.info(f"开始并行分析 {len(issue_data_list)} 个 Issues")

    results = []

    async with anyio.create_task_group() as tg:

        async def analyze_one(issue_data: dict):
            issue_number = issue_data["issue_number"]
            try:
                result = await run_observer(
                    issue_number=issue_number,
                    issue_title=issue_data.get("issue_title", ""),
                    issue_body=issue_data.get("issue_body", ""),
                    comments=issue_data.get("comments", ""),
                )
                result["issue_number"] = issue_number
                results.append(result)
                logger.info(f"Issue #{issue_number} 分析完成: should_trigger={result.get('should_trigger')}")
            except Exception as e:
                logger.error(f"Issue #{issue_number} 分析失败: {e}", exc_info=True)
                results.append(
                    {
                        "issue_number": issue_number,
                        "should_trigger": False,
                        "error": str(e),
                    }
                )

        for issue_data in issue_data_list:
            tg.start_soon(analyze_one, issue_data)

    logger.info(f"并行分析完成，总计 {len(results)} 个结果")
    return results


def build_papers_for_observer(papers: list[dict]) -> str:
    """构建供 Observer 分析的论文上下文

    Args:
        papers: 论文列表

    Returns:
        格式化的论文上下文字符串
    """
    lines = ["## 可讨论的 arXiv 论文候选\n"]

    for i, paper in enumerate(papers):
        lines.append(f"### 论文 {i}")
        lines.append(f"**标题**: {paper.get('title', '')}")
        lines.append(f"**分类**: {paper.get('category', '')}")
        lines.append(f"**发布时间**: {paper.get('published', '')}")
        lines.append(f"**链接**: [{paper.get('url', '')}]({paper.get('url', '')})")
        lines.append(f"**作者**: {paper.get('authors', '')}")
        lines.append(f"**摘要**: {paper.get('summary', '')}")
        lines.append("")

    return "\n".join(lines)


def build_pubmed_papers_for_observer(papers: list[dict], query: str) -> str:
    """构建供 PubMed Observer 分析的文献上下文

    Args:
        papers: 文献列表
        query: 检索词

    Returns:
        格式化的文献上下文字符串
    """
    lines = [
        "## PubMed 文献候选\n",
        f"**检索词**: {query}\n",
        f"**候选数量**: {len(papers)} 篇\n",
        "---\n",
    ]

    for i, paper in enumerate(papers):
        lines.append(f"### 文献 {i}")
        lines.append(f"**PMID**: [{paper.get('pmid', '')}]({paper.get('url', '')})")
        lines.append(f"**标题**: {paper.get('title', '')}")
        lines.append(f"**期刊**: {paper.get('journal', '')}")
        lines.append(f"**发表日期**: {paper.get('pubdate', '')}")
        if paper.get("epubdate"):
            lines.append(f"**在线发表**: {paper.get('epubdate', '')}")
        if paper.get("entrezdate"):
            lines.append(f"**入库日期**: {paper.get('entrezdate', '')}")
        lines.append(f"**作者**: {paper.get('authors', '')}")
        keywords = paper.get("keywords", [])
        if keywords:
            lines.append(f"**关键词**: {', '.join(keywords[:5])}")
        lines.append("")

    return "\n".join(lines)


async def run_observer_for_papers(papers: list[dict], return_result: bool = False) -> list[dict] | tuple[list[dict], dict]:
    """运行 arxiv_observer 分析 arXiv 论文列表

    Args:
        papers: 论文列表，每个论文包含:
            - id, title, summary, url, pdf_url
            - authors, published, category

    Returns:
        推荐论文列表（从 papers 中筛选出的论文）
    """
    if not papers:
        return []

    agents = discover_agents()
    arxiv_observer_config = agents.get("arxiv_observer", {})

    if not arxiv_observer_config:
        logger.error("arxiv_observer agent not found")
        return []

    # 构建论文上下文
    papers_context = build_papers_for_observer(papers)

    # 获取 prompt（移除 frontmatter）
    prompt_template = arxiv_observer_config["prompt"]
    lines = prompt_template.split("\n")
    content_lines = []
    in_frontmatter = False
    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if not in_frontmatter:
            content_lines.append(line)
    prompt = "\n".join(content_lines)

    # 替换占位符
    prompt = prompt.replace("__PAPERS_CONTEXT__", papers_context)

    # 注入协作指南（对 arxiv_observer 也生效）
    collaboration_guidelines = build_collaboration_guidelines(agents)
    if collaboration_guidelines and "## 协作指南" not in prompt:
        prompt = f"{prompt}\n\n{collaboration_guidelines}"

    logger.info(f"[arxiv_observer] 开始分析 {len(papers)} 篇候选论文")

    # 调用 arxiv_observer agent
    result = await run_single_agent(prompt, "arxiv_observer")

    # 解析响应
    response_text = result.get("response", "")
    logger.debug(f"[arxiv_observer] 响应长度: {len(response_text)} 字符")

    # 解析推荐结果
    recommended_indices = parse_papers_recommendation(response_text, len(papers))

    # 从原始论文数据中获取完整信息
    recommended_papers = []
    for item in recommended_indices:
        idx = item["index"]
        if 0 <= idx < len(papers):
            paper = papers[idx].copy()
            paper["reason"] = item.get("reason", "")
            paper["summary"] = item.get("summary", paper.get("summary", ""))
            recommended_papers.append(paper)

    logger.info(f"[arxiv_observer] 推荐 {len(recommended_papers)} 篇论文")
    if return_result:
        return recommended_papers, result
    return recommended_papers


async def run_pubmed_observer_for_papers(
    papers: list[dict], query: str, return_result: bool = False
) -> list[dict] | tuple[list[dict], dict]:
    """运行 pubmed_observer 分析 PubMed 文献列表

    Args:
        papers: 文献列表
        query: 检索词

    Returns:
        推荐文献列表（从 papers 中筛选出的文献）
    """
    if not papers:
        return []

    agents = discover_agents()
    pubmed_observer_config = agents.get("pubmed_observer", {})

    if not pubmed_observer_config:
        logger.error("pubmed_observer agent not found")
        return []

    # 构建文献上下文
    papers_context = build_pubmed_papers_for_observer(papers, query)

    # 获取 prompt（移除 frontmatter）
    prompt_template = pubmed_observer_config["prompt"]
    lines = prompt_template.split("\n")
    content_lines = []
    in_frontmatter = False
    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if not in_frontmatter:
            content_lines.append(line)
    prompt = "\n".join(content_lines)

    # 替换占位符
    prompt = prompt.replace("__PAPERS_CONTEXT__", papers_context)

    # 注入协作指南
    collaboration_guidelines = build_collaboration_guidelines(agents)
    if collaboration_guidelines and "## 协作指南" not in prompt:
        prompt = f"{prompt}\n\n{collaboration_guidelines}"

    logger.info(f"[pubmed_observer] 开始分析 {len(papers)} 篇候选文献")

    # 调用 pubmed_observer agent
    result = await run_single_agent(prompt, "pubmed_observer")

    # 解析响应
    response_text = result.get("response", "")
    logger.debug(f"[pubmed_observer] 响应长度: {len(response_text)} 字符")

    # 解析推荐结果
    recommended_indices = parse_papers_recommendation(response_text, len(papers))

    # 从原始文献数据中获取完整信息
    recommended_papers = []
    for item in recommended_indices:
        idx = item["index"]
        if 0 <= idx < len(papers):
            paper = papers[idx].copy()
            paper["reason"] = item.get("reason", "")
            paper["summary"] = item.get("summary", "")
            recommended_papers.append(paper)

    logger.info(f"[pubmed_observer] 推荐 {len(recommended_papers)} 篇文献")
    if return_result:
        return recommended_papers, result
    return recommended_papers
