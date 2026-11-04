# -*- coding: utf-8 -*-
"""取出接下来一批待查条目，供批量检索使用（断点续传的一环）。

  python crawler/ai_lookup_next.py --size 25          # 取前 25 条未查的
  python crawler/ai_lookup_next.py --size 25 --skip 0 # 从第 0 条待查开始（默认）

输出为便于阅读的纯文本，每行一条：序号 | id | 区 | 名 | 街道 | 地址 | 备案物业费
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "raw_data/ai_lookup")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=25)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--tier", default="", help="只取某一级 A/B/C")
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
    batch = pending[a.skip:a.skip + a.size]

    print(f"# 待查总数 {len(pending)}，本批 {len(batch)} 条\n")
    for i, x in enumerate(batch, 1):
        addr = x["address"] or "-"
        print(f"{i}\t{x['id']}\t{x['district'] or '?'}\t{x['name']}\t"
              f"{x['street'] or '-'}\t{addr}\t费={x['fee_ba'] or '-'}")


if __name__ == "__main__":
    main()
