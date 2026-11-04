import { ref } from 'vue'

/**
 * 小区详情弹窗的全局状态
 *
 * 表格组件分散在三处（地图页名录 / 街道列表展开行 / 小区明细页），弹窗只在
 * App 里渲染一份。用一个模块级的 ref 当代替层层 $emit，省掉三套重复接线。
 */
export const detailProject = ref(null)

export function openDetail(p) {
  if (p) detailProject.value = p
}

export function closeDetail() {
  detailProject.value = null
}
