# -*- coding: utf-8 -*-
"""生成 AI 检索队列：把 beian_master 里未匹配的备案项目排成待查清单。

分级依据是可检索性——名字像正规小区的先查，院落/单栋/家属院后查，
因为这些在互联网上通常没有独立页面，硬查只会搜到同名的更大范围小区而填错户数。

输出 raw_data/ai_lookup/queue.jsonl（一行一条，顺序即建议查询顺序）。
"""
import csv
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "raw_data/exports/beian_master.csv")
OUT_DIR = os.path.join(ROOT, "raw_data/ai_lookup")
OUT = os.path.join(OUT_DIR, "queue.jsonl")

# 名字里出现这些词，基本可以断定是院落/单栋/单位家属楼，网查命中率极低
LOW = re.compile(r"号楼|号院|家属|胡同|条|巷|宿舍|平房|简易|临建|大院|排房")
# 名字里出现这些词，更像有独立页面的商品房小区
HIGH = re.compile(r"小区|花园|家园|苑|园|公寓|国际|大厦|新城|广场|城|府|湾|里|山庄|别墅")


def tier(name):
    n = name or ""
    if LOW.search(n):
        return "C"
    if len(n) >= 4 and HIGH.search(n):
        return "A"
    if len(n) < 4:
        return "C"
    return "B"


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    todo = [r for r in rows if r["匹配类别"].startswith("未匹配")]

    out = []
    for r in todo:
        out.append({
            "id": r["备案编号"],
            "name": r["备案项目名"],
            "district": r["区"],
            "street": r["街道"],
            "address": r["备案地址"],
            "fee_ba": r["居住类物业费"],       # 备案物业费，用于交叉验证
            "property": r["房屋性质"],
            "tier": tier(r["备案项目名"]),
            "cat": r["匹配类别"],
        })

    order = {"A": 0, "B": 1, "C": 2}
    # 区/街道为空的（那 147 条「备案区缺失」）排同级末尾——连区都没有，几乎无从检索
    out.sort(key=lambda x: (order[x["tier"]], not x["district"], x["district"],
                            not x["street"], x["street"], x["name"]))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for i, x in enumerate(out):
            x["seq"] = i
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    import collections
    c = collections.Counter(x["tier"] for x in out)
    print(f"队列已生成：{OUT}")
    print(f"共 {len(out)} 条")
    for k in "ABC":
        print(f"  {k} 类 {c[k]:>5}")


if __name__ == "__main__":
    main()
