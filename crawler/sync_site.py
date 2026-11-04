#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把当前抓取进度同步到前端地图站点（抓取还在跑的时候也能用）

做的事：
  1. 从 data/list_cache.jsonl 汇总出 data/list_all.json（不受抓取进行中影响）
  2. raw_data/raw_projects.jsonl 有更新时，先跑 build_dataset.py 生成正式数据集
  3. 调用 web/build_data.py 生成前端数据
  4. 重新构建前端（npm run build）

用法: python sync_site.py [--no-build]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RAW = os.path.join(os.path.dirname(HERE), "raw_data")
SITE = os.path.join(os.path.dirname(HERE), "web")


def summarize_list():
    """从按页缓存的 list_cache.jsonl 汇总去重后的列表数据"""
    src = os.path.join(DATA, "list_cache.jsonl")
    if not os.path.exists(src):
        print("没有列表缓存，跳过")
        return
    seen = {}
    bad = 0
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                bad += 1          # 抓取中可能读到半行，忽略
                continue
            for it in rec.get("items", []):
                seen[it["project_no"]] = it
    out = os.path.join(DATA, "list_all.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(list(seen.values()), f, ensure_ascii=False)
    print(f"列表汇总：{len(seen)} 条（跳过损坏行 {bad}）-> {out}")


def main():
    summarize_list()

    raw = os.path.join(RAW, "raw_projects.jsonl")
    py = sys.executable
    clean_env = {**os.environ, "HTTP_PROXY": "", "HTTPS_PROXY": "",
                 "http_proxy": "", "https_proxy": ""}

    # 原始抓取有更新时，先重新生成正式数据集（脱敏 + 拆物业费 + 补街道）
    if os.path.exists(raw):
        print("\n--- 生成正式数据集 ---")
        subprocess.run([py, os.path.join(HERE, "build_dataset.py")], check=True,
                       cwd=HERE, env=clean_env)
    else:
        print(f"\n没有 {raw}，跳过数据集重建，直接使用已有 projects.json")

    print("\n--- 构建前端数据 ---")
    subprocess.run([py, os.path.join(SITE, "build_data.py")], check=True,
                   cwd=SITE, env=clean_env)

    if "--no-build" not in sys.argv:
        print("\n--- 构建前端 ---")
        subprocess.run("npm run build", shell=True, cwd=SITE, check=True)
        print("\n完成。需要重新部署才有线上更新。")


if __name__ == "__main__":
    main()
