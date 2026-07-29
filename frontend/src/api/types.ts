// 与后端 API 契约逐字段一致的类型定义（JSON 全部 camelCase）

export interface ProviderModel {
  id: string
  name: string
  label: string
  isDefault: boolean
  contextLength: number
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

export interface Conversation {
  id: string
  title: string
  providerId: string | null
  modelName: string | null
  createdAt: string
  updatedAt: string
}

export interface ConversationCreateInput {
  title?: string
  providerId?: string
  modelName?: string
}

export interface ConversationPatchInput {
  title?: string
  providerId?: string
  modelName?: string
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

export interface Message {
  id: string
  conversationId: string
  role: MessageRole
  content: string
  tokenCount: number | null
  sources?: SourceRef[] | null
  attachments?: Attachment[] | null
  createdAt: string
}

export interface ChatUsage {
  promptTokens: number
  completionTokens: number
}

export type SearchStage = 'searching' | 'reading'

// 搜索降级原因：noResults=搜索无结果；skipped=模型判定无需搜索
export type SearchNoticeReason = 'noResults' | 'skipped'

export type StreamEvent =
  | { type: 'chunk'; content: string }
  | { type: 'done'; messageId: string; usage: ChatUsage }
  | { type: 'error'; message: string }
  | { type: 'status'; stage: SearchStage }
  | { type: 'sources'; sources: SourceRef[] }
  | { type: 'searchNotice'; reason: SearchNoticeReason }
  // 同渠道模型自动路由：实际发生切换时才下发
  | { type: 'modelSwitch'; from: string; to: string }

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

// 同渠道模型自动路由设置（GET/PUT /api/settings/routing）
export interface RoutingSettings {
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
