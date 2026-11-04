# -*- coding: utf-8 -*-
"""把 candidates.jsonl 切成便于人工/模型逐条判定的紧凑文本批次。

每批是一个 txt，每条占 2-5 行：
    0001|项目名|街道|地址
      A 链家名 户数 | location | 证据
      B ...

判定结果按 `编号 字母` 输出，例如 `0001 C`、`0002 X`（X = 都不对）。
"""

import argparse
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
OUT = os.path.join(ROOT, "raw_data", "lianjia")
LETTERS = "ABCDE"


def tier(c):
    """证据强度分档，用于决定给几个候选。"""
    ev = c["证据"]
    if "同门牌" in ev:
        return 1
    if "同路" in ev:
        return 2
    if c["名相似"] >= 0.6:
        return 3
    return 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=250)
    ap.add_argument("--top", type=int, default=3, help="每条最多给几个候选")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(os.path.join(OUT, "candidates.jsonl"), encoding="utf-8")]
    # 证据强的排前面，弱候选垫底
    rows.sort(key=lambda r: (tier(r["候选"][0]), -r["候选"][0]["分"]))

    d = os.path.join(OUT, "batches")
    os.makedirs(d, exist_ok=True)
    for old in os.listdir(d):
        if old.endswith(".txt"):      # 保留 *.verdict
            os.remove(os.path.join(d, old))

    # 编号 -> 项目号 对照，判定结果靠它回填
    mapping = {}
    n = 0
    for bi in range(0, len(rows), args.batch):
        chunk = rows[bi:bi + args.batch]
        lines = []
        for i, r in enumerate(chunk):
            idx = f"{bi + i:04d}"
            mapping[idx] = {"project_no": r["project_no"], "名称": r["名称"],
                            "候选": [c["lj_id"] for c in r["候选"][: args.top]]}
            lines.append(f"{idx}|{r['名称']}|{r['街道']}|{r['地址'] or '-'}")
            for j, c in enumerate(r["候选"][: args.top]):
                hh = c["户数"] if c["户数"] is not None else "-"
                lines.append(f"  {LETTERS[j]} {c['链家名']} {hh}户 | {c['链家地址']} | {c['证据']}")
        p = os.path.join(d, f"b{bi // args.batch:02d}.txt")
        open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        n += 1
    json.dump(mapping, open(os.path.join(d, "mapping.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    print(f"共 {len(rows)} 条，切 {n} 批，每批 {args.batch}，每条第 {args.top} 候选")
    print("目录", d)


if __name__ == "__main__":
    main()
