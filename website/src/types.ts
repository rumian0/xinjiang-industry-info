// 新疆产业信息聚合网站 - 数据结构定义
// 与 data/articles.json 的结构一一对应，作为读取时的类型约束。

/** 来源类型 code */
export type SourceTypeCode =
  | 'government'
  | 'media'
  | 'enterprise'
  | 'association'
  | 'investment'
  | 'other';

/** 地区分组 */
export type RegionGroup = 'quanjang' | 'nanjiang' | 'beijiang' | 'pending';

/** 信息状态 */
export type ArticleStatus = 'published' | 'pending' | 'review';

/** 内容类型 */
export type ContentType = 'news' | 'policy' | 'announcement' | 'project' | 'other';

/** 单条产业信息 */
export interface Article {
  /** 唯一标识，建议用 URL 哈希或稳定 ID */
  id: string;
  title: string;
  summary: string;
  /** 摘要来源：extracted(原文提取) / truncated(原文开头片段) */
  summary_source?: 'extracted' | 'truncated';
  source_type: SourceTypeCode;
  source_name: string;
  source_url: string;
  /** ISO 8601，原文发布时间；无法确认时为 null，不得用采集时间冒充 */
  published_at: string | null;
  /** ISO 8601，采集时间 */
  collected_at: string;
  region_group: RegionGroup;
  /** 具体地区 code，对应 regions.json；不确定为 null */
  region: string | null;
  /** 产业主题标签 code 数组 */
  industry_tags: string[];
  content_type: ContentType;
  status: ArticleStatus;
  /** 标记：是否为测试数据 */
  is_test?: boolean;
  /** 重复/转载标记 */
  duplicate_of?: string;
}

/** articles.json 顶层结构 */
export interface ArticlesData {
  generated_at: string;
  count: number;
  articles: Article[];
}
