import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './style.css'

const app = createApp(App)
app.use(router)

// 等首屏路由解析完再挂载：App 的初始筛选状态直接从 route 读，
// 提前挂载会读到 START_LOCATION，把 ?district=东城区 这类参数丢掉。
router.isReady().then(() => app.mount('#app'))
