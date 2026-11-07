// 会话与消息状态：加载/新建/重命名/删除/搜索、发送、停止、重新生成、编辑
import { create } from 'zustand'
import {
  ApiError,
  conversationsApi,
  getAgentProfiles,
  memoryApi,
  messagesApi,
  streamChat,
} from '../api/client'
import type {
  AgentProfile,
  Attachment,
  Conversation,
  Message,
  SearchNoticeReason,
  SearchStage,
} from '../api/types'
import { useTaskStore } from './taskStore'
import { toast } from './toastStore'

export interface AgentStreamState {
  agentId: string
  taskId: string | null
  agentType: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  streamingContent: string
  currentTool: string | null
}

interface ChatState {
  conversations: Conversation[]
  conversationsLoading: boolean
  conversationsError: string | null
  agentProfiles: AgentProfile[]
  agentProfilesLoading: boolean
  agentProfilesError: string | null
  searchQuery: string
  currentId: string | null
  currentConversation: Conversation | null
  messages: Message[]
  messagesLoading: boolean
  streaming: boolean
  streamingContent: string
  abortController: AbortController | null
  agentStreams: Map<string, AgentStreamState>
  webSearchEnabled: boolean
  searchStage: SearchStage | null
  // 当次流式会话的搜索降级提示（不持久化，下次生成/切会话时清除）
  searchNotice: SearchNoticeReason | null
  // 发送失败且未落库时回填输入框的内容（ChatInput 消费后清除）
  pendingInput: string | null
  // 智能选模防重复弹提示：记录本会话上次已提示的模型（切会话时清空）
  lastAutoModelNotified: string | null

  loadConversations: (q?: string) => Promise<void>
  loadAgentProfiles: () => Promise<void>
  setSearchQuery: (q: string) => void
  toggleWebSearch: () => void
  createConversation: (agentType?: string) => Promise<void>
  selectConversation: (id: string | null) => Promise<void>
  renameConversation: (id: string, title: string) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  exportConversation: (format: 'pdf' | 'pptx') => Promise<void>
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

const FILE_TREE_REFRESH_DEBOUNCE_MS = 250
let fileTreeRefreshTimer: ReturnType<typeof setTimeout> | null = null
const pendingChangedFilePaths = new Set<string>()

function normalizeFilePath(path: string): string {
  const normalized = path.replace(/\\/g, '/').replace(/\/+$/, '')
  return normalized || '/'
}

function comparablePath(path: string): string {
  const normalized = normalizeFilePath(path)
  return /^[a-z]:\//i.test(normalized) ? normalized.toLowerCase() : normalized
}

function resolveTreeParentPath(filePath: string, workspacePath: string): string | null {
  const normalizedFilePath = normalizeFilePath(filePath)
  const normalizedWorkspacePath = normalizeFilePath(workspacePath)
  const workspaceBase = workspacePath.replace(/[\\/]+$/, '')
  const absolute = normalizedFilePath.startsWith('/') || /^[a-z]:\//i.test(normalizedFilePath)

  let relativeFilePath = normalizedFilePath
  if (absolute) {
    const comparableFilePath = comparablePath(normalizedFilePath)
    const comparableWorkspacePath = comparablePath(normalizedWorkspacePath)
    if (comparableFilePath === comparableWorkspacePath) return null
    if (!comparableFilePath.startsWith(`${comparableWorkspacePath}/`)) return null
    relativeFilePath = normalizedFilePath.slice(normalizedWorkspacePath.length + 1)
  }

  const separatorIndex = relativeFilePath.lastIndexOf('/')
  const relativeParent = separatorIndex >= 0 ? relativeFilePath.slice(0, separatorIndex) : ''
  return relativeParent ? `${workspaceBase}/${relativeParent}` : workspacePath
}

function scheduleFileTreeRefresh(filePath: string): void {
  pendingChangedFilePaths.add(filePath)
  if (fileTreeRefreshTimer) clearTimeout(fileTreeRefreshTimer)

  fileTreeRefreshTimer = setTimeout(() => {
    fileTreeRefreshTimer = null
    const changedPaths = Array.from(pendingChangedFilePaths)
    pendingChangedFilePaths.clear()

    void import('./ideStore')
      .then(async ({ useIdeStore }) => {
        const { workspacePath, fileTree } = useIdeStore.getState()
        if (!workspacePath) return

        const parentPaths = new Set(
          changedPaths
            .map((path) => resolveTreeParentPath(path, workspacePath))
            .filter((path): path is string => Boolean(path)),
        )
        const rootPath = comparablePath(workspacePath)
        const refreshRoot =
          fileTree.length === 0 ||
          Array.from(parentPaths).some((path) => comparablePath(path) === rootPath)

        if (refreshRoot) {
          await useIdeStore.getState().refreshFileTree()
        }

        await Promise.all(
          Array.from(parentPaths)
            .filter((path) => comparablePath(path) !== rootPath)
            .map((path) => useIdeStore.getState().loadTreeNode(path)),
        )
      })
      .catch(() => {})
  }, FILE_TREE_REFRESH_DEBOUNCE_MS)
}

function agentStoppedStatus(status?: string, reason?: string): AgentStreamState['status'] {
  if (status === 'completed' || status === 'failed' || status === 'cancelled') return status
  if (reason?.toLowerCase().includes('cancel')) return 'cancelled'
  return reason ? 'failed' : 'completed'
}

export const useChatStore = create<ChatState>((set, get) => {
  let conversationListRequest = 0
  // 返回拉到的消息列表；失败（如后端不可达、会话已删）返回 null 且保留本地消息
  async function refreshMessages(
    conversationId: string,
    pendingAssistant?: { message: Message; completedMessageId: string },
  ): Promise<Message[] | null> {
    try {
      const serverMessages = await conversationsApi.messages(conversationId)
      let messages = serverMessages

      if (pendingAssistant) {
        const { message, completedMessageId } = pendingAssistant
        const completedIndex = completedMessageId
          ? serverMessages.findIndex((item) => item.id === completedMessageId)
          : -1
        const lastIndex = serverMessages.length - 1
        const contentMatchIndex =
          lastIndex >= 0 &&
          serverMessages[lastIndex].role === 'assistant' &&
          serverMessages[lastIndex].content === message.content
            ? lastIndex
            : -1
        const persistedIndex = completedIndex !== -1 ? completedIndex : contentMatchIndex

        if (persistedIndex === -1) {
          messages = [...serverMessages, message]
        } else if (message.thinking || message.userQuestion || message.sources?.length) {
          messages = serverMessages.map((item, index) =>
            index === persistedIndex
              ? {
                  ...item,
                  ...(message.thinking ? { thinking: message.thinking } : {}),
                  ...(message.userQuestion ? { userQuestion: message.userQuestion } : {}),
                  ...(message.sources?.length && !item.sources?.length
                    ? { sources: message.sources }
                    : {}),
                }
              : item,
          )
        }
      }

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
    let thinkingAcc = ''
    let currentQuestion: Message['userQuestion']
    let completedMessageId = ''
    let hadError = false
    try {
      await streamChat(
        params,
        (event) => {
          if (event.type === 'chunk') {
            const data = event.data ?? event
            const content = data.content ?? ''
            acc += content
            // 首个 chunk 到达后搜索阶段提示不再展示
            set({ streamingContent: acc, searchStage: null })
            set((s) => {
              const next: Partial<ChatState> = {
                messages: s.messages.map((m) =>
                  m.id === placeholder.id ? { ...m, content: acc } : m,
                ),
              }
              if (data.agentId && content) {
                const current = s.agentStreams.get(data.agentId)
                if (current) {
                  const agentStreams = new Map(s.agentStreams)
                  agentStreams.set(data.agentId, {
                    ...current,
                    streamingContent: current.streamingContent + content,
                  })
                  next.agentStreams = agentStreams
                }
              }
              return next
            })
          } else if (event.type === 'thinking') {
            const data = event.data ?? event
            if (data.content) {
              thinkingAcc += data.content
              set((s) => ({
                messages: s.messages.map((m) =>
                  m.id === placeholder.id ? { ...m, thinking: thinkingAcc } : m,
                ),
              }))
            }
          } else if (event.type === 'askUser') {
            const data = event.data ?? event
            if (data.question && data.options?.length) {
              currentQuestion = {
                question: data.question,
                options: data.options,
                toolCallId: data.toolCallId,
              }
              set((s) => ({
                messages: s.messages.map((m) =>
                  m.id === placeholder.id ? { ...m, userQuestion: currentQuestion } : m,
                ),
              }))
            }
          } else if (event.type === 'confirmationRequest') {
            const data = event.data ?? event
            if (
              typeof data.id === 'string' &&
              typeof data.action === 'string' &&
              typeof data.description === 'string' &&
              data.risk_level
            ) {
              void import('./confirmationStore')
                .then(({ useConfirmationStore }) =>
                  useConfirmationStore.getState().setPending({
                    id: data.id as string,
                    action: data.action as string,
                    description: data.description as string,
                    risk_level: data.risk_level!,
                    screenshot_base64: data.screenshot_base64,
                    timestamp: Date.now(),
                  }),
                )
                .catch(() => {})
            }
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
          } else if (event.type === 'toolExecution') {
            const lines: string[] = []
            if (event.command) lines.push(`$ ${event.command}`)
            if (event.output) lines.push(event.output)
            if (lines.length) {
              void import('./ideStore')
                .then(({ useIdeStore }) => useIdeStore.getState().appendTerminalOutput(lines))
                .catch(() => {})
            }
          } else if (event.type === 'fileChanged') {
            const data = event.data ?? event
            if (
              data.path &&
              typeof data.oldContent === 'string' &&
              typeof data.newContent === 'string'
            ) {
              scheduleFileTreeRefresh(data.path as string)
              void import('./ideStore')
                .then(({ useIdeStore }) =>
                  useIdeStore.getState().showDiff({
                    path: data.path as string,
                    oldContent: data.oldContent as string,
                    newContent: data.newContent as string,
                  }),
                )
                .catch(() => {})
            }
          } else if (event.type === 'taskCreated') {
            const data = event.data ?? event
            if (data.taskId) {
              useTaskStore.getState().handleTaskCreated({
                taskId: data.taskId,
                parentTaskId: data.parentTaskId,
                description: data.description ?? '',
                conversationId: data.conversationId ?? conversationId,
              })
            }
          } else if (event.type === 'taskStatusChanged') {
            const data = event.data ?? event
            if (data.taskId && data.status) {
              useTaskStore.getState().handleTaskStatusChanged({
                taskId: data.taskId,
                status: data.status,
                result: data.result,
              })
            }
          } else if (event.type === 'agentStarted') {
            const data = event.data ?? event
            if (data.agentId) {
              const agentId = data.agentId
              const agentType = data.agentType ?? 'coding'
              useTaskStore.getState().handleAgentStarted({
                agentId,
                taskId: data.taskId,
                model: data.model,
                agentType,
              })
              set((s) => {
                const agentStreams = new Map(s.agentStreams)
                agentStreams.set(agentId, {
                  agentId,
                  taskId: data.taskId ?? null,
                  agentType,
                  status: 'running',
                  streamingContent: '',
                  currentTool: null,
                })
                return { agentStreams }
              })
            }
          } else if (event.type === 'agentStopped') {
            const data = event.data ?? event
            if (data.agentId) {
              const agentId = data.agentId
              useTaskStore.getState().handleAgentStopped({
                agentId,
                reason: data.reason,
                status: data.status,
                rounds: data.rounds,
              })
              set((s) => {
                const current = s.agentStreams.get(agentId)
                if (!current) return s
                const agentStreams = new Map(s.agentStreams)
                agentStreams.set(agentId, {
                  ...current,
                  status: agentStoppedStatus(data.status, data.reason),
                  currentTool: null,
                })
                return { agentStreams }
              })
            }
          } else if (event.type === 'toolStart') {
            const data = event.data ?? event
            if (data.agentId && data.toolName) {
              const agentId = data.agentId
              const toolName = data.toolName
              useTaskStore.getState().handleToolStart({ agentId, toolName })
              set((s) => {
                const current = s.agentStreams.get(agentId)
                if (!current) return s
                const agentStreams = new Map(s.agentStreams)
                agentStreams.set(agentId, { ...current, currentTool: toolName })
                return { agentStreams }
              })
            }
          } else if (event.type === 'toolEnd') {
            const data = event.data ?? event
            if (data.agentId && data.toolName) {
              const agentId = data.agentId
              const toolName = data.toolName
              useTaskStore.getState().handleToolEnd({ agentId, toolName })
              set((s) => {
                const current = s.agentStreams.get(agentId)
                if (!current || current.currentTool !== toolName) return s
                const agentStreams = new Map(s.agentStreams)
                agentStreams.set(agentId, { ...current, currentTool: null })
                return { agentStreams }
              })
            }
          } else if (event.type === 'done') {
            completedMessageId = event.messageId
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
      // Commit the accumulated payload to the placeholder before clearing stream-only state.
      set((s) => ({
        messages: s.messages.map((message) =>
          message.id === placeholder.id
            ? {
                ...message,
                content: acc,
                ...(thinkingAcc ? { thinking: thinkingAcc } : {}),
                ...(currentQuestion ? { userQuestion: currentQuestion } : {}),
              }
            : message,
        ),
        streaming: false,
        streamingContent: '',
        abortController: null,
        searchStage: null,
      }))
    }

    if (hadError && !acc) {
      // 无任何内容且出错：移除空占位
      set((s) => ({ messages: s.messages.filter((m) => m.id !== placeholder.id) }))
    }

    const committedPlaceholder = get().messages.find((message) => message.id === placeholder.id)
    const localAssistant = acc
      ? {
          ...(committedPlaceholder ?? placeholder),
          id: completedMessageId || placeholder.id,
          content: acc,
          ...(thinkingAcc ? { thinking: thinkingAcc } : {}),
          ...(currentQuestion ? { userQuestion: currentQuestion } : {}),
        }
      : undefined

    // Give the persistence transaction a short head start after the done event.
    if (completedMessageId) {
      await new Promise<void>((resolve) => setTimeout(resolve, 500))
    }

    // Reconcile the server snapshot without dropping a completed local response that is not visible yet.
    await refreshMessages(
      conversationId,
      localAssistant ? { message: localAssistant, completedMessageId } : undefined,
    )
    // 生成后标题/updatedAt 可能变化，静默刷新会话列表
    get().loadConversations(get().searchQuery || undefined)
  }

  return {
    conversations: [],
    conversationsLoading: false,
    conversationsError: null,
    agentProfiles: [],
    agentProfilesLoading: false,
    agentProfilesError: null,
    searchQuery: '',
    currentId: null,
    currentConversation: null,
    messages: [],
    messagesLoading: false,
    streaming: false,
    streamingContent: '',
    abortController: null,
    agentStreams: new Map(),
    webSearchEnabled: false,
    searchStage: null,
    searchNotice: null,
    pendingInput: null,
    lastAutoModelNotified: null,

    loadConversations: async (q) => {
      const requestId = ++conversationListRequest
      set({ conversationsLoading: true, conversationsError: null })
      try {
        const conversations = await conversationsApi.list(q)
        if (requestId !== conversationListRequest) return
        set((s) => ({
          conversations,
          conversationsLoading: false,
          currentConversation:
            conversations.find((conversation) => conversation.id === s.currentId) ??
            s.currentConversation,
        }))
      } catch (err) {
        if (requestId !== conversationListRequest) return
        const message = err instanceof Error ? err.message : '加载会话失败'
        set({ conversationsLoading: false, conversationsError: message })
      }
    },

    loadAgentProfiles: async () => {
      set({ agentProfilesLoading: true, agentProfilesError: null })
      try {
        const agentProfiles = await getAgentProfiles()
        set({ agentProfiles, agentProfilesLoading: false })
      } catch (err) {
        const message = err instanceof Error ? err.message : '加载 Agent 类型失败'
        set({ agentProfilesLoading: false, agentProfilesError: message })
      }
    },

    setSearchQuery: (q) => set({ searchQuery: q }),

    toggleWebSearch: () => set((s) => ({ webSearchEnabled: !s.webSearchEnabled })),

    createConversation: async (agentType = 'coding') => {
      if (get().streaming) get().stopStreaming()
      try {
        const conv = await conversationsApi.create({ agentType })
        set((s) => ({
          conversations: [conv, ...s.conversations],
          currentId: conv.id,
          currentConversation: conv,
          messages: [],
          agentStreams: new Map(),
          lastAutoModelNotified: null,
        }))
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '新建对话失败')
      }
    },

    selectConversation: async (id) => {
      if (get().streaming) get().stopStreaming()
      if (id === null) {
        set({
          currentId: null,
          currentConversation: null,
          messages: [],
          agentStreams: new Map(),
          searchNotice: null,
          lastAutoModelNotified: null,
        })
        return
      }
      set({
        currentId: id,
        currentConversation: get().conversations.find((conversation) => conversation.id === id) ??
          (get().currentConversation?.id === id ? get().currentConversation : null),
        messages: [],
        messagesLoading: true,
        agentStreams: new Map(),
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
          currentConversation: s.currentId === id ? updated : s.currentConversation,
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
            ? {
                currentId: null,
                currentConversation: null,
                messages: [],
                agentStreams: new Map(),
                lastAutoModelNotified: null,
              }
            : {}),
        }))
        toast.success('会话已删除')
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '删除失败')
      }
    },

    exportConversation: async (format) => {
      const id = get().currentId
      if (!id) return
      const conv = get().currentConversation
      try {
        const blob = await conversationsApi.export(id, format)
        // 通过临时 <a download> 触发浏览器下载，文件名用会话标题
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${conv?.title || 'conversation'}.${format}`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        toast.success(`已导出为 ${format.toUpperCase()}`)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '导出失败')
      }
    },

    updateConversationModel: async (providerId, modelName) => {
      const id = get().currentId
      if (!id) return
      try {
        const updated = await conversationsApi.patch(id, { providerId, modelName })
        set((s) => ({
          conversations: s.conversations.map((c) => (c.id === id ? updated : c)),
          currentConversation: s.currentId === id ? updated : s.currentConversation,
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
          const agentType = 'coding'
          const conv = await conversationsApi.create({ agentType })
          conversationId = conv.id
          set((s) => ({
            conversations: [conv, ...s.conversations],
            currentId: conv.id,
            currentConversation: conv,
            messages: [],
            agentStreams: new Map(),
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
