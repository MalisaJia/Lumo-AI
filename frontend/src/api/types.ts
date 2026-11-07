// 与后端 API 契约逐字段一致的类型定义（JSON 全部 camelCase）

// 模型能力标签（智能选模用，合法值仅这六个）
export type CapabilityTag = 'code' | 'writing' | 'long_text' | 'reasoning' | 'vision' | 'general'

export interface ProviderModel {
  id: string
  name: string
  label: string
  isDefault: boolean
  contextLength: number
  // 留空/null 表示使用内置默认能力
  capabilityTags?: CapabilityTag[] | null
}

export interface Provider {
  id: string
  name: string
  baseUrl: string
  maskedKey: string
  isDefault: boolean
  models: ProviderModel[]
}

export interface ProviderModelInput {
  name: string
  label?: string
  isDefault?: boolean
  // 空数组按 null 提交，表示使用内置默认能力
  capabilityTags?: CapabilityTag[] | null
}

export interface ProviderCreateInput {
  name: string
  baseUrl: string
  apiKey: string
  models: ProviderModelInput[]
}

export interface ProviderUpdateInput {
  name?: string
  baseUrl?: string
  apiKey?: string
  models?: ProviderModelInput[]
  // 契约 PUT body「同 POST 全可选」；设默认功能需要该字段（GET 已返回 isDefault）
  isDefault?: boolean
}

export interface ValidateResult {
  valid: boolean
  models?: string[]
  error?: string
}

export interface AgentProfile {
  agentType: string
  displayName: string
  description: string
  icon: string
}

export interface Conversation {
  id: string
  title: string
  providerId: string | null
  modelName: string | null
  workspaceDir: string | null
  agentType: string | null
  createdAt: string
  updatedAt: string
}

export interface ConversationCreateInput {
  title?: string
  providerId?: string
  modelName?: string
  agentType?: string
}

export interface ConversationPatchInput {
  title?: string
  providerId?: string
  modelName?: string
  workspaceDir?: string
}

export type MessageRole = 'user' | 'assistant' | 'system'

export interface SourceRef {
  id: number
  title: string
  url: string
}

// 消息图片附件（已通过 /api/uploads 上传）
export interface Attachment {
  id: string
  url: string
  fileName: string
  mimeType: string
}

// POST /api/uploads 响应
export interface UploadResult {
  id: string
  url: string
  fileName: string
  mimeType: string
  size: number
}

export interface UserQuestionOption {
  label: string
  description?: string
}

export interface UserQuestionData {
  question: string
  options: UserQuestionOption[]
  toolCallId?: string
}

export interface Message {
  id: string
  conversationId: string
  role: MessageRole
  content: string
  tokenCount: number | null
  sources?: SourceRef[] | null
  attachments?: Attachment[] | null
  thinking?: string
  userQuestion?: UserQuestionData
  createdAt: string
}

export interface ChatUsage {
  promptTokens: number
  completionTokens: number
}

export type SearchStage = 'searching' | 'reading'

// 搜索降级原因：noResults=搜索无结果；skipped=模型判定无需搜索
export type SearchNoticeReason = 'noResults' | 'skipped'

type StreamDataEvent<TType extends string, TData extends object> = {
  type: TType
  data?: TData
} & Partial<TData>

interface ChunkEventData {
  content: string
  agentId?: string
}

interface TaskCreatedEventData {
  taskId: string
  parentTaskId?: string
  description: string
  conversationId?: string
}

interface TaskStatusChangedEventData {
  taskId: string
  status: string
  result?: string
}

interface AgentStartedEventData {
  agentId: string
  taskId?: string
  model?: string
  agentType?: string
}

interface AgentStoppedEventData {
  agentId: string
  reason?: string
  status?: string
  rounds?: number
}

interface ToolEventData {
  toolName: string
  agentId: string
  toolCallId?: string
  status?: string
}

interface ConfirmationRequestEventData {
  id: string
  action: string
  description: string
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  screenshot_base64?: string
}

export type StreamEvent =
  | StreamDataEvent<'chunk', ChunkEventData>
  | { type: 'done'; messageId: string; usage: ChatUsage }
  | { type: 'error'; message: string }
  | { type: 'status'; stage: SearchStage }
  | { type: 'sources'; sources: SourceRef[] }
  | { type: 'searchNotice'; reason: SearchNoticeReason }
  // 同渠道模型自动路由：实际发生切换时才下发
  | { type: 'modelSwitch'; from: string; to: string }
  // 任务感知智能选模：会话为「自动」模式时下发实际选用的模型
  | { type: 'autoModel'; model: string; taskType: string }
  // 编码 Agent 的终端命令执行结果
  | { type: 'toolExecution'; toolName: string; command: string; output: string }
  | StreamDataEvent<'thinking', { content: string }>
  | StreamDataEvent<'askUser', UserQuestionData>
  | StreamDataEvent<'confirmationRequest', ConfirmationRequestEventData>
  | StreamDataEvent<'taskCreated', TaskCreatedEventData>
  | StreamDataEvent<'taskStatusChanged', TaskStatusChangedEventData>
  | StreamDataEvent<'agentStarted', AgentStartedEventData>
  | StreamDataEvent<'agentStopped', AgentStoppedEventData>
  | StreamDataEvent<'toolStart', ToolEventData>
  | StreamDataEvent<'toolEnd', ToolEventData>
  | StreamDataEvent<
      'fileChanged',
      { path: string; changeType?: string; oldContent?: string; newContent?: string }
    >

export interface StreamChatParams {
  conversationId: string
  content?: string
  regenerate?: boolean
  enableSearch?: boolean
  attachments?: Attachment[]
}

export type SearchProviderName = 'ddgs' | 'tavily' | 'searxng'

export interface SearchSettings {
  searchProvider: SearchProviderName
  tavilyMaskedKey: string | null
  searxngUrl: string | null
}

export interface SearchSettingsUpdateInput {
  searchProvider?: SearchProviderName
  tavilyApiKey?: string
  searxngUrl?: string
}

// 模型路由设置（GET/PUT /api/settings/routing，PUT 全量提交两个字段）
export interface RoutingSettings {
  enabled: boolean
  smartSelectionEnabled: boolean
}

// Agent 工具（skills）设置（GET/PUT /api/settings/tools，默认开启）
export interface ToolsSettings {
  enabled: boolean
}

// 长期记忆条目（GET /api/memories）
export interface MemoryItem {
  id: string
  memoryType: 'fact' | 'preference' | 'summary'
  content: string
  tags: string[]
  sourceConversationId: string | null
  isEnabled: boolean
  createdAt: string
  updatedAt: string
}

// 长期记忆设置（GET/PUT /api/settings/memory）
export interface MemorySettings {
  enabled: boolean
}
