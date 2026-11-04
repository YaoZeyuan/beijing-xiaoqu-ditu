# -*- coding: utf-8 -*-
"""备案项目主表：一行一条政府备案项目，右挂链家小区信息。

与 xiaoqu_master.py 的方向相反：
  xiaoqu_master  以链家小区为基准，把多条备案合并成一行
  beian_master   以备案项目为基准，把链家信息挂到每条备案上

关联规则（用户定）：
  - 一对一      备案只对到一个链家小区，且该小区也只被这一条备案占用
                → 均价、地址、链家id、户数、历史物业费全部填
  - 多对一      多条备案共用同一个链家小区
                → 填均价、地址、链家id、历史物业费，户数不填（是整小区合计），备注标记
  - 一对多      一条备案对到多个链家小区
                → 链家信息一律不填，备注标记（当前数据里为 0 例）
  - 未匹配      对不到任何链家小区
                → 链家信息一律不填，备注标记

数值口径：
  户数          链家 2018-11 与 2019-02 两个快照取最大（值形如「1119户」）
  历史物业费    两个快照的挂牌物业费取最大；单条是区间时取区间上限
  小区均价      取 2019，缺失时回退 2018

只读 raw_data/ 下已匹配好的结果，不重新跑匹配。输出到 raw_data/exports/（gitignore）。
"""
import collections
import csv
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOV = os.path.join(ROOT, "crawler/data/projects.json")
MATCHED = os.path.join(ROOT, "raw_data/lianjia/matched.csv")
LJ18 = os.path.join(ROOT, "raw_data/lianjia/baseinfo_201811.csv")
LJ19 = os.path.join(ROOT, "raw_data/lianjia/baseinfo_201902.csv")
OUT = os.path.join(ROOT, "raw_data/exports/beian_master.csv")

PLACEHOLDER = {"暂无信息", "暂无", "无", "-", "—", "/", ""}

RULE_CN = {
    "exact": "名称完全一致",
    "suffix_normalized": "名称归一后一致",
    "loc_address": "地址门牌匹配",
    "unit_prefix": "院号/单元前缀匹配",
    "fuzzy_name": "名称模糊且唯一",
    "llm_judge": "大模型语义判定",
    "ambiguous": "同名歧义未匹配",
    "ambiguous_same_name": "同名歧义未匹配",
    "ambiguous_prefix": "前缀歧义未匹配",
    "ambiguous_loc_address": "地址歧义未匹配",
    "ambiguous_fuzzy": "模糊歧义未匹配",
    "no_district_no_match": "区县不符且无匹配",
    "no_match": "无相似候选",
}

COLS = [
    ("备案编号", "主键，政府备案项目编号"),
    ("备案项目名", "备案登记的项目名"),
    ("区", "备案登记行政区"),
    ("街道", "备案登记街道，源数据里 1,715 条为空"),
    ("备案地址", "备案登记地址"),
    ("建成年代_备案", "备案登记建成年代，大量为空"),
    ("业委会状态", "业委会 / 物管会 / 均未成立，2026 年备案口径"),
    ("业委会人数", "业委会或物管会人数"),
    ("物业服务收费方式", "包干制 / 酬金制"),
    ("物业费标准_备案", "备案登记的原始物业费文本，未解析"),
    ("居住类物业费", "从物业费明细里取居住类单价最高者，元/㎡·月"),
    ("房屋性质", "从物业费明细里取，多值用 | 连接"),
    ("物业公司2026", "备案登记的物业服务企业全称"),
    ("公共收益是否单独列账", "是 / 否"),
    ("公共收益收入", "物业共有部分经营收入，源数据填报单位未标注（多数按元），0 与空分不清"),
    ("公共收益支出", "物业共有部分经营支出，同上"),
    ("公共收益余额", "共有部分经营余额，同上"),
    ("备案登记完整", "1=地址、物业公司、物业费明细都有；0=登记残缺，做统计要先过滤"),
    ("匹配类别", "匹配结果与未匹配成因，5 类互斥；已匹配的细分原因看「匹配方式」"),
    ("关联状态", "一对一 / 多对一 / 一对多 / 未匹配"),
    ("共享该链家的备案数", "指向同一个链家小区的备案条数；一对一 恒为 1"),
    ("匹配方式", "规则名（中文）"),
    ("匹配代码", "规则原始代码，便于回溯 match_lianjia.py"),
    ("置信度", "high / medium / low；未匹配为空"),
    ("链家id", "链家 community_id"),
    ("链家小区名", "链家页面上的小区名"),
    ("链家地址", "链家 location 字段，格式为「(区商圈)地址1, 地址2」"),
    ("商圈", "链家商圈"),
    ("经度", "链家坐标，取 2019 快照"),
    ("纬度", "链家坐标，取 2019 快照"),
    ("小区均价", "链家参考均价，取 2019，缺失回退 2018，元/㎡"),
    ("均价2018", "链家 2018-11 参考均价，元/㎡"),
    ("均价2019", "链家 2019-02 参考均价，元/㎡"),
    ("户数", "两期最大值；仅一对一填，多对一留空"),
    ("户数2018", "链家 2018-11 登记户数"),
    ("户数2019", "链家 2019-02 登记户数"),
    ("历史物业费", "两期挂牌物业费的最大值；区间取上限，元/㎡·月"),
    ("物业费2018_原始", "链家 2018 挂牌物业费原文，如「1.98至2.5元/平米/月」"),
    ("物业费2019_原始", "链家 2019 挂牌物业费原文"),
    ("链家建成年代", "链家 age 折算的年份"),
    ("备注", "关联状态、链家侧字段缺失、数值异常的逐条说明；完全无异常时为空"),
]
FIELDS = [c[0] for c in COLS]


# ── 解析小工具 ────────────────────────────────────────────────
def txt(v):
    s = str(v or "").strip()
    return "" if s in PLACEHOLDER else s


def load_lj(path):
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for x in csv.DictReader(f, delimiter=";"):
            out[x["community_id"]] = x
    return out


def house(s):
    """「1119户」→ 1119；无法解析返回 None。"""
    m = re.fullmatch(r"(\d+)户", (s or "").strip())
    return int(m.group(1)) if m else None


def fee_max(s):
    """「1.98至2.5元/平米/月」→ 2.5；「暂无信息」→ None。取区间上限。"""
    vals = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", (s or ""))]
    return max(vals) if vals else None


def price(s):
    m = re.fullmatch(r"(\d+)", (s or "").strip())
    return int(m.group(1)) if m else None


def money(v):
    """公共收益金额：源数据有 '.5118' 这种前导 0 丢失，也有浮点尾噪，规整成正常小数。"""
    s = str(v if v is not None else "").strip()
    if s in PLACEHOLDER:
        return ""
    if s.startswith("."):
        s = "0" + s
    elif s.startswith("-."):
        s = "-0" + s[1:]
    try:
        return f"{round(float(s), 4):.4f}".rstrip("0").rstrip(".")
    except ValueError:
        return s


def year_of(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def detail_props(det):
    """物业费明细 → (居住类单价最高值, 房屋性质集合)。

    只认业态严格等于「居住类」的条目；「非居住类」也含「居住」二字，不能用子串判断。
    与 build_db.house_props / house_fee 的口径保持一致。
    """
    fee, props = None, []
    for it in det or []:
        if str(it.get("业态") or "").strip() != "居住类":
            continue
        v = it.get("单价")
        if isinstance(v, (int, float)) and (fee is None or v > fee):
            fee = float(v)
        p = txt(it.get("房屋性质"))
        if p and p not in props:
            props.append(p)
    return fee, props


def match_cat(status, code):
    """关联状态 + 匹配代码 → 单一的匹配类别（互斥，便于快速筛选）。

    「置信度」「链家字段是否齐全」是叠加维度，不塞进这一列，否则会破坏互斥性。
    """
    if status == "一对一":
        return "匹配成功"
    if status == "多对一":
        return "匹配成功"          # 共享情况看「关联状态」列
    if status == "一对多":
        return "匹配成功-对应多个链家"   # 当前数据 0 例，保留分支
    if code == "no_match":
        return "未匹配-无相似候选"
    if code == "no_district_no_match":
        return "未匹配-备案区缺失"   # 147 条，项目所在区字段全空
    if code.startswith("ambiguous"):
        return "未匹配-候选歧义"
    if code == "empty_name":
        return "未匹配-项目名过短"   # 归一后不足 2 字，规则无法启用
    return "未匹配-原因未知"


def cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


# ── 主流程 ────────────────────────────────────────────────────
def build():
    gov = json.load(open(GOV, encoding="utf-8"))
    matched = {}
    with open(MATCHED, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            matched[r["project_no"]] = r

    A, B = load_lj(LJ18), load_lj(LJ19)

    # 链家 baseinfo 里没有干净的商业圈字段（hier3 是「东城小区」这类分类），
    # 商圈取上一阶段 build_db 从 hier4 归一出来的 lj_biz_area
    biz = {r["lj_community_id"].strip(): txt(r["lj_biz_area"])
           for r in matched.values() if r["lj_community_id"].strip()}

    # 每个链家小区被几条备案指向
    share = collections.Counter(
        r["lj_community_id"].strip() for r in matched.values() if r["lj_community_id"].strip()
    )

    rows = []
    stat = collections.Counter()
    for g in gov:
        no = g["project_no"]
        m = matched.get(no) or {}
        lj_ids = [x for x in (m.get("lj_community_id") or "").split("|") if x.strip()]
        note = []

        if not lj_ids:
            status = "未匹配"
        elif len(lj_ids) > 1:
            status = "一对多"
        elif share[lj_ids[0]] > 1:
            status = "多对一"
        else:
            status = "一对一"
        stat[status] += 1

        lj = lj_ids[0] if len(lj_ids) == 1 else None
        a, b = (A.get(lj), B.get(lj)) if lj else (None, None)

        code = m.get("匹配") or ""
        cat = match_cat(status, code)
        if status == "未匹配":
            if code == "no_district_no_match":
                note.append("未匹配到链家小区（备案未填所在区，未做跨区模糊匹配）")
            elif code == "empty_name":
                note.append("未匹配到链家小区（项目名归一后不足 2 字，规则无法启用）")
            elif code.startswith("ambiguous"):
                note.append("未匹配到链家小区（有同名或近似候选，街道信息不足以消歧）")
            else:
                note.append("未匹配到链家小区")
        elif status == "一对多":
            note.append(f"对应 {len(lj_ids)} 个链家小区，按规则不填链家信息")
        elif status == "多对一":
            note.append(f"该链家小区被 {share[lj]} 条备案共享，链家户数是整小区合计，"
                        f"未按备案拆分；小区层户数见「AI户数口径」列")
        if lj and a is None:
            note.append("链家 2018-11 快照无此小区")

        # 户数：仅一对一记录
        hh18 = house(a["house_amount"]) if a else None
        hh19 = house(b["house_amount"]) if b else None
        hh = max([x for x in (hh18, hh19) if x is not None], default=None)

        # 物业费：两期上限取最大
        f18 = fee_max(a["management_fee"]) if a else None
        f19 = fee_max(b["management_fee"]) if b else None
        fee = max([x for x in (f18, f19) if x is not None], default=None)

        # 均价：2019 优先
        p18 = price(a["unit_price"]) if a else None
        p19 = price(b["unit_price"]) if b else None
        p_main = p19 if p19 is not None else p18

        # 已匹配但对端根本没有这个值（不是我们丢了，是链家页面没登）
        if lj:
            if fee is None:
                note.append("链家两期均无挂牌物业费")
            if p_main is None:
                note.append("链家两期均无参考均价")
            if status == "一对一" and hh is None:
                note.append("链家两期均无户数")

        det = g.get("物业费明细") or []
        fee_res, props = detail_props(det)
        full = 1 if (txt(g.get("项目地址")) and txt(g.get("物业服务企业名称")) and det) else 0

        # 数值异常只打标签，不删行也不改值
        if status == "一对一" and hh is not None:
            if hh > 20000:
                note.append(f"链家户数异常（{hh}户），疑似链家把多个院落合成一页")
            elif hh < 6:
                note.append(f"链家户数过小（{hh}户），可能是单栋空壳条目")
        if fee_res is not None and fee_res > 50:
            note.append(f"备案居住类物业费异常（{fee_res:g} 元/㎡·月），疑似录入错误")

        keep = status in ("一对一", "多对一")
        rows.append({
            "备案编号": no,
            "备案项目名": txt(g.get("项目名称")),
            "区": txt(g.get("项目所在区")),
            "街道": txt(g.get("所属街道")),
            "备案地址": txt(g.get("项目地址")),
            "建成年代_备案": year_of(g.get("建成年代")) or "",
            "业委会状态": txt(g.get("是否成立业委会(物管会)")),
            "业委会人数": txt(g.get("业委会(物管会)人数")),
            "物业服务收费方式": txt(g.get("物业服务收费方式")),
            "物业费标准_备案": txt(g.get("物业服务费用标准")),
            "居住类物业费": fee_res,
            "房屋性质": "|".join(props),
            "物业公司2026": txt(g.get("物业服务企业名称")),
            "公共收益是否单独列账": txt(g.get("公共收益是否单独列账")),
            "公共收益收入": money(g.get("物业共有部分经营收入")),
            "公共收益支出": money(g.get("物业共有部分经营支出")),
            "公共收益余额": money(g.get("共有部分经营余额")),
            "备案登记完整": full,
            "匹配类别": cat,
            "关联状态": status,
            "共享该链家的备案数": share[lj] if lj else "",
            "匹配方式": RULE_CN.get(m.get("匹配") or "", txt(m.get("匹配"))),
            "匹配代码": m.get("匹配") or "",
            "置信度": txt(m.get("置信度")),
            "链家id": lj or "",
            "链家小区名": txt((b or a or {}).get("community_name")) if keep else "",
            "链家地址": txt((b or a or {}).get("location")) if keep else "",
            "商圈": biz.get(lj, "") if keep else "",
            "经度": txt((b or a or {}).get("longitude")) if keep else "",
            "纬度": txt((b or a or {}).get("latitude")) if keep else "",
            "小区均价": p_main if keep else "",
            "均价2018": p18 if keep else "",
            "均价2019": p19 if keep else "",
            "户数": hh if status == "一对一" else "",
            "户数2018": hh18 if status == "一对一" else "",
            "户数2019": hh19 if status == "一对一" else "",
            "历史物业费": fee if keep else "",
            "物业费2018_原始": txt(a["management_fee"]) if keep and a else "",
            "物业费2019_原始": txt(b["management_fee"]) if keep and b else "",
            "链家建成年代": (f"{year_of((b or a or {}).get('age'))}年"
                       if keep and year_of((b or a or {}).get("age")) else ""),
            "备注": "；".join(note),
        })

    rows.sort(key=lambda r: (r["区"] == "", r["区"], r["街道"], r["备案项目名"]))
    return rows, stat


def main():
    rows, stat = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow([cell(r[k]) for k in FIELDS])
    os.replace(tmp, OUT)

    with open(OUT, encoding="utf-8-sig") as f:
        h = [next(f) for _ in range(2)]
    if h[0].strip() == h[1].strip():
        sys.exit("!! 写出异常：第二行与表头相同")

    n = len(rows)
    print(f"写出 {OUT}：{n} 行 × {len(FIELDS)} 列\n")
    cats = collections.Counter(r["匹配类别"] for r in rows)
    for k, v in cats.most_common():
        print(f"  {k:<16}{v:>6}  {v / n * 100:5.1f}%")
    print()
    for k in ("小区均价", "户数", "历史物业费", "链家id"):
        print(f"  {k} 非空：{sum(1 for r in rows if r[k] not in ('', None))}")
    print()
    print("  关联状态 × 匹配类别：",
          collections.Counter((r["关联状态"], r["匹配类别"]) for r in rows).most_common())


if __name__ == "__main__":
    main()
