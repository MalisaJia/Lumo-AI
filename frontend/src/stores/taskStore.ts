import { create } from 'zustand'
import { tasksApi } from '../api/client'

export interface TaskItem {
  id: string
  conversationId: string
  parentTaskId: string | null
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  result: string | null
  agentRunId: string | null
}

export interface AgentRunItem {
  id: string
  taskId: string | null
  agentType: string
  model: string | null
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  currentTool: string | null
}

interface TaskState {
  tasks: Map<string, TaskItem>
  agentRuns: Map<string, AgentRunItem>
  totalRounds: number

  handleTaskCreated: (data: { taskId: string; parentTaskId?: string; description: string; conversationId: string }) => void
  handleTaskStatusChanged: (data: { taskId: string; status: string; result?: string }) => void
  handleAgentStarted: (data: { agentId: string; taskId?: string; model?: string; agentType: string }) => void
  handleAgentStopped: (data: { agentId: string; reason?: string; status?: string; rounds?: number }) => void
  handleToolStart: (data: { toolName: string; agentId: string }) => void
  handleToolEnd: (data: { toolName: string; agentId: string }) => void

  getTaskTree: (conversationId: string) => TaskItem[]
  getRunningAgents: () => AgentRunItem[]

  loadTasks: (conversationId: string) => Promise<void>
  cancelTask: (taskId: string) => Promise<void>
  reset: () => void
}

const TASK_STATUSES = new Set<TaskItem['status']>([
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled',
])

function asTaskStatus(status: string): TaskItem['status'] | null {
  return TASK_STATUSES.has(status as TaskItem['status']) ? (status as TaskItem['status']) : null
}

function stoppedStatus(status?: string, reason?: string): AgentRunItem['status'] {
  if (status === 'completed' || status === 'failed' || status === 'cancelled') return status
  if (reason?.toLowerCase().includes('cancel')) return 'cancelled'
  return reason ? 'failed' : 'completed'
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: new Map(),
  agentRuns: new Map(),
  totalRounds: 0,

  handleTaskCreated: (data) => {
    set((state) => {
      const tasks = new Map(state.tasks)
      tasks.set(data.taskId, {
        id: data.taskId,
        conversationId: data.conversationId,
        parentTaskId: data.parentTaskId ?? null,
        description: data.description,
        status: 'pending',
        result: null,
        agentRunId: null,
      })
      return { tasks }
    })
  },

  handleTaskStatusChanged: (data) => {
    const status = asTaskStatus(data.status)
    if (!status) return
    set((state) => {
      const current = state.tasks.get(data.taskId)
      if (!current) return state
      const tasks = new Map(state.tasks)
      tasks.set(data.taskId, {
        ...current,
        status,
        result: data.result === undefined ? current.result : data.result,
      })
      return { tasks }
    })
  },

  handleAgentStarted: (data) => {
    set((state) => {
      const agentRuns = new Map(state.agentRuns)
      agentRuns.set(data.agentId, {
        id: data.agentId,
        taskId: data.taskId ?? null,
        agentType: data.agentType || 'coding',
        model: data.model ?? null,
        status: 'running',
        currentTool: null,
      })
      const tasks = new Map(state.tasks)
      if (data.taskId) {
        const task = tasks.get(data.taskId)
        if (task) tasks.set(data.taskId, { ...task, agentRunId: data.agentId })
      }
      return { agentRuns, tasks }
    })
  },

  handleAgentStopped: (data) => {
    set((state) => {
      const current = state.agentRuns.get(data.agentId)
      if (!current) return state
      const agentRuns = new Map(state.agentRuns)
      agentRuns.set(data.agentId, {
        ...current,
        status: stoppedStatus(data.status, data.reason),
        currentTool: null,
      })
      const rounds = current.status === 'running' && Number.isFinite(data.rounds)
        ? Math.max(0, data.rounds ?? 0)
        : 0
      return { agentRuns, totalRounds: state.totalRounds + rounds }
    })
  },

  handleToolStart: (data) => {
    set((state) => {
      const current = state.agentRuns.get(data.agentId)
      if (!current) return state
      const agentRuns = new Map(state.agentRuns)
      agentRuns.set(data.agentId, { ...current, currentTool: data.toolName })
      return { agentRuns }
    })
  },

  handleToolEnd: (data) => {
    set((state) => {
      const current = state.agentRuns.get(data.agentId)
      if (!current || current.currentTool !== data.toolName) return state
      const agentRuns = new Map(state.agentRuns)
      agentRuns.set(data.agentId, { ...current, currentTool: null })
      return { agentRuns }
    })
  },

  getTaskTree: (conversationId) =>
    Array.from(get().tasks.values()).filter((task) => task.conversationId === conversationId),

  getRunningAgents: () =>
    Array.from(get().agentRuns.values()).filter((agent) => agent.status === 'running'),

  loadTasks: async (conversationId) => {
    const items = await tasksApi.list(conversationId)
    set((state) => {
      const tasks = new Map(
        Array.from(state.tasks.entries()).filter(([, task]) => task.conversationId !== conversationId),
      )
      for (const item of items) {
        const status = asTaskStatus(item.status)
        if (!status) continue
        tasks.set(item.id, {
          id: item.id,
          conversationId: item.conversation_id,
          parentTaskId: item.parent_task_id,
          description: item.description,
          status,
          result: item.result,
          agentRunId: item.agent_run_id,
        })
      }
      return { tasks }
    })
  },

  cancelTask: async (taskId) => {
    await tasksApi.cancel(taskId)
    set((state) => {
      const tasks = new Map(state.tasks)
      const pending = [taskId]
      while (pending.length > 0) {
        const id = pending.pop()
        if (!id) continue
        const task = tasks.get(id)
        if (task && (task.status === 'pending' || task.status === 'running')) {
          tasks.set(id, { ...task, status: 'cancelled' })
        }
        for (const child of tasks.values()) {
          if (child.parentTaskId === id) pending.push(child.id)
        }
      }
      return { tasks }
    })
  },

  reset: () => set({ tasks: new Map(), agentRuns: new Map(), totalRounds: 0 }),
}))
