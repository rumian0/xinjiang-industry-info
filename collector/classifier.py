"""信息分类模块。

根据标题/摘要/配置，对信息进行来源类型、产业主题、地区分类。
分类不确定时返回 None 或待确认标记，不猜测。
"""

from __future__ import annotations

import json
import os
from typing import Optional

# 配置目录
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


def _load_json(name: str) -> dict:
    path = os.path.join(_CONFIG_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# 产业主题关键词映射（用于规则分类，可后续扩展为 AI 分类）
_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "development_zone": ["开发区", "产业园区", "经济技术开发区", "高新区", "园区"],
    "enterprise": ["企业", "公司", "集团", "上市", "投资建厂", "设厂"],
    "mineral": ["矿产", "矿山", "矿石", "矿藏", "勘探", "煤炭", "铁矿", "铜矿", "锂矿", "油气", "石油", "天然气", "油气田"],
    "energy": ["新能源", "光伏", "风电", "风电", "储能", "氢能", "太阳能", "发电"],
    "transport_logistics": ["交通", "物流", "铁路", "公路", "口岸", "外贸", "出口", "进口", "贸易"],
    "agriculture": ["农业", "农产品", "棉花", "特色产业", "林果", "畜牧", "种植"],
}


def classify_industry(text: str) -> list[str]:
    """根据文本内容返回匹配的产业主题标签列表。"""
    matched = []
    for code, kws in _INDUSTRY_KEYWORDS.items():
        if any(kw in text for kw in kws):
            matched.append(code)
    return matched


def is_industry_related(text: str) -> bool:
    """判断文本是否与产业相关（命中任一产业关键词）。

    用于过滤掉时政、领导人活动等非产业内容。
    """
    return len(classify_industry(text)) > 0


def classify_source_type(source_type: str) -> Optional[str]:
    """校验来源类型是否合法，返回 code 或 None。"""
    cfg = _load_json("source_types.json")
    valid = {s["code"] for s in cfg["source_types"]}
    return source_type if source_type in valid else None


def classify_region(region_code: str | None) -> Optional[str]:
    """校验地区 code 是否合法。"""
    if not region_code:
        return None
    cfg = _load_json("regions.json")
    valid = {r["code"] for r in cfg["regions"]}
    return region_code if region_code in valid else None


def resolve_region_group(region_code: str | None) -> str:
    """根据地区 code 解析所属分组（南疆/北疆/全疆/待确认）。"""
    if not region_code:
        return "pending"
    cfg = _load_json("regions.json")
    for r in cfg["regions"]:
        if r["code"] == region_code:
            return r["group"]
    return "pending"


def guess_region_from_text(text: str) -> Optional[str]:
    """根据文本内容匹配地区名，返回地区 code 或 None。"""
    cfg = _load_json("regions.json")
    for r in cfg["regions"]:
        # 用地区名去掉常见后缀做匹配
        name = r["name"]
        short = name.replace("市", "").replace("地区", "").replace("自治州", "").replace("自治县", "")
        if name in text or (len(short) >= 2 and short in text):
            return r["code"]
    return None
