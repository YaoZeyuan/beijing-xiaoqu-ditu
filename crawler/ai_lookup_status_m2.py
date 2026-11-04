# -*- coding: utf-8 -*-
"""第二轮（多对一小区）检索进度。

  python crawler/ai_lookup_status_m2.py
  python crawler/ai_lookup_status_m2.py -n 20
"""
import argparse
import collections
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "raw_data/ai_lookup")


def load():
    qp = os.path.join(DIR, "queue_m2.jsonl")
    queue = [json.loads(x) for x in open(qp, encoding="utf-8") if x.strip()] \
        if os.path.exists(qp) else []
    done = {}
    dup = 0
    rp = os.path.join(DIR, "results_m2.jsonl")
    if os.path.exists(rp):
        for line in open(rp, encoding="utf-8", errors="replace"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r["key"] in done:
                dup += 1
            done[r["key"]] = r
    return queue, done, dup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=0)
    a = ap.parse_args()

    queue, done, dup = load()
    if not queue:
        sys.exit(f"队列不存在，先跑 python crawler/ai_lookup_queue_m2.py")

    total = len(queue)
    n_done = sum(1 for x in queue if x["key"] in done)
    pending = [x for x in queue if x["key"] not in done]
    print(f"小区 {total}   已查 {n_done}（{n_done/total*100:.1f}%）   剩 {len(pending)}")
    if dup:
        print(f"（含 {dup} 条修正记录，同 key 以最后一次为准）")
    print()

    st = collections.Counter(done[x["key"]]["status"] for x in queue if x["key"] in done)
    if st:
        for k, v in st.most_common():
            print(f"  {k:<12}{v:>5}  {v/max(n_done,1)*100:5.1f}%")
        cf = collections.Counter(done[x["key"]].get("confidence") for x in queue if x["key"] in done)
        print("  置信度：", dict(cf))
        # 覆盖到多少条备案
        cov_beian = {}
        for x in queue:
            r = done.get(x["key"])
            if not r:
                continue
            for b in x["beians"]:
                cov_beian[b["id"]] = r
        whole = sum(1 for r in cov_beian.values() if r.get("households") is not None)
        inparts = sum(1 for r in cov_beian.values() for _ in (r.get("parts") or {}))
        share = sum(len(r.get("share") or []) for r in cov_beian.values())
        print(f"  整小区户数 {whole} 个小区   分区户数 {inparts} 条备案   可下移共享 {share} 条")
        print()

    print("分级进度：")
    for t in "ABC":
        sub = [x for x in queue if x["tier"] == t]
        d = sum(1 for x in sub if x["key"] in done)
        print(f"  {t} 类  {d:>4}/{len(sub):<4}")
    print()
    print(f"涉及备案：{sum(x['n'] for x in queue)} 条，"
          f"已查小区的备案 {sum(x['n'] for x in queue if x['key'] in done)} 条")

    if a.n and pending:
        print(f"\n接下来 {min(a.n, len(pending))} 个：")
        for x in pending[:a.n]:
            print(f"  [{x['tier']}] {x['key']}  {x['district']} {x['name']}  ({x['street']})  "
                  f"备案{x['n']}条/分区{x['n_part']}")


if __name__ == "__main__":
    main()
