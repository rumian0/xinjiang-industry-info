// 数据加载与配置读取工具（全站唯一数据入口）
// 编译期读取 data/ 与 config/，集中完成排序、索引与统计，避免各页面重复计算。
import type { Article, ArticlesData, SourceTypeCode } from '../types';
import sourceTypesRaw from '../../../config/source_types.json';
import categoriesRaw from '../../../config/categories.json';
import regionsRaw from '../../../config/regions.json';
import articlesJson from '../../../data/articles.json';
import testArticlesJson from '../../../data/test-articles.json';

/* ------------------------------------------------------------------ */
/* 配置                                                                */
/* ------------------------------------------------------------------ */

export const sourceTypes = sourceTypesRaw.source_types as {
  code: SourceTypeCode;
  name: string;
  order: number;
}[];

export const industryTags = categoriesRaw.industry_tags as {
  code: string;
  name: string;
}[];

export const regionsConfig = regionsRaw.regions as {
  code: string;
  name: string;
  group: string;
  level: string;
}[];
export type RegionItem = (typeof regionsConfig)[number];

export const regionGroups = regionsRaw.groups as Record<
  string,
  { code: string; name: string; order: number }
>;

/** 名称映射表，供客户端脚本使用（统一从配置生成，不在组件里硬编码） */
export const sourceTypeMap: Record<string, string> = Object.fromEntries(
  sourceTypes.map((s) => [s.code, s.name]),
);
export const industryTagMap: Record<string, string> = Object.fromEntries(
  industryTags.map((t) => [t.code, t.name]),
);
export const regionMap: Record<string, string> = Object.fromEntries(
  regionsConfig.map((r) => [r.code, r.name]),
);
export const regionGroupMap: Record<string, string> = Object.fromEntries(
  Object.values(regionGroups).map((g) => [g.code, g.name]),
);

/* ------------------------------------------------------------------ */
/* 时间处理                                                            */
/* ------------------------------------------------------------------ */

/**
 * 解析发布时间为时间戳。
 * 数据里的 published_at 有两种形态：完整 ISO，或只有日期（YYYY-MM-DD）。
 * 无法解析时返回 null —— 调用方必须显式处理，不得回退成采集时间冒充发布时间。
 */
export function parseArticleDate(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

/** 采集时间解析，用于「最新采集」排序的降级依据 */
export function parseCollectedAt(iso: string | null | undefined): number {
  if (!iso) return 0;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
}

/** 发布日期展示：只有日期时直接展示日期，避免为原文臆造具体时刻 */
export function formatPublished(iso: string | null | undefined): string {
  if (!iso) return '时间待确认';
  const t = parseArticleDate(iso);
  if (t === null) return '时间待确认';
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  return new Date(t).toISOString().slice(0, 10);
}

/**
 * 按北京时间（UTC+8）格式化，不依赖构建机器的本地时区。
 * GitHub Actions 运行在 UTC 环境，若用 getHours() 会让时间少 8 小时。
 */
export function formatBeijingTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const d = new Date(t + 8 * 3600 * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(
    d.getUTCDate(),
  )} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** 数据更新时间展示（来自 articles.json 的 generated_at，真实值，北京时间） */
export function formatGeneratedAt(iso: string | null | undefined): string {
  return formatBeijingTime(iso);
}

/* ------------------------------------------------------------------ */
/* 排序                                                                */
/* ------------------------------------------------------------------ */

export type SortMode = 'published' | 'collected';

/**
 * 排序规则：
 * - published：按发布时间降序；无发布时间的排最后（不臆造时间），同组内按采集时间降序。
 * - collected：按采集时间降序，保证新采集内容始终在前。
 */
export function sortArticles(list: Article[], mode: SortMode = 'published'): Article[] {
  const out = [...list];
  if (mode === 'collected') {
    out.sort((a, b) => parseCollectedAt(b.collected_at) - parseCollectedAt(a.collected_at));
    return out;
  }
  out.sort((a, b) => {
    const ta = parseArticleDate(a.published_at);
    const tb = parseArticleDate(b.published_at);
    if (ta === null && tb === null) {
      return parseCollectedAt(b.collected_at) - parseCollectedAt(a.collected_at);
    }
    if (ta === null) return 1;
    if (tb === null) return -1;
    if (tb !== ta) return tb - ta;
    return parseCollectedAt(b.collected_at) - parseCollectedAt(a.collected_at);
  });
  return out;
}

/* ------------------------------------------------------------------ */
/* 数据索引                                                            */
/* ------------------------------------------------------------------ */

const rawArticles = articlesJson as ArticlesData;

/** 正式数据（剔除测试数据），已按发布时间降序排列 */
export const allArticles: Article[] = sortArticles(
  rawArticles.articles.filter((a) => !a.is_test),
  'published',
);

/** 数据文件生成时间（真实值，用于「数据更新时间」展示） */
export const generatedAt: string = rawArticles.generated_at ?? '';
export const generatedAtLabel: string = formatGeneratedAt(generatedAt);

/** id → 文章 索引，供详情页与卡片链接使用 */
const articleIndex = new Map<string, Article>(allArticles.map((a) => [a.id, a]));

/** 兼容原有调用方式 */
export function loadArticles(): Article[] {
  return allArticles;
}

export function loadTestArticles(): Article[] {
  const data = testArticlesJson as ArticlesData;
  return data.articles.filter((a) => a.is_test);
}

export function getArticleById(id: string): Article | undefined {
  return articleIndex.get(id);
}

/** 按地区分组取文章（保留配置化口径，不在此处硬编码任何地区规则） */
export function articlesByGroup(group: string): Article[] {
  return allArticles.filter((a) => a.region_group === group);
}

/** 按产业主题取文章 */
export function articlesByIndustry(code: string): Article[] {
  return allArticles.filter((a) => a.industry_tags.includes(code));
}

/* ------------------------------------------------------------------ */
/* 统计                                                                */
/* ------------------------------------------------------------------ */

/** 各分组文章数（按 config/regions.json 的 groups 定义输出） */
export const groupCounts: Record<string, number> = (() => {
  const counts: Record<string, number> = {};
  for (const code of Object.keys(regionGroups)) counts[code] = 0;
  for (const a of allArticles) {
    counts[a.region_group] = (counts[a.region_group] ?? 0) + 1;
  }
  return counts;
})();

/** 各来源类型文章数 */
export const sourceTypeCounts: Record<string, number> = (() => {
  const counts: Record<string, number> = {};
  for (const s of sourceTypes) counts[s.code] = 0;
  for (const a of allArticles) {
    counts[a.source_type] = (counts[a.source_type] ?? 0) + 1;
  }
  return counts;
})();

/** 各产业主题文章数 */
export const industryCounts: Record<string, number> = (() => {
  const counts: Record<string, number> = {};
  for (const t of industryTags) counts[t.code] = 0;
  for (const a of allArticles) {
    for (const tag of a.industry_tags) counts[tag] = (counts[tag] ?? 0) + 1;
  }
  return counts;
})();

/** 已接入来源数（按 source_name 去重） */
export const sourceNameCount: number = new Set(allArticles.map((a) => a.source_name)).size;

/* ------------------------------------------------------------------ */
/* 兼容旧 API                                                          */
/* ------------------------------------------------------------------ */

export function sourceTypeName(code: string): string {
  return sourceTypeMap[code] ?? code;
}

export function regionName(code: string | null): string {
  if (!code) return '全区性';
  return regionMap[code] ?? code;
}

export function industryTagName(code: string): string {
  return industryTagMap[code] ?? code;
}

export function regionGroupName(code: string): string {
  return regionGroupMap[code] ?? code;
}
