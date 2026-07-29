// Toast 容器：固定右上角展示
import clsx from 'clsx'
import { useToastStore } from '../../stores/toastStore'

const typeStyles = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  error: 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300',
  info: 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300',
} as const

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-100 flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={clsx(
            'pointer-events-auto cursor-pointer rounded-xl border px-4 py-3 text-sm shadow-lg backdrop-blur transition-all',
            typeStyles[t.type],
          )}
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}
