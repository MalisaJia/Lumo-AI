// 会话与消息状态：加载/新建/重命名/删除/搜索、发送、停止、重新生成、编辑
import { create } from 'zustand'
import { ApiError, conversationsApi, memoryApi, messagesApi, streamChat } from '../api/client'
import type { Attachment, Conversation, Message, SearchNoticeReason, SearchStage } from '../api/types'
import { toast } from './toastStore'

interface ChatState {
  conversations: Conversation[]
  conversationsLoading: boolean
  conversationsError: string | null
  searchQuery: string
  currentId: string | null
  messages: Message[]
  messagesLoading: boolean
  streaming: boolean
  streamingContent: string
  abortController: AbortController | null
  webSearchEnabled: boolean
  searchStage: SearchStage | null
  // 当次流式会话的搜索降级提示（不持久化，下次生成/切会话时清除）
  searchNotice: SearchNoticeReason | null
  // 发送失败且未落库时回填输入框的内容（ChatInput 消费后清除）
  pendingInput: string | null
  // 智能选模防重复弹提示：记录本会话上次已提示的模型（切会话时清空）
  lastAutoModelNotified: string | null

  loadConversations: (q?: string) => Promise<void>
  setSearchQuery: (q: string) => void
  toggleWebSearch: () => void
  createConversation: () => Promise<void>
  selectConversation: (id: string | null) => Promise<void>
  renameConversation: (id: string, title: string) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  updateConversationModel: (providerId: string, modelName: string) => Promise<void>
  sendMessage: (content: string, attachments?: Attachment[]) => Promise<void>
  clearPendingInput: () => void
  stopStreaming: () => void
  regenerate: () => Promise<void>
  editMessage: (id: string, content: string) => Promise<void>
}

// 智能选模任务类型的中文映射（未知类型回退原文）
const TASK_TYPE_LABELS: Record<string, string> = {
  code: '代码',
  writing: '文案',
  long_text: '长文',
  reasoning: '推理',
  vision: '图片',
  general: '通用',
}

// 本地占位 ID 前缀，done 后会被服务端数据替换
let tempSeq = 1
const tempId = () => `temp-${tempSeq++}`

export const useChatStore = create<ChatState>((set, get) => {
  // 返回拉到的消息列表；失败（如后端不可达、会话已删）返回 null 且保留本地消息
  async function refreshMessages(conversationId: string): Promise<Message[] | null> {
    try {
      const messages = await conversationsApi.messages(conversationId)
      if (get().currentId === conversationId) set({ messages })
      return messages
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '刷新消息失败')
      return null
    }
  }

  // 启动流式生成：先插入空 assistant 占位，chunk 增量拼接，done 后刷新
  async function runStream(params: {
    conversationId: string
    content?: string
    regenerate?: boolean
    enableSearch?: boolean
    attachments?: Attachment[]
  }) {
    const { conversationId } = params
    const controller = new AbortController()
    // 本轮开始时刻：done 后用作 since 拉取新增记忆提示用户
    const startedAt = new Date().toISOString()
    // 记住发起流的会话：延迟记忆提示只在用户仍停留在该会话时弹出
    const originConversationId = conversationId
    const placeholder: Message = {
      id: tempId(),
      conversationId,
      role: 'assistant',
      content: '',
      tokenCount: null,
      createdAt: new Date().toISOString(),
    }
    set((s) => ({
      messages: [...s.messages, placeholder],
      streaming: true,
      streamingContent: '',
      abortController: controller,
      searchStage: null,
      searchNotice: null,
    }))

    let acc = ''
    let hadError = false
    try {
      await streamChat(
        params,
        (event) => {
          if (event.type === 'chunk') {
            acc += event.content
            // 首个 chunk 到达后搜索阶段提示不再展示
            set({ streamingContent: acc, searchStage: null })
            set((s) => ({
              messages: s.messages.map((m) =>
                m.id === placeholder.id ? { ...m, content: acc } : m,
              ),
            }))
          } else if (event.type === 'status') {
            set({ searchStage: event.stage })
          } else if (event.type === 'searchNotice') {
            set({ searchNotice: event.reason, searchStage: null })
          } else if (event.type === 'modelSwitch') {
            // 同渠道自动路由：提示用户已切换到备用模型
            toast.info(`模型 ${event.from} 暂不可用，已自动切换到 ${event.to}`)
          } else if (event.type === 'autoModel') {
            // 智能选模：同一会话连续选中相同模型不重复弹
            if (get().lastAutoModelNotified !== event.model) {
              set({ lastAutoModelNotified: event.model })
              toast.info(
                `已为你选择 ${event.model}（${TASK_TYPE_LABELS[event.taskType] ?? event.taskType}）`,
              )
            }
          } else if (event.type === 'sources') {
            set((s) => ({
              messages: s.messages.map((m) =>
                m.id === placeholder.id ? { ...m, sources: event.sources } : m,
              ),
            }))
          } else if (event.type === 'done') {
            // 正常结束标记：服务端已落库（messageId/usage 可用），
            // 最终内容以流结束后的 refreshMessages 拉取为准
            // 后台记忆提取约需几秒：延迟一次性查询新增记忆，失败静默
            setTimeout(() => {
              if (get().currentId !== originConversationId) return
              memoryApi
                .list({ since: startedAt })
                .then((items) => {
                  const count = items.filter((m) => m.memoryType !== 'summary').length
                  if (count > 0) toast.info(`已记住 ${count} 条新信息`)
                })
                .catch(() => {})
            }, 4000)
          } else if (event.type === 'error') {
            hadError = true
            toast.error(event.message)
          }
        },
        controller.signal,
      )
    } finally {
      set({ streaming: false, streamingContent: '', abortController: null, searchStage: null })
    }

    const aborted = controller.signal.aborted
    if (hadError && !acc) {
      // 无任何内容且出错：移除空占位
      set((s) => ({ messages: s.messages.filter((m) => m.id !== placeholder.id) }))
    }
    // 成功/失败/中断一律刷新，让界面消息 id 与数据库对齐（临时 id 被真实 id 替换）
    const fresh = await refreshMessages(conversationId)
    if (fresh && aborted && acc && fresh[fresh.length - 1]?.role !== 'assistant') {
      // 停止时后端可能尚未落库已生成部分：保留本地气泡展示，下次刷新自动对齐
      set((s) =>
        s.currentId === conversationId
          ? { messages: [...s.messages, { ...placeholder, content: acc }] }
          : {},
      )
    }
    // 生成后标题/updatedAt 可能变化，静默刷新会话列表
    get().loadConversations(get().searchQuery || undefined)
  }

  return {
    conversations: [],
    conversationsLoading: false,
    conversationsError: null,
    searchQuery: '',
    currentId: null,
    messages: [],
    messagesLoading: false,
    streaming: false,
    streamingContent: '',
    abortController: null,
    webSearchEnabled: false,
    searchStage: null,
    searchNotice: null,
    pendingInput: null,
    lastAutoModelNotified: null,

    loadConversations: async (q) => {
      set({ conversationsLoading: true, conversationsError: null })
      try {
        const conversations = await conversationsApi.list(q)
        set({ conversations, conversationsLoading: false })
      } catch (err) {
        const message = err instanceof Error ? err.message : '加载会话失败'
        set({ conversationsLoading: false, conversationsError: message })
      }
    },

    setSearchQuery: (q) => set({ searchQuery: q }),

    toggleWebSearch: () => set((s) => ({ webSearchEnabled: !s.webSearchEnabled })),

    createConversation: async () => {
      try {
        const conv = await conversationsApi.create({})
        set((s) => ({
          conversations: [conv, ...s.conversations],
          currentId: conv.id,
          messages: [],
          lastAutoModelNotified: null,
        }))
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '新建对话失败')
      }
    },

    selectConversation: async (id) => {
      if (get().streaming) get().stopStreaming()
      if (id === null) {
        set({ currentId: null, messages: [], searchNotice: null, lastAutoModelNotified: null })
        return
      }
      set({
        currentId: id,
        messages: [],
        messagesLoading: true,
        searchNotice: null,
        lastAutoModelNotified: null,
      })
      try {
        const messages = await conversationsApi.messages(id)
        if (get().currentId === id) set({ messages, messagesLoading: false })
      } catch (err) {
        set({ messagesLoading: false })
        toast.error(err instanceof Error ? err.message : '加载消息失败')
      }
    },

    renameConversation: async (id, title) => {
      try {
        const updated = await conversationsApi.patch(id, { title })
        set((s) => ({
          conversations: s.conversations.map((c) => (c.id === id ? updated : c)),
        }))
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '重命名失败')
      }
    },

    deleteConversation: async (id) => {
      try {
        await conversationsApi.remove(id)
        set((s) => ({
          conversations: s.conversations.filter((c) => c.id !== id),
          // 删除当前活跃会话时同步重置智能选模提示记录
          ...(s.currentId === id
            ? { currentId: null, messages: [], lastAutoModelNotified: null }
            : {}),
        }))
        toast.success('会话已删除')
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '删除失败')
      }
    },

    updateConversationModel: async (providerId, modelName) => {
      const id = get().currentId
      if (!id) return
      try {
        const updated = await conversationsApi.patch(id, { providerId, modelName })
        set((s) => ({
          conversations: s.conversations.map((c) => (c.id === id ? updated : c)),
        }))
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '切换模型失败')
      }
    },

    sendMessage: async (content, attachments) => {
      if (get().streaming) return
      let conversationId = get().currentId
      // 无当前会话时先创建
      if (!conversationId) {
        try {
          const conv = await conversationsApi.create({})
          conversationId = conv.id
          set((s) => ({
            conversations: [conv, ...s.conversations],
            currentId: conv.id,
            messages: [],
            lastAutoModelNotified: null,
          }))
        } catch (err) {
          toast.error(err instanceof Error ? err.message : '创建会话失败')
          return
        }
      }
      // 本地先插入 user 消息（乐观更新，含图片附件）
      const userMsg: Message = {
        id: tempId(),
        conversationId,
        role: 'user',
        content,
        tokenCount: null,
        attachments: attachments?.length ? attachments : undefined,
        createdAt: new Date().toISOString(),
      }
      set((s) => ({ messages: [...s.messages, userMsg] }))
      await runStream({
        conversationId,
        content,
        enableSearch: get().webSearchEnabled,
        attachments: attachments?.length ? attachments : undefined,
      })
      // 兜底：刷新后消息未落库（请求未到达后端且刷新成功，如会话已被删除）时回填输入框，避免内容丢失
      if (
        content &&
        get().currentId === conversationId &&
        !get().messages.some((m) => m.role === 'user' && m.content === content)
      ) {
        set({ pendingInput: content })
        toast.error('消息未发送成功，内容已恢复到输入框')
      }
    },

    clearPendingInput: () => set({ pendingInput: null }),

    stopStreaming: () => {
      get().abortController?.abort()
      set({ streaming: false, abortController: null })
    },

    regenerate: async () => {
      const { messages, currentId, streaming } = get()
      if (!currentId || streaming) return
      // 找最后一条 assistant 消息之前的那条 user 消息
      const lastAssistantIdx = messages.map((m) => m.role).lastIndexOf('assistant')
      if (lastAssistantIdx === -1) return
      let userIdx = -1
      for (let i = lastAssistantIdx - 1; i >= 0; i--) {
        if (messages[i].role === 'user') {
          userIdx = i
          break
        }
      }
      if (userIdx === -1) return
      const userMsg = messages[userIdx]
      try {
        await messagesApi.deleteAfter(userMsg.id)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          // 界面残留了未落库的临时消息：刷新回到一致状态
          toast.error('该消息尚未保存，无法重新生成')
          await refreshMessages(currentId)
        } else {
          toast.error(err instanceof Error ? err.message : '重新生成失败')
        }
        return
      }
      set({ messages: messages.slice(0, userIdx + 1) })
      await runStream({
        conversationId: currentId,
        regenerate: true,
        enableSearch: get().webSearchEnabled,
      })
    },

    editMessage: async (id, content) => {
      const { currentId, streaming } = get()
      if (!currentId || streaming) return
      try {
        await messagesApi.update(id, content)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          // 界面残留了未落库的临时消息：友好提示并刷新回到一致状态
          toast.error('该消息尚未保存，无法编辑')
          await refreshMessages(currentId)
        } else {
          toast.error(err instanceof Error ? err.message : '编辑失败')
        }
        return
      }
      // 后端会删除该消息之后的所有消息
      set((s) => {
        const idx = s.messages.findIndex((m) => m.id === id)
        if (idx === -1) return {}
        const kept = s.messages.slice(0, idx + 1)
        kept[idx] = { ...kept[idx], content }
        return { messages: kept }
      })
      await runStream({
        conversationId: currentId,
        regenerate: true,
        enableSearch: get().webSearchEnabled,
      })
    },
  }
})
