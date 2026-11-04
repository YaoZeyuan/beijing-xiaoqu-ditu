"""
从北京市公共资源交易平台抓「老旧小区综合整治」公告里的建设规模
=============================================================
用途：为小区补充「改造建筑面积 / 栋数」两个体量指标。
数据源：https://ggzyfw.beijing.gov.cn/elasticsearch/search（站内检索接口，公开无需登录）

口径提醒：
- 只覆盖「纳入老旧小区综合整治计划」的小区，全部是 2000 年前后建成的老小区，
  样本有偏，不能代表全市 10,330 个小区。
- 公告里的面积是「本次改造建筑面积」，通常等于小区住宅建筑面积，但不含非住宅。
- 绝大多数公告**不给户数**（抽样 12 条命中 0 条），所以户数仍然取不到。

输出：raw_data/old_area/announcements.jsonl（公告级）、xiaoqu_area.jsonl（小区级去重）

用法：
  python fetch_old_area.py search   # 只扫检索结果，看候选量
  python fetch_old_area.py fetch    # 抓详情并抽取（支持断点续传）
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://ggzyfw.beijing.gov.cn"
SEARCH = f"{BASE}/elasticsearch/search"
KEYWORD = "老旧小区综合整治"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "raw_data", "old_area")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"

# 该站证书的曲线 Python 默认不认，必须显式指定 prime256v1，否则 SSLError BAD_ECPOINT
CTX = ssl.create_default_context()
CTX.set_ecdh_curve("prime256v1")


def http(url, data=None, referer=None):
    hdr = {"User-Agent": UA, "Referer": referer or BASE + "/"}
    if data is not None:
        hdr["X-Requested-With"] = "XMLHttpRequest"
        hdr["Referer"] = f"{BASE}/elasticsearch/index.jsp"
    req = urllib.request.Request(url, data=data, headers=hdr)
    for i in range(4):
        try:
            return urllib.request.urlopen(req, context=CTX, timeout=45).read().decode("utf-8", "ignore")
        except Exception:
            if i == 3:
                raise
            time.sleep(1.5 * (i + 1))


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)


def search_page(page, size=100):
    data = urllib.parse.urlencode(
        {"searchword": KEYWORD, "scope": "title", "page": page, "size": size}
    ).encode()
    d = json.loads(http(SEARCH, data))
    return d.get("total", 0), json.loads(d.get("result") or "[]")


def search_page_safe(page, size=100, tries=3):
    """深翻页会偶发 550（平台限流），失败就退避重试，仍失败则返回空表示到此为止"""
    for i in range(tries):
        try:
            return search_page(page, size)
        except Exception as e:
            if i == tries - 1:
                print(f"  第 {page} 页放弃：{type(e).__name__}")
                return None, []
            time.sleep(3 * (i + 1))
    return None, []


def page_text(url):
    h = http(url)
    h = re.sub(r"<script[\s\S]*?</script>", "", h)
    h = re.sub(r"<style[\s\S]*?</style>", "", h)
    t = re.sub(r"<[^>]+>", " ", h).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t)


# 只抓「有建设规模」的公告类型；中标/业绩/候选人公示基本不含建设规模
KEEP_TYPE = ("资格预审", "招标公告", "施工采购")
DROP_TYPE = ("中标", "业绩", "合格申请人", "候选人", "监理")

DISTRICTS = ["东城区", "西城区", "朝阳区", "海淀区", "丰台区", "石景山区", "门头沟区",
             "房山区", "通州区", "顺义区", "昌平区", "大兴区", "怀柔区", "平谷区",
             "密云区", "延庆区"]


def pick_district(title, text):
    for d in DISTRICTS:
        if d in title:
            return d
    for d in DISTRICTS:
        if d in text[:1500]:
            return d
    return ""


def pick_street(title):
    m = re.search(r"（([\u4e00-\u9fa5]{2,6}(?:街道|地区|镇|乡))）", title)
    if m:
        return m.group(1)
    m = re.search(r"([\u4e00-\u9fa5]{2,6}(?:街道|地区|镇|乡))", title)
    return m.group(1) if m else ""


def pick_name(title):
    """从标题里剥出小区名：'丰台区和义北里三区老旧小区综合整治项目施工资格预审公告' -> 和义北里三区"""
    t = title
    for d in DISTRICTS:
        t = t.replace(d, "")
    m = re.search(r"^(.*?)老旧小区", t)
    name = m.group(1) if m else ""
    name = re.sub(r"^\d{4}年?", "", name)
    name = re.sub(r"[（(].*?[）)]", "", name)
    name = re.sub(r"^[-—\s]+|[-—\s]+$", "", name)
    return name.strip()


def parse_scale(text):
    """抽「改造建筑面积 / 栋数 / 户数」

    公告里面积写法很杂，实测至少有这些：
      建设规模 138229平方米
      建设规模： 改造总面积约105292㎡
      建设规模 总建筑面积约119482平米
      本次改造共涉及6个小区…其中，承平园小区1067户，总建筑面积110541平方米
    所以先统一单位符号，再只在「建设规模」到「合同估算价/计划工期」之间取第一个面积数字。
    """
    out = {}
    t = (text.replace("㎡", "平方米").replace("m2", "平方米").replace("M2", "平方米")
             .replace("平米", "平方米"))
    i = t.find("建设规模")
    seg = t[i:i + 700] if i > 0 else ""
    # 截到下一个字段，避免把「公共区域改造室外面积」之类混进来
    for stop in ("合同估算价", "计划工期", "工程概算"):
        j = seg.find(stop)
        if j > 0:
            seg = seg[:j]
            break

    m = re.search(r"([\d,]+\.?\d*)\s*万平方米", seg)
    if m:
        out["areaM2"] = round(float(m.group(1).replace(",", "")) * 10000, 2)
    else:
        m = re.search(r"(?:改造建筑面积|总建筑面积|建筑面积|改造总面积|总改造面积)[^0-9]{0,12}([\d,]+\.?\d*)\s*平方米", seg) \
            or re.search(r"([\d,]+\.?\d*)\s*平方米", seg)
        if m:
            v = float(m.group(1).replace(",", ""))
            if 100 <= v <= 5_000_000:
                out["areaM2"] = round(v, 2)

    m = re.search(r"(\d{1,4})\s*栋", seg)
    if m:
        out["buildings"] = int(m.group(1))

    # 户数优先取「小区名+户数」的逐小区写法，其次取总量
    per = re.findall(r"([\u4e00-\u9fa5A-Za-z0-9（）()\-]{2,24}?(?:小区|家园|公寓|花园|苑|园|里|院))\s*(\d{1,6})\s*户", t)
    if per:
        out["perXiaoqu"] = [{"name": a, "households": int(b)} for a, b in dict.fromkeys(per)]
    m = re.search(r"(?:共|涉及)?\s*(\d{1,6})\s*户", seg or t)
    if m:
        n = int(m.group(1))
        if 10 <= n <= 200000:
            out["households"] = n
    return out


def cmd_search():
    total, items = search_page_safe(1)
    print(f"检索总数 {total}")
    cand = []
    page = 1
    while True:
        t, items = (total, items) if page == 1 else search_page_safe(page)
        if not items:
            break
        for x in items:
            title = strip_tags(x["title"])
            if "老旧小区" not in title or "央企" in title:
                continue
            if any(k in title for k in DROP_TYPE):
                continue
            if not any(k in title for k in KEEP_TYPE):
                continue
            cand.append({"date": x["releaseDate"], "title": title,
                         "link": BASE + x["link"], "district": pick_district(title, ""),
                         "name": pick_name(title), "street": pick_street(title)})
        if page * 100 >= min(total, 20000):
            break
        page += 1
        time.sleep(0.35)
        if page % 20 == 0:
            print(f"  已扫 {page} 页，候选 {len(cand)}")
    print(f"候选公告 {len(cand)}，去重小区名 {len({(c['district'], c['name']) for c in cand})}")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "candidates.jsonl"), "w", encoding="utf-8") as f:
        for c in cand:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def cmd_fetch(workers=4):
    os.makedirs(OUT_DIR, exist_ok=True)
    cf = os.path.join(OUT_DIR, "candidates.jsonl")
    if not os.path.exists(cf):
        print("先跑 search")
        return
    cand = [json.loads(l) for l in open(cf, encoding="utf-8")]
    # 同一小区多份公告（资格预审 / 招标公告）取一份即可
    seen, uniq = set(), []
    for c in cand:
        k = (c["district"], c["name"])
        if not c["name"] or k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    print(f"去重后 {len(uniq)} 条待抓")

    outf = os.path.join(OUT_DIR, "announcements.jsonl")
    done = set()
    if os.path.exists(outf):
        for l in open(outf, encoding="utf-8"):
            try:
                done.add(json.loads(l)["link"])
            except Exception:
                pass
    print(f"已完成 {len(done)}，续传剩余 {len(uniq) - len(done)}")

    def work(c):
        if c["link"] in done:
            return None
        try:
            t = page_text(c["link"])
        except Exception as e:
            return {**c, "error": str(e)[:80]}
        rec = {**c, "district": c["district"] or pick_district(c["title"], t)}
        rec.update(parse_scale(t))
        return rec

    todo = [c for c in uniq if c["link"] not in done]
    n = 0
    with open(outf, "a", encoding="utf-8") as f, ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(work, c): c for c in todo}
        for fu in as_completed(futs):
            r = fu.result()
            if r:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
            n += 1
            if n % 50 == 0:
                print(f"  进度 {n}/{len(todo)}")
            time.sleep(0.25)


def cmd_summarize():
    src = os.path.join(OUT_DIR, "announcements.jsonl")
    rows = [json.loads(l) for l in open(src, encoding="utf-8")]
    has_area = [r for r in rows if r.get("areaM2")]
    has_hu = [r for r in rows if r.get("households")]
    print(f"公告 {len(rows)}｜有面积 {len(has_area)}｜有户数 {len(has_hu)}")
    out = os.path.join(OUT_DIR, "xiaoqu_area.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in has_area:
            f.write(json.dumps({
                "district": r.get("district"), "street": r.get("street"),
                "name": r.get("name"), "areaM2": r.get("areaM2"),
                "buildings": r.get("buildings"), "households": r.get("households"),
                "date": r.get("date"), "title": r.get("title"), "link": r.get("link"),
            }, ensure_ascii=False) + "\n")
    print("写出", out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "search"
    if cmd == "search":
        cmd_search()
    elif cmd == "fetch":
        cmd_fetch(int(sys.argv[2]) if len(sys.argv) > 2 else 4)
    elif cmd == "summarize":
        cmd_summarize()
