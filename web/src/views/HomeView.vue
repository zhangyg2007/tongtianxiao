<template>
  <div class="home-container">
    <!-- 顶部导航栏 -->
    <el-header class="home-header">
      <div class="header-content">
        <div class="logo">
          <h1>微舆</h1>
          <span>舆情分析系统</span>
        </div>
        <el-menu
          :default-active="activeMenu"
          class="el-menu-demo"
          mode="horizontal"
          @select="handleMenuSelect"
        >
          <el-menu-item index="home">首页</el-menu-item>
          <el-menu-item index="analysis">舆情分析</el-menu-item>
          <el-menu-item index="reports">报告管理</el-menu-item>
          <el-menu-item index="config" v-if="isAdmin">系统配置</el-menu-item>
          <el-menu-item index="monitor" v-if="isAdmin">监控中心</el-menu-item>
        </el-menu>
        <div class="user-info">
          <template v-if="isLoggedIn">
            <el-dropdown>
              <span class="el-dropdown-link">
                {{ userInfo?.username }}<el-icon class="el-icon--right"><arrow-down /></el-icon>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="$router.push('/profile')">个人中心</el-dropdown-item>
                  <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else>
            <el-button type="primary" @click="$router.push('/login')">登录</el-button>
            <el-button @click="$router.push('/register')">注册</el-button>
          </template>
        </div>
      </div>
    </el-header>

    <!-- 主体内容 -->
    <el-main class="home-main">
      <!-- 英雄区域 -->
      <section class="hero-section">
        <div class="hero-content">
          <h2>洞察舆情，把握未来</h2>
          <p>微舆舆情分析系统，基于多智能体技术，为您提供全面、深入的舆情分析服务</p>
          <div class="hero-buttons">
            <el-button type="primary" size="large" @click="$router.push('/analysis')">
              开始分析
            </el-button>
            <el-button size="large" @click="scrollToFeatures">
              了解更多
            </el-button>
          </div>
        </div>
      </section>

      <!-- 功能特点 -->
      <section class="features-section" ref="featuresRef">
        <h3>核心功能</h3>
        <div class="features-grid">
          <el-card class="feature-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon class="feature-icon"><search /></el-icon>
                <h4>多平台舆情监控</h4>
              </div>
            </template>
            <p>覆盖微博、小红书、抖音、快手等30+主流社交媒体平台，实时监控舆情动态</p>
          </el-card>
          
          <el-card class="feature-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon class="feature-icon"><data-analysis /></el-icon>
                <h4>深度情感分析</h4>
              </div>
            </template>
            <p>基于深度学习模型，准确分析用户情感倾向，把握舆论走向</p>
          </el-card>
          
          <el-card class="feature-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon class="feature-icon"><document /></el-icon>
                <h4>智能报告生成</h4>
              </div>
            </template>
            <p>自动生成专业舆情分析报告，支持多种格式下载和分享</p>
          </el-card>
          
          <el-card class="feature-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon class="feature-icon"><warning /></el-icon>
                <h4>异常舆情预警</h4>
              </div>
            </template>
            <p>实时监测异常舆情，及时预警，帮助您快速响应</p>
          </el-card>
        </div>
      </section>

      <!-- 快速分析入口 -->
      <section class="quick-analysis-section">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <h3>快速分析</h3>
              <p>输入关键词，立即开始舆情分析</p>
            </div>
          </template>
          
          <el-form :model="quickAnalysisForm" @submit.prevent="handleQuickAnalysis">
            <div class="quick-analysis-form">
              <el-input
                v-model="quickAnalysisForm.keyword"
                placeholder="请输入关键词"
                :prefix-icon="Search"
                class="keyword-input"
              />
              <el-button type="primary" native-type="submit" size="large">
                开始分析
              </el-button>
            </div>
          </el-form>
        </el-card>
      </section>

      <!-- 热门话题 -->
      <section class="hot-topics-section">
        <h3>热门话题</h3>
        <div class="hot-topics-list">
          <el-card
            v-for="topic in hotTopics"
            :key="topic.id"
            class="topic-card"
            shadow="hover"
            @click="handleTopicClick(topic.keyword)"
          >
            <div class="topic-content">
              <div class="topic-rank">{{ topic.rank }}</div>
              <div class="topic-info">
                <h4 class="topic-title">{{ topic.keyword }}</h4>
                <div class="topic-meta">
                  <span class="topic-platform">{{ topic.platform }}</span>
                  <span class="topic-hotness">热度: {{ topic.hotness }}</span>
                </div>
              </div>
              <el-icon class="arrow-icon"><arrow-right /></el-icon>
            </div>
          </el-card>
        </div>
      </section>

      <!-- 历史报告 -->
      <section class="history-reports-section">
        <div class="section-header">
          <h3>历史报告</h3>
          <el-button type="text" @click="$router.push('/reports')">查看全部</el-button>
        </div>
        
        <el-table :data="recentReports" stripe style="width: 100%">
          <el-table-column prop="title" label="报告标题" min-width="200" />
          <el-table-column prop="keyword" label="关键词" />
          <el-table-column prop="created_at" label="生成时间" width="180" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag
                :type="scope.row.status === 'completed' ? 'success' : 'warning'"
                size="small"
              >
                {{ scope.row.status === 'completed' ? '已完成' : scope.row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="scope">
              <el-button
                type="primary"
                size="small"
                @click="viewReport(scope.row.id)"
                :disabled="scope.row.status !== 'completed'"
              >
                查看
              </el-button>
              <el-button
                type="success"
                size="small"
                @click="downloadReport(scope.row.id)"
                :disabled="scope.row.status !== 'completed'"
              >
                下载
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </el-main>

    <!-- 页脚 -->
    <el-footer class="home-footer">
      <div class="footer-content">
        <div class="footer-info">
          <h4>微舆舆情分析系统</h4>
          <p>基于多智能体技术的新一代舆情分析平台</p>
        </div>
        <div class="footer-links">
          <el-link type="info">关于我们</el-link>
          <el-link type="info">使用文档</el-link>
          <el-link type="info">联系我们</el-link>
          <el-link type="info">隐私政策</el-link>
        </div>
        <div class="footer-copyright">
          <p>© 2025 微舆舆情分析系统 版权所有</p>
        </div>
      </div>
    </el-footer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import http from '../utils/http'
import {
  Search,
  ArrowDown,
  DataAnalysis,
  Document,
  Warning,
  ArrowRight
} from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const featuresRef = ref<HTMLElement | null>(null)
const activeMenu = ref('home')

// 用户相关状态
const isLoggedIn = userStore.isLoggedIn
const isAdmin = userStore.isAdmin
const userInfo = userStore.userInfo

// 快速分析表单
const quickAnalysisForm = reactive({
  keyword: ''
})

// 热门话题数据（模拟）
const hotTopics = ref([
  { id: 1, rank: 1, keyword: '人工智能', platform: '微博', hotness: '100万+' },
  { id: 2, rank: 2, keyword: '新能源汽车', platform: '小红书', hotness: '80万+' },
  { id: 3, rank: 3, keyword: '气候变化', platform: '抖音', hotness: '70万+' },
  { id: 4, rank: 4, keyword: '数字经济', platform: '快手', hotness: '60万+' },
  { id: 5, rank: 5, keyword: '元宇宙', platform: '知乎', hotness: '50万+' }
])

// 最近报告数据（模拟）
const recentReports = ref([
  { id: 1, title: '人工智能舆情分析报告', keyword: '人工智能', created_at: '2025-12-10 14:30:00', status: 'completed' },
  { id: 2, title: '新能源汽车市场分析', keyword: '新能源汽车', created_at: '2025-12-09 10:15:00', status: 'completed' },
  { id: 3, title: '气候变化公众态度调研', keyword: '气候变化', created_at: '2025-12-08 16:45:00', status: 'completed' },
  { id: 4, title: '数字经济发展趋势', keyword: '数字经济', created_at: '2025-12-07 09:30:00', status: 'completed' },
  { id: 5, title: '元宇宙概念解析', keyword: '元宇宙', created_at: '2025-12-06 14:00:00', status: 'completed' }
])

// 菜单选择处理
const handleMenuSelect = (index: string) => {
  activeMenu.value = index
  switch (index) {
    case 'home':
      router.push('/')
      break
    case 'analysis':
      router.push('/analysis')
      break
    case 'reports':
      router.push('/reports')
      break
    case 'config':
      router.push('/config')
      break
    case 'monitor':
      router.push('/monitor')
      break
  }
}

// 退出登录
const handleLogout = () => {
  userStore.logout()
  router.push('/login')
}

// 滚动到功能特点区域
const scrollToFeatures = () => {
  if (featuresRef.value) {
    featuresRef.value.scrollIntoView({ behavior: 'smooth' })
  }
}

// 快速分析提交
const handleQuickAnalysis = () => {
  if (quickAnalysisForm.keyword) {
    router.push(`/analysis?keyword=${encodeURIComponent(quickAnalysisForm.keyword)}`)
  }
}

// 热门话题点击
const handleTopicClick = (keyword: string) => {
  router.push(`/analysis?keyword=${encodeURIComponent(keyword)}`)
}

// 查看报告
const viewReport = (id: number) => {
  router.push(`/report/${id}`)
}

// 下载报告
const downloadReport = (id: number) => {
  window.open(`/api/reports/${id}/download`)
}

// 页面加载时获取数据
onMounted(() => {
  // 这里可以添加实际的数据获取逻辑
  // fetchHotTopics()
  // fetchRecentReports()
})
</script>

<style scoped>
.home-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.home-header {
  background-color: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
}

.logo {
  display: flex;
  align-items: center;
}

.logo h1 {
  margin: 0;
  font-size: 24px;
  font-weight: bold;
  color: #667eea;
  margin-right: 8px;
}

.logo span {
  font-size: 14px;
  color: #666;
}

.el-menu-demo {
  flex: 1;
  justify-content: center;
  background-color: transparent;
  border-bottom: none;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-info .el-dropdown-link {
  cursor: pointer;
  color: #606266;
  display: flex;
  align-items: center;
  gap: 5px;
}

.home-main {
  flex: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  width: 100%;
}

/* 英雄区域 */
.hero-section {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  padding: 60px 40px;
  margin-bottom: 30px;
  text-align: center;
  color: white;
}

.hero-content h2 {
  font-size: 36px;
  margin-bottom: 16px;
}

.hero-content p {
  font-size: 18px;
  margin-bottom: 32px;
  opacity: 0.9;
}

.hero-buttons {
  display: flex;
  gap: 16px;
  justify-content: center;
}

/* 功能特点 */
.features-section {
  margin-bottom: 30px;
}

.features-section h3 {
  text-align: center;
  margin-bottom: 24px;
  font-size: 24px;
  color: #333;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
}

.feature-card {
  cursor: pointer;
  transition: transform 0.3s;
}

.feature-card:hover {
  transform: translateY(-5px);
}

.feature-card .card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.feature-icon {
  font-size: 24px;
  color: #667eea;
}

/* 快速分析 */
.quick-analysis-section {
  margin-bottom: 30px;
}

.quick-analysis-form {
  display: flex;
  gap: 16px;
  align-items: center;
}

.keyword-input {
  flex: 1;
  height: 48px;
}

/* 热门话题 */
.hot-topics-section {
  margin-bottom: 30px;
}

.hot-topics-section h3 {
  margin-bottom: 24px;
  font-size: 24px;
  color: #333;
}

.hot-topics-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}

.topic-card {
  cursor: pointer;
  transition: all 0.3s;
}

.topic-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.topic-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.topic-rank {
  font-size: 24px;
  font-weight: bold;
  color: #ff4d4f;
  width: 40px;
  text-align: center;
}

.topic-info {
  flex: 1;
}

.topic-title {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: bold;
  color: #333;
}

.topic-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #666;
}

.topic-platform {
  background-color: #f0f5ff;
  color: #667eea;
  padding: 2px 8px;
  border-radius: 10px;
}

.arrow-icon {
  color: #999;
}

/* 历史报告 */
.history-reports-section {
  margin-bottom: 30px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  font-size: 24px;
  color: #333;
  margin: 0;
}

/* 页脚 */
.home-footer {
  background-color: #f8f9fa;
  padding: 30px 0;
  margin-top: auto;
}

.footer-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 20px;
}

.footer-info h4 {
  margin: 0 0 8px 0;
  color: #333;
}

.footer-info p {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.footer-links {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.footer-copyright p {
  margin: 0;
  color: #999;
  font-size: 14px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .header-content {
    flex-direction: column;
    height: auto;
    padding: 10px;
  }

  .el-menu-demo {
    width: 100%;
    margin: 10px 0;
  }

  .quick-analysis-form {
    flex-direction: column;
  }

  .keyword-input {
    width: 100%;
  }

  .hot-topics-list {
    grid-template-columns: 1fr;
  }

  .footer-content {
    flex-direction: column;
    text-align: center;
  }
}
</style>
