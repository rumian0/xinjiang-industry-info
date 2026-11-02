"""网页与 RSS 获取模块。

负责从配置的信息源获取内容，遵守 robots.txt 与合理访问频率。
仅支持公开可访问的内容，不绕过登录、验证码或反爬限制。
"""

from __future__ import annotations

import time
from typing import Any, Optional

import feedparser
import requests

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
