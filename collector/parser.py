"""内容解析模块。

从网页 HTML 中提取标题、正文摘要、发布时间等字段。
字段无法可靠提取时返回 None，不编造内容。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def parse_html(
    html: str, base_url: str, source_url: str
) -> dict[str, Optional[str]]:
    """解析单个文章页面，提取标题、摘要、发布时间。

    返回 dict，字段为 title / summary / published_at(ISO 8601 或 None)。
    """
    soup = BeautifulSoup(html, "lxml")

    # 去除脚本和样式
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = _extract_title(soup)
    summary = _extract_summary(soup)
    published = _extract_published(soup)

    result = {
        "title": title,
        "summary": summary,
        "published_at": _to_iso8601(published),
    }
    return result


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """提取标题：优先 og:title，其次 <h1>，再次 <title>。"""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()

    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(" ", strip=True)
        if text:
            return text

    if soup.title and soup.title.string:
        return soup.title.string.strip()

    return None


def _extract_summary(soup: BeautifulSoup) -> Optional[str]:
    """提取摘要：优先 meta description，其次正文开头片段。"""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        text = meta["content"].strip()
        if len(text) > 20:
            return _truncate(text, 200)

    # 正文开头片段（去除导航等后取第一个大段文字）
    for tag in soup.find_all(["p", "article", "div"]):
        text = tag.get_text(" ", strip=True)
        if len(text) >= 40:
            return _truncate(text, 200)

    return None


def _extract_published(soup: BeautifulSoup) -> Optional[datetime]:
    """提取发布时间，返回带时区的 datetime 或 None。"""
    # 常见 meta 标签
    for prop in ["article:published_time", "og:published_time", "publishdate"]:
        meta = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if meta and meta.get("content"):
            dt = _parse_datetime(meta["content"])
            if dt:
                return dt

    # time 标签
    time_tag = soup.find("time")
    if time_tag:
        dt = _parse_datetime(time_tag.get("datetime") or time_tag.get_text())
        if dt:
            return dt

    # 常见日期文本模式，如 "2026-11-01" 或 "2026年11月1日"
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})", text)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                tzinfo=timezone(timedelta(hours=8)),
            )
        except ValueError:
            return None

    return None


def _parse_datetime(s: str) -> Optional[datetime]:
    """解析多种格式的时间字符串。"""
    from datetime import timedelta

    s = (s or "").strip()
    if not s:
        return None
    # 尝试 ISO 8601
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt
    except ValueError:
        pass
    # 尝试常见格式
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).replace(
                tzinfo=timezone(timedelta(hours=8))
            )
        except ValueError:
            continue
    return None


def _to_iso8601(dt: Optional[datetime]) -> Optional[str]:
    """转为 ISO 8601 字符串（含时区）。"""
    if dt is None:
        return None
    return dt.isoformat()


def _truncate(text: str, max_len: int) -> str:
    """截断文本到指定长度。"""
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def resolve_url(base_url: str, link: str) -> str:
    """将相对链接解析为绝对 URL。"""
    return urljoin(base_url, link)
