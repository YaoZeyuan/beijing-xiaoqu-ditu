<template>
  <div class="sv">
    <!-- ── 分享链接定位提示 ── -->
    <div v-if="pinStreet" class="street-pin">
      <span class="sp-dot"></span>
      <span class="sp-txt">已定位到 <b>{{ streetLabel }}</b>，下表只列该街道</span>
      <button class="sp-btn" @click="clearStreet">显示全部街道</button>
    </div>

    <!-- ── 汇总条 ── -->
    <div class="sv-sum">
      <div class="sum-item">
        <span class="sv-v">{{ summary.count.toLocaleString() }}</span>
        <span class="sv-l">小区</span>
      </div>
      <div class="sum-item">
        <span class="sv-v">{{ summary.streetCount.toLocaleString() }}</span>
        <span class="sv-l">街道 / 地区</span>
      </div>
      <div class="sum-item">
        <span class="sv-v" style="color:#22c55e">{{ summary.ywh.toLocaleString() }}</span>
        <span class="sv-l">业委会</span>
      </div>
      <div class="sum-item">
        <span class="sv-v" style="color:#f59e0b">{{ summary.wgh.toLocaleString() }}</span>
        <span class="sv-l">物管会</span>
      </div>
      <div class="sum-item">
        <span class="sv-v" style="color:#ef4444">{{ summary.none.toLocaleString() }}</span>
        <span class="sv-l">均未成立</span>
      </div>
      <div class="sum-item">
        <span class="sv-v">{{ summary.rate === null ? '—' : (summary.rate * 100).toFixed(1) + '%' }}</span>
        <span class="sv-l">自治率</span>
      </div>
      <div class="sum-item">
        <span class="sv-v">{{ summary.feeAvg === null ? '—' : summary.feeAvg.toFixed(2) }}</span>
        <span class="sv-l">均价 元/㎡·月</span>
      </div>
    </div>

    <!-- ── 工具栏 ── -->
    <div class="sv-bar">
      <div class="sv-left">
        <div class="sv-row1">
          <div class="tabs level-tabs">
            <button
              v-for="lv in LEVELS"
              :key="lv.key"
              :class="{ active: level === lv.key }"
              @click="level = lv.key"
            >{{ lv.label }}</button>
          </div>
          <div class="sv-search">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" stroke-linecap="round" />
            </svg>
            <input v-model.trim="kw" type="text" placeholder="搜索街道、城区、小区名或物业公司" />
            <button v-if="kw" class="clear-x" @click="kw = ''" title="清空">×</button>
          </div>
        </div>
        <div class="sv-chips">
          <button class="sv-chip" :class="{ on: !activeDistricts.length }" @click="activeDistricts = []">全部城区</button>
          <button
            v-for="d in districts"
            :key="d"
            class="sv-chip"
            :class="{ on: activeDistricts.includes(d) }"
            @click="toggleDistrict(d)"
          >{{ shortName(d) }}</button>
        </div>
      </div>

      <div class="sv-right">
        <div class="sv-chips">
          <button
            v-for="b in BANDS"
            :key="b.key"
            class="sv-chip"
            :class="{ on: band === b.key }"
            @click="band = b.key"
          >{{ b.label }}</button>
        </div>
        <button
          v-if="level === 'street'"
          class="sv-btn copy"
          :class="{ done: copiedStreets }"
          :disabled="!rows.length"
          @click="copyStreets"
        >
          <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.9">
            <path v-if="!copiedStreets" d="M10 13a5 5 0 007 0l2-2a5 5 0 00-7-7l-1 1" stroke-linecap="round"/>
            <path v-if="!copiedStreets" d="M14 11a5 5 0 00-7 0l-2 2a5 5 0 007 7l1-1" stroke-linecap="round"/>
            <path v-else d="M4 12.5l5 5L20 6.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          {{ copiedStreets ? '已复制' : '复制汇总表' }}
        </button>
        <button v-if="level === 'street'" class="sv-btn" :disabled="!rows.length" @click="exportStreets">导出街道 CSV</button>
        <button class="sv-btn" :disabled="!visibleProjects.length" @click="exportProjects">导出小区 CSV</button>
      </div>
    </div>

    <!-- ── 街道汇总表 ── -->
    <section v-if="level === 'street'" class="panel sv-panel">
      <div class="sv-tbl-wrap">
        <table class="sv-tbl">
          <thead>
            <tr>
              <th
                v-for="c in COLS"
                :key="c.key"
                :style="c.w ? { width: c.w + 'px' } : null"
                :class="['th-' + c.align, { sorted: sort.key === c.key }]"
                @click="setSort(c.key)"
              >
                {{ c.label }}
                <span class="sort-mark">{{ sort.key === c.key ? (sort.dir === 'asc' ? '↑' : '↓') : '' }}</span>
              </th>
              <th class="th-op"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="r in rows" :key="r.key">
              <tr class="sv-row" :class="{ open: expanded === r.key }" @click="toggleRow(r.key)">
                <td class="c-dist">{{ shortName(r.district) }}</td>
                <td class="c-street">
                  <span class="caret">{{ expanded === r.key ? '▾' : '▸' }}</span>
                  <span class="street-name">{{ r.street }}</span>
                  <span v-if="r.street === '（未标注）'" class="flag">地址未匹配</span>
                </td>
                <td class="c-num b">{{ r.count.toLocaleString() }}</td>
                <td class="c-num">{{ r.hh ? r.hh.toLocaleString() : '—' }}</td>
                <td class="c-num" :style="r.ywh ? { color: '#22c55e' } : null">{{ r.ywh }}</td>
                <td class="c-num" :style="r.wgh ? { color: '#f59e0b' } : null">{{ r.wgh }}</td>
                <td class="c-num" :style="r.none ? { color: '#ef4444' } : null">{{ r.none }}</td>
                <td class="c-num muted">{{ r.unknown }}</td>
                <td class="c-num">
                  <span class="rate" :style="rateStyle(r.rate)">{{ r.rate === null ? '—' : (r.rate * 100).toFixed(1) + '%' }}</span>
                </td>
                <td class="c-num">{{ r.feeAvg === null ? '—' : r.feeAvg.toFixed(2) }}</td>
                <td class="c-num muted">{{ r.feeCount }}</td>
                <td class="c-num">{{ r.priceAvg === null ? '—' : r.priceAvg.toLocaleString() }}</td>
                <td class="c-op">
                  <button class="map-btn" title="在地图中查看该街道" @click.stop="openInMap(r)">地图</button>
                </td>
              </tr>
              <tr v-if="expanded === r.key" class="detail-row">
                <td :colspan="COLS.length + 1">
                  <div class="detail">
                    <div class="detail-head">
                      <span>{{ r.district }} · {{ r.street }}</span>
                      <span class="dh-sub">
                        共 {{ r.count }} 个小区：业委会 {{ r.ywh }} · 物管会 {{ r.wgh }} · 均未成立 {{ r.none }}
                        <template v-if="r.unknown"> · 未知 {{ r.unknown }}</template>
                      </span>
                      <button
                        class="dh-copy"
                        :class="{ done: copiedRow === r.key }"
                        @click.stop="copyStreet(r)"
                      >{{ copiedRow === r.key ? '已复制' : '复制本街道' }}</button>
                    </div>
                    <div class="detail-scroll">
                      <table class="sub-tbl">
                        <thead>
                          <tr>
                            <th
                              v-for="c in PCOLS"
                              :key="c.key"
                              :style="{ width: c.w }"
                              :class="['th-' + c.align, { sortable: c.sortable !== false, sorted: psort.key === c.key }]"
                              @click="c.sortable !== false && setPSort(c.key)"
                            >
                              {{ c.label }}
                              <span class="sort-mark">{{ psort.key === c.key ? (psort.dir === 'asc' ? '↑' : '↓') : '' }}</span>
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="p in sortedProjects(r.projects)" :key="p.id || p.name">
                            <td class="s-name" :title="`${p.name} — 点击查看详情与物业费构成`" @click="openDetail(p)">{{ p.name }}</td>
                            <td>
                              <span class="regime-tag" :style="regimeStyle(p.regime)">{{ p.regime }}</span>
                            </td>
                            <td class="s-fee"><FeeCell :project="p" /></td>
                            <td class="s-hh" :title="p.hhScope === '整小区合计·分区未拆' ? HH_TIP : ''">
                              {{ hhCell(p) }}
                            </td>
                            <td class="s-price">{{ p.price ? p.price.toLocaleString() : '—' }}</td>
                            <td class="s-year">{{ p.year || '—' }}</td>
                            <td class="s-mode">{{ p.feeMode || '—' }}</td>
                            <td class="s-company" :title="p.company">{{ p.company || '—' }}</td>
                            <td class="s-gov"><GovLink :id="p.id" :name="p.name" /></td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!rows.length">
              <td :colspan="COLS.length + 1" class="no-data">没有符合条件的街道，试试放宽搜索或筛选条件</td>
            </tr>
          </tbody>
          <tfoot v-if="rows.length">
            <tr>
              <td colspan="2" class="tf-label">合计 / 均值（当前 {{ rows.length }} 个街道）</td>
              <td class="c-num b">{{ summary.count.toLocaleString() }}</td>
              <td class="c-num">{{ summary.hh === null ? '—' : summary.hh.toLocaleString() }}</td>
              <td class="c-num">{{ summary.ywh }}</td>
              <td class="c-num">{{ summary.wgh }}</td>
              <td class="c-num">{{ summary.none }}</td>
              <td class="c-num muted">{{ summary.unknown }}</td>
              <td class="c-num">{{ summary.rate === null ? '—' : (summary.rate * 100).toFixed(1) + '%' }}</td>
              <td class="c-num">{{ summary.feeAvg === null ? '—' : summary.feeAvg.toFixed(2) }}</td>
              <td class="c-num muted">{{ summary.feeCount }}</td>
              <td class="c-num">{{ summary.priceAvg === null ? '—' : summary.priceAvg.toLocaleString() }}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <!-- ── 小区明细表（区 / 街道下的完整清单） ── -->
    <ProjectListView
      v-else
      :projects="visibleProjects"
      :page="page"
      :size="size"
      @update:page="emit('update:page', $event)"
      @update:size="emit('update:size', $event)"
    />

    <p class="sv-note">
      <template v-if="level === 'street'">
        提示：点击任意一行可展开该街道的小区名单（默认按「均未成立 → 物管会 → 未知 → 业委会」排列）；展开后点表头还能按名称、治理状态、物业费、建成、计费方式、物业公司排序，排序也会写进地址栏。点击「地图」跳回地图视图并定位到该街道。
        「复制汇总表」得到的是当前筛选下的全部街道，可直接粘到微信或文档里。
      </template>
      <template v-else>
        提示：明细表列出当前筛选下的全部小区，点表头切换排序，「复制表格」复制的是全部结果（不受分页限制），需要 Excel 用「导出小区 CSV」。
      </template>
      当前筛选、排序、层级都会同步到地址栏，复制链接即可分享同一视图。街道名称来自住建委项目地址与小区名匹配，匹配不到的记为「（未标注）」，全市仅 16 个。
    </p>
  </div>
</template>

// 「分区未拆」的户数是整个小区的，加 * 并悬停说明，避免被当成该分区自己的数
function hhCell(p) {
  if (!p.hh) return '—'
  return p.hh.toLocaleString() + (p.hhScope === '整小区合计·分区未拆' ? '*' : '')
}
const HH_TIP = '所在小区合计（本备案仅是其中一个分区/楼栋，查不到分区独立户数）'

<script setup>
import { ref, computed, watch } from 'vue'
import ProjectListView from './ProjectListView.vue'
import { openDetail } from '../utils/detailStore'
import FeeCell from './FeeCell.vue'
import GovLink from './GovLink.vue'
import { copyText, mdTable } from '../utils/clipboard'

const props = defineProps({
  projects: { type: Array, required: true },
  districts: { type: Array, default: () => [] },
  // 与 App / URL 共享的筛选状态对象，组件内直接改其属性以保持三处同步
  filters: { type: Object, required: true },
  // 与 App / URL 共享的列表页状态：band / sortKey / sortDir / street
  listState: { type: Object, required: true },
  // 小区明细的分页（街道汇总不分页，一次列完 298 行）
  page: { type: Number, default: 1 },
  size: { type: Number, default: 10 },
})
const emit = defineEmits(['open-map', 'update:page', 'update:size'])

const COLS = [
  { key: 'district', label: '城区', align: 'left', w: 66 },
  { key: 'street', label: '街道 / 地区', align: 'left', w: 0 },
  { key: 'count', label: '小区数', align: 'right', w: 70 },
  { key: 'hh', label: '户数合计', align: 'right', w: 84 },
  { key: 'ywh', label: '业委会', align: 'right', w: 62 },
  { key: 'wgh', label: '物管会', align: 'right', w: 62 },
  { key: 'none', label: '未成立', align: 'right', w: 62 },
  { key: 'unknown', label: '未知', align: 'right', w: 54 },
  { key: 'rate', label: '自治率', align: 'right', w: 76 },
  { key: 'feeAvg', label: '物业费均价', align: 'right', w: 92 },
  { key: 'feeCount', label: '有费样本', align: 'right', w: 76 },
  { key: 'priceAvg', label: '挂牌均价', align: 'right', w: 84 },
]

// 展开街道后那张小区表的列。key 与数据字段同名（fee = 主口径单价，year = 建成年），
// 最后一列是外链按钮，不参与排序。
const PCOLS = [
  { key: 'name', label: '小区名称', align: 'left', w: '24%' },
  { key: 'regime', label: '治理状态', align: 'left', w: '86px' },
  { key: 'fee', label: '物业费', align: 'right', w: '100px' },
  { key: 'hh', label: '户数', align: 'right', w: '64px' },
  { key: 'price', label: '挂牌价', align: 'right', w: '72px' },
  { key: 'year', label: '建成', align: 'right', w: '64px' },
  { key: 'feeMode', label: '计费方式', align: 'left', w: '84px' },
  { key: 'company', label: '物业服务企业', align: 'left', w: '22%' },
  { key: 'gov', label: '官方', align: 'right', w: '46px', sortable: false },
]

const BANDS = [
  { key: 'all', label: '全部自治率' },
  { key: 'low', label: '< 30%' },
  { key: 'mid', label: '30–60%' },
  { key: 'high', label: '≥ 60%' },
]

// 列表层级：按街道汇总 / 按小区铺开
const LEVELS = [
  { key: 'street', label: '街道汇总' },
  { key: 'project', label: '小区明细' },
]

const ORDER = { 未成立: 0, 物管会: 1, 未知: 2, 业委会: 3 }

// 搜索 / 城区 / 自治率区间 / 排序都写进共享状态，便于同步到 URL
const kw = computed({
  get: () => props.filters.keyword,
  set: (v) => { props.filters.keyword = v },
})
const activeDistricts = computed({
  get: () => props.filters.districts,
  set: (v) => { props.filters.districts = v },
})
const band = computed({
  get: () => props.listState.band,
  set: (v) => { props.listState.band = v },
})
const sort = computed(() => ({ key: props.listState.sortKey, dir: props.listState.sortDir }))
// 展开表自己的排序，独立于街道汇总表
const psort = computed(() => ({ key: props.listState.psortKey, dir: props.listState.psortDir }))
const level = computed({
  get: () => props.listState.level || 'street',
  // 切换层级等于换了一张表，页码回到第一页
  set: (v) => {
    props.listState.level = v
    emit('update:page', 1)
  },
})

const expanded = ref('')

function shortName(d) {
  return (d || '').replace(/区$/, '').replace('北京经济技术开发', '经开')
}

function toggleDistrict(d) {
  const i = activeDistricts.value.indexOf(d)
  if (i >= 0) activeDistricts.value.splice(i, 1)
  else activeDistricts.value.push(d)
}

// ── 聚合：一个街道一行 ──
const rowsAll = computed(() => {
  const m = new Map()
  for (const p of props.projects) {
    const street = p.street || '（未标注）'
    const key = p.district + '|' + street
    let r = m.get(key)
    if (!r) {
      r = {
        key, district: p.district, street, count: 0,
        ywh: 0, wgh: 0, none: 0, unknown: 0,
        fees: [], hh: 0, hhSeen: new Set(), prices: [], blob: [], projects: [],
      }
      m.set(key, r)
    }
    r.count++
    r.projects.push(p)
    if (p.regime === '业委会') r.ywh++
    else if (p.regime === '物管会') r.wgh++
    else if (p.regime === '未成立') r.none++
    else r.unknown++
    if (p.feeOk && p.fee !== null && p.fee !== undefined) r.fees.push(p.fee)
    // 共享口径（多条备案共用一个小区总数）只算一次
    if (p.hh && !(p.hhKey && r.hhSeen.has(p.hhKey))) {
      if (p.hhKey) r.hhSeen.add(p.hhKey)
      r.hh += p.hh
    }
    if (p.price) r.prices.push(p.price)
    r.blob.push(p.name)
    if (p.company) r.blob.push(p.company)
  }

  const out = []
  for (const r of m.values()) {
    const feeAvg = r.fees.length
      ? r.fees.reduce((a, b) => a + b, 0) / r.fees.length
      : null
    const selfGov = r.ywh + r.wgh
    out.push({
      key: r.key,
      district: r.district,
      street: r.street,
      count: r.count,
      ywh: r.ywh,
      wgh: r.wgh,
      none: r.none,
      unknown: r.unknown,
      rate: r.count ? selfGov / r.count : null,
      feeAvg: feeAvg === null ? null : Math.round(feeAvg * 100) / 100,
      feeCount: r.fees.length,
      hh: r.hh,
      priceAvg: r.prices.length
        ? Math.round(r.prices.reduce((a, b) => a + b, 0) / r.prices.length)
        : null,
      // 每行预拼一次搜索文本，输入时只做 includes
      hay: (r.district + ' ' + r.street + ' ' + r.blob.join(' ')).toLowerCase(),
      projects: r.projects,
    })
  }
  return out
})

// ── 筛选 + 排序 ──
const pinStreet = computed(() => props.listState.street || '')
const streetLabel = computed(() => {
  const s = pinStreet.value
  if (!s) return ''
  const ds = props.filters.districts
  return ds.length === 1 ? `${ds[0]} · ${s}` : s
})

const rows = computed(() => {
  const q = kw.value.toLowerCase()
  const ds = activeDistricts.value
  const b = band.value

  let arr = rowsAll.value.filter((r) => {
    if (pinStreet.value && r.street !== pinStreet.value) return false
    if (ds.length && !ds.includes(r.district)) return false
    if (b !== 'all') {
      if (r.rate === null) return false
      if (b === 'low' && r.rate >= 0.3) return false
      if (b === 'mid' && (r.rate < 0.3 || r.rate >= 0.6)) return false
      if (b === 'high' && r.rate < 0.6) return false
    }
    if (q && !r.hay.includes(q)) return false
    return true
  })

  const k = sort.value.key
  const d = sort.value.dir === 'asc' ? 1 : -1
  arr = [...arr].sort((a, b2) => {
    if (k === 'street' || k === 'district') {
      return a[k].localeCompare(b2[k], 'zh-Hans-CN') * d
    }
    const av = a[k]
    const bv = b2[k]
    const an = av === null || av === undefined
    const bn = bv === null || bv === undefined
    if (an || bn) return an && bn ? 0 : an ? 1 : -1
    return (av - bv) * d
  })
  return arr
})

const visibleProjects = computed(() => rows.value.flatMap((r) => r.projects))

// ── 复制为 Markdown 表格：粘到微信 / 飞书 / 文档里仍然可读 ──
const copiedStreets = ref(false)
const copiedRow = ref('')
let copyTimerA = null
let copyTimerB = null

async function copyStreets() {
  const headers = ['城区', '街道 / 地区', '小区数', '户数合计', '业委会', '物管会', '均未成立', '未知', '自治率', '物业费均价', '有费样本', '挂牌均价']
  const aligns = ['left', 'left', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right']
  const s = summary.value
  const pct = (v) => (v === null ? '—' : (v * 100).toFixed(1) + '%')
  const fee = (v) => (v === null ? '—' : v.toFixed(2))
  const num = (v) => (v === null ? '—' : v.toLocaleString())
  const data = rows.value.map((r) => [
    r.district, r.street, r.count, num(r.hh), r.ywh, r.wgh, r.none, r.unknown,
    pct(r.rate), fee(r.feeAvg), r.feeCount, num(r.priceAvg),
  ])
  data.push([
    '合计 / 均值', `${rows.value.length} 个街道`, s.count, num(s.hh), s.ywh, s.wgh, s.none, s.unknown,
    pct(s.rate), fee(s.feeAvg), s.feeCount, num(s.priceAvg),
  ])
  const ok = await copyText(mdTable(headers, data, aligns))
  if (!ok) return
  copiedStreets.value = true
  clearTimeout(copyTimerA)
  copyTimerA = setTimeout(() => { copiedStreets.value = false }, 1800)
}

async function copyStreet(r) {
  const headers = ['小区名称', '治理状态', '物业费(元/㎡·月)', '户数', '挂牌价(元/㎡)', '计费方式', '建成年代', '物业服务企业']
  const aligns = ['left', 'left', 'right', 'right', 'right', 'left', 'right', 'left']
  const data = sortedProjects(r.projects).map((p) => [
    p.name,
    p.regime,
    p.fee === null || p.fee === undefined ? '—' : p.fee.toFixed(2),
    hhCell(p),
    p.price ? p.price.toLocaleString() : '—',
    p.feeMode || '—',
    p.year || '—',
    p.company || '—',
  ])
  const text = `**${r.district} · ${r.street}**（${r.count} 个小区）\n\n` + mdTable(headers, data, aligns)
  const ok = await copyText(text)
  if (!ok) return
  copiedRow.value = r.key
  clearTimeout(copyTimerB)
  copyTimerB = setTimeout(() => { copiedRow.value = '' }, 1800)
}

const summary = computed(() => {
  const list = visibleProjects.value
  const fees = list.filter((p) => p.feeOk && p.fee !== null).map((p) => p.fee)
  const prices = list.filter((p) => p.price).map((p) => p.price)
  const seen = new Set()
  let hhSum = 0
  for (const p of list) {
    if (!p.hh) continue
    if (p.hhKey) {
      if (seen.has(p.hhKey)) continue
      seen.add(p.hhKey)
    }
    hhSum += p.hh
  }
  const cnt = { 业委会: 0, 物管会: 0, 未成立: 0, 未知: 0 }
  for (const p of list) cnt[p.regime] = (cnt[p.regime] || 0) + 1
  const selfGov = cnt['业委会'] + cnt['物管会']
  return {
    count: list.length,
    streetCount: rows.value.length,
    ywh: cnt['业委会'],
    wgh: cnt['物管会'],
    none: cnt['未成立'],
    unknown: cnt['未知'],
    rate: list.length ? selfGov / list.length : null,
    feeCount: fees.length,
    feeAvg: fees.length ? fees.reduce((a, b) => a + b, 0) / fees.length : null,
    hh: hhSum || null,
    priceAvg: prices.length
      ? Math.round(prices.reduce((a, b) => a + b, 0) / prices.length)
      : null,
  }
})

// 分享链接带 street 时，自动展开对应行
function syncExpanded(street) {
  if (!street) { expanded.value = ''; return }
  const hit = rowsAll.value.find((r) => r.street === street)
  if (hit) expanded.value = hit.key
}
watch(() => props.listState.street, (s) => syncExpanded(s), { immediate: true })
watch(() => props.projects, () => syncExpanded(props.listState.street))
watch([kw, band, activeDistricts], () => {
  if (!props.listState.street) expanded.value = ''
})

function clearStreet() {
  props.listState.street = ''
}

function setSort(key) {
  if (props.listState.sortKey === key) {
    props.listState.sortDir = props.listState.sortDir === 'asc' ? 'desc' : 'asc'
  } else {
    props.listState.sortKey = key
    props.listState.sortDir = key === 'district' || key === 'street' ? 'asc' : 'desc'
  }
}

function setPSort(key) {
  if (props.listState.psortKey === key) {
    props.listState.psortDir = props.listState.psortDir === 'asc' ? 'desc' : 'asc'
  } else {
    props.listState.psortKey = key
    // 数字列第一次点默认从大到小（先看贵的 / 新的），文字列从 A 到 Z
    props.listState.psortDir = key === 'fee' || key === 'year' ? 'desc' : 'asc'
  }
}

/** 展开表用的排序：数字列空值永远排最后，治理状态按「未成立 → 物管会 → 未知 → 业委会」 */
function sortedProjects(list) {
  const k = psort.value.key
  const d = psort.value.dir === 'asc' ? 1 : -1
  const arr = [...list]
  arr.sort((a, b) => {
    if (k === 'regime') {
      return ((ORDER[a.regime] ?? 9) - (ORDER[b.regime] ?? 9)) * d ||
        a.name.localeCompare(b.name, 'zh-Hans-CN')
    }
    if (k === 'name' || k === 'feeMode' || k === 'company') {
      const av = a[k] || ''
      const bv = b[k] || ''
      // 没填的排最后，不随升降序翻面
      if (!av !== !bv) return av ? -1 : 1
      return av.localeCompare(bv, 'zh-Hans-CN') * d
    }
    const av = a[k]
    const bv = b[k]
    const an = av === null || av === undefined
    const bn = bv === null || bv === undefined
    if (an || bn) return an && bn ? 0 : an ? 1 : -1
    return (av - bv) * d
  })
  return arr
}

function toggleRow(key) {
  expanded.value = expanded.value === key ? '' : key
}

function openInMap(r) {
  emit('open-map', { district: r.district, street: r.street })
}

function rateStyle(r) {
  if (r === null) return { color: '#5b6880' }
  if (r >= 0.6) return { color: '#22c55e' }
  if (r >= 0.3) return { color: '#f59e0b' }
  return { color: '#ef4444' }
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

// ── CSV 导出 ──
function csvCell(v) {
  if (v === null || v === undefined) return ''
  const s = String(v)
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

function download(name, lines) {
  const text = '\ufeff' + lines.map((l) => l.map(csvCell).join(',')).join('\r\n')
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function stamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`
}

// 导出文件名带上当前筛选范围，多份文件不会互相覆盖
function areaTag() {
  const ds = props.filters.districts
  if (ds.length === 1) return ds[0]
  if (pinStreet.value) return pinStreet.value
  if (ds.length > 1) return '多区'
  return '全市'
}

function exportStreets() {
  const lines = [[
    '城区', '街道', '小区数', '业委会', '物管会', '均未成立', '未知',
    '自治率(%)', '物业费均价(元/㎡·月)', '有物业费样本数',
  ]]
  for (const r of rows.value) {
    lines.push([
      r.district, r.street, r.count, r.ywh, r.wgh, r.none, r.unknown,
      r.rate === null ? '' : (r.rate * 100).toFixed(1),
      r.feeAvg === null ? '' : r.feeAvg.toFixed(2),
      r.feeCount,
    ])
  }
  const s = summary.value
  lines.push([
    '合计/均值', `${rows.value.length} 个街道`, s.count, s.ywh, s.wgh, s.none, s.unknown,
    s.rate === null ? '' : (s.rate * 100).toFixed(1),
    s.feeAvg === null ? '' : s.feeAvg.toFixed(2),
    s.feeCount,
  ])
  download(`北京街道治理_${areaTag()}_汇总_${stamp()}.csv`, lines)
}

function exportProjects() {
  const lines = [['城区', '街道', '小区名称', '治理状态', '物业费(元/㎡·月)', '物业费是否异常', '计费方式', '建成年代', '物业服务企业']]
  for (const r of rows.value) {
    for (const p of sortedProjects(r.projects)) {
      lines.push([
        p.district, p.street, p.name, p.regime,
        p.fee === null || p.fee === undefined ? '' : p.fee.toFixed(2),
        p.fee === null || p.fee === undefined ? '' : (p.feeOk ? '否' : '是'),
        p.feeMode || '', p.year || '', p.company || '',
      ])
    }
  }
  download(`北京街道治理_${areaTag()}_小区明细_${stamp()}.csv`, lines)
}
</script>

<style scoped>
.sv { display: flex; flex-direction: column; gap: 10px; }

/* 分享定位提示 */
.street-pin {
  display: flex; align-items: center; gap: 9px;
  background: linear-gradient(90deg, rgba(76, 154, 255, 0.12), rgba(76, 154, 255, 0.03));
  border: 1px solid rgba(76, 154, 255, 0.3);
  border-radius: 10px;
  padding: 8px 13px;
  font-size: 12px;
  color: #9db6d4;
}
.sp-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px rgba(76, 154, 255, 0.16);
  flex-shrink: 0;
}
.sp-txt b { color: #cfe3ff; font-weight: 600; }
.sp-btn {
  margin-left: auto;
  font-size: 11px; font-family: inherit;
  padding: 3px 10px;
  border-radius: 7px;
  border: 1px solid rgba(76, 154, 255, 0.35);
  background: rgba(76, 154, 255, 0.1);
  color: #9dc2f0;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.14s;
}
.sp-btn:hover { background: rgba(76, 154, 255, 0.2); color: #dbeaff; }

/* 汇总条 */
.sv-sum {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--border-soft);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
}
.sum-item {
  background: var(--panel);
  padding: 10px 14px;
  display: flex; flex-direction: column; gap: 1px;
}
.sv-v { font-size: 18px; font-weight: 650; font-variant-numeric: tabular-nums; letter-spacing: -0.3px; }
.sv-l { font-size: 10.5px; color: var(--text-faint); }

/* 工具栏 */
.sv-bar {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px; flex-wrap: wrap;
  background: var(--panel);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 11px 14px;
}
.sv-left { display: flex; flex-direction: column; gap: 8px; flex: 1; min-width: 320px; }
.sv-row1 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.level-tabs { background: var(--panel-2); padding: 3px; flex: 0 0 auto; }
.level-tabs button { padding: 4px 13px; font-size: 11.5px; }
.sv-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.sv-search {
  display: flex; align-items: center; gap: 7px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  color: var(--text-faint);
  flex: 1;
  min-width: 220px;
  max-width: 380px;
}
.sv-search:focus-within { border-color: var(--accent); }
.sv-search input {
  flex: 1;
  background: transparent; border: 0; outline: none;
  color: var(--text); font-family: inherit; font-size: 12.5px;
}
.sv-search input::placeholder { color: #4a5872; }
.clear-x {
  background: none; border: 0; color: var(--text-faint);
  cursor: pointer; font-size: 14px; line-height: 1; padding: 0 2px;
}
.clear-x:hover { color: var(--text); }

.sv-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.sv-chip {
  font-size: 11.5px; font-family: inherit;
  padding: 3px 9px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.14s;
}
.sv-chip:hover { border-color: #3a4a6b; color: var(--text); }
.sv-chip.on { background: #1d2c48; border-color: var(--accent); color: #cfe3ff; }

.sv-btn {
  font-size: 11.5px; font-family: inherit;
  padding: 5px 11px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.14s;
  white-space: nowrap;
}
.sv-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--text); }
.sv-btn:disabled { opacity: 0.4; cursor: default; }
.sv-btn.copy { display: inline-flex; align-items: center; gap: 5px; }
.sv-btn.done { border-color: rgba(34, 197, 94, 0.45); color: var(--green); }

/* 表格 */
/* 用 clip 而不是 hidden：hidden 会成为滚动容器，把表头钉在这个盒子里而不是窗口上 */
.sv-panel { overflow: clip; }
.sv-tbl-wrap {
  min-height: 420px;
}
.sv-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }

.sv-tbl thead th {
  position: sticky; top: 0; z-index: 2;
  background: var(--panel-2);
  color: var(--text-faint);
  font-weight: 500; font-size: 11px;
  padding: 9px 8px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}
.sv-tbl thead th:hover { color: var(--text); }
.sv-tbl thead th.sorted { color: var(--accent); }
.th-left { text-align: left; }
.th-right { text-align: right; }
.th-op { width: 52px; cursor: default; }
.sort-mark { font-size: 9px; margin-left: 1px; }

.sv-row { cursor: pointer; }
.sv-row td {
  padding: 6px 8px;
  border-bottom: 1px solid #161f31;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sv-row:hover td { background: rgba(76, 154, 255, 0.05); }
.sv-row.open td { background: rgba(76, 154, 255, 0.07); }

.c-dist { color: var(--text-faint); font-size: 11.5px; }
.c-street { color: var(--text); display: flex; align-items: center; gap: 4px; }
.street-name { overflow: hidden; text-overflow: ellipsis; }
.caret { color: #3f4f6d; font-size: 9px; width: 9px; flex-shrink: 0; }
.sv-row.open .caret { color: var(--accent); }
.flag {
  font-size: 9.5px; color: #7d6a3d;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.22);
  border-radius: 4px;
  padding: 0 4px;
  flex-shrink: 0;
}
.c-num { text-align: right; font-variant-numeric: tabular-nums; }
.c-num.b { color: var(--text); font-weight: 600; }
.c-num.muted { color: #46536b; }
.c-op { text-align: right; }
.rate { font-variant-numeric: tabular-nums; }
.map-btn {
  font-size: 10.5px; font-family: inherit;
  padding: 2px 7px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-faint);
  cursor: pointer;
  transition: all 0.14s;
}
.map-btn:hover { border-color: var(--accent); color: #cfe3ff; background: #1d2c48; }

.sv-tbl tfoot td {
  /* 表格不再是内部滚动区，合计行跟着表格末尾走，不要挂在窗口底部挡住内容 */
  background: var(--panel-2);
  border-top: 1px solid var(--border);
  padding: 8px;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
.tf-label { color: var(--text-faint); text-align: left; }

.no-data { text-align: center; color: var(--text-faint); padding: 44px 0; }

/* 展开明细 */
.detail-row > td { padding: 0 !important; background: #0c1220; }
.detail { padding: 10px 12px 12px 26px; border-bottom: 1px solid var(--border); }
.detail-head {
  display: flex; align-items: center; gap: 12px;
  font-size: 12px; color: var(--text);
  padding-bottom: 7px; flex-wrap: wrap;
}
.dh-sub { font-size: 10.5px; color: var(--text-faint); }
.dh-copy {
  margin-left: auto;
  font-size: 10.5px; font-family: inherit;
  padding: 2px 9px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-faint);
  cursor: pointer;
  transition: all 0.14s;
  white-space: nowrap;
}
.dh-copy:hover { border-color: var(--accent); color: #cfe3ff; }
.dh-copy.done { border-color: rgba(34, 197, 94, 0.45); color: var(--green); }
.detail-scroll { border: 1px solid var(--border-soft); border-radius: 8px; }
.sub-tbl { width: 100%; border-collapse: collapse; font-size: 11.5px; table-layout: fixed; }
.sub-tbl th {
  position: sticky; top: 0; z-index: 3;
  background: #121a2b;
  color: var(--text-faint);
  font-weight: 500; font-size: 10.5px;
  text-align: left;
  padding: 6px 9px;
  border-bottom: 1px solid var(--border-soft);
  white-space: nowrap;
  user-select: none;
}
.sub-tbl th.sortable { cursor: pointer; }
.sub-tbl th.sortable:hover { color: var(--text); }
.sub-tbl th.sorted { color: var(--accent); }
.sub-tbl th.th-right { text-align: right; }
.sub-tbl th .sort-mark { font-size: 9px; margin-left: 1px; }
.sub-tbl td {
  padding: 5px 9px;
  border-bottom: 1px solid #141c2c;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sub-tbl tr:last-child td { border-bottom: 0; }
.sub-tbl tbody tr:hover td { background: rgba(76, 154, 255, 0.045); }
.s-name { color: var(--text); width: 26%; max-width: 320px; cursor: pointer; }
.s-name:hover { color: #9cc6ff; text-decoration: underline; text-decoration-color: rgba(76,154,255,.45); text-underline-offset: 2px; }
.s-regime { width: 82px; }
.s-fee { width: 74px; text-align: right; font-variant-numeric: tabular-nums; }
.s-hh { width: 64px; text-align: right; font-variant-numeric: tabular-nums; }
.s-price { width: 72px; text-align: right; font-variant-numeric: tabular-nums; }
.s-year { width: 60px; text-align: right; font-variant-numeric: tabular-nums; }
.s-mode { width: 76px; }
.s-company { width: 24%; }
.s-gov { width: 46px; text-align: right; }
.sub-tbl th:nth-child(7) { width: 46px; text-align: right; }

.regime-tag {
  display: inline-block;
  font-size: 10px;
  padding: 0 6px;
  border-radius: 4px;
  border: 1px solid transparent;
  line-height: 1.6;
}
.na { color: #3d4a60; }
.suspect { color: #f87171; }

.sv-note {
  font-size: 11px;
  color: #3d4a60;
  line-height: 1.6;
  padding: 0 4px 4px;
}

@media (max-width: 1100px) {
  .sv-sum { grid-template-columns: repeat(4, 1fr); }
  /* 窄屏表格放不下，仍然给个横向滚动条；表头此时跟着页面滚走 */
  .sv-tbl-wrap { overflow-x: auto; }
  .detail-scroll { overflow-x: auto; }
  .sub-tbl th { position: static; }
}
</style>
