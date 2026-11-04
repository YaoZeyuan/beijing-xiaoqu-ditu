/**
 * URL 参数 ⇄ 页面状态
 *
 * 设计原则：
 * 1. 只用 query（?a=b），不用 hash —— 微信、飞书等 IM 转发时 hash 段容易丢，query 更稳。
 * 2. 中文参数值直接用中文，浏览器地址栏会自动解码显示，复制出来的是百分号编码，两者等价。
 * 3. 默认值不写进 URL：?view=map、?metric=count、?sort=count:desc、?band=all 这些默认态一律省略，
 *    保证分享链接只有用户真正关心的那几段。
 * 4. 同一个参数在地图视图与列表视图含义一致：
 *    district = 城区（地图里是下钻的区，列表里是筛选的区，多选时逗号分隔）
 *    street   = 街道（地图里选中高亮，列表里只留该街道并展开明细）
 */

const METRIC_KEYS = ['count', 'rate', 'feeAvg']
const BAND_KEYS = ['all', 'low', 'mid', 'high']
const REGIME_KEYS = ['业委会', '物管会', '未成立', '未知']
// 列表视图的层级：按街道汇总 / 按小区铺开
const LEVEL_KEYS = ['street', 'project']
const SORT_KEYS = [
  'district', 'street', 'count', 'ywh', 'wgh', 'none', 'unknown',
  'rate', 'feeAvg', 'feeCount',
]
// 街道汇总里「展开」那张小区表自己的排序，与上面的街道排序互不干扰
const PSORT_KEYS = ['name', 'regime', 'fee', 'year', 'feeMode', 'company']
const DEFAULT_PSORT = { key: 'regime', dir: 'asc' }

/** 每页条数白名单，与页面上的下拉共用 */
export const PAGE_SIZES = [10, 20, 50, 100, 1000]
export const DEFAULT_PAGE_SIZE = 10

function normalizeSize(v) {
  const n = toNum(v)
  return PAGE_SIZES.includes(n) ? n : DEFAULT_PAGE_SIZE
}

function normalizePage(v) {
  const n = toNum(v)
  return n && n >= 1 ? Math.floor(n) : 1
}

function splitList(v) {
  return (v || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function toNum(v) {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/** "1-3" → {min:1,max:3}；"2-" → {min:2,max:null}；"-3" → {min:null,max:3}；"2.5" → {min:2.5,max:null} */
export function parseFeeRange(raw) {
  if (!raw) return { min: null, max: null }
  const s = String(raw).trim()
  const m = s.match(/^(\d+(?:\.\d+)?)?\s*[-~]\s*(\d+(?:\.\d+)?)?$/)
  if (m && (m[1] || m[2])) {
    return { min: m[1] ? Number(m[1]) : null, max: m[2] ? Number(m[2]) : null }
  }
  return { min: toNum(s), max: null }
}

export function formatFeeRange(min, max) {
  const hasMin = min !== null && min !== undefined && min !== ''
  const hasMax = max !== null && max !== undefined && max !== ''
  if (!hasMin && !hasMax) return ''
  if (hasMin && hasMax) return `${min}-${max}`
  return hasMin ? `${min}-` : `-${max}`
}

/** 支持 ?district=东城区 / 东城（省略“区”字），也支持逗号多选 */
function normalizeDistrict(name, all) {
  if (!name) return ''
  const exact = all.find((d) => d === name)
  if (exact) return exact
  const byShort = all.find((d) => d.replace(/区$/, '') === name.replace(/区$/, ''))
  return byShort || name
}

/** 支持 ?street=东华门街道 / 东华门（省略“街道 / 地区 / 镇”） */
function normalizeStreet(name, all) {
  if (!name) return ''
  if (all.includes(name)) return name
  const base = name.replace(/(街道|地区|镇)$/, '')
  const hit = all.find((s) => s === name || s.replace(/(街道|地区|镇)$/, '') === base)
  return hit || name
}

/**
 * 从 query 读状态
 * @param {{districts?: string[], streets?: string[]}} dict 可选的名称词典，用于把简称补全为全称
 * @param {string} [search] query 串（含前导 ?），默认取 location.search；由 router 传入
 */
export function readUrl(dict = {}, search) {
  const q = new URLSearchParams(search === undefined ? location.search : search)
  const allDistricts = dict.districts || []
  const allStreets = dict.streets || []

  // 视图现在由路径决定（/ 或 /list），这里只保留对老链接 ?view=list 的识别
  const view = q.get('view') === 'list' ? 'list' : 'map'

  const metric = METRIC_KEYS.includes(q.get('metric')) ? q.get('metric') : 'count'
  const band = BAND_KEYS.includes(q.get('band')) ? q.get('band') : 'all'
  const level = LEVEL_KEYS.includes(q.get('level')) ? q.get('level') : 'street'

  const districts = splitList(q.get('district'))
    .map((d) => normalizeDistrict(d, allDistricts))
    .filter(Boolean)
  const street = normalizeStreet((q.get('street') || '').trim(), allStreets)

  const regimes = splitList(q.get('regime')).filter((r) => REGIME_KEYS.includes(r))
  const fee = parseFeeRange(q.get('fee'))

  const sortRaw = (q.get('sort') || '').split(':')
  const sortKey = SORT_KEYS.includes(sortRaw[0]) ? sortRaw[0] : 'count'
  const sortDir = sortRaw[1] === 'asc' ? 'asc' : 'desc'

  const psortRaw = (q.get('psort') || '').split(':')
  const psortKey = PSORT_KEYS.includes(psortRaw[0]) ? psortRaw[0] : DEFAULT_PSORT.key
  const psortDir = psortRaw[1] === 'desc' ? 'desc' : 'asc'

  return {
    view,
    metric,
    districts,
    street,
    regimes,
    feeMin: fee.min,
    feeMax: fee.max,
    keyword: q.get('kw') || '',
    band,
    level,
    sortKey,
    sortDir,
    psortKey,
    psortDir,
    page: normalizePage(q.get('page')),
    size: normalizeSize(q.get('size')),
  }
}

/** 状态 → query string（空串表示全默认，无需参数）
 *
 *  视图不再写进 query：地图 = `/`，列表 = `/list`，由 router 表达，
 *  这样统计面板能按路径区分两个页面。老链接里的 ?view=list 由路由守卫搬到路径上。
 */
export function buildQuery(s) {
  const q = new URLSearchParams()
  if (s.metric && s.metric !== 'count') q.set('metric', s.metric)
  if (s.districts?.length) q.set('district', s.districts.join(','))
  if (s.street) q.set('street', s.street)
  if (s.regimes?.length) q.set('regime', s.regimes.join(','))
  const fee = formatFeeRange(s.feeMin, s.feeMax)
  if (fee) q.set('fee', fee)
  if (s.keyword) q.set('kw', s.keyword)
  if (s.band && s.band !== 'all') q.set('band', s.band)
  if (s.level && s.level !== 'street') q.set('level', s.level)
  if (s.sortKey && !(s.sortKey === 'count' && s.sortDir === 'desc')) {
    q.set('sort', `${s.sortKey}:${s.sortDir}`)
  }
  if (s.psortKey && !(s.psortKey === DEFAULT_PSORT.key && s.psortDir === DEFAULT_PSORT.dir)) {
    q.set('psort', `${s.psortKey}:${s.psortDir}`)
  }
  if (s.page && s.page > 1) q.set('page', String(s.page))
  if (s.size && s.size !== DEFAULT_PAGE_SIZE) q.set('size', String(s.size))
  const str = q.toString()
  return str ? `?${str}` : ''
}

/** 参数说明，README 与页面上的“参数说明”弹层共用一份 */
export const PARAM_DOC = [
  { key: 'path', desc: '视图由路径决定：/ 地图，/list 列表（旧的 ?view=list 仍可用）', example: '/list' },
  { key: 'district', desc: '城区，可用简称，多选逗号分隔', example: '东城区' },
  { key: 'street', desc: '街道，可省略“街道/地区/镇”', example: '东华门街道' },
  { key: 'metric', desc: '地图着色指标：count / rate / feeAvg', example: 'rate' },
  { key: 'regime', desc: '治理状态，多选逗号分隔', example: '未成立' },
  { key: 'fee', desc: '物业费区间（元/㎡·月），区间或单边', example: '1-3' },
  { key: 'kw', desc: '关键词，匹配小区名/街道/物业公司', example: '东华门' },
  { key: 'band', desc: '列表页自治率区间：low(<30%) / mid / high(≥60%)', example: 'low' },
  { key: 'level', desc: '列表层级：street 按街道汇总 / project 按小区铺开', example: 'project' },
  { key: 'sort', desc: '列表排序，字段:方向', example: 'rate:asc' },
  { key: 'psort', desc: '展开街道后小区表的排序，字段:方向（name/regime/fee/year/feeMode/company）', example: 'fee:desc' },
  { key: 'size', desc: '每页条数：10 / 20 / 50 / 100 / 1000，默认 10', example: '50' },
  { key: 'page', desc: '页码，从 1 开始，默认 1', example: '2' },
]
