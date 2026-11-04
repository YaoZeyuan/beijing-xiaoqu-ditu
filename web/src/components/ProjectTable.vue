<template>
  <section class="panel tbl-panel">
    <div class="tbl-head">
      <div class="panel-title" style="padding:0">
        小区名录
        <span class="sub">{{ projects.length.toLocaleString() }} 条</span>
      </div>
      <div class="tbl-tools">
        <div class="tabs sort-tabs">
          <button
            v-for="s in SORTS"
            :key="s.key"
            :class="{ active: sortKey === s.key }"
            @click="setSort(s.key)"
          >{{ s.label }}</button>
        </div>
        <input v-model.trim="localKw" class="text-input mini-input" placeholder="表内筛选" />
      </div>
    </div>

    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th class="c-name">小区名称</th>
            <th class="c-dist">城区</th>
            <th class="c-street">街道</th>
            <th class="c-regime">治理状态</th>
            <th class="c-fee">物业费</th>
            <th class="c-hh">户数</th>
            <th class="c-price">挂牌价</th>
            <th class="c-year">建成</th>
            <th class="c-company">物业服务企业</th>
            <th class="c-gov">官方</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in pageRows" :key="p.name + p.street">
            <td class="c-name" :title="`${p.name} — 点击查看详情与物业费构成`" @click="openDetail(p)">{{ p.name }}</td>
            <td class="c-dist">{{ p.district.replace(/区$/, '') }}</td>
            <td class="c-street" :title="p.street">{{ p.street || '—' }}</td>
            <td class="c-regime">
              <span class="regime-tag" :style="regimeStyle(p.regime)">{{ p.regime }}</span>
            </td>
            <td class="c-fee"><FeeCell :project="p" /></td>
            <td class="c-hh" :title="p.hhScope === '整小区合计·分区未拆' ? HH_TIP : ''">
              {{ hhCell(p) }}
            </td>
            <td class="c-price">{{ p.price ? p.price.toLocaleString() : '—' }}</td>
            <td class="c-year">{{ p.year || '—' }}</td>
            <td class="c-company" :title="p.company">{{ p.company || '—' }}</td>
            <td class="c-gov"><GovLink :id="p.id" :name="p.name" /></td>
          </tr>
          <tr v-if="!pageRows.length">
            <td colspan="10" class="no-data">没有符合条件的小区</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pager">
      <span class="pg-info">
        第 {{ page }} / {{ totalPages }} 页 · 共 {{ rows.length.toLocaleString() }} 条
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
import { openDetail } from '../utils/detailStore'
import { PAGE_SIZES } from '../utils/urlState'
import FeeCell from './FeeCell.vue'
import GovLink from './GovLink.vue'

const props = defineProps({
  projects: { type: Array, required: true },
  selectedStreet: { type: String, default: '' },
  // 分页状态由 App 持有并同步到 URL，组件只负责渲染和上报
  page: { type: Number, default: 1 },
  size: { type: Number, default: 10 },
})
const emit = defineEmits(['update:page', 'update:size'])

const SORTS = [
  { key: 'default', label: '默认' },
  { key: 'feeDesc', label: '物业费↓' },
  { key: 'feeAsc', label: '物业费↑' },
  { key: 'hhDesc', label: '户数↓' },
  { key: 'priceDesc', label: '挂牌价↓' },
  { key: 'yearDesc', label: '建成↓' },
]

const sortKey = ref('default')
const localKw = ref('')

function setSort(k) {
  sortKey.value = k
  emit('update:page', 1)
}

// 表内筛选变化后页码可能越界，回到第一页
watch(localKw, () => emit('update:page', 1))

const rows = computed(() => {
  let arr = props.projects
  const kw = localKw.value.toLowerCase()
  if (kw) {
    arr = arr.filter((p) =>
      (p.name + p.street + p.company).toLowerCase().includes(kw))
  }
  const k = sortKey.value
  if (k === 'feeDesc') {
    arr = [...arr].sort((a, b) => (b.fee ?? -1) - (a.fee ?? -1))
  } else if (k === 'feeAsc') {
    arr = [...arr].sort((a, b) => (a.fee ?? 999) - (b.fee ?? 999))
  } else if (k === 'hhDesc') {
    arr = [...arr].sort((a, b) => (b.hh ?? 0) - (a.hh ?? 0))
  } else if (k === 'priceDesc') {
    arr = [...arr].sort((a, b) => (b.price ?? 0) - (a.price ?? 0))
  } else if (k === 'yearDesc') {
    arr = [...arr].sort((a, b) => (b.year ?? 0) - (a.year ?? 0))
  }
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

// 筛选后行数变少时，把越界的页码拉回最后一页
watch(() => rows.value.length, () => {
  if (props.page > totalPages.value) emit('update:page', totalPages.value)
})

const REGIME_STYLE = {
  业委会: { color: '#22c55e', background: 'rgba(34,197,94,.12)', borderColor: 'rgba(34,197,94,.3)' },
  物管会: { color: '#f59e0b', background: 'rgba(245,158,11,.12)', borderColor: 'rgba(245,158,11,.3)' },
  未成立: { color: '#ef4444', background: 'rgba(239,68,68,.1)', borderColor: 'rgba(239,68,68,.28)' },
  未知: { color: '#8b98b2', background: 'rgba(139,152,178,.1)', borderColor: 'rgba(139,152,178,.25)' },
}
function regimeStyle(r) {
  return REGIME_STYLE[r] || REGIME_STYLE['未知']
}
</script>

<style scoped>
.tbl-panel { display: flex; flex-direction: column; overflow: hidden; }
.tbl-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; padding: 13px 16px 10px; flex-wrap: wrap;
}
.tbl-tools { display: flex; align-items: center; gap: 10px; }
.sort-tabs { padding: 2px; }
.sort-tabs button { padding: 4px 10px; font-size: 11.5px; }
.mini-input { width: 150px; padding: 5px 9px; font-size: 11.5px; }

.tbl-wrap { max-height: 340px; overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
thead th {
  position: sticky; top: 0; z-index: 1;
  background: var(--panel-2);
  color: var(--text-faint);
  font-weight: 500;
  font-size: 11px;
  text-align: left;
  padding: 8px 10px;
  letter-spacing: 0.3px;
  border-bottom: 1px solid var(--border-soft);
  white-space: nowrap;
}
tbody td {
  padding: 7px 10px;
  border-bottom: 1px solid #161f31;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
tbody tr:hover td { background: rgba(76, 154, 255, 0.045); }
.c-name { width: 22%; color: var(--text); cursor: pointer; }
.c-name:hover { color: #9cc6ff; text-decoration: underline; text-decoration-color: rgba(76,154,255,.45); text-underline-offset: 2px; }
.c-dist { width: 62px; }
.c-street { width: 15%; }
.c-regime { width: 84px; }
.c-fee { width: 106px; text-align: right; font-variant-numeric: tabular-nums; }
.c-hh { width: 66px; text-align: right; font-variant-numeric: tabular-nums; }
.c-price { width: 74px; text-align: right; font-variant-numeric: tabular-nums; }
.c-gov { width: 46px; text-align: right; }
.c-year { width: 58px; text-align: right; font-variant-numeric: tabular-nums; }
.c-company { width: 24%; }
.na { color: #3d4a60; }
.suspect { color: #f87171; }
.suspect em {
  font-style: normal;
  font-size: 10px;
  margin-left: 1px;
  opacity: 0.85;
  border: 1px solid currentColor;
  border-radius: 50%;
  display: inline-block;
  width: 10px;
  height: 10px;
  line-height: 9px;
  text-align: center;
}

.regime-tag {
  display: inline-block;
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 5px;
  border: 1px solid transparent;
  line-height: 1.55;
}

.no-data { text-align: center; color: var(--text-faint); padding: 30px 0; }

.pager {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 16px 12px;
  border-top: 1px solid var(--border-soft);
  font-size: 11.5px; color: var(--text-faint);
  flex-wrap: wrap; gap: 8px;
}
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
</style>
