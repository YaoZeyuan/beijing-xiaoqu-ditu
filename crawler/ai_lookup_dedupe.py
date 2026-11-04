# -*- coding: utf-8 -*-
"""把 results.jsonl 里同一 id 的多行合并成一行（保留最后一条）。

早期版本的 ai_lookup_record.py 是纯追加，重切批次时上一批仍在跑，
导致同一个 id 出现多行。record.py 已改为覆盖写入，本脚本用于
清理存量文件里已经产生的重复。

  python crawler/ai_lookup_dedupe.py          # 报告将要合并的重复
  python crawler/ai_lookup_dedupe.py --apply  # 实际写回
"""
import argparse
import collections
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "raw_data/ai_lookup/results.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写回；缺省只报告")
    a = ap.parse_args()

    if not os.path.exists(RESULTS):
        sys.exit(f"结果文件不存在：{RESULTS}")

    recs, order = {}, []
    raw = []
    for line in open(RESULTS, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw.append(r)
        if r["id"] not in recs:
            order.append(r["id"])
        recs[r["id"]] = r

    c = collections.Counter(r["id"] for r in raw)
    dups = {k: v for k, v in c.items() if v > 1}
    if not dups:
        print("无重复，无需处理。")
        print(f"共 {len(order)} 条记录")
        return

    qmap = {}
    qp = os.path.join(ROOT, "raw_data/ai_lookup/queue.jsonl")
    if os.path.exists(qp):
        for line in open(qp, encoding="utf-8"):
            if line.strip():
                x = json.loads(line)
                qmap[x["id"]] = x

    print(f"总行数 {len(raw)}，唯一 id {len(order)}，重复 id {len(dups)}")
    print()
    for rid, n in dups.items():
        same = [r for r in raw if r["id"] == rid]
        first, last = same[0], same[-1]
        name = qmap.get(rid, {}).get("name", "?")
        flag = "内容一致" if (first.get("households"), first.get("fee"), first.get("status")) == \
            (last.get("households"), last.get("fee"), last.get("status")) else "有差异 → 保留后一条"
        print(f"{name}  {rid}  ×{n}   {flag}")
        print(f"   保留：{last['status']} 户={last.get('households')} 费={last.get('fee')} "
              f"conf={last.get('confidence')}")
        print(f"   丢弃：{first['status']} 户={first.get('households')} 费={first.get('fee')}")

    if not a.apply:
        print("\n（未写回，加 --apply 执行）")
        return

    tmp = RESULTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for rid in order:
            f.write(json.dumps(recs[rid], ensure_ascii=False) + "\n")
    os.replace(tmp, RESULTS)
    print(f"\n已写回：{len(order)} 行（原 {len(raw)} 行）")


if __name__ == "__main__":
    main()
