"""
从区政府「街镇名片 / 社区简介」采集小区户数（严格匹配版）
=========================================================
数据源（丰台）：
  https://www.bjft.gov.cn/xxfb/xxgkmp/gkmpjz/{街镇代码}/
  街镇页列出下属社区；社区页正文写「社区规模户数 N 户」，
  部分页面还有「社区名称 | 居住小区名称 | 四至 | 办公地址」表。

严格口径：
  1. 只接受社区页明确列出的居住小区；
  2. 该社区只对应 1 个居住小区，且该名称能在现有 10,517 条小区清单中
     唯一匹配，才把社区总户数赋给这个小区；
  3. 一个社区含多个小区时，即使只认识其中一个，也不拆分、不赋值；
  4. 保留原文、来源链接和匹配依据，便于人工复核。

这不是全市完整户数库。它的用途是先验证「明确对应」能拿到多少样本。

输出（raw_data 已被 .gitignore 忽略，不会提交）：
  raw_data/households/community_pages.jsonl  社区页解析结果
  raw_data/households/matches_strict.jsonl  严格匹配成功的小区
  raw_data/households/summary.json          产量与失败原因统计

用法：
  python fetch_households.py fetch     # 抓取 26 个街镇及社区页（断点续传）
  python fetch_households.py parse     # 重新匹配，不重新抓
  python fetch_households.py report    # 打印统计
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "raw_data", "households")
PAGES = os.path.join(OUT_DIR, "community_pages.jsonl")
MATCHES = os.path.join(OUT_DIR, "matches_strict.jsonl")
SUMMARY = os.path.join(OUT_DIR, "summary.json")
PROJECTS = os.path.join(HERE, "data", "projects.json")

BASE = "https://www.bjft.gov.cn"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
CTX = ssl.create_default_context()
CTX.set_ecdh_curve("prime256v1")

# 26 个街镇。代码来自街镇名片实际链接，东高地是唯一不按常规缩写的一个。
STREETS = {
    "丰台街道": "mpftjd", "西罗园街道": "mpxly", "方庄街道": "mpfz",
    "太平桥街道": "mptpq", "东铁匠营街道": "mpdtjy", "右安门街道": "mpyam",
    "长辛店街道": "mpcxd", "新村街道": "mpxc", "六里桥街道": "mpllq",
    "云岗街道": "mpyg", "东高地街道": "mpdgd", "南苑街道": "mpny",
    "大红门街道": "mpdhm", "马家堡街道": "mpmjp", "和义街道": "mphy",
    "宛平街道": "mpwp", "成寿寺街道": "mpcss", "石榴庄街道": "mpslz",
    "看丹街道": "mpkd", "玉泉营街道": "mpyqy", "青塔街道": "mpqt",
    "五里店街道": "mpwld", "卢沟桥街道": "mplgq", "花乡街道": "mphx",
    "北宫镇": "mpbgz", "王佐镇": "mpwzz",
}


def http(url, tries=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(req, context=CTX, timeout=35).read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    raise last


def strip_tags(s):
    s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", "", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(?:p|div|tr|li|h\d)>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
         .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return s


def clean_text(s):
    s = strip_tags(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def norm_name(s):
    s = (s or "").strip()
    s = s.replace("（", "(").replace("）", ")").replace("\u3000", "")
    s = re.sub(r"\s+", "", s)
    return s


def name_keys(s):
    """小区名匹配键：原名，以及去掉常见后缀后的名字。"""
    n = norm_name(s)
    keys = {n}
    for suf in ("小区", "社区", "家园"):
        if n.endswith(suf) and len(n) > len(suf) + 1:
            keys.add(n[:-len(suf)])
    return {k for k in keys if k}


def load_projects():
    rows = json.load(open(PROJECTS, encoding="utf-8"))
    by_district = {}
    for r in rows:
        d = (r.get("项目所在区") or "").strip()
        n = r.get("项目名称") or ""
        if not d or not n:
            continue
        for k in name_keys(n):
            by_district.setdefault((d, k), []).append(r)
    return by_district


def parse_households(text):
    # 页面里常见「有常住户 2166 户」「规模户数 1123户」等写法，
    # 先去掉空格再匹配，否则数字和“户”之间的空格会漏掉。
    t = re.sub(r"\s+", "", text)
    patterns = [
        r"(?:社区)?规模户数[为共约:：]?(\d{1,7})户",
        r"(?:社区)?总户数[为共约:：]?(\d{1,7})户",
        r"(?:社区|辖区|管辖)(?:内)?(?:共|总计)?(?:有)?(?:住户|户数)(?:为|约|达|共计|:：)?(\d{1,7})户",
        r"(?:常住居民户数|居民住户|常住户|居民户数|居住户数)[为共约已达:：]?(\d{1,7})户",
        r"(?:社区|辖区|管辖)(?:内)?(?:共|共计|总计)(\d{1,7})户",
        r"有(\d{1,7})户(?:居民|住户)",
        r"(?:共|总计)(\d{1,7})户",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            n = int(m.group(1).replace(",", ""))
            if 10 <= n <= 200000:
                return n, m.group(0)
    return None, ""


def table_grid(table_html):
    """把带 rowspan/colspan 的 HTML 表展开成二维文本网格。"""
    grid, pending = [], {}
    for tr in re.findall(r"<tr[\s\S]*?</tr>", table_html, flags=re.I):
        cells = re.findall(
            r"<t[dh]([^>]*)>([\s\S]*?)</t[dh]>", tr, flags=re.I
        )
        row, col = [], 0
        while cells or any(c >= col for c in pending):
            if col in pending:
                left, val = pending[col]
                row.append(val)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col] = (left - 1, val)
                col += 1
                continue
            if not cells:
                break
            attrs, body = cells.pop(0)
            rs = re.search(r'rowspan="?(\d+)', attrs, flags=re.I)
            cs = re.search(r'colspan="?(\d+)', attrs, flags=re.I)
            rs, cs = int(rs.group(1)) if rs else 1, int(cs.group(1)) if cs else 1
            val = clean_text(body).strip(" ：:")
            for k in range(cs):
                row.append(val)
                if rs > 1:
                    pending[col + k] = (rs - 1, val)
            col += cs
        grid.append(row)

    # 处理表格最后一行之后仍挂着的 rowspan
    while pending:
        row = []
        for col in range(max(pending) + 1):
            if col in pending:
                left, val = pending[col]
                row.append(val)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col] = (left - 1, val)
        if not row:
            break
        grid.append(row)
    return grid


def parse_residential(text_html):
    """从「居住小区名称」表提取小区名。

    表头通常为：社区名称 | 居住小区名称 | 四至 | 办公地址。
    后面几行社区名称、四至常用 rowspan 合并，直接按第 2 个 td 取会把
    「北至……」误当小区名，所以先展开成网格，再按表头列号取值。
    """
    names = []
    for table in re.findall(r"<table[\s\S]*?</table>", text_html, flags=re.I):
        if "居住小区名称" not in strip_tags(table):
            continue
        grid = table_grid(table)
        col = None
        for row in grid:
            if "居住小区名称" in row:
                col = row.index("居住小区名称")
                continue
            if col is None or col >= len(row):
                continue
            a = row[col].strip()
            if not a or a in ("居住小区名称", "小区名称", "名称"):
                continue
            # 单元格里偶尔有多个小区，用顿号拆开
            for x in re.split(r"[、,，;；/]", a):
                x = x.strip()
                if 1 < len(x) <= 40 and not re.match(r"^[北东南西至]", x):
                    names.append(x)
    # 去重且保持顺序
    return list(dict.fromkeys(names))


def parse_per_xiaoqu(text):
    """抽「XX小区管辖户数 N 户」这种逐小区户数。

    例：山语城小区管辖户数1956户，燕西华府小区管辖户数2461户。
    这类数据可以把同一社区里的多个小区分别赋值，不需要拆分社区总数。
    """
    t = re.sub(r"\s+", "", text)
    suf = r"(?:小区|家园|公寓|花园|苑|园|里|院|城|府|医院)"
    pat = re.compile(
        r"([\u4e00-\u9fa5A-Za-z0-9（）()\-]{2,24}?" + suf + r")"
        r"[^。；、]{0,18}?([\d,]{1,7})\s*户"
    )
    out, seen = [], set()
    for m in pat.finditer(t):
        name = re.sub(r"^(?:辖区含|辖区内|由|包括|其中|共有|含|及|和|与|对|管辖)", "", m.group(1))
        q = m.group(0)
        n = int(m.group(2).replace(",", ""))
        if not (10 <= n <= 200000) or len(name) < 3:
            continue
        # 「角门甲4号院平房25户」只覆盖院内平房，不是整个小区，不能算
        if "平房" in q:
            continue
        # 「面积0.25平方公里，规模户数…」里的“里”不是小区名
        if "平方公里" in q:
            continue
        # 「XX社区…总户数」是社区总户数，不是某个小区
        if "社区" in q:
            continue
        if (name, n) in seen:
            continue
        seen.add((name, n))
        out.append({"name": name, "households": n, "quote": q})
    return out


def parse_page(url, html, street, link_label=""):
    # 标题：优先 ArticleTitle，其次 h1
    m = re.search(r'<meta\s+name="ArticleTitle"\s+content="([^"]*)"', html, flags=re.I)
    title = m.group(1).strip() if m else ""
    if not title:
        m = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html, flags=re.I)
        title = clean_text(m.group(1)) if m else ""
    if not title:
        title = link_label

    zoom = html
    m = re.search(r'<div[^>]+id="zoom"[^>]*>([\s\S]*?)<div[^>]+class="[^"]*(?:footer|foot)[^"]*"', html, flags=re.I)
    if m:
        zoom = m.group(1)
    else:
        m = re.search(r'<div[^>]+class="Conzynr"[^>]*>([\s\S]*?)</div>\s*<div', html, flags=re.I)
        if m:
            zoom = m.group(1)

    text = clean_text(zoom)
    text = text.split("附件：")[0].strip()
    households, quote = parse_households(text)
    residential = parse_residential(zoom)
    per_xiaoqu = parse_per_xiaoqu(text)

    # 正文明确写「下辖/管辖 1 个小区」也可以作为一小区依据
    one_community = bool(re.search(r"(?:下辖|管辖|包含|共有)\s*1\s*个(?:住宅)?小区", text))

    return {
        "district": "丰台区",
        "street": street,
        "community": title,
        "households": households,
        "household_quote": quote,
        "residential": residential,
        "per_xiaoqu": per_xiaoqu,
        "one_community_signal": one_community,
        "text": text[:4000],
        "source_url": url,
    }


def load_pages():
    pages = {}
    if os.path.exists(PAGES):
        for line in open(PAGES, encoding="utf-8"):
            try:
                r = json.loads(line)
                pages[r["source_url"]] = r
            except Exception:
                pass
    return pages


def discover():
    """抓 26 个街镇页，返回社区页 URL 列表。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    links = []
    for street, code in STREETS.items():
        url = f"{BASE}/xxfb/xxgkmp/gkmpjz/{code}/"
        try:
            h = http(url)
        except Exception as e:
            print(f"[街镇页失败] {street}: {type(e).__name__}")
            continue
        found = 0
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', h, flags=re.I):
            href, label = m.group(1), clean_text(m.group(2)).strip()
            if "社区" not in label or len(label) > 20:
                continue
            # 跳过「社区」栏目入口本身，只要具体社区文章
            if label in ("社区", "行政村"):
                continue
            if "/ftq/" not in href and not href.startswith("."):
                continue
            full = urllib.parse.urljoin(url, href)
            if full not in {x[0] for x in links}:
                links.append((full, street, label))
                found += 1
        print(f"{street:<8} {found} 个社区链接")
        time.sleep(0.35)
    return links


def cmd_fetch():
    links = discover()
    pages = load_pages()
    todo = [x for x in links if x[0] not in pages]
    print(f"社区页共 {len(links)}，已抓 {len(pages)}，待抓 {len(todo)}")
    with open(PAGES, "a", encoding="utf-8") as f:
        for i, (url, street, label) in enumerate(todo, 1):
            try:
                h = http(url)
                rec = parse_page(url, h, street, label)
                rec["link_label"] = label
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            except Exception as e:
                print(f"  失败 {url}: {type(e).__name__}")
            if i % 25 == 0:
                print(f"  进度 {i}/{len(todo)}")
            time.sleep(0.3)


def cmd_parse():
    pages = load_pages()
    index = load_projects()
    all_projects = json.load(open(PROJECTS, encoding="utf-8"))
    by_street = {}
    for p in all_projects:
        k = ((p.get("项目所在区") or "").strip(), (p.get("所属街道") or "").strip())
        by_street.setdefault(k, []).append(p)

    def match_one(d, street, name):
        """先精确匹配，再在同街道内做唯一包含匹配（如 山语城 -> 北京山语城）。"""
        cands = []
        for k in name_keys(name):
            cands.extend(index.get((d, k), []))
        uniq = {c.get("project_no"): c for c in cands}
        if uniq:
            return list(uniq.values()), "exact_name" if len(uniq) == 1 else "ambiguous"
        n = norm_name(name)
        if len(n) < 3:
            return [], "not_found"
        near = []
        for p in by_street.get((d, street), []):
            pn = norm_name(p.get("项目名称"))
            if len(pn) >= 3 and (n in pn or pn in n):
                near.append(p)
        uniq = {c.get("project_no"): c for c in near}
        if len(uniq) == 1:
            return list(uniq.values()), "unique_alias_in_street"
        return [], "ambiguous" if len(uniq) > 1 else "not_found"

    matches, reasons = [], Counter()
    for r in pages.values():
        # 旧版本抓的页面没有 per_xiaoqu 字段，用已保存正文补算
        if "per_xiaoqu" not in r:
            r["per_xiaoqu"] = parse_per_xiaoqu(r.get("text", ""))
        # 抽取规则后来补过，旧页面用正文重新算一遍户数
        if not r.get("households"):
            h, q = parse_households(r.get("text", ""))
            if h:
                r["households"], r["household_quote"] = h, q

        # A. 逐小区明确写户数：优先级最高
        for px in r.get("per_xiaoqu") or []:
            d = r["district"]
            found, how = match_one(d, r["street"], px["name"])
            if len(found) == 1:
                p = found[0]
                matches.append({
                    "district": d, "street": r["street"], "community": r["community"],
                    "xiaoqu": p.get("项目名称"), "project_no": p.get("project_no"),
                    "households": px["households"], "residential_list": [px["name"]],
                    "household_quote": px["quote"],
                    "match_rule": "per_xiaoqu_" + how,
                    "source_url": r["source_url"],
                })
            elif how == "ambiguous":
                reasons["ambiguous_per_xiaoqu"] += 1
            else:
                reasons["no_dataset_match_per_xiaoqu"] += 1

        if not r.get("households"):
            reasons["no_households"] += 1
            continue
        names = r.get("residential") or []
        if not names:
            reasons["no_residential_list"] += 1
            continue
        if len(names) > 1:
            reasons["multiple_residential"] += 1
            continue

        name = names[0]
        d = r["district"]
        found, how = match_one(d, r["street"], name)
        if not found:
            reasons["no_dataset_match"] += 1
            continue
        if len(found) > 1:
            reasons["ambiguous_match"] += 1
            continue

        p = found[0]
        matches.append({
            "district": d,
            "street": r["street"],
            "community": r["community"],
            "xiaoqu": p.get("项目名称"),
            "project_no": p.get("project_no"),
            "households": r["households"],
            "residential_list": names,
            "household_quote": r.get("household_quote"),
            "match_rule": "single_residential_" + how,
            "source_url": r["source_url"],
        })

    # 去重：同一小区多条记录，保留户数一致的首条，冲突单独标记
    by_xq, conflicts = {}, []
    for m in matches:
        k = (m["district"], norm_name(m["xiaoqu"]))
        if k not in by_xq:
            by_xq[k] = m
        elif by_xq[k]["households"] != m["households"]:
            conflicts.append({"kept": by_xq[k], "other": m})

    out = list(by_xq.values())
    with open(MATCHES, "w", encoding="utf-8") as f:
        for m in out:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    summary = {
        "community_pages": len(pages),
        "matched_xiaoqu": len(out),
        "conflicts": len(conflicts),
        "reasons": dict(reasons.most_common()),
        "by_street": dict(Counter(m["street"] for m in out).most_common()),
    }
    json.dump(summary, open(SUMMARY, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_report():
    if not os.path.exists(SUMMARY):
        print("还没有 summary，先跑 parse")
        return
    print(open(SUMMARY, encoding="utf-8").read())


def cmd_export():
    """导出两份 CSV：所有有户数的社区页、严格匹配的小区。"""
    import csv

    pages = load_pages()
    projects = {r.get("project_no"): r for r in json.load(open(PROJECTS, encoding="utf-8"))}
    for r in pages.values():
        if not r.get("households"):
            h, q = parse_households(r.get("text", ""))
            if h:
                r["households"], r["household_quote"] = h, q
    with_hh = [r for r in pages.values() if r.get("households")]
    with_hh.sort(key=lambda r: (r["street"], r["community"]))

    p1 = os.path.join(OUT_DIR, "communities_with_households.csv")
    with open(p1, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["区", "街道", "社区", "户数", "居住小区数", "居住小区名单", "原文", "来源"])
        for r in with_hh:
            w.writerow([r["district"], r["street"], r["community"], r["households"],
                        len(r.get("residential") or []), "、".join(r.get("residential") or []),
                        r.get("household_quote", ""), r["source_url"]])

    strict = [json.loads(l) for l in open(MATCHES, encoding="utf-8")] if os.path.exists(MATCHES) else []
    p2 = os.path.join(OUT_DIR, "strict_matches.csv")
    with open(p2, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["区", "街道", "小区", "户数", "社区", "建成年代", "物业费标准",
                    "业委会状态", "项目地址", "匹配依据", "来源"])
        for m in strict:
            p = projects.get(m["project_no"], {})
            w.writerow([m["district"], m["street"], m["xiaoqu"], m["households"], m["community"],
                        p.get("建成年代", ""), p.get("物业服务费用标准", ""),
                        p.get("是否成立业委会(物管会)", ""), p.get("项目地址", ""),
                        m["match_rule"], m["source_url"]])
    print(f"写出 {p1}（{len(with_hh)} 行）")
    print(f"写出 {p2}（{len(strict)} 行）")


if __name__ == "__main__":
    import urllib.parse

    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if cmd == "fetch":
        cmd_fetch()
    elif cmd == "parse":
        cmd_parse()
    elif cmd == "report":
        cmd_report()
    elif cmd == "export":
        cmd_export()
    else:
        print(__doc__)
