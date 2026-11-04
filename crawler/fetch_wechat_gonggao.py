# -*- coding: utf-8 -*-
"""逐小区在搜狗微信搜索业主大会公告，抓正文并抽取户数/业主人数。

用法:
    python fetch_wechat_gonggao.py search          # 全量(有业委会的小区)
    python fetch_wechat_gonggao.py search --limit 80   # 试点 N 个
    python fetch_wechat_gonggao.py stats           # 统计命中率

数据落盘 raw_data/households/wechat/，jsonl 追加式断点续跑，不提交 git。
"""

import json
import os
import random
import re
import sys
import time
import http.cookiejar
import ssl
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(BASE, "..", "raw_data", "households", "wechat"))
PAGES_JSONL = os.path.join(OUT_DIR, "search_pages.jsonl")      # 每个小区一次搜索的标题列表
ARTICLES_JSONL = os.path.join(OUT_DIR, "articles.jsonl")      # 每篇抓到正文的公告
DONE_JSON = os.path.join(OUT_DIR, "done_names.json")          # 已完成小区名断点

PROJECTS = os.path.join(BASE, "data", "projects.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}

DELAY_QUERY = 7.0      # 搜索间隔
DELAY_ARTICLE = 4.0    # 正文间隔

CTX = ssl.create_default_context()
CTX.set_ecdh_curve("prime256v1")

# ---------------------------------------------------------------- utilities


def make_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=CTX),
    )
    op.open(urllib.request.Request("https://weixin.sogou.com/", headers=HEADERS),
            timeout=30).read()
    return op, cj


def is_blocked(html):
    low = html[:20000].lower()
    return "antispider" in low or "请输入验证码" in html or "seccode" in low


def clean_text(s):
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", s or ""))


def strip_html(html):
    html = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p>", "\n", html, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", html)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&ldquo;", "“").replace(
        "&rdquo;", "”").replace("&nbsp;", " ")
    t = re.sub(r"[ \t\u3000]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


# ---------------------------------------------------------------- search


def wx_search(op, referer, q):
    """搜狗微信文章搜索, 返回 [(标题, link_path), ...]; 遇反爬抛 RuntimeError。"""
    u = "https://weixin.sogou.com/weixin?type=2&query=" + urllib.parse.quote(q)
    h = op.open(urllib.request.Request(u, headers={**HEADERS, "Referer": referer}),
                timeout=30).read().decode("utf-8", "ignore")
    if is_blocked(h):
        raise RuntimeError("blocked")
    out = []
    for blk in re.findall(r'<div class="txt-box">([\s\S]*?)</div>\s*</div>', h):
        t = re.search(r"<a[^>]*>([\s\S]*?)</a>", blk)
        link = re.search(r'href="(/link\?url=[^"]+)"', blk)
        if t and link:
            out.append((clean_text(t.group(1)), link.group(1)))
    return out, u


def resolve_link(op, search_url, link_path):
    raw = link_path.replace("&amp;", "&")
    link = "https://weixin.sogou.com" + urllib.parse.quote(raw, safe="/?=&%")
    r = op.open(urllib.request.Request(link, headers={**HEADERS, "Referer": search_url}),
                timeout=30)
    h = r.read().decode("utf-8", "ignore")
    if is_blocked(h):
        raise RuntimeError("blocked")
    real = "".join(x.replace("@", "") for x in re.findall(r"url \+= '([^']*)'", h))
    return real or None


def fetch_article(op, url):
    h = op.open(urllib.request.Request(url, headers=HEADERS), timeout=30).read().decode(
        "utf-8", "ignore")
    text = strip_html(h)
    acct = ""
    m = re.search(r'var nickname = "([^"]+)"', h) or re.search(
        r"profile_nickname[^>]*>([^<]+)<", h)
    if m:
        acct = m.group(1).strip()
    title = ""
    m = re.search(r'<meta property="og:title" content="([^"]*)"', h)
    if m:
        title = m.group(1).strip()
    return title, acct, text


# ---------------------------------------------------------------- extraction

HH_PATTERNS = [
    r"(?:业主总人数|业主人数总数|总人数)\s*(?:为|是|共|共计|约)?\s*([\d,]{2,7})\s*(?:人|名)",
    r"(?:业主|本小区|本物业管理区域|物业管理区域)(?:共计|总|共|共有?|合计)\s*([\d,]{2,7})\s*户",
    r"(?:本小区|本区域|本物业管理区域内)?(?:共有|共计|总计|合计)\s*([\d,]{2,7})\s*户业主",
    r"([\d,]{2,7})\s*户(?:业主)?(?:参加|参与)(?:了)?(?:本次|本小区)?(?:业主大会|表决)",
    r"(?:参会|参与表决)(?:业主|户数)\s*(?:达到|为|共)\s*([\d,]{2,7})\s*户",
    r"(?:总户数|总套数)\s*(?:为|是|共|共计|约)?\s*([\d,]{2,7})\s*户",
    r"专有部分(?:总面积|占建筑物总面积)\s*(?:为|是|共|约)?\s*([\d,.]{4,12})\s*(?:平方米|㎡)",
]


def extract_numbers(text):
    out = []
    for p in HH_PATTERNS:
        for m in re.finditer(p, text):
            n = m.group(1).replace(",", "")
            if p.startswith("专有部分"):
                try:
                    v = float(n)
                except ValueError:
                    continue
                if 1000 <= v <= 5_000_000:
                    out.append({"kind": "area", "value": v, "quote": m.group(0)})
            else:
                v = int(n)
                if 10 <= v <= 200000:
                    out.append({"kind": "count", "value": v, "quote": m.group(0)})
    # 去重
    seen, res = set(), []
    for x in out:
        k = (x["kind"], x["value"])
        if k not in seen:
            seen.add(k)
            res.append(x)
    return res


# ---------------------------------------------------------------- commands


def iter_targets(limit=None):
    rows = json.load(open(PROJECTS, encoding="utf-8"))
    y = [r for r in rows if r.get("是否成立业委会(物管会)") == "业委会"]
    # 名字去重(一个小区多个物业备案项目)
    names, seen = [], set()
    for r in y:
        n = re.sub(r"小区$", "", r["项目名称"]).strip()
        if len(n) < 3 or n in seen:
            continue
        seen.add(n)
        names.append({"name": n, "district": r["项目所在区"], "street": r["所属街道"],
                      "project": r["项目名称"], "project_no": r["project_no"]})
    random.Random(42).shuffle(names)
    if limit:
        names = names[:limit]
    return names


def load_done():
    if os.path.exists(DONE_JSON):
        return set(json.load(open(DONE_JSON, encoding="utf-8")))
    return set()


def save_done(done):
    json.dump(sorted(done), open(DONE_JSON, "w", encoding="utf-8"), ensure_ascii=False)


def append(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_search(limit=None, only_names=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    op, cj = make_opener()
    done = load_done()
    targets = iter_targets(limit)
    if only_names:
        want = set(only_names)
        targets = [t for t in targets if t["name"] in want]
    blocked_since = 0
    for i, t in enumerate(targets):
        if t["name"] in done:
            continue
        q = f"北京 {t['name']} 业主大会"
        try:
            results, search_url = wx_search(op, "https://weixin.sogou.com/", q)
        except RuntimeError:
            blocked_since += 1
            print(f"[{i}] BLOCKED ({blocked_since}) {t['name']}; sleep 300s", flush=True)
            time.sleep(300)
            try:
                op, cj = make_opener()
                results, search_url = wx_search(op, "https://weixin.sogou.com/", q)
            except Exception as e:
                print("  still failing:", type(e).__name__, e, flush=True)
                continue
        except Exception as e:
            print(f"[{i}] {t['name']} ERR {type(e).__name__} {e}", flush=True)
            time.sleep(10)
            continue
        blocked_since = 0
        append(PAGES_JSONL, {**t, "query": q,
                             "titles": [x[0] for x in results],
                             "ts": time.strftime("%F %T")})
        # 抓正文: 标题含公告/公示/大会且含小区名的, 最多 4 篇
        picked = []
        for title, lp in results:
            if t["name"] not in title.replace("小区", ""):
                continue
            if not re.search(r"业主大会|表决|决议|公示|公告|选举", title):
                continue
            picked.append((title, lp))
        picked = picked[:4]
        arts = []
        for title, lp in picked:
            try:
                real = resolve_link(op, search_url, lp)
                if not real:
                    continue
                wtitle, acct, text = fetch_article(op, real)
                nums = extract_numbers(text)
                art = {"name": t["name"], "district": t["district"],
                       "street": t["street"], "search_title": title,
                       "title": wtitle, "account": acct, "url": real[:500],
                       "len": len(text), "numbers": nums,
                       "text": text[:6000], "ts": time.strftime("%F %T")}
                append(ARTICLES_JSONL, art)
                arts.append(art)
                time.sleep(DELAY_ARTICLE)
            except RuntimeError:
                print(f"  article BLOCKED; sleep 300s", flush=True)
                time.sleep(300)
                op, cj = make_opener()
            except Exception as e:
                print(f"  art ERR {type(e).__name__} {e}", flush=True)
        done.add(t["name"])
        if i % 5 == 0 or arts:
            save_done(done)
        hit = sum(1 for a in arts if a["numbers"])
        print(f"[{i}/{len(targets)}] {t['name']}: results={len(results)} "
              f"picked={len(picked)} with_numbers={hit}", flush=True)
        time.sleep(DELAY_QUERY)
    save_done(done)
    print("done", flush=True)


def cmd_stats():
    arts = [json.loads(l) for l in open(ARTICLES_JSONL, encoding="utf-8")] \
        if os.path.exists(ARTICLES_JSONL) else []
    pages = [json.loads(l) for l in open(PAGES_JSONL, encoding="utf-8")] \
        if os.path.exists(PAGES_JSONL) else []
    print("searched:", len(pages))
    with_titles = sum(1 for p in pages if p["titles"])
    print("with any title:", with_titles)
    print("articles fetched:", len(arts))
    with_nums = [a for a in arts if a["numbers"]]
    print("articles with numbers:", len(with_nums))
    for a in with_nums[:30]:
        print(" ", a["name"], "|", a["title"][:40],
              "|", [(x["kind"], x["value"]) for x in a["numbers"]])


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "search"
    if cmd == "search":
        limit = None
        only = None
        if "--limit" in args:
            limit = int(args[args.index("--limit") + 1])
        if "--names" in args:
            only = args[args.index("--names") + 1].split(",")
        cmd_search(limit, only)
    elif cmd == "stats":
        cmd_stats()
    else:
        print(__doc__)
