# -*- coding: utf-8 -*-
"""把匹配结果清洗成一份可对外使用的 JSON 数据库。

产出 raw_data/lianjia/xiaoqu_db.json：
  meta           —— 生成时间、数据来源、口径说明、统计
  小区库         —— 确认匹配的备案小区（每条 = 一个政府备案项目）
  链家小区索引   —— 按链家小区 id 去重的小区级索引，附对应政府小区名
  未匹配小区     —— 未匹配上的备案项目，保留候选，供后续人工/规则再处理

字段口径：
  政府小区名 = 备案（业委会系统）登记的小区名，内部分析以它为准
  链家小区名 = 链家小区库中的展示名
  户数       = 链家小区库的 house_amount（2019 版），2018 版同时保留用于交叉核对

用法：
    python build_db.py                # 生成 xiaoqu_db.json
    python build_db.py --min-conf high  # 只保留高置信度记录
"""

import argparse
import collections
import csv
import datetime
import difflib
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
OUT = os.path.join(ROOT, "raw_data", "lianjia")
sys.path.insert(0, BASE)
import match_lianjia as M  # noqa: E402

MATCH_SRC = {
    "exact": "规则-完全同名",
    "suffix_normalized": "规则-后缀归一",
    "unit_prefix": "规则-楼栋前缀",
    "loc_address": "规则-地址反查",
    "fuzzy_name": "规则-模糊名称",
    "llm_judge": "模型语义判定",
}

# 判断是否为住宅小区：写字楼/商场类条目对户数分析没有意义，单独标注而不是删除
BIZ_RE = re.compile(r"(大厦|写字楼|商场|购物中心|办公楼|商务楼|科技园|产业园)")
RES_RE = re.compile(r"(公寓|住宅|宿舍|小区|家园|苑|园|里|院|村|楼|区)")

CO_NOISE = re.compile(r"((股份)?有限(责任)?公司|公司|集团|控股|总公司|中心|管理处|管理所|分公司|分部)")
CO_CITY = re.compile(r"^(北京市?|市)")
CO_CITY_TAIL = re.compile(r"(北京|上海|天津|重庆|深圳|广州|中国|市)$")
NO_PM_RE = re.compile(r"(无物业|单位自管|房管所|街道|居委会|代管|暂无)")
CO_PAREN = re.compile(r"[（(][^）)]*[）)]")


def norm_co(s):
    """物业公司名归一化。返回 (归一后名称, 是否属于「无物业/自管/代管」类)。

    归一口径：去括号注记 → 去公司类后缀（含分公司）→ 去地名前缀/尾部 → 去物业类通用词。
    目标是让「北京市丰台城建物业管理公司」与「北京丰台城建物业管理有限公司」判为同一家。
    """
    s = (s or "").strip().replace(" ", "").replace("\u3000", "")
    if not s or s in ("暂无信息", "-"):
        return "", False
    no_pm = bool(NO_PM_RE.search(s))
    s = CO_PAREN.sub("", s)
    s = CO_NOISE.sub("", s)
    s = CO_CITY_TAIL.sub("", s)
    s = CO_CITY.sub("", s)
    for w in ("服务", "管理", "物业", "顾问"):
        s = s.replace(w, "")
    return s, no_pm


def house_props(detail):
    """从物业费明细提取居住类房屋性质（普通商品房/房改房/央产房/保障房…），多值用 | 连接。

    这个字段藏在明细里，是唯一能反映产权性质的公开数据，做治理分析时必须控制它。
    """
    out = []
    for d in (detail or []):
        if d.get("业态") != "居住类":
            continue
        n = (d.get("房屋性质") or "").strip()
        if n and n not in ("-", "暂无信息") and n not in out:
            out.append(n)
    return "|".join(out)


def house_fee(detail, biz="居住类"):
    """取指定业态的物业费单价（元/㎡/月）。一个项目可能有多条明细，取第一条非空。"""
    for d in (detail or []):
        if d.get("业态") == biz and d.get("单价") is not None:
            try:
                return float(d["单价"])
            except (TypeError, ValueError):
                continue
    return None


def co_changed(a, b):
    """比对 2019 链家登记与 2026 备案登记的物业公司。返回变更标签。"""
    na, no_a = norm_co(a)
    nb, no_b = norm_co(b)
    if not na or not nb:
        return "无法判断"
    if no_a and no_b:
        return "均无物业" if na == nb else "代管方式变化"
    if no_a != no_b:
        return "从无物业到有物业" if no_a else "从有物业到无物业"
    if na == nb:
        return "未变更"
    if na in nb or nb in na:
        return "疑似未变更(名称微调)"
    r = difflib.SequenceMatcher(None, na, nb).ratio()
    if r >= 0.85:
        return "疑似未变更(名称微调)"
    if r >= 0.6:
        return "疑似变更(名称相近)"
    return "已变更"


def num(v):
    """把 '1,234户' / '12' 这类字符串转成 int 或 None。"""
    if v is None:
        return None
    s = str(v).replace(",", "").replace("户", "").strip()
    if s in ("", "-", "None", "nan"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def load_candidates():
    path = os.path.join(OUT, "candidates.jsonl")
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out[d["project_no"]] = d
    return out


def load_projects():
    """备案正式数据集，补充 matched.csv 里没有的字段（项目地址、业委会人数等）。"""
    path = os.path.join(ROOT, "crawler", "data", "projects.json")
    out = {}
    if not os.path.exists(path):
        return out
    for r in json.load(open(path, encoding="utf-8")):
        out[r["project_no"]] = r
    return out


def pick_matched():
    """matched.csv 可能被编辑器占用，此时回填结果写在 matched_llm.csv，取较新的一个。"""
    a = os.path.join(OUT, "matched.csv")
    b = os.path.join(OUT, "matched_llm.csv")
    if os.path.exists(b) and (not os.path.exists(a) or
                               os.path.getmtime(b) >= os.path.getmtime(a)):
        return b
    return a


def build(min_conf="low", include_unmatched=True, out_path=None, matched=None):
    path = matched or pick_matched()
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    cands = load_candidates()
    projs = load_projects()
    lj18 = {r["community_id"]: r for r in M.load_lj(os.path.join(OUT, "baseinfo_201811.csv"))}

    order = {"high": 3, "medium": 2, "low": 1}
    thresh = order.get(min_conf, 1)

    communities, unmatched = [], []
    lj_index = {}

    for r in rows:
        pno = r["project_no"]
        name = (r["项目名称"] or "").strip()
        conf = (r["置信度"] or "").strip()
        lj_id = (r["lj_community_id"] or "").strip()
        method = (r["匹配"] or "").strip()

        # ---- 已匹配 ----
        if lj_id and conf and order.get(conf, 0) >= thresh:
            hh = num(r["link_households"])
            hh18 = num(lj18.get(lj_id, {}).get("house_amount"))
            p = projs.get(pno, {})
            rec = {
                "project_no": pno,
                "政府小区名": name,
                "链家小区名": r["lj_name"],
                "链家小区id": lj_id,
                "区": r["区"],
                "街道": r["街道"],
                "备案地址": p.get("项目地址", ""),
                "链家地址": r["lj_address"],
                "户数": hh,
                "户数2018": hh18,
                "户数存疑": (hh is None or hh < 6),
                "两年户数一致": ("" if hh is None or hh18 is None
                              else ("是" if hh == hh18 else "否")),
                "楼栋数": num(r["lj_buildings"]),
                "建成年代": r["lj_age"],
                "物业费": r["lj_fee"],
                "物业公司名2019": r["lj_property_co"],
                "物业公司名2026": p.get("物业服务企业名称", ""),
                "物业公司变更": co_changed(r["lj_property_co"], p.get("物业服务企业名称", "")),
                "物业服务收费方式": p.get("物业服务收费方式", ""),
                "物业公司统一社会信用代码": p.get("统一社会信用代码", ""),
                "商圈": r["lj_biz_area"],
                "经度": r["lng"],
                "纬度": r["lat"],
                "链家单价2019": r["lj_unit_price_2019"],
                "链家链接": r["lj_url"],
                "业委会状态": r["业委会状态"],
                "业委会人数": p.get("业委会(物管会)人数", ""),
                "业委会负责人": p.get("业委会(物管会)负责人姓名", ""),
                "物业服务企业": p.get("物业服务企业名称", ""),
                "物业费明细": p.get("物业费明细", []),
                "房屋性质": house_props(p.get("物业费明细")),
                "居住类物业费": house_fee(p.get("物业费明细"), "居住类"),
                "非居住类物业费": house_fee(p.get("物业费明细"), "非居住类"),
                "公共收益是否单独列账": p.get("公共收益是否单独列账", ""),
                "公共收益列账方式": p.get("列账方式", ""),
                "共有部分经营收入": p.get("物业共有部分经营收入", ""),
                "共有部分经营支出": p.get("物业共有部分经营支出", ""),
                "共有部分经营余额": p.get("共有部分经营余额", ""),
                "上一周期综合评价等级": p.get("上一周期综合评价等级", ""),
                "备案建成年代": r["建成年代"],
                "备案物业费标准": r["物业费标准"],
                "匹配方式": MATCH_SRC.get(method, method),
                "匹配代码": method,
                "置信度": conf,
                "链家为聚合页": r["链家为聚合页"] == "1",
                "链家地址门牌数": num(r["链家地址数"]),
                "共用同一链家小区的备案项目数": num(r["共享项目数"]),
                "是否住宅": not (BIZ_RE.search(name) and not RES_RE.search(name)),
            }
            communities.append(rec)

            idx = lj_index.setdefault(lj_id, {
                "链家小区id": lj_id,
                "链家小区名": r["lj_name"],
                "链家地址": r["lj_address"],
                "户数": hh,
                "楼栋数": num(r["lj_buildings"]),
                "建成年代": r["lj_age"],
                "物业费": r["lj_fee"],
                "物业公司名2019": r["lj_property_co"],
                "物业公司名2026": p.get("物业服务企业名称", ""),
                "物业公司变更": co_changed(r["lj_property_co"], p.get("物业服务企业名称", "")),
                "物业服务收费方式": p.get("物业服务收费方式", ""),
                "物业公司统一社会信用代码": p.get("统一社会信用代码", ""),
                "商圈": r["lj_biz_area"],
                "经度": r["lng"],
                "纬度": r["lat"],
                "链家单价2019": r["lj_unit_price_2019"],
                "链家链接": r["lj_url"],
                "链家为聚合页": r["链家为聚合页"] == "1",
                "对应政府小区名": [],
            })
            if name and name not in idx["对应政府小区名"]:
                idx["对应政府小区名"].append(name)
            continue

        # ---- 未匹配 ----
        if not include_unmatched:
            continue
        if not name:
            continue
        cand = cands.get(pno)
        p = projs.get(pno, {})
        c_list = []
        if cand:
            for c in cand.get("候选", [])[:5]:
                c_list.append({
                    "链家小区名": c["链家名"],
                    "链家小区id": c["lj_id"],
                    "链家地址": c["链家地址"],
                    "户数": c["户数"],
                    "楼栋": c["楼栋"],
                    "名称相似度": c["名相似"],
                    "证据": c["证据"],
                    "已被其他备案项目占用": bool(c["已占用"]),
                })
        unmatched.append({
            "project_no": pno,
            "政府小区名": name,
            "区": r["区"],
            "街道": r["街道"],
            "备案地址": p.get("项目地址", ""),
            "业委会状态": r["业委会状态"],
            "未匹配原因": method if method else "无匹配",
            "房屋性质": house_props(p.get("物业费明细")),
            "居住类物业费": house_fee(p.get("物业费明细"), "居住类"),
            "物业服务收费方式": p.get("物业服务收费方式", ""),
            "公共收益是否单独列账": p.get("公共收益是否单独列账", ""),
            "公共收益列账方式": p.get("列账方式", ""),
            "业委会人数": p.get("业委会(物管会)人数", ""),
            "物业公司名2026": p.get("物业服务企业名称", ""),
            "候选": c_list,
        })

    # 按实际数据重算「共用同一链家小区的备案项目数」（matched.csv 里的旧值不可靠）
    share = collections.Counter(x["链家小区id"] for x in communities)
    for x in communities:
        x["共用同一链家小区的备案项目数"] = share[x["链家小区id"]]

    conf_cnt = collections.Counter(x["置信度"] for x in communities)
    method_cnt = collections.Counter(x["匹配代码"] for x in communities)
    db = {
        "meta": {
            "生成时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "说明": "北京备案小区 × 链家小区 的对应数据库。内部统计以「政府小区名」为准，"
                    "「链家小区名」用于回链家原始数据核对。",
            "数据来源": {
                "政府备案": "北京市住宅小区业主大会与业委会备案系统（本地导出）",
                "链家小区": "shuijingoj/LianJiaCommunityData 开源小区库（2018/2019 两期）",
            },
            "口径说明": {
                "户数": "链家小区库 house_amount 字段，2019 版为口径基准，2018 版用于交叉核对",
                "置信度": "high=程序规则完全对应；medium=规则归一或模型语义判定；low=仅模糊名称相似",
                "链家为聚合页": "链家把多个院落合并成一条展示，户数是合计值，分析时应注意",
                "共用同一链家小区的备案项目数": ">1 表示多个备案项目指向同一条链家条目，"
                                              "该户数不能直接当作单个项目的户数",
                "是否住宅": "false 表示备案名是写字楼/商场等非住宅，做户数分析时应剔除",
                "未匹配小区": "保留候选清单，便于后续用新数据源补齐",
            },
            "统计": {
                "备案项目总数": len(rows),
                "已确认匹配": len(communities),
                "匹配率": round(len(communities) / len(rows) * 100, 1),
                "去重后链家小区数": len(lj_index),
                "未匹配": len(unmatched),
                "按置信度": dict(conf_cnt),
                "按匹配方式": dict(method_cnt),
                "有户数记录": sum(1 for x in communities if x["户数"]),
                "户数存疑条目": sum(1 for x in communities if x["户数存疑"]),
                "非住宅条目": sum(1 for x in communities if not x["是否住宅"]),
                "共用聚合条的备案项目": sum(1 for x in communities
                                    if x["共用同一链家小区的备案项目数"] > 1),
            },
        },
        "小区库": communities,
        "链家小区索引": list(lj_index.values()),
        "未匹配小区": unmatched,
    }

    out_path = out_path or os.path.join(OUT, "xiaoqu_db.json")
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_path)

    # 精简版：按链家小区去重，一行一个小区，适合对外分发/公示
    slim = {
        "meta": {k: db["meta"][k] for k in ("生成时间", "说明", "数据来源", "口径说明")},
        "小区数": len(lj_index),
        "小区": sorted(lj_index.values(), key=lambda x: (x["链家小区id"])),
    }
    slim_path = out_path.replace(".json", "_slim.json")
    tmp = slim_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=1)
    os.replace(tmp, slim_path)

    _write_public(db, communities, lj_index, slim, out_path)
    return db, out_path


# 对外发布版只保留与小区本身有关的事实字段：去掉负责人姓名、财务金额等敏感/内部信息
PUBLIC_FIELDS = [
    "project_no", "政府小区名", "链家小区名", "链家小区id", "区", "街道",
    "户数", "户数2018", "户数存疑", "楼栋数", "建成年代", "物业费",
    "物业公司名2019", "物业公司名2026", "物业公司变更", "物业服务收费方式", "商圈",
    "经度", "纬度", "链家单价2019", "链家链接", "业委会状态",
    "房屋性质", "居住类物业费", "非居住类物业费",
    "公共收益是否单独列账", "公共收益列账方式", "业委会人数",
    "匹配方式", "匹配代码", "置信度", "链家为聚合页", "是否住宅",
]


def _write_public(db, communities, lj_index, slim, out_path):
    pub = {
        "meta": {
            "生成时间": db["meta"]["生成时间"],
            "说明": db["meta"]["说明"],
            "数据来源": db["meta"]["数据来源"],
            "口径说明": db["meta"]["口径说明"],
            "统计": db["meta"]["统计"],
        },
        "小区库": [{k: r.get(k) for k in PUBLIC_FIELDS} for r in communities],
        "链家小区索引": slim["小区"],
    }
    path = out_path.replace(".json", "_public.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pub, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-conf", default="low", choices=["high", "medium", "low"])
    ap.add_argument("--no-unmatched", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    db, path = build(args.min_conf, not args.no_unmatched, args.out)
    print(json.dumps(db["meta"]["统计"], ensure_ascii=False, indent=1))
    print("写出:", path)


if __name__ == "__main__":
    main()
