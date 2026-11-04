#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全量抓取（可中断续传，5 并发，每个请求成功后休眠 1 秒）

阶段 1：列表页 -> data/list_cache.jsonl（按页缓存：{"page": n, "items": [...]}）
阶段 2：详情页 -> raw_data/raw_projects.jsonl（按 project_no 缓存，22 个原始字段）
阶段 3：汇总 -> data/list_all.json / Excel / CSV

详情存 raw_data/ 是因为里面有两个联系人字段没脱敏，raw_data/ 不进仓库；
正式数据集由 build_dataset.py 从这里生成。

重跑时两个缓存都会被读取，已完成的部分直接跳过，不会重复请求。

用法:
    python crawl_all.py                # 列表 + 详情全量
    python crawl_all.py --list-only    # 只抓列表
    python crawl_all.py --detail-only  # 只抓详情（用已有列表）
"""
import argparse
import json
import os
import sys
import time

import bjjs

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RAW = os.path.join(os.path.dirname(HERE), "raw_data")
DETAIL_FILE = "raw_projects.jsonl"

WORKERS = 5      # 并发数
DELAY = 1.0      # 每个请求成功后休眠秒数


def stage_list():
    """阶段 1：翻完全部列表页"""
    cache = os.path.join(DATA, "list_cache.jsonl")
    print("=" * 60, flush=True)
    print("阶段 1/3：抓取全部列表页（小区名 + 物业企业 + 业委会状态）", flush=True)
    print(f"并发 {WORKERS}，每个请求成功后休眠 {DELAY}s", flush=True)
    if os.path.exists(cache):
        n = sum(1 for _ in open(cache, encoding="utf-8"))
        print(f"已有缓存 {n} 页，将自动续传", flush=True)
    print("=" * 60, flush=True)

    s = bjjs.new_session()
    t0 = time.time()
    items = bjjs.search(s, progress=True, cache_path=cache, delay=DELAY,
                        list_workers=WORKERS)
    path = os.path.join(DATA, "list_all.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    print(f"LIST_DONE {len(items)} 条，耗时 {(time.time()-t0)/60:.1f} 分钟 -> {path}", flush=True)
    return items


def stage_detail(items):
    """阶段 2：抓每个小区的详情（物业费在这里）"""
    print("=" * 60, flush=True)
    print("阶段 2/3：抓取全部详情页（物业服务费标准、收费方式等 22 字段）", flush=True)
    print(f"并发 {WORKERS}，每个请求成功后休眠 {DELAY}s", flush=True)
    print("=" * 60, flush=True)

    t0 = time.time()
    ok = bjjs.fetch_details(items, RAW, workers=WORKERS, delay=DELAY,
                            filename=DETAIL_FILE)
    print(f"DETAIL_DONE 本轮新增 {ok} 条，耗时 {(time.time()-t0)/60:.1f} 分钟", flush=True)


def stage_export():
    """阶段 3：汇总导出"""
    print("=" * 60, flush=True)
    print("阶段 3/3：汇总导出", flush=True)
    rows = bjjs.load_all(RAW, DETAIL_FILE)
    ok = [r for r in rows if not r.get("error")]
    print(f"共 {len(rows)} 条记录，其中成功 {len(ok)} 条", flush=True)
    if ok:
        print(f"Excel: {bjjs.export_xlsx(rows, DATA)}", flush=True)
        print(f"CSV  : {bjjs.export_csv(rows, DATA)}", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--detail-only", action="store_true")
    args = ap.parse_args()

    os.makedirs(DATA, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)

    items = None
    if not args.detail_only:
        items = stage_list()

    if not args.list_only:
        if items is None:
            p = os.path.join(DATA, "list_all.json")
            if not os.path.exists(p):
                sys.exit("缺少 data/list_all.json，请先跑列表阶段")
            items = json.load(open(p, encoding="utf-8"))
            print(f"读取已有列表 {len(items)} 条", flush=True)
        stage_detail(items)
        stage_export()


if __name__ == "__main__":
    main()
