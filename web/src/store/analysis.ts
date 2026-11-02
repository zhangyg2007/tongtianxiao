import { defineStore } from 'pinia'

export interface AnalysisTask {
  id: number
  user_id: number
  keyword: string
  start_time: string | null
  end_time: string | null
  platforms: string[]
  depth: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  created_at: string
  updated_at: string
}

export const useAnalysisStore = defineStore('analysis', {
  state: () => ({
    tasks: [] as AnalysisTask[],
    currentTask: null as AnalysisTask | null,
    isLoading: false,
    error: null as string | null
  }),

  getters: {
    runningTasks: (state) => state.tasks.filter(task => task.status === 'running'),
    completedTasks: (state) => state.tasks.filter(task => task.status === 'completed'),
    pendingTasks: (state) => state.tasks.filter(task => task.status === 'pending')
  },

  actions: {
    setLoading(loading: boolean) {
      this.isLoading = loading
    },

    setError(error: string | null) {
      this.error = error
    },

    setTasks(tasks: AnalysisTask[]) {
      this.tasks = tasks
    },

    setCurrentTask(task: AnalysisTask | null) {
      this.currentTask = task
    },

    addTask(task: AnalysisTask) {
      this.tasks.unshift(task)
    },

    updateTask(taskId: number, updates: Partial<AnalysisTask>) {
      const index = this.tasks.findIndex(task => task.id === taskId)
      if (index !== -1) {
        this.tasks[index] = { ...this.tasks[index], ...updates }
      }
      
      if (this.currentTask && this.currentTask.id === taskId) {
        this.currentTask = { ...this.currentTask, ...updates }
      }
    },

    removeTask(taskId: number) {
      this.tasks = this.tasks.filter(task => task.id !== taskId)
      if (this.currentTask && this.currentTask.id === taskId) {
        this.currentTask = null
      }
    }
  }
})
