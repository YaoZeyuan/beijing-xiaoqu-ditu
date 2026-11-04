# -*- coding: utf-8 -*-
"""记录一条「多对一小区」检索结果，追加写入 raw_data/ai_lookup/results_m2.jsonl。

和第一轮的 ai_lookup_record.py 是同一套追加写思路（并发安全、断点续传），
只是 key 从「备案编号」变成「链家id」，并多了一个「分区值」入口：

  # 查到整小区 1226 户，且百科/链家写明了分区构成
  python crawler/ai_lookup_record_m2.py --lj 1112995421285636 --status found \
      --households 1226 --fee 2.5 --site "百度百科" --confidence high \
      --url "https://baike.baidu.com/item/保利花园C区" \
      --part B2DE5B01...=0 --part 9A5B...=1226 \
      --reason "百科词条保利花园C区 27栋1226户；C区即该词条口径"

--part 是「备案编号=户数」，可重复多次，也可以写成「备案编号=户数/物业费」。
整小区值填 --households，只有分区值就直接把它们放进 --part。

查不到：
  python crawler/ai_lookup_record_m2.py --lj 1112... --status not_found --reason "..."

搜到的是整条街/更大范围、或同名不同区：
  python crawler/ai_lookup_record_m2.py --lj 1112... --status ambiguous --reason "..."
"""
import argparse
import datetime
import json
import msvcrt
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "raw_data/ai_lookup/results_m2.jsonl")
LOCK = RESULTS + ".lock"


def append_line(path, data):
    """加锁追加一行。

    Windows 上 O_APPEND 是「seek 到末尾 + write」两步，多个进程同时写会
    互相覆盖行首（实测 6 并发下约 4% 的行被截断）。所以先对独立的锁文件
    加 1 字节排它锁，再写目标文件。加锁失败就短睡重试，最多等 20 秒。
    """
    fd_lock = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_BINARY)
    try:
        got = False
        for _ in range(2000):
            try:
                msvcrt.locking(fd_lock, msvcrt.LK_NBLCK, 1)
                got = True
                break
            except OSError:
                time.sleep(0.01)
        if not got:
            sys.exit("!! 等待写盘锁超时，稍后重试这一条")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_BINARY)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
        finally:
            msvcrt.locking(fd_lock, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd_lock)


def parse_part(s):
    """「ID=1226」或「ID=1226/2.5」→ (id, {'households':…, 'fee':…})"""
    if "=" not in s:
        sys.exit(f"!! --part 格式应为 ID=户数[/物业费]，收到：{s}")
    pid, val = s.split("=", 1)
    hh, fee = (val.split("/", 1) + [""])[:2]
    d = {}
    if hh.strip():
        d["households"] = int(float(hh))
    if fee.strip():
        d["fee"] = float(fee)
    if not d:
        sys.exit(f"!! --part 没有数值：{s}")
    return pid.strip(), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lj", required=True, help="链家小区 id（队列里的 key）")
    ap.add_argument("--status", required=True, choices=["found", "not_found", "ambiguous"])
    ap.add_argument("--households", type=int, help="整小区户数")
    ap.add_argument("--fee", type=float, help="整小区物业费，元/㎡·月")
    ap.add_argument("--price", type=int, help="整小区挂牌均价，元/㎡")
    ap.add_argument("--part", action="append", default=[], help="备案编号=户数[/物业费]")
    ap.add_argument("--share", action="append", default=[],
                    help="整小区值可下移的备案编号（备案本身就是整小区口径），可重复")
    ap.add_argument("--url", default="")
    ap.add_argument("--site", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--confidence", default="", choices=["", "high", "medium", "low"])
    ap.add_argument("--reason", required=True)
    a = ap.parse_args()

    parts = {}
    for s in a.part:
        pid, d = parse_part(s)
        parts[pid] = d

    if a.status == "found" and a.households is None and a.fee is None \
            and a.price is None and not parts:
        sys.exit("!! status=found 但整小区值/分区值/物业费/均价一个都没给")

    rec = {
        "key": a.lj,
        "status": a.status,
        "households": a.households,
        "fee": a.fee,
        "price": a.price,
        "parts": parts,
        "share": a.share,
        "url": a.url,
        "site": a.site,
        "title": a.title,
        "confidence": a.confidence,
        "reason": a.reason,
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    line = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
    append_line(RESULTS, line)

    tags = []
    if rec["households"] is not None:
        tags.append(f"整小区{rec['households']}户")
    if rec["fee"] is not None:
        tags.append(f"{rec['fee']}元")
    if parts:
        tags.append(f"分区{len(parts)}条")
    print(f"✓ {a.lj} {a.status} {' '.join(tags)} {a.confidence}")


if __name__ == "__main__":
    main()
