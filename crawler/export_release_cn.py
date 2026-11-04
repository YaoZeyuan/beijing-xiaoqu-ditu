# -*- coding: utf-8 -*-
"""导出中文文件名的发布版数据（基于备案小区），方便直接下载阅读。

输出三个文件（UTF-8 带 BOM，Excel 双击打开不乱码）：

    北京小区备案台账-明细10495条.csv      10,495 条备案 × 46 列，一行一条备案
    北京小区备案台账-小区去重汇总.csv      按链家小区去重后的台账 + 关联备案数
    北京小区备案台账-字段说明.csv          46 个字段的含义与填充率（按明细实时重算）
    北京小区备案台账-数据说明.txt          一页纸口径说明

用法：
    python export_release_cn.py                                  # 默认输出到 web/public/data/发布版
    python export_release_cn.py --out ../public_data/发布版       # 指定其他目录
"""

import argparse
import csv
import datetime
import os
import sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
MASTER = os.path.join(ROOT, "public_data", "processed", "beian_master.csv")
DICT = os.path.join(ROOT, "public_data", "dictionary.csv")

# 小区级去重的 key：有链家 id 用链家 id；否则用 区+备案项目名 兜底
def xq_key(row):
    lj = (row.get("链家id") or "").strip()
    if lj:
        return "lj_" + lj
    return "n_" + (row.get("区") or "").strip() + (row.get("备案项目名") or "").strip()


def fill_rate(rows, col):
    n = sum(1 for r in rows if (r.get(col) or "").strip())
    return f"{n} 条（{n / len(rows):.1%}）" if rows else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "public", "data", "发布版"))
    ap.add_argument("--master", default=MASTER)
    args = ap.parse_args()

    with open(args.master, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys())
    print(f"读入主表 {len(rows)} 行 × {len(cols)} 列")

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.date.today().strftime("%Y-%m-%d")

    # ── 1. 明细 ──
    p1 = os.path.join(args.out, "北京小区备案台账-明细10495条.csv")
    with open(p1, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  明细   {p1}  ({os.path.getsize(p1)/1e6:.1f} MB)")

    # ── 2. 小区去重汇总 ──
    groups = {}
    for r in rows:
        groups.setdefault(xq_key(r), []).append(r)
    cols2 = cols + ["关联备案数"]
    p2 = os.path.join(args.out, "北京小区备案台账-小区去重汇总.csv")
    with open(p2, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols2)
        w.writeheader()
        for key, grp in groups.items():
            rep = dict(grp[0])
            rep["关联备案数"] = len(grp)
            w.writerow(rep)
    print(f"  汇总   {p2}  ({len(groups)} 个小区, {os.path.getsize(p2)/1e6:.1f} MB)")

    # ── 3. 字段说明（含义复用 dictionary.csv，填充率按明细重算）──
    meanings = {}
    try:
        with open(DICT, encoding="utf-8-sig", newline="") as f:
            for d in csv.DictReader(f):
                if d["文件"] == "processed/beian_master":
                    meanings[d["字段"]] = d["含义"]
    except FileNotFoundError:
        pass
    p3 = os.path.join(args.out, "北京小区备案台账-字段说明.csv")
    with open(p3, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["字段", "含义", "填充情况（共 %d 条备案）" % len(rows)])
        for c in cols:
            w.writerow([c, meanings.get(c, ""), fill_rate(rows, c)])
    print(f"  字典   {p3}")

    # ── 4. 一页纸说明 ──
    n_xq = len(groups)
    n_hh = sum(1 for r in rows if (r.get("AI户数") or "").strip())
    n_price = sum(1 for r in rows if (r.get("AI均价") or "").strip())
    scope_cnt = Counter((r.get("AI户数口径") or "").strip() for r in rows if (r.get("AI户数") or "").strip())
    p4 = os.path.join(args.out, "北京小区备案台账-数据说明.txt")
    with open(p4, "w", encoding="utf-8") as f:
        f.write(f"""北京市住宅小区物业备案台账 · 发布版（{stamp}）

一、这是什么
    北京市住建委「物业项目信息查询」备案数据（{len(rows)} 条），
    与链家小区库匹配后，再经互联网检索补齐户数 / 物业费 / 挂牌均价等
    基础信息的加工结果。一行 = 一条物业备案。

二、文件清单
    北京小区备案台账-明细10495条.csv    全部备案，一行一条（主表）
    北京小区备案台账-小区去重汇总.csv    同一小区多条备案的，合并成一行
                                        （{n_xq} 个小区），末列「关联备案数」标条数
    北京小区备案台账-字段说明.csv        46 个字段的含义与填充率
    北京小区备案台账-数据说明.txt        本文件

三、户数口径（重要，先看「AI户数口径」列再用「AI户数」）
""")
        for k, v in scope_cnt.most_common():
            f.write(f"    {k}: {v} 条\n")
        f.write(f"""    户数覆盖 {n_hh} 条备案（{n_hh/len(rows):.1%}）；挂牌均价 {n_price} 条。
    「整小区合计·分区未拆」= 只查到整个小区的户数、没查到该备案分区
    各占多少，多条备案共享时直接求和会重复计数，需按小区去重。

四、匹配状态
    「匹配类别」列六类：匹配成功 / AI寻找 / 未匹配-无相似候选 /
    未匹配-备案区缺失 / 未匹配-候选歧义 / 名过短。
    未匹配的备案没有链家小区信息，户数等列大多为空。

五、来源与许可
    备案数据：北京市住建委物业项目信息查询（公开渠道）
    小区底库：链家小区开源库 2018.11 / 2019.02
    户数等补充：互联网公开检索（「AI来源」列记录出处）
    仅用于社区治理研究，转载请注明出处。
""")
    print(f"  说明   {p4}")
    print(f"✅ 发布版输出完成：{os.path.abspath(args.out)}")


if __name__ == "__main__":
    sys.exit(main())
