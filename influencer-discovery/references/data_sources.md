# Data Sources Catalog

公开达人排行榜与数据库目录。按平台与覆盖能力选用，多源并行以提高召回与多样性。

## TikTok 数据源

### influData
- URL 模式：`https://infludata.com/rankings/top-20-influencer-{country}-{niche}-tiktok`
- 示例：`.../top-20-influencer-united-states-of-america-beauty-tiktok`
- 暴露字段：handle, followers, engagement_rate, monthly_growth, location, score
- 国家/地区细分：支持（united-states-of-america / los-angeles / 等城市级）
- 垂类细分：支持（beauty / fashion / food / fitness 等）
- 特点：互动率数据较可靠，按粉丝增长排序，更新较频繁（月更）
- 用法：WebSearch 站内 + WebFetch 榜单页提取表格

### feedspot
- URL 模式：`https://creators.feedspot.com/{niche}_{platform}_influencers/`
- 示例：`https://creators.feedspot.com/beauty_tiktok_influencers/`
- 暴露字段：handle, followers, type(micro/macro/mega), bio, email(部分 gated)
- 垂类覆盖广：beauty / makeup / skincare / fitness / tech / food 等
- 特点：列表长（Top 50+），含 bio 与商务邮箱入口，便于后续 people-search
- 用法：WebFetch 提取 handle + followers + bio

### Socialkaat
- URL 模式：`https://landing.socialkaat.com/influencers/{platform}-{niche}`
- 示例：`https://landing.socialkaat.com/influencers/tiktok-makeup`
- 暴露字段：handle, followers, engagement_rate(ER), age, location, tags
- 特点：带 ER 与年龄，按 ER 降序，适合筛高互动达人
- 注意：部分为 Instagram 数据，需确认 platform 字段

### IQFluence
- URL 模式：`https://iqfluence.io/public/top-tiktok-influencers/{niche}-influencers-on-tiktok`
- 暴露字段：handle, followers, engagement_rate, average_likes, audience_location_by_country
- 特点：含受众国家分布，可判断受众市场；公开页数据有限，完整需登录
- 用法：WebFetch 提取 + 用 audience_location 过滤目标市场

### HypeAuditor（公开榜）
- URL：`https://hypeauditor.com/top-tiktok-{niche}-{country}/`
- 暴露字段：handle, followers, engagement_rate, audience_country（部分）
- 特点：行业权威，假粉检测强；公开页仅 Top 摘要
- 用法：补充头部与质量信号

### Ainfluencer
- URL 模式：`https://influencermarketing.ainfluencer.com/{topic}-influencers/`
- 示例：`.../amazon-makeup-influencers/`、`.../american-makeup-influencers/`
- 暴露字段：handle, followers(多平台), engagement_rate, avg_likes, avg_views, bio
- 特点：跨平台粉丝量 + ER，含合作品牌线索

## YouTube 数据源

### feedspot（YouTube）
- URL 模式：`https://blog.feedspot.com/{niche}_youtube_channels/`
- 示例：`https://blog.feedspot.com/beauty_youtube_channels/`
- 暴露字段：频道名, subscribers, bio, 邮箱入口
- 特点：频道列表长，垂类全

### socialblade
- URL：`https://socialblade.com/youtube/` 与 `https://socialblade.com/tiktok/`
- 暴露字段：subscribers/followers, views, 等级, 增长
- 特点：单频道统计查询为主，适合已知频道核验；榜单页可按垂类/地区浏览
- 用法：核验粉丝量级，补 socialblade grade

### YouTube Data API v3（需凭证）
- 端点：`search.list`（按关键词搜频道）+ `channels.list`（取 statistics: subscriberCount/viewCount/videoCount）
- 配额：每日 10,000 单位，search 较耗配额
- 用法：有 API key 时封装脚本按 niche 关键词检索频道并取统计

## 策展/编辑精选（补充多样性）

### Bustle / 行业媒体
- 示例：`https://nc.bustle.com/beauty/beauty-icon-awards-2025-creators-of-the-year`
- 特点：人工策展，含粉丝量与内容风格描述，质量高但数量少
- 用法：补充差异化候选（如 SFX 妆、卷发护理等细分）

### 行业报告
- influencerfee.com：报价基准（按粉丝区间给 standard/dedicated 单价）
- 用法：补报价参考，非名单源

## 检索策略

1. **多源并行**：单一榜单常不足目标数量且偏头部，至少用 2-3 个源
2. **中英双词**：niche 同时用中英文搜（美妆/beauty），覆盖更全
3. **时效优先**：检索词带当年年份，优先最新榜单
4. **城市级细分**：influData 等支持城市级（los-angeles），可按需细化
5. **受众市场过滤**：IQFluence/HypeAuditor 的 audience_country 字段可判断真实受众市场，避免"人在美国但受众在拉美"的错配

## 各粉丝区间报价参考（2026，TikTok 美妆）

| 区间 | standard 植入 | dedicated 专属视频 |
|------|--------------|-------------------|
| nano 1K–10K | $50–$300 | $150–$600 |
| micro 10K–100K | $300–$2,500 | $800–$5,000 |
| mid 100K–500K | $2,000–$10,000 | $5,000–$20,000 |
| macro 500K–2M | $8,000–$40,000 | $15,000–$75,000 |

TikTok Shop 分销多为 8–15% 佣金制。来源：influencerfee.com。
