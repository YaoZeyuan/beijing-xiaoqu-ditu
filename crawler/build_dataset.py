#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成正式数据集 crawler/data/projects.json
==========================================
输入（原始抓取，含未脱敏的联系方式，不入库）
    raw_data/raw_projects.jsonl      住建委详情页 22 个原始字段
    raw_data/xiaoqu_list.md          区-街道-小区清单（Markdown 表格）

输出（入库）
    crawler/data/xiaoqu_streets.json 清洗后的街道清单
    crawler/data/projects.json       正式数据集（脱敏 + 物业费拆解 + 补街道）

比原始数据多做的事：
  1. 姓名只留第一个字、电话只留前 3 位（脱敏，见 anonymize.py）
  2. 「物业服务费用标准」从一行字符串拆成结构化明细
     "居住类-普通商品房-高层住宅:2.5(元/月.平方米)"
     -> {"业态":"居住类","房屋性质":"普通商品房","建筑类型":"高层住宅","单价":2.5,"单位":"元/月.平方米"}
  3. 补齐所属街道（原始数据只有区 + 地址），匹配不到填 "-"

用法:
    python build_dataset.py
    python build_dataset.py --raw xxx.jsonl --list-md yyy.md
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

import anonymize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
RAW_DIR = os.path.join(ROOT, "raw_data")

# ---------------------------------------------------------------- 物业费拆解

# 「物业服务费用标准」里三段的词表。有些小区只登记两段（如
# "居住类-高层住宅:2.5"），第二段其实是建筑类型而不是房屋性质，
# 所以按词表判定，不能按位置硬切。
CATEGORIES = {
    "居住类", "非居住类", "商住类", "综合类", "写字楼", "行政办公", "商业类",
}
NATURES = {
    "普通商品房", "房改房", "回迁房", "央产房", "保障房", "别墅",
    "自管公房", "直管公房", "其他", "其它", "其它非住宅", "非住宅",
}
BUILDINGS = {
    "高层住宅", "多层住宅有电梯", "多层住宅无电梯", "其它住宅", "非高层住宅",
    "其它非住宅", "多层非住宅有电梯", "多层非住宅无电梯",
}

FEE_PRICE_RE = re.compile(r"[:：]\s*([0-9]+(?:\.[0-9]+)?)")
FEE_UNIT_RE = re.compile(r"[（(]([^）)]*)[）)]")


def parse_fee(raw: str):
    """把「业态-性质-建筑类型:单价(单位)」拆成明细列表

    返回 (明细列表, 未识别片段列表)。空值返回 ([], [])。
    """
    if not raw:
        return [], []
    items, unknown = [], []
    for seg in re.split(r"[;；]", str(raw)):
        seg = seg.strip()
        if not seg:
            continue
        head = seg.split(":")[0].split("：")[0]
        parts = [p.strip() for p in head.split("-") if p.strip()]
        if not parts:
            continue

        category = parts[0]
        nature, building = None, None
        for p in parts[1:]:
            if p in BUILDINGS:
                building = building or p
            elif p in NATURES:
                nature = nature or p
            elif nature is None:
                nature = p          # 词表外的段落，先按性质位置放
                unknown.append(p)
            elif building is None:
                building = p
                unknown.append(p)

        m = FEE_PRICE_RE.search(seg)
        if not m:
            # 少数记录单价位置写的是字面量 null，属于"未填"，不是格式异常
            if "null" not in seg.lower():
                unknown.append(seg)
            continue
        price = float(m.group(1))
        u = FEE_UNIT_RE.search(seg)

        items.append({
            "业态": category,
            "房屋性质": nature or "-",
            "建筑类型": building or "-",
            "单价": price,
            "单位": (u.group(1).strip() if u else "-"),
        })
    return items, unknown


# ---------------------------------------------------------------- 街道清单

def norm_name(s: str) -> str:
    """小区名归一化：统一括号、去空格，用于跨源匹配"""
    s = (s or "").strip()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("\u3000", "")
    return re.sub(r"\s+", "", s)


def load_streets(path: str):
    """解析 Markdown 表格：| 城区 | 街道 | 小区名 |"""
    rows, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3:
                continue
            district, street = cells[0], cells[1]
            # 小区名里可能带竖线，多余的列并回名字
            name = "|".join(cells[2:]).strip()
            if district in ("城区", "") or set(district) <= set(":- "):
                continue
            if not street or not name:
                continue
            key = (district, street, norm_name(name))
            if key in seen:
                continue
            seen.add(key)
            rows.append({"城区": district, "街道": street, "小区名": name})
    return rows


# 住建委的区名 -> 清单里的城区名
DISTRICT_ALIAS = {
    "经开区": "北京经济技术开发区",
    "北京经济开发区": "北京经济技术开发区",
}


class StreetIndex:
    def __init__(self, rows):
        self.by_district_name = defaultdict(set)      # (区, 名) -> {街道}
        self.by_name = defaultdict(set)               # 名 -> {(区, 街道)}
        self.by_district = defaultdict(set)           # 区 -> {街道}
        for r in rows:
            d, s, n = r["城区"], r["街道"], norm_name(r["小区名"])
            self.by_district_name[(d, n)].add(s)
            self.by_name[n].add((d, s))
            self.by_district[d].add(s)

    def find(self, record):
        """返回 (街道, 来源, 可回填的区)

        来源: address / name / name_dup / name_only / none
        部分记录详情页只回了项目名称和业委会状态，区和地址都是空，这时
        如果清单里同名小区全市唯一，就连区一起回填。
        """
        d = DISTRICT_ALIAS.get((record.get("项目所在区") or "").strip(),
                               (record.get("项目所在区") or "").strip())
        n = norm_name(record.get("项目名称"))
        addr = (record.get("项目地址") or "").replace(" ", "").replace("\u3000", "")

        # 1) 地址里直接写了街道名，比按名字猜可靠
        cands = [s for s in self.by_district.get(d, ()) if s and s in addr]
        if cands:
            return max(cands, key=len), "address", ""

        # 2) 区内同名小区
        streets = self.by_district_name.get((d, n))
        if streets:
            return sorted(streets)[0], ("name" if len(streets) == 1 else "name_dup"), ""

        # 3) 同名小区在全市范围内唯一，用它所在的区和街道
        hits = self.by_name.get(n)
        if hits and len(hits) == 1:
            d2, s2 = next(iter(hits))
            return s2, "name_only", (d2 if not d else "")

        return "-", "none", ""


# ---------------------------------------------------------------- 主流程

OUT_FIELDS = [
    "project_no", "项目名称", "项目所在区", "所属街道", "街道来源",
    "项目地址", "建成年代",
    "项目负责人姓名", "项目负责人联系方式",
    "物业服务收费方式", "物业服务费用标准", "物业费明细",
    "物业共有部分经营收入", "物业共有部分经营支出", "共有部分经营余额",
    "公共收益是否单独列账", "列账方式",
    "是否成立业委会(物管会)", "业委会(物管会)人数",
    "业委会(物管会)负责人姓名", "业委会(物管会)负责人联系方式",
    "物业服务企业名称", "统一社会信用代码", "法定代表人", "企业注册地址",
    "上一周期综合评价等级",
]


def main():
    ap = argparse.ArgumentParser(description="生成正式数据集")
    ap.add_argument("--raw", default=os.path.join(RAW_DIR, "raw_projects.jsonl"))
    ap.add_argument("--list-md", default=os.path.join(RAW_DIR, "xiaoqu_list.md"))
    ap.add_argument("--out", default=os.path.join(DATA, "projects.json"))
    args = ap.parse_args()

    for p in (args.raw, args.list_md):
        if not os.path.exists(p):
            sys.exit(f"找不到输入文件：{p}")

    # 1) 街道清单
    streets = load_streets(args.list_md)
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "xiaoqu_streets.json"), "w", encoding="utf-8") as f:
        json.dump(streets, f, ensure_ascii=False, indent=1)
    idx = StreetIndex(streets)
    print(f"街道清单 {len(streets)} 条 / {len(idx.by_district)} 个城区 / "
          f"{len({(r['城区'], r['街道']) for r in streets})} 个街道")

    # 2) 原始记录：按 project_no 去重（成功记录优先），丢掉抓取失败行
    records, dropped = {}, 0
    with open(args.raw, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("error") or not rec.get("project_no"):
                dropped += 1
                continue
            prev = records.get(rec["project_no"])
            if prev is None or (not prev.get("项目名称") and rec.get("项目名称")):
                records[rec["project_no"]] = rec
    print(f"原始记录 {len(records)} 条（丢弃失败行 {dropped}）")

    # 3) 逐条处理
    out, fee_unknown = [], Counter()
    src_stat, fee_stat, fee_items_total = Counter(), Counter(), 0
    district_filled = 0
    for rec in records.values():
        items, unknown = parse_fee(rec.get("物业服务费用标准"))
        for u in unknown:
            fee_unknown[u] += 1
        street, source, district_fill = idx.find(rec)
        if district_fill:
            rec["项目所在区"] = district_fill
            district_filled += 1
        src_stat[source] += 1
        if items:
            fee_stat["有明细"] += 1
            fee_items_total += len(items)
        else:
            fee_stat["无明细"] += 1

        anonymize.mask_record(rec)
        row = {k: rec.get(k, "") for k in OUT_FIELDS if k not in
               ("所属街道", "街道来源", "物业费明细")}
        row["所属街道"] = street
        row["街道来源"] = source
        row["物业费明细"] = items
        # 按 OUT_FIELDS 顺序重排
        out.append({k: row.get(k, "") for k in OUT_FIELDS})

    out.sort(key=lambda r: (r["项目所在区"], r["所属街道"], r["项目名称"]))

    # 4) 一行一条的 JSON 数组：合法 JSON，体积小，diff 也看得懂
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("[\n")
        for i, r in enumerate(out):
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
            f.write(",\n" if i < len(out) - 1 else "\n")
        f.write("]\n")

    size = os.path.getsize(args.out) / 1024 / 1024
    print(f"\n✅ {args.out}  ({size:.1f} MB, {len(out)} 条)")
    print(f"   街道来源：{dict(src_stat)}")
    print(f"   按清单回填所属区：{district_filled} 条"
          f"（仍无区：{sum(1 for r in out if not r['项目所在区'])} 条）")
    print(f"   有物业费明细：{fee_stat['有明细']} 条（共 {fee_items_total} 档价格）"
          f" / 无：{fee_stat['无明细']} 条")
    if fee_unknown:
        print(f"   ⚠ 未识别的费用片段 {sum(fee_unknown.values())} 个，"
              f"Top: {fee_unknown.most_common(5)}")


if __name__ == "__main__":
    main()
