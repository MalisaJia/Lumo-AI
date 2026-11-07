import { useMemo, useState } from 'react'
import clsx from 'clsx'
import { useChatStore, type AgentStreamState } from '../../stores/chatStore'
import { useTaskStore, type AgentRunItem, type TaskItem } from '../../stores/taskStore'
import { toast } from '../../stores/toastStore'

const STATUS_LABELS: Record<TaskItem['status'], string> = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

function StatusIcon({ status }: { status: TaskItem['status'] }) {
  if (status === 'running') {
    return <span className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-blue-200 border-t-blue-500 dark:border-blue-950 dark:border-t-blue-400" />
  }
  if (status === 'completed') {
    return (
      <span className="flex size-3.5 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-[9px] font-bold text-white">✓</span>
    )
  }
  if (status === 'failed') {
    return <span className="flex size-3.5 shrink-0 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">×</span>
  }
  if (status === 'cancelled') {
    return <span className="flex size-3.5 shrink-0 items-center justify-center rounded-full border border-neutral-400 text-[10px] text-neutral-400">×</span>
  }
  return <span className="size-3.5 shrink-0 rounded-full border-2 border-neutral-300 dark:border-neutral-600" />
}

interface TaskBranchProps {
  task: TaskItem
  childrenByParent: Map<string, TaskItem[]>
  agents: AgentRunItem[]
  agentStreams: Map<string, AgentStreamState>
  cancellingId: string | null
  onCancel: (taskId: string) => void
}

function TaskBranch({ task, childrenByParent, agents, agentStreams, cancellingId, onCancel }: TaskBranchProps) {
  const children = childrenByParent.get(task.id) ?? []
  const activeAgent = agents.find((agent) => agent.taskId === task.id && agent.status === 'running')
  const agentStream = activeAgent ? agentStreams.get(activeAgent.id) : undefined
  const currentTool = agentStream?.currentTool ?? activeAgent?.currentTool
  const streamPreview = agentStream?.streamingContent.replace(/\s+/g, ' ').trim().slice(-100) ?? ''
  const cancellable = task.status === 'pending' || task.status === 'running'

  return (
    <div>
      <div className="group flex min-w-0 items-start gap-2 rounded-lg px-2 py-2 transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-800/70">
        <span className="mt-0.5" title={STATUS_LABELS[task.status]}>
          <StatusIcon status={task.status} />
        </span>
        <div className="min-w-0 flex-1">
          <p className={clsx(
            'break-words text-xs leading-4',
            task.status === 'cancelled' ? 'text-neutral-400 line-through' : 'text-neutral-700 dark:text-neutral-200',
          )}>
            {task.description}
          </p>
          {task.status === 'running' && activeAgent && (
            <div className="mt-1.5 overflow-hidden rounded-md border border-blue-200/70 bg-blue-50/70 dark:border-blue-900/70 dark:bg-blue-950/25">
              <div className="flex min-w-0 items-center gap-1.5 px-2 py-1 font-mono text-[10px] text-blue-700 dark:text-blue-300">
                <span className="flex h-2.5 shrink-0 items-end gap-0.5" aria-label="Agent 正在执行">
                  {[0, 1, 2].map((index) => (
                    <span
                      key={index}
                      className="h-full w-0.5 animate-pulse rounded-full bg-blue-500"
                      style={{ animationDelay: `${index * 160}ms` }}
                    />
                  ))}
                </span>
                <span className="shrink-0 text-blue-500/70">LIVE</span>
                <span className="truncate">{currentTool ?? '处理中'}</span>
              </div>
              {streamPreview && (
                <p
                  className="border-t border-blue-200/60 px-2 py-1.5 font-mono text-[10px] leading-4 text-neutral-600 dark:border-blue-900/60 dark:text-neutral-300"
                  title={streamPreview}
                >
                  …{streamPreview}
                </p>
              )}
            </div>
          )}
        </div>
        {cancellable && (
          <button
            type="button"
            onClick={() => onCancel(task.id)}
            disabled={cancellingId === task.id}
            title="取消任务"
            aria-label={'取消任务：' + task.description}
            className="shrink-0 rounded-md px-1.5 py-0.5 text-[11px] text-neutral-400 opacity-0 transition hover:bg-red-50 hover:text-red-500 disabled:opacity-40 group-hover:opacity-100 focus:opacity-100 dark:hover:bg-red-500/10"
          >
            {cancellingId === task.id ? '…' : '取消'}
          </button>
        )}
      </div>
      {children.length > 0 && (
        <div className="ml-4 border-l border-neutral-200 pl-1 dark:border-neutral-700">
          {children.map((child) => (
            <TaskBranch
              key={child.id}
              task={child}
              childrenByParent={childrenByParent}
              agents={agents}
              agentStreams={agentStreams}
              cancellingId={cancellingId}
              onCancel={onCancel}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function TaskTreePanel() {
  const conversationId = useChatStore((state) => state.currentId)
  const agentStreamsMap = useChatStore((state) => state.agentStreams)
  const tasksMap = useTaskStore((state) => state.tasks)
  const agentRunsMap = useTaskStore((state) => state.agentRuns)
  const [cancellingId, setCancellingId] = useState<string | null>(null)

  const tasks = useMemo(
    () => Array.from(tasksMap.values()).filter((task) => task.conversationId === conversationId),
    [conversationId, tasksMap],
  )
  const agents = useMemo(() => Array.from(agentRunsMap.values()), [agentRunsMap])
  const { roots, childrenByParent } = useMemo(() => {
    const ids = new Set(tasks.map((task) => task.id))
    const children = new Map<string, TaskItem[]>()
    const rootTasks: TaskItem[] = []
    for (const task of tasks) {
      if (!task.parentTaskId || !ids.has(task.parentTaskId)) {
        rootTasks.push(task)
        continue
      }
      const siblings = children.get(task.parentTaskId) ?? []
      siblings.push(task)
      children.set(task.parentTaskId, siblings)
    }
    return { roots: rootTasks, childrenByParent: children }
  }, [tasks])

  const handleCancel = async (taskId: string) => {
    setCancellingId(taskId)
    try {
      await useTaskStore.getState().cancelTask(taskId)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '取消任务失败')
    } finally {
      setCancellingId(null)
    }
  }

  return (
    <aside className="flex h-full min-h-0 flex-col bg-neutral-50 dark:bg-neutral-900">
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-neutral-200 px-3 dark:border-neutral-800">
        <span className="relative flex size-4 items-center justify-center" aria-hidden>
          <span className="absolute size-3 rounded-sm border border-blue-500" />
          <span className="absolute -bottom-0.5 -right-0.5 size-1.5 rounded-full bg-emerald-500 ring-2 ring-neutral-50 dark:ring-neutral-900" />
        </span>
        <span className="text-xs font-medium text-neutral-700 dark:text-neutral-200">任务树</span>
        <span className="ml-auto rounded-full bg-neutral-200 px-1.5 py-0.5 font-mono text-[10px] leading-none text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
          {tasks.length}
        </span>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {roots.length > 0 ? (
          roots.map((task) => (
            <TaskBranch
              key={task.id}
              task={task}
              childrenByParent={childrenByParent}
              agents={agents}
              agentStreams={agentStreamsMap}
              cancellingId={cancellingId}
              onCancel={(id) => void handleCancel(id)}
            />
          ))
        ) : (
          <div className="flex h-full min-h-32 flex-col items-center justify-center gap-2 text-neutral-400">
            <span className="size-5 rounded-full border border-dashed border-neutral-300 dark:border-neutral-700" />
            <p className="text-xs">暂无任务</p>
          </div>
        )}
      </div>
    </aside>
  )
}
