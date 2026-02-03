"""主入口：支持多种子命令"""

import argparse
import asyncio
import json
import subprocess

from issuelab.config import Config
from issuelab.logging_config import get_logger, setup_logging
from issuelab.sdk_executor import (
    discover_agents,
    get_agent_matrix_markdown,
    run_agents_parallel,
    run_observer,
)
from issuelab.tools.github import get_issue_info, post_comment

# 初始化日志
setup_logging(level=Config.get_log_level(), log_file=Config.get_log_file())
logger = get_logger(__name__)


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
    observe_batch_parser.add_argument(
        "--auto-trigger", action="store_true", help="自动触发 agent（内置agent用label，用户agent用dispatch）"
    )
    observe_batch_parser.add_argument(
        "--post", action="store_true", help="自动发布触发评论到 Issue（已弃用，推荐使用 --auto-trigger）"
    )

    # 列出所有可用 Agent
    subparsers.add_parser("list-agents", help="列出所有可用的 Agent")

    # 个人Agent扫描命令（用于fork仓库）
    personal_scan_parser = subparsers.add_parser(
        "personal-scan", help="个人agent扫描主仓库issues（用于fork仓库）"
    )
    personal_scan_parser.add_argument("--agent", type=str, required=True, help="个人agent名称")
    personal_scan_parser.add_argument("--issues", type=str, required=True, help="候选issue编号（逗号分隔）")
    personal_scan_parser.add_argument(
        "--max-replies", type=int, default=3, help="最多回复的issue数量（默认3）"
    )
    personal_scan_parser.add_argument(
        "--repo", type=str, default="gqy20/IssueLab", help="主仓库名称（默认gqy20/IssueLab）"
    )

    # 个人Agent回复命令（用于fork仓库）
    personal_reply_parser = subparsers.add_parser(
        "personal-reply", help="个人agent回复主仓库issue（用于fork仓库）"
    )
    personal_reply_parser.add_argument("--agent", type=str, required=True, help="个人agent名称")
    personal_reply_parser.add_argument("--issue", type=int, required=True, help="Issue编号")
    personal_reply_parser.add_argument(
        "--repo", type=str, default="gqy20/IssueLab", help="主仓库名称（默认gqy20/IssueLab）"
    )
    personal_reply_parser.add_argument("--issue-title", type=str, default="", help="Issue标题（可选，用于优化）")
    personal_reply_parser.add_argument("--issue-body", type=str, default="", help="Issue内容（可选，用于优化）")
    personal_reply_parser.add_argument("--post", action="store_true", help="自动发布回复到主仓库")

    args = parser.parse_args()

    # 自动获取 Issue 信息（适用于 execute, review, observe）
    if args.command in ("execute", "review", "observe"):
        print(f"📥 正在获取 Issue #{args.issue} 信息...")
        issue_info = get_issue_info(args.issue, format_comments=True)

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
        for agent_name, result in results.items():
            response = result.get("response", str(result))
            cost_usd = result.get("cost_usd", 0.0)
            num_turns = result.get("num_turns", 0)
            tool_calls = len(result.get("tool_calls", []))

            print(f"\n=== {agent_name} result (成本: ${cost_usd:.4f}, 轮数: {num_turns}, 工具: {tool_calls}) ===")
            print(response)

            # 🔥 处理response中的@mentions（自动触发被@的agents）
            from issuelab.response_processor import process_agent_response

            processed = process_agent_response(
                agent_name=agent_name,
                response=result,
                issue_number=args.issue,
                issue_title=issue_info.get("title", ""),
                issue_body=issue_info.get("body", ""),
                auto_dispatch=True,  # 自动触发被@的agents
            )

            if processed["mentions"]:
                print(f"📬 发现 @mentions: {', '.join(processed['mentions'])}")
                for mentioned_user, success in processed["dispatch_results"].items():
                    status = "✅" if success else "❌"
                    print(f"  {status} 触发 {mentioned_user}")

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

        for agent_name, result in results.items():
            response = result.get("response", str(result))
            cost_usd = result.get("cost_usd", 0.0)
            num_turns = result.get("num_turns", 0)
            tool_calls = len(result.get("tool_calls", []))

            print(f"\n=== {agent_name} result (成本: ${cost_usd:.4f}, 轮数: {num_turns}, 工具: {tool_calls}) ===")
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

                # 🔥 自动触发 agent（通过 label 或 dispatch）
                if getattr(args, "auto_trigger", False):
                    from issuelab.observer_trigger import auto_trigger_agent

                    # 查找对应的 issue 数据
                    issue_info = next((d for d in issue_data_list if d["issue_number"] == issue_num), None)
                    if issue_info:
                        success = auto_trigger_agent(
                            agent_name=result.get("agent", ""),
                            issue_number=issue_num,
                            issue_title=issue_info.get("issue_title", ""),
                            issue_body=issue_info.get("issue_body", ""),
                        )
                        if success:
                            print("  🚀 已自动触发 agent")
                        else:
                            print("  ❌ 自动触发失败")

                # 如果需要，自动发布触发评论（已弃用，使用 auto_trigger 代替）
                elif getattr(args, "post", False):
                    comment = result.get("comment")
                    if comment and post_comment(issue_num, comment):
                        print("  ✅ 已发布触发评论（⚠️ 注意：bot评论不会触发workflow）")
                    else:
                        print("  ❌ 发布评论失败")
            else:
                print(f"  原因: {result.get('reason', 'N/A')}")

            if "error" in result:
                print(f"  ⚠️  错误: {result['error']}")

            print()

        print(f"\n总结: {triggered_count}/{len(results)} 个 Issues 需要触发 Agent")

    elif args.command == "personal-scan":
        # 个人Agent扫描主仓库issues
        import yaml

        from issuelab.personal_scan import scan_issues_for_personal_agent

        # 读取agent配置
        agent_config_path = f"agents/{args.agent}/agent.yml"
        try:
            with open(agent_config_path) as f:
                agent_config = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"❌ 未找到agent配置: {agent_config_path}")
            return 1

        # 解析issue编号
        issue_numbers = [int(n.strip()) for n in args.issues.split(",") if n.strip().isdigit()]

        if not issue_numbers:
            print("❌ 未提供有效的issue编号")
            return 1

        # 扫描issues
        result = scan_issues_for_personal_agent(
            agent_name=args.agent,
            agent_config=agent_config,
            issue_numbers=issue_numbers,
            repo=args.repo,
            max_replies=args.max_replies,
            username="",  # TODO: 从环境获取
        )

        # 输出JSON结果（供workflow解析）
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "personal-reply":
        # 个人Agent回复主仓库issue
        import json
        import os
        import subprocess
        import yaml

        # 读取agent配置
        agent_config_path = f"agents/{args.agent}/agent.yml"
        try:
            with open(agent_config_path) as f:
                agent_config = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"❌ 未找到agent配置: {agent_config_path}")
            return 1

        # 获取issue信息：优先使用传入的参数，否则从gh获取
        if args.issue_title and args.issue_body:
            issue_title = args.issue_title
            issue_body = args.issue_body
            print(f"使用传入的Issue信息")
        else:
            try:
                result = subprocess.run(
                    ["gh", "issue", "view", str(args.issue), "--repo", args.repo, "--json", "title,body"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                issue_data = json.loads(result.stdout)
                issue_title = issue_data.get("title", "")
                issue_body = issue_data.get("body", "")
                print(f"从主仓库获取Issue信息")
            except Exception as e:
                print(f"❌ 获取issue信息失败: {e}")
                return 1

        # 构建更详细的上下文，明确告诉Agent应该做什么
        context = f"""你被邀请参与讨论 GitHub Issue #{args.issue}。

**Issue 标题**: {issue_title}

**Issue 内容**:
{issue_body}

**你的任务**:
请根据你的专业领域（见你的 prompt.md 配置），对这个 Issue 提供有价值的见解、建议或评审意见。

**要求**:
1. 基于 Issue 的具体内容发表观点
2. 提供建设性的建议或解决方案
3. 如果相关，可以分享类似案例或最佳实践
4. 保持专业和友好的语气
5. 回复应该简洁明了，聚焦核心观点

请直接给出你的回复内容，不需要任何前缀（系统会自动处理）。"""

        # 执行agent
        print(f"🚀 使用 {args.agent} 分析 {args.repo}#{args.issue}")
        results = asyncio.run(run_agents_parallel(args.issue, [args.agent], context, 0))

        if args.agent not in results:
            print(f"❌ Agent {args.agent} 执行失败")
            return 1

        result = results[args.agent]
        response = result.get("response", str(result))

        print(f"\n=== {args.agent} Response ===")
        print(response)

        # 发布到主仓库
        if getattr(args, "post", False):
            try:
                # 检查是否配置了PAT
                gh_token = os.environ.get("GH_TOKEN", "")
                if gh_token == os.environ.get("GITHUB_TOKEN", ""):
                    print(
                        "\n⚠️  警告: 使用默认 GITHUB_TOKEN 可能无法跨仓库评论"
                        "\n建议: 配置 PAT_TOKEN secret 以显示用户身份并获得完整权限"
                        "\n详见: agents/_template/agent.yml 中的 GitHub Token 配置说明\n"
                    )

                subprocess.run(
                    ["gh", "issue", "comment", str(args.issue), "--repo", args.repo, "--body", response],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                print(f"✅ 已发布到 {args.repo}#{args.issue}")
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                print(f"❌ 发布失败: {error_msg}")

                # 判断是否为权限问题
                if "not accessible" in error_msg.lower() or "forbidden" in error_msg.lower():
                    print(
                        "\n💡 这可能是权限问题！"
                        "\n解决方法："
                        "\n1. 在你的 fork 仓库设置 PAT_TOKEN secret"
                        "\n2. 创建 PAT: Settings → Developer settings → Personal access tokens"
                        "\n3. 需要权限: repo (评论) + workflow (触发)"
                        "\n\n配置后，你的回复会显示为真实用户名，而非 bot\n"
                    )

                # 将结果输出到文件，供workflow使用
                output_file = os.environ.get("GITHUB_OUTPUT")
                if output_file:
                    with open(output_file, "a") as f:
                        # 转义换行符
                        escaped_response = response.replace("\n", "%0A").replace("\r", "%0D")
                        f.write(f"agent_response={escaped_response}\n")
                        f.write(f"comment_failed=true\n")
                    print("📝 结果已保存到 GITHUB_OUTPUT，workflow可以处理")

                return 1
            except Exception as e:
                print(f"❌ 发布失败: {e}")
                return 1

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
