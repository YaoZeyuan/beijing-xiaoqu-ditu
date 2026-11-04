<template>
  <div class="dd">
    <div class="dd-head">
      <div>
        <div class="dd-name">{{ district }}</div>
        <div class="dd-sub">{{ stats.streetCount }} 个街道 · {{ stats.count.toLocaleString() }} 个小区</div>
      </div>
      <button class="close-btn" @click="$emit('close')" title="返回全市">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12" stroke-linecap="round"/>
        </svg>
      </button>
    </div>

    <div class="dd-mini">
      <div class="mini">
        <span class="mv" style="color:#22c55e">{{ stats.regime['业委会'] || 0 }}</span>
        <span class="ml">业委会</span>
      </div>
      <div class="mini">
        <span class="mv" style="color:#f59e0b">{{ stats.regime['物管会'] || 0 }}</span>
        <span class="ml">物管会</span>
      </div>
      <div class="mini">
        <span class="mv" style="color:#ef4444">{{ stats.regime['未成立'] || 0 }}</span>
        <span class="ml">均未成立</span>
      </div>
      <div class="mini">
        <span class="mv">{{ stats.feeAvg === null ? '—' : stats.feeAvg.toFixed(2) }}</span>
        <span class="ml">均价 元/㎡</span>
      </div>
    </div>

    <div class="dd-sec-title">
      街道明细
      <span class="sub">{{ sortKey === 'count' ? '按小区数' : sortKey === 'rate' ? '按覆盖率' : '按均价' }}</span>
    </div>

    <div class="street-table">
      <div class="st-row st-head">
        <span class="st-name">街道</span>
        <span class="st-num">小区</span>
        <span class="st-num">自治率</span>
        <span class="st-num">均价</span>
      </div>
      <div
        v-for="s in streets"
        :key="s.street"
        class="st-row"
        :class="{ dim: s.count === 0, on: s.street === selectedStreet }"
        @click="$emit('selectStreet', s.street)"
      >
        <span class="st-name" :title="s.street">
          <span v-if="s.street === selectedStreet" class="pin">●</span>{{ s.street || '—' }}
        </span>
        <span class="st-num">{{ s.count }}</span>
        <span class="st-num" :style="{ color: rateColor(s.rate) }">
          {{ s.rate === null ? '—' : (s.rate * 100).toFixed(0) + '%' }}
        </span>
        <span class="st-num">{{ s.feeAvg === null ? '—' : s.feeAvg.toFixed(2) }}</span>
      </div>
      <div v-if="!streets.length" class="empty">该区暂无符合条件的小区</div>
    </div>

    <div class="dd-foot">
      <span>共 {{ streets.length }} 个街道</span>
      <span>物业费基于 {{ stats.feeCount }} 个小区的公开数据</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  district: { type: String, required: true },
  projects: { type: Array, required: true },
  metric: { type: String, default: 'count' },
  selectedStreet: { type: String, default: '' },
})
defineEmits(['close', 'selectStreet'])

const sortKey = computed(() => props.metric === 'rate' ? 'rate' : props.metric === 'feeAvg' ? 'fee' : 'count')

const stats = computed(() => {
  const list = props.projects
  const fees = list.filter((p) => p.feeOk).map((p) => p.fee)
  const regime = { 业委会: 0, 物管会: 0, 未成立: 0, 未知: 0 }
  for (const p of list) regime[p.regime] = (regime[p.regime] || 0) + 1
  return {
    count: list.length,
    regime,
    feeCount: fees.length,
    feeAvg: fees.length ? fees.reduce((a, b) => a + b, 0) / fees.length : null,
    streetCount: new Set(list.map((p) => p.street)).size,
  }
})

const streets = computed(() => {
  const m = new Map()
  for (const p of props.projects) {
    const k = p.street || '（未标注）'
    let s = m.get(k)
    if (!s) {
      s = { street: k, count: 0, fees: [], selfGov: 0 }
      m.set(k, s)
    }
    s.count++
    if (p.feeOk) s.fees.push(p.fee)
    if (p.regime === '业委会' || p.regime === '物管会') s.selfGov++
  }
  const arr = [...m.values()].map((s) => ({
    street: s.street,
    count: s.count,
    rate: s.count ? s.selfGov / s.count : null,
    feeAvg: s.fees.length ? s.fees.reduce((a, b) => a + b, 0) / s.fees.length : null,
  }))
  const key = sortKey.value
  arr.sort((a, b) => {
    if (key === 'count') return b.count - a.count
    if (key === 'rate') return (b.rate ?? -1) - (a.rate ?? -1)
    return (b.feeAvg ?? -1) - (a.feeAvg ?? -1)
  })
  return arr
})

function rateColor(r) {
  if (r === null) return '#5b6880'
  if (r >= 0.6) return '#22c55e'
  if (r >= 0.3) return '#f59e0b'
  return '#ef4444'
}
</script>

<style scoped>
.dd { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

.dd-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 15px 16px 10px;
}
.dd-name { font-size: 17px; font-weight: 650; letter-spacing: 0.2px; }
.dd-sub { font-size: 11px; color: var(--text-faint); margin-top: 1px; }
.close-btn {
  background: var(--panel-2); border: 1px solid var(--border);
  color: var(--text-dim); border-radius: 7px; cursor: pointer;
  width: 26px; height: 26px; display: grid; place-items: center;
  flex-shrink: 0; transition: all 0.15s;
}
.close-btn:hover { color: var(--text); border-color: #3a4a6b; }

.dd-mini {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 6px; padding: 0 14px 12px;
  border-bottom: 1px solid var(--border-soft);
}
.mini {
  background: var(--panel-2); border-radius: 8px;
  padding: 7px 4px; text-align: center;
  display: flex; flex-direction: column; gap: 1px;
}
.mv { font-size: 15px; font-weight: 650; font-variant-numeric: tabular-nums; }
.ml { font-size: 9.5px; color: var(--text-faint); letter-spacing: 0.2px; }

.dd-sec-title {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px; font-weight: 600; padding: 11px 16px 7px;
}
.dd-sec-title .sub { font-size: 10.5px; color: var(--text-faint); font-weight: 400; }

.street-table { flex: 1; overflow-y: auto; padding: 0 8px; }
.st-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 42px 48px 48px;
  gap: 4px;
  align-items: center;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 11.5px;
  cursor: pointer;
  transition: background 0.12s, box-shadow 0.12s;
}
.st-row:hover { background: var(--panel-2); }
.st-row.dim { opacity: 0.45; }
.st-row.on {
  background: #1d2c48;
  box-shadow: inset 0 0 0 1px #2b3a5a;
}
.st-row.on .st-name { color: #cfe3ff; }
.pin { color: #7c5cff; font-size: 7px; margin-right: 3px; vertical-align: 1px; }
.st-head {
  color: var(--text-faint); font-size: 10.5px;
  position: sticky; top: 0; background: var(--panel); z-index: 1;
  padding-bottom: 6px;
  cursor: default;
}
.st-head:hover { background: var(--panel); }
.st-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-dim); }
.st-num { text-align: right; font-variant-numeric: tabular-nums; color: var(--text); }

.dd-foot {
  display: flex; justify-content: space-between;
  font-size: 10.5px; color: #3d4a60;
  padding: 8px 16px 12px;
  border-top: 1px solid var(--border-soft);
  margin-top: 4px;
  flex-wrap: wrap; gap: 4px;
}
</style>
