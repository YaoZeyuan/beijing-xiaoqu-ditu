<template>
  <section class="panel pv">
    <div class="pv-head">
      <div class="pv-title">
        小区明细
        <span class="sub">{{ rows.length.toLocaleString() }} 个小区</span>
      </div>
      <div class="pv-tools">
        <div class="tabs pv-tabs">
          <button
            v-for="s in SORTS"
            :key="s.key"
            :class="{ active: sortKey === s.key }"
            @click="setSort(s.key)"
          >{{ s.label }}<span v-if="sortKey === s.key" class="sm">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
        </div>
        <button class="pv-copy" :class="{ done: copied }" @click="copyAll">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8">
            <path v-if="!copied" d="M10 13a5 5 0 007 0l2-2a5 5 0 00-7-7l-1 1" stroke-linecap="round"/>
            <path v-if="!copied" d="M14 11a5 5 0 00-7 0l-2 2a5 5 0 007 7l1-1" stroke-linecap="round"/>
            <path v-else d="M4 12.5l5 5L20 6.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          {{ copied ? '已复制' : '复制表格' }}
        </button>
      </div>
    </div>

    <div class="pv-wrap">
      <table class="pv-tbl">
        <colgroup>
          <col style="width:62px" />
          <col style="width:132px" />
          <col />
          <col style="width:80px" />
          <col style="width:106px" />
          <col style="width:64px" />
          <col style="width:72px" />
          <col style="width:74px" />
          <col style="width:56px" />
          <col style="width:200px" />
          <col style="width:46px" />
        </colgroup>
        <thead>
          <tr>
            <th>城区</th>
            <th>街道</th>
            <th>小区名称</th>
            <th>治理状态</th>
            <th class="r">物业费</th>
            <th class="r">户数</th>
            <th class="r">挂牌价</th>
            <th>计费方式</th>
            <th class="r">建成</th>
            <th>物业服务企业</th>
            <th class="r">官方</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in pageRows" :key="p.id || p.name + p.street">
            <td class="c-dist">{{ shortName(p.district) }}</td>
            <td class="c-street" :title="p.street">{{ p.street }}</td>
            <td class="c-name" :title="`${p.name} — 点击查看详情与物业费构成`" @click="openDetail(p)">{{ p.name }}</td>
            <td>
              <span class="regime-tag" :style="regimeStyle(p.regime)">{{ p.regime }}</span>
            </td>
            <td class="r"><FeeCell :project="p" /></td>
            <td class="r num" :title="p.hhScope === '整小区合计·分区未拆' ? HH_TIP : ''">
              {{ hhCell(p) }}
            </td>
            <td class="r num">{{ p.price ? p.price.toLocaleString() : '—' }}</td>
            <td class="c-mode">{{ p.feeMode || '—' }}</td>
            <td class="r">{{ p.year || '—' }}</td>
            <td class="c-company" :title="p.company">{{ p.company || '—' }}</td>
            <td class="r"><GovLink :id="p.id" :name="p.name" /></td>
          </tr>
          <tr v-if="!pageRows.length">
            <td colspan="11" class="no-data">没有符合条件的小区</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pv-foot">
      <span class="pg-info">
        第 {{ page }} / {{ totalPages }} 页 · 共 {{ rows.length.toLocaleString() }} 条
        <span class="pg-hint">复制按钮导出的是全部筛选结果，不受分页限制</span>
      </span>
      <div class="pg-right">
        <label class="pg-size" title="每页条数，会写进链接便于保存">
          每页
          <select :value="size" @change="onSize">
            <option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }}</option>
          </select>
          条
        </label>
        <div class="pg-btns">
          <button :disabled="page <= 1" title="第一页" @click="goPage(1)">«</button>
          <button :disabled="page <= 1" title="上一页" @click="goPage(page - 1)">‹</button>
          <button :disabled="page >= totalPages" title="下一页" @click="goPage(page + 1)">›</button>
          <button :disabled="page >= totalPages" title="最后一页" @click="goPage(totalPages)">»</button>
        </div>
      </div>
    </div>
  </section>
</template>

// 「分区未拆」的户数是整个小区的，加 * 并悬停说明，避免被当成该分区自己的数
function hhCell(p) {
  if (!p.hh) return '—'
  return p.hh.toLocaleString() + (p.hhScope === '整小区合计·分区未拆' ? '*' : '')
}
const HH_TIP = '所在小区合计（本备案仅是其中一个分区/楼栋，查不到分区独立户数）'

<script setup>
import { ref, computed, watch } from 'vue'
import { copyText, mdTable } from '../utils/clipboard'
import { openDetail } from '../utils/detailStore'
import { feeView, fmtPrice } from '../utils/fee'
import { PAGE_SIZES } from '../utils/urlState'
import FeeCell from './FeeCell.vue'
import GovLink from './GovLink.vue'

const props = defineProps({
  projects: { type: Array, required: true },
  // 分页状态由 App 持有并同步到 URL
  page: { type: Number, default: 1 },
  size: { type: Number, default: 10 },
})
const emit = defineEmits(['update:page', 'update:size'])

const SORTS = [
  { key: 'street', label: '按街道' },
  { key: 'name', label: '按小区名' },
  { key: 'fee', label: '按物业费' },
  { key: 'hh', label: '按户数' },
  { key: 'price', label: '按挂牌价' },
  { key: 'year', label: '按建成' },
  { key: 'regime', label: '按治理状态' },
]

const ORDER = { 未成立: 0, 物管会: 1, 未知: 2, 业委会: 3 }

const sortKey = ref('street')
const sortDir = ref('asc')
const copied = ref(false)
let copyTimer = null

function setSort(k) {
  if (sortKey.value === k) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = k
    sortDir.value = k === 'fee' || k === 'year' || k === 'hh' || k === 'price' ? 'desc' : 'asc'
  }
  emit('update:page', 1)
}

const rows = computed(() => {
  const k = sortKey.value
  const d = sortDir.value === 'asc' ? 1 : -1
  const arr = [...props.projects]
  arr.sort((a, b) => {
    if (k === 'street') {
      return (a.district.localeCompare(b.district, 'zh-Hans-CN') ||
        a.street.localeCompare(b.street, 'zh-Hans-CN') ||
        (ORDER[a.regime] - ORDER[b.regime]) ||
        a.name.localeCompare(b.name, 'zh-Hans-CN')) * d
    }
    if (k === 'name') return a.name.localeCompare(b.name, 'zh-Hans-CN') * d
    if (k === 'regime') {
      return ((ORDER[a.regime] ?? 9) - (ORDER[b.regime] ?? 9)) * d ||
        a.name.localeCompare(b.name, 'zh-Hans-CN')
    }
    // fee / year：空值永远排最后
    const av = a[k]
    const bv = b[k]
    const an = av === null || av === undefined
    const bn = bv === null || bv === undefined
    if (an || bn) return an && bn ? 0 : an ? 1 : -1
    return (av - bv) * d
  })
  return arr
})

const totalPages = computed(() => Math.max(1, Math.ceil(rows.value.length / props.size)))
const pageRows = computed(() =>
  rows.value.slice((props.page - 1) * props.size, props.page * props.size))

function goPage(p) {
  const n = Math.min(Math.max(1, p), totalPages.value)
  if (n !== props.page) emit('update:page', n)
}

function onSize(e) {
  emit('update:size', Number(e.target.value))
  emit('update:page', 1)
}

watch(() => rows.value.length, () => {
  if (props.page > totalPages.value) emit('update:page', totalPages.value)
})

function shortName(d) {
  return (d || '').replace(/区$/, '').replace('北京经济技术开发', '经开')
}

const REGIME_STYLE = {
  业委会: { color: '#22c55e', background: 'rgba(34,197,94,.12)', borderColor: 'rgba(34,197,94,.3)' },
  物管会: { color: '#f59e0b', background: 'rgba(245,158,11,.12)', borderColor: 'rgba(245,158,11,.3)' },
  未成立: { color: '#ef4444', background: 'rgba(239,68,68,.1)', borderColor: 'rgba(239,68,68,.28)' },
  未知: { color: '#8b98b2', background: 'rgba(139,152,178,.1)', borderColor: 'rgba(139,152,178,.25)' },
}
function regimeStyle(r) {
  return REGIME_STYLE[r] || REGIME_STYLE['未知']
}

async function copyAll() {
  const headers = ['城区', '街道', '小区名称', '治理状态', '物业费(元/㎡·月)', '户数', '挂牌价(元/㎡)', '计费方式', '建成年代', '物业服务企业']
  const aligns = ['left', 'left', 'left', 'left', 'right', 'right', 'right', 'left', 'right', 'left']
  // 物业费输出区间而非单一主值，避免复制出去后丢失「分档」这个关键信息
  function feeText(p) {
    const v = feeView(p)
    if (v.kind === 'range') return `${fmtPrice(v.lo)}–${fmtPrice(v.hi)}（${v.tiers}档）`
    if (v.kind === 'single') return v.tiers >= 2 ? `${fmtPrice(v.value)}（${v.tiers}档同价）` : fmtPrice(v.value)
    if (v.kind === 'high') return `${fmtPrice(v.value)}（超限）`
    if (v.kind === 'zero') return '未填'
    if (v.kind === 'mixed') return '综合类'
    if (v.kind === 'other') return '非住宅'
    return '—'
  }
  const data = rows.value.map((p) => [
    p.district,
    p.street,
    p.name,
    p.regime,
    feeText(p),
    hhCell(p),
    p.price ? p.price.toLocaleString() : '—',
    p.feeMode || '—',
    p.year || '—',
    p.company || '—',
  ])
  const ok = await copyText(mdTable(headers, data, aligns))
  if (!ok) return
  copied.value = true
  clearTimeout(copyTimer)
  copyTimer = setTimeout(() => { copied.value = false }, 1800)
}
</script>

<style scoped>
.pv { display: flex; flex-direction: column; overflow: hidden; }

.pv-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 11px 14px 9px; flex-wrap: wrap;
  border-bottom: 1px solid var(--border-soft);
}
.pv-title { font-size: 13px; font-weight: 600; display: flex; align-items: baseline; gap: 8px; }
.pv-title .sub { font-size: 11px; font-weight: 400; color: var(--text-faint); }
.pv-tools { display: flex; align-items: center; gap: 9px; }
.pv-tabs { background: var(--panel-2); padding: 2px; }
.pv-tabs button { padding: 4px 9px; font-size: 11.5px; display: inline-flex; align-items: center; gap: 2px; }
.sm { font-size: 9px; opacity: 0.8; }

.pv-copy {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; font-family: inherit;
  padding: 5px 10px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.14s;
  white-space: nowrap;
}
.pv-copy:hover { border-color: var(--accent); color: #cfe3ff; }
.pv-copy.done { border-color: rgba(34, 197, 94, 0.45); color: var(--green); }

.pv-wrap { max-height: calc(100vh - 400px); min-height: 340px; overflow: auto; }
.pv-tbl { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
.pv-tbl thead th {
  position: sticky; top: 0; z-index: 1;
  background: var(--panel-2);
  color: var(--text-faint);
  font-weight: 500; font-size: 11px;
  text-align: left;
  padding: 8px 9px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.pv-tbl thead th.r, .pv-tbl td.r { text-align: right; font-variant-numeric: tabular-nums; }
.pv-tbl td {
  padding: 5px 9px;
  border-bottom: 1px solid #161f31;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pv-tbl tbody tr:hover td { background: rgba(76, 154, 255, 0.05); }
.c-dist { color: var(--text-faint); }
.c-street { color: var(--text-dim); }
.c-name { color: var(--text); cursor: pointer; }
.c-name:hover { color: #9cc6ff; text-decoration: underline; text-decoration-color: rgba(76,154,255,.45); text-underline-offset: 2px; }
.c-mode { color: var(--text-faint); font-size: 11.5px; }
.c-company { color: var(--text-dim); }
.na { color: #3d4a60; }
.suspect { color: #f87171; }

.regime-tag {
  display: inline-block;
  font-size: 10px;
  padding: 0 6px;
  border-radius: 4px;
  border: 1px solid transparent;
  line-height: 1.65;
}

.no-data { text-align: center; color: var(--text-faint); padding: 42px 0; }

.pv-foot {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px 10px;
  border-top: 1px solid var(--border-soft);
  font-size: 11.5px; color: var(--text-faint);
  flex-wrap: wrap; gap: 8px;
}
.pg-hint { color: #34405a; margin-left: 8px; }
.pg-info { font-variant-numeric: tabular-nums; }
.pg-btns { display: flex; gap: 4px; }
.pg-right { display: flex; align-items: center; gap: 12px; }
.pg-size {
  display: inline-flex; align-items: center; gap: 5px;
  color: var(--text-faint); font-size: 11.5px;
}
.pg-size select {
  appearance: none;
  padding: 3px 18px 3px 7px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background:
    linear-gradient(45deg, transparent 50%, var(--text-faint) 50%) right 8px center / 4px 4px no-repeat,
    linear-gradient(135deg, var(--text-faint) 50%, transparent 50%) right 4px center / 4px 4px no-repeat,
    var(--panel-2);
  color: var(--text-dim);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  outline: none;
}
.pg-size select:hover { border-color: var(--accent); color: var(--text); }
.pg-btns button {
  width: 26px; height: 24px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  transition: all 0.14s;
}
.pg-btns button:hover:not(:disabled) { border-color: var(--accent); color: var(--text); }
.pg-btns button:disabled { opacity: 0.32; cursor: default; }

@media (max-width: 1100px) {
  .pv-wrap { max-height: none; }
}
</style>
