"""内容解析模块。

从网页 HTML 中提取标题、正文摘要、发布时间等字段。
字段无法可靠提取时返回 None，不编造内容。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
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
    summary = _extract_summary(soup, title or "")
    published = _extract_published(soup)

    result = {
        "title": title,
        "summary": summary,
        "published_at": _to_iso8601(published),
    }
    return result


# --- 正文提取辅助 ---------------------------------------------------------

# 正文容器候选（id / class 关键词）。政务 CMS 常见 TRS_Editor / zoom 等。
CONTENT_HINTS = (
    "trs_editor", "article-content", "article_content", "articlecon",
    "content_box", "contentbox", "detail-content", "detail_content",
    "view-content", "view_content", "main-content", "main_content",
    "art-con", "artcon", "zoom", "content",
)

# 需要排除的容器（导航、页眉页脚、侧栏等）
EXCLUDE_HINTS = (
    "nav", "menu", "header", "footer", "aside", "breadcrumb", "crumb",
    "sidebar", "share", "comment", "related", "friendlink", "friend-link",
    "search", "toolbar", "position", "copyright", "banner",
)

# 元信息/功能按钮类噪声行的前缀
NOISE_PREFIX = (
    "当前位置", "您现在的位置", "您的位置", "文章来源", "来源：", "来源:",
    "发布时间", "发布日期", "发布机构", "浏览", "点击", "字体", "打印",
    "关闭", "分享", "扫一扫", "上一篇", "下一篇", "责任编辑", "附件",
    "相关链接", "网站地图", "主办单位", "技术支持", "ICP备",
)

# 导航栏特征词：出现即判定该段不是正文
NAV_TOKENS = (
    "首页", "政务公开", "政务服务", "政民互动", "智能问答", "无障碍",
    "热门搜索", "政务微信", "政务微博", "RSS订阅", "登录", "注册",
    "要闻动态", "政府信息公开", "互动交流", "政策文件", "业务系统",
)

# 页脚/友链特征词
LINK_FARM_TOKENS = (
    "友情链接", "各政府网站", "政府网站", "网站群", "相关链接",
    "主办单位", "承办单位", "网站标识码", "版权所有",
)

# 元信息关键词（短段落中命中多个即视为信息行，非正文）
META_TOKENS = (
    "日期：", "日期:", "作者：", "作者:", "浏览次数", "点击", "来源：",
    "来源:", "字体", "分享", "打印", "关闭", "【", "次]", "阅读",
)

# 中文句读：正文段落应包含
SENTENCE_PUNCT = "。！？；，、"


def _classify_container(tag) -> int:
    """判断容器是正文(1)/噪声(-1)/未知(0)。"""
    ident = " ".join(
        filter(None, [tag.get("id") or "", " ".join(tag.get("class") or [])])
    ).lower()
    if not ident:
        return 0
    if any(k in ident for k in EXCLUDE_HINTS):
        return -1
    if any(k in ident for k in CONTENT_HINTS):
        return 1
    return 0


def _is_noise_line(text: str) -> bool:
    """判断一段文字是否为导航/元信息/友链等噪声。"""
    t = text.strip()
    if not t:
        return True
    if len(t) < 8:
        return True

    for p in NOISE_PREFIX:
        if t.startswith(p):
            return True

    # 页脚、友情链接、站点群列表
    if any(k in t for k in LINK_FARM_TOKENS):
        return True

    # 短段落中命中多个元信息关键词 → 是「日期/作者/来源/字体」信息行
    if len(t) <= 120 and sum(1 for k in META_TOKENS if k in t) >= 2:
        return True

    # 空格分隔的碎片列表：词多且平均词短（典型友链/导航行）
    words = t.split()
    if len(words) >= 8:
        avg = sum(len(w) for w in words) / len(words)
        if avg < 6:
            return True

    # 导航特征词命中 2 个以上
    if sum(1 for tok in NAV_TOKENS if tok in t) >= 2:
        return True

    return False


def _is_content_line(text: str) -> bool:
    """判断是否为像样的正文段落：有句读、长度足够。"""
    t = text.strip()
    if len(t) < 30:
        return False
    punct = sum(1 for ch in t if ch in SENTENCE_PUNCT)
    return punct >= 2


def _strip_leading_title(text: str, title: str) -> str:
    """若段落以标题开头（允许空白/标点差异），去掉该标题部分。"""
    cn = re.sub(r"\s+", "", title or "")
    if len(cn) < 8:
        return text

    # 找出原文第 len(cn) 个非空白字符的位置
    positions = [i for i, ch in enumerate(text) if not ch.isspace()]
    if len(positions) < len(cn):
        return text
    end = positions[len(cn) - 1] + 1
    cand = re.sub(r"\s+", "", text[:end])

    # 取前 10 字比较，容忍引号/顿号等细微差异
    if cand[:10] == cn[:10]:
        return text[end:].strip()
    return text


def _strip_meta_prefix(text: str, title: str = "") -> str:
    """去掉段落开头的标题重复与元信息（发布日期/来源/浏览次数/字体等）。

    政务站正文常与标题、元信息挤在同一段，例如：
    「某标题 文章来源：某报 发布时间：2026-06-26 17:23 浏览次数：
      【字体: 大 中 小 】 打印本文 正文开始…」
    需要剥离这些前缀，只留正文。
    """
    t = (text or "").strip()
    if not t:
        return t

    # 1. 去掉重复的标题前缀
    if title:
        t = _strip_leading_title(t, title)

    # 2. 定位到最后一个「字体/打印/关闭」标记之后，那里才是正文
    markers = list(
        re.finditer(
            r"(?:【\s*大\s*中\s*小\s*】|【\s*字\s*体[^】]*】|【\s*打\s*印\s*】|"
            r"【\s*关\s*闭\s*】|打印本文|关闭窗口)",
            t,
        )
    )
    if markers:
        after = t[markers[-1].end():].strip()
        if len(after) >= 20:
            t = after

    # 去掉开头的纯日期/时间（如「2026-10-30 16:37 来源：…」）
    t = re.sub(r"^20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}日?\s*\d{0,2}[:：]?\d{0,2}\s*", "", t)

    # 3. 「词：值」形式的连续元信息前缀
    prefix = re.compile(
        r"^(?:(?:发布\s*日期|发布日期|发布时间|日期|文章来源|来源|作者|浏览\s*次数|浏览次数|"
        r"点击\s*次数|访问量|浏览量|字号|字体|阅读|打印|分享)\s*[:：]?\s*[^\s。，；]{0,24}\s*)+"
    )
    m2 = prefix.match(t)
    if m2 and m2.end() > 0:
        t = t[m2.end():].strip()

    # 清掉残留的引导标点/孤立括号
    t = re.sub(r"^[：:，,、\-—\s】\]]+", "", t)
    return t


def _extract_paragraphs(root, title: str = "") -> list[str]:
    """从容器中提取有效正文段落（已剥离开头标题与元信息）。"""
    out = []
    for p in root.find_all(["p", "div", "span", "td"]):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        text = _strip_meta_prefix(text, title)
        if not text or _is_noise_line(text):
            continue
        # 单个容器文字过长时应取其直接文本，避免重复父级内容
        if len(out) and any(text in o for o in out):
            continue
        out.append(text)
    return out


def _clean_title(raw: str) -> str:
    """清洗标题：去掉「栏目_站点」类后缀。"""
    t = (raw or "").strip()
    if not t:
        return t
    # 形如「标题_产业发展_新疆维吾尔自治区发展和改革委员会」
    parts = re.split(r"[_|]", t)
    if len(parts) >= 2:
        head = parts[0].strip()
        # 仅当首段足够长、且后续段像栏目/站点名时才截断
        if len(head) >= 8:
            t = head
    # 形如「标题 - 新疆维吾尔自治区人民政府」
    m = re.match(r"^(.{10,}?)\s*[-–—]\s*(新疆|自治区|乌鲁木齐|伊犁|喀什|巴音郭楞|吐鲁番).{0,30}$", t)
    if m:
        t = m.group(1).strip()
    return t


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """提取标题：优先 og:title，其次 <h1>，再次 <title>。"""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        t = _clean_title(og["content"])
        if t:
            return t

    h1 = soup.find("h1")
    if h1:
        t = _clean_title(h1.get_text(" ", strip=True))
        if t:
            return t

    if soup.title and soup.title.string:
        return _clean_title(soup.title.string) or None

    return None


def _finalize_summary(text: str, title: str = "") -> Optional[str]:
    """摘要最终清洗与校验：要么得到干净正文，要么返回 None。"""
    s = _strip_meta_prefix(text, title).strip()
    if not s:
        return None

    # 仍残留元信息标记时，从最后一个标记之后重新取正文
    leftovers = ("浏览次数", "浏览量", "文章来源", "字体：", "字体:", "【")
    if any(k in s[:80] for k in leftovers) or "】" in s[:80]:
        repaired = ""
        for m in reversed(
            list(re.finditer(r"(?:】|浏览次数[:：]?|浏览量[:：]?|文章来源[:：]?)", s))
        ):
            tail = s[m.end():].strip()
            if len(tail) >= 30:
                repaired = tail
                break
        if repaired:
            s = repaired

    # 清洗后仍不像正文的，直接放弃（宁可没有摘要，也不展示垃圾文本）
    if any(k in s[:60] for k in ("浏览次数", "浏览量", "文章来源", "字体：", "字体:")):
        return None
    if not _is_content_line(s):
        return None

    return _truncate(s, 200)


def _extract_summary(soup: BeautifulSoup, title: str = "") -> Optional[str]:
    """提取摘要：优先正文容器内的首个有效段落。

    只取真正的内容段落（含中文句读），跳过导航、面包屑、友链、
    来源/日期等元信息行。无法可靠提取时返回 None，不用导航文字凑数。
    """
    # 收集候选容器，按「有效正文字数」打分，取最优
    scored = []
    for tag in soup.find_all(["div", "article", "section"]):
        if _classify_container(tag) == -1:
            continue
        lines = _extract_paragraphs(tag, title)
        good = [ln for ln in lines if _is_content_line(ln)]
        if not good:
            continue
        score = sum(len(ln) for ln in good)
        # 正文容器加权（TRS 编辑器等最可靠）
        if _classify_container(tag) == 1:
            score *= 1.5
        scored.append((score, good[0]))

    if scored:
        scored.sort(key=lambda x: -x[0])
        result = _finalize_summary(scored[0][1], title)
        if result:
            return result

    # 兜底：任意 <p> 中的有效段落
    for p in soup.find_all("p"):
        result = _finalize_summary(p.get_text(" ", strip=True), title)
        if result and not _is_noise_line(result):
            return result

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
