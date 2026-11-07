import { useEffect, useState } from 'react'
import { Group, Panel, Separator, useDefaultLayout } from 'react-resizable-panels'
import { workspaceApi } from '../../api/client'
import { useChatStore } from '../../stores/chatStore'
import { useIdeStore } from '../../stores/ideStore'
import { useTaskStore } from '../../stores/taskStore'
import { toast } from '../../stores/toastStore'
import { ChatInput } from '../chat/ChatInput'
import { MessageList } from '../chat/MessageList'
import { AgentStatusBar } from './AgentStatusBar'
import { CodeViewer } from './CodeViewer'
import { FileTree } from './FileTree'
import { TaskTreePanel } from './TaskTreePanel'
import { TerminalPanel } from './TerminalPanel'
import { WorkspacePicker } from './WorkspacePicker'

export default function IdeLayout() {
  const workspacePath = useIdeStore((state) => state.workspacePath)
  const currentId = useChatStore((state) => state.currentId)
  const currentConversation = useChatStore((state) => state.currentConversation)
  const conversationWorkspace = currentConversation?.workspaceDir
  const [choosingWorkspace, setChoosingWorkspace] = useState(false)
  const [leftPanel, setLeftPanel] = useState<'files' | 'tasks'>('files')
  const horizontalLayout = useDefaultLayout({
    id: 'ide-layout-h',
    panelIds: ['files', 'editor', 'chat'],
  })
  const verticalLayout = useDefaultLayout({
    id: 'ide-layout-v',
    panelIds: ['code', 'terminal'],
  })

  useEffect(() => {
    setChoosingWorkspace(false)
    if (currentId) {
      void useTaskStore.getState().loadTasks(currentId).catch(() => {})
    }
    if (conversationWorkspace) {
      if (useIdeStore.getState().workspacePath !== conversationWorkspace) {
        void useIdeStore.getState().setWorkspace(conversationWorkspace)
      }
    } else {
      useIdeStore.getState().reset()
    }
  }, [currentId, conversationWorkspace])

  const handleSelectWorkspace = async (path: string) => {
    let persisted = false
    if (currentId) {
      try {
        await workspaceApi.updateWorkspaceDir(currentId, path)
        persisted = true
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '更新工作区失败')
      }
    }
    await useIdeStore.getState().setWorkspace(path)
    setChoosingWorkspace(false)
    if (persisted) {
      const { searchQuery } = useChatStore.getState()
      void useChatStore.getState().loadConversations(searchQuery || undefined)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Group orientation="horizontal" className="min-h-0 flex-1" {...horizontalLayout}>
        <Panel id="files" defaultSize="20%" minSize="15%" maxSize="35%">
          <div className="flex h-full min-h-0 flex-col border-r border-neutral-200 dark:border-neutral-800">
            <nav className="grid h-9 shrink-0 grid-cols-2 gap-1 border-b border-neutral-200 bg-white p-1 dark:border-neutral-800 dark:bg-neutral-950">
              {(['files', 'tasks'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setLeftPanel(tab)}
                  className={tab === leftPanel
                    ? 'rounded-md bg-neutral-900 text-[11px] font-medium text-white shadow-sm dark:bg-neutral-100 dark:text-neutral-900'
                    : 'rounded-md text-[11px] text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-800 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100'}
                >
                  {tab === 'files' ? '文件' : '任务'}
                </button>
              ))}
            </nav>
            <div className="min-h-0 flex-1">
              {leftPanel === 'files' ? (
                <FileTree
                  onChangeWorkspace={() => {
                    useIdeStore.getState().reset()
                    setChoosingWorkspace(true)
                  }}
                />
              ) : (
                <TaskTreePanel />
              )}
            </div>
          </div>
        </Panel>

        <Separator className="w-1 bg-neutral-200 transition-colors hover:bg-violet-400 dark:bg-neutral-700 dark:hover:bg-violet-500" />

        <Panel id="editor" defaultSize="50%" minSize="30%">
          <Group orientation="vertical" className="h-full" {...verticalLayout}>
            <Panel id="code" defaultSize="70%" minSize="30%">
              {choosingWorkspace || (!workspacePath && !conversationWorkspace) ? (
                <WorkspacePicker onSelect={handleSelectWorkspace} />
              ) : (
                <CodeViewer />
              )}
            </Panel>
            <Separator className="h-1 bg-neutral-200 transition-colors hover:bg-violet-400 dark:bg-neutral-700 dark:hover:bg-violet-500" />
            <Panel id="terminal" defaultSize="30%" minSize="10%" collapsible>
              <TerminalPanel />
            </Panel>
          </Group>
        </Panel>

        <Separator className="w-1 bg-neutral-200 transition-colors hover:bg-violet-400 dark:bg-neutral-700 dark:hover:bg-violet-500" />

        <Panel id="chat" defaultSize="30%" minSize="25%" maxSize="50%">
          <div className="flex h-full min-h-0 flex-col">
            <MessageList />
            <ChatInput />
          </div>
        </Panel>
      </Group>
      <AgentStatusBar />
    </div>
  )
}
