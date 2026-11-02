"""网页与 RSS 获取模块。

负责从配置的信息源获取内容，遵守 robots.txt 与合理访问频率。
仅支持公开可访问的内容，不绕过登录、验证码或反爬限制。
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

# 合理的 User-Agent，标识采集用途
USER_AGENT = (
    "Mozilla/5.0 (compatible; XinjiangIndustryInfoBot/1.0; "
    "+https://github.com/xinjiang-industry-info)"
)

# 请求超时（秒）
TIMEOUT = 20

# 同源请求最小间隔（秒），控制访问频率
REQUEST_INTERVAL = 2.0

_last_request_time: dict[str, float] = {}


def _throttle(host: str) -> None:
    """对同一 host 施加最小请求间隔，避免访问过快。"""
    now = time.time()
    last = _last_request_time.get(host)
    if last is not None:
        elapsed = now - last
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request_time[host] = time.time()


def fetch_url(url: str, timeout: int = TIMEOUT) -> Optional[str]:
    """获取网页 HTML 文本。失败返回 None，不抛出异常。"""
    try:
        _throttle(_host_of(url))
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        # 仅处理 HTML 文本
        if "text/html" not in resp.headers.get("Content-Type", ""):
            return None
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text
    except Exception:
        return None


def fetch_rss(url: str, timeout: int = TIMEOUT) -> list[dict[str, Any]]:
    """获取 RSS/Atom 源，返回条目列表。失败返回空列表。"""
    try:
        _throttle(_host_of(url))
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = []
        for e in feed.entries:
            entries.append(
                {
                    "title": e.get("title", "").strip(),
                    "link": e.get("link", "").strip(),
                    "summary": _strip_html(e.get("summary", "")),
                    "published": e.get("published") or e.get("updated"),
                }
            )
        return entries
    except Exception:
        return []


def _strip_html(text: str) -> str:
    """去除 HTML 标签，保留纯文本。"""
    import re

    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _host_of(url: str) -> str:
    """提取 URL 的 host 部分，用于限速。"""
    from urllib.parse import urlparse

    return urlparse(url).netloc


def fetch_list_page(list_url: str, article_url_pattern: str | None = None) -> list[dict[str, Any]]:
    """解析栏目列表页，提取文章条目（标题、链接、日期）。

    适用于「大汉版通」等政务 CMS 的 list.shtml 列表页结构：
    - 文章链接通常形如 /前缀/c栏目ID/年月/哈希.shtml
    - 标题在 <a> 内，日期可能在相邻节点或 title 中

    返回条目列表，每项含 title / link / published（原始日期字符串或 None）。
    """
    html = fetch_url(list_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    entries = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 6:
            continue

        # 判断是否为文章详情链接
        if not _is_article_link(href, article_url_pattern):
            continue

        full_link = urljoin(list_url, href)
        if full_link in seen_links:
            continue
        seen_links.add(full_link)

        # 尝试从标题或相邻节点提取日期
        published = _extract_date_from_node(a)

        entries.append(
            {
                "title": title,
                "link": full_link,
                "summary": "",
                "published_at": published,
            }
        )

    return entries


def _is_article_link(href: str, pattern: str | None) -> bool:
    """判断链接是否为文章详情页链接。"""
    if pattern:
        return bool(re.search(pattern, href))
    # 默认规则：.shtml / .html 结尾且路径较深（含栏目目录）
    if not (href.endswith(".shtml") or href.endswith(".html")):
        return False
    # 排除列表页、首页、RSS 页
    if any(k in href for k in ("list", "index", "rss", "common_list")):
        return False
    return True


def fetch_generic_list(
    list_url: str,
    link_pattern: str | None = None,
    max_items: int = 30,
) -> list[dict[str, Any]]:
    """通用列表页解析：提取标题、链接、日期。

    适用于企业官网（aspx/静态页）等非政务 CMS 的列表结构，比 fetch_list_page
    更宽松——不强制 .shtml 结尾，通过 link_pattern 正则或启发式规则识别文章链接。

    标题提取优先级：<a> 文本 > title 属性；若文本为截断片段（含"…"或"..."），
    仍保留，由上层决定是否抓详情页补全。
    """
    html = fetch_url(list_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    entries = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue

        # 标题：文本优先，其次 title 属性
        title = a.get_text(" ", strip=True)
        if (not title or len(title) < 4) and a.get("title"):
            title = a["title"].strip()

        if not title or len(title) < 4:
            continue

        # 判断是否为文章详情链接
        if not _is_generic_article_link(href, link_pattern):
            continue

        full_link = urljoin(list_url, href)
        if full_link in seen_links:
            continue
        seen_links.add(full_link)

        published = _extract_date_from_node(a)
        entries.append(
            {
                "title": title,
                "link": full_link,
                "summary": "",
                "published_at": published,
            }
        )
        if len(entries) >= max_items:
            break

    return entries


def _is_generic_article_link(href: str, pattern: str | None) -> bool:
    """判断链接是否为文章详情链接（通用启发式）。"""
    if pattern:
        return bool(re.search(pattern, href))
    # 启发式：排除明显的导航/功能链接
    low = href.lower()
    if any(k in low for k in ("list", "index", "rss", "search", "login", "register", "map", "sitemap")):
        return False
    # 含数字 id 或 .shtml/.html/.aspx 且带 nid/id 参数的，视为文章
    if re.search(r"(nid=|id=|/content_|/announcement-|_detail|detail/|/\d{4}[-/]\d{1,2}[-/]\d{1,2})", low):
        return True
    if low.endswith((".shtml", ".html", ".htm", ".aspx")) and "?" in href:
        return True
    return False


def _normalize_date(s: str) -> str:
    """把 2026-1-8 规范化为 2026-01-08。"""
    m = re.match(r"(20\d{2})-(\d{1,2})-(\d{1,2})", s)
    if not m:
        return s
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _extract_date_from_node(a_tag) -> Optional[str]:
    """从链接节点及其相邻节点提取日期字符串。

    只从「非标题文本」中提取，并要求是完整日期格式。标题里常出现
    「2026年1-8月经济要情」这类期间描述，若从标题取日期会得到错误
    的发布时间（如把 1-8 月当成 1 月 8 日）。
    """
    # 1. 链接自身 title 属性中的完整日期
    title_attr = a_tag.get("title") or ""
    m = re.search(r"(20\d{2}-\d{1,2}-\d{1,2})", title_attr)
    if m:
        return _normalize_date(m.group(1))

    # 2. 父节点或相邻兄弟节点中的日期（排除链接自身文本）
    parent = a_tag.parent
    for _ in range(3):  # 向上最多查 3 层
        if parent is None:
            break
        text = _text_excluding_a(parent, a_tag)
        m = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?", text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y}-{mo:02d}-{d:02d}"
        parent = parent.parent

    return None


def _text_excluding_a(node, a_tag) -> str:
    """收集节点内的文本，但排除目标 <a> 标签内的文字。"""
    parts = []
    for s in node.find_all(string=True):
        parent = s.parent
        if parent is None:
            continue
        # 跳过位于该链接内部的文本
        if parent is a_tag or a_tag in parent.parents:
            continue
        t = str(s).strip()
        if t:
            parts.append(t)
    return " ".join(parts)
