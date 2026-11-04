# -*- coding: utf-8 -*-
"""记录一条 AI 检索结果，追加写入 raw_data/ai_lookup/results.jsonl。

之所以做成命令行而不是直接编辑文件：一是避免手工拼 JSON 出错，
二是每条查完立刻落盘，中断后能断点续传。

用法：
  # 查到了
  python crawler/ai_lookup_record.py --id 1101010001 --status found \
      --households 208 --fee 24 --price 150000 \
      --url "https://m.cih-index.com/wy/industrynews/news/55077500.html" \
      --site "中指研究院" --confidence high \
      --reason "中指研究院小区报告标注总户数208户、物业费24元/㎡·月，与备案物业费一致"

  # 没查到
  python crawler/ai_lookup_record.py --id 1101010002 --status not_found \
      --reason "百度百科、吉屋、安居客均无独立页面，只搜到同名的更大范围街区"

  # 搜到了同名但不是这个小区
  python crawler/ai_lookup_record.py --id 1101010003 --status ambiguous \
      --url "https://bj.jiwu.com/xiaoqu/detail/807957.html" \
      --reason "搜到「东交民巷」257户，但那是整片街区，不是东交民巷7号院"

## 为什么是「追加」而不是「读-改-写」

多个子代理会并行写同一个文件。若采用「读整个文件 → 改一条 → 写回」，
两个进程会各自基于旧快照写回，后写的把先写的记录冲掉——实测 8 个并发丢了 2 条。
文件锁在这个场景也不可靠（Windows 上 O_EXCL 语义与 POSIX 有差异）。

因此改成**只追加**：每条记录一行，用 O_APPEND 单次 write 落盘。
30 个并发进程实测 30 条全部写入，无丢失。
同一个 id 出现多行时，**以最后一行为准**（读取时覆盖，见 ai_lookup_status.py
与 ai_lookup_dedupe.py）——所以「先记录、事后修正」只需再执行一次本命令即可。
"""
import argparse
import datetime
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "raw_data/ai_lookup/results.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--status", required=True, choices=["found", "not_found", "ambiguous"])
    ap.add_argument("--households", type=int)
    ap.add_argument("--fee", type=float)
    ap.add_argument("--price", type=int)
    ap.add_argument("--url", default="")
    ap.add_argument("--site", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--confidence", default="", choices=["", "high", "medium", "low"])
    ap.add_argument("--reason", required=True)
    a = ap.parse_args()

    if a.status == "found" and a.households is None and a.fee is None and a.price is None:
        sys.exit("!! status=found 但户数/物业费/均价一个都没给")

    rec = {
        "id": a.id,
        "status": a.status,
        "households": a.households,
        "fee": a.fee,
        "price": a.price,
        "url": a.url,
        "site": a.site,
        "title": a.title,
        "confidence": a.confidence,
        "reason": a.reason,
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    line = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(RESULTS, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)

    tags = []
    if rec["households"] is not None:
        tags.append(f"{rec['households']}户")
    if rec["fee"] is not None:
        tags.append(f"{rec['fee']}元")
    if rec["price"] is not None:
        tags.append(f"{rec['price']}元/㎡")
    print(f"✓ {a.id} {a.status} {' '.join(tags)} {a.confidence}")


if __name__ == "__main__":
    main()
