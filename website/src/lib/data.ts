// 数据加载与配置读取工具
// 读取 data/ 下的 JSON 与 config/ 下的配置，供页面使用。
import type { Article, ArticlesData, SourceTypeCode } from '../types';
import sourceTypesRaw from '../../../config/source_types.json';
import categoriesRaw from '../../../config/categories.json';
import regionsRaw from '../../../config/regions.json';

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

export const regionGroups = regionsRaw.groups as Record<
  string,
  { code: string; name: string; order: number }
>;

/** 读取正式数据（不含测试数据） */
export function loadArticles(): Article[] {
  const data = readArticlesFile();
  return data.articles.filter((a) => !a.is_test);
}

/** 读取测试数据（仅开发环境展示用，is_test 为 true） */
export function loadTestArticles(): Article[] {
  const data = readTestFile();
  return data.articles.filter((a) => a.is_test);
}

function readArticlesFile(): ArticlesData {
  // Astro 构建时通过 Vite 的 JSON 导入读取
  const data = articlesJson as ArticlesData;
  return data;
}

function readTestFile(): ArticlesData {
  return testArticlesJson as ArticlesData;
}

// 通过 Vite 的 ?raw 或默认 JSON 导入读取数据文件
import articlesJson from '../../../data/articles.json';
import testArticlesJson from '../../../data/test-articles.json';

/** 按来源类型 code 查名称 */
export function sourceTypeName(code: string): string {
  const found = sourceTypes.find((s) => s.code === code);
  return found?.name ?? code;
}

/** 按地区 code 查名称 */
export function regionName(code: string | null): string {
  if (!code) return '待确认';
  const found = regionsConfig.find((r) => r.code === code);
  return found?.name ?? code;
}

/** 按产业主题 code 查名称 */
export function industryTagName(code: string): string {
  const found = industryTags.find((t) => t.code === code);
  return found?.name ?? code;
}

/** 按地区分组查名称 */
export function regionGroupName(code: string): string {
  return regionGroups[code]?.name ?? code;
}
