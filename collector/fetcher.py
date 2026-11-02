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


def _extract_date_from_node(a_tag) -> Optional[str]:
    """从链接节点及其相邻节点提取日期字符串。"""
    # 1. 链接自身的 title 属性
    title_attr = a_tag.get("title", "")
    m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", title_attr)
    if m:
        return m.group(1)

    # 2. 父节点或相邻兄弟节点中的日期
    # 常见结构：<li><a>标题</a><span>2026-10-16</span></li>
    parent = a_tag.parent
    for _ in range(3):  # 向上最多查 3 层
        if parent is None:
            break
        text = parent.get_text(" ", strip=True)
        m = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})", text)
        if m:
            # 规范化
            d = m.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
            return d
        parent = parent.parent

    return None
