// 单条消息气泡（React.memo：流式时只有生成中的消息重渲）
import { memo, useState } from 'react'
import clsx from 'clsx'
import type { Attachment, Message, SourceRef } from '../../api/types'
import { MarkdownRenderer } from '../markdown/MarkdownRenderer'
import { useChatStore } from '../../stores/chatStore'
import { toast } from '../../stores/toastStore'

interface MessageItemProps {
  message: Message
  isLastAssistant: boolean
  isStreamingThis: boolean
}

function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

// 可折叠「参考来源」面板（默认收起）
function SourcesPanel({ sources }: { sources: SourceRef[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-2 border-t border-neutral-100 pt-2 dark:border-neutral-700/60">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-neutral-400 transition-colors hover:text-violet-500 dark:hover:text-violet-300"
      >
        <svg
          viewBox="0 0 20 20"
          className={clsx('size-3 fill-current transition-transform', open && 'rotate-90')}
        >
          <path d="M7.3 5.3a1 1 0 0 1 1.4 0l4 4a1 1 0 0 1 0 1.4l-4 4a1 1 0 1 1-1.4-1.4L10.6 10 7.3 6.7a1 1 0 0 1 0-1.4z" />
        </svg>
        参考来源 ({sources.length})
      </button>
      {open && (
        <ul className="mt-1.5 flex flex-col gap-1">
          {sources.map((s) => (
            <li key={s.id}>
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="group/src flex items-baseline gap-2 rounded-lg px-2 py-1 text-xs transition-colors hover:bg-neutral-50 dark:hover:bg-neutral-700/50"
              >
                <span className="flex size-4 shrink-0 translate-y-0.5 items-center justify-center rounded-full bg-violet-100 text-[10px] font-medium text-violet-600 dark:bg-violet-500/20 dark:text-violet-300">
                  {s.id}
                </span>
                <span className="min-w-0 truncate text-neutral-600 group-hover/src:text-violet-600 dark:text-neutral-300 dark:group-hover/src:text-violet-300">
                  {s.title}
                </span>
                <span className="shrink-0 text-neutral-400">{hostnameOf(s.url)}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// 图片附件缩略图网格 + 点击全屏 lightbox（默认关闭，不引入新依赖）
function AttachmentGrid({ attachments }: { attachments: Attachment[] }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  return (
    <>
      <div className="flex flex-wrap justify-end gap-1.5">
        {attachments.map((a) => (
          <button key={a.id} onClick={() => setPreviewUrl(a.url)} title={a.fileName || '查看图片'}>
            <img
              src={a.url}
              alt={a.fileName || '图片附件'}
              loading="lazy"
              className="max-h-[200px] max-w-[200px] cursor-zoom-in rounded-xl border border-neutral-200 object-cover shadow-sm transition-opacity hover:opacity-90 dark:border-neutral-700"
            />
          </button>
        ))}
      </div>
      {previewUrl && (
        <div
          onClick={() => setPreviewUrl(null)}
          className="fixed inset-0 z-50 flex cursor-zoom-out items-center justify-center bg-black/80 p-6"
        >
          <img
            src={previewUrl}
            alt="图片预览"
            className="max-h-full max-w-full rounded-lg object-contain"
          />
        </div>
      )}
    </>
  )
}

function MessageItemInner({ message, isLastAssistant, isStreamingThis }: MessageItemProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const isUser = message.role === 'user'
  // 全局流式中：编辑/重新生成不可用（editMessage/regenerate 会直接 return，避免误导）
  const streaming = useChatStore((s) => s.streaming)
  // 仅生成中的消息关心搜索阶段，避免其他消息重渲
  const searchStage = useChatStore((s) => (isStreamingThis ? s.searchStage : null))
  // 搜索降级提示：只挂在当次会话最后一条助手消息上
  const searchNotice = useChatStore((s) =>
    !isUser && isLastAssistant ? s.searchNotice : null,
  )

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      toast.success('已复制到剪贴板')
    } catch {
      toast.error('复制失败')
    }
  }

  const handleStartEdit = () => {
    setDraft(message.content)
    setEditing(true)
  }

  const handleSaveEdit = () => {
    const content = draft.trim()
    if (!content) return
    setEditing(false)
    useChatStore.getState().editMessage(message.id, content)
  }

  const handleRegenerate = () => {
    useChatStore.getState().regenerate()
  }

  return (
    <div className={clsx('group flex gap-3 px-4 py-3', isUser && 'flex-row-reverse')}>
      {/* 头像 */}
      {isUser ? (
        <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full bg-neutral-200 text-sm font-semibold text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300">
          我
        </div>
      ) : (
        <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-blue-500 text-sm font-bold text-white shadow-sm">
          L
        </div>
      )}

      <div className={clsx('flex min-w-0 max-w-[85%] flex-col gap-1', isUser && 'items-end')}>
        {editing ? (
          <div className="w-full min-w-[280px] rounded-2xl border border-violet-300 bg-white p-3 shadow-sm dark:border-violet-700 dark:bg-neutral-800">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={Math.min(10, Math.max(3, draft.split('\n').length))}
              autoFocus
              className="w-full resize-y bg-transparent text-[15px] leading-6 text-neutral-800 outline-none dark:text-neutral-200"
            />
            <div className="mt-2 flex justify-end gap-2">
              <button
                onClick={() => setEditing(false)}
                className="rounded-lg px-3 py-1.5 text-sm text-neutral-500 transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-700"
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={!draft.trim()}
                className="rounded-lg bg-gradient-to-r from-violet-500 to-blue-500 px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                保存并重新生成
              </button>
            </div>
          </div>
        ) : isUser ? (
          <div className="flex max-w-full flex-col items-end gap-1.5">
            {!!message.attachments?.length && (
              <AttachmentGrid attachments={message.attachments} />
            )}
            {message.content && (
              <div className="rounded-2xl rounded-tr-md bg-gradient-to-br from-violet-500 to-blue-500 px-4 py-2.5 text-[15px] leading-7 whitespace-pre-wrap break-words text-white shadow-sm">
                {message.content}
              </div>
            )}
          </div>
        ) : (
          <div className="w-full rounded-2xl rounded-tl-md border border-neutral-200 bg-white px-4 py-2 shadow-sm dark:border-neutral-700 dark:bg-neutral-800">
            {searchNotice && (
              // 搜索降级提示条（仅当次流式会话内展示）
              <div className="mt-1.5 mb-1 rounded-lg bg-neutral-100 px-2.5 py-1.5 text-xs text-neutral-500 dark:bg-neutral-700/50 dark:text-neutral-400">
                {searchNotice === 'noResults'
                  ? '联网搜索未找到相关结果，以下回答基于模型自身知识'
                  : '模型判断此问题无需联网搜索'}
              </div>
            )}
            {message.content ? (
              <MarkdownRenderer content={message.content} citations={!!message.sources?.length} />
            ) : isStreamingThis && searchStage ? (
              // 联网搜索阶段提示（轻微脉冲动画）
              <div className="flex items-center gap-2 py-2 text-sm text-violet-500 dark:text-violet-300">
                <svg
                  viewBox="0 0 24 24"
                  className="size-4 animate-pulse fill-none stroke-current"
                  strokeWidth="1.8"
                >
                  <circle cx="12" cy="12" r="9" />
                  <path d="M3 12h18M12 3c2.5 2.4 3.8 5.6 3.8 9S14.5 18.6 12 21c-2.5-2.4-3.8-5.6-3.8-9S9.5 5.4 12 3z" />
                </svg>
                <span className="animate-pulse">
                  {searchStage === 'searching' ? '正在联网搜索…' : '正在阅读网页…'}
                </span>
              </div>
            ) : isStreamingThis ? (
              <div className="flex items-center gap-1.5 py-2">
                <span className="size-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:0ms]" />
                <span className="size-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:150ms]" />
                <span className="size-1.5 animate-bounce rounded-full bg-blue-400 [animation-delay:300ms]" />
              </div>
            ) : (
              <p className="py-1 text-sm text-neutral-400">（空回复）</p>
            )}
            {isStreamingThis && message.content && (
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-violet-400 align-text-bottom" />
            )}
            {!!message.sources?.length && !isStreamingThis && (
              <SourcesPanel sources={message.sources} />
            )}
          </div>
        )}

        {/* hover 操作栏 */}
        {!editing && !isStreamingThis && (
          <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={handleCopy}
              title="复制"
              className="rounded-md px-2 py-1 text-xs text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-600 dark:hover:bg-neutral-800 dark:hover:text-neutral-300"
            >
              复制
            </button>
            {isUser && !streaming && (
              <button
                onClick={handleStartEdit}
                title="编辑"
                className="rounded-md px-2 py-1 text-xs text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-600 dark:hover:bg-neutral-800 dark:hover:text-neutral-300"
              >
                编辑
              </button>
            )}
            {isLastAssistant && (
              <button
                onClick={handleRegenerate}
                title="重新生成"
                className="rounded-md px-2 py-1 text-xs text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-600 dark:hover:bg-neutral-800 dark:hover:text-neutral-300"
              >
                重新生成
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export const MessageItem = memo(MessageItemInner)
