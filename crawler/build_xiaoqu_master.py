# -*- coding: utf-8 -*-
"""小区级主表：一行一个链家小区，把多个政府备案项目聚合到该小区。

聚合规则（用户已定）：
  - 粒度：一个链家小区一行；863 个小区一对多，涉及 2,402 条备案
  - 业委会状态：业委会 > 物管会 > 均未成立，取最高
  - 物业费：取备案居住类单价最高者
  - 收费方式：组内出现酬金制则记为酬金制（用户指定，知悉会引入 228 个小区的偏差）
  - 房屋性质：商品房 > 别墅 > 保障房 > 回迁房 > 房改房 > 央产房 > 公房，取最高
  - 时间口径：规模与价格用链家 2019 快照；治理与备案字段只有 2026

其余字段的默认规则见各字段注释，一律只聚合不删除，可疑值写入「数据质量标记」。

对外发布版剔除公共收益金额（见 SECRET_FIELDS），沿用原有脱敏规则；物业公司全称保留。
"""
import csv
import json
import os
import re
import sys
import collections

sys.stdout.reconfigure(encoding="utf-8")

SRC = "raw_data/lianjia/xiaoqu_db.json"
OUT = "raw_data/exports/xiaoqu_master.csv"

PLACEHOLDER = {"暂无信息", "暂无", "无", "-", "—", "/"}

YE_RANK = {"业委会": 3, "物管会": 2, "均未成立": 1}
PROP_RANK = {"普通商品房": 8, "别墅": 7, "保障房": 6, "回迁房": 5,
             "房改房": 4, "央产房": 3, "自管公房": 1, "直管公房": 1, "其他": 0}
CHANGE_RANK = [("已变更", 6), ("从无物业到有物业", 5), ("代管方式变化", 4),
               ("疑似变更", 3), ("未变更", 2), ("疑似未变更", 1)]
BT_RANK = ["高层住宅", "多层住宅有电梯", "多层住宅无电梯", "其它住宅",
           "非高层住宅", "多层非住宅有电梯", "多层非住宅无电梯", "其它非住宅"]

# 发布时剔除的字段（金额类，沿用原脱敏规则；公司全称保留）
SECRET_FIELDS = {"公共收益收入", "公共收益支出", "公共收益余额"}

DESC = {
    "小区id": "主键，LJ + 链家小区 id",
    "链家小区id": "链家 community_id",
    "链家小区名": "链家页面上的小区名",
    "政府小区名": "对应的备案登记名，多个用顿号连接",
    "备案项目数": "该小区对应的备案项目数，>1 说明备案按楼栋拆分登记",
    "区": "行政区",
    "街道": "所属街道",
    "商圈": "链家商圈",
    "经度": "链家坐标 WGS84",
    "纬度": "链家坐标 WGS84",
    "户数": "链家 2019 登记户数（不是官方统计）",
    "户数2018": "链家 2018-11 登记值，用于交叉核对",
    "户数变化": "户数 - 户数2018",
    "楼栋数": "链家登记楼栋数",
    "楼栋均户数": "户数 / 楼栋数，密度代理变量",
    "建成年代": "链家 age 折算的年份",
    "房龄": "2026 - 建成年代",
    "单价2019": "链家 2019 参考均价，元/㎡",
    "物业公司2019": "链家 2019 登记的物业公司，可能填的是管理模式（如「单位自管物业」）",
    "物业管理模式2019": "由上一列归类：专业物业公司/无物业/单位自管/业主自管/政府代管/私人承办/未知",
    "物业公司2026": "备案 2026 登记的物业服务企业",
    "物业管理模式2026": "由上一列归类",
    "物业公司变更": "2019 vs 2026 比对；多个项目冲突时取变化确定性最高的一档",
    "物业服务收费方式": "包干制 / 酬金制；组内出现酬金制即记酬金制",
    "收费方式判定": "单一 / 冲突取酬金制；后者可用来自行改口径重算",
    "物业费": "备案居住类单价，多个备案项目取最高，元/㎡·月",
    "物业费_最低": "同一小区内备案居住类单价的最低值，用来看组内离散",
    "物业费_档数": "该小区有几个不同的备案居住类单价",
    "物业费_链家2019": "链家 2019 挂牌物业费区间取中值，用于交叉核对",
    "房屋性质": "主产权性质，按 商品房>别墅>保障房>回迁>房改>央产>公房 取最高",
    "房屋性质_全部": "该小区出现过的全部产权性质，用 | 分隔",
    "建筑类型": "备案明细里出现最多的一种：高层住宅/多层住宅有电梯/多层住宅无电梯/…",
    "电梯": "1 有 / 0 无 / 空 未提",
    "公共收益收入": "多个备案项目加总，单位口径未统一",
    "公共收益支出": "同上",
    "公共收益余额": "同上",
    "公共收益单独列账": "1 = 任一备案项目单独列账",
    "公共收益列账方式": "会计列账 / 账户列账",
    "业委会状态": "业委会 / 物管会 / 均未成立；多个项目取最高档",
    "业委会人数": "取与最终业委会状态同源的那条记录",
    "备案登记完整": "1 = 该小区至少有一条备案地址、物业公司、物业费明细齐全的记录",
    "置信度": "匹配置信度，多个项目取最低",
    "链家为聚合页": "1 = 链家把多个院落合成一条，户数为合计值",
    "是否住宅": "0 = 写字楼/商场等非住宅",
    "匹配方式": "命中的匹配规则，多个用顿号连接",
    "数据质量标记": "分号分隔的可疑值标签：户数异常/备案物业费异常/业委会人数异常/公共收益金额异常/收费方式冲突/链家聚合页/低置信匹配/备案不完整",
}

ALL_FIELDS = list(DESC.keys())
COLS = [(f, DESC[f]) for f in ALL_FIELDS if f not in SECRET_FIELDS]


def txt(v):
    s = str(v if v is not None else "").strip()
    return "" if s in PLACEHOLDER else s


def numf(v):
    s = txt(v)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def money(v):
    s = txt(v)
    if not s:
        return None
    if s.startswith("."):
        s = "0" + s
    elif s.startswith("-."):
        s = "-0" + s[1:]
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def year(v):
    m = re.search(r"(19|20)\d{2}", str(v or ""))
    return int(m.group(0)) if m else None


def fee_range(s):
    s = txt(s)
    if not s:
        return None, None
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums:
        return None, None
    vals = [float(x) for x in nums[:2]]
    return vals[0], (vals[1] if len(vals) > 1 else vals[0])


def change_label(names):
    """组内多个变更标签时，取「变化确定性最高」的一个。"""
    best, best_rank = "", -1
    for s in names:
        r = 0
        for kw, rk in CHANGE_RANK:
            if kw in s:
                r = rk
                break
        if r > best_rank:
            best, best_rank = s, r
    return best


def lift(items):
    """从物业费明细判断电梯：1 有 / 0 无 / None 未提。"""
    s = "".join(items)
    if "有电梯" in s:
        return 1
    if "无电梯" in s:
        return 0
    if "高层住宅" in s:
        return 1
    return None


def mgmt_mode(v):
    """把「物业公司名」归类成管理模式 —— 链家这一列混了公司名和模式说明。"""
    s = str(v or "").strip()
    if not s or s in {"暂无信息", "暂无", "-", "—", "/"}:
        return "未知"
    if s == "无" or "无物业" in s:
        return "无物业"
    if "单位自管" in s:
        return "单位自管"
    if "业主自" in s or "自筹" in s:
        return "业主自管"
    if "代管" in s:
        return "政府代管"
    if "私人承办" in s:
        return "私人承办"
    return "专业物业公司"


def cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def build(comms):
    """comms：xiaoqu_db.json 的「小区库」（一个备案项目一条），返回小区级行。"""
    groups = collections.OrderedDict()
    for r in comms:
        groups.setdefault(r["链家小区id"], []).append(r)

    out = []
    for lid, g in groups.items():
        first = g[0]

        # ---- 规模与价格：链家 2019 快照，组内应一致，取第一条非空 ----
        hh = next((numf(x["户数"]) for x in g if numf(x["户数"]) is not None), None)
        hh18 = next((numf(x["户数2018"]) for x in g if numf(x["户数2018"]) is not None), None)
        bl = next((numf(x["楼栋数"]) for x in g if numf(x["楼栋数"]) is not None), None)
        y_lj = next((year(x["建成年代"]) for x in g if year(x["建成年代"])), None)
        price = next((numf(x["链家单价2019"]) for x in g if numf(x["链家单价2019"]) is not None), None)

        # ---- 区 / 街道：多数票 ----
        qu = collections.Counter(txt(x["区"]) for x in g if txt(x["区"])).most_common(1)
        st = collections.Counter(txt(x["街道"]) for x in g if txt(x["街道"])).most_common(1)
        qu = qu[0][0] if qu else ""
        st = st[0][0] if st else ""

        # ---- 业委会：等级取最高，人数跟同源记录 ----
        best_ye, best_rank = "", 0
        for x in g:
            r = YE_RANK.get(txt(x["业委会状态"]), 0)
            if r > best_rank:
                best_ye, best_rank = txt(x["业委会状态"]), r
        ye_n = None
        for x in g:
            if txt(x["业委会状态"]) == best_ye and numf(x["业委会人数"]) is not None:
                ye_n = numf(x["业委会人数"])
                break

        # ---- 物业费：备案居住类取最高 ----
        fees = [numf(x["居住类物业费"]) for x in g if numf(x["居住类物业费"]) is not None]
        fee = max(fees) if fees else None
        fee_min = min(fees) if fees else None
        lj_mid = [(a + b) / 2 for a, b in (fee_range(x["物业费"]) for x in g) if a is not None]
        lj_mid = round(max(lj_mid), 2) if lj_mid else None

        # ---- 收费方式：出现酬金制即酬金制 ----
        modes = [txt(x["物业服务收费方式"]) for x in g if txt(x["物业服务收费方式"])]
        if not modes:
            mode, mode_src = "", "无记录"
        elif len(set(modes)) == 1:
            mode, mode_src = modes[0], "单一"
        elif "酬金制" in modes:
            mode, mode_src = "酬金制", "冲突取酬金制"
        else:
            mode, mode_src = "包干制", "单一"

        # ---- 房屋性质：等级最高为主，全部值并列 ----
        props = []
        for x in g:
            for p in str(x["房屋性质"] or "").split("|"):
                p = txt(p)
                if p and p not in props:
                    props.append(p)
        props.sort(key=lambda p: -PROP_RANK.get(p, 0))
        prop_main = props[0] if props else ""

        # ---- 建筑类型 / 电梯 ----
        bts = []
        for x in g:
            for it in (x.get("物业费明细") or []):
                b = txt(it.get("建筑类型"))
                if b:
                    bts.append(b)
        bt_cnt = collections.Counter(bts)
        bt = ""
        if bt_cnt:
            bt = sorted(bt_cnt.items(),
                        key=lambda kv: (-kv[1], BT_RANK.index(kv[0]) if kv[0] in BT_RANK else 99))[0][0]
        elevator = lift(bts)

        # ---- 公共收益：加总；单独列账任一为是即 1 ----
        def total(k):
            vals = [money(x.get(k)) for x in g]
            vals = [v for v in vals if v is not None]
            return round(sum(vals), 4) if vals else None

        ledger = 1 if any(txt(x.get("公共收益是否单独列账")) == "是" for x in g) else 0
        ledger_way = next((txt(x.get("公共收益列账方式")) for x in g
                           if txt(x.get("公共收益列账方式"))), "")

        # ---- 质量：置信度取最低 ----
        confs = [txt(x["置信度"]) for x in g]
        conf = "low" if "low" in confs else ("medium" if "medium" in confs else "high")
        complete = 1 if any(
            txt(x.get("备案地址")) and txt(x.get("物业公司名2026")) and (x.get("物业费明细") or [])
            for x in g) else 0

        inc, spd, bal = (total("共有部分经营收入"), total("共有部分经营支出"),
                         total("共有部分经营余额"))

        flags = []
        if hh is not None and (hh < 6 or hh > 20000):
            flags.append("户数异常")
        if fee is not None and fee > 50:
            flags.append("备案物业费异常")
        if ye_n is not None and ye_n > 30:
            flags.append("业委会人数异常")
        if any(abs(v) > 100000 for v in (inc, spd, bal) if v is not None):
            flags.append("公共收益金额异常")
        if mode_src == "冲突取酬金制":
            flags.append("收费方式冲突")
        if any(x.get("链家为聚合页") for x in g):
            flags.append("链家聚合页")
        if conf == "low":
            flags.append("低置信匹配")
        if not complete:
            flags.append("备案不完整")

        out.append({
            "小区id": "LJ" + lid,
            "链家小区id": lid,
            "链家小区名": txt(first["链家小区名"]),
            "政府小区名": "、".join(dict.fromkeys(txt(x["政府小区名"]) for x in g if txt(x["政府小区名"]))),
            "备案项目数": len(g),
            "区": qu,
            "街道": st,
            "商圈": txt(first["商圈"]),
            "经度": txt(first["经度"]),
            "纬度": txt(first["纬度"]),
            "户数": hh,
            "户数2018": hh18,
            "户数变化": (hh - hh18) if hh is not None and hh18 is not None else None,
            "楼栋数": bl,
            "楼栋均户数": round(hh / bl, 1) if hh and bl else None,
            "建成年代": y_lj,
            "房龄": (2026 - y_lj) if y_lj else None,
            "单价2019": price,
            "物业公司2019": txt(first["物业公司名2019"]),
            "物业管理模式2019": mgmt_mode(first["物业公司名2019"]),
            "物业公司2026": next((txt(x["物业公司名2026"]) for x in g if txt(x["物业公司名2026"])), ""),
            "物业管理模式2026": mgmt_mode(next((x["物业公司名2026"] for x in g
                                         if txt(x["物业公司名2026"])), "")),
            "物业公司变更": change_label([txt(x["物业公司变更"]) for x in g]),
            "物业服务收费方式": mode,
            "收费方式判定": mode_src,
            "物业费": fee,
            "物业费_最低": fee_min,
            "物业费_档数": len(fees),
            "物业费_链家2019": lj_mid,
            "房屋性质": prop_main,
            "房屋性质_全部": "|".join(props),
            "建筑类型": bt,
            "电梯": elevator,
            "公共收益收入": inc,
            "公共收益支出": spd,
            "公共收益余额": bal,
            "公共收益单独列账": ledger,
            "公共收益列账方式": ledger_way,
            "业委会状态": best_ye,
            "业委会人数": ye_n,
            "备案登记完整": complete,
            "置信度": conf,
            "链家为聚合页": 1 if first.get("链家为聚合页") else 0,
            "是否住宅": 1 if first.get("是否住宅") else 0,
            "匹配方式": "、".join(dict.fromkeys(txt(x["匹配方式"]) for x in g)),
            "数据质量标记": ";".join(flags),
        })

    # 整数值的浮点转成 int，避免导出成 210.0 / 0.0 这种
    for rec in out:
        for k, v in list(rec.items()):
            if isinstance(v, float) and v.is_integer():
                rec[k] = int(v)

    out.sort(key=lambda r: (r["区"] == "", r["区"], r["街道"], r["链家小区名"]))
    return out


def main():
    db = json.load(open(SRC, encoding="utf-8"))
    rows = build(db["小区库"])
    names = ALL_FIELDS

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(names)
        for rec in rows:
            w.writerow([cell(rec[k]) for k in names])
    os.replace(tmp, OUT)

    with open(OUT, encoding="utf-8-sig") as f:
        h = [next(f) for _ in range(2)]
    if h[0].strip() == h[1].strip():
        sys.exit("!! 写出异常：第二行与表头相同")

    print(f"写出 {OUT}：{len(rows)} 行 × {len(names)} 列（源 {len(db['小区库'])} 条备案项目）\n")
    for k in ["业委会状态", "物业服务收费方式", "房屋性质", "置信度", "建筑类型", "电梯"]:
        c = collections.Counter(rec[k] for rec in rows)
        print(f"  {k}: {c.most_common(9)}")


if __name__ == "__main__":
    main()
