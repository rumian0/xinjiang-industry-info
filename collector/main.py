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

from fetcher import fetch_rss, fetch_url  # noqa: E402
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


def collect_from_source(source: dict) -> list[dict]:
    """从单个信息源采集，返回标准化后的文章列表。"""
    name = source["name"]
    base_url = source["url"]
    source_type = source["type"]
    rss = source.get("rss")

    raw_items = []

    # RSS 优先
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

    # 若 RSS 无结果，尝试网页抓取（此处仅演示首页标题列表提取，具体站点的列表解析需按站点定制）
    if not raw_items:
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
            # 限制数量，避免首页导航链接噪音
            raw_items = raw_items[:50]

    # 标准化 + 分类
    articles = []
    for item in raw_items:
        art = normalize_article(item, name, source_type)
        # 分类
        full_text = f"{art['title']} {art['summary']}"
        # 仅保留与产业相关的内容（过滤时政新闻、领导人活动等）
        if not is_industry_related(full_text):
            continue
        art["industry_tags"] = classify_industry(full_text)
        region_code = guess_region_from_text(full_text)
        art["region"] = classify_region(region_code)
        art["region_group"] = resolve_region_group(art["region"])
        articles.append(art)

    return articles


def main() -> int:
    """主流程，返回退出码（0 成功）。"""
    print(f"[采集] 开始，时间：{datetime.now(timezone.utc).astimezone().isoformat()}")

    sources_cfg = load_json(os.path.join(CONFIG_DIR, "sources.json"))
    sources = [s for s in sources_cfg["sources"] if s.get("enabled", True)]

    print(f"[采集] 启用的信息源数量：{len(sources)}")

    existing = load_existing()
    print(f"[采集] 已有文章数量：{len(existing)}")

    new_articles = []
    success_count = 0
    fail_count = 0

    for src in sources:
        print(f"[采集] 处理信息源：{src['name']} ({src['url']})")
        try:
            collected = collect_from_source(src)
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

    # 仅在有变化时写回
    if added > 0 or invalid:
        save_articles(valid)
        print(f"[写入] 已更新 {ARTICLES_FILE}")
    else:
        print("[写入] 无新增数据，保持原有数据不变")

    print(f"[采集] 完成。成功源 {success_count}，失败源 {fail_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
