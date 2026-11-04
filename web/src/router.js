import { createRouter, createWebHistory } from 'vue-router'

/**
 * 路由只负责 URL，不负责渲染。
 *
 * 页面上没有 <RouterView>：地图和列表共用同一个 App（数据、筛选、弹窗都在里面），
 * 拆成两个路由组件会各加载一次 3MB 数据、互相看不见对方的选中状态。
 * 所以这里把路由当成「URL 的唯一出口」：
 *
 *   /       地图视图
 *   /list   街道列表 / 小区明细
 *   /data   数据下载说明
 *
 * 其余筛选条件仍然放在 query 里（?district=东城区&street=东华门街道…），
 * 规则见 utils/urlState.js。这样做的好处是 Vercel Analytics 能按 / 和 /list
 * 分开统计访问量——只靠 query 的话所有访问都会算在同一个页面上。
 */

// 路由表必须能匹配，但不渲染任何东西
const Blank = { name: 'Blank', render: () => null }

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'map', component: Blank },
    { path: '/list', name: 'list', component: Blank },
    { path: '/data', name: 'data', component: Blank },
    // 其余路径一律回首页，避免直接访问 /xxx 白屏
    { path: '/:pathMatch(.*)*', name: 'fallback', component: Blank },
  ],
})

router.beforeEach((to) => {
  // 统一去掉尾斜杠：/list/ 和 /list 视为同一页，否则 route.path 对不上，视图判断会落回地图
  if (to.path.length > 1 && to.path.endsWith('/')) {
    return { path: to.path.replace(/\/+$/, ''), query: to.query, hash: to.hash, replace: true }
  }

  const { view, ...rest } = to.query

  // 兼容早期写法：?view=list 现在搬到路径上，其余参数原样保留
  if (view === 'list' && to.path !== '/list') {
    return { path: '/list', query: rest, hash: '', replace: true }
  }
  if (view === 'data' && to.path !== '/data') {
    return { path: '/data', query: rest, hash: '', replace: true }
  }
  if (view && view !== 'list' && view !== 'data' && (to.path === '/list' || to.path === '/data')) {
    return { path: '/', query: rest, hash: '', replace: true }
  }
  if (view) {
    return { path: to.path, query: rest, hash: to.hash, replace: true }
  }

  // 更早的版本用 #/streets 标记列表页
  if (to.hash.startsWith('#/streets')) {
    return { path: '/list', query: to.query, hash: '', replace: true }
  }

  if (to.path !== '/' && to.path !== '/list' && to.path !== '/data') {
    return { path: '/', query: to.query, hash: '', replace: true }
  }
  return true
})
