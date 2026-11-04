<template>
  <span
    class="fee-cell"
    :class="{ clk: clickable, suspect: isSuspect }"
    :title="tip"
    @click="onClick"
  >
    <template v-if="view.kind === 'range'">
      <span class="lo">{{ fmtPrice(view.lo) }}</span>
      <span class="dash">–</span>
      <span class="hi">{{ fmtPrice(view.hi) }}</span>
      <span class="tiers">{{ view.tiers }}档</span>
    </template>
    <template v-else-if="view.kind === 'single'">
      <span :class="{ bad: isSuspect }">{{ fmtPrice(view.value) }}</span>
      <span v-if="view.tiers >= 2" class="tiers">{{ view.tiers }}档</span>
    </template>
    <template v-else-if="view.kind === 'high'">
      <span class="bad">{{ fmtPrice(view.value) }}</span>
      <span class="tiers">超限</span>
    </template>
    <template v-else-if="view.kind === 'zero'">
      <span class="other">未填</span>
    </template>
    <template v-else-if="view.kind === 'mixed'">
      <span class="other">综合类</span>
    </template>
    <template v-else-if="view.kind === 'other'">
      <span class="other">非住宅</span>
    </template>
    <span v-else class="na">—</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { feeView, fmtPrice, FEE_VALID_MAX } from '../utils/fee'
import { openDetail } from '../utils/detailStore'

const props = defineProps({
  project: { type: Object, required: true },
})

const view = computed(() => feeView(props.project))

// 多档、或登记里有需要解释的档位时，可以点开看构成
const clickable = computed(() => view.value.items.length > 0)

const isSuspect = computed(() => props.project.fee && !props.project.feeOk)

const tip = computed(() => {
  const v = view.value
  if (v.kind === 'range') {
    return `该小区登记了 ${v.tiers} 档住宅物业费，单价 ${fmtPrice(v.lo)}–${fmtPrice(v.hi)} 元/㎡·月\n点击查看各档对应的房屋性质与建筑类型`
  }
  if (v.kind === 'single' && v.tiers >= 2) {
    return `该小区登记了 ${v.tiers} 档住宅物业费，单价均为 ${fmtPrice(v.value)} 元/㎡·月\n点击查看各档对应的房屋性质与建筑类型`
  }
  if (v.kind === 'high') {
    return `申报单价 ${fmtPrice(v.value)} 元/㎡·月，超过 ${FEE_VALID_MAX} 元的上限，不计入均价统计\n可能是特殊物业或录入笔误，点击查看明细`
  }
  if (v.kind === 'zero') return '住建委登记为 0 元/㎡·月（多为未填报占位），不计入均价统计，点击查看明细'
  if (v.kind === 'mixed') return '登记的是综合类业态（住宅与商业混合），未单独标注住宅单价，点击查看明细'
  if (v.kind === 'other') return '登记的都是非居住类业态（商业/写字楼等），点击查看明细'
  if (v.kind === 'none') return '住建委未登记物业费标准'
  if (isSuspect.value) return '申报值异常（>20 元/㎡·月），不计入均价统计，点击查看明细'
  return v.items.length ? '点击查看物业费构成' : ''
})

function onClick() {
  if (clickable.value) openDetail(props.project)
}
</script>

<style scoped>
.fee-cell {
  display: inline-flex;
  align-items: baseline;
  gap: 1px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.fee-cell.clk {
  cursor: pointer;
  border-bottom: 1px dashed rgba(76, 154, 255, 0.45);
  padding-bottom: 1px;
}
.fee-cell.clk:hover { border-bottom-color: var(--accent); color: #cfe3ff; }
.lo { opacity: 0.85; }
.dash { opacity: 0.45; margin: 0 1px; }
.hi { font-weight: 600; }
.tiers {
  font-size: 9px;
  color: var(--text-faint);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0 2px;
  margin-left: 3px;
  line-height: 1.5;
  font-variant-numeric: normal;
}
.other { font-size: 10.5px; color: var(--text-faint); }
.na { color: #3d4a60; }
.bad { color: #f87171; }
.suspect { color: #f87171; }
</style>
