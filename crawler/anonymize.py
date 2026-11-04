#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
发布数据脱敏
============
公开项目的硬要求：所有人名与手机号必须打码。
姓名只保留第一个字（单字名记 *），联系电话只保留前 3 位，其余字符替换为 *。
覆盖项目/业委会负责人、企业法定代表人，并按字段名兜底自动识别新增的个人信息列。
规则幂等，重复调用结果不变。

正式数据集由 build_dataset.py 生成，它直接调用本文件的函数；本文件也可以
单独跑，输出逐行脱敏后的 jsonl。

用法:
    python anonymize.py                     # raw_data/raw_projects.jsonl -> data/projects.masked.jsonl
    python anonymize.py --in a.jsonl --out b.jsonl
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "raw_data", "raw_projects.jsonl")
DATA = os.path.join(HERE, "data")

NAME_FIELDS = ("项目负责人姓名", "业委会(物管会)负责人姓名", "法定代表人")
PHONE_FIELDS = ("项目负责人联系方式", "业委会(物管会)负责人联系方式")

# 字段名兜底：以后源站新增的个人信息列，不用改这里也会被自动打码
NAME_KEYS = ("姓名",)
PHONE_KEYS = ("联系方式", "电话", "手机")


def mask_name(v: str) -> str:
    """张三丰 -> 张**；单字名 -> *（保留首字等于没打码）"""
    v = (v or "").strip()
    if not v:
        return ""
    if len(v) == 1:
        return "*"
    return v[0] + "*" * (len(v) - 1)


def mask_phone(v: str) -> str:
    """13800138000 -> 138********；太短的整体打码"""
    v = (v or "").strip()
    if not v:
        return ""
    return (v[:3] + "*" * (len(v) - 3)) if len(v) > 4 else "*" * len(v)


def mask_record(rec: dict) -> dict:
    """就地脱敏一条记录：显式字段 + 字段名兜底，重复调用结果不变"""
    for k in list(rec.keys()):
        v = rec.get(k)
        if not isinstance(v, str) or not v.strip():
            continue
        if k in NAME_FIELDS or any(t in k for t in NAME_KEYS):
            rec[k] = mask_name(v)
        elif k in PHONE_FIELDS or any(t in k for t in PHONE_KEYS):
            rec[k] = mask_phone(v)
    return rec


def main():
    ap = argparse.ArgumentParser(description="发布数据脱敏")
    ap.add_argument("--in", dest="src", default=RAW)
    ap.add_argument("--out", dest="dst",
                    default=os.path.join(DATA, "projects.masked.jsonl"))
    args = ap.parse_args()

    if not os.path.exists(args.src):
        raise SystemExit(f"找不到 {args.src}")
    os.makedirs(os.path.dirname(args.dst) or ".", exist_ok=True)

    n = 0
    with open(args.src, encoding="utf-8") as f, \
            open(args.dst, "w", encoding="utf-8") as out:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            out.write(json.dumps(mask_record(rec), ensure_ascii=False) + "\n")
            n += 1

    print(f"{n} 条 -> {args.dst}")


if __name__ == "__main__":
    main()
