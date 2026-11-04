# -*- coding: utf-8 -*-
"""为未匹配的物业备案项目召回链家候选小区，供模型逐批判定。

程序规则能处理「名字几乎一样」和「门牌完全一致」，但处理不了
商品名 vs 登记名（宣海家园 / 今家园）、一个链家条目聚合多个备案项目
这类语义差异。这里只负责把候选缩到 3-6 个并附证据，判定交给模型。

用法:
    python gen_candidates.py            # 生成候选并打印统计
    python gen_candidates.py --batch 300  # 同时切分成批文件
"""

import argparse
import collections
import csv
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import match_lianjia as M

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
OUT = os.path.join(ROOT, "raw_data", "lianjia")
PROJECTS = os.path.join(BASE, "data", "projects.json")

ROAD_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:路|街|大街|胡同|巷|条|道|里))")


def road_num(addr):
    """从地址里抽「路名 + 门牌号」，抽不到返回 (路名, '')。"""
    a = re.sub(r"^北京市?", "", addr or "")
    a = re.sub(r"^[\u4e00-\u9fa5]{2,4}区", "", a)
    a = re.sub(r"\s+", "", a)
    m = re.search(ROAD_RE.pattern + r"([甲乙丙丁]?\d+)\s*(?:号|院)", a)
    if m:
        return m.group(1), m.group(2)
    m = ROAD_RE.search(a)
    return (m.group(1), "") if m else ("", "")


def lcs_len(a, b):
    """最长公共子串长度，用来衡量两个名字共享多少连续字。"""
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=0, help="切分批次，每批多少条")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    lj = M.load_lj(os.path.join(OUT, "baseinfo_201902.csv"))
    proj = {p["project_no"]: p for p in json.load(open(PROJECTS, encoding="utf-8"))}
    matched = list(csv.DictReader(open(os.path.join(OUT, "matched.csv"), encoding="utf-8-sig")))
    unmatched = [r for r in matched if not r["lj_community_id"]]

    # 链家小区按区归并，附带 location 里的路名集合
    by_d = collections.defaultdict(list)
    for r in lj:
        d = M.lj_district(r)
        roads = {road_num(p)[0] for p in M.loc_parts(r["location"])}
        roads.discard("")
        by_d[d].append({
            "id": r["community_id"],
            "name": r["community_name"],
            "loc": r["location"],
            "hh": M.hh(r["house_amount"]),
            "bd": M.bd(r["building_amount"]),
            "roads": roads,
            "norm": M.norm(r["community_name"]),
        })

    # 已被占用的链家小区：候选命中时要提示「已有 N 个备案项目指向它」
    used = collections.Counter(r["lj_community_id"] for r in matched if r["lj_community_id"])

    out = []
    stat = collections.Counter()
    for r in unmatched:
        p = proj.get(r["project_no"], {})
        d = M.canon_district(r["区"]) or M.canon_district(p.get("项目所在区") or "")
        name = M.norm(r["项目名称"] or "")
        addr = p.get("项目地址") or ""
        rd, num = road_num(addr)
        if not name and not rd:
            stat["无名称无地址"] += 1
            continue

        cands = []
        for c in by_d.get(d, []):
            ev = []
            score = 0
            # 名称共享连续字
            l = lcs_len(name, c["norm"])
            if l >= 2:
                score += l * 2
                ev.append(f"共{l}字")
            # 路名
            if rd and rd in c["roads"]:
                score += 6
                ev.append(f"同路:{rd}")
            # 门牌号
            if rd and num and any(rd in p_ and num in p_ for p_ in M.loc_parts(c["loc"])):
                score += 8
                ev.append(f"同门牌:{rd}{num}")
            # 商圈与街道吻合
            if M.street_score(r["街道"], {"hier4": c["name"], "location": c["loc"]}) > 0:
                score += 2
            else:
                biz = ""
                if rd and rd in c["loc"]:
                    score += 1
            if score < 4:
                continue
            ratio = difflib.SequenceMatcher(None, name, c["norm"]).ratio()
            score += ratio * 5
            cands.append((round(score, 1), round(ratio, 2), c, ev))

        if not cands:
            stat["无候选"] += 1
            continue
        cands.sort(key=lambda x: -x[0])
        # 同分只留前 top 个，并且要求与第一名差距不过大
        cands = cands[: args.top]
        stat["有候选"] += 1
        out.append({
            "project_no": r["project_no"],
            "名称": r["项目名称"],
            "区": r["区"],
            "街道": r["街道"],
            "地址": p.get("项目地址") or "",
            "候选": [{
                "lj_id": c["id"], "链家名": c["name"], "链家地址": c["loc"],
                "户数": c["hh"], "楼栋": c["bd"],
                "已占用": used.get(c["id"], 0),
                "分": s, "名相似": rt, "证据": "；".join(e),
            } for s, rt, c, e in cands],
        })

    path = os.path.join(OUT, "candidates.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"未匹配 {len(unmatched)}，有候选 {stat['有候选']}，无候选 {stat['无候选']}，"
          f"无名称无地址 {stat['无名称无地址']}")
    dist = collections.Counter(len(r["候选"]) for r in out)
    print("每条候选数分布", sorted(dist.items()))
    print(f"写入 {path}")

    if args.batch:
        d = os.path.join(OUT, "batches")
        os.makedirs(d, exist_ok=True)
        for i in range(0, len(out), args.batch):
            chunk = out[i:i + args.batch]
            with open(os.path.join(d, f"batch_{i // args.batch:03d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(chunk, f, ensure_ascii=False, indent=1)
        print(f"切分 {(len(out) + args.batch - 1) // args.batch} 批，每批 {args.batch}")


if __name__ == "__main__":
    main()
