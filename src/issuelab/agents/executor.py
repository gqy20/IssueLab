"""Agent 执行器核心

处理 Agent 的执行、消息流和日志记录。
"""

import anyio
import os
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)

from issuelab.agents.options import create_agent_options, format_mcp_servers_for_prompt
from issuelab.logging_config import get_logger
from issuelab.retry import retry_async

logger = get_logger(__name__)


async def run_single_agent(prompt: str, agent_name: str) -> dict:
    """运行单个代理（带完善的中间日志监听）

    Args:
        prompt: 用户提示词
        agent_name: 代理名称

    Returns:
        {
            "response": str,  # 代理响应文本
            "cost_usd": float,  # 成本（美元）
            "num_turns": int,  # 对话轮数
            "tool_calls": list[str],  # 工具调用列表
            "local_id": str,  # 会话 ID
        }
    """
    logger.info(f"[{agent_name}] 开始运行 Agent")
    logger.debug(f"[{agent_name}] Prompt 长度: {len(prompt)} 字符")

    # 执行信息收集
    execution_info = {
        "response": "",
        "cost_usd": 0.0,
        "num_turns": 0,
        "tool_calls": [],
        "local_id": "",
        "text_blocks": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    async def _query_agent():
        options = create_agent_options(agent_name=agent_name)
        response_text = []
        turn_count = 0
        tool_calls = []
        first_result = True

        async for message in query(prompt=prompt, options=options):
            # AssistantMessage: AI 响应（文本或工具调用）
            if isinstance(message, AssistantMessage):
                turn_count += 1
                logger.debug(f"[{agent_name}] 收到消息 (第 {turn_count} 轮)")

                for block in message.content:
                    # 文本块 → 终端流式输出 + INFO 日志
                    if isinstance(block, TextBlock):
                        text = block.text
                        response_text.append(text)
                        execution_info["text_blocks"].append(text)

                        # 终端流式输出
                        print(text, end="", flush=True)
                        # 日志记录（INFO 级别）
                        logger.info(f"[{agent_name}] [Text] {text[:100]}...")

                    # 思考块 → 输出思考过程
                    elif isinstance(block, ThinkingBlock):
                        thinking = getattr(block, "thinking", "")
                        if thinking:
                            thinking_preview = thinking[:200] + "..." if len(thinking) > 200 else thinking
                            logger.debug(f"[{agent_name}] [Thinking] {thinking_preview}")

                    # 工具调用块 → 终端显示 + INFO 日志
                    elif isinstance(block, ToolUseBlock):
                        tool_name = block.name
                        tool_use_id = getattr(block, "tool_use_id", "")
                        tool_input = getattr(block, "input", {})
                        tool_calls.append(tool_name)
                        execution_info["tool_calls"].append(tool_name)

                        # 终端输出
                        print(f"\n[{tool_name}] id={tool_use_id}", end="", flush=True)
                        if tool_name == "Skill" or tool_name.startswith("Skill"):
                            logger.info(f"[{agent_name}] [Skill] {tool_name}(id={tool_use_id})")
                        if tool_name == "Task":
                            logger.info(f"[{agent_name}] [Subagent] Task(id={tool_use_id})")
                        # 详细日志输出
                        if isinstance(tool_input, dict):
                            import json

                            input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)
                            logger.info(f"[{agent_name}] [Tool] {tool_name}(id={tool_use_id})")
                            logger.debug(f"[{agent_name}] [ToolInput] {input_str}")
                        else:
                            logger.info(f"[{agent_name}] [Tool] {tool_name}(id={tool_use_id})")

                    # 工具结果块 → 只日志，不终端输出
                    elif isinstance(block, ToolResultBlock):
                        tool_use_id = getattr(block, "tool_use_id", "")
                        is_error = getattr(block, "is_error", False)
                        result = getattr(block, "result", "")
                        # 限制结果长度，避免日志过多
                        if isinstance(result, str) and len(result) > 500:
                            logger.info(f"[{agent_name}] [ToolResult] id={tool_use_id} error={is_error} (truncated)")
                            logger.debug(f"[{agent_name}] [ToolResult] id={tool_use_id}:\n{result[:500]}...")
                        else:
                            logger.info(f"[{agent_name}] [ToolResult] id={tool_use_id} error={is_error}")
                            if result:
                                logger.debug(f"[{agent_name}] [ToolResult] id={tool_use_id}: {result}")

            # ResultMessage: 执行结果（成本、统计信息）
            elif isinstance(message, ResultMessage):
                # 打印统计信息
                print("\n")
                session_id = message.session_id or ""
                cost_usd = message.total_cost_usd or 0.0
                result_turns = message.num_turns or turn_count
                usage = message.usage or {}
                input_tokens = int(usage.get("input_tokens") or 0)
                output_tokens = int(usage.get("output_tokens") or 0)
                total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))

                execution_info["session_id"] = session_id
                execution_info["cost_usd"] = cost_usd
                execution_info["num_turns"] = result_turns
                execution_info["input_tokens"] = input_tokens
                execution_info["output_tokens"] = output_tokens
                execution_info["total_tokens"] = total_tokens

                # 只在第一次收到 ResultMessage 时记录
                if first_result:
                    logger.info(f"[{agent_name}] [Result] session_id={session_id}")
                    first_result = False

                # 日志记录成本和统计
                stats_line = (
                    f"[{agent_name}] [Stats] 成本: ${cost_usd:.4f}, 轮数: {result_turns}, 工具调用: {len(tool_calls)}"
                )
                if input_tokens or output_tokens or total_tokens:
                    stats_line += f", 输入Token: {input_tokens}, 输出Token: {output_tokens}, 总Token: {total_tokens}"
                logger.info(stats_line)

        result = "\n".join(response_text)
        return result

    try:
        response = await retry_async(_query_agent, max_retries=3, initial_delay=2.0, backoff_factor=2.0)
        execution_info["response"] = response

        # 最终日志
        logger.info(
            f"[{agent_name}] 完成 - "
            f"响应长度: {len(response)} 字符, "
            f"成本: ${execution_info['cost_usd']:.4f}, "
            f"轮数: {execution_info['num_turns']}, "
            f"工具调用: {len(execution_info['tool_calls'])}, "
            f"输入Token: {execution_info['input_tokens']}, "
            f"输出Token: {execution_info['output_tokens']}, "
            f"总Token: {execution_info['total_tokens']}"
        )

        return execution_info
    except Exception as e:
        logger.error(f"[{agent_name}] 运行失败: {e}", exc_info=True)
        return {
            "response": f"[错误] Agent {agent_name} 执行失败: {e}",
            "cost_usd": 0.0,
            "num_turns": 0,
            "tool_calls": [],
            "session_id": "",
            "text_blocks": [],
        }


async def run_single_agent_text(prompt: str, agent_name: str | None = None) -> str:
    """轻量封装：只返回响应文本"""
    name = agent_name or "default"
    result = await run_single_agent(prompt, name)
    return result.get("response", "")


async def run_agents_parallel(
    issue_number: int,
    agents: list[str],
    context: str = "",
    comment_count: int = 0,
    available_agents: list[dict] | None = None,
    trigger_comment: str | None = None,
) -> dict:
    """并行运行多个代理

    Args:
        issue_number: Issue 编号
        agents: 代理名称列表
        context: 上下文信息（Issue 标题、内容、评论等）
        comment_count: 评论数量（用于增强上下文）
        available_agents: 系统中可用的智能体列表

    Returns:
        {
            agent_name: {
                "response": str,
                "cost_usd": float,
                "num_turns": int,
                "tool_calls": list[str],
                "session_id": str,
            }
        }
    """
    from issuelab.agents.discovery import discover_agents, load_prompt
    from issuelab.agents.observer import run_observer_for_papers, run_pubmed_observer_for_papers
    from issuelab.agents.paper_extractors import (
        extract_issue_body,
        format_arxiv_reanalysis,
        format_pubmed_reanalysis,
        parse_arxiv_papers_from_issue,
        parse_pubmed_papers_from_issue,
    )
    from issuelab.collaboration import build_collaboration_guidelines

    # 构建任务上下文（Issue 信息）
    task_context = context
    if trigger_comment:
        task_context = (
            "## 最新触发评论（最高优先级）\n"
            f"{trigger_comment}\n\n"
            "---\n\n"
            f"{task_context}"
        )
    if comment_count > 0:
        task_context += f"\n\n**重要提示**: 本 Issue 已有 {comment_count} 条历史评论。请仔细阅读并分析这些评论。"

    # 协作指南：统一在执行器注入，覆盖所有入口（CLI/personal-reply/observer_trigger 等）
    # 为避免重复注入：如果上游 context 已包含协作指南标题，则跳过
    if "## 协作指南" not in task_context:
        agents_dict = discover_agents()
        collaboration_guidelines = build_collaboration_guidelines(agents_dict, available_agents=available_agents)
        if collaboration_guidelines:
            task_context += f"\n\n{collaboration_guidelines}"

    results: dict[str, dict] = {}
    total_cost = 0.0

    async def run_agent_task(agent_name: str, results: dict[str, dict]) -> None:
        """并行任务：运行单个 agent"""
        logger.info(f"[Issue#{issue_number}] [并行] 开始执行 {agent_name}")

        # 特殊：pubmed_observer / arxiv_observer 需要从 Issue 正文解析文献列表
        if agent_name in {"pubmed_observer", "arxiv_observer"}:
            issue_body = extract_issue_body(task_context)
            if agent_name == "pubmed_observer":
                papers, query = parse_pubmed_papers_from_issue(issue_body)
                if not papers:
                    results[agent_name] = {
                        "response": "[Agent: pubmed_observer]\n未在 Issue 正文中识别到 PubMed 文献列表。",
                        "cost_usd": 0.0,
                        "num_turns": 0,
                        "tool_calls": [],
                    }
                    return

                recommended, raw_result = await run_pubmed_observer_for_papers(papers, query, return_result=True)
                response = format_pubmed_reanalysis(recommended, query, total=len(papers))
                raw_result["response"] = response
                results[agent_name] = raw_result
                return

            papers = parse_arxiv_papers_from_issue(issue_body)
            if not papers:
                results[agent_name] = {
                    "response": "[Agent: arxiv_observer]\n未在 Issue 正文中识别到 arXiv 论文信息。",
                    "cost_usd": 0.0,
                    "num_turns": 0,
                    "tool_calls": [],
                }
                return

            recommended, raw_result = await run_observer_for_papers(papers, return_result=True)
            response = format_arxiv_reanalysis(recommended, total=len(papers))
            raw_result["response"] = response
            results[agent_name] = raw_result
            return

        # 1. 加载 agent 的专属 prompt（定义角色和职责）
        agent_prompt = load_prompt(agent_name)
        if not agent_prompt:
            logger.warning(f"[{agent_name}] 未找到 prompt 文件，使用默认配置")
            agent_prompt = f"你是 {agent_name} 代理。"

        if "{mcp_servers}" in agent_prompt:
            mcp_text = format_mcp_servers_for_prompt(agent_name)
            agent_prompt = agent_prompt.replace("{mcp_servers}", mcp_text)

        # 2. 构建最终 prompt：角色定义 + 当前任务
        final_prompt = f"""{agent_prompt}

---

## 当前任务

你需要分析 GitHub Issue #{issue_number}：

{task_context}

---

**输出要求**：
- 请以 [Agent: {agent_name}] 为前缀发布你的回复
- 专注于 Issue 的讨论话题和内容
- 不要去分析项目代码或架构（除非 Issue 明确要求）
"""
        if os.environ.get("PROMPT_LOG") == "1":
            max_len = 2000
            preview = final_prompt[:max_len]
            suffix = "..." if len(final_prompt) > max_len else ""
            logger.debug(f"[{agent_name}] [Prompt] length={len(final_prompt)}\\n{preview}{suffix}")

        result = await run_single_agent(final_prompt, agent_name)
        results[agent_name] = result
        total_cost_local = result.get("cost_usd", 0.0)
        logger.info(
            f"[Issue#{issue_number}] {agent_name} 完成 - "
            f"成本: ${total_cost_local:.4f}, "
            f"轮数: {result.get('num_turns', 0)}, "
            f"工具: {len(result.get('tool_calls', []))}"
        )

    # 使用 anyio.create_task_group 实现真正的并行执行
    async with anyio.create_task_group() as tg:
        for agent in agents:
            tg.start_soon(run_agent_task, agent, results)

    # 汇总总成本
    total_cost = sum(r.get("cost_usd", 0.0) for r in results.values())
    logger.info(f"[Issue#{issue_number}] 所有 Agent 完成 - 总成本: ${total_cost:.4f}")
    return results
