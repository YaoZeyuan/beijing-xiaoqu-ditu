# -*- coding: utf-8 -*-
"""把待查队列切成若干批次文件，供并行检索使用。

并行时必须先切好文件再分发，否则多个执行体各自取「前 N 条未完成」会拿到同一批。

  python crawler/ai_lookup_make_batches.py --size 15 --count 6

输出 raw_data/ai_lookup/batches/batch_01.txt ... 每行一条：
  序号 | id | 区 | 小区名 | 街道 | 地址 | 备案物业费
"""
import argparse
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "raw_data/ai_lookup")
OUT = os.path.join(DIR, "batches")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=15, help="每批条数")
    ap.add_argument("--count", type=int, default=6, help="批数")
    ap.add_argument("--tier", default="", help="只取某级 A/B/C")
    a = ap.parse_args()

    queue = [json.loads(x) for x in open(os.path.join(DIR, "queue.jsonl"), encoding="utf-8") if x.strip()]
    done = set()
    p = os.path.join(DIR, "results.jsonl")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8", errors="replace"):
            if not line.strip():
                continue
            try:
                done.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                # 并发写入可能留下字节交错的残行，跳过即可
                continue

    pending = [x for x in queue if x["id"] not in done]
    if a.tier:
        pending = [x for x in pending if x["tier"] == a.tier]

    need = a.size * a.count
    if len(pending) < need:
        print(f"!! 剩余仅 {len(pending)} 条，不够切 {a.count} 批", file=sys.stderr)

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
                f.write(f"{j}\t{x['id']}\t{x['district'] or '?'}\t{x['name']}\t"
                        f"{x['street'] or '-'}\t{x['address'] or '-'}\t费={x['fee_ba'] or '-'}\n")
        made += 1

    print(f"已切 {made} 批，共 {min(need, len(pending))} 条 → {OUT}")
    print(f"剩余待查 {len(pending)}")


if __name__ == "__main__":
    main()
