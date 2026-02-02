"""主入口：支持多种子命令"""

import argparse
import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path

from issuelab.logging_config import get_logger, setup_logging
from issuelab.sdk_executor import (
    discover_agents,
    get_agent_matrix_markdown,
    run_agents_parallel,
    run_observer,
)

# 评论最大长度 (GitHub 限制 65536，实际使用 10000 留余量)
MAX_COMMENT_LENGTH = 10000

# 初始化日志
log_level = os.environ.get("LOG_LEVEL", "INFO")
log_file = os.environ.get("LOG_FILE")
log_file_path = Path(log_file) if log_file else None
setup_logging(level=log_level, log_file=log_file_path)
logger = get_logger(__name__)


def fetch_issue_info(issue_number: int) -> dict:
    """
    通过 gh 命令获取 Issue 信息

    Args:
        issue_number: Issue 编号

    Returns:
        包含 title, body, comments, comment_count 的字典
    """
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--json", "title,body,comments"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)

        # 格式化评论
        comments_list = []
        for comment in data.get("comments", []):
            author = comment.get("author", {}).get("login", "unknown")
            created_at = comment.get("createdAt", "")[:10]  # 只取日期部分
            body = comment.get("body", "")
            comments_list.append(f"- **[{author}]** ({created_at}):\n{body}")

        return {
            "title": data.get("title", ""),
            "body": data.get("body", ""),
            "comments": "\n\n".join(comments_list),
            "comment_count": len(data.get("comments", [])),
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"获取 Issue #{issue_number} 信息失败: {e.stderr}")
        return {"title": "", "body": "", "comments": "", "comment_count": 0}
    except json.JSONDecodeError as e:
        logger.error(f"解析 Issue #{issue_number} JSON 失败: {e}")
        return {"title": "", "body": "", "comments": "", "comment_count": 0}


def parse_agents_arg(agents_str: str) -> list[str]:
    """
    解析 agents 参数，支持多种格式

    Args:
        agents_str: agents 字符串，支持:
            - 逗号分隔: "echo,test"
            - 空格分隔: "echo test"
            - JSON 数组: '["echo", "test"]'

    Returns:
        agent 名称列表（小写）
    """
    agents_str = agents_str.strip()

    # JSON 数组格式
    if agents_str.startswith("[") and agents_str.endswith("]"):
        try:
            agents = json.loads(agents_str)
            return [agent.lower() for agent in agents]
        except json.JSONDecodeError:
            logger.warning(f"JSON 格式解析失败，尝试其他格式: {agents_str}")

    # 逗号分隔格式（优先）
    if "," in agents_str:
        return [a.strip().lower() for a in agents_str.split(",") if a.strip()]

    # 空格分隔格式
    return [a.lower() for a in agents_str.split() if a]


def truncate_text(text: str, max_length: int = MAX_COMMENT_LENGTH) -> str:
    """截断文本到指定长度，保留完整段落"""
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


def post_comment(issue_number: int, body: str) -> bool:
    """发布评论到 Issue，自动截断过长内容"""
    # 截断内容
    truncated_body = truncate_text(body, MAX_COMMENT_LENGTH)

    # 使用临时文件避免命令行长度限制
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(truncated_body)
        f.flush()
        # 优先使用 GH_TOKEN，fallback 到 GITHUB_TOKEN
        env = os.environ.copy()
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            env["GH_TOKEN"] = token
        result = subprocess.run(
            ["gh", "issue", "comment", str(issue_number), "--body-file", f.name],
            capture_output=True,
            text=True,
            env=env,
        )
        os.unlink(f.name)

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Issue Lab Agent")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # @mention 并行执行（简化版）
    execute_parser = subparsers.add_parser("execute", help="并行执行代理")
    execute_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    execute_parser.add_argument("--agents", type=str, required=True, help="代理名称（逗号分隔）")
    execute_parser.add_argument("--post", action="store_true", help="自动发布结果到 Issue")

    # 顺序评审流程（简化版）
    review_parser = subparsers.add_parser("review", help="运行顺序评审流程")
    review_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    review_parser.add_argument("--post", action="store_true", help="自动发布结果到 Issue")

    # Observer 监控命令（简化版）
    observe_parser = subparsers.add_parser("observe", help="运行 Observer Agent 分析 Issue")
    observe_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    observe_parser.add_argument("--post", action="store_true", help="自动发布触发评论到 Issue")

    # Observer 批量分析命令（并行）
    observe_batch_parser = subparsers.add_parser("observe-batch", help="并行分析多个 Issues")
    observe_batch_parser.add_argument("--issues", type=str, required=True, help="Issue 编号列表（逗号分隔）")
    observe_batch_parser.add_argument("--post", action="store_true", help="自动发布触发评论到 Issue")

    # 列出所有可用 Agent
    subparsers.add_parser("list-agents", help="列出所有可用的 Agent")

    args = parser.parse_args()

    # 自动获取 Issue 信息（适用于 execute, review, observe）
    if args.command in ("execute", "review", "observe"):
        print(f"📥 正在获取 Issue #{args.issue} 信息...")
        issue_info = fetch_issue_info(args.issue)

        # 构建上下文
        context = f"**Issue 标题**: {issue_info['title']}\n\n**Issue 内容**:\n{issue_info['body']}"
        comment_count = issue_info["comment_count"]
        comments = issue_info["comments"]

        if comment_count > 0 and comments:
            context += f"\n\n**本 Issue 共有 {comment_count} 条历史评论，请仔细阅读并分析：**\n\n{comments}"

        print(f"✅ 已获取: 标题={issue_info['title'][:30]}..., 评论数={comment_count}")
    else:
        context = ""
        comment_count = 0
        comments = ""
        issue_info = {}

    if args.command == "execute":
        agents = parse_agents_arg(args.agents)

        if not agents:
            print("❌ 未提供有效的 agent 名称")
            return 1

        print(f"🚀 执行 agents: {agents}")

        results = asyncio.run(run_agents_parallel(args.issue, agents, context, comment_count))

        # 输出结果
        for agent_name, response in results.items():
            print(f"\n=== {agent_name} result ===")
            print(response)

            # 如果需要，自动发布到 Issue
            if getattr(args, "post", False):
                if post_comment(args.issue, response):
                    print(f"✅ {agent_name} response posted to issue #{args.issue}")
                else:
                    print(f"❌ Failed to post {agent_name} response")

    elif args.command == "review":
        # 顺序执行：moderator -> reviewer_a -> reviewer_b -> summarizer
        agents = ["moderator", "reviewer_a", "reviewer_b", "summarizer"]
        results = asyncio.run(run_agents_parallel(args.issue, agents, context, comment_count))

        for agent_name, response in results.items():
            print(f"\n=== {agent_name} result ===")
            print(response)

            # 如果需要，自动发布到 Issue
            if getattr(args, "post", False):
                if post_comment(args.issue, response):
                    print(f"✅ {agent_name} response posted to issue #{args.issue}")
                else:
                    print(f"❌ Failed to post {agent_name} response")

    elif args.command == "observe":
        # 运行 Observer Agent 分析 Issue
        result = asyncio.run(
            run_observer(args.issue, issue_info.get("title", ""), issue_info.get("body", ""), comments)
        )

        print(f"\n=== Observer Analysis for Issue #{args.issue} ===")
        print(f"\nAnalysis:\n{result.get('analysis', 'N/A')}")
        print(f"\nShould Trigger: {result.get('should_trigger', False)}")
        if result.get("should_trigger"):
            print(f"Agent: {result.get('agent', 'N/A')}")
            print(f"Trigger Comment: {result.get('comment', 'N/A')}")
            print(f"Reason: {result.get('reason', 'N/A')}")

            # 如果需要，自动发布触发评论
            if getattr(args, "post", False):
                if result.get("comment") and post_comment(args.issue, result["comment"]):
                    print(f"\n✅ Trigger comment posted to issue #{args.issue}")
                else:
                    print("\n❌ Failed to post trigger comment")
        else:
            print(f"Skip Reason: {result.get('reason', 'N/A')}")

    elif args.command == "observe-batch":
        # 并行分析多个 Issues
        issue_numbers = [int(i.strip()) for i in args.issues.split(",") if i.strip()]

        if not issue_numbers:
            print("❌ 未提供有效的 Issue 编号")
            return

        print(f"\n=== 并行分析 {len(issue_numbers)} 个 Issues ===")

        # 获取所有 Issues 的详情
        issue_data_list = []
        for issue_num in issue_numbers:
            try:
                # 使用 gh 命令获取 Issue 详情
                result = subprocess.run(
                    ["gh", "issue", "view", str(issue_num), "--json", "title,body,comments"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                import json

                data = json.loads(result.stdout)

                # 格式化评论
                comments = []
                for comment in data.get("comments", []):
                    author = comment.get("author", {}).get("login", "unknown")
                    body = comment.get("body", "")
                    comments.append(f"- **[{author}]**: {body}")

                issue_data_list.append(
                    {
                        "issue_number": issue_num,
                        "issue_title": data.get("title", ""),
                        "issue_body": data.get("body", ""),
                        "comments": "\n".join(comments),
                    }
                )
            except Exception as e:
                print(f"⚠️  获取 Issue #{issue_num} 失败: {e}")
                continue

        if not issue_data_list:
            print("❌ 无有效的 Issue 数据")
            return

        # 并行分析
        from issuelab.sdk_executor import run_observer_batch

        results = asyncio.run(run_observer_batch(issue_data_list))

        # 输出结果
        print(f"\n{'=' * 60}")
        print(f"分析完成：{len(results)} 个 Issues")
        print(f"{'=' * 60}\n")

        triggered_count = 0
        for result in results:
            issue_num = result.get("issue_number")
            should_trigger = result.get("should_trigger", False)

            print(f"Issue #{issue_num}:")
            print(f"  触发: {'✅ 是' if should_trigger else '❌ 否'}")

            if should_trigger:
                triggered_count += 1
                print(f"  Agent: {result.get('agent', 'N/A')}")
                print(f"  理由: {result.get('reason', 'N/A')}")

                # 如果需要，自动发布触发评论
                if getattr(args, "post", False):
                    comment = result.get("comment")
                    if comment and post_comment(issue_num, comment):
                        print("  ✅ 已发布触发评论")
                    else:
                        print("  ❌ 发布评论失败")
            else:
                print(f"  原因: {result.get('reason', 'N/A')}")

            if "error" in result:
                print(f"  ⚠️  错误: {result['error']}")

            print()

        print(f"\n总结: {triggered_count}/{len(results)} 个 Issues 需要触发 Agent")

    elif args.command == "list-agents":
        # 列出所有可用的 Agent
        agents = discover_agents()
        print("\n=== Available Agents ===\n")
        print(f"{'Agent':<15} {'Description':<50} {'Trigger Conditions'}")
        print("-" * 100)
        for name, config in agents.items():
            conditions = config.get("trigger_conditions", [])
            if conditions and all(isinstance(c, str) for c in conditions):
                conditions_str = ", ".join(conditions)
            else:
                conditions_str = "auto-detect"
            desc = config.get("description", "")[:48]
            print(f"{name:<15} {desc:<50} {conditions_str[:40]}")

        print("\n\n=== Agent Matrix (for Observer) ===\n")
        print(get_agent_matrix_markdown())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
