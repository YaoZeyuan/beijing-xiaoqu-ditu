# -*- coding: utf-8 -*-
"""把 AI 检索结果合并回 beian_master.csv。

合并逻辑在 ai_lookup_merge.py（export_dataset.py 也共用），本脚本只负责
读写 raw_data/exports/beian_master.csv。可反复运行（幂等）。
"""
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_lookup_merge as M  # noqa: E402
import ai_lookup_merge_m2 as M2  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "raw_data/exports/beian_master.csv")


def main():
    res = M.load_results()
    if not res:
        sys.exit("没有检索结果，先跑 ai_lookup_record.py")

    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    cols = list(rows[0].keys())
    for c, _ in M.AI_COLS:
        if c not in cols:
            cols.insert(cols.index("备注"), c)

    stat = M.merge_rows(rows, res)
    stat2 = M2.merge_rows(rows)

    tmp = CSV + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # 写盘前硬校验：第二行不能等于表头
    with open(tmp, encoding="utf-8-sig") as f:
        h1 = f.readline().strip()
        h2 = f.readline().strip()
    if h1 == h2:
        sys.exit("!! 写出异常：第二行与表头相同")

    os.replace(tmp, CSV)

    print(f"已合并 {len(res)} 条检索结果进 {os.path.basename(CSV)}")
    for k, v in stat.most_common():
        print(f"  {k:<8}{v:>5}")
    print(f"\n多对一小区补查（第二轮）：")
    for k, v in stat2.most_common():
        print(f"  {k:<12}{v:>5}")
    print(f"\n列数 {len(cols)}，行数 {len(rows)}")


if __name__ == "__main__":
    main()
