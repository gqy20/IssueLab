"""主入口：支持多种子命令"""

import argparse
import asyncio
import json
import os
import subprocess

from issuelab.agents.discovery import discover_agents, get_agent_matrix_markdown
from issuelab.agents.executor import run_agents_parallel
from issuelab.agents.observer import run_observer
from issuelab.config import Config
from issuelab.logging_config import get_logger, setup_logging
from issuelab.tools import github as github_tools
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

    # 列出所有可用 Agent
    subparsers.add_parser("list-agents", help="列出所有可用的 Agent")

    # 个人Agent扫描命令（用于fork仓库）
    personal_scan_parser = subparsers.add_parser("personal-scan", help="个人agent扫描主仓库issues（用于fork仓库）")
    personal_scan_parser.add_argument("--agent", type=str, required=True, help="个人agent名称")
    personal_scan_parser.add_argument("--issues", type=str, required=True, help="候选issue编号（逗号分隔）")
    personal_scan_parser.add_argument("--max-replies", type=int, default=3, help="最多回复的issue数量（默认3）")
    personal_scan_parser.add_argument(
        "--repo", type=str, default="gqy20/IssueLab", help="主仓库名称（默认gqy20/IssueLab）"
    )

    # 个人Agent回复命令（用于fork仓库）
    personal_reply_parser = subparsers.add_parser("personal-reply", help="个人agent回复主仓库issue（用于fork仓库）")
    personal_reply_parser.add_argument("--agent", type=str, required=True, help="个人agent名称")
    personal_reply_parser.add_argument("--issue", type=int, required=True, help="Issue编号")
    personal_reply_parser.add_argument(
        "--repo", type=str, default="gqy20/IssueLab", help="主仓库名称（默认gqy20/IssueLab）"
    )
    personal_reply_parser.add_argument("--issue-title", type=str, default="", help="Issue标题（可选，用于优化）")
    personal_reply_parser.add_argument("--issue-body", type=str, default="", help="Issue内容（可选，用于优化）")
    personal_reply_parser.add_argument(
        "--available-agents", type=str, default="", help="系统中可用的智能体列表（JSON格式）"
    )
    personal_reply_parser.add_argument("--post", action="store_true", help="自动发布回复到主仓库")

    args = parser.parse_args()

    # 自动获取 Issue 信息（适用于 execute, review, observe）
    if args.command in ("execute", "review", "observe"):
        print(f"[INFO] 正在获取 Issue #{args.issue} 信息...")
        issue_info = get_issue_info(args.issue, format_comments=True)

        from issuelab.tools.github import write_issue_context_file

        issue_file = write_issue_context_file(
            issue_number=args.issue,
            title=issue_info.get("title", ""),
            body=issue_info.get("body", ""),
            comments=issue_info.get("comments", ""),
            comment_count=issue_info.get("comment_count", 0),
        )

        # 构建上下文（改为文件引用，避免超长 prompt）
        context = f"**Issue 内容文件**: {issue_file}\n" "请使用 Read 工具读取该文件后再进行分析。"
        comment_count = issue_info["comment_count"]
        comments = issue_info["comments"]

        print(f"[OK] 已获取: 标题={issue_info['title'][:30]}..., 评论数={comment_count}")
    else:
        context = ""
        comment_count = 0
        comments = ""
        issue_info = {}
        issue_file = ""

    if args.command == "execute":
        agents = parse_agents_arg(args.agents)

        if not agents:
            print("[ERROR] 未提供有效的 agent 名称")
            return 1

        print(f"[START] 执行 agents: {agents}")

        trigger_comment = os.environ.get("ISSUELAB_TRIGGER_COMMENT", "")
        results = asyncio.run(
            run_agents_parallel(args.issue, agents, context, comment_count, trigger_comment=trigger_comment)
        )

        # 输出结果
        for agent_name, result in results.items():
            response = result.get("response", str(result))
            cost_usd = result.get("cost_usd", 0.0)
            num_turns = result.get("num_turns", 0)
            tool_calls = len(result.get("tool_calls", []))

            print(f"\n=== {agent_name} result (成本: ${cost_usd:.4f}, 轮数: {num_turns}, 工具: {tool_calls}) ===")
            print(response)

            # 如果需要，自动发布到 Issue（auto_clean 会自动处理 @mentions）
            if getattr(args, "post", False):
                if post_comment(args.issue, response, agent_name=agent_name):
                    print(f"[OK] {agent_name} response posted to issue #{args.issue}")
                else:
                    print(f"[ERROR] Failed to post {agent_name} response")

    elif args.command == "review":
        # 顺序执行：moderator -> reviewer_a -> reviewer_b -> summarizer
        agents = ["moderator", "reviewer_a", "reviewer_b", "summarizer"]
        trigger_comment = os.environ.get("ISSUELAB_TRIGGER_COMMENT", "")
        results = asyncio.run(
            run_agents_parallel(args.issue, agents, context, comment_count, trigger_comment=trigger_comment)
        )

        for agent_name, result in results.items():
            response = result.get("response", str(result))
            cost_usd = result.get("cost_usd", 0.0)
            num_turns = result.get("num_turns", 0)
            tool_calls = len(result.get("tool_calls", []))

            print(f"\n=== {agent_name} result (成本: ${cost_usd:.4f}, 轮数: {num_turns}, 工具: {tool_calls}) ===")
            print(response)

            # 如果需要，自动发布到 Issue（auto_clean 会自动处理 @mentions）
            if getattr(args, "post", False):
                if post_comment(args.issue, response, agent_name=agent_name):
                    print(f"[OK] {agent_name} response posted to issue #{args.issue}")
                else:
                    print(f"[ERROR] Failed to post {agent_name} response")

            # 如果是 summarator，检查是否需要自动关闭
            if agent_name == "summarizer":
                from issuelab.response_processor import close_issue, should_auto_close

                if should_auto_close(response, agent_name):
                    print(f"\n[INFO] 检测到 [CLOSE] 标记，正在自动关闭 Issue #{args.issue}...")
                    if close_issue(args.issue):
                        print(f"[OK] Issue #{args.issue} 已自动关闭")
                    else:
                        print("[ERROR] 自动关闭失败")

    elif args.command == "observe":
        # 运行 Observer Agent 分析 Issue
        issue_body_ref = (
            f"内容已保存至文件: {issue_file}\n请使用 Read 工具读取该文件后再分析。"
            if issue_file
            else (issue_info.get("body", "") or "无内容")
        )
        comments_ref = "历史评论已包含在同一文件中。" if issue_file else (comments or "无评论")

        result = asyncio.run(run_observer(args.issue, issue_info.get("title", ""), issue_body_ref, comments_ref))

        print(f"\n=== Observer Analysis for Issue #{args.issue} ===")
        print(f"\nAnalysis:\n{result.get('analysis', 'N/A')}")
        print(f"\nShould Trigger: {result.get('should_trigger', False)}")
        if result.get("should_trigger"):
            print(f"Agent: {result.get('agent', 'N/A')}")
            print(f"Trigger Comment: {result.get('comment', 'N/A')}")
            print(f"Reason: {result.get('reason', 'N/A')}")

            # 如果需要，自动发布触发评论（auto_clean 会自动处理 @mentions）
            if getattr(args, "post", False):
                if result.get("comment") and post_comment(args.issue, result["comment"], agent_name="observer"):
                    print(f"\n[OK] Trigger comment posted to issue #{args.issue}")
                else:
                    print("\n[ERROR] Failed to post trigger comment")
        else:
            print(f"Skip Reason: {result.get('reason', 'N/A')}")

    elif args.command == "observe-batch":
        # 并行分析多个 Issues
        issue_numbers = [int(i.strip()) for i in args.issues.split(",") if i.strip()]

        if not issue_numbers:
            print("[ERROR] 未提供有效的 Issue 编号")
            return

        print(f"\n=== 并行分析 {len(issue_numbers)} 个 Issues ===")

        # 获取所有 Issues 的详情
        issue_data_list = []
        for issue_num in issue_numbers:
            try:
                data = get_issue_info(issue_num, format_comments=True)

                issue_file = github_tools.write_issue_context_file(
                    issue_number=issue_num,
                    title=data.get("title", ""),
                    body=data.get("body", ""),
                    comments=data.get("comments", ""),
                    comment_count=data.get("comment_count", 0),
                )

                issue_data_list.append(
                    {
                        "issue_number": issue_num,
                        "issue_title": data.get("title", ""),
                        "issue_body": f"内容已保存至文件: {issue_file}\n请使用 Read 工具读取该文件后再分析。",
                        "comments": "历史评论已包含在同一文件中。",
                    }
                )
            except Exception as e:
                print(f"[WARNING] 获取 Issue #{issue_num} 失败: {e}")
                continue

        if not issue_data_list:
            print("[ERROR] 无有效的 Issue 数据")
            return

        # 并行分析
        from issuelab.agents.observer import run_observer_batch

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
            print(f"  触发: {'[OK] 是' if should_trigger else '[ERROR] 否'}")

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
                            print("  [OK] 已自动触发 agent")
                        else:
                            print("  [ERROR] 自动触发失败")

            else:
                print(f"  原因: {result.get('reason', 'N/A')}")

            if "error" in result:
                print(f"  [WARNING] 错误: {result['error']}")

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
            print(f"[ERROR] 未找到agent配置: {agent_config_path}")
            return 1

        # 解析issue编号
        issue_numbers = [int(n.strip()) for n in args.issues.split(",") if n.strip().isdigit()]

        if not issue_numbers:
            print("[ERROR] 未提供有效的issue编号")
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
        import yaml

        # 读取agent配置
        agent_config_path = f"agents/{args.agent}/agent.yml"
        try:
            with open(agent_config_path) as f:
                agent_config = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"[ERROR] 未找到agent配置: {agent_config_path}")
            return 1

        # 获取issue信息：优先使用传入的参数，否则从gh获取
        if args.issue_title and args.issue_body:
            issue_title = args.issue_title
            issue_body = args.issue_body
            print("使用传入的Issue信息")
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
                print("从主仓库获取Issue信息")
            except Exception as e:
                print(f"[ERROR] 获取issue信息失败: {e}")
                return 1

        # 构建简洁明确的上下文
        context = f"""你被邀请参与 GitHub Issue #{args.issue} 的讨论。

**Issue 标题**: {issue_title}

**Issue 内容**:
{issue_body}

**你的任务**:
基于你的专业知识和经验，对这个Issue提供有价值的见解、建议或评审意见。

**回复要求**:
1. 直接针对Issue的具体内容发表观点
2. 提供建设性的建议或可行的解决方案
3. 如相关可分享类似案例或最佳实践
4. 保持专业、友好、简洁的语气

请直接给出你的专业回复，不需要任何前缀或说明。"""

        # 解析available_agents
        available_agents = None
        if hasattr(args, "available_agents") and args.available_agents:
            try:
                available_agents = json.loads(args.available_agents)
                print(f"[INFO] 收到 {len(available_agents)} 个可用智能体信息")
            except json.JSONDecodeError as e:
                print(f"[WARNING] 解析available_agents失败: {e}")

        # 执行agent
        print(f"[START] 使用 {args.agent} 分析 {args.repo}#{args.issue}")
        trigger_comment = os.environ.get("ISSUELAB_TRIGGER_COMMENT", "")
        results = asyncio.run(
            run_agents_parallel(args.issue, [args.agent], context, 0, available_agents, trigger_comment=trigger_comment)
        )

        if args.agent not in results:
            print(f"[ERROR] Agent {args.agent} 执行失败")
            return 1

        result = results[args.agent]
        response = result.get("response", str(result))

        print(f"\n=== {args.agent} Response ===")
        print(response)

        # 发布到主仓库（使用 post_comment 统一处理）
        if getattr(args, "post", False):
            # 使用 post_comment 统一处理（auto_clean 会自动处理 @mentions）
            if post_comment(args.issue, response, agent_name=args.agent, repo=args.repo):
                print(f"[OK] 已发布到 {args.repo}#{args.issue}")
            else:
                print(f"[ERROR] 发布到 {args.repo}#{args.issue} 失败")
                # 将结果输出到文件，供workflow使用
                output_file = os.environ.get("GITHUB_OUTPUT")
                if output_file:
                    try:
                        with open(output_file, "a") as f:
                            # 转义换行符
                            escaped_response = response.replace("\n", "%0A").replace("\r", "%0D")
                            f.write(f"agent_response={escaped_response}\n")
                            f.write("comment_failed=true\n")
                        print("[INFO] 结果已保存到 GITHUB_OUTPUT，workflow可以处理")
                    except Exception as e:
                        print(f"[WARNING] 保存到 GITHUB_OUTPUT 失败: {e}")

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
