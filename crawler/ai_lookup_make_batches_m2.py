# -*- coding: utf-8 -*-
"""把第二轮队列切成批次文件，供并行检索使用。

  python crawler/ai_lookup_make_batches_m2.py --size 30 --count 6

输出 raw_data/ai_lookup/batches_m2/batch_01.txt … 每批按「小区」成块：

  ## 1  [A] lj=1112995421285636  保利花园  (密云区/鼓楼街道 · 商圈:密云 · 阳光街390号院)
     链家户数：空   备案 2 条（带分区标记 2 条）
     - B2DE5B01… | 保利花园B区 | 费=2.5 | 密云区宾阳村
     - 9A5B…     | 保利花园C区 | 费=2.5 | 密云区宾阳村
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "raw_data/ai_lookup")
OUT = os.path.join(DIR, "batches_m2")


def load_done():
    done = set()
    p = os.path.join(DIR, "results_m2.jsonl")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8", errors="replace"):
            if not line.strip():
                continue
            try:
                done.add(json.loads(line)["key"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=30, help="每批小区数")
    ap.add_argument("--count", type=int, default=6, help="批数")
    ap.add_argument("--tier", default="", help="只取某级 A/B/C")
    a = ap.parse_args()

    queue = [json.loads(x) for x in open(os.path.join(DIR, "queue_m2.jsonl"), encoding="utf-8") if x.strip()]
    done = load_done()
    pending = [x for x in queue if x["key"] not in done]
    if a.tier:
        pending = [x for x in pending if x["tier"] == a.tier]

    need = a.size * a.count
    if len(pending) < need:
        print(f"!! 剩余仅 {len(pending)} 个小区，不够切 {a.count} 批", file=sys.stderr)

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.startswith("batch_"):
            os.remove(os.path.join(OUT, f))

    made = 0
    for i in range(a.count):
        chunk = pending[i * a.size:(i + 1) * a.size]
        if not chunk:
            break
        path = os.path.join(OUT, f"batch_{i+1:02d}.txt")
        with open(path, "w", encoding="utf-8") as f:
            for j, x in enumerate(chunk, 1):
                loc = "/".join(y for y in (x["district"] or "?", x["street"] or "-") if y)
                extra = " · ".join(y for y in (
                    f"商圈:{x['bizarea']}" if x["bizarea"] else "",
                    x["address"] or "") if y)
                f.write(f"## {j}  [{x['tier']}] lj={x['key']}  {x['name']}"
                        f"  ({loc}{' · ' + extra if extra else ''})\n")
                f.write(f"   链家户数：{x['lianjia_hh'] or '空'}"
                        f"   备案 {x['n']} 条（带分区标记 {x['n_part']} 条）\n")
                for b in x["beians"]:
                    f.write(f"   - {b['id']} | {b['name']}"
                            f" | 费={b['fee'] or '-'}"
                            f" | {b['addr'] or '-'}"
                            f"{' | [分区]' if b['part'] else ''}\n")
                f.write("\n")
        made += 1

    print(f"已切 {made} 批，共 {min(need, len(pending))} 个小区 → {OUT}")
    print(f"剩余待查 {len(pending)} 个小区")


if __name__ == "__main__":
    main()
