"""
北京市住建委「物业项目信息查询」抓取工具
=========================================
数据源：http://bjjs.zjw.beijing.gov.cn/eportal/ui?pageId=53619997
公开页面，无需登录。包含：物业费标准、收费方式、业委会情况、物业企业信息等。

用法：
  python bjjs.py search 万柳书院            # 按小区名搜索并输出详情
  python bjjs.py search company 万科     # 按物业企业名搜索
  python bjjs.py batch names.txt        # 批量搜索（每行一个小区名）
  python bjjs.py full                   # 全量抓取（10571 个小区，耗时较长）
  python bjjs.py export                 # 把已抓取数据导出为 Excel
公共参数：--out 目录（默认 ./data） --workers 并发数（默认 6）
"""
import argparse
import csv
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = "http://bjjs.zjw.beijing.gov.cn"
LIST_URL = f"{BASE}/eportal/ui?pageId=53619997"
PAGE_SIZE = 6  # 服务端固定每页 6 条

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": LIST_URL,
}

FIELDS = [
    "项目名称", "项目所在区", "项目地址", "建成年代",
    "项目负责人姓名", "项目负责人联系方式",
    "物业服务收费方式", "物业服务费用标准",
    "物业共有部分经营收入", "物业共有部分经营支出", "共有部分经营余额",
    "公共收益是否单独列账", "列账方式",
    "是否成立业委会(物管会)", "业委会(物管会)人数",
    "业委会(物管会)负责人姓名", "业委会(物管会)负责人联系方式",
    "物业服务企业名称", "统一社会信用代码", "法定代表人",
    "企业注册地址", "上一周期综合评价等级",
]


def new_session():
    s = requests.Session()
    s.trust_env = False        # 忽略系统/环境代理：本地代理会让政务站点请求超时
    s.headers.update(HEADERS)
    s.get(LIST_URL, timeout=30)  # 取 cookie
    return s


def _retry(fn, times=4, wait=3):
    for i in range(times):
        try:
            return fn()
        except Exception as e:
            if i == times - 1:
                raise
            time.sleep(wait * (i + 1) + random.random())
    return None


def parse_list(html):
    """解析列表页，返回 ([(project_no, 小区名, 物业企业名, 是否成立业委会)], 总数)"""
    items = []
    parts = html.split('<div class="item-card">')[1:]
    for block in parts:
        no = re.search(r'project_no=([A-F0-9]+)', block)
        if not no:
            continue
        name = re.search(r'class="item-title"[^>]*title="([^"]*)"', block) or \
               re.search(r'class="item-title"[^>]*>([^<]*)<', block)
        pairs = dict(re.findall(
            r'<span class="info-label">([^<]*)</span>\s*'
            r'<span class="info-value[^"]*"[^>]*>([^<]*)</span>', block))
        items.append({
            "project_no": no.group(1),
            "项目名称": (name.group(1) if name else "").strip(),
            "物业服务企业名称": pairs.get("物业服务企业名称", "").strip(),
            "是否成立业委会(物管会)": pairs.get("是否成立业委会(物管会)", "").strip(),
        })
    total = None
    m = re.search(r'总记录数\s*[:：]\s*(\d+)', html)
    if m:
        total = int(m.group(1))
    return items, total


def search(session, name=None, company=None, max_pages=None, progress=True,
           list_workers=1, cache_path=None, delay=1.1):
    """搜索项目，返回列表条目（自动翻页，支持列表缓存续传）

    默认串行 + 每次请求间隔 delay 秒，避免给政务服务器造成压力。
    """
    data = {"currentPage": 1, "pageSize": PAGE_SIZE}
    if name:
        data["filter_LIKE_name_"] = name
    if company:
        data["filter_LIKE_property_name"] = company

    first, items, total = "", [], None
    for _ in range(4):
        try:
            first = session.post(LIST_URL, data=data, timeout=30).text
            items, total = parse_list(first)
            if items:
                break
        except Exception:
            pass
        time.sleep(1.5)
    if not items:
        print("  首页请求未取到数据（服务端可能临时限流），稍后重试", flush=True)
    all_items = list(items)
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
    if max_pages:
        pages = min(pages, max_pages)
    if progress:
        print(f"  命中 {total} 条，共 {pages} 页", flush=True)

    # 已缓存的列表（断点续传：中断后不用从头翻）
    cached_pages = {}
    if cache_path and os.path.exists(cache_path):
        bad = 0
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:                       # 逐行容错：中断时写入的半行不影响其它页
                    rec = json.loads(line)
                except Exception:
                    bad += 1
                    continue
                cached_pages[rec["page"]] = rec["items"]
        for its in cached_pages.values():
            for it in its:
                all_items.append(it)
        if progress:
            print(f"  列表缓存命中 {len(cached_pages)} 页，已收 {len(all_items)} 条"
                  + (f"（忽略损坏行 {bad}）" if bad else ""), flush=True)

    import threading
    from threading import Lock
    seen = {it["project_no"] for it in all_items}
    lock = Lock()
    done_cnt = [0]
    fail_pages = []
    jar = session.cookies.copy()
    tl = threading.local()

    def get_list_sess():
        """每个线程复用一个连接（省掉每页 TCP/TLS 握手）"""
        if list_workers == 1:
            return session
        if not hasattr(tl, "s"):
            s = requests.Session()
            s.trust_env = False
            s.headers.update(HEADERS)
            s.cookies.update(jar)
            tl.s = s
        return tl.s

    lockf = open(cache_path, "a", encoding="utf-8") if cache_path else None

    def fetch_page(p):
        d = dict(data, currentPage=p)
        s = get_list_sess()
        for attempt in range(3):
            try:
                r = s.post(LIST_URL, data=d, timeout=40)
                its = parse_list(r.text)[0]
                if its:
                    time.sleep(delay)      # 请求成功后才休眠，保证对服务器友好
                    return p, its
                if list_workers > 1:
                    s.cookies.update(session.cookies)
            except Exception:
                pass
            time.sleep(2.0 * (attempt + 1))   # 失败才退避，成功的走上面的 delay
        return p, []

    todo_pages = [p for p in range(2, pages + 1) if p not in cached_pages]
    if progress:
        print(f"  待翻页 {len(todo_pages)} 页（并发 {list_workers}）", flush=True)

    with ThreadPoolExecutor(max_workers=list_workers) as ex:
        futs = [ex.submit(fetch_page, p) for p in todo_pages]
        for fut in as_completed(futs):
            p, its = fut.result()
            with lock:
                if not its:
                    fail_pages.append(p)
                else:
                    for it in its:
                        if it["project_no"] not in seen:
                            seen.add(it["project_no"])
                            all_items.append(it)
                    if lockf:
                        lockf.write(json.dumps({"page": p, "items": its}, ensure_ascii=False) + "\n")
                        lockf.flush()
                done_cnt[0] += 1
                if progress and done_cnt[0] % 150 == 0:
                    print(f"  列表进度 {done_cnt[0]}/{len(todo_pages)}，已收 {len(all_items)} 条"
                          f"（失败 {len(fail_pages)}）", flush=True)

    # 失败页重试一轮（降速）
    if fail_pages:
        if progress:
            print(f"  重试 {len(fail_pages)} 个失败页...", flush=True)
        retry_pages = list(fail_pages)
        fail_pages = []
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(fetch_page, p) for p in retry_pages]
            for fut in as_completed(futs):
                p, its = fut.result()
                if not its:
                    fail_pages.append(p)
                    continue
                for it in its:
                    if it["project_no"] not in seen:
                        seen.add(it["project_no"])
                        all_items.append(it)
                if lockf:
                    lockf.write(json.dumps({"page": p, "items": its}, ensure_ascii=False) + "\n")
                    lockf.flush()
        if progress:
            print(f"  重试后仍失败 {len(fail_pages)} 页", flush=True)

    if lockf:
        lockf.close()
    if progress:
        print(f"  列表完成：共 {len(all_items)} 条", flush=True)
    return all_items


def parse_detail(html, project_no):
    """解析详情页 HTML，返回 22 个原始字段（不重试、不发请求）"""
    d = {"project_no": project_no}
    for k, v in re.findall(
            r'info-label">([^<]+)</span>\s*<span class="info-value[^"]*"[^>]*title="([^"]*)"', html):
        d[k.strip()] = v.strip()
    if len(d) <= 1:  # 解析失败时回退
        for k, v in re.findall(
                r'info-label">([^<]+)</span>\s*<span class="info-value[^"]*"[^>]*>([^<]*)<', html):
            d[k.strip()] = v.strip()
    return d


def detail(session, project_no):
    """抓取单个项目详情（内部带重试），返回 dict"""
    url = f"{LIST_URL}&t=toDetail&project_no={project_no}"
    html = _retry(lambda: session.get(url, timeout=25).text, times=2, wait=1)
    return parse_detail(html or "", project_no)


def fetch_details(items, out_dir, workers=5, progress=True, delay=1.0, save_html=False,
                  filename="projects.jsonl"):
    """抓详情，边抓边落盘（断点续传）

    并发 workers 个线程；**每个请求成功后**休眠 delay 秒，失败则指数退避。
    已成功的 project_no 写入 out_dir/filename，重跑自动跳过。
    """
    import threading
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if not rec.get("error"):      # 失败项允许重抓
                        done.add(rec["project_no"])
                except Exception:
                    pass
    todo = [i for i in items if i["project_no"] not in done]
    if progress:
        print(f"  待抓详情 {len(todo)} 个（缓存已完成 {len(done)}）", flush=True)
    if not todo:
        return 0

    html_dir = os.path.join(out_dir, "html") if save_html else None
    if html_dir:
        os.makedirs(html_dir, exist_ok=True)

    lock_file = open(path, "a", encoding="utf-8")
    wlock = threading.Lock()
    base = new_session()
    base_cookies = base.cookies.copy()
    tl = threading.local()

    def get_sess():
        if not hasattr(tl, "s"):
            s = requests.Session()
            s.trust_env = False
            s.headers.update(HEADERS)
            s.cookies.update(base_cookies)
            tl.s = s
        return tl.s

    def work(it):
        s = get_sess()
        url = f"{LIST_URL}&t=toDetail&project_no={it['project_no']}"
        last = None
        for attempt in range(3):
            try:
                r = s.get(url, timeout=40)
                d = parse_detail(r.text, it["project_no"])
                if len(d) > 1:
                    d.setdefault("项目名称", it.get("项目名称", ""))
                    if html_dir:
                        fn = os.path.join(html_dir, f"{it['project_no']}.html")
                        with open(fn, "w", encoding="utf-8") as fh:
                            fh.write(r.text)
                    time.sleep(delay)      # 成功后才休眠
                    return d
                last = "解析为空"
            except Exception as e:
                last = str(e)
            time.sleep(2.0 * (attempt + 1))   # 只有失败才退避
        return {"project_no": it["project_no"], "error": last or "unknown",
                "项目名称": it.get("项目名称", "")}

    ok = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(work, it): it for it in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            d = fut.result()
            with wlock:
                lock_file.write(json.dumps(d, ensure_ascii=False) + "\n")
                lock_file.flush()
            ok += 1
            if progress and (i % 200 == 0 or i == len(todo)):
                el = time.time() - t0
                rate = i / el if el else 0
                eta = (len(todo) - i) / rate / 60 if rate else 0
                print(f"  详情进度 {i}/{len(todo)}  {rate:.2f} 条/秒  "
                      f"预计剩余 {eta:.0f} 分钟", flush=True)
    lock_file.close()
    return ok


def load_all(out_dir, filename="projects.jsonl"):
    """读取全部已抓数据，按 project_no 去重（成功记录优先于失败记录，后来的覆盖先前的）"""
    path = os.path.join(out_dir, filename)
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                no = rec.get("project_no")
                if not no:
                    continue
                prev = rows.get(no)
                # 已存成功记录时，新的失败记录不覆盖
                if prev is not None and not prev.get("error") and rec.get("error"):
                    continue
                rows[no] = rec
    return list(rows.values())


def export_xlsx(rows, out_dir, filename="物业项目信息.xlsx"):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    wb = Workbook()
    ws = wb.active
    ws.title = "物业项目信息"

    cols = ["项目名称", "项目所在区", "项目地址", "物业服务费用标准", "物业服务收费方式",
            "是否成立业委会(物管会)", "业委会(物管会)人数", "业委会(物管会)负责人姓名",
            "物业服务企业名称", "上一周期综合评价等级", "建成年代",
            "项目负责人姓名", "项目负责人联系方式", "统一社会信用代码",
            "法定代表人", "企业注册地址", "公共收益是否单独列账"] + \
           [f for f in FIELDS if f not in (
               "项目名称", "项目所在区", "项目地址", "物业服务费用标准", "物业服务收费方式",
               "是否成立业委会(物管会)", "业委会(物管会)人数", "业委会(物管会)负责人姓名",
               "物业服务企业名称", "上一周期综合评价等级", "建成年代",
               "项目负责人姓名", "项目负责人联系方式", "统一社会信用代码",
               "法定代表人", "企业注册地址", "公共收益是否单独列账")]

    head_fill = PatternFill("solid", fgColor="1F4E79")
    for c, name in enumerate(cols, 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center")

    for r, row in enumerate(rows, 2):
        for c, name in enumerate(cols, 1):
            ws.cell(row=r, column=c, value=row.get(name, ""))

    widths = {"项目名称": 24, "项目地址": 30, "物业服务费用标准": 50, "物业服务企业名称": 28,
              "企业注册地址": 30, "项目所在区": 10}
    for c, name in enumerate(cols, 1):
        ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = widths.get(name, 14)
    ws.freeze_panes = "A2"
    wb.save(path)
    return path


def export_csv(rows, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "物业项目信息.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["项目名称"] + FIELDS[1:] + ["project_no"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def main():
    ap = argparse.ArgumentParser(description="北京市物业项目信息查询工具")
    ap.add_argument("mode", choices=["search", "company", "batch", "full", "export"])
    ap.add_argument("keyword", nargs="?", help="小区名 / 企业名 / 文件路径")
    ap.add_argument("--out", default="data")
    ap.add_argument("--workers", type=int, default=5, help="详情并发数（默认 5）")
    ap.add_argument("--list-workers", type=int, default=5, help="列表翻页并发数（默认 5）")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="每个请求成功后休眠的秒数，默认 1.0s")
    args = ap.parse_args()

    out_dir = args.out
    session = new_session()

    if args.mode in ("search", "company"):
        if not args.keyword:
            sys.exit("请提供关键词")
        items = search(session, name=args.keyword if args.mode == "search" else None,
                       company=args.keyword if args.mode == "company" else None)
        for it in items:
            print(f"  · {it['项目名称']} | {it['物业服务企业名称']} | 业委会: {it['是否成立业委会(物管会)']}")
        fetch_details(items, out_dir, args.workers)
        rows = load_all(out_dir)
        p = export_xlsx(rows, out_dir)
        print(f"已导出: {p}")

    elif args.mode == "batch":
        if not args.keyword:
            sys.exit("请提供小区名清单文件")
        names = [l.strip() for l in open(args.keyword, encoding="utf-8") if l.strip()]
        for i, n in enumerate(names, 1):
            print(f"[{i}/{len(names)}] 搜索: {n}")
            items = search(session, name=n, progress=False)
            if not items:
                print("  未找到")
                continue
            fetch_details(items, out_dir, args.workers, progress=False)
            print(f"  完成 {len(items)} 条")
        rows = load_all(out_dir)
        print(f"已导出: {export_xlsx(rows, out_dir)}")

    elif args.mode == "full":
        print("全量抓取列表（单线程，间隔 %.1fs）..." % args.delay, flush=True)
        os.makedirs(out_dir, exist_ok=True)
        items = search(session, progress=True,
                       list_workers=args.list_workers,
                       cache_path=os.path.join(out_dir, "list_cache.jsonl"),
                       delay=args.delay)
        print(f"共 {len(items)} 个项目，开始抓详情（可中断，重跑自动续传）", flush=True)
        fetch_details(items, out_dir, args.workers, delay=args.delay)
        rows = load_all(out_dir)
        print(f"已导出: {export_xlsx(rows, out_dir)}")
        print(f"CSV: {export_csv(rows, out_dir)}")

    else:  # export
        rows = load_all(out_dir)
        print(f"共 {len(rows)} 条")
        print(f"Excel: {export_xlsx(rows, out_dir)}")
        print(f"CSV: {export_csv(rows, out_dir)}")


if __name__ == "__main__":
    main()
