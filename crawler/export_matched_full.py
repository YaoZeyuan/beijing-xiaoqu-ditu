# -*- coding: utf-8 -*-
"""把匹配成功的备案项目导出成一份扁平 CSV（内部自用版）。

一行 = 一个备案项目（7,194 行），链家侧与政府侧字段合并在一张宽表里。
与 public_data/processed/matched.csv 的区别：
  - 含经纬度、链家链接、物业费明细、公共收益金额、统一社会信用代码
  - 嵌套的「物业费明细」拍平成可读文本 + 条数
输出：raw_data/exports/matched_full.csv（gitignore 内，不对外发布）
"""
import csv
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

SRC = "raw_data/lianjia/xiaoqu_db.json"
OUT_DIR = "raw_data/exports"
OUT = os.path.join(OUT_DIR, "matched_full.csv")

# (输出列名, 源字段, 说明)
COLS = [
    ("备案项目编号", "project_no", "政府备案库主键，可与源表对接"),
    ("链家小区id", "链家小区id", "链家 community_id"),
    ("小区id", "小区id", "指向公开数据集 xiaoqu 的主键，LJ+链家id"),
    ("备案登记名", "政府小区名", "政府备案登记的项目名"),
    ("链家小区名", "链家小区名", "链家页面上的小区名"),
    ("区", "区", "行政区"),
    ("街道", "街道", "所属街道"),
    ("商圈", "商圈", "链家商圈"),
    ("备案地址", "备案地址", "备案登记地址"),
    ("链家地址", "链家地址", "链家 location 原文，括号内为商圈"),
    ("经度", "经度", ""),
    ("纬度", "纬度", ""),
    ("链家链接", "链家链接", ""),
    ("链家单价2019", "链家单价2019", "2019 年链家挂牌单价，元/㎡"),
    ("户数", "户数", "链家当前户数"),
    ("户数2018", "户数2018", "2018-11 链家户数，用于看两年是否一致"),
    ("两年户数一致", "两年户数一致", "是 / 否"),
    ("户数存疑", "户数存疑", "户数缺失或 <6"),
    ("楼栋数", "楼栋数", ""),
    ("建成年代", "建成年代", "链家建成年代"),
    ("备案建成年代", "备案建成年代", "政府备案建成年代"),
    ("物业公司名2019", "物业公司名2019", "链家 2019 登记的物业公司"),
    ("物业公司名2026", "物业公司名2026", "备案 2026 登记的物业服务企业"),
    ("物业公司变更", "物业公司变更", "归一化后比对：已变更 / 未变更 / 疑似变更 / 从无物业到有物业 / 无法判断"),
    ("物业公司统一社会信用代码", "物业公司统一社会信用代码", "仅此表保留，公开数据集已剔除"),
    ("物业服务收费方式", "物业服务收费方式", "包干制 / 酬金制"),
    ("链家物业费", "物业费", "链家挂牌价，多为区间，如 2.05至5.5元/平米/月"),
    ("备案居住类物业费", "居住类物业费", "备案明细中居住类最低单价，元/月·㎡"),
    ("备案非居住类物业费", "非居住类物业费", "备案明细中非居住类最低单价，元/月·㎡"),
    ("房屋性质", "房屋性质", "普通商品房 / 房改房 / 回迁房 / 央产房 / 保障房 / 别墅 / 自管公房 / 直管公房，多值用竖线分隔"),
    ("物业费明细条数", None, "备案按业态+建筑类型拆分的档数"),
    ("物业费明细", None, "拍平文本：业态/房屋性质/建筑类型=单价，多条用分号分隔"),
    ("公共收益是否单独列账", "公共收益是否单独列账", "是 / 否"),
    ("公共收益列账方式", "公共收益列账方式", "会计列账 / 账户列账"),
    ("共有部分经营收入", "共有部分经营收入", "原始填报口径未统一，0 与空需谨慎解读"),
    ("共有部分经营支出", "共有部分经营支出", "同上"),
    ("共有部分经营余额", "共有部分经营余额", "同上"),
    ("业委会状态", "业委会状态", "业委会 / 物管会 / 均未成立"),
    ("业委会人数", "业委会人数", "业委会或物管会成员人数，未填则空"),
    ("备案登记完整", None, "备案地址、物业服务企业、物业费明细三项是否都填了"),
    ("匹配方式", "匹配方式", "命中的规则名或模型语义判定"),
    ("匹配代码", "匹配代码", "匹配方式的内部代码"),
    ("置信度", "置信度", "high / medium / low"),
    ("链家为聚合页", "链家为聚合页", "链家把多个小区合并成了一页"),
    ("链家地址门牌数", "链家地址门牌数", "链家地址里含几个门牌号"),
    ("共用同一链家小区的备案项目数", "共用同一链家小区的备案项目数", ">1 说明多个备案项目指向同一个链家小区"),
    ("是否住宅", "是否住宅", "按名称判定的粗筛，非官方口径"),
]


def fee_detail(items):
    """把物业费明细拍平成 '业态/房屋性质/建筑类型=单价' 文本。"""
    parts = []
    for x in items or []:
        seg = "/".join(v for v in (x.get("业态"), x.get("房屋性质"), x.get("建筑类型"))
                       if v and v != "-")
        price = x.get("单价")
        if seg and price not in (None, ""):
            parts.append(f"{seg}={price}")
    return "; ".join(parts)


PLACEHOLDER = {"暂无信息", "暂无", "无", "-", "—", "/"}


def money(v):
    """公共收益金额：源数据存在 '.5118' 这类前导 0 丢失和浮点尾噪，规整成正常小数。"""
    s = str(v or "").strip()
    if s in PLACEHOLDER or s == "":
        return ""
    if s.startswith("."):
        s = "0" + s
    elif s.startswith("-."):
        s = "-0" + s[1:]
    try:
        return f"{round(float(s), 4):.4f}".rstrip("0").rstrip(".")
    except ValueError:
        return s


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".")
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    s = str(v).strip()
    return "" if s in PLACEHOLDER else s


def main():
    db = json.load(open(SRC, encoding="utf-8"))
    rows = db["小区库"]
    os.makedirs(OUT_DIR, exist_ok=True)

    out = []
    for r in rows:
        det = r.get("物业费明细") or []
        rec = dict(r)
        rec["小区id"] = "LJ" + str(r["链家小区id"])
        rec["物业费明细条数"] = len(det)
        rec["物业费明细"] = fee_detail(det)
        rec["备案登记完整"] = "是" if (
            (r.get("备案地址") or "").strip()
            and (r.get("物业公司名2026") or "").strip()
            and det
        ) else "否"
        out.append({name: fmt(rec.get(src or name)) for name, src, _ in COLS})
        for k in ("共有部分经营收入", "共有部分经营支出", "共有部分经营余额"):
            out[-1][k] = money(rec.get(k))

    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([name for name, _, _ in COLS])
        for rec in out:
            w.writerow([rec[name] for name, _, _ in COLS])
    os.replace(tmp, OUT)

    with open(OUT, encoding="utf-8-sig") as f:
        head = [next(f) for _ in range(2)]
    if head[0].strip() == head[1].strip():
        sys.exit("!! 写出异常：第二行与表头相同")

    print(f"写出 {OUT}：{len(out)} 行 × {len(COLS)} 列")
    print(f"覆盖链家小区 {len({r['链家小区id'] for r in rows})} 个\n")

    # 各列填充率，便于自检
    for name, _, _ in COLS:
        n = sum(1 for rec in out if rec[name])
        print(f"  {name:<26}{n / len(out) * 100:>6.1f}%")


if __name__ == "__main__":
    main()
