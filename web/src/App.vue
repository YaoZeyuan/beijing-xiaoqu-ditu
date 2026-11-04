<template>
  <div class="app">
    <!-- ── 右上角 Fork 角标（纯 CSS 缎带，任意 DPI 都清晰） ── -->
    <a
      class="fork-me"
      :href="REPO_URL"
      data-ribbon="Fork me on GitHub"
      target="_blank"
      rel="noopener"
      title="在 GitHub 上查看源码"
    >Fork me on GitHub</a>

    <!-- ── 头部 ── -->
    <header class="hdr">
      <div class="brand">
        <div class="logo">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="brand-txt">
          <h1>北京住宅小区治理地图</h1>
          <p>分布 · 物业费 · 业委会 / 物管会</p>
        </div>
      </div>
      <div class="hdr-meta">
        <div class="meta-item">
          <span class="mk">数据来源</span>
          <a :href="meta.sourceUrl" target="_blank" rel="noopener">北京市住建委 · 物业项目信息查询</a>
        </div>
        <div class="meta-item">
          <span class="mk">更新</span>
          <span>{{ meta.generated || '—' }}</span>
        </div>
        <div class="meta-item">
          <span class="mk">物业费覆盖</span>
          <span :class="['cov', feeCoverage >= 60 ? 'ok' : 'warn']">
            {{ meta.withFee || 0 }} / {{ meta.total || 0 }}
          </span>
        </div>
      </div>
    </header>

    <!-- ── 加载 ── -->
    <!-- 数据下载页不依赖小区数据，别让它等这 3MB -->
    <div v-if="loading && view !== 'data'" class="loading">
      <div class="spinner"></div>
      <p>正在载入 {{ loadingMsg }}</p>
    </div>

    <template v-if="!loading || view === 'data'">
      <!-- ── 视图切换 ── -->
      <div class="view-bar">
        <div class="tabs view-tabs">
          <button
            v-for="v in VIEWS"
            :key="v.key"
            :class="{ active: view === v.key }"
            @click="setView(v.key)"
          >
            <span class="vt-icon" v-html="v.icon"></span>{{ v.label }}
          </button>
        </div>
        <span class="view-hint">
          <template v-if="view === 'map'">按城区下钻到街道，点击街道查看该街道小区</template>
          <template v-else-if="view === 'list'">按街道汇总排序、筛选、展开明细，可导出 CSV 用于线下核对</template>
          <template v-else>全部数据以 CSV / JSON 双份开放下载，可直接用于研究</template>
        </span>
        <div class="view-actions">
          <button class="copy-btn" :class="{ done: copied }" @click="copyLink">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8">
              <path v-if="!copied" d="M10 13a5 5 0 007 0l2-2a5 5 0 00-7-7l-1 1" stroke-linecap="round"/>
              <path v-if="!copied" d="M14 11a5 5 0 00-7 0l-2 2a5 5 0 007 7l1-1" stroke-linecap="round"/>
              <path v-else d="M4 12.5l5 5L20 6.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            {{ copied ? '链接已复制' : '复制分享链接' }}
          </button>

          <!-- 移动端：缎带太占地方，换成这一枚胶囊；桌面端隐藏 -->
          <a
            class="fork-pill"
            :href="REPO_URL"
            target="_blank"
            rel="noopener"
            title="在 GitHub 上查看源码"
          >
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <path
                fill="currentColor"
                d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
              />
            </svg>
            <span>GitHub</span>
          </a>
        </div>
      </div>

      <!-- ── 数据口径说明（数据下载页不显示） ── -->
      <template v-if="view !== 'data'">
      <div v-if="pendingRatio < 0.9" class="banner">
        <span class="b-icon">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2" stroke-linecap="round"/>
          </svg>
        </span>
        <span class="b-txt">
          <b>数据补抓中</b>　当前已匹配 <b>{{ (meta.withRegime || 0).toLocaleString() }}</b> / {{ (meta.total || 0).toLocaleString() }} 个小区。
        </span>
        <span class="b-bar"><i :style="{ width: Math.max(2, pendingRatio * 100) + '%' }"></i></span>
      </div>
      <div v-else class="banner banner-info">
        <span class="b-icon">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="9"/><path d="M12 16v-5M12 8h.01" stroke-linecap="round"/>
          </svg>
        </span>
        <span class="b-txt">
          <b>数据口径</b>　全量 {{ (meta.total || 0).toLocaleString() }} 个小区已从住建委抓取完成，
          <b>{{ (meta.withRegime || 0).toLocaleString() }}</b> 个有业委会/物管会状态、
          <b>{{ (meta.withFee || 0).toLocaleString() }}</b> 个有物业费标准。
          无物业费的小区多为<b>酬金制</b>（{{ (meta.feeMode?.酬金制 || 0).toLocaleString() }} 个，费用按实结算、不设固定单价）或尚未申报；
          另有 {{ meta.feeSuspect || 0 }} 个申报值明显异常（&gt;20 元/㎡·月），已在统计中标注并排除均价计算。
          <template v-if="meta.withFeeTiers">
            另有 <b>{{ meta.withFeeTiers.toLocaleString() }}</b> 个小区按房屋性质 / 建筑类型分档登记，
            其中 <b>{{ (meta.withFeeRange || 0).toLocaleString() }}</b> 个各档单价不同
            （如同一小区回迁房 1.0、商品房 2.58），列表里给出的是<b>区间</b>而非单一数字。
            <b>点小区名</b>可看逐档构成；每行末尾的 ↗ 可直接跳到住建委原页面。
          </template>
          <template v-if="meta.withHH">
            户数与挂牌参考价来自<b>链家开源小区库</b>（2018/2019 快照，与备案一对一匹配）与
            <b>互联网公开页补查</b>（百科 / 房产平台 / 政府网站，来源见小区详情），
            分别覆盖 {{ (meta.withHH || 0).toLocaleString() }} 与 {{ (meta.withPrice || 0).toLocaleString() }} 个小区，
            挂牌价≠成交价，仅供横向比较。
            带 <b>*</b> 的户数是<b>所在小区合计</b>——该备案只是一个分区/楼栋，网上查不到分区独立户数；
            这类数在合计与地图着色里已按小区去重，只算一次。
          </template>
        </span>
      </div>
      </template>

      <!-- ── KPI ── -->
      <div v-if="view === 'map'" class="kpi-row">
        <div class="kpi" v-for="k in kpis" :key="k.label">
          <div class="kpi-label">{{ k.label }}</div>
          <div class="kpi-value">
            {{ k.value }}<span class="kpi-unit" v-if="k.unit">{{ k.unit }}</span>
          </div>
          <div class="kpi-foot" :class="k.tone">{{ k.foot }}</div>
        </div>
      </div>

      <!-- ── 主体 ── -->
      <main v-if="view === 'map'" class="main">
        <!-- 左：指标 + 筛选 -->
        <aside class="panel left">
          <div class="panel-title">
            视图指标
            <span class="sub">点击切换着色</span>
          </div>
          <div class="metric-list">
            <button
              v-for="m in METRICS"
              :key="m.key"
              :class="['metric-btn', { active: metric === m.key }]"
              @click="metric = m.key"
            >
              <span class="mb-left">
                <span class="mb-dot" :style="{ background: m.color }"></span>
                {{ m.label }}
              </span>
              <span class="mb-desc">{{ m.desc }}</span>
            </button>
          </div>

          <div class="divider"></div>

          <div class="panel-title">
            筛选
            <button class="link-btn" v-if="hasFilter" @click="resetFilters">清空</button>
          </div>

          <div class="filter-block">
            <label class="f-label">城区</label>
            <div class="chip-wrap">
              <button
                v-for="d in districtNames"
                :key="d"
                :class="['f-chip', { on: filters.districts.includes(d) }]"
                @click="toggleDistrict(d)"
              >{{ shortName(d) }}</button>
            </div>
          </div>

          <div class="filter-block">
            <label class="f-label">治理状态</label>
            <div class="chip-wrap">
              <button
                v-for="r in REGIMES"
                :key="r.key"
                :class="['f-chip', { on: filters.regimes.includes(r.key) }]"
                :style="filters.regimes.includes(r.key) ? { borderColor: r.color, color: r.color } : {}"
                @click="toggleRegime(r.key)"
              >
                <span class="dot" :style="{ background: r.color }"></span>{{ r.key }}
              </button>
            </div>
          </div>

          <div class="filter-block">
            <label class="f-label">物业费区间 <span class="hint">元/㎡·月</span></label>
            <div class="fee-range">
              <input v-model.number="filters.feeMin" type="number" step="0.5" min="0" placeholder="最低" />
              <span class="sep">—</span>
              <input v-model.number="filters.feeMax" type="number" step="0.5" min="0" placeholder="最高" />
            </div>
          </div>

          <div class="filter-block">
            <label class="f-label">关键词</label>
            <input
              v-model.trim="filters.keyword"
              class="text-input"
              type="text"
              placeholder="小区名 / 街道 / 物业公司"
            />
          </div>

          <div class="filter-result">
            命中 <b>{{ filtered.length.toLocaleString() }}</b> 个小区
          </div>
        </aside>

        <!-- 中：地图 -->
        <section class="panel center">
          <div class="panel-title">
            <span>{{ selectedDistrict ? selectedDistrict + ' · ' + metricLabel : metricLabel + '分布' }}</span>
            <span class="sub">
              <template v-if="selectedDistrict">点击街道筛选小区 · 左上角返回全市</template>
              <template v-else>滚轮缩放 · 点击城区下钻到街道</template>
            </span>
          </div>
          <div class="map-wrap">
            <BeijingMap
              :districts="mapData"
              :streets="streetData"
              :metric="metric"
              :selected="selectedDistrict"
              :selected-street="selectedStreet"
              @select="onMapSelect"
              @select-street="onSelectStreet"
              @back="clearSelection"
            />
            <div v-if="metric === 'feeAvg' && feeCoverage < 5" class="map-hint">
              物业费数据仍在补抓中，当前覆盖率 {{ feeCoverage.toFixed(1) }}%
            </div>
          </div>
        </section>

        <!-- 右：排行 / 构成 -->
        <aside class="panel right">
          <template v-if="selectedDistrict">
            <DistrictDetail
              :district="selectedDistrict"
              :projects="districtProjects"
              :metric="metric"
              :selected-street="selectedStreet"
              @select-street="onSelectStreet"
              @close="clearSelection"
            />
          </template>
          <template v-else>
            <div class="panel-title">
              街道排行榜
              <span class="sub">按 {{ metricLabel }}</span>
            </div>
            <div class="rank-list">
              <div
                v-for="(s, i) in topStreets"
                :key="s.district + s.street"
                class="rank-item"
                @click="jumpToStreet(s)"
              >
                <span class="rank-no" :class="{ top3: i < 3 }">{{ i + 1 }}</span>
                <span class="rank-mid">
                  <span class="rank-name">{{ s.street }}</span>
                  <span class="rank-dist">{{ shortName(s.district) }}</span>
                </span>
                <span class="rank-bar">
                  <i :style="{ width: (s.value / topStreets[0].value * 100) + '%', background: metricColor }"></i>
                </span>
                <span class="rank-val">{{ fmtVal(s.value) }}</span>
              </div>
            </div>

            <div class="divider"></div>

            <div class="panel-title">
              治理状态构成
              <span class="sub">全市</span>
            </div>
            <div class="regime-bars">
              <div class="rb-item" v-for="r in regimeSummary" :key="r.key">
                <span class="rb-dot" :style="{ background: r.color }"></span>
                <span class="rb-name">{{ r.key }}</span>
                <span class="rb-track"><i :style="{ width: r.pct + '%', background: r.color }"></i></span>
                <span class="rb-num">{{ r.count.toLocaleString() }}</span>
                <span class="rb-pct">{{ r.pct.toFixed(1) }}%</span>
              </div>
            </div>
          </template>
        </aside>
      </main>

      <!-- ── 名录 ── -->
      <ProjectTable
        v-if="view === 'map'"
        :projects="tableProjects"
        :selected-street="jumpStreet"
        :page="pager.page"
        :size="pager.size"
        @update:page="pager.page = $event"
        @update:size="pager.size = $event"
      />

      <!-- ── 街道列表视图 ── -->
      <StreetListView
        v-else-if="view === 'list'"
        :projects="filtered"
        :districts="districtNames"
        :filters="filters"
        :list-state="listState"
        :page="pager.page"
        :size="pager.size"
        @update:page="pager.page = $event"
        @update:size="pager.size = $event"
        @open-map="onOpenMap"
      />

      <!-- ── 数据下载 ── -->
      <DataPage v-else-if="view === 'data'" />
    </template>

    <!-- ── 小区详情弹窗（三处表格共用） ── -->
    <ProjectModal />

    <!-- ── Vercel Web Analytics（仅生产构建注入，本地 dev 不发请求） ── -->
    <Analytics v-if="isProd" :before-send="beforeSend" />

    <footer class="foot">
      <span>数据来自北京市住建委公开页面，仅供社区治理研究参考</span>
      <span v-if="meta.coverage">
        名称匹配 {{ meta.coverage.listMatched }} 条 · 详情匹配 {{ meta.coverage.detailMatched }} 条
      </span>
    </footer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, provide } from 'vue'
import { Analytics } from '@vercel/analytics/vue'
import { useRoute, useRouter } from 'vue-router'
import BeijingMap from './components/BeijingMap.vue'
import DistrictDetail from './components/DistrictDetail.vue'
import ProjectTable from './components/ProjectTable.vue'
import StreetListView from './components/StreetListView.vue'
import ProjectModal from './components/ProjectModal.vue'
import DataPage from './components/DataPage.vue'
import { readUrl, buildQuery, DEFAULT_PAGE_SIZE } from './utils/urlState'

const REPO_URL = 'https://github.com/YaoZeyuan/beijing-xiaoqu-ditu'
const isProd = import.meta.env.PROD

// 筛选、下钻都会 replace 一次地址，但页面还是同一个页面。
// Analytics 组件会跟着 route 变化上报 pageview，这里把「路径没变」的重复上报丢掉，
// 只保留真正从 / 切到 /list（或反过来）的那一次，否则调一次筛选就多一条浏览记录。
let lastTrackedPath = ''
function beforeSend(event) {
  if (event.type !== 'pageview') return event
  const key = event.route || String(event.url || '').split('?')[0]
  if (key === lastTrackedPath) return null
  lastTrackedPath = key
  return event
}

const VIEWS = [
  {
    key: 'map',
    label: '地图视图',
    icon: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 3L3 6v15l6-3 6 3 6-3V3l-6 3-6-3z" stroke-linejoin="round"/><path d="M9 3v15M15 6v15"/></svg>',
  },
  {
    key: 'list',
    label: '街道列表',
    icon: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" stroke-linecap="round"/></svg>',
  },
  {
    key: 'data',
    label: '数据下载',
    icon: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v11m0 0l-4-4m4 4l4-4M4 20h16" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  },
]

const METRICS = [
  { key: 'count', label: '小区数量', desc: '密度分布', color: '#4c9aff', unit: '个' },
  { key: 'rate', label: '自治组织覆盖率', desc: '业委会+物管会', color: '#22c55e', unit: '%' },
  { key: 'feeAvg', label: '平均物业费', desc: '元/㎡·月', color: '#f59e0b', unit: '' },
  { key: 'hh', label: '小区规模', desc: '户数合计', color: '#8b5cf6', unit: '' },
  { key: 'price', label: '平均挂牌价', desc: '元/㎡·参考价', color: '#ec4899', unit: '' },
]

const REGIMES = [
  { key: '业委会', color: '#22c55e' },
  { key: '物管会', color: '#f59e0b' },
  { key: '未成立', color: '#ef4444' },
  { key: '未知', color: '#64748b' },
]

const loading = ref(true)
const loadingMsg = ref('小区数据')
const meta = ref({})
// 政府详情页链接模板藏在 meta 里，供各处 GovLink 拼地址
provide('meta', meta)
const projects = ref([])

// ── 初始状态来自 URL，支持分享具体区域 ──
// 视图由路径决定（/ 地图，/list 列表），其余筛选条件仍在 query 里
const route = useRoute()
const router = useRouter()

// 只取 query 部分交给 readUrl，避免它再去读一次 location
function queryOf(r) {
  const i = r.fullPath.indexOf('?')
  return i >= 0 ? r.fullPath.slice(i) : ''
}

// 视图 = 路径。守卫已经把尾斜杠去掉，这里再兜一层，防止将来加子路径时判断失效
function viewOfPath(path) {
  if (path === '/data' || path.startsWith('/data/')) return 'data'
  return path === '/list' || path.startsWith('/list/') ? 'list' : 'map'
}

const boot = readUrl({}, queryOf(route))
const bootView = viewOfPath(route.path)

const metric = ref(boot.metric)
const view = ref(bootView)
const selectedDistrict = ref(bootView === 'map' ? boot.districts[0] || '' : '')
const selectedStreet = ref(boot.street)
const jumpStreet = ref(bootView === 'map' ? boot.street : '')

const filters = reactive({
  districts: bootView === 'list' ? [...boot.districts] : [],
  regimes: [...boot.regimes],
  feeMin: boot.feeMin,
  feeMax: boot.feeMax,
  keyword: boot.keyword,
})

// 列表视图专属状态，同样参与 URL 同步
const listState = reactive({
  band: boot.band,
  level: boot.level,
  sortKey: boot.sortKey,
  sortDir: boot.sortDir,
  // 展开街道后那张小区表自己的排序
  psortKey: boot.psortKey,
  psortDir: boot.psortDir,
  street: bootView === 'list' ? boot.street : '',
})

// 分页：地图页的名录和列表页的小区明细共用一套 page/size，写进 URL 便于保存分享
const pager = reactive({ page: boot.page, size: boot.size })
// 街道汇总一次列完 298 行，不分页；只有这两个视图需要把 page/size 写进链接
const paginated = computed(() =>
  view.value === 'data' ? false
    : (view.value === 'map' || listState.level === 'project'))

const districtNames = computed(() => meta.value.districts || [])
const hasFilter = computed(() =>
  filters.districts.length || filters.regimes.length ||
  filters.feeMin !== null || filters.feeMax !== null || filters.keyword)

const metricLabel = computed(() => METRICS.find((m) => m.key === metric.value)?.label || '')
const metricColor = computed(() => METRICS.find((m) => m.key === metric.value)?.color || '#4c9aff')

const feeCoverage = computed(() => {
  const t = meta.value.total || 0
  return t ? ((meta.value.withFee || 0) / t) * 100 : 0
})

const pendingRatio = computed(() => {
  const t = meta.value.total || 0
  return t ? (meta.value.withRegime || 0) / t : 0
})

function shortName(d) {
  return (d || '').replace(/区$/, '').replace('北京经济技术开发', '经开')
}

function toggleDistrict(d) {
  const i = filters.districts.indexOf(d)
  i >= 0 ? filters.districts.splice(i, 1) : filters.districts.push(d)
}

function toggleRegime(k) {
  const i = filters.regimes.indexOf(k)
  i >= 0 ? filters.regimes.splice(i, 1) : filters.regimes.push(k)
}

function resetFilters() {
  filters.districts = []
  filters.regimes = []
  filters.feeMin = null
  filters.feeMax = null
  filters.keyword = ''
}

// ── 筛选 ──
const filtered = computed(() => {
  const kw = filters.keyword.toLowerCase()
  const dSet = filters.districts
  const rSet = filters.regimes
  const fmin = filters.feeMin
  const fmax = filters.feeMax
  return projects.value.filter((p) => {
    if (dSet.length && !dSet.includes(p.district)) return false
    if (rSet.length && !rSet.includes(p.regime)) return false
    if (fmin !== null && fmin !== '' && (p.fee === null || p.fee < fmin)) return false
    if (fmax !== null && fmax !== '' && (p.fee === null || p.fee > fmax)) return false
    if (kw) {
      const hay = (p.name + p.street + p.company + p.district).toLowerCase()
      if (!hay.includes(kw)) return false
    }
    return true
  })
})

// ── 聚合（区级 / 街道级共用一套口径） ──
function aggregateBy(list, keyField) {
  const m = new Map()
  for (const p of list) {
    const k = p[keyField] || (keyField === 'street' ? '未标注街道' : '')
    if (!k) continue
    let s = m.get(k)
    if (!s) {
      s = {
        name: k, count: 0, fees: [], selfGov: 0,
        hh: 0, hhCount: 0, hhSeen: new Set(), prices: [],
        regime: { 业委会: 0, 物管会: 0, 未成立: 0, 未知: 0 },
        streets: new Set(),
      }
      m.set(k, s)
    }
    s.count++
    if (p.feeOk && p.fee !== undefined) s.fees.push(p.fee)
    if (p.regime === '业委会' || p.regime === '物管会') s.selfGov++
    // 户数：同一小区被多条备案共用的「分区未拆」值只算一次（hhKey = 链家id）
    if (p.hh && !(p.hhKey && s.hhSeen.has(p.hhKey))) {
      if (p.hhKey) s.hhSeen.add(p.hhKey)
      s.hh += p.hh
      s.hhCount++
    }
    if (p.price) s.prices.push(p.price)
    s.regime[p.regime] = (s.regime[p.regime] || 0) + 1
    if (keyField === 'district') s.streets.add(p.street)
  }
  const out = []
  for (const s of m.values()) {
    const feeAvg = s.fees.length
      ? s.fees.reduce((a, b) => a + b, 0) / s.fees.length
      : null
    const fee2 = feeAvg === null ? null : Math.round(feeAvg * 100) / 100
    const priceAvg = s.prices.length
      ? Math.round(s.prices.reduce((a, b) => a + b, 0) / s.prices.length)
      : null
    out.push({
      name: s.name,
      count: s.count,
      feeAvg: fee2,
      feeCount: s.fees.length,
      hh: s.hh,
      hhCount: s.hhCount,
      priceAvg,
      priceCount: s.prices.length,
      regime: s.regime,
      selfGov: s.selfGov,
      streetCount: s.streets.size,
      value: metric.value === 'count' ? s.count
        : metric.value === 'rate' ? (s.count ? s.selfGov / s.count : 0)
        : metric.value === 'hh' ? (s.hh || null)
        : metric.value === 'price' ? priceAvg
        : fee2,
    })
  }
  return out
}

const mapData = computed(() => {
  const agg = aggregateBy(filtered.value, 'district')
  // 补齐没有数据的区，避免地图空洞
  const have = new Set(agg.map((a) => a.name))
  for (const d of districtNames.value) {
    if (!have.has(d)) {
      agg.push({
        name: d, count: 0, feeAvg: null, feeCount: 0,
        hh: 0, hhCount: 0, priceAvg: null, priceCount: 0,
        regime: { 业委会: 0, 物管会: 0, 未成立: 0, 未知: 0 },
        selfGov: 0, streetCount: 0, value: null,
      })
    }
  }
  return agg
})

// 下钻到某个区时，该区的街道聚合
const streetData = computed(() => {
  if (!selectedDistrict.value) return []
  return aggregateBy(
    filtered.value.filter((p) => p.district === selectedDistrict.value),
    'street',
  )
})

const districtProjects = computed(() =>
  filtered.value.filter((p) => p.district === selectedDistrict.value))

// 底部名录：选中街道时只列该街道的小区
const tableProjects = computed(() => {
  if (!selectedDistrict.value || !selectedStreet.value) return filtered.value
  return filtered.value.filter(
    (p) => p.district === selectedDistrict.value && p.street === selectedStreet.value)
})

// ── KPI ──
const kpis = computed(() => {
  const list = filtered.value
  const total = list.length
  const fees = list.filter((p) => p.feeOk).map((p) => p.fee)
  const avgFee = fees.length ? fees.reduce((a, b) => a + b, 0) / fees.length : null
  // 共享口径（多条备案用同一个小区总数）按 hhKey 去重，避免放大
  const seenHH = new Set()
  let hhTotal = null
  let hhCount = 0
  for (const p of list) {
    if (!p.hh) continue
    if (p.hhKey) {
      if (seenHH.has(p.hhKey)) continue
      seenHH.add(p.hhKey)
    }
    hhTotal = (hhTotal || 0) + p.hh
    hhCount++
  }
  const prices = list.filter((p) => p.price).map((p) => p.price)
  const priceAvg = prices.length
    ? Math.round(prices.reduce((a, b) => a + b, 0) / prices.length)
    : null
  const ywh = list.filter((p) => p.regime === '业委会').length
  const wgh = list.filter((p) => p.regime === '物管会').length
  const none = list.filter((p) => p.regime === '未成立').length
  const streetSet = new Set(list.map((p) => p.street))

  return [
    {
      label: '小区总数', value: total.toLocaleString(), unit: '个',
      foot: `覆盖 ${streetSet.size} 个街道`, tone: 'muted',
    },
    {
      label: '业委会', value: ywh.toLocaleString(), unit: '个',
      foot: total ? `占 ${(ywh / total * 100).toFixed(1)}%` : '—', tone: 'ok',
    },
    {
      label: '物管会', value: wgh.toLocaleString(), unit: '个',
      foot: total ? `占 ${(wgh / total * 100).toFixed(1)}%` : '—', tone: 'warn',
    },
    {
      label: '均未成立', value: none.toLocaleString(), unit: '个',
      foot: total ? `占 ${(none / total * 100).toFixed(1)}%` : '—', tone: 'bad',
    },
    {
      label: '平均物业费',
      value: avgFee === null ? '—' : avgFee.toFixed(2),
      unit: avgFee === null ? '' : '元/㎡·月',
      foot: `基于 ${fees.length.toLocaleString()} 个有数据小区`, tone: 'muted',
    },
    {
      label: '住宅户数',
      value: hhTotal === null ? '—' : (hhTotal / 10000).toFixed(1),
      unit: hhTotal === null ? '' : '万户',
      foot: `基于 ${hhCount.toLocaleString()} 个有户数小区`, tone: 'muted',
    },
    {
      label: '平均挂牌价',
      value: priceAvg === null ? '—' : priceAvg.toLocaleString(),
      unit: priceAvg === null ? '' : '元/㎡',
      foot: `基于 ${prices.length.toLocaleString()} 个有报价小区`, tone: 'muted',
    },
  ]
})

const regimeSummary = computed(() => {
  const total = filtered.value.length || 1
  const cnt = { 业委会: 0, 物管会: 0, 未成立: 0, 未知: 0 }
  for (const p of filtered.value) cnt[p.regime] = (cnt[p.regime] || 0) + 1
  return REGIMES.map((r) => ({
    key: r.key, color: r.color, count: cnt[r.key] || 0,
    pct: ((cnt[r.key] || 0) / total) * 100,
  }))
})

// ── 街道排行 ──
const topStreets = computed(() => {
  const m = new Map()
  for (const p of filtered.value) {
    const k = p.district + '|' + p.street
    let s = m.get(k)
    if (!s) {
      s = { district: p.district, street: p.street, count: 0, fees: [], selfGov: 0 }
      m.set(k, s)
    }
    s.count++
    if (p.feeOk) s.fees.push(p.fee)
    if (p.regime === '业委会' || p.regime === '物管会') s.selfGov++
  }
  const arr = []
  for (const s of m.values()) {
    const feeAvg = s.fees.length ? s.fees.reduce((a, b) => a + b, 0) / s.fees.length : null
    let value
    if (metric.value === 'count') value = s.count
    else if (metric.value === 'rate') value = s.count ? s.selfGov / s.count : 0
    else value = feeAvg
    if (value === null || value === undefined) continue
    arr.push({
      district: s.district, street: s.street, count: s.count,
      feeAvg, selfGov: s.selfGov, value,
    })
  }
  arr.sort((a, b) => b.value - a.value)
  return arr.slice(0, 15)
})

function fmtVal(v) {
  if (v === null || v === undefined) return '—'
  if (metric.value === 'rate') return (v * 100).toFixed(0) + '%'
  if (metric.value === 'feeAvg') return v.toFixed(2)
  return v
}

function onMapSelect(name) {
  if (selectedDistrict.value === name) {
    clearSelection()
  } else {
    selectedDistrict.value = name
    selectedStreet.value = ''
  }
}

function onSelectStreet(name) {
  selectedStreet.value = selectedStreet.value === name ? '' : name
}

function clearSelection() {
  selectedDistrict.value = ''
  selectedStreet.value = ''
}

function jumpToStreet(s) {
  selectedDistrict.value = s.district
  selectedStreet.value = s.street
  jumpStreet.value = s.street
}

// ── 视图切换：两个数据视图共用 district / street 参数，切换时把值搬过去 ──
// 数据下载页不涉及筛选，进出它时原样保留地图/列表的选中状态
function setView(v) {
  if (v === view.value) return
  if (v === 'data' || view.value === 'data') {
    view.value = v
    pager.page = 1
    window.scrollTo({ top: 0 })
    return
  }
  if (v === 'list') {
    filters.districts = selectedDistrict.value ? [selectedDistrict.value] : []
    listState.street = selectedStreet.value
  } else {
    // 地图视图的 district 表示“下钻到哪个区”，不是筛选条件：
    // 单一选区转成下钻，多选无法在地图上表达就清空，保证与直接打开链接的口径一致
    const ds = filters.districts
    selectedDistrict.value = ds.length === 1 ? ds[0] : ''
    filters.districts = []
    selectedStreet.value = listState.street
    jumpStreet.value = listState.street
  }
  view.value = v
  // 两张表的内容完全不同，页码不通用，切视图回到第一页
  pager.page = 1
  window.scrollTo({ top: 0 })
}

// 列表页点「地图」：跳回地图并定位到该街道
function onOpenMap({ district, street }) {
  selectedDistrict.value = district
  const s = street === '（未标注）' ? '' : street
  selectedStreet.value = s
  jumpStreet.value = s
  view.value = 'map'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ── 状态 → URL：router 是唯一出口，只 replace，不新增历史记录（否则后退键会被塞满） ──
const urlTarget = computed(() => {
  const path = view.value === 'list' ? '/list' : view.value === 'data' ? '/data' : '/'
  return path + buildQuery({
    metric: metric.value,
    // 地图视图优先用下钻的区，没有下钻时退回左侧的城区筛选
    districts: view.value === 'map'
      ? (selectedDistrict.value ? [selectedDistrict.value] : filters.districts)
      : filters.districts,
    street: view.value === 'map' ? selectedStreet.value : listState.street,
    regimes: filters.regimes,
    feeMin: filters.feeMin,
    feeMax: filters.feeMax,
    keyword: filters.keyword,
    band: listState.band,
    level: listState.level,
    sortKey: listState.sortKey,
    sortDir: listState.sortDir,
    psortKey: listState.psortKey,
    psortDir: listState.psortDir,
    page: paginated.value ? pager.page : 1,
    size: paginated.value ? pager.size : DEFAULT_PAGE_SIZE,
  })
})

watch(urlTarget, (t) => {
  if (route.fullPath === t) return
  // 换视图（/ ↔ /list）记一条历史，后退键能回到上一个视图；
  // 只是调筛选就 replace，否则点几下筛选就得按十几次后退
  const path = t.split('?')[0]
  if (path !== route.path) router.push(t)
  else router.replace(t)
}, { flush: 'post' })

// 数据加载完成后再按词典规范化一次（把“东城”“东华门”这类简称补成全称）
function applyUrlState(dict, search, viewOverride) {
  const s = readUrl(dict, search)
  view.value = viewOverride || s.view
  metric.value = s.metric
  if (view.value === 'map') {
    selectedDistrict.value = s.districts[0] || ''
    selectedStreet.value = s.street
    jumpStreet.value = s.street
  } else {
    filters.districts = [...s.districts]
    listState.street = s.street
  }
  filters.regimes = [...s.regimes]
  filters.feeMin = s.feeMin
  filters.feeMax = s.feeMax
  filters.keyword = s.keyword
  listState.band = s.band
  listState.level = s.level
  listState.sortKey = s.sortKey
  listState.sortDir = s.sortDir
  listState.psortKey = s.psortKey
  listState.psortDir = s.psortDir
  pager.page = s.page
  pager.size = s.size
}

// ── URL → 状态：浏览器前进 / 后退、手改地址栏、老链接重定向都走这里 ──
// 名称词典在数据到位后才有，先用空的，onMounted 里再补一次
const urlDict = ref({ districts: [], streets: [] })

watch(() => route.fullPath, () => {
  // 和当前状态算出来的地址一致，说明是上面 watch 自己写进去的，不用回灌
  if (route.fullPath === urlTarget.value) return
  applyUrlState(urlDict.value, queryOf(route), viewOfPath(route.path))
})

// ── 复制分享链接 ──
const copied = ref(false)
let copyTimer = null
async function copyLink() {
  const url = location.href
  try {
    await navigator.clipboard.writeText(url)
  } catch (e) {
    const ta = document.createElement('textarea')
    ta.value = url
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try { document.execCommand('copy') } catch (_) { /* 忽略 */ }
    ta.remove()
  }
  copied.value = true
  clearTimeout(copyTimer)
  copyTimer = setTimeout(() => { copied.value = false }, 1800)
}

onMounted(async () => {
  try {
    // 用 BASE_URL 拼绝对路径：/list 下用 document.baseURI 拼相对路径时，
    // 一旦地址带尾斜杠（/list/）就会去请求 /list/data/projects.json
    const res = await fetch(`${import.meta.env.BASE_URL}data/projects.json`)
    const json = await res.json()
    meta.value = json.meta || {}
    projects.value = json.projects || []
    // 用真实数据的名称词典把 URL 里的简称补全（?district=东城 → 东城区，?street=东华门 → 东华门街道）
    urlDict.value = {
      districts: meta.value.districts || [],
      streets: [...new Set(projects.value.map((p) => p.street).filter((s) => s && s !== '未标注街道'))],
    }
    applyUrlState(urlDict.value, queryOf(route), viewOfPath(route.path))
  } catch (e) {
    console.error(e)
    loadingMsg.value = '数据加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.app {
  max-width: 1760px;
  margin: 0 auto;
  padding: 0 22px 26px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: relative;
}

/* 右上角 Fork me on GitHub 角标。
   做法参考 github-fork-ribbon-css（Simon Whitaker，MIT）：外层 overflow:hidden 裁出角落，
   ::before 画缎带本体、::after 放文字，尺寸全部用 em —— 不依赖位图，2x / 3x 屏和
   浏览器缩放下都不会发虚，改 font-size 就能整体缩放（之前用的 PNG 在 2x 屏上发虚）。
   缎带的折角由 overflow 裁切产生，不需要 clip-path */
.fork-me {
  position: absolute;
  top: 0;
  right: 0;
  width: 12.1em;
  height: 12.1em;
  overflow: hidden;
  z-index: 20;
  font-size: 13px;
  text-decoration: none;
  text-indent: -999999px;   /* 真文字留给读屏，视觉上交给 ::after */
  pointer-events: none;
  transition: filter 0.15s ease;
}
.fork-me::before,
.fork-me::after {
  position: absolute;
  display: block;
  width: 15.38em;
  height: 1.54em;
  top: 3.23em;
  right: -3.23em;
  box-sizing: content-box;
  transform: rotate(45deg);
}
/* 缎带本体 */
.fork-me::before {
  content: "";
  padding: 0.38em 0;
  background-color: #1f883d;
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.14), rgba(0, 0, 0, 0.16));
  box-shadow: 0 0.15em 0.23em 0 rgba(0, 0, 0, 0.5);
  pointer-events: auto;
}
/* 缎带文字 + 上下两道点线「缝线」 */
.fork-me::after {
  content: attr(data-ribbon);
  color: #fff;
  font: 700 1em "Helvetica Neue", Helvetica, Arial, sans-serif;
  line-height: 1.54em;
  text-shadow: 0 -0.08em rgba(0, 0, 0, 0.45);
  text-align: center;
  text-indent: 0;
  padding: 0.15em 0;
  margin: 0.15em 0;
  border-width: 0.08em 0;
  border-style: dotted;
  border-color: rgba(255, 255, 255, 0.7);
  pointer-events: auto;
}
.fork-me:hover { filter: brightness(1.14); }

/* 移动端：缎带隐藏，改用工具栏里的胶囊按钮。
   不做成悬浮球，是因为页面主体是密集表格，浮层会压住筛选按钮和表行 */
.fork-pill { display: none; }
@media (max-width: 900px) {
  .fork-me { display: none; }
  .fork-pill {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px 5px 10px;
    border-radius: 999px;
    border: 1px solid rgba(46, 164, 79, 0.55);
    background: rgba(31, 136, 61, 0.16);
    color: #57d98b;
    font-size: 11.5px;
    font-family: inherit;
    letter-spacing: 0.2px;
    text-decoration: none;
    -webkit-tap-highlight-color: transparent;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  /* 外观跟相邻按钮等高，但热区四周各外扩 6px，手机上更好点 */
  .fork-pill::after {
    content: "";
    position: absolute;
    inset: -6px;
    border-radius: 999px;
  }
  .fork-pill svg { display: block; flex: none; }
  .fork-pill:active {
    background: rgba(31, 136, 61, 0.32);
    border-color: rgba(46, 164, 79, 0.85);
    color: #8ceab0;
  }
}

/* header */
.hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 4px 6px;
  flex-wrap: wrap;
}
/* 给角的缎带让位，避免压住右侧元信息 */
@media (min-width: 901px) {
  .hdr { padding-right: 164px; }
}
.brand { display: flex; align-items: center; gap: 12px; }
.logo {
  width: 40px; height: 40px;
  display: grid; place-items: center;
  border-radius: 12px;
  background: linear-gradient(135deg, #2b4b8f, #4c9aff);
  color: #fff;
  box-shadow: 0 6px 18px rgba(76, 154, 255, 0.3);
}
.brand-txt h1 { font-size: 19px; font-weight: 650; letter-spacing: 0.2px; }
.brand-txt p { font-size: 12px; color: var(--text-faint); letter-spacing: 0.6px; }

.hdr-meta { display: flex; gap: 22px; flex-wrap: wrap; }
.meta-item { display: flex; flex-direction: column; gap: 1px; font-size: 12px; }
.meta-item .mk { color: var(--text-faint); font-size: 10.5px; letter-spacing: 0.5px; }
.meta-item a { color: var(--accent); text-decoration: none; }
.meta-item a:hover { text-decoration: underline; }
.cov.warn { color: var(--orange); }
.cov.ok { color: var(--green); }

/* 视图切换条 */
.view-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.view-tabs {
  background: var(--panel);
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 3px;
  flex: 0 0 auto;
}
.view-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 15px;
}
.vt-icon { display: inline-flex; }
.vt-icon :deep(svg) { display: block; }
.view-hint { font-size: 11px; color: var(--text-faint); }
.view-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.copy-btn {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px; font-family: inherit;
  padding: 5px 11px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.copy-btn:hover { border-color: var(--accent); color: #cfe3ff; }
.copy-btn.done { border-color: rgba(34, 197, 94, 0.45); color: var(--green); }
@media (min-width: 901px) {
  .view-bar { padding-right: 164px; }
}

/* loading */
.loading {
  height: 60vh;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 16px; color: var(--text-dim); font-size: 13px;
}
.spinner {
  width: 34px; height: 34px;
  border: 2.5px solid #1f2b42;
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* banner */
.banner {
  display: flex;
  align-items: center;
  gap: 11px;
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.10), rgba(245, 158, 11, 0.02));
  border: 1px solid rgba(245, 158, 11, 0.26);
  border-radius: 10px;
  padding: 9px 15px;
  font-size: 11.5px;
  color: #b99a63;
}
.banner-info {
  background: linear-gradient(90deg, rgba(76, 154, 255, 0.09), rgba(76, 154, 255, 0.02));
  border-color: rgba(76, 154, 255, 0.24);
  color: #8ba7c9;
  align-items: flex-start;
}
.banner-info .b-icon { color: #4c9aff; margin-top: 2px; }
.banner-info b { color: #c3d8f0; font-weight: 600; }
.b-icon { color: #f59e0b; display: grid; place-items: center; flex-shrink: 0; }
.b-txt { flex: 1; line-height: 1.55; }
.b-txt b { color: #fbbf24; font-weight: 600; }
.b-bar {
  width: 84px; height: 4px; border-radius: 3px;
  background: #2a2410; overflow: hidden; flex-shrink: 0;
}
.b-bar i { display: block; height: 100%; background: #f59e0b; border-radius: 3px; transition: width 0.4s; }

/* kpi */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 12px;
}
.kpi {
  background: var(--panel);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 13px 16px 12px;
  position: relative;
  overflow: hidden;
}
.kpi::after {
  content: '';
  position: absolute; inset: 0 auto 0 0;
  width: 2px;
  background: linear-gradient(180deg, var(--accent), transparent);
  opacity: 0.7;
}
.kpi-label { font-size: 11.5px; color: var(--text-faint); letter-spacing: 0.3px; }
.kpi-value {
  font-size: 25px; font-weight: 650; letter-spacing: -0.5px;
  font-variant-numeric: tabular-nums; margin: 2px 0 1px;
}
.kpi-unit { font-size: 12px; font-weight: 400; color: var(--text-faint); margin-left: 3px; }
.kpi-foot { font-size: 11px; }
.kpi-foot.ok { color: var(--green); }
.kpi-foot.warn { color: var(--orange); }
.kpi-foot.bad { color: var(--red); }
.kpi-foot.muted { color: var(--text-faint); }

/* main */
.main {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr) 340px;
  gap: 12px;
  align-items: stretch;
}

.left { padding-bottom: 14px; display: flex; flex-direction: column; }
.center { display: flex; flex-direction: column; min-height: 600px; }
.right { display: flex; flex-direction: column; overflow: hidden; }

.divider { height: 1px; background: var(--border-soft); margin: 12px 16px; }

.metric-list { padding: 0 12px; display: flex; flex-direction: column; gap: 5px; }
.metric-btn {
  display: flex; flex-direction: column; gap: 1px;
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 9px;
  padding: 8px 11px;
  cursor: pointer;
  color: var(--text-dim);
  font-family: inherit;
  transition: all 0.16s;
}
.metric-btn:hover { background: var(--panel-2); color: var(--text); }
.metric-btn.active {
  background: var(--panel-3);
  border-color: #2b3a5a;
  color: var(--text);
}
.mb-left { display: flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 550; }
.mb-dot { width: 7px; height: 7px; border-radius: 2px; }
.mb-desc { font-size: 10.5px; color: var(--text-faint); padding-left: 14px; }

.filter-block { padding: 7px 16px; display: flex; flex-direction: column; gap: 6px; }
.f-label { font-size: 11px; color: var(--text-faint); letter-spacing: 0.3px; }
.hint { color: #40506e; font-size: 10px; }
.chip-wrap { display: flex; flex-wrap: wrap; gap: 5px; }
.f-chip {
  font-size: 11.5px; font-family: inherit;
  padding: 3px 8px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  cursor: pointer;
  display: inline-flex; align-items: center; gap: 4px;
  transition: all 0.14s;
}
.f-chip:hover { border-color: #3a4a6b; color: var(--text); }
.f-chip.on { background: #1d2c48; border-color: var(--accent); color: #cfe3ff; }

.fee-range { display: flex; align-items: center; gap: 6px; }
.fee-range input {
  flex: 1; min-width: 0;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 7px;
  color: var(--text);
  font-family: inherit;
  font-size: 12px;
  padding: 5px 8px;
  outline: none;
}
.fee-range input:focus, .text-input:focus { border-color: var(--accent); }
.sep { color: var(--text-faint); font-size: 11px; }

.text-input {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 7px;
  color: var(--text);
  font-family: inherit;
  font-size: 12px;
  padding: 6px 9px;
  outline: none;
  width: 100%;
}
.text-input::placeholder, .fee-range input::placeholder { color: #4a5872; }

.link-btn {
  background: none; border: 0; color: var(--accent);
  font-size: 11px; cursor: pointer; font-family: inherit; padding: 0;
}

.filter-result {
  margin-top: auto;
  padding: 10px 16px 0;
  font-size: 11.5px;
  color: var(--text-faint);
  border-top: 1px solid var(--border-soft);
}
.filter-result b { color: var(--accent); font-size: 13px; }

/* map */
.map-wrap { flex: 1; position: relative; padding: 0 6px 6px; }
.map-hint {
  position: absolute;
  top: 12px; right: 14px;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.35);
  color: #fbbf24;
  font-size: 11.5px;
  padding: 6px 11px;
  border-radius: 8px;
  backdrop-filter: blur(6px);
  max-width: 260px;
  line-height: 1.45;
}

/* rank */
.rank-list { padding: 2px 12px 0; display: flex; flex-direction: column; gap: 1px; overflow-y: auto; }
.rank-item {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 6px;
  border-radius: 7px;
  cursor: pointer;
  transition: background 0.14s;
}
.rank-item:hover { background: var(--panel-2); }
.rank-no {
  width: 17px; text-align: center;
  font-size: 10.5px; color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.rank-no.top3 { color: var(--accent); font-weight: 700; }
.rank-mid { display: flex; flex-direction: column; min-width: 0; width: 108px; flex-shrink: 0; }
.rank-name { font-size: 12px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rank-dist { font-size: 10px; color: var(--text-faint); }
.rank-bar {
  flex: 1; height: 4px; background: #182236; border-radius: 3px; overflow: hidden; min-width: 20px;
}
.rank-bar i { display: block; height: 100%; border-radius: 3px; opacity: 0.85; }
.rank-val {
  font-size: 11.5px; color: var(--text-dim); width: 42px; text-align: right;
  font-variant-numeric: tabular-nums; flex-shrink: 0;
}

/* regime bars */
.regime-bars { padding: 4px 16px 8px; display: flex; flex-direction: column; gap: 9px; }
.rb-item { display: flex; align-items: center; gap: 7px; font-size: 11.5px; }
.rb-dot { width: 7px; height: 7px; border-radius: 2px; flex-shrink: 0; }
.rb-name { width: 46px; color: var(--text-dim); flex-shrink: 0; }
.rb-track { flex: 1; height: 5px; background: #182236; border-radius: 3px; overflow: hidden; }
.rb-track i { display: block; height: 100%; border-radius: 3px; }
.rb-num { width: 48px; text-align: right; color: var(--text); font-variant-numeric: tabular-nums; }
.rb-pct { width: 40px; text-align: right; color: var(--text-faint); font-variant-numeric: tabular-nums; }

.foot {
  display: flex; justify-content: space-between;
  font-size: 11px; color: #3d4a60;
  padding: 2px 4px 0;
  flex-wrap: wrap; gap: 8px;
}

@media (max-width: 1320px) {
  .main { grid-template-columns: 230px minmax(0, 1fr); }
  .right { grid-column: 1 / -1; }
  .kpi-row { grid-template-columns: repeat(3, 1fr); }
  /* 小屏时户数/挂牌价两张新卡藏起来，避免挤成三行 */
  .kpi:nth-child(6), .kpi:nth-child(7) { display: none; }
}
@media (max-width: 900px) {
  .main { grid-template-columns: 1fr; }
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
  /* 三个视图按钮加上右侧操作在窄屏放不下，操作区独占一行，避免 GitHub 胶囊被裁 */
  .view-actions { margin-left: 0; width: 100%; justify-content: flex-start; }
}
</style>
