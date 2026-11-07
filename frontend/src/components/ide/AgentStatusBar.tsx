import { useMemo } from 'react'
import { useTaskStore } from '../../stores/taskStore'

export function AgentStatusBar() {
  const agentRuns = useTaskStore((state) => state.agentRuns)
  const totalRounds = useTaskStore((state) => state.totalRounds)
  const runningAgents = useMemo(
    () => Array.from(agentRuns.values()).filter((agent) => agent.status === 'running'),
    [agentRuns],
  )
  const tools = useMemo(
    () => Array.from(new Set(runningAgents.map((agent) => agent.currentTool).filter(Boolean))),
    [runningAgents],
  )

  return (
    <footer
      aria-live="polite"
      className="flex h-7 shrink-0 items-center gap-3 border-t border-neutral-200 bg-neutral-100 px-3 font-mono text-[10px] text-neutral-500 dark:border-neutral-800 dark:bg-neutral-950 dark:text-neutral-400"
    >
      <span className="flex shrink-0 items-center gap-1.5">
        <span className={runningAgents.length > 0 ? 'size-1.5 animate-pulse rounded-full bg-emerald-500' : 'size-1.5 rounded-full bg-neutral-400'} />
        {runningAgents.length} {runningAgents.length === 1 ? 'agent' : 'agents'} running
      </span>
      <span className="h-3 w-px bg-neutral-300 dark:bg-neutral-700" />
      <span className="min-w-0 flex-1 truncate" title={tools.join(', ')}>
        {tools.length > 0 ? 'tool: ' + tools.join(', ') : 'tool: idle'}
      </span>
      <span className="shrink-0 tabular-nums">{totalRounds} rounds</span>
    </footer>
  )
}
