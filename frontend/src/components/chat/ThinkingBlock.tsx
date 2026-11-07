import { useState } from 'react'
import clsx from 'clsx'

interface ThinkingBlockProps {
  content: string
}

export function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-amber-200/80 bg-amber-50/60 dark:border-amber-500/20 dark:bg-amber-500/5">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
        className="group/thinking flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-amber-100/60 dark:hover:bg-amber-500/10"
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-amber-300/80 bg-white text-amber-600 shadow-sm dark:border-amber-500/30 dark:bg-neutral-900 dark:text-amber-300">
          <svg viewBox="0 0 24 24" className="size-3.5 fill-none stroke-current" strokeWidth="1.7">
            <path d="M9.2 18h5.6M10 21h4" />
            <path d="M8.4 15.4A7 7 0 1 1 15.6 15.4C14.6 16.1 14.4 17 14.4 18H9.6c0-1-.2-1.9-1.2-2.6Z" />
            <path d="M9.5 10.5 11 12l3.5-3.5" />
          </svg>
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-[11px] font-semibold tracking-[0.12em] text-amber-700 uppercase dark:text-amber-300">
            思考过程
          </span>
          <span className="truncate text-[11px] text-neutral-400">
            {expanded ? '收起模型推理轨迹' : '展开查看模型推理轨迹'}
          </span>
        </span>
        <svg
          viewBox="0 0 20 20"
          className={clsx(
            'size-4 fill-current text-amber-500 transition-transform duration-200',
            expanded && 'rotate-180',
          )}
        >
          <path d="M5.2 7.4a1 1 0 0 1 1.4-.1l3.4 3 3.4-3a1 1 0 1 1 1.3 1.5l-4 3.5a1 1 0 0 1-1.4 0l-4-3.5a1 1 0 0 1-.1-1.4Z" />
        </svg>
      </button>
      {expanded && (
        <div className="border-t border-amber-200/70 bg-white/60 px-4 py-3 text-[13px] leading-6 whitespace-pre-wrap text-neutral-600 dark:border-amber-500/15 dark:bg-black/10 dark:text-neutral-400">
          {content}
        </div>
      )}
    </div>
  )
}
