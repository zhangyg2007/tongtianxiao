<template>
  <div class="analysis-container">
    <!-- 顶部导航栏 -->
    <el-header class="analysis-header">
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
        </div>
      </div>
    </el-header>

    <!-- 主体内容 -->
    <el-main class="analysis-main">
      <div class="analysis-content">
        <!-- 左侧分析配置 -->
        <div class="analysis-config">
          <el-card shadow="hover">
            <template #header>
              <div class="card-header">
                <h3>分析配置</h3>
              </div>
            </template>
            
            <el-form
              :model="analysisForm"
              :rules="analysisRules"
              ref="analysisFormRef"
              label-position="top"
            >
              <el-form-item label="关键词" prop="keyword">
                <el-input
                  v-model="analysisForm.keyword"
                  placeholder="请输入要分析的关键词"
                  :prefix-icon="Search"
                />
              </el-form-item>
              
              <el-form-item label="时间范围">
                <el-date-picker
                  v-model="analysisForm.timeRange"
                  type="daterange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                />
              </el-form-item>
              
              <el-form-item label="平台选择" prop="platforms">
                <el-checkbox-group v-model="analysisForm.platforms">
                  <el-checkbox label="微博" name="platform" />
                  <el-checkbox label="小红书" name="platform" />
                  <el-checkbox label="抖音" name="platform" />
                  <el-checkbox label="快手" name="platform" />
                  <el-checkbox label="知乎" name="platform" />
                  <el-checkbox label="贴吧" name="platform" />
                  <el-checkbox label="B站" name="platform" />
                </el-checkbox-group>
              </el-form-item>
              
              <el-form-item label="分析深度" prop="depth">
                <el-select v-model="analysisForm.depth" placeholder="请选择分析深度">
                  <el-option label="基础分析" value="1" />
                  <el-option label="深度分析" value="2" />
                  <el-option label="全面分析" value="3" />
                </el-select>
              </el-form-item>
              
              <el-form-item label="分析类型" prop="analysisType">
                <el-select v-model="analysisForm.analysisType" placeholder="请选择分析类型">
                  <el-option label="情感分析" value="sentiment" />
                  <el-option label="热点分析" value="hotspot" />
                  <el-option label="趋势分析" value="trend" />
                  <el-option label="综合分析" value="comprehensive" />
                </el-select>
              </el-form-item>
              
              <el-form-item>
                <el-button
                  type="primary"
                  :loading="isSubmitting"
                  @click="handleSubmit"
                  class="submit-button"
                  native-type="submit"
                >
                  开始分析
                </el-button>
                <el-button @click="resetForm">重置</el-button>
              </el-form-item>
            </el-form>
          </el-card>
          
          <!-- 智能体状态 -->
          <el-card shadow="hover" class="agent-status-card">
            <template #header>
              <div class="card-header">
                <h3>智能体状态</h3>
              </div>
            </template>
            
            <div class="agent-status-list">
              <div
                v-for="agent in agentStatus"
                :key="agent.name"
                class="agent-item"
                :class="{ 'agent-running': agent.status === 'running' }"
              >
                <div class="agent-info">
                  <div class="agent-name">{{ agent.name }}</div>
                  <div class="agent-desc">{{ agent.description }}</div>
                </div>
                <el-tag
                  :type="agent.status === 'running' ? 'success' : 'warning'"
                  size="small"
                >
                  {{ agent.status === 'running' ? '运行中' : '已停止' }}
                </el-tag>
              </div>
            </div>
          </el-card>
        </div>
        
        <!-- 右侧分析进度和结果 -->
        <div class="analysis-result">
          <!-- 分析进度 -->
          <el-card shadow="hover" v-if="currentTask">
            <template #header>
              <div class="card-header">
                <h3>分析进度</h3>
                <el-button
                  type="danger"
                  size="small"
                  @click="handleCancelTask"
                  :loading="isCanceling"
                >
                  取消分析
                </el-button>
              </div>
            </template>
            
            <div class="progress-info">
              <div class="progress-item">
                <span class="progress-label">关键词：</span>
                <span class="progress-value">{{ currentTask.keyword }}</span>
              </div>
              <div class="progress-item">
                <span class="progress-label">状态：</span>
                <el-tag
                  :type="getTaskStatusType(currentTask.status)"
                  size="small"
                >
                  {{ getTaskStatusText(currentTask.status) }}
                </el-tag>
              </div>
              <div class="progress-item">
                <span class="progress-label">进度：</span>
                <span class="progress-value">{{ currentTask.progress }}%</span>
              </div>
              <div class="progress-item">
                <span class="progress-label">开始时间：</span>
                <span class="progress-value">{{ formatTime(currentTask.start_time) }}</span>
              </div>
              <div class="progress-item">
                <span class="progress-label">预计完成：</span>
                <span class="progress-value">{{ estimatedCompletion }}</span>
              </div>
            </div>
            
            <el-progress
              :percentage="currentTask.progress"
              :status="getTaskProgressStatus(currentTask.status)"
              class="task-progress"
            />
            
            <!-- 智能体工作状态 -->
            <div class="agent-work-status" v-if="currentTask.status === 'running'">
              <h4>智能体工作状态</h4>
              <div class="agent-work-list">
                <div
                  v-for="agent in workingAgents"
                  :key="agent.name"
                  class="agent-work-item"
                >
                  <div class="agent-work-info">
                    <div class="agent-work-name">{{ agent.name }}</div>
                    <div class="agent-work-desc">{{ agent.currentAction }}</div>
                  </div>
                  <el-progress
                    :percentage="agent.progress"
                    size="small"
                    :color="agent.color"
                  />
                </div>
              </div>
            </div>
          </el-card>
          
          <!-- 历史任务 -->
          <el-card shadow="hover" v-else>
            <template #header>
              <div class="card-header">
                <h3>历史分析任务</h3>
              </div>
            </template>
            
            <el-table :data="historyTasks" stripe style="width: 100%">
              <el-table-column prop="keyword" label="关键词" width="180" />
              <el-table-column prop="created_at" label="创建时间" width="180" />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="scope">
                  <el-tag
                    :type="getTaskStatusType(scope.row.status)"
                    size="small"
                  >
                    {{ getTaskStatusText(scope.row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="progress" label="进度" width="120">
                <template #default="scope">
                  <el-progress
                    :percentage="scope.row.progress"
                    size="small"
                  />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="scope">
                  <el-button
                    type="primary"
                    size="small"
                    @click="viewTaskResult(scope.row.id)"
                    :disabled="scope.row.status !== 'completed'"
                  >
                    查看结果
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
          
          <!-- 实时日志 -->
          <el-card shadow="hover" class="log-card">
            <template #header>
              <div class="card-header">
                <h3>实时日志</h3>
                <el-button type="text" size="small" @click="clearLogs">清空日志</el-button>
              </div>
            </template>
            
            <div class="log-container">
              <div
                v-for="(log, index) in logs"
                :key="index"
                class="log-item"
                :class="log.level"
              >
                <span class="log-time">{{ log.time }}</span>
                <span class="log-level">{{ log.level }}</span>
                <span class="log-content">{{ log.content }}</span>
              </div>
            </div>
          </el-card>
        </div>
      </div>
    </el-main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { useAnalysisStore } from '../store/analysis'
import http from '../utils/http'
import {
  Search,
  ArrowDown
} from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()
const analysisStore = useAnalysisStore()
const analysisFormRef = ref<FormInstance>()
const activeMenu = ref('analysis')

// 用户相关状态
const isLoggedIn = userStore.isLoggedIn
const isAdmin = userStore.isAdmin
const userInfo = userStore.userInfo

// 表单状态
const isSubmitting = ref(false)
const isCanceling = ref(false)

// 分析表单
const analysisForm = reactive({
  keyword: '',
  timeRange: null as [string, string] | null,
  platforms: [] as string[],
  depth: 1,
  analysisType: 'comprehensive'
})

// 表单验证规则
const analysisRules = reactive<FormRules>({
  keyword: [
    { required: true, message: '请输入关键词', trigger: 'blur' },
    { min: 1, max: 50, message: '关键词长度在 1 到 50 个字符', trigger: 'blur' }
  ],
  platforms: [
    { required: true, message: '请选择至少一个平台', trigger: 'change' }
  ],
  depth: [
    { required: true, message: '请选择分析深度', trigger: 'change' }
  ],
  analysisType: [
    { required: true, message: '请选择分析类型', trigger: 'change' }
  ]
})

// 当前任务
const currentTask = ref<any>(null)

// 历史任务
const historyTasks = ref<any[]>([
  // 模拟数据
  {
    id: 1,
    keyword: '人工智能',
    created_at: '2025-12-10 14:30:00',
    status: 'completed',
    progress: 100
  },
  {
    id: 2,
    keyword: '新能源汽车',
    created_at: '2025-12-09 10:15:00',
    status: 'completed',
    progress: 100
  }
])

// 智能体状态
const agentStatus = ref([
  { name: 'Insight Agent', description: '私有数据库挖掘', status: 'running' },
  { name: 'Media Agent', description: '多模态内容分析', status: 'running' },
  { name: 'Query Agent', description: '精准信息搜索', status: 'running' },
  { name: 'Report Agent', description: '智能报告生成', status: 'running' },
  { name: 'Forum Engine', description: '智能体协作管理', status: 'running' }
])

// 工作中的智能体
const workingAgents = ref([
  { name: 'Query Agent', currentAction: '正在搜索相关信息...', progress: 60, color: '#409EFF' },
  { name: 'Media Agent', currentAction: '正在分析多媒体内容...', progress: 45, color: '#67C23A' },
  { name: 'Insight Agent', currentAction: '正在挖掘数据库...', progress: 30, color: '#E6A23C' }
])

// 实时日志
const logs = ref([
  { time: '14:30:00', level: 'info', content: '分析任务已开始' },
  { time: '14:30:05', level: 'info', content: 'Query Agent开始工作' },
  { time: '14:30:10', level: 'info', content: 'Media Agent开始工作' },
  { time: '14:30:15', level: 'info', content: 'Insight Agent开始工作' },
  { time: '14:31:00', level: 'info', content: '已获取100条相关信息' },
  { time: '14:32:00', level: 'info', content: '已分析50条多媒体内容' }
])

// 预计完成时间
const estimatedCompletion = ref('2025-12-11 14:45:00')

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

// 表单提交
const handleSubmit = async () => {
  if (!analysisFormRef.value) return
  
  try {
    await analysisFormRef.value.validate()
    isSubmitting.value = true
    
    // 构建请求数据
    const requestData = {
      keyword: analysisForm.keyword,
      start_time: analysisForm.timeRange?.[0] || null,
      end_time: analysisForm.timeRange?.[1] || null,
      platforms: analysisForm.platforms,
      depth: analysisForm.depth,
      analysis_type: analysisForm.analysisType
    }
    
    // 发送分析请求
    const response = await http.post('/analysis/tasks', requestData)
    
    if (response.success) {
      // 更新当前任务
      currentTask.value = response.data.task
      analysisStore.setCurrentTask(response.data.task)
      
      // 清空表单
      resetForm()
      
      // 开始监听任务进度
      startTaskProgressMonitoring(response.data.task.id)
    } else {
      ElMessage.error(response.message || '分析请求提交失败')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '提交失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

// 重置表单
const resetForm = () => {
  if (analysisFormRef.value) {
    analysisFormRef.value.resetFields()
  }
  analysisForm.platforms = []
  analysisForm.depth = 1
  analysisForm.analysisType = 'comprehensive'
}

// 取消任务
const handleCancelTask = async () => {
  if (!currentTask.value) return
  
  try {
    isCanceling.value = true
    const response = await http.post(`/analysis/tasks/${currentTask.value.id}/cancel`)
    
    if (response.success) {
      ElMessage.success('任务已取消')
      currentTask.value = null
      analysisStore.setCurrentTask(null)
    } else {
      ElMessage.error(response.message || '任务取消失败')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '取消失败，请稍后重试')
  } finally {
    isCanceling.value = false
  }
}

// 查看任务结果
const viewTaskResult = (id: number) => {
  router.push(`/report/${id}`)
}

// 清空日志
const clearLogs = () => {
  logs.value = []
}

// 获取任务状态类型
const getTaskStatusType = (status: string) => {
  switch (status) {
    case 'running':
      return 'warning'
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    default:
      return 'info'
  }
}

// 获取任务状态文本
const getTaskStatusText = (status: string) => {
  switch (status) {
    case 'pending':
      return '待处理'
    case 'running':
      return '运行中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    default:
      return status
  }
}

// 获取任务进度状态
const getTaskProgressStatus = (status: string) => {
  if (status === 'completed') {
    return 'success'
  } else if (status === 'failed') {
    return 'exception'
  }
  return ''
}

// 格式化时间
const formatTime = (time: string | null) => {
  if (!time) return '未开始'
  return new Date(time).toLocaleString()
}

// 开始监听任务进度
const startTaskProgressMonitoring = (taskId: number) => {
  // 这里可以添加实际的进度监听逻辑
  // 例如使用WebSocket或定时轮询
  let progress = 0
  const interval = setInterval(() => {
    progress += 5
    if (progress >= 100) {
      progress = 100
      clearInterval(interval)
      // 模拟任务完成
      setTimeout(() => {
        if (currentTask.value) {
          currentTask.value.status = 'completed'
          currentTask.value.progress = 100
          analysisStore.updateTask(taskId, { status: 'completed', progress: 100 })
          ElMessage.success('分析任务已完成')
        }
      }, 1000)
    }
    
    if (currentTask.value) {
      currentTask.value.progress = progress
      analysisStore.updateTask(taskId, { progress })
    }
  }, 2000)
}

// 页面加载时的处理
onMounted(() => {
  // 检查URL参数中是否有关键词
  const keyword = router.currentRoute.value.query.keyword as string
  if (keyword) {
    analysisForm.keyword = keyword
  }
  
  // 获取历史任务
  fetchHistoryTasks()
})

// 获取历史任务
const fetchHistoryTasks = async () => {
  try {
    const response = await http.get('/analysis/tasks')
    if (response.success) {
      analysisStore.setTasks(response.data.tasks)
    }
  } catch (error) {
    console.error('获取历史任务失败:', error)
  }
}
</script>

<style scoped>
.analysis-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.analysis-header {
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

.analysis-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  width: 100%;
}

.analysis-content {
  display: grid;
  grid-template-columns: 350px 1fr;
  gap: 20px;
}

/* 左侧配置 */
.analysis-config {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.submit-button {
  width: 100%;
}

.agent-status-card {
  margin-top: 20px;
}

.agent-status-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  border-radius: 6px;
  transition: all 0.3s;
}

.agent-item:hover {
  background-color: #f5f7fa;
}

.agent-running {
  background-color: #f0f9eb;
  border-left: 4px solid #67c23a;
}

.agent-info {
  flex: 1;
}

.agent-name {
  font-weight: bold;
  margin-bottom: 4px;
}

.agent-desc {
  font-size: 12px;
  color: #666;
}

/* 右侧结果 */
.analysis-result {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.progress-info {
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.progress-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-label {
  font-weight: bold;
  min-width: 80px;
  color: #666;
}

.progress-value {
  flex: 1;
}

.task-progress {
  margin: 20px 0;
}

.agent-work-status {
  margin-top: 20px;
}

.agent-work-status h4 {
  margin-bottom: 15px;
  font-size: 16px;
}

.agent-work-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.agent-work-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.agent-work-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.agent-work-name {
  font-weight: bold;
}

.agent-work-desc {
  font-size: 14px;
  color: #666;
}

/* 日志样式 */
.log-card {
  flex: 1;
}

.log-container {
  max-height: 300px;
  overflow-y: auto;
  background-color: #fafafa;
  padding: 15px;
  border-radius: 6px;
  font-family: 'Courier New', monospace;
  font-size: 14px;
}

.log-item {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.log-time {
  color: #999;
  font-size: 12px;
  min-width: 80px;
}

.log-level {
  font-weight: bold;
  min-width: 60px;
  text-align: center;
  border-radius: 10px;
  padding: 2px 8px;
  font-size: 12px;
}

.log-level.info {
  background-color: #e3f2fd;
  color: #1976d2;
}

.log-level.warn {
  background-color: #fff3e0;
  color: #f57c00;
}

.log-level.error {
  background-color: #ffebee;
  color: #d32f2f;
}

.log-level.debug {
  background-color: #f3e5f5;
  color: #7b1fa2;
}

.log-content {
  flex: 1;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .analysis-content {
    grid-template-columns: 1fr;
  }
  
  .analysis-config {
    order: 2;
  }
  
  .analysis-result {
    order: 1;
  }
}
</style>
