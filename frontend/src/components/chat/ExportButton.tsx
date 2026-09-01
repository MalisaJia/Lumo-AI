// 顶栏导出按钮：下拉选择 PDF/PPTX 格式，导出期间显示 loading
import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '../../stores/chatStore'

export function ExportButton() {
  const [open, setOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const currentId = useChatStore((s) => s.currentId)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const handleExport = async (format: 'pdf' | 'pptx') => {
    setOpen(false)
    setExporting(true)
    try {
      await useChatStore.getState().exportConversation(format)
    } finally {
      setExporting(false)
    }
  }

  if (!currentId) return null

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={exporting}
        title="导出会话"
        className="rounded-lg p-2 text-neutral-500 transition-colors hover:bg-neutral-100 disabled:cursor-not-allowed dark:text-neutral-400 dark:hover:bg-neutral-800"
      >
        {exporting ? (
          <svg className="size-4.5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <svg viewBox="0 0 20 20" className="size-4.5 fill-current">
            <path d="M10 3a1 1 0 0 1 1 1v7.586l2.293-2.293a1 1 0 1 1 1.414 1.414l-4 4a1 1 0 0 1-1.414 0l-4-4a1 1 0 0 1 1.414-1.414L9 11.586V4a1 1 0 0 1 1-1zM4 16a1 1 0 1 0 0 2h12a1 1 0 1 0 0-2H4z" />
          </svg>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-36 rounded-xl border border-neutral-200 bg-white p-1.5 shadow-lg dark:border-neutral-700 dark:bg-neutral-800">
          <button
            onClick={() => handleExport('pdf')}
            className="flex w-full items-center rounded-lg px-2.5 py-1.5 text-left text-sm text-neutral-700 transition-colors hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-700"
          >
            导出 PDF
          </button>
          <button
            onClick={() => handleExport('pptx')}
            className="flex w-full items-center rounded-lg px-2.5 py-1.5 text-left text-sm text-neutral-700 transition-colors hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-700"
          >
            导出 PPTX
          </button>
        </div>
      )}
    </div>
  )
}
