<template>
  <div class="map-root">
    <div ref="el" class="map-canvas"></div>

    <!-- 街道视图：返回按钮 + 边界缺失提示 -->
    <button v-if="selected" class="back-btn" @click="$emit('back')">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M15 18l-6-6 6-6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      返回全市
    </button>

    <div v-if="selected && !geoLoading && missing.length" class="geo-warn">
      {{ missing.length }} 个街道无边界数据（{{ missing.slice(0, 3).join('、') }}{{ missing.length > 3 ? ' 等' : '' }}），已在小区的街道明细中保留
    </div>

    <div v-if="geoLoading" class="geo-loading">
      <span class="gl-spin"></span>加载 {{ selected }} 街道边界…
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import * as echarts from 'echarts'
import bjGeo from '../data/beijing.json'

echarts.registerMap('beijing', bjGeo)

const props = defineProps({
  districts: { type: Array, required: true },        // 区级聚合 [{name, value, count, feeAvg, selfGov, regime}]
  streets: { type: Array, default: () => [] },       // 当前区街道聚合
  metric: { type: String, default: 'count' },
  selected: { type: String, default: '' },           // 选中的区
  selectedStreet: { type: String, default: '' },     // 选中的街道
})
const emit = defineEmits(['select', 'selectStreet', 'back'])

const el = ref(null)
let chart = null

const geoCache = new Map()      // 已加载的区级街道边界
const activeGeo = ref(null)     // 当前显示的区街道边界
const geoLoading = ref(false)

const METRIC_META = {
  count: {
    label: '小区数量',
    colors: ['#0d1a2e', '#1b3b66', '#2d6fae', '#4c9aff', '#9cccff'],
    fmt: (v) => `${v} 个`,
  },
  feeAvg: {
    label: '平均物业费',
    colors: ['#0e2a24', '#155e4b', '#3f9e6a', '#c9b458', '#e8663c', '#d62828'],
    fmt: (v) => `${v} 元/㎡·月`,
  },
  hh: {
    label: '小区规模（户数合计）',
    colors: ['#15102e', '#2a2060', '#4c3a9e', '#7a63d4', '#a78bfa', '#d8c9ff'],
    fmt: (v) => (v >= 10000 ? `${(v / 10000).toFixed(1)} 万户` : `${v} 户`),
  },
  price: {
    label: '平均挂牌价',
    colors: ['#26060f', '#5c1030', '#9e2050', '#d64570', '#ec7d9d', '#f6bcd0'],
    fmt: (v) => `${v.toLocaleString()} 元/㎡`,
  },
  rate: {
    label: '自治组织覆盖率',
    colors: ['#231a1a', '#4a2020', '#7a4a1e', '#3f7a3a', '#22c55e'],
    fmt: (v) => `${(v * 100).toFixed(1)}%`,
  },
}

const currentMeta = computed(() => METRIC_META[props.metric] || METRIC_META.count)

// ── 街道名归一化 ──
// 数据侧的街道名来自小区清单，边界侧来自行政区划图，二者的后缀不一定一致：
// 「沙河地区」与「沙河镇」是同一实体（北京的地区办事处与镇合署），
// 「良乡街道」与「良乡镇」同理。这里先精确匹配，再按去掉后缀后的核心词唯一匹配。
const SUFFIX = /(街道|地区|镇|乡)$/

function coreOf(s) {
  return (s || '').trim().replace(SUFFIX, '')
}

const streetItems = computed(() => {
  const geo = activeGeo.value
  if (!geo) return []
  const names = new Set(geo.features.map((f) => f.properties.name))
  // 核心词 -> 边界名（多候选时置 null，避免张冠李戴）
  const byCore = new Map()
  for (const n of names) {
    const c = coreOf(n)
    if (byCore.has(c)) {
      if (byCore.get(c) !== n) byCore.set(c, null)
    } else {
      byCore.set(c, n)
    }
  }
  const used = new Set()
  const out = []
  for (const s of props.streets) {
    if (!s.name || s.name === '-' || s.name === '未标注街道') continue
    let name = names.has(s.name) ? s.name : byCore.get(coreOf(s.name))
    if (!name || used.has(name)) continue
    used.add(name)
    // rawName 是数据侧的写法（如「沙河地区」），name 是边界侧的写法（如「沙河镇」），
    // 二者可能不同，点击回传与高亮都要用数据侧的写法才对得上筛选条件
    out.push({ ...s, rawName: s.name, name })
  }
  return out
})

const missing = computed(() => {
  if (!activeGeo.value) return []
  // 用数据侧的原始写法比对，streetItems 里的 name 已经换成边界侧写法了
  const shown = new Set(streetItems.value.map((s) => s.rawName))
  return props.streets
    .filter((s) => s.name && s.name !== '-' && s.name !== '未标注街道' && !shown.has(s.name))
    .map((s) => s.name)
})

async function loadDistrictGeo(d) {
  if (!d) {
    activeGeo.value = null
    return
  }
  if (geoCache.has(d)) {
    activeGeo.value = geoCache.get(d)
    render()
    return
  }
  geoLoading.value = true
  activeGeo.value = null
  try {
    const url = new URL(`data/streets/${encodeURIComponent(d)}.json`, document.baseURI)
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const geo = await res.json()
    geoCache.set(d, geo)
    echarts.registerMap('streets_' + d, geo)
    if (props.selected === d) {
      activeGeo.value = geo
      render()
    }
  } catch (e) {
    console.error('街道边界加载失败', d, e)
  } finally {
    geoLoading.value = false
  }
}

function itemsForView() {
  return props.selected ? streetItems.value : props.districts
}

function mapNameForView() {
  return props.selected ? 'streets_' + props.selected : 'beijing'
}

function buildOption() {
  const meta = currentMeta.value
  const items = itemsForView()
  const values = items.map((d) => d.value).filter((v) => v !== null && v !== undefined && v > 0)
  const max = values.length ? Math.max(...values) : 1
  const isStreet = !!props.selected

  // 高亮项：区级比区名，街道级比数据侧写法
  const activeName = isStreet
    ? (streetItems.value.find((s) => s.rawName === props.selectedStreet)?.name || '')
    : props.selected

  const data = items.map((d) => ({
    name: d.name,
    value: d.value === null || d.value === undefined ? '-' : Number(d.value),
    itemStyle: d.name === activeName
      ? { areaColor: '#2c4266', borderColor: '#7c5cff', borderWidth: 1.6 }
      : undefined,
    raw: d,
  }))

  return {
    backgroundColor: 'transparent',
    animationDuration: 700,
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(12,18,30,0.96)',
      borderColor: '#2a3550',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#e8eefb', fontSize: 12 },
      extraCssText: 'border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.45);border:1px solid #2a3550;',
      formatter: (p) => {
        const r = p.data && p.data.raw
        if (!r) return `<b>${p.name}</b><br/><span style="color:#8b98b2">暂无数据</span>`
        const fee = r.feeAvg ? `${r.feeAvg.toFixed(2)} 元/㎡·月` : '—'
        const rate = r.count ? `${((r.selfGov / r.count) * 100).toFixed(1)}%` : '—'
        const hh = r.hh ? (r.hh >= 10000 ? `${(r.hh / 10000).toFixed(1)} 万户` : `${r.hh} 户`) : '—'
        const price = r.priceAvg ? `${r.priceAvg.toLocaleString()} 元/㎡` : '—'
        return `
          <div style="font-weight:600;font-size:13px;margin-bottom:6px">${r.name}</div>
          <div style="display:grid;grid-template-columns:auto auto;gap:2px 18px;font-size:12px;color:#b9c4d8">
            <span style="color:#8b98b2">小区数</span><span style="text-align:right;color:#e8eefb">${r.count}</span>
            <span style="color:#8b98b2">户数合计</span><span style="text-align:right;color:#e8eefb">${hh}</span>
            <span style="color:#8b98b2">平均物业费</span><span style="text-align:right;color:#e8eefb">${fee}</span>
            <span style="color:#8b98b2">平均挂牌价</span><span style="text-align:right;color:#e8eefb">${price}</span>
            <span style="color:#8b98b2">业委会</span><span style="text-align:right;color:#22c55e">${r.regime['业委会'] || 0}</span>
            <span style="color:#8b98b2">物管会</span><span style="text-align:right;color:#f59e0b">${r.regime['物管会'] || 0}</span>
            <span style="color:#8b98b2">均未成立</span><span style="text-align:right;color:#ef4444">${r.regime['未成立'] || 0}</span>
          </div>
          <div style="margin-top:6px;padding-top:6px;border-top:1px solid #1f2a40;font-size:11px;color:#5b6880">
            自治组织覆盖率 ${rate} · ${isStreet ? '点击只看该街道' : '点击查看街道'}
          </div>`
      },
    },
    visualMap: {
      type: 'continuous',
      min: 0,
      max,
      left: 14,
      bottom: 18,
      itemWidth: 12,
      itemHeight: 110,
      calculable: true,
      inRange: { color: meta.colors },
      text: [meta.fmt(max), '0'],
      textStyle: { color: '#8b98b2', fontSize: 11 },
      formatter: (v) => (props.metric === 'rate'
        ? `${(v * 100).toFixed(0)}%`
        : props.metric === 'feeAvg' ? v.toFixed(1)
        : props.metric === 'hh' ? (v >= 10000 ? `${(v / 10000).toFixed(1)}万` : Math.round(v))
        : props.metric === 'price' ? `${Math.round(v / 1000)}k`
        : Math.round(v)),
    },
    series: [
      {
        type: 'map',
        map: mapNameForView(),
        roam: true,
        // 街道级用 top/bottom/left/right 框定绘制区，交给 echarts 自适应 bbox；
        // 用 layoutCenter+layoutSize 时容器高宽比一变就容易偏上或偏下
        ...(isStreet
          ? { top: 18, bottom: 30, left: 30, right: 30, zoom: 1 }
          : { zoom: 1.14, center: [116.36, 40.1], layoutCenter: ['50%', '52%'], layoutSize: '96%' }),
        scaleLimit: { min: 0.85, max: 10 },
        selectedMode: false,
        data,
        labelLayout: { hideOverlap: true },
        itemStyle: {
          areaColor: '#111a2b',
          borderColor: isStreet ? '#2c3d5c' : '#25334d',
          borderWidth: isStreet ? 0.8 : 0.9,
          shadowColor: 'rgba(76,154,255,0.10)',
          shadowBlur: 16,
        },
        label: {
          show: true,
          color: '#b8c6da',
          fontSize: isStreet ? 9 : 10.5,
          lineHeight: isStreet ? 11 : 14,
          formatter: (p) => {
            const r = p.data && p.data.raw
            if (!r || !r.count) return p.name
            if (isStreet) return p.name
            if (props.metric === 'rate') return `${p.name}\n${((r.selfGov / r.count) * 100).toFixed(0)}%`
            if (props.metric === 'feeAvg') return `${p.name}\n${r.feeAvg ? r.feeAvg.toFixed(1) : '—'}`
            if (props.metric === 'hh') return `${p.name}\n${r.hh ? (r.hh >= 10000 ? `${(r.hh / 10000).toFixed(1)}万` : r.hh) : '—'}`
            if (props.metric === 'price') return `${p.name}\n${r.priceAvg ? (r.priceAvg >= 10000 ? `${(r.priceAvg / 10000).toFixed(1)}万` : r.priceAvg) : '—'}`
            return `${p.name}\n${r.count}`
          },
        },
        emphasis: {
          label: { show: true, color: '#ffffff', fontSize: isStreet ? 11 : 12, fontWeight: 600 },
          itemStyle: {
            areaColor: '#2a3f63',
            borderColor: '#4c9aff',
            borderWidth: 1.6,
            shadowColor: 'rgba(76,154,255,0.45)',
            shadowBlur: 22,
          },
        },
      },
    ],
  }
}

function render() {
  if (!chart) return
  // 街道边界还没到位时先不画，避免 echarts 找不到 map 报警
  if (props.selected && !activeGeo.value) return
  chart.setOption(buildOption(), true)
}

onMounted(() => {
  chart = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
  chart.on('click', (p) => {
    if (p.componentType !== 'series' && p.componentType !== 'geo') return
    if (props.selected) {
      const hit = streetItems.value.find((x) => x.name === p.name)
      emit('selectStreet', hit ? hit.rawName : p.name)
    } else {
      emit('select', p.name)
    }
  })
  window.addEventListener('resize', onResize)
  if (props.selected) loadDistrictGeo(props.selected)
})

function onResize() {
  chart && chart.resize()
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart && chart.dispose()
  chart = null
})

watch(() => props.selected, (d, old) => {
  if (!d) {
    activeGeo.value = null
    render()
  } else {
    loadDistrictGeo(d)
  }
})
watch(() => [props.districts, props.streets, props.metric, props.selectedStreet], render, { deep: true })
</script>

<style scoped>
.map-root {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 480px;
}
.map-canvas {
  width: 100%;
  height: 100%;
  min-height: 480px;
}

.back-btn {
  position: absolute;
  top: 6px;
  left: 8px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: rgba(20, 28, 44, 0.9);
  border: 1px solid var(--border);
  color: var(--text-dim);
  font-family: inherit;
  font-size: 11.5px;
  padding: 5px 10px 5px 7px;
  border-radius: 8px;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: all 0.15s;
}
.back-btn:hover { color: var(--text); border-color: #3a4a6b; }

.geo-warn {
  position: absolute;
  left: 8px;
  top: 36px;
  z-index: 3;
  max-width: 58%;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.28);
  color: #b99a63;
  font-size: 10.5px;
  line-height: 1.5;
  padding: 5px 9px;
  border-radius: 7px;
  backdrop-filter: blur(6px);
}

.geo-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-dim);
  font-size: 12px;
  background: rgba(11, 16, 26, 0.55);
  z-index: 2;
}
.gl-spin {
  width: 14px;
  height: 14px;
  border: 2px solid #24314a;
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: glspin 0.8s linear infinite;
}
@keyframes glspin { to { transform: rotate(360deg); } }
</style>
