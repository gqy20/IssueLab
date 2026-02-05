"""GitHub 操作工具 - 统一的 GitHub API 接口"""

import json
import os
import subprocess
import tempfile
from typing import Literal

from issuelab.config import Config
from issuelab.logging_config import get_logger
from issuelab.retry import retry_sync

logger = get_logger(__name__)

# GitHub 评论最大长度
MAX_COMMENT_LENGTH = 10000


@retry_sync(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
def get_issue_info(issue_number: int, format_comments: bool = False, repo: str | None = None) -> dict:
    """获取 Issue 信息（带重试机制）

    Args:
        issue_number: Issue 编号
        format_comments: 是否格式化评论为字符串（用于 LLM 输入）

    Returns:
        包含 title, body, comments, comment_count 等字段的字典
        如果 format_comments=True，comments 为格式化字符串，否则为原始列表
    """
    logger.debug(f"获取 Issue #{issue_number} 信息")
    env = Config.prepare_github_env()

    cmd = ["gh", "issue", "view", str(issue_number), "--json", "number,title,body,labels,comments"]
    if repo:
        cmd.extend(["--repo", repo])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        logger.error(f"获取 Issue #{issue_number} 失败: {result.stderr}")
        raise RuntimeError(f"Failed to get issue info: {result.stderr}")

    data = json.loads(result.stdout)

    # 先计算评论数（使用原始列表）
    comment_count = len(data.get("comments", []))
    data["comment_count"] = comment_count

    # 格式化评论（如果需要）
    if format_comments:
        comments_list = []
        for comment in data.get("comments", []):
            author = comment.get("author", {}).get("login", "unknown")
            created_at = comment.get("createdAt", "")[:10]  # 只取日期部分
            body = comment.get("body", "")
            comments_list.append(f"- **[{author}]** ({created_at}):\n{body}")

        data["comments"] = "\n\n".join(comments_list)

    return data


def write_issue_context_file(
    issue_number: int,
    title: str,
    body: str,
    comments: str,
    comment_count: int | None = None,
) -> str:
    """写入 Issue 上下文到临时文件，返回文件路径。"""
    base_dir = os.path.join(os.getcwd(), ".issuelab")
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"issue_{issue_number}.md")

    lines = [f"# Issue {issue_number}", ""]
    if title:
        lines.extend(["## 标题", title, ""])

    lines.extend(["## 正文", body or "无内容", ""])

    if comment_count is None:
        comment_count = 0 if not comments else len([c for c in comments.splitlines() if c.strip()])

    lines.append(f"## 评论（{comment_count}）")
    if comments:
        lines.append(comments)
    else:
        lines.append("无评论")

    content = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path


def truncate_text(text: str, max_length: int = MAX_COMMENT_LENGTH) -> str:
    """截断文本到指定长度，保留完整段落

    Args:
        text: 要截断的文本
        max_length: 最大长度（默认 10000）

    Returns:
        截断后的文本，如果需要会添加截断提示
    """
    suffix = "\n\n_(内容已截断)_"
    suffix_len = len(suffix)

    if len(text) <= max_length:
        return text

    # 预留后缀空间，截断内容部分
    available = max_length - suffix_len
    truncated = text[:available]

    # 尝试在最后一个完整段落后截断
    last_newline = truncated.rfind("\n\n")

    if last_newline > available * 0.5:  # 保留至少 50% 的内容
        return truncated[:last_newline].strip() + suffix

    # 否则直接在字符边界截断
    return truncated.strip() + suffix


def post_comment(
    issue_number: int,
    body: str,
    agent_name: str | None = None,
    mentions: list[str] | None = None,
    auto_truncate: bool = True,
    auto_clean: bool = True,
    repo: str | None = None,
) -> bool:
    """在 Issue 下发布评论（集中式 @ 管理）

    新增功能：
    1. 支持拼接 @ 区域
    2. 支持自动清理和过滤 @mentions（默认开启）
    3. 支持跨仓库评论

    Args:
        issue_number: Issue 编号
        body: 评论内容
        mentions: 需要 @ 的用户列表（会拼接到评论末尾）
                 如果为 None 且 auto_clean=True，会自动提取并过滤
        auto_truncate: 是否自动截断过长内容（默认 True）
        auto_clean: 是否自动清理和过滤 @mentions（默认 True）
                   设为 False 可完全禁用 @ 管理（绕过策略）
        repo: 仓库名称（格式：owner/repo），None 表示当前仓库

    Returns:
        是否成功发布
    """
    env = Config.prepare_github_env()
    from issuelab.response_processor import normalize_comment_body

    raw_body = body
    body = normalize_comment_body(body, agent_name=agent_name)

    # 自动清理和过滤 @mentions（集中式管理的核心）
    if mentions is None and auto_clean:
        from issuelab.mention_policy import clean_mentions_in_text, filter_mentions, rank_mentions_by_frequency

        # 1. 提取所有 @mentions（基于原始文本，避免规范化后丢失）
        all_mentions = rank_mentions_by_frequency(raw_body)

        # 2. 应用策略过滤
        if all_mentions:
            allowed_mentions, filtered_mentions = filter_mentions(all_mentions)

            if filtered_mentions:
                logger.info(f"[FILTER] 过滤了 {len(filtered_mentions)} 个 @mentions: {filtered_mentions}")

            # 3. 清理主体内容（@ → "用户 xxx"）
            body = clean_mentions_in_text(body)

            # 4. 使用过滤后的 mentions（最多 2 个，按出现次数排序）
            if len(allowed_mentions) > 2:
                logger.info(f"[FILTER] 仅保留出现次数最多的 2 个 @mentions: {allowed_mentions[:2]}")
            mentions = allowed_mentions[:2]
        else:
            mentions = []

    # 拼接 @ 区域
    if mentions:
        from issuelab.mention_policy import build_mention_section

        mention_section = build_mention_section(mentions, format_type="labeled")
        final_body = f"{body}\n\n{mention_section}"
    else:
        final_body = body

    # 自动截断
    if auto_truncate:
        final_body = truncate_text(final_body, MAX_COMMENT_LENGTH)

    # 使用临时文件避免命令行长度限制
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(final_body)
        f.flush()

        # 构建命令
        cmd = ["gh", "issue", "comment", str(issue_number), "--body-file", f.name]
        if repo:
            cmd.extend(["--repo", repo])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )
        os.unlink(f.name)

    if result.returncode != 0:
        logger.error(f"发布评论到 Issue #{issue_number} 失败: {result.stderr}")
        return False

    logger.info(f"评论已发布到 Issue #{issue_number}")
    return True


def update_label(issue_number: int, label: str, action: Literal["add", "remove"] = "add") -> bool:
    """更新 Issue 标签

    Args:
        issue_number: Issue 编号
        label: 标签名称
        action: 操作类型（"add" 或 "remove"）

    Returns:
        是否成功更新
    """
    action_flag = "--add-label" if action == "add" else "--remove-label"
    env = Config.prepare_github_env()

    result = subprocess.run(
        ["gh", "issue", "edit", str(issue_number), action_flag, label],
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        logger.error(f"更新标签 '{label}' 失败: {result.stderr}")
        return False

    logger.info(f"标签 '{label}' 已{action}到 Issue #{issue_number}")
    return True
