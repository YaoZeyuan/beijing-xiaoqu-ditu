# -*- coding: utf-8 -*-
"""把链家小区数据（2018.11 / 2019.02）匹配到住建委物业项目清单，补充户数等字段。

数据来源: https://github.com/shuijingoj/LianJiaCommunityData
    raw_data/lianjia/baseinfo_201811.csv
    raw_data/lianjia/baseinfo_201902.csv

用法:
    python match_lianjia.py

输出 raw_data/lianjia/
    matched.csv        匹配结果（以物业项目为主键）
    match_stats.json   漏斗统计
"""

import collections
import csv
import difflib
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
OUT = os.path.join(ROOT, "raw_data", "lianjia")
PROJECTS = os.path.join(BASE, "data", "projects.json")
LJ_2018 = os.path.join(OUT, "baseinfo_201811.csv")
LJ_2019 = os.path.join(OUT, "baseinfo_201902.csv")

CN_NUM = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
          "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}

CN_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9}
CN_TEN_RE = re.compile(r"([一二三四五六七八九])?十([一二三四五六七八九])?")

# 普通后缀（可整层剥掉）
SUFFIX_RE = re.compile(
    r"(小区|家园|公寓|花园|新村|大厦|宿舍|楼|苑|园|里|院|城|府|区)$")

# 允许的"多对一"修饰尾巴：项目名比链家名多出来的部分
TAIL_RE = re.compile(
    r"^("
    r"[0-9]+(-[0-9]+)?号楼?"
    r"|[0-9]+区"
    r"|[0-9]+期"
    r"|[甲乙丙丁戊己庚辛]"
    r"|[0-9]+号院?"
    r"|[东西南北](院|区|里)?"
    r"|楼?"
    r")+$")

# 备案库与链家常用的开发区写法不同，统一到「经开区」。
# 注意 lj_district 会先去掉「小区」再补「区」，所以别名里要写补过之后的形式。
DISTRICT_MAP = {
    "亦庄开发区": "经开区",
    "亦庄开发区区": "经开区",
    "经济技术开发区": "经开区",
    "北京经济技术开发区": "经开区",
    "经开区": "经开区",
}


def canon_district(d):
    """把各方写法收敛成同一个区名。空值原样返回。"""
    d = (d or "").strip()
    if not d:
        return ""
    if d in DISTRICT_MAP:
        return DISTRICT_MAP[d]
    if not d.endswith("区"):
        d += "区"
    return DISTRICT_MAP.get(d, d)

# 链家里存在一类"街区聚合页"：白广路、枣林前街、中关村南大街、东四十条。
# 它们是整条街/整片胡同的汇总页，不是单一小区，户数不能当小区户数用。
AGG_RE = re.compile(r"(路|街|大街|胡同|巷|条|道|里弄|村)$")
REAL_SUFFIX_RE = re.compile(r"(院|小区|家园|公寓|花园|新村|大厦|宿舍|楼|苑|园|城|府|区|邸|墅)$")


def is_aggregate(name):
    """链家小区名看起来像街道/胡同聚合页（且不像具体院落）。"""
    n = norm(name)
    if not n:
        return False
    return bool(AGG_RE.search(n)) and not bool(REAL_SUFFIX_RE.search(n))


def load_lj(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def cn2num(s):
    """中文数字转阿拉伯：十七→17、二十→20、二十五→25，纯「十」→10。"""
    def rep(m):
        a, b = m.group(1), m.group(2)
        if a and b:
            return str(CN_DIGIT[a] * 10 + CN_DIGIT[b])
        if a:
            return str(CN_DIGIT[a] * 10)
        if b:
            return str(10 + CN_DIGIT[b])
        return "10"
    return CN_TEN_RE.sub(rep, s)


def norm(s):
    """名称归一化：全角转半角、去空格、去括号内容、去北京前缀、中文数字转阿拉伯。"""
    s = re.sub(r"\s+", "", s or "")
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^北京市?", "", s)
    s = cn2num(s)
    for k, v in CN_NUM.items():
        s = s.replace(k, v)
    return s


def num_sig(s):
    """名称中的数字/甲乙丙签名，用于防止门牌号不同的误配。"""
    return re.findall(r"\d+|[甲乙丙丁戊己]", s or "")


def strip_suffix(s):
    prev = None
    while prev != s:
        prev = s
        s = SUFFIX_RE.sub("", s)
    return s


def lj_district(row):
    d = row["hier3"].replace("小区", "") + "区"
    return canon_district(d)


def loc_parts(loc):
    """链家 location 形如：「(东城东花市)东花市南里一区, 东花市南里二区」。

    括号里是商圈，后面逗号分隔的是备案门牌地址。这些地址才是和住建委
    备案项目名同一套命名体系的名字，匹配价值高于 community_name。
    """
    loc = (loc or "").strip()
    m = re.match(r"^[（(]([^）)]*)[）)](.*)$", loc)
    tail = m.group(2) if m else loc
    return [p.strip() for p in re.split(r"[,，]", tail) if p.strip()]


def hh(v):
    m = re.match(r"^(\d+)户$", (v or "").strip())
    return int(m.group(1)) if m else None


def bd(v):
    m = re.match(r"^(\d+)栋$", (v or "").strip())
    return int(m.group(1)) if m else None


def norm_street(s):
    s = (s or "").strip()
    for suf in ("街道办事处", "街道", "地区", "镇", "乡"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s


def street_score(proj_street, lj_row):
    """街道与链家商圈的吻合程度，仅用于同分消歧。"""
    st = norm_street(proj_street)
    biz = (lj_row.get("hier4") or "").replace("小区", "").strip()
    if not st or not biz or st == "-":
        return 0
    if st == biz:
        return 3
    if st in biz or biz in st:
        return 2
    loc = lj_row.get("location") or ""
    if st and st in loc:
        return 1
    return 0


def build_index(rows):
    idx = collections.defaultdict(list)
    addr_idx = collections.defaultdict(list)
    for r in rows:
        d = lj_district(r)
        n = norm(r["community_name"])
        keys = {n, strip_suffix(n)}
        for k in keys:
            if len(k) >= 2:
                idx[(d, k)].append(r)
                idx[("*", k)].append(r)     # 区名缺失时的全北京兜底
        # 门牌地址别名：链家 community_name 常是市场俗称（首开璞瑅公馆），
        # location 里才是备案名（紫芳园五区），两边都要能查到同一个小区。
        for part in loc_parts(r["location"]):
            pn = norm(part)
            if len(pn) < 3:
                continue
            for k in {pn, strip_suffix(pn)}:
                if len(k) >= 3:
                    addr_idx[(d, k)].append(r)
                    addr_idx[("*", k)].append(r)
    # 同区全部小区，供前后缀匹配
    by_district = collections.defaultdict(list)
    for r in rows:
        by_district[lj_district(r)].append(r)
        by_district["*"].append(r)
    for d in by_district:
        by_district[d].sort(key=lambda x: -len(norm(x["community_name"])))
    return idx, by_district, addr_idx


def pick(cands, proj):
    """多个候选时用街道/商圈消歧；无信息则返回 None。"""
    if len(cands) == 1:
        return cands[0], "unique"
    scored = sorted(((street_score(proj.get("所属街道"), c), c) for c in cands),
                    key=lambda x: -x[0])
    if scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1], "street_disambig"
    return None, "ambiguous"


def match_project(proj, idx, by_district, addr_idx=None):
    d = canon_district(proj.get("项目所在区")) or "*"
    raw = proj.get("项目名称") or ""
    n = norm(raw)
    if len(n) < 2:
        return None, "empty_name"

    # 规则1/2: 归一化同名
    cands = {}
    for k in {n, strip_suffix(n)}:
        for r in idx.get((d, k), []):
            cands[r["community_id"]] = r
    if cands:
        r, how = pick(list(cands.values()), proj)
        if r:
            rule = "exact" if norm(r["community_name"]) == n else "suffix_normalized"
            return (r, rule), how
        return None, "ambiguous_same_name"

    # 规则2b: 用链家 location 里的门牌地址反查（备案名 vs 市场俗称的主要通道）
    if addr_idx is not None:
        cands = {}
        for k in {n, strip_suffix(n)}:
            for r in addr_idx.get((d, k), []):
                cands[r["community_id"]] = r
        if cands:
            r, how = pick(list(cands.values()), proj)
            if r:
                return (r, "loc_address"), how
            return None, "ambiguous_loc_address"

    # 区名缺失时只做精确/地址级匹配，不做前缀与模糊，避免跨区误配
    if d == "*":
        return None, "no_district_no_match"

    # 规则3: 多对一，项目名 = 链家名 + 楼栋/区/期 修饰
    best = []
    for r in by_district.get(d, []):
        ln = norm(r["community_name"])
        if len(ln) < 3:
            continue
        if n.startswith(ln):
            tail = n[len(ln):]
        elif ln.startswith(n) and len(n) >= 4:
            tail = ln[len(n):]
        else:
            continue
        if tail and TAIL_RE.match(tail):
            best.append((len(ln), r, tail))
    if best:
        best.sort(key=lambda x: -x[0])
        top_len = best[0][0]
        top = [x for x in best if x[0] == top_len]
        cands = {x[1]["community_id"]: x[1] for x in top}
        r, how = pick(list(cands.values()), proj)
        if r:
            return (r, "unit_prefix"), how
        return None, "ambiguous_prefix"

    # 规则4: 同区名称高度相似（标点/写法差异），强制数字签名一致防门牌号误配
    best = []
    sig = num_sig(n)
    for r in by_district.get(d, []):
        ln = norm(r["community_name"])
        if not ln or abs(len(ln) - len(n)) > 4 or ln[0] != n[0]:
            continue
        if num_sig(ln) != sig:
            continue
        s = difflib.SequenceMatcher(None, n, ln).ratio()
        if s >= 0.84:
            best.append((s, r))
    if best:
        best.sort(key=lambda x: -x[0])
        if len(best) == 1 or best[0][0] - best[1][0] > 0.03:
            return (best[0][1], "fuzzy_name"), "unique"
        return None, "ambiguous_fuzzy"

    return None, "no_match"


def build_xiaoqu_table(rows_out):
    """把项目级结果压成「链家小区」级主表，供分析使用。

    一个链家小区可能对应多个备案项目（一期/二期/不同楼栋各自备案），
    这里按 community_id 去重，并保留对应项目数，方便判断户数归属。
    """
    usable = [r for r in rows_out
              if r.get("lj_community_id") and r.get("置信度") in ("high", "medium")]
    by = collections.defaultdict(list)
    for r in usable:
        by[r["lj_community_id"]].append(r)

    out = []
    for cid, v in by.items():
        r = v[0]
        st = {x["业委会状态"] for x in v if x["业委会状态"]}
        out.append({
            "区": r["区"], "街道": r["街道"], "lj_community_id": cid,
            "小区名": r["lj_name"],
            "链家名与备案名一致": int(r["匹配"] in ("exact", "suffix_normalized", "fuzzy_name")),
            "户数": r["link_households"], "户数2018": r["households_2018"],
            "两期一致": r["户数一致"], "楼栋数": r["lj_buildings"],
            "链家地址数": r["链家地址数"], "地址": r["lj_address"],
            "商圈": r["lj_biz_area"], "经度": r["lng"], "纬度": r["lat"],
            "建成年代": r["lj_age"], "物业费": r["lj_fee"], "物业公司": r["lj_property_co"],
            "2019参考均价": r["lj_unit_price_2019"], "链家链接": r["lj_url"],
            "业委会状态": "/".join(sorted(st)),
            "对应备案项目数": len(v),
        })
    cols = list(out[0]) if out else []
    path = os.path.join(OUT, "xiaoqu_with_households.csv")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(sorted(out, key=lambda x: (x["区"] or "", x["街道"] or "", x["小区名"] or "")))
    try:
        os.replace(tmp, path)
    except PermissionError:
        # 目标文件被 Excel / 预览占用时保留临时文件，别把结果丢了
        print(f"[warn] {path} 被占用，最新结果写在 {tmp}")
    return len(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    lj19 = load_lj(LJ_2019)
    lj18 = load_lj(LJ_2018)
    by18 = {r["community_id"]: r for r in lj18}
    idx, by_district, addr_idx = build_index(lj19)
    proj = json.load(open(PROJECTS, encoding="utf-8"))

    stats = collections.Counter()
    rows_out = []
    for p in proj:
        res, why = match_project(p, idx, by_district, addr_idx)
        stats[why] += 1
        base = {
            "project_no": p.get("project_no"),
            "项目名称": p.get("项目名称"),
            "区": p.get("项目所在区"),
            "街道": p.get("所属街道"),
            "业委会状态": p.get("是否成立业委会(物管会)"),
            "物业费标准": p.get("物业服务费用标准"),
            "建成年代": p.get("建成年代"),
        }
        if not res:
            base["匹配"] = why
            rows_out.append(base)
            continue
        r, rule = res
        stats["matched"] += 1
        h18 = hh(by18.get(r["community_id"], {}).get("house_amount"))
        h19 = hh(r["house_amount"])
        agg = is_aggregate(r["community_name"])
        consistent = "" if (h18 is None or h19 is None) else int(h18 == h19)
        if agg:
            conf = "low"          # 街区聚合页，不是单一小区
        elif len(loc_parts(r["location"])) > 1:
            # 一个链家条目对应多个门牌（如「北礼士路」含 68 号、191 号），户数是合计
            conf = "medium"
        elif rule in ("exact", "suffix_normalized", "loc_address"):
            conf = "high" if consistent == 1 else "medium"
        else:
            conf = "medium"       # 楼栋/单元级多对一，名称可靠但户数是整个小区
        base.update({
            "匹配": rule,
            "置信度": conf,
            "链家为聚合页": int(agg),
            "链家地址数": len(loc_parts(r["location"])),
            "link_households": h19,
            "households_2018": h18,
            "户数一致": consistent,
            "lj_community_id": r["community_id"],
            "lj_name": r["community_name"],
            "lj_buildings": bd(r["building_amount"]),
            "lj_address": r["location"],
            "lj_biz_area": (r.get("hier4") or "").replace("小区", ""),
            "lng": r["longitude"],
            "lat": r["latitude"],
            "lj_age": r["age"],
            "lj_fee": r["management_fee"],
            "lj_property_co": r["management_co"],
            "lj_unit_price_2019": r["unit_price"],
            "lj_url": r["url"],
        })
        rows_out.append(base)

    cols = ["project_no", "项目名称", "区", "街道", "业委会状态", "建成年代",
            "物业费标准", "匹配", "置信度", "链家为聚合页", "链家地址数", "link_households",
            "households_2018", "户数一致", "共享项目数",
            "lj_community_id", "lj_name", "lj_buildings", "lj_address", "lj_biz_area",
            "lng", "lat", "lj_age", "lj_fee", "lj_property_co",
            "lj_unit_price_2019", "lj_url"]

    # 同一个链家小区被多个物业项目指向时，户数会被重复计入，需标记
    share = collections.Counter(r["lj_community_id"] for r in rows_out
                                if r.get("lj_community_id"))
    for r in rows_out:
        if r.get("lj_community_id"):
            r["共享项目数"] = share[r["lj_community_id"]]
    out_csv = os.path.join(OUT, "matched.csv")
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows_out, key=lambda x: (x.get("区") or "", x.get("街道") or "",
                                                 x.get("项目名称") or "")):
            w.writerow(r)

    # 统计
    matched = [r for r in rows_out if r.get("lj_community_id")]
    uniq_lj = {r["lj_community_id"] for r in matched}
    xiaoqu_n = build_xiaoqu_table(rows_out)
    both = [r for r in matched if r.get("households_2018") is not None
            and r.get("link_households") is not None]
    consistent = sum(1 for r in both if r["households_2018"] == r["link_households"])
    summary = {
        "projects": len(proj),
        "matched": len(matched),
        "match_rate": round(len(matched) / len(proj) * 100, 2),
        "unique_lianjia_communities": len(uniq_lj),
        "xiaoqu_table_rows": xiaoqu_n,
        "with_households": sum(1 for r in matched if r.get("link_households")),
        "two_year_consistent": consistent,
        "two_year_compared": len(both),
        "confidence": dict(collections.Counter(r["置信度"] for r in matched)),
        "aggregate_pages": sum(1 for r in matched if r.get("链家为聚合页") == 1),
        "reasons": dict(stats),
    }
    json.dump(summary, open(os.path.join(OUT, "match_stats.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
