"""数据标准化模块。

将采集到的原始数据标准化为统一的数据结构。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import dedup


def normalize_article(
    raw: dict[str, Any],
    source_name: str,
    source_type: str,
    collected_at: Optional[str] = None,
) -> dict[str, Any]:
    """将原始采集数据标准化为统一文章结构。

    raw 字段：title, link(source_url), summary, published_at
    """
    source_url = raw.get("link") or raw.get("source_url") or ""
    title = (raw.get("title") or "").strip()
    summary = (raw.get("summary") or "").strip()

    published_at = _normalize_time(raw.get("published_at"))
    if collected_at is None:
        collected_at = _now_iso()

    article = {
        "id": dedup.url_hash(source_url) if source_url else _fallback_id(title),
        "title": title,
        "summary": summary,
        "summary_source": "truncated" if summary else None,
        "source_type": source_type,
        "source_name": source_name,
        "source_url": source_url,
        "published_at": published_at,
        "collected_at": collected_at,
        "region_group": "pending",
        "region": None,
        "industry_tags": [],
        "content_type": "news",
        "status": "pending",
        "is_test": False,
    }
    return article


def _normalize_time(value: Any) -> Optional[str]:
    """将时间标准化为 ISO 8601（含时区）。无法解析返回 None。"""
    if not value:
        return None
    if isinstance(value, str):
        return value if _looks_iso(value) else None
    # feedparser 返回 struct_time 或 datetime
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    try:
        # struct_time
        import time

        dt = datetime.fromtimestamp(time.mktime(value), tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _looks_iso(s: str) -> bool:
    import re

    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T", s)) or bool(
        re.match(r"^\d{4}-\d{2}-\d{2}", s)
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _fallback_id(title: str) -> str:
    import hashlib

    return "n" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:24]
