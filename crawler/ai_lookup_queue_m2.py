# -*- coding: utf-8 -*-
"""第二轮 AI 检索队列：以「链家小区」为检索单元，覆盖多对一备案。

背景：2,402 条备案共用 863 个链家小区（多对一），这些链家小区的户数在
2018/2019 快照里全是空的，所以备案侧一条都没户数。第一轮队列只装了未匹配的
3,302 条，多对一从来没进过队列。

为什么按小区而不是按备案排队：863 个小区 ↔ 2,402 条备案，平均一对 2.8。
一个小区搜一次能同时回答「整小区多少户」，顺带（搜索页里常带分区信息）回答
「A区/C区各多少户」，比按备案拆开搜 2,402 次省 2/3 的搜索量。

输出 raw_data/ai_lookup/queue_m2.jsonl，一行一个小区：
  key=链家id，beians=[该小区下的备案…]
"""
import collections
import csv
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "raw_data/exports/beian_master.csv")
OUT_DIR = os.path.join(ROOT, "raw_data/ai_lookup")
OUT = os.path.join(OUT_DIR, "queue_m2.jsonl")

# 备案名里带这些 = 分区/分期/楼栋口径，整小区户数不能下移到它身上
PART = re.compile(r"[A-Za-z]区|期|号楼|号院|第.{1,2}区|地块|院$|楼$")
# 名字像不像有独立页面的正规小区
HIGH = re.compile(r"小区|花园|家园|苑|园|公寓|国际|大厦|新城|广场|城|府|湾|里|山庄|别墅")
LOW = re.compile(r"胡同|街$|巷|条$|号院|宿舍|平房|简易|临建|大院|排房|楼$")


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
    groups = collections.OrderedDict()
    for r in rows:
        if r["关联状态"] != "多对一":
            continue
        groups.setdefault(r["链家id"], []).append(r)

    out = []
    for lj, members in groups.items():
        head = members[0]
        # 小区级已有户数的不必再查（本轮 863 个全为空，留个保险）
        has_hh = any(m["户数2018"].strip() or m["户数2019"].strip() for m in members)
        beians = []
        for m in members:
            name = m["备案项目名"]
            beians.append({
                "id": m["备案编号"],
                "name": name,
                "fee": m["居住类物业费"],
                "addr": m["备案地址"],
                "prop": m["房屋性质"],
                "part": bool(PART.search(name)),
            })
        name = head["链家小区名"] or beians[0]["name"]
        out.append({
            "key": lj,
            "name": name,
            "district": head["区"],
            "street": head["街道"],
            "bizarea": head["商圈"],
            "address": head["链家地址"],
            "lianjia_hh": "" if not has_hh else head["户数2018"] or head["户数2019"],
            "n": len(beians),
            "n_part": sum(1 for b in beians if b["part"]),
            "tier": tier(name),
            "beians": beians,
        })

    order = {"A": 0, "B": 1, "C": 2}
    out.sort(key=lambda x: (order[x["tier"]], not x["district"], x["district"],
                            not x["street"], x["street"], -x["n"], x["name"]))
    for i, x in enumerate(out):
        x["seq"] = i

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for x in out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    c = collections.Counter(x["tier"] for x in out)
    print(f"队列已生成：{OUT}")
    print(f"小区 {len(out)} 个，覆盖备案 {sum(x['n'] for x in out)} 条"
          f"（其中带分区标记 {sum(x['n_part'] for x in out)} 条）")
    for k in "ABC":
        n = c[k]
        print(f"  {k} 类 {n:>4} 个小区 / {sum(x['n'] for x in out if x['tier'] == k):>5} 条备案")
    print(f"  有分区标记备案的小区 {sum(1 for x in out if x['n_part'])} 个")


if __name__ == "__main__":
    main()
