/** 复制文本到剪贴板，返回是否成功 */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (e) {
    // 非 https 或旧浏览器退回 execCommand
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.top = '-1000px'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    let ok = false
    try { ok = document.execCommand('copy') } catch (_) { ok = false }
    ta.remove()
    return ok
  }
}

/**
 * 生成 Markdown 表格文本，粘到微信 / 飞书 / 文档里是等宽可读的
 * @param {string[]} headers 表头
 * @param {(string|number|null)[][]} rows 数据行
 * @param {('left'|'right'|'center')[]} aligns 每列对齐方式
 */
export function mdTable(headers, rows, aligns = []) {
  const sep = headers.map((_, i) => {
    const a = aligns[i]
    if (a === 'right') return '---:'
    if (a === 'center') return ':---:'
    return '---'
  })
  const line = (cells) => '| ' + cells
    .map((c) => String(c === null || c === undefined ? '' : c).replace(/\|/g, '\\|'))
    .join(' | ') + ' |'
  return [line(headers), line(sep), ...rows.map(line)].join('\n')
}
