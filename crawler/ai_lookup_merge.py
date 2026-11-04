# -*- coding: utf-8 -*-
"""把 AI 互联网检索结果（raw_data/ai_lookup/results.jsonl）合并进行 dict 行。

供两处共用：
  - apply_ai_lookup.py  → 合并进 raw_data/exports/beian_master.csv
  - export_dataset.py   → 合并进公开数据集的 processed/beian_master

行是中文键的 dict，至少要有「备案编号」「匹配类别」「备注」。
合并是幂等的：备注里旧的「AI检索…」段落先清掉再按最新结果重写。

规则：
  found + high/medium  匹配类别 → AI寻找，填 AI户数/AI物业费/AI均价/AI来源
  found + low          类别不变，备注里留一条存疑记录
  ambiguous            类别不变，备注注明「搜到同名但不能确认是这个小区」
  not_found            类别不变，备注注明已检索无果
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "raw_data", "ai_lookup", "results.jsonl")

MARK = "AI检索"

# 公开数据集里追加的 4 列（(列名, 字段含义) 元组，排在「备注」前）
AI_COLS = [
    ("AI户数", "AI 网上检索到的户数（户），来源与链接见备注"),
    ("AI户数口径", "户数口径四选一：单条备案 / 本备案分区 / 整小区合计 / 整小区合计·分区未拆。"
                  "后两种是「整小区合计」，其中带「分区未拆」的为多条备案共用同一个小区总数，"
                  "求和前必须按「链家id」去重"),
    ("AI物业费", "AI 网上检索到的物业费（元/㎡·月）"),
    ("AI均价", "AI 网上检索到的挂牌均价（元/㎡）"),
    ("AI来源", "AI 检索来源页面链接"),
]


def load_results():
    """读取检索结果，同 id 后写的覆盖先写的；坏行跳过。"""
    out = {}
    if os.path.exists(RESULTS):
        for line in open(RESULTS, encoding="utf-8", errors="replace"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                out[r["id"]] = r
            except (json.JSONDecodeError, KeyError):
                continue
    return out


def strip_ai_note(note):
    """去掉备注里以前写入的 AI检索 段落（幂等）。

    备注是「；」拼接的，而 reason 里本身也带「；」，逐段过滤会把
    上次写入的 note 切碎留下残段。AI 段落总是追加在末尾，所以
    从第一次出现 MARK 的位置整段截断最稳。
    """
    note = note or ""
    i = note.find(MARK)
    return note[:i].rstrip("；") if i != -1 else note


def merge_rows(rows, res=None):
    """就地合并检索结果进 rows，返回分类统计 Counter。"""
    import collections

    if res is None:
        res = load_results()
    stat = collections.Counter()

    for r in rows:
        rec = res.get(r.get("备案编号"))
        if not rec:
            continue
        st = rec["status"]
        conf = rec.get("confidence") or ""
        note = strip_ai_note(r.get("备注"))

        for c, _ in AI_COLS:
            r.setdefault(c, "")

        if st == "found" and conf in ("high", "medium"):
            r["匹配类别"] = "AI寻找"
            if rec.get("households") is not None:
                r["AI户数"] = rec["households"]
                r["AI户数口径"] = "单条备案"
            if rec.get("fee") is not None:
                r["AI物业费"] = rec["fee"]
            if rec.get("price") is not None:
                r["AI均价"] = rec["price"]
            r["AI来源"] = rec.get("url") or rec.get("site") or ""
            src = rec.get("site") or "网页"
            tail = f"（来源：{src} {rec['url']}）" if rec.get("url") else f"（来源：{src}）"
            add = f"{MARK}：{rec['reason']}{tail}"
            stat["AI寻找"] += 1

        elif st == "found":  # low 置信
            add = f"{MARK}存疑：{rec['reason']}"
            if rec.get("url"):
                add += f"（{rec['url']}）"
            stat["存疑"] += 1

        elif st == "ambiguous":
            add = f"{MARK}未采用：{rec['reason']}"
            if rec.get("url"):
                add += f"（{rec['url']}）"
            stat["未采用"] += 1

        else:
            add = f"{MARK}未找到：{rec['reason']}"
            stat["未找到"] += 1

        r["备注"] = "；".join(x for x in (note, add) if x)

    return stat
