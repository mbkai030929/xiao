#!/usr/bin/env python3
"""
build_shortlist.py — 达人候选名单聚合工具（含报价估算）

读取 JSON 记录数组（来自多源 WebFetch 抓取后整理），执行：
  去重 → 过滤（粉丝区间/平台/预算）→ 报价估算 → 排序（互动率优先）→ 输出（CSV + Markdown）

输入 JSON 格式（数组）：
[
  {
    "handle": "@xxx",
    "platform": "tiktok",
    "followers": 533900,
    "engagement_rate": 4.64,
    "location": "US",
    "niche": "beauty",
    "partnerships": "Fenty, NYX",
    "source": "influData",
    "source_date": "2026-07"
  },
  ...
]

字段说明：
  handle(必填) platform(必填) followers(必填, int)
  engagement_rate(可选, float 百分比) location/niche/partnerships/source/source_date(可选, str)

用法：
  python3 build_shortlist.py --input records.json \
      --min-followers 100000 --max-followers 1000000 \
      --platform tiktok --limit 20 \
      --budget-max 10000 --pricing-model dedicated \
      --csv shortlist.csv --md shortlist.md

也支持 stdin：cat records.json | python3 build_shortlist.py ...
"""

import argparse
import json
import sys
import csv
import io
from datetime import datetime


# ── 输出字段 ──────────────────────────────────────────────
FIELDS = ["handle", "platform", "followers", "engagement_rate",
          "location", "niche", "partnerships", "source", "source_date",
          "estimated_price_low", "estimated_price_high", "pricing_model"]

# ── 报价基准表（2026，USD）──────────────────────────────────
# 按 (platform, tier) 查找，返回 (standard_low, standard_high, dedicated_low, dedicated_high)
# 来源：influencerfee.com、SocialBlade 估算、行业基准，近似值
#
# tier 由粉丝量决定：
#   nano    1K–10K
#   micro   10K–100K
#   mid     100K–500K
#   macro   500K–2M
#   mega    2M+
#
# TikTok 报价通常高于 YouTube 同级别（短视频制作门槛低+算法推荐爆发力强）

TIERS = [
    # (min_followers, tier_name)
    (0,         "nano"),
    (10_000,    "micro"),
    (100_000,   "mid"),
    (500_000,   "macro"),
    (2_000_000, "mega"),
]

PRICING_TABLE = {
    # (platform, tier): (std_low, std_high, ded_low, ded_high)
    # TikTok 美妆/时尚/生活方式（高商业价值垂类）
    ("tiktok", "nano"):  (50,    300,    150,    600),
    ("tiktok", "micro"): (300,   2_500,  800,    5_000),
    ("tiktok", "mid"):   (2_000, 10_000, 5_000,  20_000),
    ("tiktok", "macro"): (8_000, 40_000, 15_000, 75_000),
    ("tiktok", "mega"):  (20_000,100_000,50_000, 200_000),

    # YouTube（CPM 模型，通常按万次观看报价，这里折算为粉丝量近似）
    ("youtube", "nano"):  (0,     200,    100,    500),
    ("youtube", "micro"): (200,   2_000,  600,    4_000),
    ("youtube", "mid"):   (1_500, 8_000,  4_000,  18_000),
    ("youtube", "macro"): (6_000, 30_000, 12_000, 60_000),
    ("youtube", "mega"):  (15_000,80_000, 40_000, 150_000),
}

# 低商业价值垂类折扣系数（科技/游戏/教育等 B2B 或低转化垂类通常报价更低）
LOW_VALUE_NICHES = {"gaming", "education", "tech", "science", "politics"}
LOW_VALUE_DISCOUNT = 0.7

# 高商业价值垂类溢价（美妆/时尚/理财/健康）
HIGH_VALUE_NICHES = {"beauty", "makeup", "skincare", "fashion", "finance",
                     "fitness", "health", "luxury", "travel"}
HIGH_VALUE_PREMIUM = 1.2


def get_tier(followers):
    """根据粉丝量返回 tier 名称。"""
    tier = "nano"
    for threshold, name in TIERS:
        if followers >= threshold:
            tier = name
        else:
            break
    return tier


def estimate_price(followers, platform, niche=""):
    """估算报价，返回 (low, high, model_note)。

    model_note 说明报价口径：
      standard = 植入/提及
      dedicated = 专属视频/帖子
    返回 dedicated 档报价（更常用做预算规划），同时输出区间。
    若需 standard 档，调用方可用 pricing_model 参数切换。
    """
    tier = get_tier(followers)
    niche_lower = (niche or "").lower()

    key = (platform, tier)
    if key not in PRICING_TABLE:
        # 未知平台，回退到 tiktok 基准
        key = ("tiktok", tier)

    std_low, std_high, ded_low, ded_high = PRICING_TABLE[key]

    # 垂类修正
    if any(n in niche_lower for n in HIGH_VALUE_NICHES):
        std_low, std_high = int(std_low * HIGH_VALUE_PREMIUM), int(std_high * HIGH_VALUE_PREMIUM)
        ded_low, ded_high = int(ded_low * HIGH_VALUE_PREMIUM), int(ded_high * HIGH_VALUE_PREMIUM)
    elif any(n in niche_lower for n in LOW_VALUE_NICHES):
        std_low, std_high = int(std_low * LOW_VALUE_DISCOUNT), int(std_high * LOW_VALUE_DISCOUNT)
        ded_low, ded_high = int(ded_low * LOW_VALUE_DISCOUNT), int(ded_high * LOW_VALUE_DISCOUNT)

    return std_low, std_high, ded_low, ded_high


def parse_followers(raw):
    """容忍字符串形式粉丝量：'533.9K' / '1.2M' / 533900"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    s = str(raw).strip().replace(",", "")
    if not s:
        return None
    mult = 1
    low = s.lower()
    for suffix, m in (("k", 1_000), ("m", 1_000_000), ("b", 1_000_000_000)):
        if low.endswith(suffix):
            mult = m
            s = s[:-1]
            break
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


def normalize_record(rec):
    """规范化单条记录，补全缺失字段 + 估算报价。"""
    if not isinstance(rec, dict):
        return None
    handle = str(rec.get("handle", "")).strip()
    platform = str(rec.get("platform", "")).strip().lower()
    followers = parse_followers(rec.get("followers"))
    if not handle or not platform or followers is None:
        return None  # 必填缺失
    er = rec.get("engagement_rate")
    try:
        er = float(er) if er not in (None, "", "-") else None
    except (TypeError, ValueError):
        er = None

    niche = str(rec.get("niche", "") or "").strip()
    std_low, std_high, ded_low, ded_high = estimate_price(followers, platform, niche)

    return {
        "handle": handle,
        "platform": platform,
        "followers": followers,
        "engagement_rate": er,
        "location": str(rec.get("location", "") or "").strip(),
        "niche": niche,
        "partnerships": str(rec.get("partnerships", "") or "").strip(),
        "source": str(rec.get("source", "") or "").strip(),
        "source_date": str(rec.get("source_date", "") or "").strip(),
        # 报价字段
        "estimated_price_low": ded_low,
        "estimated_price_high": ded_high,
        "pricing_model": "dedicated",
        # 保留 standard 报价供切换（不输出但可用于过滤）
        "_std_low": std_low,
        "_std_high": std_high,
    }


def completeness_score(rec):
    """数据完整度评分，用于去重冲突时择优保留。"""
    score = 0
    if rec["engagement_rate"] is not None:
        score += 3
    for f in ("location", "niche", "partnerships", "source_date"):
        if rec.get(f):
            score += 1
    score += min(rec["followers"], 10_000_000) / 10_000_000  # 粉丝量微弱加权
    return score


def dedupe(records):
    """按 (platform, handle) 去重，冲突保留完整度更高者。"""
    seen = {}
    for rec in records:
        key = (rec["platform"], rec["handle"].lower().lstrip("@"))
        if key not in seen or completeness_score(rec) > completeness_score(seen[key]):
            seen[key] = rec
    return list(seen.values())


def filter_records(records, min_f, max_f, platform, budget_max, pricing_model):
    """过滤：粉丝区间 + 平台 + 预算上限。

    budget_max: 若指定，过滤掉报价下限超过预算的达人。
                pricing_model 决定用 standard 还是 dedicated 档报价比较。
    """
    out = []
    for r in records:
        if platform and r["platform"] != platform:
            continue
        if min_f is not None and r["followers"] < min_f:
            continue
        if max_f is not None and r["followers"] > max_f:
            continue

        if budget_max is not None:
            if pricing_model == "standard":
                price_low = r["_std_low"]
            else:
                price_low = r["estimated_price_low"]
            if price_low > budget_max:
                continue

        out.append(r)
    return out


def sort_records(records):
    """有互动率者优先（ER 降序），无 ER 者按粉丝量降序垫后。"""
    with_er = [r for r in records if r["engagement_rate"] is not None]
    without_er = [r for r in records if r["engagement_rate"] is None]
    with_er.sort(key=lambda r: r["engagement_rate"], reverse=True)
    without_er.sort(key=lambda r: r["followers"], reverse=True)
    return with_er + without_er


def fmt_followers(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def fmt_price(low, high):
    """格式化报价区间：$2,000–$10,000"""
    return f"${low:,}–${high:,}"


def to_csv(records, pricing_model="dedicated"):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    for r in records:
        if pricing_model == "standard":
            low, high = r["_std_low"], r["_std_high"]
        else:
            low, high = r["estimated_price_low"], r["estimated_price_high"]
        writer.writerow({
            "handle": r["handle"],
            "platform": r["platform"],
            "followers": r["followers"],
            "engagement_rate": r["engagement_rate"] if r["engagement_rate"] is not None else "",
            "location": r["location"],
            "niche": r["niche"],
            "partnerships": r["partnerships"],
            "source": r["source"],
            "source_date": r["source_date"],
            "estimated_price_low": low,
            "estimated_price_high": high,
            "pricing_model": pricing_model,
        })
    return buf.getvalue()


def to_markdown(records, pricing_model="dedicated"):
    header = (f"| # | handle | platform | followers | ER(%) | location | niche | "
              f"est. price ({pricing_model}) | partnerships | source |")
    sep = "|---|--------|----------|-----------|-------|----------|-------|-----------|--------------|--------|"
    lines = [header, sep]
    for i, r in enumerate(records, 1):
        er = "" if r["engagement_rate"] is None else f"{r['engagement_rate']:.2f}"
        if pricing_model == "standard":
            price = fmt_price(r["_std_low"], r["_std_high"])
        else:
            price = fmt_price(r["estimated_price_low"], r["estimated_price_high"])
        lines.append(
            f"| {i} | {r['handle']} | {r['platform']} | {fmt_followers(r['followers'])} | {er} | "
            f"{r['location']} | {r['niche']} | {price} | {r['partnerships']} | {r['source']} |"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="达人候选名单聚合工具（含报价估算）")
    ap.add_argument("--input", help="输入 JSON 文件路径（不给则读 stdin）")
    ap.add_argument("--min-followers", type=int, help="粉丝下限")
    ap.add_argument("--max-followers", type=int, help="粉丝上限")
    ap.add_argument("--platform", help="平台过滤 (tiktok/youtube)")
    ap.add_argument("--limit", type=int, help="输出数量上限")
    ap.add_argument("--budget-max", type=int,
                    help="预算上限（USD），过滤掉报价下限超出预算的达人")
    ap.add_argument("--pricing-model", choices=["standard", "dedicated"],
                    default="dedicated",
                    help="报价档位：standard=植入/提及，dedicated=专属视频（默认）")
    ap.add_argument("--csv", help="CSV 输出文件路径")
    ap.add_argument("--md", help="Markdown 输出文件路径")
    args = ap.parse_args()

    # 读取输入
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = json.load(sys.stdin)

    if not isinstance(raw, list):
        sys.exit("错误：输入需为 JSON 数组")

    # 规范化（含报价估算）
    records = [r for r in (normalize_record(x) for x in raw) if r]
    skipped = len(raw) - len(records)

    # 去重 → 过滤（含预算）→ 排序
    records = dedupe(records)
    pre_filter_count = len(records)
    records = filter_records(records, args.min_followers, args.max_followers,
                             args.platform, args.budget_max, args.pricing_model)
    if args.limit:
        records = records[:args.limit]

    # 输出
    md = to_markdown(records, args.pricing_model)
    csv_text = to_csv(records, args.pricing_model)

    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(md)

    # 摘要
    budget_note = f"，预算上限 ${args.budget_max:,}" if args.budget_max else ""
    model_note = f"（{args.pricing_model} 档）" if args.budget_max else ""
    print(f"输入 {len(raw)} 条，有效 {len(raw)-skipped} 条，跳过 {skipped} 条无效记录", file=sys.stderr)
    print(f"去重后 {pre_filter_count} 条，过滤后 {len(records)} 条{budget_note}{model_note}", file=sys.stderr)
    print(f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n", file=sys.stderr)
    print(md)


if __name__ == "__main__":
    main()
