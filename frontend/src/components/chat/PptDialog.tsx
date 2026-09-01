// 制作 PPT 对话框：输入主题 + 可选参考文本，提交后等待后端生成并自动下载 .pptx
import { useEffect, useState } from 'react'
import { pptApi } from '../../api/client'
import { toast } from '../../stores/toastStore'

interface PptDialogProps {
  initialReference?: string // 从聊天输入框预填充的参考文本
  onClose: () => void
}

export function PptDialog({ initialReference, onClose }: PptDialogProps) {
  const [topic, setTopic] = useState('')
  const [reference, setReference] = useState(initialReference ?? '')
  const [loading, setLoading] = useState(false)

  // Escape 关闭对话框（生成中不允许关闭，避免误操作丢失等待进度）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [loading, onClose])

  const handleGenerate = async () => {
    const trimmed = topic.trim()
    if (!trimmed || loading) return
    setLoading(true)
    try {
      const blob = await pptApi.generate({
        topic: trimmed,
        referenceText: reference.trim() || undefined,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${trimmed}.pptx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast.success('PPT 已生成')
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'PPT 生成失败')
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => !loading && onClose()}
    >
      <div
        className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl dark:bg-neutral-800"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-neutral-800 dark:text-neutral-100">
          制作 PPT
        </h2>
        <div className="mt-4 flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-neutral-600 dark:text-neutral-300">主题</span>
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={loading}
              autoFocus
              placeholder="例：Q3 季度销售汇报"
              className="rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-800 outline-none transition-colors placeholder:text-neutral-400 focus:border-violet-400 disabled:opacity-60 dark:border-neutral-600 dark:bg-neutral-700/40 dark:text-neutral-200 dark:focus:border-violet-500"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-neutral-600 dark:text-neutral-300">
              参考文本（选填）
            </span>
            <textarea
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              disabled={loading}
              rows={6}
              placeholder="粘贴或输入参考材料，AI 将基于此内容生成 PPT"
              className="max-h-[200px] resize-none overflow-y-auto rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm leading-6 text-neutral-800 outline-none transition-colors placeholder:text-neutral-400 focus:border-violet-400 disabled:opacity-60 dark:border-neutral-600 dark:bg-neutral-700/40 dark:text-neutral-200 dark:focus:border-violet-500"
            />
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="rounded-lg border border-neutral-300 px-4 py-2 text-sm text-neutral-600 transition-colors hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-700"
          >
            取消
          </button>
          <button
            onClick={handleGenerate}
            disabled={!topic.trim() || loading}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-violet-500 to-blue-500 px-4 py-2 text-sm text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {loading ? (
              <>
                <span className="size-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                正在生成…（约 20 秒）
              </>
            ) : (
              '生成 PPT'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
