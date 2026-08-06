---
name: influencer-discovery
description: 采集 YouTube / TikTok 达人候选名单的技能。按行业/垂类、地区/市场、粉丝量区间、平台、预算/报价等条件，从公开排行榜与达人数据库抓取并汇总达人名单（handle、粉丝量、互动率、所在地、内容定位、已知合作、估算报价）。当用户需要"找达人 / 筛选 KOL / 采集网红名单 / 找 TikTok 或 YouTube 博主 / 按粉丝量筛选达人 / 按预算找达人 / influencer discovery / influencer list / KOL 候选名单"时触发。本技能产出候选名单与粗略指标含报价估算，不负责精确受众画像分析或联系方式采集（由后续 fit-scorer / people-search 环节处理）。
agent_created: true
---

# Influencer Discovery

## Overview

按行业、地区、粉丝量、预算/报价等条件，采集 YouTube / TikTok 达人候选名单。核心方法是用 WebSearch + WebFetch 从公开排行榜与达人数据库抓取结构化数据，再聚合、去重、过滤、报价估算、排序，输出可直接用于筛选的候选表（Markdown 表格 + 可选 CSV），含每人的估算报价区间。

数据来自第三方公开榜单（influData、feedspot、Socialkaat、IQFluence、HypeAuditor 公开页、socialblade 等），指标为近似值且会实时变动；精确受众画像与互动真实性需后续 fit-scorer 环节用专业工具（HypeAuditor / Modash 等付费 API）核验。

## When to Use

触发场景：
- "帮我找 TikTok 美国美妆达人，10万到100万粉丝"
- "筛选 YouTube 科技区博主，50万粉以上，给我20个"
- "找 TikTok 健身 KOL，预算 $5,000 以内的"
- "采集 TikTok 美妆类 KOL 名单，要看报价"
- "按地区和粉丝量筛网红候选，单条预算不超过 $3,000"

不处理：精确受众画像 / 假粉检测（→ fit-scorer）、联系方式采集（→ people-search）、外联邮件（→ cold-message-writer）。

## Workflow

### Step 1 — 解析筛选条件

从用户请求中提取以下参数，缺失项主动询问或做合理默认：

| 参数 | 说明 | 示例 |
|------|------|------|
| platform | YouTube / TikTok / 两者 | TikTok |
| niche | 行业/垂类关键词（中英双语） | 美妆 beauty / 健身 fitness / 科技 tech |
| region/market | 地区或市场 | 美国 US / 东南亚 / 全球 |
| follower_min | 粉丝下限 | 100000 |
| follower_max | 粉丝上限 | 1000000 |
| count | 需要的候选数量 | 20 |
| budget_max | 预算上限（USD，可选）| 5000 |
| pricing_model | 报价档位：standard(植入) / dedicated(专属视频) | dedicated |
| extra | 互动率门槛、人群定向等（可选） | ER ≥ 5% |

将 niche 转成英文关键词（达人榜单多为英文），并准备多个同义词以提高检索召回（如 美妆 → beauty, makeup, cosmetics, skincare）。

### Step 2 — 选择数据源并检索

参考 `references/data_sources.md`（完整数据源目录、URL 模式、各源暴露的字段）。按 platform 与 region 选择最匹配的源，用 WebSearch 发起多组并行检索：

- 榜单站检索：`{niche_en} influencers {platform} {region} {year}` + 站点名（influData / feedspot / Socialkaat / IQFluence）
- 排行 URL 直取：对已知 URL 模式（见 references）直接 WebFetch，提取 handle / 粉丝量 / 互动率 / 所在地
- 编辑精选：补充 Bustle、行业媒体等策展名单，增加多样性

检索要点：
- 多源并行，单源往往不足 N 个且偏头部
- 同时搜中英文 niche 词，覆盖更全
- 关注 year 字段，优先取最新榜单（当年或去年）

### Step 3 — 抓取与结构化

对检索到的榜单页用 WebFetch，prompt 明确要求提取以下字段（按源能力取子集）：
`handle | platform | followers | engagement_rate | location | niche/content_focus | known_partnerships | source | source_date`

WebFetch 返回多为半结构化文本。将其整理为 JSON 记录数组，每条记录字段对齐 output schema（见下）。无法解析的字段留空，不要编造。

### Step 4 — 聚合、去重、过滤、报价估算、排序

将各源记录合并后运行 `scripts/build_shortlist.py`：

```bash
# 脚本仅用 Python 标准库，任何 Python 3.x 均可
python3 scripts/build_shortlist.py \
  --input records.json \
  --min-followers 100000 --max-followers 1000000 \
  --platform tiktok \
  --limit 20 \
  --budget-max 10000 \
  --pricing-model dedicated \
  --csv shortlist.csv \
  --md shortlist.md
```

脚本功能：
- 按 (platform, handle) 去重，冲突时保留数据更完整的记录
- 按粉丝量区间过滤
- 按平台过滤
- **报价估算**：按 (平台 × 粉丝区间 × 垂类) 查报价基准表，垂类自动溢价/折扣（美妆/时尚/理财 +20%，科技/游戏/教育 -30%）
- **预算过滤**：`--budget-max` 指定后，报价下限超出预算的达人自动剔除
- 排序：有互动率者优先（ER 降序），无 ER 者按粉丝量降序垫后
- 输出 CSV 与 Markdown 表格，含 `est. price` 列

报价档位说明：
- `standard` = 植入/提及（在现有内容中露出品牌）
- `dedicated` = 专属视频/帖子（整条内容围绕品牌）

若脚本不可用或数据量小，可直接手工去重过滤，但优先用脚本保证一致性。

### Step 5 — 输出与说明

输出包含：
1. **候选表**（Markdown 表格，按 ER/质量排序），列：序号 / handle / 粉丝量(约) / 互动率 / 所在地 / 内容定位 / **估算报价** / 已知合作 / 数据来源
2. **重要说明**：
   - 粉丝量为近似值，来自第三方公开数据，实时变动，合作前以实时数据为准
   - 互动率口径因源而异，部分标"待测"，需专业工具核验
   - **报价为脚本按粉丝区间×垂类自动估算的参考区间，非达人实际报价**；实际报价受季节性、排期、内容复杂度、独家性等影响波动较大
   - 报价档位标注（standard/dedicated），TikTok Shop 分销另计佣金（8–15%）
3. **下一步建议**：收敛细分方向 / 补测 ER+受众画像 / 采集联系方式 / 按预算进一步收敛

## Output Schema

每条候选记录字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| handle | string | 平台用户名（含@） |
| platform | string | tiktok / youtube |
| followers | int | 粉丝数（近似） |
| engagement_rate | float\|null | 互动率（百分比，无则 null） |
| location | string | 所在地（国家/城市） |
| niche | string | 内容定位/垂类 |
| partnerships | string | 已知品牌合作 |
| estimated_price_low | int | 估算报价下限（USD） |
| estimated_price_high | int | 估算报价上限（USD） |
| pricing_model | string | standard / dedicated |
| source | string | 数据来源（站名） |
| source_date | string | 数据日期 |

## Limitations & Caveats

- 公开榜单偏头部与英语市场，小语种/小众垂类召回可能不足，需额外定向搜索或人工补充
- 互动率等指标为第三方估算，与平台原生后台可能有差异
- 不采集联系方式、不验证假粉、不做受众画像深度分析——这些是后续环节职责
- 抓取遵守各站公开页面，不绕过付费墙或登录墙

## Extending with Paid APIs

若具备以下任一付费 API 凭证，可在 Step 3 增加直连接口以提升数据精度与覆盖：
- HypeAuditor API：受众画像、互动真实性、假粉检测
- Modash API：达人搜索 + 基础指标
- Upfluence / Grin API：达人库 + 联系方式
- YouTube Data API v3：频道搜索与统计（需 Google API key，配额受限）

接入时将 API 调用封装为 scripts/ 下脚本，凭证从环境变量读取，不写入技能文件。
