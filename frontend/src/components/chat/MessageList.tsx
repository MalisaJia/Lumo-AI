// 消息列表：自动滚底，用户上滚时暂停自动滚动
import { useEffect, useRef } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { MessageItem } from './MessageItem'

export function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const messagesLoading = useChatStore((s) => s.messagesLoading)
  const streaming = useChatStore((s) => s.streaming)
  const streamingContent = useChatStore((s) => s.streamingContent)

  const containerRef = useRef<HTMLDivElement>(null)
  const autoScrollRef = useRef(true)

  // 用户上滚时暂停自动滚动，滚回底部附近恢复
  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  useEffect(() => {
    const el = containerRef.current
    if (el && autoScrollRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages.length, streamingContent])

  // 切换会话后强制滚底
  const currentId = useChatStore((s) => s.currentId)
  useEffect(() => {
    autoScrollRef.current = true
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [currentId, messagesLoading])

  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id
  const streamingMsgId = streaming ? messages[messages.length - 1]?.id : undefined

  return (
    <div ref={containerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl py-4">
        {messagesLoading ? (
          <div className="flex items-center justify-center py-16 text-sm text-neutral-400">
            加载消息中…
          </div>
        ) : (
          messages.map((m) => (
            <MessageItem
              key={m.id}
              message={m}
              isLastAssistant={!streaming && m.id === lastAssistantId}
              isStreamingThis={m.id === streamingMsgId}
            />
          ))
        )}
      </div>
    </div>
  )
}
