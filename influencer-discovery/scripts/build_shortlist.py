#!/usr/bin/env python3
"""
build_shortlist.py — 达人候选名单聚合工具

读取 JSON 记录数组（来自多源 WebFetch 抓取后整理），执行：
  去重 → 过滤（粉丝区间/平台）→ 排序（互动率优先）→ 输出（CSV + Markdown）

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
      --csv shortlist.csv --md shortlist.md

也支持 stdin：cat records.json | python3 build_shortlist.py ...
"""

import argparse
import json
import sys
import csv
import io
from datetime import datetime


FIELDS = ["handle", "platform", "followers", "engagement_rate",
          "location", "niche", "partnerships", "source", "source_date"]


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
    """规范化单条记录，补全缺失字段。"""
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
    return {
        "handle": handle,
        "platform": platform,
        "followers": followers,
        "engagement_rate": er,
        "location": str(rec.get("location", "") or "").strip(),
        "niche": str(rec.get("niche", "") or "").strip(),
        "partnerships": str(rec.get("partnerships", "") or "").strip(),
        "source": str(rec.get("source", "") or "").strip(),
        "source_date": str(rec.get("source_date", "") or "").strip(),
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


def filter_records(records, min_f, max_f, platform):
    out = []
    for r in records:
        if platform and r["platform"] != platform:
            continue
        if min_f is not None and r["followers"] < min_f:
            continue
        if max_f is not None and r["followers"] > max_f:
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


def to_csv(records):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    for r in records:
        writer.writerow({f: ("" if r.get(f) is None else r.get(f)) for f in FIELDS})
    return buf.getvalue()


def to_markdown(records):
    header = "| # | handle | platform | followers | ER(%) | location | niche | partnerships | source |"
    sep = "|---|--------|----------|-----------|-------|----------|-------|--------------|--------|"
    lines = [header, sep]
    for i, r in enumerate(records, 1):
        er = "" if r["engagement_rate"] is None else f"{r['engagement_rate']:.2f}"
        lines.append(
            f"| {i} | {r['handle']} | {r['platform']} | {fmt_followers(r['followers'])} | {er} | "
            f"{r['location']} | {r['niche']} | {r['partnerships']} | {r['source']} |"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="达人候选名单聚合工具")
    ap.add_argument("--input", help="输入 JSON 文件路径（不给则读 stdin）")
    ap.add_argument("--min-followers", type=int, help="粉丝下限")
    ap.add_argument("--max-followers", type=int, help="粉丝上限")
    ap.add_argument("--platform", help="平台过滤 (tiktok/youtube)")
    ap.add_argument("--limit", type=int, help="输出数量上限")
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

    # 规范化
    records = [r for r in (normalize_record(x) for x in raw) if r]
    skipped = len(raw) - len(records)

    # 去重 → 过滤 → 排序
    records = dedupe(records)
    records = filter_records(records, args.min_followers, args.max_followers, args.platform)
    records = sort_records(records)
    if args.limit:
        records = records[:args.limit]

    # 输出
    md = to_markdown(records)
    csv_text = to_csv(records)

    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(md)

    # 摘要到 stderr / stdout
    print(f"输入 {len(raw)} 条，有效 {len(raw)-skipped} 条，跳过 {skipped} 条无效记录", file=sys.stderr)
    print(f"去重后 {len(dedupe([r for r in (normalize_record(x) for x in raw) if r]))} 条，"
          f"过滤后 {len(records)} 条", file=sys.stderr)
    print(f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n", file=sys.stderr)
    print(md)


if __name__ == "__main__":
    main()
