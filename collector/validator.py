"""数据质量检查模块。

对标准化后的文章进行基础质量校验，过滤明显无效的数据。
校验不通过的信息不进入正式数据，而是被标记或丢弃。
"""

from __future__ import annotations

from typing import Any


def validate_article(article: dict[str, Any]) -> tuple[bool, list[str]]:
    """校验单条文章数据质量。

    返回 (是否通过, 问题列表)。
    """
    problems: list[str] = []

    # 必填字段
    if not article.get("title"):
        problems.append("缺少标题")
    if not article.get("source_url"):
        problems.append("缺少原文链接")
    if not article.get("source_name"):
        problems.append("缺少来源名称")
    if not article.get("source_type"):
        problems.append("缺少来源类型")

    # 标题长度合理性
    title = article.get("title", "")
    if title and len(title) > 300:
        problems.append("标题过长")

    # 链接格式
    url = article.get("source_url", "")
    if url and not (url.startswith("http://") or url.startswith("https://")):
        problems.append("链接格式非法")

    # 时间格式
    published = article.get("published_at")
    if published is not None and not isinstance(published, str):
        problems.append("发布时间格式错误")

    return (len(problems) == 0), problems


def validate_articles(articles: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """批量校验，返回 (有效列表, 无效列表)。"""
    valid = []
    invalid = []
    for a in articles:
        ok, problems = validate_article(a)
        if ok:
            valid.append(a)
        else:
            invalid.append({"article": a, "problems": problems})
    return valid, invalid
