#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
构建前端数据：把「区-街道-小区」清单与住建委列表/详情数据合并

数据来源（按优先级）：
  1. crawler/data/yz_list.json      区+街道+小区名  （全量 1 万+，主索引）
  2. crawler/data/list_all.json     住建委列表页抓取结果（小区名+企业+业委会状态）
  3. crawler/data/projects.jsonl    住建委详情页抓取结果（物业费+地址+建成年代）

用法: python build_data.py
"""
import json
import os
import re
import statistics
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "crawler", "data")
OUT = os.path.join(HERE, "public", "data", "projects.json")

# 备案主表：户数 / 挂牌均价 的补充来源（链家匹配 + AI 互联网检索）
BEIAN_MASTER = os.path.join(ROOT, "raw_data", "exports", "beian_master.csv")

DISTRICTS = [
    "东城区", "西城区", "朝阳区", "丰台区", "石景山区", "海淀区", "门头沟区",
    "房山区", "通州区", "顺义区", "昌平区", "大兴区", "怀柔区", "平谷区",
    "密云区", "延庆区",
]
# 经济技术开发区地理上属大兴，地图只有 16 个区面
DISTRICT_MERGE = {"北京经济技术开发区": "大兴区"}

FEE_RE = re.compile(r":\s*([0-9]+(?:\.[0-9]+)?)\s*\(\s*元\s*/\s*月\s*[.·]?\s*平\s*方\s*米\s*\)")


def norm_name(s: str) -> str:
    """小区名归一化，用于跨源匹配"""
    s = (s or "").strip()
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", "", s)
    return s


FEE_VALID_MAX = 20.0   # 住宅物业费上限（元/㎡·月），超过视为申报录入异常，不参与统计


def load_beian_scale():
    """备案主表 → {备案编号: (户数, 户数来源, 户数口径, 共享键, 挂牌均价, 均价来源)}

    户数：链家匹配（一对一）优先，其次 AI 互联网检索；均价同理。
    来源标签会一路带到前端，用户能看出这个数是官方匹配来的还是检索来的。

    口径（AI户数口径）决定这个数能不能参与合计：
      · 整小区合计·分区未拆 —— 多条备案共用同一个小区总数，只能按链家id算一次
    共享键就取链家id，前端聚合时用它去重。
    """
    import csv

    def _num(v):
        try:
            x = float(str(v).strip())
            return int(x) if x == int(x) else x
        except (TypeError, ValueError):
            return None

    out = {}
    if not os.path.exists(BEIAN_MASTER):
        print(f"  ⚠ 找不到 {BEIAN_MASTER}，户数/均价将全部为空")
        return out
    with open(BEIAN_MASTER, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            hh_lj = _num(r.get("户数"))
            hh_ai = _num(r.get("AI户数"))
            hh, hh_src = (hh_lj, "链家") if hh_lj else (hh_ai, "AI") if hh_ai else (None, "")
            scope = "" if hh_lj else (r.get("AI户数口径") or "")
            # 只有「分区未拆」这一种是共享值，其余都是一条备案自己的户数
            shared = bool(hh_ai) and not hh_lj and scope.endswith("分区未拆")
            key = (r.get("链家id") or r["备案编号"]) if shared else ""
            pr_lj = _num(r.get("小区均价"))
            pr_ai = _num(r.get("AI均价"))
            pr, pr_src = (pr_lj, "链家") if pr_lj else (pr_ai, "AI") if pr_ai else (None, "")
            if hh or pr:
                out[r["备案编号"]] = (hh, hh_src, scope, key, pr, pr_src)
    return out


def scale_fields(pid, beian):
    """按备案编号取户数/均价字段；查无备案号时返回空字段"""
    hh, hh_src, scope, key, pr, pr_src = beian.get(
        pid or "", (None, "", "", "", None, ""))
    return {"hh": hh, "hhSrc": hh_src, "hhScope": scope, "hhKey": key,
            "price": pr, "priceSrc": pr_src}


def fee_is_valid(v):
    return v is not None and 0 < v <= FEE_VALID_MAX


def fee_breakdown(items):
    """把一个项目的物业费明细拆成「区间 + 档数 + 构成」

    住建委的「物业服务费用标准」允许一个项目按业态/房屋性质/建筑类型分档登记，
    例如同一个小区：普通商品房-多层有电梯 2.58、回迁房-高层住宅 1.0。
    只报一个数会误导——业主会以为回迁房也按 2.58 收（或反过来）。

    返回 (最低, 最高, 有效档数, 明细列表或 None)。区间只统计居住类的有效单价：
    0 是常见的占位未填、>20 基本是录入笔误，两者都不进区间，但在明细里保留并标注。
    """
    if not items:
        return None, None, 0, None
    live = []
    for it in items:
        if (it.get("业态") or "") != "居住类":
            continue
        p = it.get("单价")
        if isinstance(p, (int, float)) and 0 < p <= FEE_VALID_MAX:
            live.append(float(p))

    lo = round(min(live), 2) if live else None
    hi = round(max(live), 2) if live else None

    # 只有「唯一一条居住类有效档」时无需解释；其余情况都要把构成摆出来
    noisy = len(live) >= 2 or any(
        (it.get("业态") or "") != "居住类"
        or not isinstance(it.get("单价"), (int, float))
        or it.get("单价") <= 0
        or it.get("单价") > FEE_VALID_MAX
        for it in items)
    detail = None
    if noisy:
        detail = [
            {
                "kind": it.get("业态") or "-",
                "prop": it.get("房屋性质") or "-",
                "build": it.get("建筑类型") or "-",
                "price": float(it["单价"]) if isinstance(it.get("单价"), (int, float)) else None,
            }
            for it in items
        ]
    return lo, hi, len(live), detail


def parse_fee(raw: str):
    """从「业态:价格(元/月.平方米)」列表里取住宅物业费

    一个小区常同时登记多个业态（高层住宅/多层住宅/商业等），直接取中位数会被
    非住宅业态拉高。策略：只看居住类、剔除 0 占位值，优先取住宅主体业态：
    高层住宅 > 多层住宅无电梯 > 其它居住类。
    """
    if not raw:
        return []
    groups = {"高层": [], "无电梯多层": [], "其它": []}
    for seg in re.split(r"[;；]", str(raw)):
        m = FEE_RE.search(seg)
        if not m:
            continue
        tag = seg.split(":")[0].split("：")[0]
        if "非居住类" in tag:
            continue                       # 写字楼/商业，不是住宅小区
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if not (0 < v <= 100):
            continue
        if "居住类" not in tag:
            continue
        if "高层住宅" in tag:
            groups["高层"].append(v)
        elif "多层住宅无电梯" in tag:
            groups["无电梯多层"].append(v)
        else:
            groups["其它"].append(v)
    for k in ("高层", "无电梯多层", "其它"):
        if groups[k]:
            vals = sorted(groups[k])
            n = len(vals)
            return [vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2]
    return []


def fees_from_items(items):
    """从结构化明细里取住宅物业费，优先级与 parse_fee 一致：
    高层 > 多层无电梯 > 其它居住类，组内取中位数。

    明细由 crawler/build_dataset.py 从「物业服务费用标准」拆出，非居住类已在
    明细里单独标出，这里只取居住类。
    """
    if not items:
        return []
    groups = {"高层": [], "无电梯多层": [], "其它": []}
    for it in items:
        if (it.get("业态") or "") != "居住类":
            continue
        p = it.get("单价")
        if not isinstance(p, (int, float)) or not (0 < p <= 100):
            continue
        b = it.get("建筑类型") or ""
        if "高层住宅" in b:
            groups["高层"].append(p)
        elif "多层住宅无电梯" in b:
            groups["无电梯多层"].append(p)
        else:
            groups["其它"].append(p)
    for k in ("高层", "无电梯多层", "其它"):
        if groups[k]:
            vals = sorted(groups[k])
            n = len(vals)
            return [vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2]
    return []


def build_fee_fields(items, raw_fee_text):
    """物业费相关的全部输出字段

    主值 fee 的口径保持原样（主力建筑类型组内取中位数），用于排序、着色和均价统计；
    区间 feeMin/feeMax 另有口径（居住类有效单价的最小/最大值），只用于展示。
    两者可能不一致——比如富贵园主值 1.00（高层组里两档回迁房），区间 1.00–2.58，
    这正是需要把构成列出来的原因。
    """
    fees = fees_from_items(items) or parse_fee(raw_fee_text)
    main = round(statistics.median(fees), 2) if fees else None
    lo, hi, tiers, detail = fee_breakdown(items)
    out = {
        "fee": main,
        "feeOk": fee_is_valid(main),
        "feeMin": lo,
        "feeMax": hi,
        "feeTiers": tiers,
    }
    if detail:
        out["fees"] = detail
    return out


def normalize_regime(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "未知"
    if "物管会" in s and "业委会" not in s:
        return "物管会"
    if "业委会" in s:
        return "业委会"
    if "未成立" in s or "均未" in s:
        return "未成立"
    return "未知"


def load_json(path, default):
    if not os.path.exists(path):
        print(f"  · 跳过（不存在）{os.path.basename(path)}")
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    print("构建前端数据...")

    # 1) 主索引：区-街道-小区清单（由 crawler/build_dataset.py 从 Markdown 清洗而来）
    raw_list = load_json(os.path.join(DATA, "xiaoqu_streets.json"), [])
    rows = [[r.get("城区"), r.get("街道"), r.get("小区名")] for r in raw_list]
    print(f"  · 小区清单 {len(rows)} 条")

    # 2) 列表页抓取（by 区 + 名字）
    list_items = load_json(os.path.join(DATA, "list_all.json"), [])
    list_by_key = {}
    for it in list_items:
        k = norm_name(it.get("项目名称"))
        if k:
            list_by_key.setdefault(k, []).append(it)
    print(f"  · 列表页数据 {len(list_items)} 条（覆盖 {len(list_by_key)} 个不同名称）")

    # 3) 正式数据集（已脱敏、已拆物业费、已补街道）
    detail_rows = []
    p = os.path.join(DATA, "projects.json")
    if os.path.exists(p):
        _dedupe = {}
        for d in load_json(p, []):
            if d.get("error") or not d.get("项目名称"):
                continue
            _dedupe[d["project_no"]] = d
        detail_rows = list(_dedupe.values())
    detail_by_key = {}
    detail_by_name = {}
    for d in detail_rows:
        dt = DISTRICT_MERGE.get((d.get("项目所在区") or "").strip(),
                                (d.get("项目所在区") or "").strip())
        detail_by_key[(norm_name(d.get("项目名称")), dt)] = d
        detail_by_name.setdefault(norm_name(d.get("项目名称")), []).append(d)
    print(f"  · 详情页数据 {len(detail_rows)} 条")

    # 4) 街道名索引：用于从「项目地址」直接定位街道（详情页自带区+地址，比按名字匹配可靠）
    street_names = {}
    for r in rows:
        if not isinstance(r, list) or len(r) != 3:
            continue
        d_sc = DISTRICT_MERGE.get(r[0], r[0])
        street_names.setdefault(d_sc, set()).add(r[1])

    def street_from_addr(district, addr):
        """从项目地址里找出街道名（同区内取最长匹配）"""
        addr = (addr or "").replace(" ", "")
        best = ""
        for s in street_names.get(district, ()):
            if s and s in addr and len(s) > len(best):
                best = s
        return best

    projects = []
    seen = set()
    used_detail = set()
    matched_list = matched_detail = 0
    beian = load_beian_scale()

    for r in rows:
        if not isinstance(r, list) or len(r) != 3:
            continue
        district, street, name = r
        district = DISTRICT_MERGE.get(district, district)
        key = (district, street, norm_name(name))
        if key in seen:
            continue
        seen.add(key)

        nkey = norm_name(name)
        li = list_by_key.get(nkey, [])
        # 同名时优先取区一致的
        li_hit = next((x for x in li if x.get("是否成立业委会(物管会)")), li[0] if li else None)
        # 详情匹配：优先「同名 + 同区」，避免跨区同名小区错配
        det = detail_by_key.get((nkey, district))
        if det is None:
            for cand in detail_by_name.get(nkey, []):
                cd = DISTRICT_MERGE.get((cand.get("项目所在区") or "").strip(),
                                        (cand.get("项目所在区") or "").strip())
                if not cd or cd == district:
                    det = cand
                    break
        if det:
            used_detail.add(det.get("project_no"))
            # 详情页带的街道比按名字对齐的清单更准
            ds = (det.get("所属街道") or "").strip()
            if ds and ds != "-":
                street = ds

        regime_raw = (det or {}).get("是否成立业委会(物管会)") or \
                     (li_hit or {}).get("是否成立业委会(物管会)") or ""
        feefields = build_fee_fields(
            (det or {}).get("物业费明细"),
            (det or {}).get("物业服务费用标准"))
        if li_hit:
            matched_list += 1
        if det:
            matched_detail += 1

        year = (det or {}).get("建成年代") or ""
        ym = re.search(r"(19|20)\d{2}", str(year))

        projects.append({
            "name": name,
            "district": district,
            "street": street,
            "regime": normalize_regime(regime_raw),
            **feefields,
            "feeMode": (det or {}).get("物业服务收费方式") or "",
            "company": (det or {}).get("物业服务企业名称") or (li_hit or {}).get("物业服务企业名称") or "",
            "year": int(ym.group(0)) if ym else None,
            "committeeSize": (det or {}).get("业委会(物管会)人数") or "",
            "id": (det or {}).get("project_no") or (li_hit or {}).get("project_no") or "",
            **scale_fields((det or {}).get("project_no") or (li_hit or {}).get("project_no"), beian),
        })

    # 5) 补录：详情页里有、但清单里名字对不上的小区（用「区 + 地址街道」定位）
    added = 0
    for d in detail_rows:
        if d.get("project_no") in used_detail:
            continue
        district = DISTRICT_MERGE.get((d.get("项目所在区") or "").strip(),
                                      (d.get("项目所在区") or "").strip())
        if district not in DISTRICTS:
            continue
        name = (d.get("项目名称") or "").strip()
        if not name:
            continue
        street = (d.get("所属街道") or "").strip()
        if not street or street == "-":
            street = street_from_addr(district, d.get("项目地址")) or "未标注街道"
        key = (district, street, norm_name(name))
        if key in seen:
            continue
        seen.add(key)
        feefields = build_fee_fields(d.get("物业费明细"), d.get("物业服务费用标准"))
        ym = re.search(r"(19|20)\d{2}", str(d.get("建成年代") or ""))
        projects.append({
            "name": name,
            "district": district,
            "street": street,
            "regime": normalize_regime(d.get("是否成立业委会(物管会)")),
            **feefields,
            "feeMode": d.get("物业服务收费方式") or "",
            "company": d.get("物业服务企业名称") or "",
            "year": int(ym.group(0)) if ym else None,
            "committeeSize": d.get("业委会(物管会)人数") or "",
            "id": d.get("project_no") or "",
            **scale_fields(d.get("project_no"), beian),
        })
        added += 1
    if added:
        print(f"  · 详情页补录 {added} 条（清单里名称对不上的小区）")

    dorder = {d: i for i, d in enumerate(DISTRICTS)}
    projects.sort(key=lambda x: (dorder.get(x["district"], 99), x["street"], x["name"]))

    districts_present = sorted({p["district"] for p in projects},
                               key=lambda x: dorder.get(x, 99))
    meta = {
        "source": "北京市住房和城乡建设委员会 · 物业项目信息查询",
        "sourceUrl": "http://bjjs.zjw.beijing.gov.cn/eportal/ui?pageId=53619997",
        # 政府详情页直链模板，把 {id} 换成项目的 project_no 即可打开官方页面
        "detailUrl": ("http://bjjs.zjw.beijing.gov.cn/eportal/ui"
                      "?pageId=53619997&t=toDetail&project_no={id}"),
        "nameListSource": "截止202610 北京全部小区列表（满意度调查问卷整理）",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": len(projects),
        "withFee": sum(1 for p in projects if p["feeOk"]),
        "feeSuspect": sum(1 for p in projects if p["fee"] and not p["feeOk"]),
        "feeValidMax": FEE_VALID_MAX,
        # 多档物业费的小区数 / 各档价差不为 0（即列表上会显示区间）的小区数 / 带构成明细的小区数
        "withFeeTiers": sum(1 for p in projects if p["feeTiers"] >= 2),
        "withFeeRange": sum(1 for p in projects
                            if p["feeTiers"] >= 2 and p["feeMin"] is not None
                            and p["feeMax"] is not None and p["feeMin"] != p["feeMax"]),
        "withFeeItems": sum(1 for p in projects if p.get("fees")),
        "feeMode": {
            "包干制": sum(1 for p in projects if p["feeMode"] == "包干制"),
            "酬金制": sum(1 for p in projects if p["feeMode"] == "酬金制"),
        },
        "withRegime": sum(1 for p in projects if p["regime"] != "未知"),
        "withHH": sum(1 for p in projects if p["hh"]),
        "withHHAI": sum(1 for p in projects if p["hh"] and p["hhSrc"] == "AI"),
        "withPrice": sum(1 for p in projects if p["price"]),
        "withPriceAI": sum(1 for p in projects if p["price"] and p["priceSrc"] == "AI"),
        "streets": len({(p["district"], p["street"]) for p in projects}),
        "districts": districts_present,
        "coverage": {
            "listMatched": matched_list,
            "detailMatched": matched_detail,
        },
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # 输出带缩进的 JSON，便于直接打开查阅；newline="\n" 避免 Windows 下写出 CRLF
    # 让 git 反复判定为已修改（.gitattributes 里该文件是 eol=lf）
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"meta": meta, "projects": projects}, f, ensure_ascii=False,
                  indent=2)

    size = os.path.getsize(OUT) / 1024
    print(f"\n✅ {OUT}  ({size:.0f} KB)")
    print(f"   小区 {meta['total']} | 街道 {meta['streets']} | 区 {len(meta['districts'])}")
    print(f"   有业委会状态 {meta['withRegime']} | 有物业费 {meta['withFee']}")
    print(f"   有户数 {meta['withHH']}（其中AI补查 {meta['withHHAI']}）| 有挂牌均价 {meta['withPrice']}（AI {meta['withPriceAI']}）")
    print(f"   列表匹配 {matched_list} | 详情匹配 {matched_detail}")


if __name__ == "__main__":
    main()
