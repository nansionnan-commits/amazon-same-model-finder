#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
找同款的辅助工具：核心词提取 + 价格对比 + 报告生成

用法：
  # 1. 从标题提核心词
  python same_model_helper.py --title "Reusable Self Sealing Potato and Onion Storage Bags (3 Pack)"

  # 2. 价格对比（喂前台搜索结果 JSON）
  python same_model_helper.py --compare search.json --our-price 25.99

  # 3. 生成报告骨架
  python same_model_helper.py --report search.json --our-sku CHT20260822149 --out report.md
"""
import argparse
import json
import os
import re
import statistics

# 需要从标题里剥掉的噪声
NOISE_WORDS = {
    # 形容词
    "premium", "upgraded", "new", "2026", "2027", "2025", "best", "professional",
    "reusable", "washable", "breathable", "durable", "portable", "foldable",
    "adjustable", "multipurpose", "versatile", "eco-friendly", "eco", "friendly",
    "large", "small", "mini", "extra", "super", "ultra", "heavy", "duty",
    "soft", "warm", "cool", "cute", "funny", "novelty", "creative", "unique",
    "modern", "classic", "vintage", "boho", "farmhouse", "rustic",
    "self", "sealing", "light", "blocking", "proof", "resistant", "free",
    "non", "slip", "stick", "easy", "clean", "quick", "fast", "instant",
    # 数量/包装
    "pack", "pcs", "piece", "pieces", "set", "count", "bundle", "kit",
    # 通用词
    "for", "with", "and", "the", "a", "an", "of", "to", "in", "on",
    "your", "home", "kitchen", "indoor", "outdoor", "daily", "use",
}

# 品类核心词（保留这些）
CATEGORY_NOUNS = {
    "bag", "bags", "pouch", "sack", "container", "box", "basket", "bin",
    "holder", "rack", "organizer", "stand", "shelf", "hanger", "hook",
    "cup", "mug", "glass", "bottle", "jar", "can", "tumbler",
    "juicer", "squeezer", "press", "grinder", "cutter", "slicer", "peeler",
    "sprayer", "bottle", "dispenser", "pump",
    "glove", "gloves", "mitten", "mittens", "sock", "socks", "slipper", "slippers",
    "hat", "cap", "scarf", "earmuff", "earmuffs", "headband",
    "boot", "boots", "shoe", "shoes", "sneaker", "sneakers",
    "bed", "house", "cave", "tunnel", "mat", "pad", "cushion",
    "toy", "kit", "set", "tool",
    "cover", "shield", "guard", "protector", "wrap",
    "tie", "ties", "strap", "straps", "clip", "clips", "hook", "hooks",
    "wreath", "garland", "ornament", "decoration",
    "costume", "accessory", "accessories",
}


def extract_keyword(title):
    """
    从标题提取核心词。
    策略：保留品类名词 + 它前面的修饰名词（材质/对象/功能），去掉噪声词。
    """
    if not title:
        return ""
    # 去掉括号内容（通常是规格）
    t = re.sub(r"\([^)]*\)", " ", title)
    t = re.sub(r"（[^）]*）", " ", t)
    # 去掉逗号后的部分（通常是补充说明/规格）
    t = t.split(",")[0]
    # 分词（保留原形，后面按原形判断单复数）
    raw = re.findall(r"[a-zA-Z]+", t)

    kept_raw = []
    for w in raw:
        lw = w.lower()
        if lw in NOISE_WORDS or len(lw) <= 2:
            continue
        kept_raw.append((lw, w))

    # 找品类名词：从后往前找（最后一个通常是主名词，如 slipper boots → boots）
    noun_idx = None
    for i in range(len(kept_raw) - 1, -1, -1):
        lw = kept_raw[i][0]
        if lw in CATEGORY_NOUNS:
            noun_idx = i
            break
        if lw.endswith("s") and lw[:-1] in CATEGORY_NOUNS:
            noun_idx = i
            break

    if noun_idx is None:
        return " ".join(o for _, o in kept_raw[:4])

    start = max(0, noun_idx - 3)
    # 用原形（保留复数 s）
    return " ".join(o.lower() for _, o in kept_raw[start:noun_idx + 1])


def parse_price(p):
    """从 '19.99' 或 '$19.99' 或 null 里拿数"""
    if p is None:
        return None
    if isinstance(p, (int, float)):
        return float(p)
    m = re.search(r"([\d.]+)", str(p))
    return float(m.group(1)) if m else None


def parse_shipping(delivery):
    """从 'delivery: $7.99 delivery Nov 2 - 10' 里提运费；FREE 返回 0"""
    if not delivery:
        return None
    s = str(delivery)
    if re.search(r"\bfree\b", s, re.I):
        return 0.0
    m = re.search(r"\$\s*([\d.]+)", s)
    return float(m.group(1)) if m else None


def compare_prices(products, our_price):
    """价格对比：基于前台搜索结果"""
    rows = []
    for p in products:
        price = parse_price(p.get("extractedPrice") or p.get("price"))
        ship = parse_shipping(p.get("delivery"))
        if price is None:
            continue
        total = price + (ship if ship is not None else 0)
        rows.append({
            "asin": p.get("asin"),
            "position": p.get("position"),
            "title": (p.get("title") or "")[:50],
            "price": price,
            "shipping": ship,
            "total": total,
            "sponsored": p.get("sponsored"),
        })

    if not rows:
        return {"error": "没有可用价格数据"}

    totals = [r["total"] for r in rows]
    med = statistics.median(totals)
    our = float(our_price)
    diff = our - med
    pct = diff / med * 100 if med else 0

    if pct > 15:
        verdict = "🔴 严重偏高，转化必受影响"
    elif pct > 5:
        verdict = "⚠️ 偏高，需要理由支撑（材料/配件/内容更强）"
    elif pct >= -5:
        verdict = "✅ 正常区间"
    else:
        verdict = "⚠️ 偏低，有涨价空间"

    return {
        "n": len(rows),
        "min": min(totals),
        "max": max(totals),
        "median": round(med, 2),
        "mean": round(statistics.mean(totals), 2),
        "ours": round(our, 2),
        "diff": round(diff, 2),
        "pct": round(pct, 1),
        "verdict": verdict,
        "rows": sorted(rows, key=lambda x: x["total"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", help="从标题提核心词")
    ap.add_argument("--compare", help="前台搜索结果 JSON")
    ap.add_argument("--our-price", type=float, help="我们的总价（含运费）")
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.title:
        kw = extract_keyword(args.title)
        print(f"标题：{args.title}")
        print(f"核心词：**{kw}**")
        return

    if args.compare and args.our_price:
        data = json.load(open(args.compare, encoding="utf-8"))
        products = data.get("products") or data
        r = compare_prices(products, args.our_price)
        if "error" in r:
            print(r["error"])
            return
        print(f"样本 {r['n']} 个")
        print(f"价格区间：${r['min']} – ${r['max']}")
        print(f"中位数：${r['median']}")
        print(f"我们：${r['ours']}")
        print(f"差异：${r['diff']:+.2f}（{r['pct']:+.1f}%）")
        print(f"结论：{r['verdict']}")
        print()
        print(f"{'ASIN':<14}{'位置':<6}{'商品价':<9}{'运费':<8}{'总价':<9}标题")
        print("-" * 100)
        for x in r["rows"]:
            ship = f"${x['shipping']:.2f}" if x["shipping"] is not None else "-"
            print(f"{x['asin']:<14}{str(x['position'] or ''):<6}${x['price']:<8.2f}"
                  f"{ship:<8}${x['total']:<8.2f}{x['title']}")
        return

    print(__doc__)


if __name__ == "__main__":
    main()
