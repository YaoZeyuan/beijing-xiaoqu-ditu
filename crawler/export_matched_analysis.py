# -*- coding: utf-8 -*-
"""导出「分析就绪版」CSV：把文本字段转成可直接算描述统计的数值/类别列。

一行 = 一个备案项目（7,194 行），保留链家小区id，需要小区级时自行 groupby。
缺失值一律留空（读进 pandas 即 NaN），不填 0，避免污染均值。
输出：raw_data/exports/matched_analysis.csv
"""
import csv
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

SRC = "raw_data/lianjia/xiaoqu_db.json"
OUT = "raw_data/exports/matched_analysis.csv"

PLACEHOLDER = {"暂无信息", "暂无", "无", "-", "—", "/"}


def fee_range(s):
    """'2.05至5.5元/平米/月' -> (2.05, 5.5)；'2.5元/平米/月' -> (2.5, 2.5)。"""
    s = (s or "").strip()
    if not s or s in PLACEHOLDER:
        return None, None
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums:
        return None, None
    vals = [float(x) for x in nums[:2]]
    lo = vals[0]
    hi = vals[1] if len(vals) > 1 else vals[0]
    return lo, hi


def year(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def money(v):
    s = str(v or "").strip()
    if not s or s in PLACEHOLDER:
        return None
    if s.startswith("."):
        s = "0" + s
    elif s.startswith("-."):
        s = "-0" + s[1:]
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def numf(v):
    s = str(v if v is not None else "").strip()
    if not s or s in PLACEHOLDER:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def txt(v):
    s = str(v if v is not None else "").strip()
    return "" if s in PLACEHOLDER else s


def cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def main():
    db = json.load(open(SRC, encoding="utf-8"))
    rows = db["小区库"]
    share = {}
    for r in rows:
        share[r["链家小区id"]] = share.get(r["链家小区id"], 0) + 1

    out = []
    for r in rows:
        det = r.get("物业费明细") or []
        lo, hi = fee_range(r.get("物业费"))
        y_lj = year(r.get("建成年代"))
        y_ba = year(r.get("备案建成年代"))
        hh = numf(r.get("户数"))
        bl = numf(r.get("楼栋数"))
        props = [p for p in str(r.get("房屋性质") or "").split("|") if p]
        income = money(r.get("共有部分经营收入"))
        spend = money(r.get("共有部分经营支出"))
        balance = money(r.get("共有部分经营余额"))
        price = numf(r.get("链家单价2019"))
        fee_res = numf(r.get("居住类物业费"))
        ye_n = numf(r.get("业委会人数"))
        agg = 1 if r.get("链家为聚合页") else 0

        # 只打标记，不删数据；用不用由分析者决定
        flags = []
        if hh is not None and (hh < 6 or hh > 20000):
            flags.append("户数异常")
        if fee_res is not None and fee_res > 50:
            flags.append("备案物业费异常")
        if ye_n is not None and ye_n > 30:
            flags.append("业委会人数异常")
        if any(abs(x) > 100000 for x in (income, spend, balance) if x is not None):
            flags.append("公共收益金额异常")
        if any(x is not None and x < 0 for x in (income, spend, balance)):
            flags.append("公共收益为负")
        if price is not None and (price < 5000 or price > 200000):
            flags.append("单价异常")
        if agg:
            flags.append("链家聚合页")

        out.append({
            "链家小区id": r["链家小区id"],
            "备案登记名": txt(r.get("政府小区名")),
            "链家小区名": txt(r.get("链家小区名")),
            "区": txt(r.get("区")),
            "街道": txt(r.get("街道")),
            "商圈": txt(r.get("商圈")),
            "物业服务收费方式": txt(r.get("物业服务收费方式")),
            "房屋性质": props[0] if props else "",
            "物业公司变更": txt(r.get("物业公司变更")),
            "业委会状态": txt(r.get("业委会状态")),
            "置信度": txt(r.get("置信度")),
            "匹配方式": txt(r.get("匹配方式")),
            "户数": hh,
            "户数2018": numf(r.get("户数2018")),
            "楼栋数": bl,
            "楼栋均户数": round(hh / bl, 1) if hh and bl else None,
            "建成年代_链家": y_lj,
            "建成年代_备案": y_ba,
            "房龄_链家": (2026 - y_lj) if y_lj else None,
            "房龄_备案": (2026 - y_ba) if y_ba else None,
            "单价2019": price,
            "物业费_备案居住类": fee_res,
            "物业费_链家下限": lo,
            "物业费_链家上限": hi,
            "物业费_链家中值": round((lo + hi) / 2, 2) if lo is not None else None,
            "物业费_备案档数": len(det),
            "公共收益收入": income,
            "公共收益支出": spend,
            "公共收益余额": balance,
            "公共收益单独列账": 1 if r.get("公共收益是否单独列账") == "是" else 0,
            "业委会人数": ye_n,
            "备案登记完整": 1 if ((r.get("备案地址") or "").strip()
                            and (r.get("物业公司名2026") or "").strip() and det) else 0,
            "是否住宅": 1 if r.get("是否住宅") else 0,
            "链家为聚合页": agg,
            "共用同一链家小区的项目数": share[r["链家小区id"]],
            "质量标记": ";".join(flags),
        })

    names = [k for k in out[0].keys()]
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(names)
        for rec in out:
            w.writerow([cell(rec[k]) for k in names])
    os.replace(tmp, OUT)

    with open(OUT, encoding="utf-8-sig") as f:
        h = [next(f) for _ in range(2)]
    if h[0].strip() == h[1].strip():
        sys.exit("!! 写出异常：第二行与表头相同")

    print(f"写出 {OUT}：{len(out)} 行 × {len(names)} 列\n")
    print("缺失率（空值占比，越大越要小心）：")
    for k in names:
        miss = sum(1 for rec in out if rec[k] in (None, ""))
        print(f"  {k:<24}{miss / len(out) * 100:>6.1f}%")


if __name__ == "__main__":
    main()
