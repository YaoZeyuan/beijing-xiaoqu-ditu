<template>
  <Teleport to="body">
    <Transition name="pm">
      <div v-if="project" class="pm-mask" @click.self="close">
        <div class="pm-card" role="dialog" aria-modal="true">
          <header class="pm-head">
            <div class="pm-title-wrap">
              <h2 class="pm-name">{{ project.name }}</h2>
              <div class="pm-loc">
                {{ project.district }}
                <span class="sep">·</span>
                {{ project.street === '未标注街道' ? '街道未标注' : project.street }}
              </div>
            </div>
            <button class="pm-x" title="关闭（Esc）" @click="close">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12" stroke-linecap="round" />
              </svg>
            </button>
          </header>

          <div class="pm-body">
            <!-- ── 基本信息 ── -->
            <section class="pm-sec">
              <div class="pm-sec-h">基本信息</div>
              <dl class="pm-grid">
                <div class="kv">
                  <dt>治理状态</dt>
                  <dd><span class="regime-tag" :style="regimeStyle(project.regime)">{{ project.regime }}</span></dd>
                </div>
                <div class="kv">
                  <dt>计费方式</dt>
                  <dd>{{ project.feeMode || '—' }}</dd>
                </div>
                <div class="kv">
                  <dt>建成年代</dt>
                  <dd>{{ project.year || '—' }}</dd>
                </div>
                <div class="kv">
                  <dt>{{ hhLabel }}</dt>
                  <dd>
                    <template v-if="project.hh">{{ project.hh.toLocaleString() }} 户</template>
                    <template v-else>—</template>
                    <span v-if="project.hh && project.hhSrc" class="src-tag" :title="hhSrcTip">
                      {{ project.hhSrc }}
                    </span>
                    <span v-if="project.hh && project.hhScope" class="scope-tag" :title="hhScopeTip">
                      {{ project.hhScope }}
                    </span>
                  </dd>
                </div>
                <div class="kv">
                  <dt>挂牌参考价</dt>
                  <dd>
                    <template v-if="project.price">{{ project.price.toLocaleString() }} 元/㎡</template>
                    <template v-else>—</template>
                    <span v-if="project.price" class="src-tag" :title="priceSrcTip">{{ project.priceSrc }}</span>
                  </dd>
                </div>
                <div class="kv">
                  <dt>业委会/物管会人数</dt>
                  <dd>{{ project.committeeSize || '—' }}</dd>
                </div>
                <div class="kv wide">
                  <dt>物业服务企业</dt>
                  <dd>{{ project.company || '未登记' }}</dd>
                </div>
              </dl>
            </section>

            <!-- ── 物业费 ── -->
            <section class="pm-sec">
              <div class="pm-sec-h">
                物业费构成
                <span class="pm-sec-sub">元 / ㎡ · 月</span>
              </div>

              <template v-if="items.length">
                <div v-if="kind === 'range'" class="pm-note">
                  该小区按房屋性质 / 建筑类型分 <b>{{ live.length }}</b> 档登记，单价
                  <b>{{ fmtPrice(lo) }} – {{ fmtPrice(hi) }}</b> 元/㎡·月。
                  列表里给出的就是这个区间；排序和均价统计用的是
                  <b>{{ fmtPrice(project.fee) }}</b>（主力户型所在建筑类型组的中位数）。
                  <span class="warn">不同楼栋实际收费不同，请按下表对照自己所属的房屋性质。</span>
                </div>
                <div v-else-if="kind === 'single'" class="pm-note">
                  <template v-if="live.length > 1">
                    该小区登记了 <b>{{ live.length }}</b> 档住宅物业费，单价均为
                    <b>{{ fmtPrice(lo) }}</b> 元/㎡·月——不同房屋性质 / 建筑类型之间没有差价。
                  </template>
                  <template v-else>
                    仅登记一档住宅物业费：<b>{{ fmtPrice(lo) }}</b> 元/㎡·月。
                  </template>
                </div>
                <div v-else-if="kind === 'high'" class="pm-note">
                  登记的住宅单价为 <b>{{ fmtPrice(lo) }}</b> 元/㎡·月，高于 {{ FEE_VALID_MAX }} 元的上限，
                  <span class="warn">未计入区间与均价统计</span>，可能是特殊物业或录入有误。
                </div>
                <div v-else-if="kind === 'zero'" class="pm-note">
                  住建委登记的单价为 <b>0 元</b>，多为未填报的占位值，
                  <span class="warn">无法确定实际收费标准</span>。下表仅作原始登记留档。
                </div>
                <div v-else-if="kind === 'mixed'" class="pm-note">
                  登记的是<b>综合类</b>业态（住宅与商业混合），未单独标注住宅单价。
                  下表仅作原始登记留档。
                </div>
                <div v-else class="pm-note">
                  登记的都是<b>非居住类</b>业态（商业 / 写字楼等），没有住宅物业费可比。
                  下表仅作原始登记留档。
                </div>

                <div class="pm-tbl-wrap">
                  <table class="pm-tbl">
                    <thead>
                      <tr>
                        <th>业态</th>
                        <th>房屋性质</th>
                        <th>建筑类型</th>
                        <th class="r">单价</th>
                        <th class="r">对照</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(f, i) in sortedItems" :key="i" :class="{ ghost: !isLive(f), odd: isOdd(f) }">
                        <td>{{ f.kind }}</td>
                        <td class="prop">{{ f.prop }}</td>
                        <td>{{ f.build }}</td>
                        <td class="r strong">{{ fmtPrice(f.price) }}</td>
                        <td class="r">
                          <span v-if="f.kind !== '居住类'" class="flag grey">非住宅</span>
                          <span v-else-if="f.price === 0" class="flag grey">疑未填</span>
                          <span v-else-if="f.price > 10" class="flag red">偏高</span>
                          <span v-else class="flag ok">有效</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p class="pm-fine">
                  0 元多为未填报占位、20 元以上多为录入笔误，均不计入区间与均价统计；本次共
                  {{ items.length }} 档，其中有效 {{ live.length }} 档。
                </p>
              </template>

              <div v-else-if="project.fee !== null && project.fee !== undefined" class="pm-note">
                住建委只登记了一个总价：<b>{{ fmtPrice(project.fee) }}</b> 元/㎡·月，未按房屋性质分档。
              </div>
              <div v-else class="pm-note dim">
                住建委未登记该小区的物业费标准。
              </div>
            </section>
          </div>

          <footer class="pm-foot">
            <span class="pm-src">数据来源：北京市住建委物业项目信息查询</span>
            <div class="pm-acts">
              <button class="pm-btn ghost" @click="close">关闭</button>
              <GovLink v-if="project.id" :id="project.id" :name="project.name" text="政府原页面" />
              <span v-else class="pm-noid">该项目无项目编号，无法直达官方页面</span>
            </div>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { detailProject, closeDetail } from '../utils/detailStore'
import { feeView, fmtPrice, tierIsLive, tierIsOdd, FEE_VALID_MAX } from '../utils/fee'
import GovLink from './GovLink.vue'

const project = computed(() => detailProject.value)
const close = closeDetail

// 户数/挂牌价来源说明（链家=开源小区库匹配，AI=互联网公开页补查）
const SRC_TIP = {
  链家: '链家开源小区库（2018/2019 快照）与备案一对一匹配得到',
  AI: '互联网公开页（百科/房产平台/政府网站）补查，详情见数据下载页 beian_master 备注列',
}
// 「整小区合计·分区未拆」不是这条备案自己的户数，标题也要改，否则会被当成该分区户数
const hhLabel = computed(() => (project.value?.hhScope === '整小区合计·分区未拆'
  ? '所在小区户数' : '户数'))
const hhScopeTip = computed(() => (project.value?.hhScope === '整小区合计·分区未拆'
  ? '这条备案只是该小区的一个分区/楼栋，查不到分区独立户数，这里给的是整个小区的合计'
  : project.value?.hhScope || ''))
const hhSrcTip = computed(() => SRC_TIP[project.value?.hhSrc] || '')
const priceSrcTip = computed(() => SRC_TIP[project.value?.priceSrc] || '')

const view = computed(() => (project.value ? feeView(project.value) : null))
const items = computed(() => view.value?.items || [])
const live = computed(() => items.value.filter(tierIsLive))
const lo = computed(() => view.value?.lo ?? view.value?.value ?? null)
const hi = computed(() => view.value?.hi ?? view.value?.value ?? null)
const kind = computed(() => view.value?.kind || 'none')

function isLive(f) { return tierIsLive(f) }
function isOdd(f) { return tierIsOdd(f) }

// 按房屋性质 → 建筑类型排序，方便对照自己的房本
const sortedItems = computed(() => {
  const order = ['普通商品房', '房改房', '央产房', '回迁房', '保障房', '自管公房', '直管公房', '别墅', '其他']
  const rank = (p) => {
    const i = order.indexOf(p)
    return i < 0 ? order.length : i
  }
  return [...items.value].sort((a, b) =>
    rank(a.prop) - rank(b.prop)
    || String(a.build).localeCompare(String(b.build), 'zh-Hans-CN')
    || (b.price ?? 0) - (a.price ?? 0))
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

function onKey(e) {
  if (e.key === 'Escape' && project.value) close()
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.pm-mask {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: rgba(4, 7, 13, 0.72);
  backdrop-filter: blur(3px);
  display: grid;
  place-items: center;
  padding: 24px;
}
.pm-card {
  width: min(720px, 100%);
  max-height: min(84vh, 760px);
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.6);
  overflow: hidden;
}

.pm-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--border-soft);
}
.pm-name { font-size: 16px; font-weight: 650; letter-spacing: 0.2px; line-height: 1.4; }
.pm-loc { font-size: 11.5px; color: var(--text-faint); margin-top: 2px; }
.pm-loc .sep { margin: 0 3px; opacity: 0.6; }
.pm-x {
  flex-shrink: 0;
  width: 28px; height: 28px;
  display: grid; place-items: center;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.14s;
}
.pm-x:hover { color: var(--text); border-color: #3a4a6b; }

.pm-body { overflow-y: auto; padding: 4px 18px 18px; }

.pm-sec { padding-top: 14px; }
.pm-sec-h {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  padding-bottom: 8px;
  display: flex;
  align-items: baseline;
  gap: 7px;
}
.pm-sec-sub { font-size: 10.5px; font-weight: 400; color: var(--text-faint); }

.pm-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border-soft);
  border: 1px solid var(--border-soft);
  border-radius: 9px;
  overflow: hidden;
}
.kv { background: var(--panel-2); padding: 8px 11px; display: flex; gap: 10px; align-items: baseline; }
.kv.wide { grid-column: 1 / -1; }
.kv dt { font-size: 10.5px; color: var(--text-faint); flex-shrink: 0; min-width: 78px; }
.kv dd { font-size: 12px; color: var(--text); }

.scope-tag {
  display: inline-block;
  margin-left: 4px;
  font-size: 10.5px;
  padding: 0 5px;
  border-radius: 4px;
  background: rgba(139, 92, 246, 0.16);
  color: #a78bfa;
  border: 1px solid rgba(139, 92, 246, 0.35);
  line-height: 1.6;
}

.regime-tag {
  display: inline-block;
  font-size: 10.5px;
  padding: 0 6px;
  border-radius: 4px;
  border: 1px solid transparent;
  line-height: 1.6;
}

/* 户数/挂牌价来源标签：链家=蓝，AI=紫 */
.src-tag {
  display: inline-block;
  margin-left: 5px;
  font-size: 9.5px;
  padding: 0 4px;
  border-radius: 3px;
  line-height: 1.5;
  color: #9cccff;
  background: rgba(76, 154, 255, 0.1);
  border: 1px solid rgba(76, 154, 255, 0.25);
  vertical-align: 1px;
  cursor: help;
}
.src-tag[title*='互联网'] {
  color: #c4b5fd;
  background: rgba(139, 92, 246, 0.1);
  border-color: rgba(139, 92, 246, 0.28);
}

.pm-note {
  font-size: 11.5px;
  line-height: 1.75;
  color: var(--text-dim);
  background: var(--panel-2);
  border: 1px solid var(--border-soft);
  border-left: 2px solid rgba(76, 154, 255, 0.55);
  border-radius: 7px;
  padding: 8px 11px;
  margin-bottom: 9px;
}
.pm-note b { color: var(--text); }
.pm-note .warn { color: #fbbf24; }
.pm-note.dim { border-left-color: var(--border); color: var(--text-faint); }

.pm-tbl-wrap {
  border: 1px solid var(--border-soft);
  border-radius: 9px;
  overflow: auto;
  max-height: 260px;
}
.pm-tbl { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.pm-tbl thead th {
  position: sticky; top: 0;
  background: var(--panel-3);
  color: var(--text-faint);
  font-weight: 500;
  font-size: 10.5px;
  text-align: left;
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.pm-tbl th.r, .pm-tbl td.r { text-align: right; font-variant-numeric: tabular-nums; }
.pm-tbl td {
  padding: 6px 10px;
  border-bottom: 1px solid #161f31;
  color: var(--text-dim);
  white-space: nowrap;
}
.pm-tbl tbody tr:last-child td { border-bottom: none; }
.pm-tbl .prop { color: var(--text); }
.pm-tbl .strong { color: var(--text); font-weight: 600; }
.pm-tbl tr.ghost td { opacity: 0.42; }
.pm-tbl tr.odd td.strong { color: #f87171; }

.flag {
  font-size: 9.5px;
  padding: 0 5px;
  border-radius: 3px;
  border: 1px solid transparent;
  line-height: 1.55;
  display: inline-block;
}
.flag.ok { color: #4ade80; background: rgba(34, 197, 94, 0.1); border-color: rgba(34, 197, 94, 0.25); }
.flag.grey { color: var(--text-faint); background: rgba(139, 152, 178, 0.08); border-color: var(--border); }
.flag.red { color: #f87171; background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.28); }

.pm-fine {
  font-size: 10.5px;
  color: #4a5670;
  line-height: 1.7;
  margin-top: 7px;
}

.pm-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 18px;
  border-top: 1px solid var(--border-soft);
  background: var(--panel-2);
  flex-wrap: wrap;
}
.pm-src { font-size: 10.5px; color: #4a5670; }
.pm-noid { font-size: 10.5px; color: var(--text-faint); }
.pm-acts { display: flex; align-items: center; gap: 8px; }
.pm-btn {
  font-size: 11.5px;
  font-family: inherit;
  padding: 6px 13px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.14s;
  line-height: 1.5;
}
.pm-btn.ghost:hover { color: var(--text); border-color: #3a4a6b; }
/* 主按钮是子组件 GovLink，用 :deep 穿透它的 scoped 样式 */
.pm-acts :deep(.gov-link) {
  font-size: 11.5px;
  padding: 6px 13px;
  border-radius: 7px;
  border-color: rgba(76, 154, 255, 0.5);
  background: rgba(76, 154, 255, 0.12);
  color: #9cc6ff;
  gap: 5px;
}
.pm-acts :deep(.gov-link:hover) { background: rgba(76, 154, 255, 0.22); color: #cfe3ff; }
.pm-acts :deep(.gl-text) { font-size: 11.5px; }

.pm-enter-active, .pm-leave-active { transition: opacity 0.16s ease; }
.pm-enter-from, .pm-leave-to { opacity: 0; }
.pm-enter-active .pm-card, .pm-leave-active .pm-card { transition: transform 0.18s ease; }
.pm-enter-from .pm-card, .pm-leave-to .pm-card { transform: translateY(8px) scale(0.99); }

@media (max-width: 640px) {
  .pm-mask { padding: 12px; }
  .pm-grid { grid-template-columns: 1fr; }
  .pm-card { max-height: 90vh; }
}
</style>
