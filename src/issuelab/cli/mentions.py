"""
解析 Issue/Comment 中的 @mentions

提取可复用的 mention 解析逻辑。
"""

import argparse
import json
import os
import re
import sys


def parse_mentions(text: str) -> list[str]:
    """
    从文本中提取所有 @mentions

    Args:
        text: 要解析的文本

    Returns:
        提取到的用户名列表（不包含 @），去重保持顺序

    Example:
        >>> parse_mentions("@alice and @bob, please review")
        ['alice', 'bob']
        >>> parse_mentions("@alice @alice @bob")
        ['alice', 'bob']
    """
    if not text:
        return []

    # 匹配 @username 模式
    # GitHub 用户名规则：字母、数字、连字符，不能以连字符开头或结尾
    pattern = r"@([a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)"
    matches = re.findall(pattern, text)

    # 去重并保持顺序
    seen = set()
    result = []
    for username in matches:
        if username not in seen:
            seen.add(username)
            result.append(username)

    return result


def write_github_output(mentions: list[str]) -> None:
    """
    写入 GitHub Actions 输出变量

    Args:
        mentions: mention 列表
    """
    if "GITHUB_OUTPUT" not in os.environ:
        return

    try:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            # 使用逗号分隔格式，避免 shell 引号问题
            f.write(f"mentions={','.join(mentions)}\n")
            f.write(f"count={len(mentions)}\n")
    except OSError as e:
        print(f"Warning: Failed to write GitHub output: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """
    CLI 入口点

    Args:
        argv: 命令行参数，None 则使用 sys.argv

    Returns:
        退出码，0 表示成功
    """
    parser = argparse.ArgumentParser(description="Parse @mentions from GitHub Issue/Comment")
    parser.add_argument("--issue-body", help="Issue body text", default="")
    parser.add_argument("--comment-body", help="Comment body text", default="")
    parser.add_argument("--output", default="csv", choices=["json", "csv", "text"], help="Output format (default: csv)")

    args = parser.parse_args(argv)

    # 合并 Issue body 和 Comment body
    text = args.issue_body + "\n" + args.comment_body

    if not text.strip():
        print("Error: No text provided", file=sys.stderr)
        return 1

    # 解析 mentions
    mentions = parse_mentions(text)

    # 输出
    if args.output == "json":
        print(json.dumps({"mentions": mentions, "count": len(mentions)}))
    elif args.output == "csv":
        # 逗号分隔格式，适合 shell 使用
        print(",".join(mentions))
    else:  # text
        for mention in mentions:
            print(mention)

    # 写入 GitHub Actions 输出
    write_github_output(mentions)

    return 0


if __name__ == "__main__":
    sys.exit(main())
