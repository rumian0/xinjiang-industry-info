# 新疆产业信息聚合网站

收集、整理和展示新疆各地区产业相关信息，通过 GitHub Actions 自动采集公开信息并更新到网站。

## 技术栈

- **网站**：Astro + TypeScript + CSS
- **采集**：Python（requests + BeautifulSoup + lxml + feedparser）
- **数据存储**：JSON 文件（`data/articles.json`）
- **自动采集**：GitHub Actions
- **部署**：GitHub Pages

## 目录结构

```
xinjiang-industry-info/
├── .github/workflows/
│   ├── collect.yml      # 自动采集工作流
│   └── deploy.yml       # 网站部署工作流
├── collector/           # Python 采集程序
│   ├── main.py          # 采集入口
│   ├── fetcher.py       # 网页与 RSS 获取
│   ├── parser.py        # 内容解析
│   ├── classifier.py    # 信息分类
│   ├── dedup.py         # 去重
│   ├── normalize.py     # 数据标准化
│   └── validator.py     # 数据质量检查
├── config/
│   ├── sources.json     # 信息来源配置
│   ├── source_types.json # 来源类型分类
│   ├── categories.json  # 产业主题分类
│   └── regions.json     # 地区配置
├── data/
│   ├── articles.json    # 正式数据（采集结果）
│   └── test-articles.json # 测试数据（明确标记，不混入正式数据）
├── website/             # Astro 网站项目
└── requirements.txt     # Python 依赖
```

## 三个页面

- **全疆**（`/`）：新疆产业信息总入口
- **南疆**（`/nanjiang/`）：南疆范围内产业信息
- **北疆**（`/beijiang/`）：北疆范围内产业信息

南疆、北疆页面复用统一的 `RegionPage` 组件，仅通过 `regionGroup` 参数区分。

## 地区划分说明

南疆 / 北疆的划分采用**业务口径**，可能与行政口径存在差异。划分规则单独放在 `config/regions.json` 中，**可在此修改**，请勿在代码中写死。

- `region_group` 取值：`quanjang`（全疆）、`nanjiang`（南疆）、`beijiang`（北疆）、`pending`（待确认）。
- 无法可靠确定归属的信息，标记为 `pending`（待确认），不擅自归类。

## 信息来源分类

六个一级来源分类（见 `config/source_types.json`）：

1. 政府及官方机构
2. 新闻媒体
3. 企业及集团官网
4. 行业协会及专业平台
5. 招商及项目平台
6. 其他专业信息来源

每条信息关联一个主要来源类型；产业主题标签可有多个，来源类型与产业主题分开管理。

## 已接入的信息源

当前接入 **18 个来源**（16 个启用成功采集），覆盖政府、企业、园区三类：

### 政府及官方机构（15 个）

| 信息源 | 栏目 | 采集方式 |
| --- | --- | --- |
| 自治区发展和改革委员会 | 产业发展 | 列表页解析 |
| 自治区发展和改革委员会 | 能源信息 | 列表页解析 |
| 自治区工业和信息化厅 | 工信动态 | 列表页解析 |
| 自治区工业和信息化厅 | 通知公告 | 列表页解析 |
| 自治区商务厅 | 商务动态 | 列表页解析 |
| 自治区国有资产监督管理委员会 | 经济运行情况 | 列表页解析 |
| 自治区农业农村厅 | 农业农村动态 | 列表页解析 |
| 乌鲁木齐经济技术开发区（头屯河区） | 要闻 | 列表页解析 |
| 乌鲁木齐高新技术产业开发区（新市区） | 高新要闻 | 通用列表解析 |
| 奎屯-独山子经济技术开发区 | 园区要闻 | 列表页解析 |
| 伊犁哈萨克自治州 | 重大项目建设 / 政务动态 | 列表页解析 |
| 喀什地区行政公署 | 政务动态 | 列表页解析 |
| 巴音郭楞蒙古自治州政府 | 政务动态 | 列表页解析 |
| 吐鲁番市人民政府 | 政务动态 | 列表页解析 |

### 企业及集团官网（3 个）

| 信息源 | 栏目 | 采集方式 |
| --- | --- | --- |
| 特变电工 | 企业动态 | 通用列表解析 |
| 新疆有色集团 | 公示公告 | 通用列表解析 |
| 广汇能源 | 公司要闻 | 通用列表解析 |

> **关于 RSS**：新疆政府网站多数**不提供标准 RSS/Atom 源**（`list_rss.shtml` 只是订阅说明页）。因此采集程序实现了两种网页解析方式：`method: "list"`（政务 CMS 栏目列表页，针对「大汉版通」类 CMS）和 `method: "generic"`（通用列表页，企业官网等非政务 CMS）。若未来某源提供了标准 RSS，可在 `config/sources.json` 中将其 `method` 设为 `"rss"` 并填 `rss` 地址。

> 完整的信息源调研记录（含已测试但暂未接入的来源及原因）见 `docs/sources-research.md`。

信息源全部在 `config/sources.json` 中配置，可增删，无需改代码。

## 产业主题

六大产业主题（见 `config/categories.json`），允许一条信息关联多个：

- 经济开发区与产业园区
- 企业与公司
- 矿产与自然资源
- 能源与新能源
- 交通物流与对外贸易
- 农业与特色产业

## 本地开发

### 采集程序

```bash
# 使用系统 Python（需先安装依赖）
pip install -r requirements.txt
python collector/main.py
```

### 网站

```bash
cd website
npm install
npm run dev      # 本地开发
npm run build    # 构建
```

## GitHub Actions 自动采集

- 每天北京时间 **08:00** 和 **16:00** 各采集一次。
- 也支持手动触发（workflow_dispatch）。
- 仅在数据发生变化时提交更新。
- 采集失败时保留已有数据，不因单个网站失败导致数据丢失。

> **注意**：GitHub Actions 定时任务存在延迟，不能保证每次都在指定分钟准时运行。这是 GitHub 平台的固有行为。

## 数据真实性原则

- 标题和摘要必须来自真实采集内容，不编造。
- 原文发布时间无法确认时，不将采集时间伪装成发布时间（`published_at` 留空）。
- 测试数据明确标记 `is_test: true`，并存放在独立的 `test-articles.json`，不混入正式数据。
- 分类不确定的信息标记为待确认，不猜测。
