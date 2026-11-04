#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成街道级行政边界：区名 -> 街道边界 GeoJSON

数据源：rooma1989/china_geo_data（按区存放的乡镇街道边界，properties 为 省/市/县/乡）
        原始数据是 WGS84，而现有区级底图（DataV.GeoAtlas）是 GCJ-02，
        两者直接叠加会整体偏移约 500m，所以这里统一转成 GCJ-02。

处理流程：
  1. 16 个区逐个下载（缓存到 raw_data/streets_raw/，重跑不再请求）
  2. WGS84 -> GCJ-02
  3. Douglas-Peucker 简化（容差默认 0.00015 度 ≈ 15m）
  4. 合并为单个 FeatureCollection，properties 只留 name / district
  5. 输出 web/public/data/beijing_streets.json

用法:
  python tools/build_streets.py                # 用缓存，缺失才下载
  python tools/build_streets.py --refresh      # 强制重新下载
  python tools/build_streets.py --tolerance 0.0002
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "raw_data", "streets_raw")
# 只输出按区拆分的分片，前端下钻时按需加载；不产出合并版（1.6MB，前端用不到）
SHARD_DIR = os.path.join(ROOT, "web", "public", "data", "streets")

# 仓库里的文件名用的是 2015 年撤县设区之前的旧名
DISTRICTS = [
    ("东城区", "东城区"), ("西城区", "西城区"), ("朝阳区", "朝阳区"), ("丰台区", "丰台区"),
    ("石景山区", "石景山区"), ("海淀区", "海淀区"), ("门头沟区", "门头沟区"), ("房山区", "房山区"),
    ("通州区", "通州区"), ("顺义区", "顺义区"), ("昌平区", "昌平区"), ("大兴区", "大兴区"),
    ("怀柔区", "怀柔区"), ("平谷区", "平谷区"), ("密云区", "密云县"), ("延庆区", "延庆县"),
]

BASE = ("https://raw.githubusercontent.com/rooma1989/china_geo_data/master/"
        "%E5%8C%97%E4%BA%AC%E5%B8%82/%E5%8C%97%E4%BA%AC%E5%B8%82/geo_{name}.json")


# ---------- 坐标转换 ----------
_A = 6378245.0
_EE = 0.00669342162296594323


def _transform_lat(x, y):
    r = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    r += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return r


def _transform_lng(x, y):
    r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    r += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return r


def wgs84_to_gcj02(lng, lat):
    """公开经验算法，境外坐标原样返回"""
    if not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = 1 - _EE * math.sin(radlat) ** 2
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


# ---------- 简化 ----------
def _dist_to_seg(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(pts, tol):
    """Douglas-Peucker，迭代实现避免深递归"""
    n = len(pts)
    if n < 4:
        return pts
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        dmax, idx = 0.0, i
        for k in range(i + 1, j):
            d = _dist_to_seg(pts[k], pts[i], pts[j])
            if d > dmax:
                dmax, idx = d, k
        if dmax > tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(pts, keep) if k]


def simplify_ring(ring, tol):
    if len(ring) < 4 or tol <= 0:
        return ring
    closed = ring[0] == ring[-1]
    pts = ring[:-1] if closed else ring
    out = simplify(pts, tol)
    if closed:
        out = out + [out[0]]
    return out


def simplify_geom(geom, tol):
    t = geom.get("type")
    if t == "Polygon":
        return {"type": "Polygon", "coordinates": [simplify_ring(r, tol) for r in geom["coordinates"]]}
    if t == "MultiPolygon":
        return {"type": "MultiPolygon",
                "coordinates": [[simplify_ring(r, tol) for r in poly] for poly in geom["coordinates"]]}
    return geom


# ---------- 下载 ----------
def fetch(district, refresh=False):
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, f"{district}.json")
    if os.path.exists(path) and not refresh:
        return path
    url = BASE.format(name=urllib.parse.quote(district))
    print(f"  下载 {district} …", end="", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (data build)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)
    print(f" {len(data)/1024:.0f} KB")
    time.sleep(0.4)  # 对 GitHub raw 也保持克制
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="强制重新下载")
    ap.add_argument("--tolerance", type=float, default=0.00015, help="简化容差（度）")
    args = ap.parse_args()

    features = []
    stat = []
    for name, fname in DISTRICTS:
        path = fetch(fname, args.refresh)
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        before = after = 0
        for it in items:
            props = it.get("properties") or {}
            street = (props.get("乡") or props.get("镇") or "").strip()
            if not street:
                continue
            geom = it.get("geometry")
            if not geom:
                continue
            # 坐标转换
            def conv(c):
                if isinstance(c[0], (int, float)):
                    lng, lat = wgs84_to_gcj02(c[0], c[1])
                    return [round(lng, 6), round(lat, 6)]
                return [conv(x) for x in c]
            geom["coordinates"] = conv(geom["coordinates"])
            before += _count_pts(geom["coordinates"])
            geom = simplify_geom(geom, args.tolerance)
            after += _count_pts(geom["coordinates"])
            features.append({
                "type": "Feature",
                "properties": {"name": street, "district": name},
                "geometry": geom,
            })
        stat.append((name, len(items), before, after))

    # 按区拆分：下钻某个区时只加载这一份（东城 25KB，密云 176KB），
    # 避免首屏为看城六区先拖 1.6MB
    by_district = {}
    for ft in features:
        by_district.setdefault(ft["properties"]["district"], []).append(ft)
    os.makedirs(SHARD_DIR, exist_ok=True)
    for d, items in by_district.items():
        path = os.path.join(SHARD_DIR, f"{d}.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"type": "FeatureCollection", "features": items}, f,
                      ensure_ascii=False, separators=(",", ":"))
            f.write("\n")

    tb = sum(s[2] for s in stat)
    ta = sum(s[3] for s in stat)
    print(f"\n{'区':<10}{'要素':>6}{'原顶点':>10}{'简化后':>10}")
    for n, c, b, a in stat:
        print(f"{n:<10}{c:>6}{b:>10}{a:>10}")
    print(f"\n合计 {len(features)} 个街道/乡镇，顶点 {tb} -> {ta}（保留 {ta/tb*100:.1f}%）")
    total_shard = sum(os.path.getsize(os.path.join(SHARD_DIR, f"{d}.json")) for d in by_district)
    print(f"输出 {SHARD_DIR}  {len(by_district)} 个文件，合计 {total_shard/1024:.0f} KB")


def _count_pts(c):
    if isinstance(c[0], (int, float)):
        return 1
    return sum(_count_pts(x) for x in c)


if __name__ == "__main__":
    main()
