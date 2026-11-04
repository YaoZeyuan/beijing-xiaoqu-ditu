<template>
  <a
    class="gov-link"
    :class="{ off: !href }"
    :href="href || undefined"
    :target="href ? '_blank' : undefined"
    :rel="href ? 'noopener noreferrer' : undefined"
    :title="tip"
    @click="onClick"
  >
    <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M14 4h6v6" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M20 4l-8.5 8.5" stroke-linecap="round" />
      <path d="M18 14.5V19a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 014 19V8a1.5 1.5 0 011.5-1.5H10" stroke-linecap="round" />
    </svg>
    <span v-if="text" class="gl-text">{{ text }}</span>
  </a>
</template>

<script setup>
import { computed, inject } from 'vue'

const props = defineProps({
  id: { type: String, default: '' },
  name: { type: String, default: '' },
  text: { type: String, default: '' },
})

// meta.detailUrl 形如 ...&t=toDetail&project_no={id}
const meta = inject('meta', null)

const href = computed(() => {
  const tpl = meta?.value?.detailUrl || meta?.detailUrl
  if (!tpl || !props.id) return ''
  return tpl.replace('{id}', encodeURIComponent(props.id))
})

const tip = computed(() => {
  if (!href.value) return '该项目在住建委没有对应的项目编号，无法直达官方页面'
  return `在北京市住建委网站查看「${props.name || '该项目'}」的在册信息（新窗口打开）`
})

function onClick(e) {
  e.stopPropagation()
  if (!href.value) e.preventDefault()
}
</script>

<style scoped>
.gov-link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--text-dim);
  text-decoration: none;
  padding: 1px 5px;
  border-radius: 5px;
  border: 1px solid transparent;
  transition: all 0.14s;
  white-space: nowrap;
  cursor: pointer;
  line-height: 1.5;
  font-family: inherit;
}
.gov-link:hover {
  color: var(--accent);
  border-color: rgba(76, 154, 255, 0.4);
  background: rgba(76, 154, 255, 0.08);
}
.gov-link.off { opacity: 0.28; cursor: not-allowed; }
.gov-link.off:hover { color: var(--text-faint); border-color: transparent; background: none; }
.gl-text { font-size: 10.5px; }
</style>
