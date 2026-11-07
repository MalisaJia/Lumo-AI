interface UserQuestionProps {
  question: string
  options: Array<{ label: string; description?: string }>
  onSelect: (label: string) => void
}

export function UserQuestion({ question, options, onSelect }: UserQuestionProps) {
  return (
    <section className="my-3 overflow-hidden rounded-2xl border border-violet-200 bg-[linear-gradient(135deg,rgba(245,243,255,0.95),rgba(239,246,255,0.72))] shadow-[0_10px_32px_-24px_rgba(109,40,217,0.8)] dark:border-violet-500/25 dark:bg-[linear-gradient(135deg,rgba(76,29,149,0.18),rgba(30,58,138,0.12))]">
      <div className="flex items-start gap-3 border-b border-violet-200/70 px-4 py-3 dark:border-violet-500/15">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-violet-600 text-white shadow-sm shadow-violet-500/30">
          <svg viewBox="0 0 24 24" className="size-4 fill-none stroke-current" strokeWidth="1.8">
            <path d="M5 5h14v11H9l-4 3V5Z" />
            <path d="M9.5 9.5a2.5 2.5 0 1 1 4 2c-1 .7-1.5 1.1-1.5 2" />
            <path d="M12 15.5h.01" />
          </svg>
        </span>
        <div>
          <p className="text-[10px] font-semibold tracking-[0.16em] text-violet-500 uppercase dark:text-violet-300">
            需要你的确认
          </p>
          <p className="mt-1 text-sm font-medium leading-6 text-neutral-800 dark:text-neutral-100">
            {question}
          </p>
        </div>
      </div>
      <div className="grid gap-2 p-3 sm:grid-cols-2">
        {options.map((option, index) => (
          <button
            key={option.label}
            type="button"
            onClick={() => onSelect(option.label)}
            className="group/option flex min-w-0 items-start gap-2.5 rounded-xl border border-violet-200/90 bg-white/80 px-3 py-2.5 text-left transition-all hover:-translate-y-0.5 hover:border-violet-400 hover:bg-white hover:shadow-md hover:shadow-violet-500/10 dark:border-violet-500/20 dark:bg-neutral-900/55 dark:hover:border-violet-400/50 dark:hover:bg-neutral-900"
          >
            <span className="flex size-5 shrink-0 items-center justify-center rounded-md bg-violet-100 text-[10px] font-bold text-violet-600 transition-colors group-hover/option:bg-violet-600 group-hover/option:text-white dark:bg-violet-500/15 dark:text-violet-300">
              {String.fromCharCode(65 + index)}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium text-neutral-700 dark:text-neutral-200">
                {option.label}
              </span>
              {option.description && (
                <span className="mt-0.5 block text-xs leading-5 text-neutral-400">
                  {option.description}
                </span>
              )}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}
