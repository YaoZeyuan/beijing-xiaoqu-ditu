/** 住宅物业费上限，与 web/build_data.py 的 FEE_VALID_MAX 保持一致 */
export const FEE_VALID_MAX = 20

/**
 * 物业费的展示口径
 *
 * 一个项目在住建委可能按「业态-房屋性质-建筑类型」分档登记，比如富贵园：
 *   普通商品房 · 多层有电梯 2.58 / 回迁房 · 高层 1.00 / 回迁房 · 多层有电梯 1.00
 * 任何单一数字都会误导人，所以：
 *   · 单档 → 直接显示该单价
 *   · 多档 → 显示区间，并提示可以展开看构成
 * 主值 fee 仍保留（排序、着色、均价统计要用），但不再作为列表里的唯一显示。
 */

/** 该档位是否参与区间计算 */
export function tierIsLive(f) {
  return f.kind === '居住类' && typeof f.price === 'number'
    && f.price > 0 && f.price <= FEE_VALID_MAX
}

/** 该档位是否存疑（未填 0、超上限、或高得离谱） */
export function tierIsOdd(f) {
  if (typeof f.price !== 'number') return true
  return f.price <= 0 || f.price > FEE_VALID_MAX || f.price > 10
}

/** 给一行小区算出展示用的物业费结构 */
export function feeView(p) {
  const items = p.fees || []
  const lo = p.feeMin
  const hi = p.feeMax
  const tiers = p.feeTiers || 0

  // 有有效住宅档：多档但价格全相同（橡林郡三档都是 4.98）仍然是单值，
  // 别掉到下面「没有住宅价」的分支里去。
  if (tiers >= 1 && lo !== null && hi !== null) {
    if (lo === hi) return { kind: 'single', value: lo, tiers, main: p.fee, items }
    return { kind: 'range', lo, hi, tiers, main: p.fee, items }
  }

  // 没有任何有效住宅档，但登记过：要分清是「真非住宅」还是「登记了但不可用」
  if (items.length) {
    const resi = items.filter((f) => f.kind === '居住类' && typeof f.price === 'number')
    // 价格超出有效上限：别墅/高档公寓可能是真值，也可能是笔误，主值照实显示并标红
    if (resi.some((f) => f.price > FEE_VALID_MAX)) {
      const v = p.fee !== null && p.fee !== undefined
        ? p.fee
        : Math.max(...resi.map((f) => f.price))
      return { kind: 'high', value: v, tiers, main: p.fee, items }
    }
    // 居住类价格全是 0：多为未填报占位，不能说成非住宅
    if (resi.length) return { kind: 'zero', tiers, main: p.fee, items }
    // 综合类（住宅 + 商业混合业态）
    if (items.some((f) => f.kind === '综合类')) {
      return { kind: 'mixed', tiers, main: p.fee, items }
    }
    return { kind: 'other', tiers, main: p.fee, items }
  }

  if (p.fee !== null && p.fee !== undefined) {
    return { kind: 'single', value: p.fee, tiers: 1, main: p.fee, items: [] }
  }
  return { kind: 'none', tiers: 0, main: null, items: [] }
}

export function fmtPrice(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toFixed(2)
}
