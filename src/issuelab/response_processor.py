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
from pathlib import Path
from typing import Any

import yaml

from issuelab.mention_policy import (
    build_mention_section,
    clean_mentions_in_text,
    filter_mentions,
)

logger = logging.getLogger(__name__)

__all__ = [
    "build_mention_section",
    "clean_mentions_in_text",
    "filter_mentions",
    "trigger_mentioned_agents",
    "process_agent_response",
    "normalize_comment_body",
    "extract_mentions_from_yaml",
    "should_auto_close",
    "close_issue",
]


_DEFAULT_FORMAT_RULES = {
    "force_normalize": False,
    "sections": {
        "summary": "## Summary",
        "findings": "## Key Findings",
        "actions": "## Recommended Actions",
        "structured": "## Structured (YAML)",
    },
    "limits": {
        "summary_max_chars": 20,
        "findings_count": 3,
        "findings_max_chars": 25,
        "actions_max_count": 2,
        "actions_max_chars": 30,
        "mentions_max_count": 5,
    },
    "rules": {
        "mentions_only_in_actions": True,
        "yaml_required": True,
    },
}

_FORMAT_RULES_CACHE: dict[str, Any] | None = None


def _load_format_rules() -> dict[str, Any]:
    global _FORMAT_RULES_CACHE
    if _FORMAT_RULES_CACHE is not None:
        return _FORMAT_RULES_CACHE

    rules = {**_DEFAULT_FORMAT_RULES}
    config_path = Path(__file__).resolve().parents[2] / "config" / "response_format.yml"
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            rules.update({k: v for k, v in data.items() if k in rules})
            if "sections" in data:
                rules["sections"].update(data.get("sections", {}))
            if "limits" in data:
                rules["limits"].update(data.get("limits", {}))
            if "rules" in data:
                rules["rules"].update(data.get("rules", {}))
        except Exception as exc:
            logger.warning("Failed to load response format rules: %s", exc)

    _FORMAT_RULES_CACHE = rules
    return rules


def _truncate_text(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit]


def _extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_mentions_from_yaml(response_text: str) -> list[str]:
    yaml_text = _extract_yaml_block(response_text)
    if not yaml_text:
        return []
    try:
        parsed = yaml.safe_load(yaml_text) or {}
    except Exception:
        return []
    mentions_value = parsed.get("mentions")
    if not mentions_value:
        return []

    if isinstance(mentions_value, str):
        candidates = [mentions_value]
    elif isinstance(mentions_value, list):
        candidates = [str(item) for item in mentions_value]
    else:
        return []

    normalized: list[str] = []
    for item in candidates:
        cleaned = item.strip()
        if cleaned.startswith("@"):
            cleaned = cleaned[1:]
        if not cleaned:
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", cleaned):
            continue
        if cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _normalize_agent_output(response_text: str, agent_name: str | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    rules = _load_format_rules()
    sections = rules["sections"]
    limits = rules["limits"]
    force_normalize = bool(rules.get("force_normalize", False))

    summary_marker = sections["summary"]
    findings_marker = sections["findings"]
    actions_marker = sections["actions"]
    yaml_marker = sections["structured"]

    # Render YAML-only responses into markdown for user-facing agents.
    if summary_marker not in response_text:
        yaml_text = _extract_yaml_block(response_text)
        if yaml_text and agent_name not in {"arxiv_observer", "pubmed_observer"}:
            try:
                parsed = yaml.safe_load(yaml_text) or {}
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                summary_line = str(parsed.get("summary", "")).strip()
                findings_list = parsed.get("findings", []) if isinstance(parsed.get("findings"), list) else []
                recs_list = parsed.get("recommendations", []) if isinstance(parsed.get("recommendations"), list) else []

                findings_count = int(limits.get("findings_count", 3))
                actions_max = int(limits.get("actions_max_count", 2))
                summary_line = _truncate_text(
                    clean_mentions_in_text(summary_line), int(limits.get("summary_max_chars", 20))
                )
                findings = [
                    _truncate_text(clean_mentions_in_text(str(item)), int(limits.get("findings_max_chars", 25)))
                    for item in findings_list[:findings_count]
                ]
                actions = [
                    _truncate_text(str(item), int(limits.get("actions_max_chars", 30)))
                    for item in recs_list[:actions_max]
                ]

                normalized = [
                    f"[Agent: {agent_name}]",
                    "",
                    summary_marker,
                    summary_line or "(missing)",
                    "",
                    findings_marker,
                    *(f"- {item}" for item in findings),
                    "",
                    actions_marker,
                    *(f"- [ ] {item}" for item in actions),
                    "",
                    yaml_marker,
                    "```yaml",
                    yaml_text.strip(),
                    "```",
                ]

                return "\n".join(normalized).rstrip() + "\n", warnings

    if not force_normalize and summary_marker not in response_text:
        return response_text, warnings

    markers = [summary_marker, findings_marker, actions_marker, yaml_marker]
    positions = {marker: response_text.find(marker) for marker in markers}
    missing = [marker for marker, pos in positions.items() if pos == -1]
    if missing:
        warnings.append(f"Missing sections: {', '.join(missing)}")
        if not force_normalize:
            return response_text, warnings

    summary_block = response_text[
        positions.get(summary_marker, 0) + len(summary_marker) : positions.get(findings_marker, len(response_text))
    ].strip()
    findings_block = response_text[
        positions.get(findings_marker, len(response_text)) + len(findings_marker) : positions.get(
            actions_marker, len(response_text)
        )
    ].strip()
    actions_block = response_text[
        positions.get(actions_marker, len(response_text)) + len(actions_marker) : positions.get(
            yaml_marker, len(response_text)
        )
    ].strip()
    yaml_block = response_text[positions.get(yaml_marker, len(response_text)) + len(yaml_marker) :].strip()

    summary_line = ""
    for line in summary_block.splitlines():
        if line.strip():
            summary_line = line.strip()
            break
    if not summary_line:
        warnings.append("Summary is empty")
    summary_line = clean_mentions_in_text(summary_line)
    summary_line = _truncate_text(summary_line, int(limits.get("summary_max_chars", 20)))

    findings: list[str] = []
    for line in findings_block.splitlines():
        match = re.match(r"^\s*[-*]\s+(.*)", line)
        if match:
            findings.append(match.group(1).strip())
    if not findings:
        warnings.append("Key Findings missing bullets")
    findings_count = int(limits.get("findings_count", 3))
    findings = [
        _truncate_text(clean_mentions_in_text(item), int(limits.get("findings_max_chars", 25)))
        for item in findings[:findings_count]
    ]
    if len(findings) < findings_count:
        warnings.append(f"Key Findings fewer than {findings_count} bullets")

    actions: list[str] = []
    for line in actions_block.splitlines():
        match = re.match(r"^\s*[-*]\s+(.*)", line)
        if match:
            actions.append(match.group(1).strip())
    if not actions:
        warnings.append("Recommended Actions missing bullets")
    actions_max = int(limits.get("actions_max_count", 2))
    actions = [_truncate_text(item, int(limits.get("actions_max_chars", 30))) for item in actions[:actions_max]]
    if len(actions) > actions_max:
        warnings.append(f"Recommended Actions truncated to {actions_max} bullets")

    confidence = "medium"
    parsed_mentions: list[str] = []
    yaml_text = _extract_yaml_block(yaml_block)
    parsed = None
    if yaml_text:
        try:
            parsed = yaml.safe_load(yaml_text)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            parsed_confidence = str(parsed.get("confidence", "")).lower()
            if parsed_confidence in {"high", "medium", "low"}:
                confidence = parsed_confidence
            parsed_mentions = extract_mentions_from_yaml(response_text)

    def _yaml_escape(value: str) -> str:
        return value.replace('"', '\\"')

    yaml_lines = [
        "```yaml",
        f'summary: "{_yaml_escape(summary_line)}"',
        "findings:",
    ]
    for item in findings:
        yaml_lines.append(f'  - "{_yaml_escape(item)}"')
    yaml_lines.append("recommendations:")
    for item in actions:
        yaml_lines.append(f'  - "{_yaml_escape(item)}"')
    if parsed_mentions:
        mentions_max = int(limits.get("mentions_max_count", 5))
        yaml_lines.append("mentions:")
        for item in parsed_mentions[:mentions_max]:
            yaml_lines.append(f'  - "{_yaml_escape(item)}"')
    yaml_lines.append(f'confidence: "{confidence}"')
    yaml_lines.append("```")

    normalized: list[str] = []
    if agent_name:
        normalized.extend([f"[Agent: {agent_name}]", ""])
    normalized.extend(
        [
            summary_marker,
            summary_line or "(missing)",
            "",
            findings_marker,
            *(f"- {item}" for item in findings),
            "",
            actions_marker,
            *(f"- [ ] {item}" for item in actions),
            "",
            yaml_marker,
            *yaml_lines,
        ]
    )

    return "\n".join(normalized).rstrip() + "\n", warnings


def _extract_agent_name(response_text: str) -> str:
    lines = response_text.strip().splitlines()
    first_line = lines[0] if lines else ""
    match = re.search(r"^\[Agent:\s*(.+?)\]\s*$", first_line)
    if match:
        return match.group(1).strip()
    inline = re.search(r"\[Agent:\s*(.+?)\]", response_text)
    if inline:
        return inline.group(1).strip()
    return "unknown"


def normalize_comment_body(body: str, agent_name: str | None = None) -> str:
    if not body:
        return body
    if not agent_name:
        inferred = _extract_agent_name(body)
        agent_name = inferred if inferred != "unknown" else None
    normalized, _warnings = _normalize_agent_output(body, agent_name)
    rules = _load_format_rules()
    yaml_marker = rules["sections"]["structured"]
    if yaml_marker in normalized:
        head, _sep, _tail = normalized.partition(yaml_marker)
        normalized = head.rstrip() + "\n"
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip() + "\n"
    return normalized


def trigger_mentioned_agents(
    response: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    policy: dict | None = None,
) -> tuple[dict[str, bool], list[str], list[str]]:
    """
    解析agent response中的@mentions，应用策略过滤，并触发允许的agent

    Args:
        response: Agent的response内容
        issue_number: Issue编号
        issue_title: Issue标题
        issue_body: Issue内容
        policy: @ 策略配置（None 则自动加载）

    Returns:
        (results, allowed_mentions, filtered_mentions)
    """
    mentions = extract_mentions_from_yaml(response)

    if not mentions:
        logger.info("[INFO] Response中没有@mentions")
        return {}, [], []

    logger.info(f"[INFO] 发现 {len(mentions)} 个@mentions: {mentions}")

    # 应用策略过滤
    allowed_mentions, filtered_mentions = filter_mentions(mentions, policy)

    if filtered_mentions:
        logger.info(f"[FILTER] 过滤了 {len(filtered_mentions)} 个@mentions: {filtered_mentions}")

    if not allowed_mentions:
        logger.info("[INFO] 没有允许的@mentions")
        return {}, [], filtered_mentions

    logger.info(f"[INFO] 允许触发 {len(allowed_mentions)} 个@mentions: {allowed_mentions}")

    from issuelab.observer_trigger import auto_trigger_agent

    results = {}
    for username in allowed_mentions:
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

    return results, allowed_mentions, filtered_mentions


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

    新增功能：
    1. 清理主体内容中的所有 @mentions（替换为"用户 xxx"）
    2. 应用策略过滤，区分允许和被过滤的 mentions
    3. 触发允许的 agents
    4. 返回清理后的主体内容和 mentions 信息

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
            "response": str,  # 原始回复
            "clean_response": str,  # 清理后的回复（所有 @ 替换为"用户 xxx"）
            "mentions": list[str],  # 所有提取的 mentions
            "allowed_mentions": list[str],  # 允许的 mentions
            "filtered_mentions": list[str],  # 被过滤的 mentions
            "dispatch_results": dict[str, bool]  # 触发结果
        }
    """
    # 提取response文本
    response_text = response.get("response", str(response)) if isinstance(response, dict) else str(response)
    raw_response_text = response_text

    normalized_response, format_warnings = _normalize_agent_output(response_text, agent_name)
    if format_warnings:
        logger.warning("Response format warnings for '%s': %s", agent_name, "; ".join(format_warnings))
    response_text = normalized_response

    # 提取所有 @mentions（基于原始回复，避免规范化后丢失）
    mentions = extract_mentions_from_yaml(raw_response_text)

    # 清理主体内容（将所有 @username 替换为 "用户 username"）
    clean_response = clean_mentions_in_text(response_text)

    result: dict[str, Any] = {
        "agent_name": agent_name,
        "response": response_text,
        "raw_response": raw_response_text,
        "clean_response": clean_response,
        "mentions": mentions,
        "allowed_mentions": [],
        "filtered_mentions": [],
        "dispatch_results": {},
        "format_warnings": format_warnings,
    }

    # 自动触发被@的agents
    if auto_dispatch and mentions:
        logger.info(f"🔗 {agent_name} 的response中@了 {len(mentions)} 个用户")
        dispatch_results, allowed_mentions, filtered_mentions = trigger_mentioned_agents(
            response_text, issue_number, issue_title, issue_body
        )
        result["dispatch_results"] = dispatch_results
        result["allowed_mentions"] = allowed_mentions
        result["filtered_mentions"] = filtered_mentions

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
            [
                "gh",
                "issue",
                "close",
                str(issue_number),
                "--repo",
                os.environ.get("GITHUB_REPOSITORY", ""),
                "--reason",
                "completed",
            ],
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
