"""主入口：支持多种子命令"""
import asyncio
import argparse
import os
from issuelab.sdk_executor import run_agents_parallel
from issuelab.parser import parse_mentions


def main():
    parser = argparse.ArgumentParser(description="Issue Lab Agent")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # @mention 并行执行
    execute_parser = subparsers.add_parser("execute", help="并行执行代理")
    execute_parser.add_argument("--issue", type=int, required=True)
    execute_parser.add_argument("--agents", type=str, required=True, help="空格分隔的代理名称")

    # 顺序评审流程
    review_parser = subparsers.add_parser("review", help="运行顺序评审流程")
    review_parser.add_argument("--issue", type=int, required=True)

    args = parser.parse_args()

    if args.command == "execute":
        agents = args.agents.split()
        results = asyncio.run(run_agents_parallel(args.issue, agents))
        for agent_name, response in results.items():
            print(f"\n=== {agent_name} result ===")
            print(response)
    elif args.command == "review":
        # 顺序执行：moderator -> reviewer_a -> reviewer_b -> summarizer
        agents = ["moderator", "reviewer_a", "reviewer_b", "summarizer"]
        results = asyncio.run(run_agents_parallel(args.issue, agents))
        for agent_name, response in results.items():
            print(f"\n=== {agent_name} result ===")
            print(response)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
