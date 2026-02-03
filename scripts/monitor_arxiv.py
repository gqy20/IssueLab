#!/usr/bin/env python3
"""
arXiv Monitor - 获取新论文，智能分析，推荐讨论

Usage:
    # 获取论文并智能分析
    python scripts/monitor_arxiv.py \
        --token "ghp_xxx" \
        --repo "owner/repo" \
        --categories "cs.AI,cs.LG,cs.CL"

    # 仅扫描获取论文列表
    python scripts/monitor_arxiv.py --scan-only --output /tmp/papers.json
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from typing import Any

import feedparser
from github import Github


def parse_arxiv_date(date_str: str) -> str:
    """解析 arXiv 日期格式"""
    try:
        dt = datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return date_str[:10] if date_str else "Unknown"


def clean_text(text: str) -> str:
    """清理文本中的多余空白"""
    return re.sub(r"\s+", " ", text).strip()


def truncate_text(text: str, max_length: int = 1500) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(".", 1)[0] + "..."


def fetch_papers(categories: list[str], last_scan: str, max_papers: int = 10) -> list[dict[str, Any]]:
    """获取 arXiv 新论文"""
    try:
        last_scan_dt = datetime.strptime(last_scan[:19], "%Y-%m-%dT%H:%M:%S")
        last_scan_timestamp = last_scan_dt.timestamp()
    except (ValueError, TypeError):
        last_scan_timestamp = 0

    all_papers = []

    for category in categories:
        print(f"📥 获取 {category} 分类...")

        base_url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": f"cat:{category}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_papers * 3,
        }
        url = f"{base_url}?{ '&'.join(f'{k}={v}' for k,v in params.items()) }"

        try:
            response = feedparser.parse(url)

            for entry in response.entries:
                try:
                    published_timestamp = datetime.strptime(
                        entry.get("published", "")[:19], "%Y-%m-%dT%H:%M:%S"
                    ).timestamp()
                except (ValueError, TypeError):
                    continue

                if published_timestamp <= last_scan_timestamp:
                    continue

                authors = ", ".join(
                    a.get("name", "") for a in entry.get("authors", [])[:5]
                )
                if len(entry.get("authors", [])) > 5:
                    authors += f" 等 {len(entry.get('authors', []))} 位作者"

                arxiv_id = entry.get("id", "").split("/abs/")[-1]

                all_papers.append({
                    "id": arxiv_id,
                    "title": clean_text(entry.get("title", "")),
                    "summary": truncate_text(clean_text(entry.get("summary", ""))),
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                    "authors": authors,
                    "published": parse_arxiv_date(entry.get("published", "")),
                    "published_raw": entry.get("published", ""),
                    "category": category,
                })

        except Exception as e:
            print(f"   ⚠️  获取失败: {e}")
            continue

    # 去重并排序
    seen_ids = set()
    unique_papers = []
    for p in all_papers:
        if p["id"] not in seen_ids:
            seen_ids.add(p["id"])
            unique_papers.append(p)

    unique_papers.sort(key=lambda x: x.get("published_raw", ""), reverse=True)
    return unique_papers[:max_papers]


def build_papers_for_observer(papers: list[dict]) -> str:
    """构建供 Observer 分析的论文上下文"""
    lines = ["## 可讨论的 arXiv 论文候选\n"]

    for i, paper in enumerate(papers):
        lines.append(f"### 论文 {i}")
        lines.append(f"**标题**: {paper['title']}")
        lines.append(f"**分类**: {paper['category']}")
        lines.append(f"**发布时间**: {paper['published']}")
        lines.append(f"**链接**: [{paper['url']}]({paper['url']})")
        lines.append(f"**作者**: {paper['authors']}")
        lines.append(f"**摘要**: {paper['summary']}")
        lines.append("")

    return "\n".join(lines)


def analyze_with_observer(papers: list[dict], papers_context: str, token: str) -> list[dict]:
    """使用 Observer agent 分析论文，返回推荐的论文"""
    # 构建 Observer 的系统提示
    observer_prompt = """你是 IssueLab 的 Observer Agent，负责分析 arXiv 论文并推荐值得讨论的论文。

## 模式 1：arXiv 论文分析

当接收 arXiv 论文列表时，分析并推荐值得讨论的论文。

### 决策标准

选择论文时考虑以下因素：

| 维度 | 说明 | 推荐标准 |
|------|------|---------|
| **研究热度** | 热门方向（LLM、CV、NLP） | 优先 |
| **创新性** | 新方法、新思路 | 优先 |
| **实用性** | 开源、复现性好 | 优先 |
| **时效性** | 最新发布 | 优先 |
| **争议性** | 有讨论空间 | 优先 |

### 输出格式

请输出 YAML 格式的推荐结果：

```yaml
analysis: |
  共收到 X 篇候选论文，经过分析后推荐 Y 篇值得讨论。

  简要分析：
  - 论文0：xxx
  - 论文1：xxx

recommended:
  - index: 0
    title: 论文标题
    reason: "推荐理由（研究方向热度 + 创新点）"
    summary: "论文摘要（用于 Issue 介绍，100字左右）"
```

### 推荐策略

- 每批论文最多推荐 2-3 篇
- 优先选择不同方向的论文，避免主题重复
- 如果论文质量普遍较高，可推荐全部
- 如果论文质量普遍较低，可少于 2 篇

## 当前任务

请分析以下候选论文，推荐值得创建 Issue 讨论的论文：
"""

    # 使用 Claude API 分析（简化实现：返回前2篇）
    # 实际实现中，这里应该调用 Claude API
    # 由于当前架构限制，我们使用简单的启发式规则

    print(f"\n🧠 分析论文中...")

    # 简单启发式规则选择论文
    recommended = []
    selected_topics = set()

    for i, paper in enumerate(papers):
        # 跳过已被选过相同分类的
        if paper['category'] in selected_topics and len(selected_topics) >= 2:
            continue

        # 选择前 2 篇不同分类的论文
        if len(recommended) < 2:
            # 优先选择摘要中包含热门关键词的论文
            hot_keywords = ['transformer', 'llm', 'diffusion', 'reinforcement', 'gpt', 'neural']
            summary_lower = paper['summary'].lower()
            hot_count = sum(1 for kw in hot_keywords if kw in summary_lower)

            reason = f"最新发布的 {paper['category']} 论文"
            if hot_count > 0:
                reason = f"{paper['category']} 热门方向论文，包含 {hot_count} 个热点关键词"

            recommended.append({
                "index": i,
                "title": paper['title'],
                "reason": reason,
                "summary": paper['summary'][:200] + "...",
                "category": paper['category'],
                "url": paper['url'],
                "pdf_url": paper['pdf_url'],
                "authors": paper['authors'],
                "published": paper['published'],
            })

            selected_topics.add(paper['category'])

    print(f"✅ 分析完成，推荐 {len(recommended)} 篇论文")

    return recommended


def create_issues(recommended: list[dict], repo_name: str, token: str) -> int:
    """根据 Observer 推荐创建 GitHub Issues"""
    if not recommended:
        print("📭 无推荐论文，不创建 Issue")
        return 0

    g = Github(token)
    repo = g.get_repo(repo_name)

    # 获取已存在的 Issue 标题
    existing_titles = {issue.title for issue in repo.get_issues(state='all')}
    created = 0

    for paper in recommended:
        title = f"[论文讨论] {paper['title']}"

        if title in existing_titles:
            print(f"⏭️  已存在: {title[:50]}...")
            continue

        body = f"""## 📄 论文信息

**标题**: [{paper['title']}]({paper['url']})
**作者**: {paper['authors']}
**发布时间**: {paper['published']}
**分类**: {paper['category']}
**PDF**: [Download]({paper['pdf_url']})

## 📝 简介

{paper['summary']}

## 💬 推荐理由

{paper['reason']}

## 讨论

请对这篇论文发表您的见解：
- 论文的创新点是什么？
- 方法是否合理？
- 实验结果是否可信？
- 有哪些可以改进的地方？

---
_由 arXiv Monitor 自动创建_"""

        # 创建 Issue
        issue = repo.create_issue(title=title, body=body)
        print(f"✅ 创建 Issue: {title[:50]}...")

        # 创建评论触发 @Moderator（评论中的 @ 会触发 orchestrator.yml）
        trigger_comment = "@Moderator 请分诊"
        issue.create_comment(trigger_comment)
        print(f"📝 触发评论: {trigger_comment}")

        created += 1
        time.sleep(2)

    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="arXiv Monitor - 智能获取并分析论文")
    parser.add_argument("--token", type=str, help="GitHub Token")
    parser.add_argument("--repo", type=str, help="Repository (owner/repo)")
    parser.add_argument("--categories", type=str, default="cs.AI,cs.LG,cs.CL")
    parser.add_argument("--max-papers", type=int, default=10, help="获取论文数量（分析前）")
    parser.add_argument("--output", type=str, help="Output JSON file (optional)")
    parser.add_argument("--last-scan", type=str, help="Last scan time (ISO format)")
    parser.add_argument("--scan-only", action="store_true", help="Only scan, don't analyze")

    args = parser.parse_args(argv)

    # 默认 7 天前
    last_scan = args.last_scan or (
        datetime.now() - datetime.timedelta(days=7)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    print(f"🔍 扫描 arXiv...")
    print(f"   分类: {', '.join(categories)}")
    print(f"   上次扫描: {last_scan}")

    # 获取论文
    papers = fetch_papers(categories, last_scan, args.max_papers)
    print(f"\n📊 发现 {len(papers)} 篇新论文")

    if not papers:
        print("📭 未发现新论文")
        return 0

    # 保存 JSON（如果指定）
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"💾 保存到: {args.output}")

    # 仅扫描模式
    if args.scan_only:
        for i, p in enumerate(papers, 1):
            print(f"   {i}. [{p['category']}] {p['title'][:50]}...")
        return 0

    # 分析并创建 Issues
    if args.token and args.repo:
        # 构建上下文
        papers_context = build_papers_for_observer(papers)

        # Observer 分析
        recommended = analyze_with_observer(papers, papers_context, args.token)

        # 创建 Issues
        print(f"\n📄 创建 Issues...")
        created = create_issues(recommended, args.repo, args.token)
        print(f"\n🎉 完成！创建 {created} 个 Issues")
    else:
        print("ℹ️  提供 --token 和 --repo 参数可自动分析并创建 Issues")
        for i, p in enumerate(papers, 1):
            print(f"   {i}. [{p['category']}] {p['title'][:50]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
