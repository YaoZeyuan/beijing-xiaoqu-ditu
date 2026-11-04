# -*- coding: utf-8 -*-
"""导出可公开发布的数据集：raw/ 放原始数据，processed/ 放加工结果，每份都同时给 CSV 和 JSON。

目录结构：

    public_data/
      README.md                  总说明
      dictionary.csv             全部字段的含义与填充率
      raw/
        gov_projects.csv|json    政府备案的一万个小区（脱敏）
        lianjia_2018.csv|json    链家开源小区库 2018.11 全量
        lianjia_2019.csv|json    链家开源小区库 2019.02 全量
      processed/
        xiaoqu.csv|json          小区级主表（按链家小区去重，匹配成功的）
        matched.csv|json         项目级匹配成功明细
        unmatched.csv|json       未匹配的备案项目 + Top3 候选

raw 是「我们手上有什么」，processed 是「把两个源接起来之后得到了什么」。
分开的好处是别人可以拿 raw 自己跑匹配、复核我们的结果，不必相信 processed。

用法：
    python export_dataset.py
    python export_dataset.py --out ../public_data
"""

import argparse
import collections
import csv
import datetime
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
LJ = os.path.join(ROOT, "raw_data", "lianjia")
sys.path.insert(0, BASE)
import match_lianjia as M  # noqa: E402
import build_db as B  # noqa: E402
import build_beian_master as BM  # noqa: E402
import ai_lookup_merge as AL  # noqa: E402
import ai_lookup_merge_m2 as AL2  # noqa: E402

YE_ORDER = {"业委会": 3, "物管会": 2, "均未成立": 1, "": 0}
CONF_ORDER = {"high": 3, "medium": 2, "low": 1, "": 0}

# 匹配脚本内部的失败代码 → 人话
REASON_CN = {
    "no_match": "未找到候选",
    "no_district_no_match": "区名缺失且未找到候选",
    "ambiguous_prefix": "多个同名候选（含楼栋前缀），无法判定",
    "ambiguous_loc_address": "多个候选门牌都能对上，无法判定",
    "ambiguous_fuzzy": "模糊匹配命中多个候选",
    "ambiguous_same_name": "完全同名的候选不止一个",
    "empty_name": "备案项目名缺失",
}


# ────────────────────────── 公共小工具 ──────────────────────────

def num_i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def reg_full(addr, co, prop):
    """备案登记是否完整：地址、物业公司、房屋性质三项都有填。

    只填了名称和收费方式的项目大多是胡同院落/单体楼/老旧公房，字段大面积缺失，
    且几乎全为「均未成立」。混入统计会严重压低成立率（详见 README）。
    """
    return "是" if (addr and co and prop) else "否"


def pick_worst(confs):
    return min((c for c in confs if c), key=lambda c: CONF_ORDER.get(c, 0), default="")


def detail_str(detail):
    """把物业费明细压成一行：业态-房屋性质-建筑类型:单价，多档用 ; 分隔。"""
    out = []
    for d in (detail or []):
        parts = [x for x in (d.get("业态"), d.get("房屋性质"), d.get("建筑类型"))
                 if x and x != "-"]
        price = d.get("单价")
        out.append("-".join(parts) + (f":{price}" if price is not None else ""))
    return ";".join(out)


def _cell(v):
    """CSV 单元格取值：None 写空，布尔写是/否，列表压成竖线分隔串。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (list, tuple)):
        return "|".join(str(x) for x in v)
    return v


def write_csv(path, cols, rows):
    """rows 可以是 dict 列表（按 cols 顺序取值）或值列表。

    注意：csv.writerows 直接吃 dict 会写出 dict 的 key，整列变成表头，
    所以这里必须显式按列名取值，写盘前再校验一次。
    """
    header = [c[0] for c in cols]

    def to_values(r):
        if isinstance(r, dict):
            return [_cell(r.get(h, "")) for h in header]
        return [_cell(v) for v in r]

    values = [to_values(r) for r in rows]
    if values and values[0] == header:
        raise SystemExit(f"{os.path.basename(path)} 生成异常：数据行与表头相同，已中止写盘")

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(values)
    try:
        os.replace(tmp, path)
    except PermissionError:
        alt = path[:-4] + ".new.csv"
        os.replace(tmp, alt)
        print(f"  !! {os.path.basename(path):<24} 被占用，写到 {os.path.basename(alt)}")
        return
    print(f"  {os.path.basename(path):<26} {len(values):>6} 行 {len(header):>3} 列")


def write_json(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    size = os.path.getsize(path) / 1e6
    print(f"  {os.path.basename(path):<26} {payload['count']:>6} 条  {size:.1f}MB")


# ────────────────────────── raw ──────────────────────────

GOV_COLS = [
    ("project_no", "政府备案项目编号（住建委系统内的唯一 ID）"),
    ("项目名称", "备案登记的小区名"),
    ("区", "行政区"),
    ("街道", "所属街道"),
    ("项目地址", "备案登记地址"),
    ("建成年代", "备案登记的建成年份（覆盖 84%，与链家的 age 是两套独立登记）"),
    ("物业服务收费方式", "包干制 / 酬金制"),
    ("物业费明细", "按 业态-房屋性质-建筑类型:单价 压缩成一行，多档用 ; 分隔；单价单位 元/㎡·月"),
    ("房屋性质", "从物业费明细里取出的产权性质：普通商品房/房改房/央产房/回迁房/保障房/别墅/公房等"),
    ("公共收益是否单独列账", "是 / 否"),
    ("公共收益列账方式", "会计列账 / 账户列账"),
    ("业委会状态", "业委会 / 物管会 / 均未成立"),
    ("业委会人数", "业委会或物管会成员人数"),
    ("物业服务企业名称", "2026 年备案登记的物业公司"),
    ("备案登记完整", "地址/物业公司/物业费明细是否都有填；否=残缺记录，见 README"),
]

LJ_COLS = [
    ("community_id", "链家小区 ID"),
    ("community_name", "链家小区名"),
    ("区", "行政区"),
    ("商圈", "链家商圈"),
    ("地址", "链家地址（括号内是商圈，后面是门牌）"),
    ("户数", "house_amount"),
    ("楼栋数", "building_amount"),
    ("建成年代", "age 字段原值，如「1980年建成」"),
    ("建筑结构", "structure"),
    ("物业费", "management_fee"),
    ("物业公司", "management_co"),
    ("开发商", "developer"),
    ("参考均价", "unit_price，元/㎡"),
    ("均价月份", "price_date"),
    ("经度", "longitude"),
    ("纬度", "latitude"),
    ("链家页面", "url"),
]


def build_gov(projs):
    rows, jobs = [], []
    for r in projs:
        name = (r.get("项目名称") or "").strip()
        if not name:
            continue          # 全空壳记录（原始 10,496 条里有 1 条），无分析价值
        addr = r.get("项目地址", "")
        detail = r.get("物业费明细") or []
        prop = B.house_props(detail)
        co = r.get("物业服务企业名称", "")
        rec = {
            "project_no": r["project_no"],
            "项目名称": name,
            "区": r.get("项目所在区", ""),
            "街道": r.get("所属街道", ""),
            "项目地址": addr,
            "建成年代": r.get("建成年代", ""),
            "物业服务收费方式": r.get("物业服务收费方式", ""),
            "物业费明细": detail_str(detail),
            "房屋性质": prop,
            "公共收益是否单独列账": r.get("公共收益是否单独列账", ""),
            "公共收益列账方式": r.get("列账方式", ""),
            "业委会状态": r.get("是否成立业委会(物管会)", ""),
            "业委会人数": r.get("业委会(物管会)人数", ""),
            "物业服务企业名称": co,
            "备案登记完整": reg_full(addr, co, prop),
        }
        rows.append(rec)
        j = dict(rec)
        j["物业费明细"] = detail        # JSON 保留原始结构，CSV 里是压缩串
        j["房屋性质"] = prop
        jobs.append(j)
    rows.sort(key=lambda x: x["project_no"])
    jobs.sort(key=lambda x: x["project_no"])
    return rows, jobs


def build_lj(path):
    rows, jobs = [], []
    for r in M.load_lj(path):
        rec = {
            "community_id": r.get("community_id"),
            "community_name": r.get("community_name"),
            "区": (r.get("hier4") or "").replace("小区", ""),
            "商圈": r.get("hier3") or "",
            "地址": r.get("location"),
            "户数": M.hh(r.get("house_amount")),
            "楼栋数": M.bd(r.get("building_amount")),
            "建成年代": r.get("age"),
            "建筑结构": r.get("structure"),
            "物业费": r.get("management_fee"),
            "物业公司": r.get("management_co"),
            "开发商": r.get("developer"),
            "参考均价": r.get("unit_price"),
            "均价月份": r.get("price_date"),
            "经度": r.get("longitude"),
            "纬度": r.get("latitude"),
            "链家页面": r.get("url"),
        }
        rows.append(rec)
        jobs.append(dict(rec))
    rows.sort(key=lambda x: str(x["community_id"]))
    jobs.sort(key=lambda x: str(x["community_id"]))
    return rows, jobs


# ────────────────────────── processed ──────────────────────────

XIAOQU_COLS = [
    ("小区id", "LJ+链家小区ID"),
    ("小区名", "链家小区名，对外展示用"),
    ("政府小区名", "对应的备案登记名，一个链家小区对应多个备案名时以 | 连接"),
    ("区", "行政区"), ("街道", "所属街道"), ("商圈", "链家商圈"),
    ("户数", "链家 2019 登记的户数"),
    ("户数2018", "链家 2018 登记值，用于交叉核对（92% 完全一致）"),
    ("楼栋数", "链家登记楼栋数"),
    ("建成年代", "链家 age"),
    ("物业费", "链家 management_fee"),
    ("物业公司名2019", "链家 2019 登记的物业公司"),
    ("物业公司名2026", "备案 2026 登记的物业服务企业"),
    ("物业公司变更", "两者比对结果；疑似档需人工复核"),
    ("物业服务收费方式", "包干制 / 酬金制"),
    ("房屋性质", "产权性质，来自备案物业费明细；多值用 | 分隔"),
    ("居住类物业费", "备案登记的居住类单价，元/㎡·月"),
    ("公共收益是否单独列账", "任一条目为是则为是"),
    ("业委会人数", "多个备案项目取最大值"),
    ("备案登记完整", "该小区所有备案项目里是否至少有一条登记完整"),
    ("业委会状态", "业委会 / 物管会 / 均未成立，多个项目取最高档"),
    ("经度", "经度"), ("纬度", "纬度"),
    ("链家单价2019", "链家小区参考均价，元/㎡"),
    ("链家小区id", "链家小区 ID"),
    ("链家链接", "链家页面"),
    ("备案项目数", "该小区对应的备案项目数，>1 说明备案按楼栋拆分登记"),
    ("匹配置信度", "high / medium / low，多个项目取最低"),
    ("匹配方式", "命中的匹配规则"),
    ("链家为聚合页", "是=链家把多个院落合成一条，户数为合计值"),
    ("是否住宅", "否=写字楼/商场等非住宅"),
]

MATCHED_COLS = [
    ("project_no", "政府备案项目编号"),
    ("政府小区名", "备案登记名"),
    ("链家小区名", "匹配到的链家小区名"),
    ("链家小区id", "链家小区 ID"),
    ("小区id", "对应 xiaoqu 里的主键"),
    ("区", "行政区"), ("街道", "所属街道"),
    ("备案地址", "备案登记地址"),
    ("户数", "该链家小区的户数"),
    ("楼栋数", "该链家小区的楼栋数"),
    ("建成年代", "链家 age"),
    ("物业公司名2019", "链家 2019 登记的物业公司"),
    ("物业公司名2026", "备案 2026 登记的物业服务企业"),
    ("物业公司变更", "两者比对结果"),
    ("物业服务收费方式", "包干制 / 酬金制"),
    ("房屋性质", "产权性质"),
    ("居住类物业费", "备案居住类单价"),
    ("公共收益是否单独列账", "是 / 否"),
    ("业委会人数", "业委会或物管会成员人数"),
    ("备案登记完整", "地址/物业公司/物业费是否都填了"),
    ("业委会状态", "业委会 / 物管会 / 均未成立"),
    ("匹配方式", "命中的规则或模型语义判定"),
    ("置信度", "high / medium / low"),
]

UNMATCHED_COLS = [
    ("project_no", "政府备案项目编号"),
    ("政府小区名", "备案登记名"),
    ("区", "行政区"), ("街道", "所属街道"),
    ("备案地址", "备案登记地址"),
    ("业委会状态", "业委会 / 物管会 / 均未成立"),
    ("物业服务收费方式", "包干制 / 酬金制"),
    ("房屋性质", "产权性质"),
    ("未匹配原因", "最后一步尝试的规则名；no_candidate=链家里确实没有相似的"),
    ("候选1小区名", "程序召回的 Top1 候选，仅供人工参考，不一定对"),
    ("候选1户数", ""), ("候选1地址", ""), ("候选1相似度", "名称相似度 0~1"),
    ("候选2小区名", ""), ("候选2户数", ""), ("候选2地址", ""), ("候选2相似度", ""),
    ("候选3小区名", ""), ("候选3户数", ""), ("候选3地址", ""), ("候选3相似度", ""),
]


def first_nonempty(rows, key):
    """合并多个备案项目时，区/街道取第一个有值的，避免因首行为空而丢掉信息。"""
    for r in rows:
        v = str(r.get(key) or "").strip()
        if v and v != "-":
            return v
    return ""


def build_xiaoqu(comms):
    groups = collections.OrderedDict()
    for r in comms:
        g = groups.setdefault(r["链家小区id"], {
            "names": [], "rows": [], "ye": "", "conf": [], "methods": set(),
            "props": [], "ledger": False, "pm_n": 0, "fee_res": None, "full": False,
        })
        if r["政府小区名"] and r["政府小区名"] not in g["names"]:
            g["names"].append(r["政府小区名"])
        g["rows"].append(r)
        if YE_ORDER.get(r["业委会状态"], 0) > YE_ORDER.get(g["ye"], 0):
            g["ye"] = r["业委会状态"]
        g["conf"].append(r["置信度"])
        g["methods"].add(r["匹配方式"])
        for p in (r.get("房屋性质") or "").split("|"):
            if p and p not in g["props"]:
                g["props"].append(p)
        if r.get("公共收益是否单独列账") == "是":
            g["ledger"] = True
        g["pm_n"] = max(g["pm_n"], num_i(r.get("业委会人数")))
        if g["fee_res"] is None and r.get("居住类物业费") is not None:
            g["fee_res"] = r["居住类物业费"]
        if reg_full(r.get("备案地址"), r.get("物业公司名2026"), r.get("房屋性质")) == "是":
            g["full"] = True

    rows = []
    for lj_id, g in groups.items():
        r = g["rows"][0]
        rows.append({
            "小区id": f"LJ{lj_id}",
            "小区名": r["链家小区名"],
            "政府小区名": "|".join(g["names"][:3]) + ("等" if len(g["names"]) > 3 else ""),
            "区": first_nonempty(g["rows"], "区"), "街道": first_nonempty(g["rows"], "街道"),
            "商圈": r["商圈"],
            "户数": r["户数"], "户数2018": r["户数2018"], "楼栋数": r["楼栋数"],
            "建成年代": r["建成年代"], "物业费": r["物业费"],
            "物业公司名2019": r["物业公司名2019"],
            "物业公司名2026": r["物业公司名2026"],
            "物业公司变更": r["物业公司变更"],
            "物业服务收费方式": r["物业服务收费方式"],
            "房屋性质": "|".join(g["props"]),
            "居住类物业费": g["fee_res"],
            "公共收益是否单独列账": "是" if g["ledger"] else "否",
            "业委会人数": g["pm_n"] or "",
            "备案登记完整": "是" if g["full"] else "否",
            "业委会状态": g["ye"],
            "经度": r["经度"], "纬度": r["纬度"],
            "链家单价2019": r["链家单价2019"],
            "链家小区id": lj_id, "链家链接": r["链家链接"],
            "备案项目数": len(g["rows"]),
            "匹配置信度": pick_worst(g["conf"]),
            "匹配方式": "、".join(sorted(g["methods"])),
            "链家为聚合页": "是" if r["链家为聚合页"] else "否",
            "是否住宅": "是" if r["是否住宅"] else "否",
        })
    # 区/街道有空值的排到最后，免得打开文件先看到一片空白
    rows.sort(key=lambda x: (x["区"] == "", x["区"], x["街道"], x["小区名"]))
    return rows


def build_matched(comms):
    rows = []
    for r in comms:
        rows.append({
            "project_no": r["project_no"], "政府小区名": r["政府小区名"],
            "链家小区名": r["链家小区名"], "链家小区id": r["链家小区id"],
            "小区id": f"LJ{r['链家小区id']}",
            "区": r["区"], "街道": r["街道"], "备案地址": r["备案地址"],
            "户数": r["户数"], "楼栋数": r["楼栋数"], "建成年代": r["建成年代"],
            "物业公司名2019": r["物业公司名2019"],
            "物业公司名2026": r["物业公司名2026"],
            "物业公司变更": r["物业公司变更"],
            "物业服务收费方式": r["物业服务收费方式"],
            "房屋性质": r.get("房屋性质", ""),
            "居住类物业费": r.get("居住类物业费"),
            "公共收益是否单独列账": r.get("公共收益是否单独列账", ""),
            "业委会人数": num_i(r.get("业委会人数")) or "",
            "备案登记完整": reg_full(r.get("备案地址"), r.get("物业公司名2026"),
                                     r.get("房屋性质")),
            "业委会状态": r["业委会状态"],
            "匹配方式": r["匹配方式"], "置信度": r["置信度"],
        })
    rows.sort(key=lambda x: x["project_no"])
    return rows


def build_unmatched(unmatched):
    rows = []
    for u in unmatched:
        rec = {
            "project_no": u["project_no"], "政府小区名": u["政府小区名"],
            "区": u["区"], "街道": u["街道"], "备案地址": u["备案地址"],
            "业委会状态": u["业委会状态"],
            "物业服务收费方式": u.get("物业服务收费方式", ""),
            "房屋性质": u.get("房屋性质", ""),
            "未匹配原因": REASON_CN.get(u["未匹配原因"], u["未匹配原因"]),
        }
        for i, c in enumerate((u.get("候选") or [])[:3], 1):
            rec[f"候选{i}小区名"] = c["链家小区名"]
            rec[f"候选{i}户数"] = c["户数"]
            rec[f"候选{i}地址"] = c["链家地址"]
            rec[f"候选{i}相似度"] = c["名称相似度"]
        rows.append(rec)
    rows.sort(key=lambda x: x["project_no"])
    return rows


# ────────────────────────── 主流程 ──────────────────────────

def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


GROUP_META = {
    "raw": ("原始数据",
            "未经加工的源数据。想自己重跑匹配、或验证我们的结果，从这三份开始。"),
    "processed": ("加工结果",
                  "把政府备案和链家小区库接起来之后的结果。"
                  "以备案为单位做分析用 beian_master，以小区为单位用 xiaoqu。"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "public_data"))
    ap.add_argument("--db", default=os.path.join(LJ, "xiaoqu_db.json"))
    args = ap.parse_args()

    raw_dir = os.path.join(args.out, "raw")
    proc_dir = os.path.join(args.out, "processed")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(proc_dir, exist_ok=True)

    db = json.load(open(args.db, encoding="utf-8"))
    comms, unmatched = db["小区库"], db["未匹配小区"]
    projs = json.load(open(os.path.join(BASE, "data", "projects.json"), encoding="utf-8"))
    generated = datetime.datetime.now().strftime("%Y-%m-%d")

    datasets = []          # (路径, 列定义, 行)
    manifest = collections.OrderedDict()
    for k, (t, d) in GROUP_META.items():
        manifest[k] = {"key": k, "title": t, "desc": d, "items": []}

    def emit(dir_, name, cols, rows, jrows=None, title="", desc="", group="raw"):
        csv_path = os.path.join(dir_, name + ".csv")
        json_path = os.path.join(dir_, name + ".json")
        write_csv(csv_path, cols, rows)
        payload = {
            "meta": {
                "title": title,
                "description": desc,
                "generated": generated,
                "source": "北京市住建委住宅小区业主大会与业委会备案公示 / "
                          "github.com/shuijingoj/LianJiaCommunityData",
                "license": "CC BY 4.0",
                "字段说明": {c[0]: c[1] for c in cols if c[1]},
            },
            "count": len(rows),
            "data": jrows if jrows is not None else rows,
        }
        write_json(json_path, payload)
        datasets.append((f"{os.path.basename(dir_)}/{name}", cols, rows))
        manifest[group]["items"].append({
            "name": name,
            "title": title,
            "desc": desc,
            "rows": len(rows),
            "fields": len(cols),
            "csv": f"{os.path.basename(dir_)}/{name}.csv",
            "json": f"{os.path.basename(dir_)}/{name}.json",
            "csvSize": human(os.path.getsize(csv_path)),
            "jsonSize": human(os.path.getsize(json_path)),
        })
        return len(rows)

    print("raw/")
    gov_rows, gov_json = build_gov(projs)
    n_gov = emit(raw_dir, "gov_projects", GOV_COLS, gov_rows, gov_json,
                 "北京住宅小区政府备案数据",
                 "北京市住建委住宅小区业主大会与业委会备案系统导出的全量项目，已脱敏。")

    n18 = n19 = 0
    for y, fn in (("2018", "baseinfo_201811.csv"), ("2019", "baseinfo_201902.csv")):
        rows, jrows = build_lj(os.path.join(LJ, fn))
        emit(raw_dir, f"lianjia_{y}", LJ_COLS, rows, jrows,
             f"链家开源小区库 {y}",
             "来自 shuijingoj/LianJiaCommunityData，两期可交叉核对户数。")
        if y == "2018":
            n18 = len(rows)
        else:
            n19 = len(rows)

    print("processed/")
    x_rows = build_xiaoqu(comms)
    n_xq = emit(proc_dir, "xiaoqu", XIAOQU_COLS, x_rows, group="processed",
                title="北京小区级主表（匹配成功）",
                desc="按链家小区去重，一行一个小区。统计时用这张表，"
                     "不要用 matched（备案按楼栋拆分会重复计数）。")

    m_rows = build_matched(comms)
    n_m = emit(proc_dir, "matched", MATCHED_COLS, m_rows, group="processed",
               title="备案项目 ↔ 链家小区 匹配明细",
               desc="一行一个备案项目，保留匹配方式与置信度，可追溯每个匹配是怎么来的。")

    # 公开包与 gov_projects / unmatched 保持同一批备案（剔除 1 条空名记录）
    b_rows, _ = BM.build()
    b_rows = [r for r in b_rows if r["备案项目名"]]
    # 合并 AI 互联网检索结果（户数/物业费/均价 + 来源），幂等
    ai_stat = AL.merge_rows(b_rows)
    ai_stat2 = AL2.merge_rows(b_rows)
    print("  AI检索合并：", dict(ai_stat))
    print("  多对一小区补查：", dict(ai_stat2))
    b_stat = collections.Counter(r["关联状态"] for r in b_rows)
    b_cat = collections.Counter(r["匹配类别"] for r in b_rows)
    # 公开列：BM.COLS 基础上，在「备注」前插入 AI 5 列（户数/口径/物业费/均价/来源）
    bm_cols = BM.COLS[:-1] + AL.AI_COLS + [BM.COLS[-1]]
    n_b = emit(proc_dir, "beian_master", bm_cols, b_rows, group="processed",
               title="北京备案项目主表（一行一条备案）",
               desc="以政府备案项目为基准，右挂链家小区信息。业委会状态、物业费、公共收益均为备案口径"
                    "——这是目前唯一带业委会成立情况的一手数据。链家字段按关联状态决定填不填，"
                    "未匹配的成因看匹配类别列（6 类互斥，含 AI 互联网补查的「AI寻找」）。"
                    "户数看 户数/AI户数 两列，AI户数口径标明是「单条备案」「本备案分区」"
                    "「整小区合计」还是「整小区合计·分区未拆」——最后一种多条备案共用，"
                    "求和前必须按链家id去重。")

    u_rows = build_unmatched(unmatched)
    n_u = emit(proc_dir, "unmatched", UNMATCHED_COLS, u_rows, group="processed",
               title="未匹配的备案项目",
               desc="链家库里找不到对应小区的备案项目，附程序召回的 Top3 候选，"
                    "供人工或换数据源时补匹配。")

    # ── 字段字典 ──
    dict_rows = []
    for fn, cols, rows in datasets:
        n = len(rows) or 1
        for name, desc in cols:
            if not desc:
                continue
            filled = sum(1 for r in rows if str(r.get(name, "")).strip() not in ("", "None"))
            dict_rows.append([fn, name, desc, f"{filled / n * 100:.0f}%"])
    write_csv(os.path.join(args.out, "dictionary.csv"),
              [("文件", "文件路径"), ("字段", "字段名"), ("含义", "字段含义"),
               ("填充率", "非空占比")], dict_rows)

    # ── 前端用的数据清单 ──
    st = {"gov": n_gov, "lj18": n18, "lj19": n19,
          "xiaoqu": n_xq, "matched": n_m, "unmatched": n_u, "beian": n_b,
          "b_11": b_stat["一对一"], "b_n1": b_stat["多对一"], "b_nm": b_stat["未匹配"],
          "cat_cand": b_cat["未匹配-无相似候选"], "cat_dist": b_cat["未匹配-备案区缺失"],
          "cat_amb": b_cat["未匹配-候选歧义"], "cat_short": b_cat["未匹配-项目名过短"],
          "cat_ai": b_cat["AI寻找"],
          "hh_lj": sum(1 for r in b_rows if str(r.get("户数", "")).strip()),
          "hh_ai": sum(1 for r in b_rows if str(r.get("AI户数", "")).strip()),
          "hh_scope_whole": sum(1 for r in b_rows if r.get("AI户数口径") == "整小区合计"),
          "hh_scope_part": sum(1 for r in b_rows if r.get("AI户数口径") == "本备案分区"),
          "hh_scope_shared": sum(1 for r in b_rows
                                  if r.get("AI户数口径") == "整小区合计·分区未拆"),
          "hh_scope_single": sum(1 for r in b_rows if r.get("AI户数口径") == "单条备案"),
          "b_n1_no_hh": sum(1 for r in b_rows if r.get("关联状态") == "多对一"
                            and not str(r.get("户数", "")).strip()
                            and not str(r.get("AI户数", "")).strip())}
    prev = [x for x in x_rows if x["匹配置信度"] and x["匹配置信度"] != "high"]
    ok = [x for x in x_rows if x["备案登记完整"] == "是" and x["是否住宅"] == "是"]
    ye = collections.Counter(x["业委会状态"] for x in ok)
    n_ok = len(ok) or 1

    manifest["meta"] = {
        "generated": generated,
        "repo": "https://github.com/YaoZeyuan/beijing-xiaoqu-ditu",
        "rawBase": "https://raw.githubusercontent.com/YaoZeyuan/beijing-xiaoqu-ditu/main/public_data/",
        "browseBase": "https://github.com/YaoZeyuan/beijing-xiaoqu-ditu/tree/main/public_data/",
        "license": "CC BY 4.0",
        "stats": {
            "备案项目": st["gov"], "已匹配": st["matched"],
            "匹配率": round(st["matched"] / max(st["gov"], 1) * 100, 1),
            "去重小区": st["xiaoqu"], "未匹配": st["unmatched"],
            "备案主表": st["beian"], "一对一": st["b_11"], "多对一": st["b_n1"],
            "低置信匹配": len(prev),
        },
        "regime": {
            "样本": len(ok),
            "业委会": ye["业委会"], "物管会": ye["物管会"], "均未成立": ye["均未成立"],
            "业委会率": round(ye["业委会"] / n_ok * 100, 1),
            "物管会率": round(ye["物管会"] / n_ok * 100, 1),
        },
    }
    ordered = {"meta": manifest["meta"],
               "groups": [manifest["raw"], manifest["processed"]]}
    for target in (os.path.join(args.out, "manifest.json"),
                   os.path.join(ROOT, "web", "public", "data", "dataset.json")):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(ordered, f, ensure_ascii=False, indent=1)
    print(f"  manifest.json / web/public/data/dataset.json")

    print_stats(st, x_rows)
    write_readme(args.out, st, generated, x_rows)
    print(f"输出目录: {args.out}")


def print_stats(st, x_rows):
    rate = st["matched"] / st["gov"] * 100
    print(f"\n  备案项目 {st['gov']:,}  匹配 {st['matched']:,}（{rate:.1f}%）"
          f"  去重小区 {st['xiaoqu']:,}  未匹配 {st['unmatched']:,}")
    ok = [x for x in x_rows if x["备案登记完整"] == "是" and x["是否住宅"] == "是"]
    ye = collections.Counter(x["业委会状态"] for x in ok)
    if ok:
        print(f"  登记完整住宅小区 {len(ok):,}：业委会 {ye['业委会']/len(ok)*100:.1f}%"
              f"  物管会 {ye['物管会']/len(ok)*100:.1f}%"
              f"  均未成立 {ye['均未成立']/len(ok)*100:.1f}%")


def write_readme(out, st, generated, x_rows):
    rate = st["matched"] / st["gov"] * 100
    ok = [x for x in x_rows if x["备案登记完整"] == "是" and x["是否住宅"] == "是"]
    ye = collections.Counter(x["业委会状态"] for x in ok)
    n_ok = len(ok) or 1

    readme = f"""# 北京住宅小区数据（公开版）

北京住宅小区的**小区级与备案级基础数据**，把两个互不相通的数据源接了起来：

- **政府侧**：北京市住建委住宅小区业主大会与业委会备案系统（项目名、区、街道、物业费、物业公司、收费方式、业委会状态）
- **链家侧**：开源小区库（户数、楼栋数、建成年代、经纬度、参考均价、链家小区页）

两边的小区名经常对不上：备案记「今家园」、链家叫「宣海家园」；备案按楼栋拆成多条、
链家合成一条展示。这里用程序规则 + 大模型逐条语义判定做了对齐，并保留置信度。

## 目录

```
raw/          原始数据，未经加工
processed/    把两个源接起来之后的结果
```

### raw/ 原始数据

| 文件 | 行数 | 说明 |
|---|---|---|
| `gov_projects.csv` / `.json` | {st['gov']:,} | 政府备案的全量小区项目，已脱敏 |
| `lianjia_2018.csv` / `.json` | {st['lj18']:,} | 链家开源小区库 2018.11 |
| `lianjia_2019.csv` / `.json` | {st['lj19']:,} | 链家开源小区库 2019.02 |

两期链家数据可以交叉核对：同一个链家 `community_id` 的户数 **92% 完全一致**，
不一致的多是链家自身修正，可当数据质量参考。

### processed/ 加工结果

| 文件 | 行数 | 说明 |
|---|---|---|
| `xiaoqu.csv` / `.json` | {st['xiaoqu']:,} | **小区主表**：一行一个小区，按链家小区去重 |
| `matched.csv` / `.json` | {st['matched']:,} | 一行一个备案项目，附匹配方式与置信度，可追溯 |
| `beian_master.csv` / `.json` | {st['beian']:,} | **备案主表**：一行一条备案，链家信息右挂。业委会状态与公共收益只有这张有 |
| `unmatched.csv` / `.json` | {st['unmatched']:,} | 未匹配的备案项目，附 Top3 候选供人工补匹配 |

匹配结果：**{st['matched']:,} / {st['gov']:,} = {rate:.1f}%** 的备案项目找到了对应小区。

## 怎么用

**做小区层面的统计** → `processed/xiaoqu.csv`。
**做备案层面的研究（业委会成立、公共收益、物业费结构）** → `processed/beian_master.csv`。
**查某个备案项目对到哪个链家小区、为什么这么对** → `processed/matched.csv`。
**想自己重跑匹配** → 用 `raw/` 三份数据，`matched` 里有我们用的规则名可以对照。

CSV 全部是 UTF-8 BOM，Excel 双击打开不乱码；JSON 是 `{{meta, count, data}}` 结构，`data` 为对象数组。

```python
import pandas as pd
df = pd.read_csv('processed/xiaoqu.csv', encoding='utf-8-sig')
```

## 四个必须知道的口径

### 1. 先过滤 `备案登记完整 = 是`

备案库里有一批只填了项目名、区、街道和收费方式的记录（占 19%），
地址、物业公司、物业费明细全空，业委会状态清一色「均未成立」。
这批记录**不成比例地集中在「酬金制」上**（酬金制里 75% 是这种残缺记录，包干制只有 3%）。

不过滤会得出「酬金制小区几乎不成立业委会」的假结论；过滤后两者没有差异。

### 2. 户数来自链家，不是官方统计

`户数` 是链家 2019 年登记值，与 2018 版交叉核对。个别小区是单栋空壳条目（<6 户），已在源数据里标出。

### 3. `链家为聚合页 = 是` 的户数是合计值

链家把多个院落合成一条展示时，户数是整片街区的合计，不能当作单个小区。
这类记录 `备案项目数` 通常也 >1——做户数分析必须用 `xiaoqu.csv` 去重后的值。

### 4. 剔除非住宅

`是否住宅 = 否` 是写字楼/商场，做住宅分析要排除。

### 5. 户数有两列，先看 `AI户数口径` 再用

`beian_master` 每条备案一行，户数分两列：`户数`（链家匹配得来）与 `AI户数`（互联网补查得来）。
{st['beian']:,} 条备案里，{st['hh_lj']:,} 条有链家户数、{st['hh_ai']:,} 条有补查户数，
`AI户数口径` 说明每个数是哪种口径：

| 口径 | 条数 | 含义 | 能不能直接加总 |
|---|---|---|---|
| 单条备案 | {st['hh_scope_single']:,} | 链家没匹配上，但网上查到了这一条备案自己的户数 | 能 |
| 本备案分区 | {st['hh_scope_part']:,} | 查到了该分区/该栋的独立户数 | 能 |
| 整小区合计 | {st['hh_scope_whole']:,} | 这条备案本身就等于整个小区 | 能 |
| 整小区合计·分区未拆 | {st['hh_scope_shared']:,} | 只是小区的一部分，这里放的是**整个小区**的户数作参考 | **不能**，要按 `链家id` 去重 |

最后一行是最容易踩的：{st['b_n1']:,} 条「多对一」备案共用 863 个链家小区，平均 2.8 条对 1 个小区。
网上只查得到小区总数、查不到各分区，于是把小区总数放在每条上并标「分区未拆」——
直接求和会把户数放大 2.8 倍。**算户数总量时：按 `链家id` 去重，只数一次。**

完全没户数的还剩 {st['beian'] - st['hh_lj'] - st['hh_ai']:,} 条：其中 {st['b_n1_no_hh']:,} 条是
多对一里连小区总数都没搜到的分区，其余是胡同院落/单位自管院/非住宅项目——
这些在公开互联网上大概率就没有权威数字了。

### 6. 三种「未匹配」的成因不同，别当成一回事

`beian_master` 的 `匹配类别` 列是 6 类互斥枚举，可直接用来筛样本：

| 匹配类别 | 条数 | 性质 |
|---|---|---|
| 匹配成功 | {st['beian'] - st['b_nm'] - st['cat_ai']:,} | — |
| AI寻找 | {st['cat_ai']:,} | 链家没匹配上，但通过互联网公开页面（百科/房产平台/政府网站）补查到了户数、物业费，见 `AI户数`/`AI物业费`/`AI来源` 列 |
| 未匹配-无相似候选 | {st['cat_cand']:,} | 真实覆盖缺口，链家侧可能就没有这个小区 |
| 未匹配-备案区缺失 | {st['cat_dist']:,} | **登记问题**：项目所在区为空，跳过跨区模糊匹配。补上区名后这部分多数能匹配 |
| 未匹配-候选歧义 | {st['cat_amb']:,} | **算法保守**：有多条同名候选，宁可留空也不猜 |
| 未匹配-项目名过短 | {st['cat_short']:,} | 项目名归一后不足 2 字 |

评估「覆盖率」时，把「备案区缺失」从分母里剔除会得到更公允的数字。
`匹配类别` 只回答成没成、为什么不成；**置信度**与链家字段是否齐全属叠加维度，另列。

## 一个参考数字

只看登记完整、且为住宅的 {len(ok):,} 个小区：

| 状态 | 小区数 | 占比 |
|---|---|---|
| 业委会 | {ye['业委会']:,} | {ye['业委会']/n_ok*100:.1f}% |
| 物管会 | {ye['物管会']:,} | {ye['物管会']/n_ok*100:.1f}% |
| 均未成立 | {ye['均未成立']:,} | {ye['均未成立']/n_ok*100:.1f}% |

（这个数字会随数据更新变化，引用前请自己按上面四条口径重算。）

## 字段

见 `dictionary.csv`，列了每个文件的每个字段含义与实测填充率。

几个容易被忽略但很有用的：

- `房屋性质`：普通商品房 / 房改房 / 央产房 / 回迁房 / 保障房 / 别墅 / 自管公房 / 直管公房。藏在备案的物业费明细里，是这套数据里唯一的产权性质来源，做治理分析时应作为控制变量。
- `物业公司变更`：2019 链家登记 vs 2026 备案登记的比对结果，能看七年里哪些小区换了物业。
- `公共收益是否单独列账`：100% 覆盖，是个现成的治理变量。
- `匹配方式` / `置信度`：`high` 是程序规则完全对应，`medium` 含模型语义判定，`low` 只有模糊名称相似，可按需过滤。

## 已做的脱敏

剔除：业委会与项目负责人的姓名、联系方式、企业法定代表人、统一社会信用代码、企业注册地址。

保留：物业公司全称、物业费等收费标准、业委会状态、**物业共有部分经营收支金额**
（`beian_master` 的 `公共收益收入` / `支出` / `余额` 三列）——均属政府公示的公共事项。

## 来源与许可

- 政府备案：北京市住建委住宅小区业主大会与业委会备案公示
- 链家小区库：github.com/shuijingoj/LianJiaCommunityData（2018 / 2019 两期）
- 生成时间：{generated}
- 许可：CC BY 4.0，注明来源即可自由使用

## 已知局限

- {100 - rate:.0f}% 的备案项目在链家找不到对应小区，多为单位家属院、胡同院落、单栋楼。这些没有户数，但物业费、收费方式、业委会状态是有的
- 名称匹配有误差，`置信度 = low` 的建议人工复核
- 「物业公司变更」是字符串比对结果，`疑似` 档需人工确认
- 备案的 `房屋性质` 有 17% 未登记，且缺失不是随机的——它和整条记录的完整度高度相关
- `beian_master` 里「一对多」为 0 例，是匹配阶段每个备案只保留一个最优链家小区所致，不是数据里真的没有
- 公共收益金额原始填报单位未统一，且有 6,000 多行填 0，分不清「真为 0」与「未填」
"""
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)
    print("  README.md")


if __name__ == "__main__":
    main()
