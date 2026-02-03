#!/usr/bin/env python3
"""
arXiv Monitor - 获取新论文并创建 GitHub Issues

Usage:
    # 带 Token：获取论文并创建 Issue
    python scripts/monitor_arxiv.py \
        --token "ghp_xxx" \
        --repo "owner/repo" \
        --categories "cs.AI,cs.LG,cs.CL" \
        --max-papers 5

    # 不带 Token：仅获取论文列表到 JSON
    python scripts/monitor_arxiv.py \
        --output /tmp/papers.json \
        --categories "cs.AI"
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
    return text[:max_length].rsplit(".", 1)[0] +..."


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


def create_issues(papers: list[dict], repo_name: str, token: str) -> int:
    """创建 GitHub Issues"""
    if not papers:
        return 0

    g = Github(token)
    repo = g.get_repo(repo_name)

    existing_titles = {issue.title for issue in repo.get_issues(state='all')}
    created = 0

    for paper in papers:
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

## 📝 摘要

{paper['summary']}

## 💬 讨论

请对这篇论文发表您的见解：
- 论文的创新点是什么？
- 方法是否合理？
- 实验结果是否可信？
- 有哪些可以改进的地方？

@Moderator 请分诊

---
_由 arXiv Monitor 自动创建_"""

        repo.create_issue(title=title, body=body)
        created += 1
        print(f"✅ 创建: {title[:50]}...")
        time.sleep(2)

    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="arXiv Monitor - 获取论文并创建 Issue")
    parser.add_argument("--token", type=str, help="GitHub Token")
    parser.add_argument("--repo", type=str, help="Repository (owner/repo)")
    parser.add_argument("--categories", type=str, default="cs.AI,cs.LG,cs.CL")
    parser.add_argument("--max-papers", type=int, default=5)
    parser.add_argument("--output", type=str, help="Output JSON file (optional)")
    parser.add_argument("--last-scan", type=str, help="Last scan time (ISO format)")

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

    # 保存 JSON（如果指定）
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"💾 保存到: {args.output}")

    # 创建 Issues（如果提供 Token）
    if args.token and args.repo:
        print(f"\n📄 创建 Issues...")
        created = create_issues(papers, args.repo, args.token)
        print(f"\n🎉 完成！创建 {created} 个 Issues")
    else:
        for i, p in enumerate(papers, 1):
            print(f"   {i}. [{p['category']}] {p['title'][:50]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
