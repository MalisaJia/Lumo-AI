import { useEffect, useRef } from 'react'
import { useIdeStore } from '../../stores/ideStore'

export function TerminalPanel() {
  const terminalLines = useIdeStore((state) => state.terminalLines)
  const clearTerminal = useIdeStore((state) => state.clearTerminal)
  const outputRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const output = outputRef.current
    if (output) output.scrollTop = output.scrollHeight
  }, [terminalLines])

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-[#282436]/95 text-slate-200 dark:bg-[#211e30]/95">
      <header className="flex h-8 shrink-0 items-center border-b border-violet-400/20 bg-violet-400/10 px-3 text-xs text-violet-100 dark:bg-violet-900/20">
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <svg viewBox="0 0 20 20" className="size-3.5 fill-current text-violet-300" aria-hidden>
            <path d="M3.3 4.3a1 1 0 0 1 1.4 0l4 4a1 1 0 0 1 0 1.4l-4 4a1 1 0 0 1-1.4-1.4L6.6 9 3.3 5.7a1 1 0 0 1 0-1.4ZM10 14a1 1 0 0 1 1-1h5a1 1 0 1 1 0 2h-5a1 1 0 0 1-1-1Z" />
          </svg>
          <span className="font-medium">终端</span>
          {terminalLines.length > 0 && (
            <span className="rounded border border-violet-400/15 bg-violet-400/10 px-1.5 py-0.5 text-[10px] text-violet-200 tabular-nums">
              {terminalLines.length}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={clearTerminal}
          disabled={terminalLines.length === 0}
          title="清空终端"
          aria-label="清空终端"
          className="rounded p-1 text-violet-200/70 transition-colors enabled:hover:bg-violet-400/15 enabled:hover:text-violet-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/60 disabled:cursor-default disabled:opacity-30"
        >
          <svg viewBox="0 0 20 20" className="size-3.5 fill-current" aria-hidden>
            <path d="M7 3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1h3a1 1 0 1 1 0 2h-1l-.8 11.1A2 2 0 0 1 12.2 18H7.8a2 2 0 0 1-2-1.9L5 5H4a1 1 0 0 1 0-2h3Zm2 4a1 1 0 0 1 2 0v7a1 1 0 1 1-2 0V7Z" />
          </svg>
        </button>
      </header>

      <div
        ref={outputRef}
        role="log"
        aria-live="polite"
        aria-label="终端输出"
        tabIndex={0}
        style={{ scrollbarWidth: 'thin', scrollbarColor: 'rgba(167, 139, 250, 0.4) transparent' }}
        className="min-h-0 flex-1 overflow-y-auto bg-transparent p-3 font-mono text-xs leading-5 text-slate-200 selection:bg-violet-400/25 selection:text-slate-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet-300/30 focus-visible:ring-inset"
      >
        {terminalLines.length > 0 ? (
          terminalLines.map((line, index) => (
            <div key={`${index}-${line}`} className="min-h-5 whitespace-pre-wrap break-all">
              {line.startsWith('$ ') ? (
                <>
                  <span className="text-violet-400">$</span>
                  <span className="text-violet-200">{line.slice(1)}</span>
                </>
              ) : (
                line || ' '
              )}
            </div>
          ))
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-violet-200/70">
            <span className="flex size-8 items-center justify-center rounded-lg border border-violet-400/15 bg-violet-400/10 text-violet-300" aria-hidden="true">
              <svg viewBox="0 0 20 20" className="size-4 fill-none stroke-current" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="m5 6 4 4-4 4m6 0h4" />
              </svg>
            </span>
            <span>暂无输出</span>
          </div>
        )}
      </div>
    </section>
  )
}
