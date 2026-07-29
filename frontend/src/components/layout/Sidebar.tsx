// 侧边栏：新建对话、搜索（防抖 300ms）、会话列表（行内重命名/删除二次确认）、设置入口
import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { useChatStore } from '../../stores/chatStore'
import { useSettingsStore } from '../../stores/settingsStore'
import type { Conversation } from '../../api/types'

function ConversationRow({ conv }: { conv: Conversation }) {
  const currentId = useChatStore((s) => s.currentId)
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState(conv.title)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const active = conv.id === currentId

  const submitRename = () => {
    setRenaming(false)
    const t = title.trim()
    if (t && t !== conv.title) {
      useChatStore.getState().renameConversation(conv.id, t)
    } else {
      setTitle(conv.title)
    }
  }

  return (
    <div
      className={clsx(
        'group relative flex items-center rounded-xl transition-colors',
        active
          ? 'bg-violet-50 dark:bg-violet-500/15'
          : 'hover:bg-neutral-100 dark:hover:bg-neutral-800',
      )}
    >
      {renaming ? (
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={submitRename}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submitRename()
            if (e.key === 'Escape') {
              setTitle(conv.title)
              setRenaming(false)
            }
          }}
          autoFocus
          className="mx-1 my-1 w-full rounded-lg border border-violet-400 bg-white px-2 py-1 text-sm text-neutral-800 outline-none dark:bg-neutral-800 dark:text-neutral-200"
        />
      ) : (
        <>
          <button
            onClick={() => useChatStore.getState().selectConversation(conv.id)}
            className={clsx(
              'flex-1 truncate px-3 py-2 text-left text-sm',
              active
                ? 'font-medium text-violet-700 dark:text-violet-300'
                : 'text-neutral-700 dark:text-neutral-300',
            )}
          >
            {conv.title || '新对话'}
          </button>
          <div className="mr-1 hidden shrink-0 items-center gap-0.5 group-hover:flex">
            <button
              onClick={() => {
                setTitle(conv.title)
                setRenaming(true)
              }}
              title="重命名"
              className="rounded-md p-1 text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-600 dark:hover:bg-neutral-700 dark:hover:text-neutral-300"
            >
              <svg viewBox="0 0 20 20" className="size-3.5 fill-current">
                <path d="M13.6 2.6a2 2 0 0 1 2.8 2.8l-8.8 8.8-3.7.9.9-3.7 8.8-8.8z" />
              </svg>
            </button>
            <button
              onClick={() => setConfirmDelete(true)}
              title="删除"
              className="rounded-md p-1 text-neutral-400 transition-colors hover:bg-red-100 hover:text-red-500 dark:hover:bg-red-950"
            >
              <svg viewBox="0 0 20 20" className="size-3.5 fill-current">
                <path d="M7 3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1h3a1 1 0 1 1 0 2h-1l-.8 11.1A2 2 0 0 1 12.2 18H7.8a2 2 0 0 1-2-1.9L5 5H4a1 1 0 0 1 0-2h3zm2 4a1 1 0 0 1 2 0v7a1 1 0 1 1-2 0V7z" />
              </svg>
            </button>
          </div>
        </>
      )}

      {/* 删除二次确认小弹层 */}
      {confirmDelete && (
        <div className="absolute right-0 top-full z-40 mt-1 w-48 rounded-xl border border-neutral-200 bg-white p-3 shadow-lg dark:border-neutral-700 dark:bg-neutral-800">
          <p className="text-xs text-neutral-600 dark:text-neutral-300">确定删除该会话？不可恢复。</p>
          <div className="mt-2 flex justify-end gap-1.5">
            <button
              onClick={() => setConfirmDelete(false)}
              className="rounded-lg px-2 py-1 text-xs text-neutral-500 transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-700"
            >
              取消
            </button>
            <button
              onClick={() => {
                setConfirmDelete(false)
                useChatStore.getState().deleteConversation(conv.id)
              }}
              className="rounded-lg bg-red-500 px-2 py-1 text-xs font-medium text-white transition-colors hover:bg-red-600"
            >
              删除
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function Sidebar({ collapsed }: { collapsed: boolean }) {
  const conversations = useChatStore((s) => s.conversations)
  const conversationsLoading = useChatStore((s) => s.conversationsLoading)
  const conversationsError = useChatStore((s) => s.conversationsError)
  const searchQuery = useChatStore((s) => s.searchQuery)
  const debounceRef = useRef<number | undefined>(undefined)

  // 搜索防抖 300ms
  const handleSearch = (q: string) => {
    useChatStore.getState().setSearchQuery(q)
    window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      useChatStore.getState().loadConversations(q.trim() || undefined)
    }, 300)
  }

  useEffect(() => () => window.clearTimeout(debounceRef.current), [])

  return (
    <aside
      className={clsx(
        'flex h-full shrink-0 flex-col overflow-hidden border-r border-neutral-200 bg-neutral-50 transition-[width] duration-200 dark:border-neutral-800 dark:bg-neutral-900',
        collapsed ? 'w-0 border-r-0' : 'w-[260px]',
      )}
    >
      <div className="flex w-[260px] flex-col gap-2 p-3">
        <button
          onClick={() => useChatStore.getState().selectConversation(null)}
          className="flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-violet-500 to-blue-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-opacity hover:opacity-90"
        >
          <svg viewBox="0 0 20 20" className="size-4 fill-current">
            <path d="M10 3a1 1 0 0 1 1 1v5h5a1 1 0 1 1 0 2h-5v5a1 1 0 1 1-2 0v-5H4a1 1 0 1 1 0-2h5V4a1 1 0 0 1 1-1z" />
          </svg>
          新建对话
        </button>
        <input
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="搜索会话…"
          className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-800 outline-none transition-colors placeholder:text-neutral-400 focus:border-violet-400 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200 dark:focus:border-violet-500"
        />
      </div>

      <div className="w-[260px] flex-1 overflow-y-auto px-3 pb-2">
        {conversationsLoading && conversations.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-neutral-400">加载中…</p>
        ) : conversationsError ? (
          <div className="px-3 py-4 text-center">
            <p className="text-xs text-red-400">{conversationsError}</p>
            <button
              onClick={() => useChatStore.getState().loadConversations(searchQuery.trim() || undefined)}
              className="mt-2 rounded-lg px-3 py-1 text-xs text-violet-500 transition-colors hover:bg-violet-50 dark:hover:bg-violet-500/10"
            >
              重试
            </button>
          </div>
        ) : conversations.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-neutral-400">
            {searchQuery ? '未找到匹配的会话' : '暂无会话，开始新对话吧'}
          </p>
        ) : (
          <div className="flex flex-col gap-0.5">
            {conversations.map((c) => (
              <ConversationRow key={c.id} conv={c} />
            ))}
          </div>
        )}
      </div>

      <div className="w-[260px] border-t border-neutral-200 p-3 dark:border-neutral-800">
        <button
          onClick={() => useSettingsStore.getState().setSettingsOpen(true)}
          className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-neutral-600 transition-colors hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          <svg viewBox="0 0 20 20" className="size-4 fill-current">
            <path d="M11.5 2.4a1.5 1.5 0 0 0-3 0l-.1.8a1.5 1.5 0 0 1-2.1.9l-.7-.4a1.5 1.5 0 0 0-2.1 2.1l.4.7a1.5 1.5 0 0 1-.9 2.1l-.8.1a1.5 1.5 0 0 0 0 3l.8.1a1.5 1.5 0 0 1 .9 2.1l-.4.7a1.5 1.5 0 0 0 2.1 2.1l.7-.4a1.5 1.5 0 0 1 2.1.9l.1.8a1.5 1.5 0 0 0 3 0l.1-.8a1.5 1.5 0 0 1 2.1-.9l.7.4a1.5 1.5 0 0 0 2.1-2.1l-.4-.7a1.5 1.5 0 0 1 .9-2.1l.8-.1a1.5 1.5 0 0 0 0-3l-.8-.1a1.5 1.5 0 0 1-.9-2.1l.4-.7a1.5 1.5 0 0 0-2.1-2.1l-.7.4a1.5 1.5 0 0 1-2.1-.9l-.1-.8zM10 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
          </svg>
          设置
        </button>
      </div>
    </aside>
  )
}
