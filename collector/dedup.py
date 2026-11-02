"""去重模块。

对采集到的信息进行去重：
1. 原文 URL 规范化后去重。
2. 标题相似度辅助判断（不直接删除，仅标记重复）。
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


def normalize_url(url: str) -> str:
    """URL 规范化：去 fragment、排序 query、去默认端口、统一小写 host。"""
    try:
        p = urlparse(url.strip())
        scheme = p.scheme.lower()
        host = p.netloc.lower()
        # 去除默认端口
        if host.endswith(":80") and scheme == "http":
            host = host[:-3]
        elif host.endswith(":443") and scheme == "https":
            host = host[:-4]
        # 排序 query 参数
        query = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
        return urlunparse((scheme, host, p.path.rstrip("/") or "/", "", query, ""))
    except Exception:
        return url.strip()


def url_hash(url: str) -> str:
    """生成 URL 的稳定哈希，作为文章 id。"""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:32]


def title_similarity(a: str, b: str) -> float:
    """计算两个标题的相似度（0~1）。"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _clean_title(a), _clean_title(b)).ratio()


def _clean_title(title: str) -> str:
    """清理标题，去除常见噪音词，便于相似度比较。"""
    t = re.sub(r"[\s\-—|·【】\[\]（）()]", "", title or "")
    # 去除常见转载标记
    t = re.sub(r"(原标题|来源[:：].*?)$", "", t)
    return t.lower()


def find_duplicate(new_url: str, new_title: str, existing: list[dict]) -> str | None:
    """在已有文章中查找重复。

    返回重复文章的 id；若无重复返回 None。
    规则：URL 相同直接判重；标题相似度 > 0.9 标记为疑似重复。
    """
    norm_url = normalize_url(new_url)
    for art in existing:
        if normalize_url(art.get("source_url", "")) == norm_url:
            return art.get("id")
        # 标题相似度辅助判断（仅标记，不删除）
        sim = title_similarity(new_title, art.get("title", ""))
        if sim > 0.9:
            return art.get("id")
    return None
