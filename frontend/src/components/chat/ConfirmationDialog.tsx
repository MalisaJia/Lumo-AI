import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import clsx from 'clsx'
import { confirmAction } from '../../api/client'
import {
  type ConfirmationRiskLevel,
  useConfirmationStore,
} from '../../stores/confirmationStore'
import { toast } from '../../stores/toastStore'

const CONFIRMATION_TIMEOUT_MS = 60_000

const RISK_META: Record<
  ConfirmationRiskLevel,
  { label: string; badge: string; accent: string; progress: string }
> = {
  low: {
    label: '低风险 · Low',
    badge: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300',
    accent: 'bg-emerald-500',
    progress: 'bg-emerald-500',
  },
  medium: {
    label: '中风险 · Medium',
    badge: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300',
    accent: 'bg-amber-500',
    progress: 'bg-amber-500',
  },
  high: {
    label: '高风险 · High',
    badge: 'border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-500/30 dark:bg-orange-500/10 dark:text-orange-300',
    accent: 'bg-orange-500',
    progress: 'bg-orange-500',
  },
  critical: {
    label: '严重风险 · Critical',
    badge: 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300',
    accent: 'bg-red-500',
    progress: 'bg-red-500',
  },
}

function screenshotSource(value: string): string {
  return value.startsWith('data:') ? value : `data:image/png;base64,${value}`
}

export default function ConfirmationDialog() {
  const pending = useConfirmationStore((state) => state.pending)
  const [reason, setReason] = useState('')
  const [remaining, setRemaining] = useState(60)
  const [submitting, setSubmitting] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const respondingRef = useRef(false)

  useEffect(() => {
    if (!pending) return

    respondingRef.current = false
    setReason('')
    setSubmitting(false)
    setRemaining(
      Math.max(0, Math.ceil((pending.timestamp + CONFIRMATION_TIMEOUT_MS - Date.now()) / 1000)),
    )
    const frame = requestAnimationFrame(() => dialogRef.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [pending])

  useEffect(() => {
    if (!pending) return

    const root = document.getElementById('root')
    const previousOverflow = document.body.style.overflow
    const wasInert = root?.inert ?? false
    document.body.style.overflow = 'hidden'
    if (root) root.inert = true

    return () => {
      document.body.style.overflow = previousOverflow
      if (root) root.inert = wasInert
    }
  }, [pending])

  useEffect(() => {
    if (!pending) return

    const expiresAt = pending.timestamp + CONFIRMATION_TIMEOUT_MS
    const autoDeny = () => {
      const store = useConfirmationStore.getState()
      if (store.pending?.id !== pending.id || respondingRef.current) return

      respondingRef.current = true
      store.setPending(null)
      void confirmAction(pending.id, false, 'Confirmation timed out after 60 seconds').catch((error) => {
        toast.error(error instanceof Error ? error.message : '自动拒绝操作失败')
      })
    }
    const updateCountdown = () => {
      const seconds = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000))
      setRemaining(seconds)
      if (seconds === 0) autoDeny()
    }

    updateCountdown()
    const interval = window.setInterval(updateCountdown, 250)
    const timeout = window.setTimeout(autoDeny, Math.max(0, expiresAt - Date.now()))
    return () => {
      window.clearInterval(interval)
      window.clearTimeout(timeout)
    }
  }, [pending])

  useEffect(() => {
    if (!pending) return

    const keepFocusInside = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      )
      if (focusable.length === 0) {
        event.preventDefault()
        dialogRef.current.focus()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', keepFocusInside)
    return () => document.removeEventListener('keydown', keepFocusInside)
  }, [pending])

  if (!pending) return null

  const risk = RISK_META[pending.risk_level]
  const progress = Math.max(0, Math.min(100, (remaining / 60) * 100))

  const respond = async (approved: boolean) => {
    if (respondingRef.current) return

    respondingRef.current = true
    setSubmitting(true)
    try {
      await confirmAction(pending.id, approved, approved ? '' : reason.trim())
      const store = useConfirmationStore.getState()
      if (store.pending?.id === pending.id) store.setPending(null)
    } catch (error) {
      respondingRef.current = false
      setSubmitting(false)
      toast.error(error instanceof Error ? error.message : '提交确认失败')
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-120 flex items-center justify-center bg-neutral-950/60 p-4 backdrop-blur-[3px]">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirmation-title"
        aria-describedby="confirmation-description"
        tabIndex={-1}
        className="relative max-h-[calc(100vh-2rem)] w-full max-w-xl overflow-y-auto rounded-2xl border border-neutral-200/90 bg-white shadow-[0_28px_80px_-20px_rgba(0,0,0,0.55)] outline-none dark:border-neutral-700 dark:bg-neutral-900"
      >
        <div className={clsx('absolute inset-x-0 top-0 h-1', risk.accent)} />

        <div className="border-b border-neutral-200 px-5 pb-4 pt-5 dark:border-neutral-800 sm:px-6">
          <div className="flex items-start gap-4">
            <div className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-neutral-200 bg-neutral-50 text-neutral-700 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200">
              <svg viewBox="0 0 24 24" className="size-5 fill-none stroke-current" strokeWidth="1.8" aria-hidden="true">
                <path d="M12 3 4.5 6v5.4c0 4.6 3.1 8.5 7.5 9.6 4.4-1.1 7.5-5 7.5-9.6V6L12 3Z" />
                <path d="M12 8v5M12 16.5v.1" strokeLinecap="round" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 id="confirmation-title" className="text-lg font-semibold tracking-tight text-neutral-950 dark:text-white">
                    操作确认
                  </h2>
                  <p className="mt-0.5 text-xs font-medium uppercase tracking-[0.14em] text-neutral-400">
                    Action Confirmation
                  </p>
                </div>
                <span className={clsx('rounded-full border px-2.5 py-1 text-xs font-semibold', risk.badge)}>
                  {risk.label}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-5 px-5 py-5 sm:px-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-neutral-400">Requested action</p>
            <p className="mt-2 inline-flex max-w-full rounded-lg bg-neutral-100 px-3 py-1.5 font-mono text-sm font-medium text-neutral-800 dark:bg-neutral-800 dark:text-neutral-100">
              {pending.action}
            </p>
            <p id="confirmation-description" className="mt-3 text-sm leading-6 text-neutral-600 dark:text-neutral-300">
              {pending.description}
            </p>
          </div>

          {pending.screenshot_base64 && (
            <figure className="rounded-xl border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-700 dark:bg-neutral-800/60">
              <figcaption className="mb-2 text-xs font-medium text-neutral-500 dark:text-neutral-400">操作预览 · Screenshot</figcaption>
              <img
                src={screenshotSource(pending.screenshot_base64)}
                alt="待确认操作的屏幕截图"
                className="max-h-36 w-full max-w-[200px] rounded-lg border border-neutral-200 object-contain shadow-sm dark:border-neutral-700"
              />
            </figure>
          )}

          <label className="block">
            <span className="text-sm font-medium text-neutral-700 dark:text-neutral-200">拒绝原因（选填） · Deny reason</span>
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={submitting}
              placeholder="可选：说明拒绝此次操作的原因"
              className="mt-2 w-full rounded-xl border border-neutral-300 bg-white px-3.5 py-2.5 text-sm text-neutral-900 outline-none transition focus:border-neutral-500 focus:ring-3 focus:ring-neutral-200/70 disabled:cursor-not-allowed disabled:opacity-60 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100 dark:placeholder:text-neutral-500 dark:focus:border-neutral-500 dark:focus:ring-neutral-700/60"
            />
          </label>

          <div aria-live="polite" className="rounded-xl border border-neutral-200 bg-neutral-50 px-3.5 py-3 dark:border-neutral-700 dark:bg-neutral-800/60">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="text-neutral-500 dark:text-neutral-400">超时后将自动拒绝</span>
              <span className={clsx('font-mono text-base font-bold tabular-nums', remaining <= 10 ? 'text-red-600 dark:text-red-400' : 'text-neutral-800 dark:text-neutral-100')}>
                {remaining}s
              </span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
              <div className={clsx('h-full rounded-full transition-[width] duration-200', risk.progress)} style={{ width: `${progress}%` }} />
            </div>
          </div>
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-neutral-200 bg-neutral-50/80 px-5 py-4 dark:border-neutral-800 dark:bg-neutral-950/30 sm:flex-row sm:justify-end sm:px-6">
          <button
            type="button"
            onClick={() => void respond(false)}
            disabled={submitting}
            className="rounded-xl border border-neutral-300 bg-white px-4 py-2.5 text-sm font-semibold text-neutral-700 transition hover:border-red-300 hover:bg-red-50 hover:text-red-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200 dark:hover:border-red-500/50 dark:hover:bg-red-500/10 dark:hover:text-red-300"
          >
            拒绝 (Deny)
          </button>
          <button
            type="button"
            onClick={() => void respond(true)}
            disabled={submitting}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-emerald-500 dark:text-emerald-950 dark:hover:bg-emerald-400"
          >
            {submitting && <span className="size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" />}
            允许 (Approve)
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
