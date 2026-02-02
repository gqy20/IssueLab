"""SDK 执行器：使用 Claude Agent SDK 构建评审代理"""

import os
import re
from pathlib import Path

import anyio
from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    query,
)

from issuelab.logging_config import get_logger
from issuelab.retry import retry_async

logger = get_logger(__name__)

# 提示词目录
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def parse_agent_metadata(content: str) -> dict | None:
    """从 prompt 文件中解析 YAML 元数据

    格式：
    ---
    agent: moderator
    description: 分诊与控场代理
    trigger_conditions:
      - 新论文 Issue
      - 需要分配评审流程
    ---
    """
    # 匹配 YAML frontmatter
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return None

    yaml_str = match.group(1)
    metadata = {}
    current_list_key = None
    current_list = []

    # 解析 YAML
    for line in yaml_str.split("\n"):
        line = line.rstrip()

        # 检测列表项
        if line.strip().startswith("- "):
            item = line.strip()[2:].strip()
            current_list.append(item)
            # 找到最后一个列表键
            for key in ["trigger_conditions"]:
                if key in metadata:
                    current_list_key = key
            continue

        # 检测普通键值对
        if ":" in line and not line.strip().startswith("-"):
            # 先保存之前的列表
            if current_list and current_list_key:
                metadata[current_list_key] = current_list
                current_list = []
                current_list_key = None

            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            if value:
                metadata[key] = value
            else:
                metadata[key] = None

    # 保存最后的列表
    if current_list and current_list_key:
        metadata[current_list_key] = current_list

    return metadata if metadata else None


def discover_agents() -> dict:
    """动态发现所有可用的 Agent

    通过读取 prompts 文件夹下的 .md 文件，解析 YAML 元数据

    Returns:
        {
            "agent_name": {
                "description": "Agent 描述",
                "prompt": "完整 prompt 内容",
                "trigger_conditions": ["触发条件1", "触发条件2"],
            }
        }
    """
    agents = {}

    if not PROMPTS_DIR.exists():
        return agents

    for prompt_file in PROMPTS_DIR.glob("*.md"):
        content = prompt_file.read_text()
        metadata = parse_agent_metadata(content)

        if metadata and "agent" in metadata:
            agent_name = metadata["agent"]
            # 移除 frontmatter，获取纯 prompt 内容
            clean_content = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()

            agents[agent_name] = {
                "description": metadata.get("description", ""),
                "prompt": clean_content,
                "trigger_conditions": metadata.get("trigger_conditions", []),
            }

    return agents


def get_agent_matrix_markdown() -> str:
    """生成 Agent 矩阵的 Markdown 表格（用于 Observer Prompt）"""
    agents = discover_agents()

    lines = [
        "| Agent | 描述 | 何时触发 |",
        "|-------|------|---------|",
    ]

    for name, config in agents.items():
        if name == "observer":
            continue  # Observer 不需要被自己触发
        trigger_conditions = config.get("trigger_conditions", [])
        trigger = ", ".join(trigger_conditions) if trigger_conditions else "自动判断"
        desc = config.get("description", "")
        lines.append(f"| **{name}** | {desc} | {trigger} |")

    return "\n".join(lines)


def load_prompt(agent_name: str) -> str:
    """加载代理提示词（从动态发现的 agents 中）"""
    agents = discover_agents()
    if agent_name in agents:
        return agents[agent_name]["prompt"]
    return ""


def create_agent_options() -> ClaudeAgentOptions:
    """创建包含所有评审代理的配置（动态发现）"""
    # 从环境变量读取配置
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    model = os.environ.get("ANTHROPIC_MODEL", "sonnet")

    # 构建环境变量字典传给 SDK
    env = {}
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url
    if model:
        env["ANTHROPIC_MODEL"] = model

    # arxiv MCP 存储路径
    arxiv_storage_path = os.environ.get("ARXIV_STORAGE_PATH", str(Path.home() / ".arxiv-mcp-server" / "papers"))

    # MCP 服务器配置
    mcp_servers = []
    if os.environ.get("ENABLE_ARXIV_MCP", "true").lower() == "true":
        mcp_servers.append(
            {
                "name": "arxiv-mcp-server",
                "command": "uv",
                "args": [
                    "--directory",
                    str(Path(__file__).parent.parent.parent),
                    "tool",
                    "run",
                    "arxiv-mcp-server",
                    "--storage-path",
                    arxiv_storage_path,
                ],
                "env": env.copy(),
            }
        )

    # GitHub MCP 服务器配置
    if os.environ.get("ENABLE_GITHUB_MCP", "true").lower() == "true":
        mcp_servers.append(
            {
                "name": "github-mcp-server",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": env.copy(),
            }
        )

    # 动态获取所有 Agent（排除 observer，它不能自己触发自己）
    agents = discover_agents()
    arxiv_tools = ["search_papers", "download_paper", "read_paper", "list_papers"]
    # GitHub 工具 - 用于搜索开源实现、查看代码仓库
    github_tools = [
        "search_repositories",  # 搜索仓库
        "get_file_contents",  # 读取文件
        "list_commits",  # 查看提交历史
        "search_code",  # 搜索代码
        "get_issue",  # 获取 Issue
    ]
    all_tools = ["Read", "Write", "Bash"] + arxiv_tools + github_tools

    agent_definitions = {}
    for name, config in agents.items():
        if name == "observer":
            continue  # Observer 单独处理，不在此处注册
        agent_definitions[name] = AgentDefinition(
            description=config["description"],
            prompt=config["prompt"],
            tools=all_tools,
            model=model,
        )

    return ClaudeAgentOptions(
        agents=agent_definitions,
        setting_sources=["user", "project"],
        env=env,
        mcp_servers=mcp_servers,
    )


async def run_single_agent(prompt: str, agent_name: str) -> str:
    """运行单个代理（带重试机制）

    Args:
        prompt: 用户提示词
        agent_name: 代理名称

    Returns:
        代理响应文本
    """
    logger.info(f"开始运行 agent: {agent_name}")

    async def _query_agent():
        options = create_agent_options()
        response_text = []

        async for message in query(
            prompt=prompt,
            options=options,
        ):
            from claude_agent_sdk import AssistantMessage, TextBlock

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text.append(block.text)

        result = "\n".join(response_text)
        logger.info(f"Agent {agent_name} 响应完成，长度: {len(result)} 字符")
        return result

    try:
        return await retry_async(_query_agent, max_retries=3, initial_delay=2.0, backoff_factor=2.0)
    except Exception as e:
        logger.error(f"Agent {agent_name} 运行失败: {e}", exc_info=True)
        return f"[错误] Agent {agent_name} 执行失败: {e}"


async def run_agents_parallel(issue_number: int, agents: list[str], context: str = "", comment_count: int = 0) -> dict:
    """并行运行多个代理

    Args:
        issue_number: Issue 编号
        agents: 代理名称列表
        context: 上下文信息
        comment_count: 评论数量（用于增强上下文）

    Returns:
        {agent_name: response_text}
    """
    # 构建增强的上下文
    full_context = context
    if comment_count > 0:
        full_context += f"\n\n**重要提示**: 本 Issue 已有 {comment_count} 条历史评论。Summarizer 代理应读取并分析这些评论，提取共识、分歧和行动项。"

    base_prompt = f"""请对 GitHub Issue #{issue_number} 执行以下任务：

{full_context}

请以 [Agent: {{agent_name}}] 为前缀发布你的回复。"""

    results = {}
    async with anyio.create_task_group() as tg:

        async def run_and_store(agent_name: str):
            prompt = base_prompt.format(agent_name=agent_name)
            response = await run_single_agent(prompt, agent_name)
            results[agent_name] = response

        for agent in agents:
            tg.start_soon(run_and_store, agent)

    return results


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

    # 动态生成 Agent 矩阵
    agent_matrix = get_agent_matrix_markdown()

    prompt = observer_config["prompt"].format(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body or "无内容",
        comments=comments or "无评论",
        agent_matrix=agent_matrix,
    )

    response = await run_single_agent(prompt, "observer")

    # 解析响应
    return parse_observer_response(response, issue_number)


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


def parse_observer_response(response: str, issue_number: int) -> dict:
    """解析 Observer Agent 的响应

    Args:
        response: Agent 响应文本
        issue_number: Issue 编号

    Returns:
        解析后的决策结果
    """
    result = {
        "should_trigger": False,
        "agent": "",
        "comment": "",
        "reason": "",
        "analysis": "",
    }

    # 简单的解析逻辑
    lines = response.split("\n")

    # 查找 action/should_trigger
    for line in lines:
        line_lower = line.lower().strip()
        if "action: trigger" in line_lower or "should_trigger: true" in line_lower:
            result["should_trigger"] = True
        elif "action: skip" in line_lower or "should_trigger: false" in line_lower:
            result["should_trigger"] = False
            return result

    # 查找 agent
    for line in lines:
        if line.startswith("agent:") or line.startswith("trigger_agent:"):
            result["agent"] = line.split(":", 1)[1].strip().lower()
            break

    # 查找 comment
    in_comment = False
    comment_lines = []
    for line in lines:
        if "comment:" in line.lower() or "trigger_comment:" in line.lower():
            in_comment = True
            continue
        if in_comment and line.startswith("---"):
            break
        if in_comment:
            comment_lines.append(line)
    result["comment"] = "\n".join(comment_lines).strip()

    # 查找 reason
    for line in lines:
        if "reason:" in line.lower():
            result["reason"] = line.split(":", 1)[1].strip()
            break

    # 查找 analysis
    for line in lines:
        if "analysis:" in line.lower():
            result["analysis"] = line.split(":", 1)[1].strip()
            break

    # 如果没有解析到触发评论，使用默认格式
    if result["should_trigger"] and result["agent"] and not result["comment"]:
        agent_map = {
            "moderator": "@Moderator 请分诊",
            "reviewer_a": "@ReviewerA 评审",
            "reviewer_b": "@ReviewerB 找问题",
            "summarizer": "@Summarizer 汇总",
        }
        result["comment"] = agent_map.get(result["agent"], f"@{result['agent']}")

    return result
