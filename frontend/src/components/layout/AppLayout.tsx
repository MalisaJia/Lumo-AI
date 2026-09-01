// 应用主布局：侧边栏（可折叠）+ 顶栏 + 聊天区/开始页 + 设置模态
import { useEffect, useState } from 'react'
import { Sidebar } from './Sidebar'
import { ToastContainer } from './ToastContainer'
import { MessageList } from '../chat/MessageList'
import { ChatInput } from '../chat/ChatInput'
import { ModelSelector } from '../chat/ModelSelector'
import { ExportButton } from '../chat/ExportButton'
import { StartScreen } from '../chat/StartScreen'
import { SettingsModal } from '../settings/SettingsModal'
import { useChatStore } from '../../stores/chatStore'
import { useSettingsStore } from '../../stores/settingsStore'

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const currentId = useChatStore((s) => s.currentId)
  const theme = useSettingsStore((s) => s.theme)
  const settingsOpen = useSettingsStore((s) => s.settingsOpen)

  // 首次加载会话列表、服务商与模型路由设置
  useEffect(() => {
    useChatStore.getState().loadConversations()
    useSettingsStore.getState().loadProviders()
    useSettingsStore.getState().loadRoutingSettings()
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-white text-neutral-900 dark:bg-neutral-900 dark:text-neutral-100">
      <Sidebar collapsed={collapsed} />

      <main className="flex min-w-0 flex-1 flex-col">
        {/* 顶栏 */}
        <header className="flex h-13 shrink-0 items-center gap-2 border-b border-neutral-200 px-3 dark:border-neutral-800">
          <button
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? '展开侧边栏' : '折叠侧边栏'}
            className="rounded-lg p-2 text-neutral-500 transition-colors hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
          >
            <svg viewBox="0 0 20 20" className="size-4.5 fill-current">
              <path d="M3 5a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H4a1 1 0 0 1-1-1zm0 5a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H4a1 1 0 0 1-1-1zm1 4a1 1 0 1 0 0 2h12a1 1 0 1 0 0-2H4z" />
            </svg>
          </button>

          <ModelSelector />

          <div className="flex-1" />

          {currentId && <ExportButton />}

          {!currentId && (
            <span className="bg-gradient-to-r from-violet-500 to-blue-500 bg-clip-text text-sm font-semibold text-transparent">
              Lumo AI
            </span>
          )}

          <button
            onClick={() => useSettingsStore.getState().toggleTheme()}
            title={theme === 'dark' ? '切换为浅色' : '切换为深色'}
            className="rounded-lg p-2 text-neutral-500 transition-colors hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
          >
            {theme === 'dark' ? (
              <svg viewBox="0 0 20 20" className="size-4.5 fill-current">
                <path d="M10 2a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1zm0 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm7-5a1 1 0 1 1 0 2h-1a1 1 0 1 1 0-2h1zM5 10a1 1 0 0 1-1 1H3a1 1 0 1 1 0-2h1a1 1 0 0 1 1 1zm10.66-5.66a1 1 0 0 1 0 1.41l-.7.71a1 1 0 1 1-1.42-1.41l.71-.71a1 1 0 0 1 1.41 0zM6.46 13.54a1 1 0 0 1 0 1.41l-.71.71a1 1 0 0 1-1.41-1.41l.7-.71a1 1 0 0 1 1.42 0zm9.2 2.12a1 1 0 0 1-1.42 0l-.7-.71a1 1 0 0 1 1.41-1.41l.71.7a1 1 0 0 1 0 1.42zM6.46 6.46a1 1 0 0 1-1.42 0l-.7-.7A1 1 0 0 1 5.75 4.34l.71.71a1 1 0 0 1 0 1.41zM10 15a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1z" />
              </svg>
            ) : (
              <svg viewBox="0 0 20 20" className="size-4.5 fill-current">
                <path d="M17.3 12.6A7.5 7.5 0 0 1 7.4 2.7a.75.75 0 0 0-.98-.98 8.5 8.5 0 1 0 11.86 11.86.75.75 0 0 0-.98-.98z" />
              </svg>
            )}
          </button>
        </header>

        {/* 主内容 */}
        {currentId ? <MessageList /> : <StartScreen />}
        <ChatInput />
      </main>

      {settingsOpen && <SettingsModal />}
      <ToastContainer />
    </div>
  )
}
