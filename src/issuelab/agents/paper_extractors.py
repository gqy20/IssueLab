"""Helpers to extract paper lists from Issue bodies for observer agents."""

from __future__ import annotations

import re
from typing import Any


def extract_issue_body(context: str) -> str:
    """Extract the raw Issue body from the execute-context string."""
    if not context:
        return ""

    marker = "**Issue 内容**:\n"
    if marker in context:
        body = context.split(marker, 1)[1]
    else:
        body = context

    comments_marker = "\n\n**本 Issue 共有"
    if comments_marker in body:
        body = body.split(comments_marker, 1)[0]

    return body.strip()


def _parse_markdown_fields(section: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("- **"):
            continue
        match = re.match(r"- \*\*(.+?)\*\*:\s*(.+)$", line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            fields[key] = value
    return fields


def _extract_markdown_link(text: str) -> str:
    match = re.search(r"\((https?://[^)]+)\)", text)
    return match.group(1).strip() if match else ""


def _extract_doi(value: str) -> str:
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"n/a", "na", "none"}:
        return ""

    doi_match = re.search(r"(10\.\d{4,9}/\S+)", value)
    if doi_match:
        return doi_match.group(1).rstrip(".)")

    link = _extract_markdown_link(value)
    if link and "doi.org/" in link:
        return link.split("doi.org/")[-1]

    return value


def parse_pubmed_papers_from_issue(body: str) -> tuple[list[dict[str, Any]], str]:
    """Parse PubMed paper list from Issue body."""
    if not body:
        return [], ""

    query = ""
    query_match = re.search(r"\*\*检索词\*\*:\s*`?(.+?)`?\s*(?:\n|$)", body)
    if query_match:
        query = query_match.group(1).strip()

    pattern = re.compile(
        r"###\s+\d+\.\s+(?P<title>.+?)\n(?P<section>.*?)(?=\n---|\n###\s+\d+\.|\Z)",
        re.S,
    )

    papers: list[dict[str, Any]] = []
    for match in pattern.finditer(body):
        title = match.group("title").strip()
        section = match.group("section")
        fields = _parse_markdown_fields(section)

        pmid_value = fields.get("PMID", "")
        pmid_match = re.search(r"(\d{5,})", pmid_value)
        if not pmid_match:
            continue
        pmid = pmid_match.group(1)

        url = _extract_markdown_link(pmid_value) or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        doi = _extract_doi(fields.get("DOI", ""))
        journal = fields.get("期刊", "")
        pubdate = fields.get("发表日期", "")
        epubdate = fields.get("在线发表", "")
        entrezdate = fields.get("入库日期", "")
        authors = fields.get("作者", "")
        keywords_raw = fields.get("关键词", "")
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()] if keywords_raw else []

        papers.append(
            {
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "pubdate": pubdate,
                "epubdate": epubdate,
                "entrezdate": entrezdate,
                "authors": authors,
                "doi": doi,
                "url": url,
                "keywords": keywords,
            }
        )

    return papers, query


def parse_arxiv_papers_from_issue(body: str) -> list[dict[str, Any]]:
    """Parse a single arXiv paper from Issue body."""
    if not body:
        return []

    title_match = re.search(r"\*\*标题\*\*:\s*\[(.+?)\]\((.+?)\)", body)
    if not title_match:
        return []

    title = title_match.group(1).strip()
    url = title_match.group(2).strip()

    authors_match = re.search(r"\*\*作者\*\*:\s*(.+)", body)
    published_match = re.search(r"\*\*发布时间\*\*:\s*(.+)", body)
    category_match = re.search(r"\*\*分类\*\*:\s*(.+)", body)
    pdf_match = re.search(r"\*\*PDF\*\*:\s*\[.*?\]\((.+?)\)", body)

    summary = ""
    summary_match = re.search(r"## 简介\s+(.+?)(?=\n## |\Z)", body, re.S)
    if summary_match:
        summary = summary_match.group(1).strip()

    paper = {
        "id": url.split("/abs/")[-1],
        "title": title,
        "summary": summary,
        "url": url,
        "pdf_url": pdf_match.group(1).strip() if pdf_match else "",
        "authors": authors_match.group(1).strip() if authors_match else "",
        "published": published_match.group(1).strip() if published_match else "",
        "category": category_match.group(1).strip() if category_match else "",
    }

    return [paper]


def format_pubmed_reanalysis(recommended: list[dict[str, Any]], query: str, total: int) -> str:
    """Format PubMed observer reanalysis response."""
    lines = ["[Agent: pubmed_observer]", "## PubMed 文献再分析"]

    if query:
        lines.append(f"**检索词**: `{query}`")
    lines.append(f"**候选文献**: {total} 篇")
    lines.append(f"**推荐文献**: {len(recommended)} 篇")
    lines.append("")

    if not recommended:
        lines.append("未能从 Issue 中的文献列表生成有效推荐。")
        return "\n".join(lines)

    lines.append("---")
    for i, paper in enumerate(recommended, 1):
        lines.append(f"### {i}. {paper.get('title', '')}")
        pmid = paper.get("pmid", "")
        url = paper.get("url", "")
        if pmid:
            lines.append(f"- **PMID**: [{pmid}]({url})" if url else f"- **PMID**: {pmid}")
        if paper.get("doi"):
            lines.append(f"- **DOI**: {paper.get('doi')}")
        if paper.get("journal"):
            lines.append(f"- **期刊**: {paper.get('journal')}")
        if paper.get("pubdate"):
            lines.append(f"- **发表日期**: {paper.get('pubdate')}")
        if paper.get("epubdate"):
            lines.append(f"- **在线发表**: {paper.get('epubdate')}")
        if paper.get("entrezdate"):
            lines.append(f"- **入库日期**: {paper.get('entrezdate')}")
        if paper.get("authors"):
            lines.append(f"- **作者**: {paper.get('authors')}")
        if paper.get("reason"):
            lines.append(f"- **推荐理由**: {paper.get('reason')}")
        if paper.get("summary"):
            lines.append(f"- **推荐摘要**: {paper.get('summary')}")
        lines.append("")

    return "\n".join(lines)


def format_arxiv_reanalysis(recommended: list[dict[str, Any]], total: int) -> str:
    """Format arXiv observer reanalysis response."""
    lines = ["[Agent: arxiv_observer]", "## arXiv 论文再分析"]
    lines.append(f"**候选论文**: {total} 篇")
    lines.append(f"**推荐论文**: {len(recommended)} 篇")
    lines.append("")

    if not recommended:
        lines.append("未能从 Issue 中的论文信息生成有效推荐。")
        return "\n".join(lines)

    lines.append("---")
    for i, paper in enumerate(recommended, 1):
        lines.append(f"### {i}. {paper.get('title', '')}")
        if paper.get("url"):
            lines.append(f"- **链接**: {paper.get('url')}")
        if paper.get("pdf_url"):
            lines.append(f"- **PDF**: {paper.get('pdf_url')}")
        if paper.get("category"):
            lines.append(f"- **分类**: {paper.get('category')}")
        if paper.get("published"):
            lines.append(f"- **发布时间**: {paper.get('published')}")
        if paper.get("authors"):
            lines.append(f"- **作者**: {paper.get('authors')}")
        if paper.get("reason"):
            lines.append(f"- **推荐理由**: {paper.get('reason')}")
        if paper.get("summary"):
            lines.append(f"- **推荐摘要**: {paper.get('summary')}")
        lines.append("")

    return "\n".join(lines)
