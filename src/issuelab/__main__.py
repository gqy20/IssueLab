"""主入口：支持多种子命令"""
import asyncio
import argparse
import os
from issuelab.executor import run_parallel_agents
from issuelab.parser import parse_mentions


def main():
    parser = argparse.ArgumentParser(description="Issue Lab Agent")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # @mention 并行执行
    execute_parser = subparsers.add_parser("execute", help="并行执行代理")
    execute_parser.add_argument("--issue", type=int, required=True)
    execute_parser.add_argument("--agents", type=str, required=True, help="空格分隔的代理名称")

    args = parser.parse_args()

    if args.command == "execute":
        agents = args.agents.split()
        asyncio.run(run_parallel_agents(args.issue, agents))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
