// PPT 工作区：参考资料 / 内容预览 / 对话 三面板可拖拽布局（尺寸持久化）
import { useEffect } from 'react'
import { Group, Panel, Separator, useDefaultLayout } from 'react-resizable-panels'
import { useChatStore } from '../../stores/chatStore'
import { usePptStore } from '../../stores/pptStore'
import { ChatInput } from '../chat/ChatInput'
import { MessageList } from '../chat/MessageList'
import { ContentViewer } from './ContentViewer'
import { ReferencePanel } from './ReferencePanel'

export default function PptLayout() {
  const currentId = useChatStore((state) => state.currentId)
  const horizontalLayout = useDefaultLayout({
    id: 'ppt-layout-h',
    panelIds: ['references', 'viewer', 'chat'],
  })

  // 会话切换时清空上一会话的参考资料
  useEffect(() => {
    usePptStore.getState().reset()
  }, [currentId])

  return (
    <Group orientation="horizontal" className="min-h-0 flex-1" {...horizontalLayout}>
      <Panel id="references" defaultSize="20%" minSize="15%" maxSize="35%">
        <ReferencePanel />
      </Panel>

      <Separator className="w-1 bg-neutral-200 transition-colors hover:bg-violet-400 dark:bg-neutral-700 dark:hover:bg-violet-500" />

      <Panel id="viewer" defaultSize="50%" minSize="30%">
        <ContentViewer />
      </Panel>

      <Separator className="w-1 bg-neutral-200 transition-colors hover:bg-violet-400 dark:bg-neutral-700 dark:hover:bg-violet-500" />

      <Panel id="chat" defaultSize="30%" minSize="25%" maxSize="50%">
        <div className="flex h-full min-h-0 flex-col">
          <MessageList />
          <ChatInput hidePptButton />
        </div>
      </Panel>
    </Group>
  )
}
