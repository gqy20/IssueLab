"""Claude Agent SDK 选项构建

处理 SDK 选项的创建和缓存管理。
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import suppress
from pathlib import Path
from typing import Any

import yaml
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

from issuelab.agents.config import AgentConfig
from issuelab.agents.discovery import AGENTS_DIR, discover_agents
from issuelab.agents.registry import get_agent_config
from issuelab.config import Config
from issuelab.logging_config import get_logger

logger = get_logger(__name__)

# 全局缓存：存储 Agent 选项
_cached_agent_options: dict[tuple, ClaudeAgentOptions] = {}


def clear_agent_options_cache() -> None:
    """清除 Agent 选项缓存

    在测试或配置更改后调用此函数以确保使用最新的配置。
    """
    global _cached_agent_options
    _cached_agent_options = {}
    logger.info("Agent 选项缓存已清除")


def _get_agent_run_overrides(agent_name: str | None) -> dict[str, float | int]:
    """读取 agent.yml 中的运行覆盖参数"""
    if not agent_name:
        return {}

    config = get_agent_config(agent_name, agents_dir=AGENTS_DIR, include_disabled=False)
    if not config:
        return {}

    overrides: dict[str, float | int] = {}
    if "max_turns" in config:
        with suppress(TypeError, ValueError):
            overrides["max_turns"] = int(config["max_turns"])
    if "max_budget_usd" in config:
        with suppress(TypeError, ValueError):
            overrides["max_budget_usd"] = float(config["max_budget_usd"])
    if "timeout_seconds" in config:
        with suppress(TypeError, ValueError):
            overrides["timeout_seconds"] = int(config["timeout_seconds"])
    return overrides


def _get_agent_feature_flags(agent_name: str | None) -> dict[str, bool]:
    """读取 agent.yml 中的功能开关（默认启用）"""
    flags = {
        "enable_skills": True,
        "enable_subagents": True,
        "enable_mcp": True,
    }
    if not agent_name:
        return flags

    config = get_agent_config(agent_name, agents_dir=AGENTS_DIR, include_disabled=False)
    if not config:
        return flags

    for key in ("enable_skills", "enable_subagents", "enable_mcp"):
        if key in config:
            flags[key] = bool(config.get(key))

    return flags


def _read_mcp_servers_from_file(path: Path) -> dict[str, Any]:
    """读取 .mcp.json 并返回 mcpServers 字典

    支持两种格式：
    1) {"mcpServers": { ... }}
    2) { ... }  # 直接就是 servers 映射
    """
    if not path.exists():
        return {}

    try:
        raw_text = _read_text_with_timeout(path)
        raw = json.loads(raw_text)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取 MCP 配置失败: %s (%s)", path, exc)
        return {}
    except TimeoutError as exc:
        logger.warning("读取 MCP 配置超时，已跳过: %s (%s)", path, exc)
        return {}

    if not isinstance(raw, dict):
        logger.warning("MCP 配置格式错误（非 dict）: %s", path)
        return {}

    servers = raw.get("mcpServers", raw)
    if not isinstance(servers, dict):
        logger.warning("MCP 配置格式错误（mcpServers 非 dict）: %s", path)
        return {}

    return servers


def _read_text_with_timeout(path: Path) -> str:
    """读取文件内容（带超时）"""
    timeout_ms = int(os.environ.get("MCP_CONFIG_LOAD_TIMEOUT_MS", "3000"))
    timeout_sec = max(timeout_ms, 0) / 1000.0

    def _read() -> str:
        return path.read_text(encoding="utf-8")

    if timeout_sec <= 0:
        return _read()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_read)
        try:
            return future.result(timeout=timeout_sec)
        except FutureTimeoutError as exc:
            raise TimeoutError(f"read timeout after {timeout_ms}ms") from exc


def load_mcp_servers_for_agent(agent_name: str | None, root_dir: Path | None = None) -> dict[str, Any]:
    """加载 MCP 服务器配置（全局 + per-agent 覆盖）"""
    root = root_dir or AGENTS_DIR.parent
    servers: dict[str, Any] = {}

    # 全局配置：项目根目录 .mcp.json
    servers.update(_read_mcp_servers_from_file(root / ".mcp.json"))

    # Agent 级别配置：agents/<name>/.mcp.json
    if agent_name:
        servers.update(_read_mcp_servers_from_file(root / "agents" / agent_name / ".mcp.json"))

    return servers


def format_mcp_servers_for_prompt(agent_name: str | None, root_dir: Path | None = None) -> str:
    """为 prompt 格式化 MCP 服务器列表"""
    servers = load_mcp_servers_for_agent(agent_name, root_dir=root_dir)
    if not servers:
        return "（未配置 MCP 工具）"
    lines = []
    for name, cfg in servers.items():
        cfg_type = ""
        if isinstance(cfg, dict):
            cfg_type = cfg.get("type", "")
        type_text = f" [{cfg_type}]" if cfg_type else ""
        lines.append(f"- {name}{type_text}")
    return "\n".join(lines)


def _get_agent_cwd(agent_name: str | None, root_dir: Path | None = None) -> Path:
    """根据 agent 选择 cwd（用于加载 per-agent skills）"""
    root = root_dir or AGENTS_DIR.parent
    if not agent_name:
        return root

    agent_root = root / "agents" / agent_name
    agent_skills = agent_root / ".claude" / "skills"
    agent_subagents = agent_root / ".claude" / "agents"
    if agent_skills.exists() or agent_subagents.exists():
        return agent_root

    return root


def _discover_skills_in_path(base: Path) -> list[str]:
    """列出指定路径下的 skills 名称"""
    skills_dir = base / ".claude" / "skills"
    if not skills_dir.exists():
        return []

    names = []
    for child in skills_dir.iterdir():
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if skill_file.exists():
            names.append(child.name)
    return sorted(names)


def _skills_signature(cwd: Path) -> str:
    """生成技能列表签名（用于缓存键）"""
    project_skills = _discover_skills_in_path(cwd)
    user_skills = _discover_skills_in_path(Path(os.path.expanduser("~")))
    return json.dumps({"project": project_skills, "user": user_skills}, ensure_ascii=True)


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """解析 markdown frontmatter"""
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return {}, content

    meta_str = match.group(1)
    try:
        metadata = yaml.safe_load(meta_str) or {}
    except Exception:
        metadata = {}

    body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()
    return metadata, body


def _load_subagents_from_dir(path: Path, default_tools: list[str]) -> dict[str, AgentDefinition]:
    """从 .claude/agents 加载 subagents"""
    agents_dir = path / ".claude" / "agents"
    if not agents_dir.exists():
        return {}

    subagents: dict[str, AgentDefinition] = {}
    for md in agents_dir.glob("*.md"):
        try:
            content = md.read_text(encoding="utf-8")
        except OSError:
            continue

        meta, body = _parse_frontmatter(content)
        name = (meta.get("agent") or meta.get("name") or md.stem).strip()
        if not name:
            continue

        description = (meta.get("description") or "").strip()
        tools = meta.get("tools") or default_tools
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",") if t.strip()]
        if not isinstance(tools, list):
            tools = default_tools

        # Subagents must not call subagents
        tools = [t for t in tools if t != "Task"]

        subagents[name] = AgentDefinition(
            description=description,
            prompt=body if body else f"You are {name}.",
            tools=tools,
            model="inherit",
        )

    return subagents


def _subagents_signature(subagents: dict[str, AgentDefinition]) -> str:
    """生成 subagents 签名（用于缓存键）"""
    if not subagents:
        return ""
    return json.dumps(sorted(subagents.keys()), ensure_ascii=True)


def _subagents_signature_from_dir(path: Path) -> list[tuple[str, float]]:
    """获取 subagents 目录签名（基于文件名与 mtime）"""
    agents_dir = path / ".claude" / "agents"
    if not agents_dir.exists():
        return []

    entries = []
    for md in agents_dir.glob("*.md"):
        try:
            entries.append((md.name, md.stat().st_mtime))
        except OSError:
            continue
    return sorted(entries)


def _subagents_signature_for_cache(
    project_entries: list[tuple[str, float]], user_entries: list[tuple[str, float]]
) -> str:
    """生成 subagents 缓存签名（包含 mtime）"""
    return json.dumps({"project": project_entries, "user": user_entries}, ensure_ascii=True)


def _run_async_in_thread(coro, timeout_ms: int) -> Any:
    """在独立线程中运行 async 任务，避免与当前事件循环冲突"""
    timeout_sec = max(timeout_ms, 0) / 1000.0

    def _runner():
        import anyio

        async def _async_runner():
            return await coro

        return anyio.run(_async_runner)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_runner)
        try:
            return future.result(timeout=timeout_sec if timeout_sec > 0 else None)
        except FutureTimeoutError as exc:
            raise TimeoutError(f"async task timeout after {timeout_ms}ms") from exc


async def _list_tools_stdio(server_name: str, cfg: dict[str, Any]) -> list[str]:
    """通过 MCP stdio 连接列出工具"""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=cfg.get("command", ""),
        args=cfg.get("args", []) or [],
        env=cfg.get("env"),
        cwd=cfg.get("cwd"),
    )

    async with stdio_client(params) as (read_stream, write_stream):
        session = ClientSession(read_stream, write_stream)
        await session.initialize()
        result = await session.list_tools()
        tools = result.tools or []
        return [t.name for t in tools if getattr(t, "name", None)]


def _list_tools_for_mcp_server(server_name: str, cfg: dict[str, Any], timeout_ms: int) -> list[str]:
    """列出单个 MCP server 的工具（目前仅支持 stdio）"""
    if not isinstance(cfg, dict):
        return []

    if "command" not in cfg:
        logger.debug("Skip MCP tool listing for '%s': non-stdio server", server_name)
        return []

    try:
        return _run_async_in_thread(_list_tools_stdio(server_name, cfg), timeout_ms=timeout_ms)
    except TimeoutError as exc:
        logger.warning("List tools timeout for MCP server '%s': %s", server_name, exc)
        return []
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("List tools failed for MCP server '%s': %s", server_name, exc)
        return []


def _mcp_cache_key(servers: dict[str, Any]) -> str:
    """生成 MCP 配置的稳定缓存键"""
    if not servers:
        return ""
    try:
        return json.dumps(servers, sort_keys=True, ensure_ascii=True)
    except TypeError:
        return str(servers)


def _create_agent_options_impl(
    max_turns: int | None,
    max_budget_usd: float | None,
    *,
    agent_name: str | None,
    mcp_servers: dict[str, Any],
    cwd: Path,
    subagents_sig: str,
    enable_subagents: bool,
) -> ClaudeAgentOptions:
    """创建 Agent 选项的实际实现（无缓存）"""
    env = Config.get_anthropic_env()
    env["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "true"

    # 收集 SDK 内部日志的回调
    sdk_logs: list[str] = []

    def sdk_stderr_handler(message: str) -> None:
        """捕获 SDK 内部日志（包含详细的模型交互信息）"""
        log_entry = f"[SDK] {message}"
        sdk_logs.append(log_entry)
        # 输出到终端
        print(message, end="", flush=True)
        # 记录到日志
        logger.debug(f"[SDK] {message}")

    agents = discover_agents()

    base_tools = ["Read", "Write", "Bash", "Skill"]
    main_tools = base_tools + ["Task"]
    agent_definitions = {}
    for name, config in agents.items():
        if name == "observer":
            continue
        agent_definitions[name] = AgentDefinition(
            description=config["description"],
            prompt=config["prompt"],
            tools=base_tools,
            model="inherit",
        )

    if enable_subagents:
        # per-agent subagents from .claude/agents
        subagent_tools = base_tools
        project_subagents = _load_subagents_from_dir(cwd, subagent_tools)
        user_subagents = _load_subagents_from_dir(Path(os.path.expanduser("~")), subagent_tools)

        # programmatic subagents override file-based on name collision
        for name, definition in {**user_subagents, **project_subagents}.items():
            agent_definitions[name] = definition

        if project_subagents or user_subagents:
            logger.info(
                "Subagents loaded for agent '%s': project=%s user=%s",
                agent_name or "default",
                ", ".join(sorted(project_subagents.keys())) if project_subagents else "(none)",
                ", ".join(sorted(user_subagents.keys())) if user_subagents else "(none)",
            )
        else:
            logger.info("No subagents configured for agent '%s'", agent_name or "default")
    else:
        logger.info("Subagents disabled for agent '%s'", agent_name or "default")

    allowed_tools = main_tools[:]
    if mcp_servers:
        allowed_tools.extend([f"mcp__{name}__*" for name in mcp_servers])
    if os.environ.get("MCP_LOG_DETAIL") == "1":
        logger.debug("Allowed tools for agent '%s': %s", agent_name or "default", allowed_tools)

    if agent_name in {"arxiv_observer", "pubmed_observer"}:
        output_format_rules = "Follow response format rules in config/papers_recommendation_format.yml."
    else:
        output_format_rules = "Follow response format rules in config/response_format.yml."

    return ClaudeAgentOptions(
        agents=agent_definitions,
        max_turns=max_turns if max_turns is not None else AgentConfig().max_turns,
        max_budget_usd=max_budget_usd if max_budget_usd is not None else AgentConfig().max_budget_usd,
        system_prompt={"type": "preset", "preset": "claude_code", "append": output_format_rules},
        setting_sources=["user", "project"],
        env=env,
        permission_mode="bypassPermissions",
        allowed_tools=allowed_tools,
        mcp_servers=mcp_servers,
        cwd=str(cwd),
        stderr=sdk_stderr_handler,  # 捕获 SDK 内部详细日志
    )


def create_agent_options(
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    *,
    agent_name: str | None = None,
) -> ClaudeAgentOptions:
    """创建包含所有评审代理的配置（动态发现）

    官方推荐的超时控制参数：
    - max_turns: 限制对话轮数，防止无限循环
    - max_budget_usd: 限制花费，防止意外支出

    Args:
        max_turns: 最大对话轮数（默认使用 AgentConfig 默认值）
        max_budget_usd: 最大花费限制（默认使用 AgentConfig 默认值）

    Returns:
        ClaudeAgentOptions: 配置好的 SDK 选项

    Note:
        此函数使用缓存来避免重复创建相同的配置。
        如果需要强制刷新配置，请先调用 clear_agent_options_cache()。
    """
    overrides = _get_agent_run_overrides(agent_name)
    feature_flags = _get_agent_feature_flags(agent_name)
    # 使用默认值 + per-agent 覆盖
    effective_max_turns = (
        max_turns if max_turns is not None else int(overrides.get("max_turns", AgentConfig().max_turns))
    )
    effective_max_budget = (
        max_budget_usd
        if max_budget_usd is not None
        else float(overrides.get("max_budget_usd", AgentConfig().max_budget_usd))
    )

    # 缓存键：使用参数元组
    mcp_servers = load_mcp_servers_for_agent(agent_name) if feature_flags["enable_mcp"] else {}
    if mcp_servers:
        server_names = ", ".join(sorted(mcp_servers.keys()))
        logger.info("MCP servers loaded for agent '%s': %s", agent_name or "default", server_names)
    else:
        logger.info("No MCP servers configured for agent '%s'", agent_name or "default")

    if os.environ.get("MCP_LOG_DETAIL") == "1":
        logger.debug("MCP servers detail for agent '%s': %s", agent_name or "default", mcp_servers)

    cwd = _get_agent_cwd(agent_name)
    if feature_flags["enable_skills"]:
        project_skills = _discover_skills_in_path(cwd)
        user_skills = _discover_skills_in_path(Path(os.path.expanduser("~")))
        if project_skills or user_skills:
            logger.info(
                "Skills loaded for agent '%s': project=%s user=%s",
                agent_name or "default",
                ", ".join(project_skills) if project_skills else "(none)",
                ", ".join(user_skills) if user_skills else "(none)",
            )
        else:
            logger.info("No skills configured for agent '%s'", agent_name or "default")
    else:
        project_skills = []
        user_skills = []
        logger.info("Skills disabled for agent '%s'", agent_name or "default")

    # per-agent subagents signature for cache (avoid loading full files on cache hit)
    if feature_flags["enable_subagents"]:
        project_subagents_sig = _subagents_signature_from_dir(cwd)
        user_subagents_sig = _subagents_signature_from_dir(Path(os.path.expanduser("~")))
        subagents_sig = _subagents_signature_for_cache(project_subagents_sig, user_subagents_sig)
    else:
        subagents_sig = "disabled"

    cache_key = (
        effective_max_turns,
        effective_max_budget,
        agent_name or "",
        _mcp_cache_key(mcp_servers),
        _skills_signature(cwd),
        subagents_sig,
    )

    # 检查缓存
    if cache_key in _cached_agent_options:
        logger.debug(f"使用缓存的 Agent 选项 (key={cache_key})")
        return _cached_agent_options[cache_key]

    if os.environ.get("MCP_LOG_TOOLS") == "1" and mcp_servers:
        timeout_ms = int(os.environ.get("MCP_LIST_TOOLS_TIMEOUT_MS", "3000"))
        for name, cfg in mcp_servers.items():
            tools = _list_tools_for_mcp_server(name, cfg, timeout_ms=timeout_ms)
            if tools:
                logger.info("MCP tools for '%s': %s", name, ", ".join(sorted(tools)))
            else:
                logger.info("MCP tools for '%s': (none or unavailable)", name)
    # 创建新配置
    options = _create_agent_options_impl(
        effective_max_turns,
        effective_max_budget,
        agent_name=agent_name,
        mcp_servers=mcp_servers,
        cwd=cwd,
        subagents_sig=subagents_sig,
        enable_subagents=feature_flags["enable_subagents"],
    )

    # 存入缓存
    _cached_agent_options[cache_key] = options
    logger.debug(f"创建新的 Agent 选项并缓存 (key={cache_key})")

    return options
