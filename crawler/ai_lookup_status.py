# -*- coding: utf-8 -*-
"""查看 AI 检索进度，并列出接下来该查哪些（断点续传用）。

  python crawler/ai_lookup_status.py          # 进度总览
  python crawler/ai_lookup_status.py -n 20    # 顺便打印下 20 条待查
"""
import argparse
import collections
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "raw_data/ai_lookup")
QUEUE = os.path.join(DIR, "queue.jsonl")
RESULTS = os.path.join(DIR, "results.jsonl")


def load():
    """读队列与结果。

    results.jsonl 采用追加写（并发安全），同一 id 可能有多行——
    写盘命令每条只应执行一次，但子代理事后修正时会再写一次，
    覆盖语义由「后写入的为准」实现。
    """
    queue = [json.loads(x) for x in open(QUEUE, encoding="utf-8") if x.strip()] \
        if os.path.exists(QUEUE) else []
    done = {}
    dup = 0
    if os.path.exists(RESULTS):
        for line in open(RESULTS, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                # 并发写入可能留下字节交错的残行，跳过即可
                continue
            if r["id"] in done:
                dup += 1
            done[r["id"]] = r
    return queue, done, dup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=0, help="打印接下来 n 条待查")
    a = ap.parse_args()

    queue, done, dup = load()
    if not queue:
        sys.exit(f"队列不存在：{QUEUE}\n先跑 python crawler/ai_lookup_queue.py")

    total = len(queue)
    n_done = sum(1 for x in queue if x["id"] in done)
    pending = [x for x in queue if x["id"] not in done]

    print(f"总待查 {total}   已完成 {n_done}（{n_done/total*100:.1f}%）   剩 {len(pending)}")
    if dup:
        print(f"（结果文件含 {dup} 条修正记录，同 id 以最后一次为准）")
    print()

    st = collections.Counter(done[x["id"]]["status"] for x in queue if x["id"] in done)
    if st:
        print("结果分布：")
        for k, v in st.most_common():
            print(f"  {k:<12}{v:>5}  {v/max(n_done,1)*100:5.1f}%")
        cf = collections.Counter(done[x["id"]]["confidence"] for x in queue if x["id"] in done)
        print("  置信度：", dict(cf))
        with_hh = sum(1 for x in queue if x["id"] in done and done[x["id"]]["households"])
        with_fee = sum(1 for x in queue if x["id"] in done and done[x["id"]]["fee"])
        print(f"  补到户数 {with_hh}   补到物业费 {with_fee}")
        print()

    # 分级进度
    print("分级进度：")
    for t in "ABC":
        sub = [x for x in queue if x["tier"] == t]
        d = sum(1 for x in sub if x["id"] in done)
        print(f"  {t} 类  {d:>5}/{len(sub):<5}")
    print()

    if a.n and pending:
        print(f"接下来 {min(a.n, len(pending))} 条：")
        for x in pending[:a.n]:
            print(f"  [{x['tier']}] {x['id']}  {x['district']} {x['name']}  "
                  f"({x['street']}) 费={x['fee_ba'] or '-'}")


if __name__ == "__main__":
    main()
