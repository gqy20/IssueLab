"""SDK 执行器：使用 Claude Agent SDK 构建评审代理"""
import anyio
from pathlib import Path
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
)

# 提示词目录
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def load_prompt(agent_name: str) -> str:
    """加载代理提示词"""
    prompts = {
        "moderator": "moderator.md",
        "reviewer_a": "reviewer_a.md",
        "reviewer_b": "reviewer_b.md",
        "summarizer": "summarizer.md",
    }
    if agent_name not in prompts:
        return ""
    prompt_path = PROMPTS_DIR / prompts[agent_name]
    if prompt_path.exists() and prompt_path.is_file():
        return prompt_path.read_text()
    return ""


def create_agent_options() -> ClaudeAgentOptions:
    """创建包含所有评审代理的配置"""
    return ClaudeAgentOptions(
        agents={
            "moderator": AgentDefinition(
                description="分诊与控场代理",
                prompt=load_prompt("moderator"),
                tools=["Read", "Write", "Bash"],
                model="sonnet",
            ),
            "reviewer_a": AgentDefinition(
                description="正方评审代理",
                prompt=load_prompt("reviewer_a"),
                tools=["Read", "Write", "Bash"],
                model="sonnet",
            ),
            "reviewer_b": AgentDefinition(
                description="反方评审代理",
                prompt=load_prompt("reviewer_b"),
                tools=["Read", "Write", "Bash"],
                model="sonnet",
            ),
            "summarizer": AgentDefinition(
                description="共识汇总代理",
                prompt=load_prompt("summarizer"),
                tools=["Read", "Write"],
                model="sonnet",
            ),
        },
        setting_sources=["user", "project"],
    )


async def run_single_agent(prompt: str, agent_name: str) -> str:
    """运行单个代理

    Args:
        prompt: 用户提示词
        agent_name: 代理名称

    Returns:
        代理响应文本
    """
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

    return "\n".join(response_text)


async def run_agents_parallel(issue_number: int, agents: list[str], context: str = "") -> dict:
    """并行运行多个代理

    Args:
        issue_number: Issue 编号
        agents: 代理名称列表
        context: 上下文信息

    Returns:
        {agent_name: response_text}
    """
    base_prompt = f"""请对 GitHub Issue #{issue_number} 执行以下任务：

{context}

请以 [Agent: {{agent_name}}] 为前缀发布你的回复。"""

    async def run_one(agent_name: str) -> tuple[str, str]:
        prompt = base_prompt.format(agent_name=agent_name)
        response = await run_single_agent(prompt, agent_name)
        return agent_name, response

    results = {}
    async with anyio.create_task_group() as tg:
        for agent in agents:
            tg.start_soon(run_one, agent)

    # 收集结果
    # 由于 task_group 不直接返回结果，使用另一种方式
    async with anyio.create_task_group() as tg:
        async def run_and_store(agent_name: str):
            prompt = base_prompt.format(agent_name=agent_name)
            response = await run_single_agent(prompt, agent_name)
            results[agent_name] = response

        for agent in agents:
            tg.start_soon(run_and_store, agent)

    return results
