# -*- coding: utf-8 -*-
"""把第二轮检索结果（raw_data/ai_lookup/results_m2.jsonl）合并进 beian 行。

第一轮（ai_lookup_merge.py）处理的是「备案 ↔ 链家未匹配」，一个备案一个检索结果。
这一轮处理「多对一」：多条备案共用同一个链家小区，检索结果挂在链家小区上。

合并规则（对应 RULES_M2.md 的判断准则）：

  1. 备案分区值（parts 里有本条备案的编号）→ 直接填，口径「本备案分区」
  2. 整小区值（households）→ 只有当本条备案本身就是整小区口径时才填：
       - 检索时用 --share 明确指定的备案；或
       - 备案名不带分区标记，且
           · 该小区下只有这一条非分区备案，或
           · 该备案名 == 链家小区名
     否则不填，只在备注写明「整小区 N 户，本备案为分区口径未下移」
  3. 物业费/均价跟着同一条规则走：分区报价常不同，不整片下移
  4. 置信度 low 一律不填，备注记「AI小区补查存疑」
  5. 置信度为空按 medium（子代理给了数据但漏写置信度）

为什么不把整小区值无脑填给每条备案：2,402 条备案对着 863 个小区，无脑填会让
户数总量放大 2.8 倍。填了的也标了口径（AI户数口径），导出/前端去重时按
「链家id + 整小区合计」去重即可。
"""
import collections
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "raw_data", "ai_lookup", "results_m2.jsonl")
QUEUE = os.path.join(ROOT, "raw_data", "ai_lookup", "queue_m2.jsonl")

MARK = "AI小区补查"

# 与 ai_lookup_queue_m2.py 的 PART 保持一致
PART = re.compile(r"[A-Za-z]区|期|号楼|号院|第.{1,2}区|地块|院$|楼$")


def norm(s):
    s = re.sub(r"[（(].*?[)）]", "", s or "")
    return re.sub(r"[\s·、,，\-—_]", "", s)


def load_results():
    """同 key 后写覆盖先写；坏行与不在队列里的 key 跳过。"""
    valid = set()
    if os.path.exists(QUEUE):
        for line in open(QUEUE, encoding="utf-8"):
            if line.strip():
                try:
                    valid.add(json.loads(line)["key"])
                except (json.JSONDecodeError, KeyError):
                    continue
    out = {}
    if os.path.exists(RESULTS):
        for line in open(RESULTS, encoding="utf-8", errors="replace"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, KeyError):
                continue
            if valid and r["key"] not in valid:
                continue
            out[r["key"]] = r
    return out


def applies(rec, member, members):
    """整小区值能不能落到这条备案上。"""
    share = set(rec.get("share") or [])
    if share:
        return member["备案编号"] in share
    if PART.search(member["备案项目名"] or ""):
        return False
    others = [m for m in members if not PART.search(m["备案项目名"] or "")]
    if len(others) == 1:
        return True
    return norm(member["备案项目名"]) == norm(member["链家小区名"])


def merge_rows(rows, res=None):
    """就地合并第二轮结果，返回分类统计 Counter。"""
    if res is None:
        res = load_results()

    clusters = collections.OrderedDict()
    for r in rows:
        if r.get("关联状态") == "多对一" and r.get("链家id"):
            clusters.setdefault(r["链家id"], []).append(r)

    stat = collections.Counter()
    stat["共享小区合计"] = sum(len(v) for v in clusters.values())

    for lj, members in clusters.items():
        rec = res.get(lj)
        if not rec:
            stat["无检索结果"] += len(members)
            continue
        st = rec.get("status")
        conf = rec.get("confidence") or "medium"
        src = rec.get("site") or "网页"
        url = rec.get("url") or ""
        tail = f"（来源：{src} {url}）" if url else f"（来源：{src}）"
        parts = rec.get("parts") or {}
        whole_hh = rec.get("households")
        whole_fee = rec.get("fee")
        whole_price = rec.get("price")

        for m in members:
            note = ""
            p = parts.get(m["备案编号"]) or {}
            usable = conf in ("high", "medium")

            if st == "found" and usable:
                if p.get("households"):
                    m["AI户数"] = p["households"]
                    m["AI户数口径"] = "本备案分区"
                    note = f"{MARK}：本分区 {p['households']} 户"
                    stat["填部分区户数"] += 1
                    if p.get("fee"):
                        m["AI物业费"] = p["fee"]
                elif whole_hh:
                    if applies(rec, m, members):
                        m["AI户数"] = whole_hh
                        m["AI户数口径"] = "整小区合计"
                        note = f"{MARK}：整小区合计 {whole_hh} 户（本备案即整小区口径）"
                        stat["填整小区户数"] += 1
                    else:
                        # 本备案只是小区的一部分，整小区数不能当它的户数，
                        # 但这个数本身有用（能说明所在小区规模），按参考口径存下，
                        # 统计总量时按「链家id」去重即可。
                        m["AI户数"] = whole_hh
                        m["AI户数口径"] = "整小区合计·分区未拆"
                        note = (f"{MARK}：所在小区合计 {whole_hh} 户，"
                                f"本备案仅为其中一个分区，未拆分（统计需按链家id去重）")
                        stat["填小区参考户数"] += 1
                elif p.get("fee") or whole_fee or whole_price:
                    note = f"{MARK}：仅补到物业费/均价"
                    stat["仅物业费均价"] += 1
                else:
                    note = f"{MARK}：未取到可用数值"
                    stat["无可用数值"] += 1

                # 物业费 / 均价：分区值优先，其次整小区值（同一口径才用）
                if not p.get("fee"):
                    if whole_fee and applies(rec, m, members):
                        m["AI物业费"] = whole_fee
                if whole_price and applies(rec, m, members):
                    m["AI均价"] = whole_price

                if m.get("AI户数") or m.get("AI物业费") or m.get("AI均价"):
                    m["AI来源"] = url or src
                    note += f"，{rec.get('reason', '')}{tail}"
                    if conf == "medium":
                        note += "［中置信］"
            elif st == "found" and not usable:
                note = f"{MARK}存疑：{rec.get('reason', '')}{tail}"
                stat["存疑"] += 1
            elif st == "ambiguous":
                note = f"{MARK}未采用：{rec.get('reason', '')}{tail}"
                stat["未采用"] += 1
            else:
                note = f"{MARK}未找到：{rec.get('reason', '')}{tail}"
                stat["未找到"] += 1

            # AI 段落总在末尾，从第一次出现 MARK 处截断（reason 里也带「；」，逐段过滤会留残段）
            prev = m.get("备注") or ""
            i = prev.find(MARK)
            base = prev[:i].rstrip("；") if i != -1 else prev
            m["备注"] = "；".join(x for x in (base, note) if x)

    return stat
