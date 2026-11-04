# -*- coding: utf-8 -*-
"""把逐批判定结果（batches/*.verdict）汇总成 project_no -> 链家小区 的映射。

verdict 文件格式：每行 `编号 字母`，字母对应候选序号（A/B/C...），
不写或用 X 表示「候选都不对」。缺省的编号同样视为 X。

用法:
    python apply_verdicts.py            # 汇总已完成的批次
    python apply_verdicts.py --merge    # 同时写进 matched.csv 的 llm_* 列
"""

import argparse
import collections
import csv
import glob
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
OUT = os.path.join(ROOT, "raw_data", "lianjia")
BDIR = os.path.join(OUT, "batches")
LETTERS = "ABCDE"

# 判定后的硬性校验：候选不满足就直接否决，避免把错误户数带进分析。
# 1) 户数极少（1~5）的条目多是单栋/空壳，不是小区规模
# 2) location 含 3 个以上门牌时，该条目是整片聚合，户数是合计值
# 3) 商业地产（大厦/商场/广场）对到纯住宅，口径不一致
BIZ_RE = re.compile(r"(大厦|商场|购物|写字楼|办公|广场|中心)")
RES_RE = re.compile(r"(公寓|住宅|宿舍|小区|家园|苑|园|里|院|村|镇)")
MIN_HH = 6
MAX_ADDR = 2


def verify(lj_row):
    """返回 (是否通过, 原因)。"""
    if not lj_row:
        return False, "no_lj_row"
    h = M.hh(lj_row.get("house_amount"))
    if h is not None and h < MIN_HH:
        return False, "tiny_households"
    if len(M.loc_parts(lj_row.get("location"))) > MAX_ADDR:
        return False, "aggregate_address"
    return True, ""


def check_biz(proj_name, lj_name):
    """商业地产对住宅：备案名是写字楼/商场，链家条目是住宅，不能算。"""
    if BIZ_RE.search(proj_name or "") and not RES_RE.search(proj_name or ""):
        if RES_RE.search(lj_name or "") and not BIZ_RE.search(lj_name or ""):
            return False
    return True


def load_verdicts(lj):
    mapping = json.load(open(os.path.join(BDIR, "mapping.json"), encoding="utf-8"))
    picked, rejected = {}, {}
    done_batches = []
    for p in sorted(glob.glob(os.path.join(BDIR, "*.verdict"))):
        done_batches.append(os.path.basename(p).split(".")[0])
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            idx, letter = parts[0], parts[1].upper()
            m = mapping.get(idx)
            if not m:
                continue
            if letter == "X":
                rejected[m["project_no"]] = "judged_no"
                continue
            j = LETTERS.find(letter)
            if j < 0 or j >= len(m["候选"]):
                continue
            lid = m["候选"][j]
            row = lj.get(lid, {})
            ok, why = verify(row)
            if not ok:
                rejected[m["project_no"]] = why
                continue
            if not check_biz(m["名称"], row.get("community_name")):
                rejected[m["project_no"]] = "biz_vs_residential"
                continue
            picked[m["project_no"]] = {"lj_id": lid, "名称": m["名称"],
                                       "批次": os.path.basename(p).split(".")[0]}
    # 全批次跑完后仍未出现的编号：视为未判定（不是"判定无匹配"），单独标注
    for idx, m in mapping.items():
        pno = m["project_no"]
        if pno not in picked and pno not in rejected:
            rejected[pno] = "unjudged"
    return mapping, picked, rejected, done_batches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()

    lj = {r["community_id"]: r for r in M.load_lj(os.path.join(OUT, "baseinfo_201902.csv"))}
    mapping, picked, rejected, batches = load_verdicts(lj)
    total = len(mapping)
    print(f"批次 {len(batches)}/{len(glob.glob(os.path.join(BDIR, 'b*.txt')))}"
          f"（{' '.join(batches)}）")
    print(f"已判定 {len(picked) + len(rejected)}/{total}，"
          f"匹配 {len(picked)}，判定无匹配 {len(rejected)}")
    if picked:
        print(f"匹配率 {len(picked) / (len(picked) + len(rejected)) * 100:.1f}%")

    with open(os.path.join(OUT, "verdicts.jsonl"), "w", encoding="utf-8") as f:
        for pno, v in picked.items():
            f.write(json.dumps({"project_no": pno, **v}, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, "verdicts_rejected.jsonl"), "w", encoding="utf-8") as f:
        for pno in sorted(rejected):
            f.write(json.dumps({"project_no": pno}, ensure_ascii=False) + "\n")

    if not args.merge:
        return
    path = os.path.join(OUT, "matched.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    n = 0
    for r in rows:
        v = picked.get(r["project_no"])
        if not v or r["lj_community_id"]:
            continue
        c = lj.get(v["lj_id"], {})
        r["lj_community_id"] = v["lj_id"]
        r["匹配"] = "llm_judge"
        r["置信度"] = "medium"          # 语义匹配，人工/模型判定，非字符串等价
        r["link_households"] = M.hh(c.get("house_amount"))
        r["lj_name"] = c.get("community_name")
        r["lj_buildings"] = M.bd(c.get("building_amount"))
        r["lj_address"] = c.get("location")
        r["lj_biz_area"] = (c.get("hier4") or "").replace("小区", "")
        r["lng"], r["lat"] = c.get("longitude"), c.get("latitude")
        r["lj_age"] = c.get("age")
        r["lj_fee"] = c.get("management_fee")
        r["lj_property_co"] = c.get("management_co")
        r["lj_unit_price_2019"] = c.get("unit_price")
        r["lj_url"] = c.get("url")
        r["链家地址数"] = len(M.loc_parts(c.get("location")))
        n += 1
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    try:
        os.replace(tmp, path)
    except PermissionError:
        # 文件被 Excel / 编辑器占用，退而写到同目录的新文件
        alt = path.replace(".csv", "_llm.csv")
        os.replace(tmp, alt)
        print(f"提示: {os.path.basename(path)} 被占用，结果写入 {os.path.basename(alt)}")
    print(f"回填 matched.csv {n} 条")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, BASE)
    import match_lianjia as M
    main()
