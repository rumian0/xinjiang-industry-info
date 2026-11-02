"""信息采集入口。

流程：
读取启用的信息源 → 抓取（RSS 优先 / 网页）→ 解析 → 标准化 →
分类（来源类型/产业主题/地区）→ 去重 → 质量校验 → 写回 data/articles.json。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

# 确保可独立运行（相对导入）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetcher import fetch_rss, fetch_url, fetch_list_page, fetch_generic_list  # noqa: E402
from parser import parse_html, resolve_url  # noqa: E402
from normalize import normalize_article  # noqa: E402
from classifier import (  # noqa: E402
    classify_industry,
    classify_region,
    classify_source_type,
    guess_region_from_text,
    resolve_region_group,
    is_industry_related,
)
from dedup import find_duplicate  # noqa: E402
from validator import validate_articles  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
ARTICLES_FILE = os.path.join(DATA_DIR, "articles.json")


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_existing() -> list[dict]:
    """读取已有文章数据。"""
    if os.path.exists(ARTICLES_FILE):
        data = load_json(ARTICLES_FILE)
        return data.get("articles", [])
    return []


def save_articles(articles: list[dict]) -> None:
    """写回 articles.json。"""
    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "count": len(articles),
        "articles": articles,
    }
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _fetch_detail(url: str) -> dict | None:
    """抓取文章详情页，提取标题、摘要、发布时间。

    返回 dict（title/summary/published_at），失败返回 None。
    仅用于列表页标题被截断、需要补全的情况。
    """
    try:
        html = fetch_url(url)
        if not html:
            return None
        parsed = parse_html(html, url, url)
        return {
            "title": parsed.get("title"),
            "summary": parsed.get("summary"),
            "published_at": parsed.get("published_at"),
        }
    except Exception:
        return None


def collect_from_source(
    source: dict, existing_urls: frozenset[str] = frozenset()
) -> list[dict]:
    """从单个信息源采集，返回标准化后的文章列表。

    支持三种采集方式（按优先级）：
    1. rss：标准 RSS/Atom 源
    2. list：政务 CMS 栏目列表页（list.shtml）
    3. generic：企业官网等通用列表页
    4. homepage：网页首页兜底（通用链接提取）

    existing_urls 为已收录文章的 URL 集合。已收录的条目不再抓详情页，
    既节省请求，也避免重复覆盖已有数据。
    """
    name = source["name"]
    base_url = source["url"]
    source_type = source["type"]
    method = source.get("method", "list")

    raw_items = []

    if method == "rss":
        rss = source.get("rss")
        if rss:
            entries = fetch_rss(rss)
            for e in entries:
                raw_items.append(
                    {
                        "title": e.get("title", ""),
                        "link": e.get("link", ""),
                        "summary": e.get("summary", ""),
                        "published_at": e.get("published"),
                    }
                )
        if not raw_items:
            # RSS 失败则退回列表页解析
            raw_items = fetch_list_page(base_url, source.get("article_pattern"))

    elif method == "list":
        list_url = source.get("list_url") or base_url
        raw_items = fetch_list_page(list_url, source.get("article_pattern"))

    elif method == "generic":
        # 通用列表页（企业官网等非政务 CMS 结构）
        list_url = source.get("list_url") or base_url
        raw_items = fetch_generic_list(
            list_url, source.get("article_pattern"), source.get("max_items", 30)
        )

    else:  # homepage 兜底
        html = fetch_url(base_url)
        if html:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                text = a.get_text(" ", strip=True)
                if len(text) >= 10:
                    raw_items.append(
                        {
                            "title": text,
                            "link": resolve_url(base_url, a["href"]),
                            "summary": "",
                            "published_at": None,
                        }
                    )
            raw_items = raw_items[:50]

    # 标准化 + 分类
    articles = []
    # 若信息源本身是产业专题栏目，则不过滤（force_keep_industry）
    force_keep = source.get("force_keep_industry", False)
    # 是否抓取详情页补全摘要（列表页只有标题和日期，摘要需进详情页）
    fetch_detail = source.get("fetch_detail", False)
    # 单源单次最多抓取详情页的条数，防止请求量失控
    max_detail = int(source.get("max_detail", 40))
    detail_done = 0

    for item in raw_items:
        # 详情页：仅补齐未收录文章，已收录的不重复抓取
        link = item.get("link") or ""
        need_detail = (
            fetch_detail
            and link
            and link not in existing_urls
            and detail_done < max_detail
        )
        if need_detail:
            detail_done += 1
            detail = _fetch_detail(link)
            if detail:
                if detail.get("title"):
                    item["title"] = detail["title"]
                if detail.get("summary"):
                    item["summary"] = detail["summary"]
                if detail.get("published_at"):
                    item["published_at"] = detail["published_at"]

        art = normalize_article(item, name, source_type)
        # 分类
        full_text = f"{art['title']} {art['summary']}"
        # 仅保留与产业相关的内容（过滤时政新闻、领导人活动等）
        # 但产业专题栏目（如发改委"产业发展"）可强制保留
        if not force_keep and not is_industry_related(full_text):
            continue
        art["industry_tags"] = classify_industry(full_text)
        region_code = guess_region_from_text(full_text)
        # 文本未匹配到地区时，回退到信息源配置的默认地区
        if not region_code:
            region_code = source.get("region")
        art["region"] = classify_region(region_code)
        # 若来源为"全疆"（自治区级机构，无具体地区），直接标记为全疆
        if region_code == "quanjang":
            art["region_group"] = "quanjang"
        else:
            art["region_group"] = resolve_region_group(art["region"])
        articles.append(art)

    return articles


def _needs_summary(art: dict) -> bool:
    """判断该条是否需要（重新）抓取摘要。

    包括两种情况：摘要为空；摘要是早期版本抓到的「标题+元信息」噪声。
    """
    s = (art.get("summary") or "").strip()
    if not s:
        return True
    head = s[:100]
    # 早期解析器会把元信息当摘要
    if any(k in head for k in ("浏览次数", "浏览量", "【字体", "大 中 小", "文章来源", "打印本文")):
        return True
    # 摘要开头重复标题
    title = (art.get("title") or "").strip()
    if title and s[:25] == title[:25]:
        return True
    return False


def backfill_summaries(articles: list[dict], limit: int = 60) -> int:
    """为摘要缺失或被噪声污染的已收录文章重新抓取摘要。

    历史数据是在未开启详情抓取时采集的，摘要为空；早期解析器还会把
    「标题+元信息」当摘要。每次运行限量处理一部分，多轮即可补齐，
    避免单次任务耗时过长。返回本次成功回填的条数。
    """
    todo = [
        a for a in articles
        if _needs_summary(a) and a.get("source_url")
    ]
    if not todo:
        return 0

    updated = 0
    for art in todo[:limit]:
        detail = _fetch_detail(art["source_url"])
        summary = (detail or {}).get("summary")
        if summary:
            art["summary"] = summary
            art["summary_source"] = "truncated"
            updated += 1
    print(f"[回填] 待补摘要 {len(todo)} 条，本次处理 {min(limit, len(todo))} 条，成功 {updated} 条")
    return updated


def main() -> int:
    """主流程，返回退出码（0 成功）。"""
    print(f"[采集] 开始，时间：{datetime.now(timezone.utc).astimezone().isoformat()}")

    sources_cfg = load_json(os.path.join(CONFIG_DIR, "sources.json"))
    sources = [s for s in sources_cfg["sources"] if s.get("enabled", True)]

    print(f"[采集] 启用的信息源数量：{len(sources)}")

    existing = load_existing()
    print(f"[采集] 已有文章数量：{len(existing)}")
    # 已收录 URL，用于跳过重复的详情页请求
    existing_urls = frozenset(
        a["source_url"] for a in existing if a.get("source_url")
    )

    new_articles = []
    success_count = 0
    fail_count = 0

    for src in sources:
        print(f"[采集] 处理信息源：{src['name']} ({src['url']})")
        try:
            collected = collect_from_source(src, existing_urls)
            if collected:
                success_count += 1
                new_articles.extend(collected)
                print(f"[采集]   - 获取 {len(collected)} 条候选信息")
            else:
                fail_count += 1
                print(f"[采集]   - 未获取到信息（可能无 RSS 或网页无法访问）")
        except Exception as e:
            fail_count += 1
            print(f"[采集]   - 采集异常：{e}")

    # 去重
    print(f"[去重] 候选信息 {len(new_articles)} 条，开始去重")
    merged = list(existing)
    added = 0
    skipped_dup = 0
    for art in new_articles:
        dup_id = find_duplicate(art["source_url"], art["title"], merged)
        if dup_id:
            skipped_dup += 1
            continue
        merged.append(art)
        added += 1

    # 质量校验
    valid, invalid = validate_articles(merged)
    if invalid:
        print(f"[校验] 发现 {len(invalid)} 条无效数据，已剔除")

    print(f"[结果] 新增 {added} 条，重复跳过 {skipped_dup} 条，有效总数 {len(valid)} 条")

    # 回填历史数据缺失的摘要
    backfilled = backfill_summaries(valid)

    # 仅在数据有变化时写回
    if added > 0 or invalid or backfilled > 0:
        save_articles(valid)
        print(f"[写入] 已更新 {ARTICLES_FILE}")
    else:
        print("[写入] 无新增数据，保持原有数据不变")

    print(f"[采集] 完成。成功源 {success_count}，失败源 {fail_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
