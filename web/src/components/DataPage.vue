<template>
  <div class="dp">
    <!-- ── 概述 ── -->
    <section class="dp-hero">
      <div class="hero-txt">
        <h2>数据下载</h2>
        <p>
          这套数据把北京市住建委的<b>住宅小区备案信息</b>和链家的<b>开源小区库</b>对齐了。
          备案有物业费、物业公司、收费方式、业委会状态，但没有户数；链家有户数、楼栋数、经纬度，
          但没有治理信息。两边的小区名还经常对不上——备案记「今家园」，链家叫「宣海家园」。
        </p>
        <p>
          全部文件都以 <b>CSV 和 JSON 双份</b>提供，已脱敏，许可为 CC BY 4.0，注明来源即可自由使用。
        </p>
        <p class="hero-note">
          本站地图上展示的是其中能定位到城区 / 街道的小区，本页给的是备案系统的<b>全量</b>记录，
          包括少数区划信息缺失的项目。
        </p>
      </div>
      <div v-if="meta" class="hero-stats">
        <div class="hs">
          <span class="hs-v">{{ n(meta.stats.备案项目) }}</span>
          <span class="hs-l">备案项目</span>
        </div>
        <div class="hs">
          <span class="hs-v accent">{{ n(meta.stats.已匹配) }}</span>
          <span class="hs-l">已匹配 {{ meta.stats.匹配率 }}%</span>
        </div>
        <div class="hs">
          <span class="hs-v">{{ n(meta.stats.去重小区) }}</span>
          <span class="hs-l">去重小区</span>
        </div>
        <div class="hs">
          <span class="hs-v">{{ n(meta.stats.未匹配) }}</span>
          <span class="hs-l">未匹配</span>
        </div>
      </div>
    </section>

    <div v-if="!ds" class="dp-loading">正在读取数据清单…</div>

    <template v-else>
      <!-- ── 文件分组 ── -->
      <section v-for="g in ds.groups" :key="g.key" class="dp-group">
        <div class="dg-head">
          <span class="dg-tag" :class="g.key">{{ g.key }}</span>
          <h3>{{ g.title }}</h3>
          <span class="dg-desc">{{ g.desc }}</span>
        </div>

        <div class="dg-grid">
          <article v-for="it in g.items" :key="it.name" class="card">
            <div class="c-top">
              <code class="c-path">{{ g.key }}/{{ it.name }}</code>
              <span class="c-size">{{ it.csvSize }} / {{ it.jsonSize }}</span>
            </div>
            <h4>{{ it.title }}</h4>
            <p class="c-desc">{{ it.desc }}</p>
            <div class="c-meta">
              <span><b>{{ n(it.rows) }}</b> 行</span>
              <span><b>{{ it.fields }}</b> 字段</span>
            </div>
            <div class="c-actions">
              <a class="dl" :href="url(it.csv)" target="_blank" rel="noopener">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 19h16" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                CSV
              </a>
              <a class="dl ghost" :href="url(it.json)" target="_blank" rel="noopener">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 19h16" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                JSON
              </a>
            </div>
          </article>
        </div>
      </section>

      <!-- ── 用法 ── -->
      <section class="dp-usage">
        <h3>怎么用</h3>
        <div class="usage-grid">
          <div class="u-block">
            <div class="u-label">做统计 → 用 <code>processed/xiaoqu</code></div>
            <pre class="code"><code>import pandas as pd

df = pd.read_csv(
    'processed/xiaoqu.csv',
    encoding='utf-8-sig',
)

# 先过滤掉登记残缺的记录，否则成立率会被压低一半
ok = df[
    (df['备案登记完整'] == '是')
    &amp; (df['是否住宅'] == '是')
]

print(ok['业委会状态'].value_counts(normalize=True))</code></pre>
            <button class="copy" @click="copyCode">
              {{ copied ? '已复制' : '复制代码' }}
            </button>
          </div>

          <div class="u-side">
            <div class="u-tip">
              <span class="tip-k">想自己重跑匹配</span>
              <p>用 <code>raw/</code> 下三份数据即可。<code>processed/matched</code> 里记了每条匹配用的是哪个规则，可以对照复核。</p>
            </div>
            <div class="u-tip">
              <span class="tip-k">想看某个小区为什么这么对</span>
              <p>在 <code>processed/matched</code> 里按 <code>project_no</code> 搜，看 <code>匹配方式</code> 与 <code>置信度</code>。</p>
            </div>
            <div class="u-tip">
              <span class="tip-k">CSV 编码</span>
              <p>全部 UTF-8 BOM，Excel 双击打开不乱码；pandas 用 <code>encoding='utf-8-sig'</code>。</p>
            </div>
            <div class="u-tip">
              <span class="tip-k">JSON 结构</span>
              <p><code>{ meta, count, data }</code>，<code>data</code> 是对象数组，<code>meta</code> 里带每个字段的说明。</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ── 口径 ── -->
      <section class="dp-caveat">
        <h3>引用数字前请先看这四条</h3>
        <ol>
          <li>
            <b>先过滤 <code>备案登记完整 = 是</code></b>
            备案库里有 19% 的记录只填了项目名、区、街道和收费方式，地址、物业公司、物业费明细全空，
            业委会状态清一色「均未成立」。这批残缺记录 <b>75% 集中在酬金制上</b>（包干制只有 3%）。
            不过滤会得出「酬金制小区几乎不成立业委会」的假结论——过滤后两者没有差异。
          </li>
          <li>
            <b>户数是链家 2019 年登记值，不是官方统计</b>
            已与 2018 版交叉核对，92% 完全一致；个别小区是单栋空壳条目（&lt;6 户）。
          </li>
          <li>
            <b><code>链家为聚合页 = 是</code> 的户数是合计值</b>
            链家把多个院落合成一条展示时，户数是整片街区的合计。做户数分析务必用
            <code>xiaoqu</code> 这张去重后的表，不要用 <code>matched</code>。
          </li>
          <li>
            <b>剔除非住宅</b>
            <code>是否住宅 = 否</code> 的是写字楼、商场，做住宅分析要排除。
          </li>
        </ol>

        <div v-if="meta" class="sample">
          <div class="s-head">按上面四条口径，只看登记完整的住宅小区</div>
          <div class="s-row">
            <div class="s-item">
              <span class="s-v">{{ n(meta.regime.样本) }}</span>
              <span class="s-l">样本小区</span>
            </div>
            <div class="s-item">
              <span class="s-v green">{{ meta.regime.业委会率 }}%</span>
              <span class="s-l">业委会 {{ n(meta.regime.业委会) }}</span>
            </div>
            <div class="s-item">
              <span class="s-v orange">{{ meta.regime.物管会率 }}%</span>
              <span class="s-l">物管会 {{ n(meta.regime.物管会) }}</span>
            </div>
            <div class="s-item">
              <span class="s-v red">{{ (100 - meta.regime.业委会率 - meta.regime.物管会率).toFixed(1) }}%</span>
              <span class="s-l">均未成立 {{ n(meta.regime.均未成立) }}</span>
            </div>
          </div>
          <div class="s-foot">数字随数据更新变化，正式引用前请自己重算。</div>
        </div>
      </section>

      <!-- ── 底部操作 ── -->
      <section class="dp-foot">
        <a class="fbtn" :href="ds.meta.browseBase" target="_blank" rel="noopener">
          <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">
            <path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/>
          </svg>
          在 GitHub 查看完整数据集
        </a>
        <a class="fbtn ghost" :href="url('dictionary.csv')" target="_blank" rel="noopener">
          字段字典 dictionary.csv
        </a>
        <a class="fbtn ghost" :href="url('manifest.json')" target="_blank" rel="noopener">
          数据清单 manifest.json
        </a>
        <span class="f-note">
          CC BY 4.0 · 更新于 {{ ds.meta.generated }} · 数据来自北京市住建委公开页面与链家开源小区库
        </span>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const ds = ref(null)
const copied = ref(false)
const meta = computed(() => ds.value?.meta || null)

function n(v) {
  return (v ?? 0).toLocaleString()
}

// raw.githubusercontent.com 直连，点开即下载/预览
function url(p) {
  const base = ds.value?.meta?.rawBase || ''
  return base + p
}

const SAMPLE = `import pandas as pd

df = pd.read_csv(
    'processed/xiaoqu.csv',
    encoding='utf-8-sig',
)

# 先过滤掉登记残缺的记录，否则成立率会被压低一半
ok = df[
    (df['备案登记完整'] == '是')
    & (df['是否住宅'] == '是')
]

print(ok['业委会状态'].value_counts(normalize=True))`

async function copyCode() {
  try {
    await navigator.clipboard.writeText(SAMPLE)
  } catch (e) {
    return
  }
  copied.value = true
  setTimeout(() => { copied.value = false }, 1600)
}

onMounted(async () => {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data/dataset.json`)
    ds.value = await res.json()
  } catch (e) {
    console.error('dataset.json 加载失败', e)
  }
})
</script>

<style scoped>
.dp {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: 20px;
}

/* ── hero ── */
.dp-hero {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  flex-wrap: wrap;
  background: var(--panel);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 18px 22px;
}
.hero-txt { flex: 1; min-width: 340px; }
.hero-txt h2 { font-size: 17px; font-weight: 650; margin-bottom: 6px; }
.hero-txt p {
  font-size: 12.5px;
  color: var(--text-dim);
  line-height: 1.75;
  margin-top: 4px;
}
.hero-txt b { color: #c3d8f0; font-weight: 600; }
.hero-note { color: var(--text-faint) !important; font-size: 11.5px !important; }

.hero-stats { display: flex; gap: 26px; flex-wrap: wrap; padding-top: 4px; }
.hs { display: flex; flex-direction: column; gap: 1px; }
.hs-v {
  font-size: 21px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.4px;
}
.hs-v.accent { color: var(--accent); }
.hs-l { font-size: 10.5px; color: var(--text-faint); }

.dp-loading { font-size: 12.5px; color: var(--text-faint); padding: 20px 4px; }

/* ── group ── */
.dp-group { display: flex; flex-direction: column; gap: 10px; }
.dg-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.dg-tag {
  font-size: 10px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  padding: 1px 7px;
  border-radius: 5px;
  border: 1px solid var(--border);
  color: var(--text-faint);
}
.dg-tag.raw { border-color: rgba(124, 92, 255, 0.4); color: #a691ff; }
.dg-tag.processed { border-color: rgba(76, 154, 255, 0.4); color: #7fb6ff; }
.dg-head h3 { font-size: 14px; font-weight: 600; }
.dg-desc { font-size: 11.5px; color: var(--text-faint); }

.dg-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.card {
  background: var(--panel);
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  padding: 13px 15px 12px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  transition: border-color 0.15s;
}
.card:hover { border-color: #2b3a5a; }
.c-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.c-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10.5px;
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.c-size {
  font-size: 10px;
  color: #45536e;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.card h4 { font-size: 13px; font-weight: 600; margin-top: 1px; }
.c-desc { font-size: 11.5px; color: var(--text-dim); line-height: 1.6; flex: 1; }
.c-meta { display: flex; gap: 12px; font-size: 10.5px; color: var(--text-faint); }
.c-meta b { color: var(--text); font-weight: 600; font-variant-numeric: tabular-nums; }

.c-actions { display: flex; gap: 7px; margin-top: 6px; }
.dl {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 5px 0;
  border-radius: 8px;
  border: 1px solid rgba(76, 154, 255, 0.45);
  background: rgba(76, 154, 255, 0.13);
  color: #9cc7ff;
  font-size: 11.5px;
  text-decoration: none;
  transition: all 0.15s;
}
.dl:hover { background: rgba(76, 154, 255, 0.24); border-color: var(--accent); color: #cfe3ff; }
.dl.ghost {
  border-color: var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
}
.dl.ghost:hover { border-color: #3a4a6b; color: var(--text); background: var(--panel-3); }
.dl svg { display: block; }

/* ── usage ── */
.dp-usage, .dp-caveat {
  background: var(--panel);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 16px 20px 18px;
}
.dp-usage h3, .dp-caveat h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}
.usage-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 20px;
}
.u-block { position: relative; }
.u-label { font-size: 11.5px; color: var(--text-faint); margin-bottom: 7px; }
.u-label code, .u-side code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  color: #9cc7ff;
  background: rgba(76, 154, 255, 0.1);
  padding: 1px 4px;
  border-radius: 4px;
}
.code {
  background: #0c1220;
  border: 1px solid #1b2436;
  border-radius: 10px;
  padding: 12px 14px;
  overflow-x: auto;
  font-size: 11.5px;
  line-height: 1.75;
}
.code code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #b9c7dd;
  white-space: pre;
}
.copy {
  position: absolute;
  top: 4px;
  right: 0;
  font-size: 10.5px;
  font-family: inherit;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text-faint);
  cursor: pointer;
}
.copy:hover { border-color: var(--accent); color: #cfe3ff; }

.u-side { display: flex; flex-direction: column; gap: 11px; }
.u-tip { display: flex; flex-direction: column; gap: 2px; }
.tip-k { font-size: 11.5px; color: #c3d8f0; font-weight: 600; }
.u-tip p { font-size: 11.5px; color: var(--text-dim); line-height: 1.65; }

/* ── caveat ── */
.dp-caveat ol {
  list-style: none;
  counter-reset: cv;
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.dp-caveat li {
  counter-increment: cv;
  position: relative;
  padding-left: 26px;
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.75;
}
.dp-caveat li::before {
  content: counter(cv);
  position: absolute;
  left: 0;
  top: 2px;
  width: 17px;
  height: 17px;
  display: grid;
  place-items: center;
  border-radius: 5px;
  background: rgba(245, 158, 11, 0.14);
  border: 1px solid rgba(245, 158, 11, 0.32);
  color: #fbbf24;
  font-size: 10px;
  font-weight: 700;
}
.dp-caveat li b { color: #dbe6f7; font-weight: 600; }
.dp-caveat code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  color: #9cc7ff;
  background: rgba(76, 154, 255, 0.1);
  padding: 1px 4px;
  border-radius: 4px;
}

.sample {
  margin-top: 14px;
  border-top: 1px solid var(--border-soft);
  padding-top: 12px;
}
.s-head { font-size: 11.5px; color: var(--text-faint); margin-bottom: 9px; }
.s-row { display: flex; gap: 34px; flex-wrap: wrap; }
.s-item { display: flex; flex-direction: column; }
.s-v {
  font-size: 19px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.3px;
}
.s-v.green { color: var(--green); }
.s-v.orange { color: var(--orange); }
.s-v.red { color: var(--red); }
.s-l { font-size: 10.5px; color: var(--text-faint); }
.s-foot { font-size: 10.5px; color: #45536e; margin-top: 8px; }

/* ── foot ── */
.dp-foot { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.fbtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  padding: 6px 13px;
  border-radius: 8px;
  border: 1px solid rgba(46, 164, 79, 0.5);
  background: rgba(31, 136, 61, 0.16);
  color: #6fd99b;
  text-decoration: none;
  transition: all 0.15s;
}
.fbtn:hover { background: rgba(31, 136, 61, 0.28); color: #8ceab0; }
.fbtn.ghost {
  border-color: var(--border);
  background: var(--panel);
  color: var(--text-dim);
}
.fbtn.ghost:hover { border-color: var(--accent); color: #cfe3ff; }
.f-note { font-size: 10.5px; color: #3d4a60; }

@media (max-width: 1180px) {
  .dg-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .usage-grid { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .dg-grid { grid-template-columns: minmax(0, 1fr); }
  .hero-txt { min-width: 0; width: 100%; }
  .hero-stats { gap: 18px 22px; width: 100%; }
  .hs { flex: 0 0 calc(50% - 11px); }
  .dp-hero { padding: 15px 16px; }
  .dp-usage, .dp-caveat { padding: 14px 15px 16px; }
  .c-size { display: none; }
}
</style>
