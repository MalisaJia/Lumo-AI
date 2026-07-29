// 顶栏模型选择器：provider/model 两级下拉，选择后 PATCH 会话
import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { useChatStore } from '../../stores/chatStore'
import { useSettingsStore } from '../../stores/settingsStore'

export function ModelSelector() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const providers = useSettingsStore((s) => s.providers)
  const currentId = useChatStore((s) => s.currentId)
  const conversations = useChatStore((s) => s.conversations)

  const conv = conversations.find((c) => c.id === currentId)
  const currentProvider = providers.find((p) => p.id === conv?.providerId)
  const currentModel = currentProvider?.models.find((m) => m.name === conv?.modelName)
  const label = currentModel
    ? currentModel.label || currentModel.name
    : conv?.modelName || '选择模型'

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const handleSelect = (providerId: string, modelName: string) => {
    setOpen(false)
    useChatStore.getState().updateConversationModel(providerId, modelName)
  }

  if (!currentId) return null

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800"
      >
        {currentProvider && (
          <span className="text-neutral-400 dark:text-neutral-500">{currentProvider.name} /</span>
        )}
        <span>{label}</span>
        <svg viewBox="0 0 20 20" className={clsx('size-4 fill-current text-neutral-400 transition-transform', open && 'rotate-180')}>
          <path d="M5.3 7.7a1 1 0 0 1 1.4 0L10 11l3.3-3.3a1 1 0 1 1 1.4 1.4l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 0 1 0-1.4z" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 max-h-96 w-72 overflow-y-auto rounded-xl border border-neutral-200 bg-white p-1.5 shadow-lg dark:border-neutral-700 dark:bg-neutral-800">
          {providers.length === 0 ? (
            <p className="px-3 py-4 text-center text-sm text-neutral-400">
              暂无可用模型，请先在设置中添加服务商
            </p>
          ) : (
            providers.map((p) => (
              <div key={p.id} className="mb-1 last:mb-0">
                <div className="px-2.5 py-1 text-xs font-semibold text-neutral-400 dark:text-neutral-500">
                  {p.name}
                </div>
                {p.models.map((m) => {
                  const active = conv?.providerId === p.id && conv?.modelName === m.name
                  return (
                    <button
                      key={m.id}
                      onClick={() => handleSelect(p.id, m.name)}
                      className={clsx(
                        'flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors',
                        active
                          ? 'bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300'
                          : 'text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-700',
                      )}
                    >
                      <span className="truncate">{m.label || m.name}</span>
                      {active && (
                        <svg viewBox="0 0 20 20" className="size-4 shrink-0 fill-current">
                          <path d="M16.7 5.3a1 1 0 0 1 0 1.4l-8 8a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L8 12.6l7.3-7.3a1 1 0 0 1 1.4 0z" />
                        </svg>
                      )}
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
