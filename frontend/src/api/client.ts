// fetch 封装：JSON 请求 + SSE 流式聊天
import type {
  Conversation,
  ConversationCreateInput,
  ConversationPatchInput,
  Message,
  MemoryItem,
  MemorySettings,
  Provider,
  ProviderCreateInput,
  ProviderUpdateInput,
  RoutingSettings,
  SearchSettings,
  SearchSettingsUpdateInput,
  StreamChatParams,
  StreamEvent,
  UploadResult,
  ValidateResult,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

// 多用户模式：localStorage 存有 token 时统一附加 Authorization 头；无 token 时不加任何头
function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('lumo_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
        ...(options.headers ?? {}),
      },
    })
  } catch {
    throw new ApiError(0, '网络请求失败，请检查后端服务是否已启动')
  }
  if (!res.ok) {
    let detail = `请求失败（${res.status}）`
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') detail = data.detail
      else if (Array.isArray(data?.detail))
        // FastAPI 422 验证错误：提取各项 msg 拼成可读文案
        detail = data.detail
          .map((d: { msg?: string }) => (typeof d?.msg === 'string' ? d.msg : JSON.stringify(d)))
          .join('；')
      else if (data?.detail) detail = JSON.stringify(data.detail)
    } catch {
      // 忽略非 JSON 响应体
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// ---------- Providers ----------
export const providersApi = {
  list: () => request<Provider[]>('/api/providers'),
  create: (body: ProviderCreateInput) =>
    request<Provider>('/api/providers', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: ProviderUpdateInput) =>
    request<Provider>(`/api/providers/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  remove: (id: string) => request<void>(`/api/providers/${id}`, { method: 'DELETE' }),
  validate: (body: { baseUrl: string; apiKey: string }) =>
    request<ValidateResult>('/api/providers/validate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

// ---------- Conversations ----------
export const conversationsApi = {
  list: (q?: string) =>
    request<Conversation[]>(`/api/conversations${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  create: (body: ConversationCreateInput = {}) =>
    request<Conversation>('/api/conversations', { method: 'POST', body: JSON.stringify(body) }),
  patch: (id: string, body: ConversationPatchInput) =>
    request<Conversation>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  remove: (id: string) => request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),
  messages: (id: string) => request<Message[]>(`/api/conversations/${id}/messages`),
}

// ---------- Messages ----------
export const messagesApi = {
  update: (id: string, content: string) =>
    request<Message>(`/api/messages/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),
  deleteAfter: (id: string) => request<void>(`/api/messages/${id}/after`, { method: 'DELETE' }),
}

// ---------- 图片上传 ----------
export const uploadsApi = {
  // multipart 上传：不手动设 Content-Type，让浏览器自动带 boundary
  upload: async (file: File): Promise<UploadResult> => {
    const form = new FormData()
    form.append('file', file)
    let res: Response
    try {
      res = await fetch('/api/uploads', { method: 'POST', body: form, headers: authHeaders() })
    } catch {
      throw new ApiError(0, '网络请求失败，请检查后端服务是否已启动')
    }
    if (!res.ok) {
      let detail = `上传失败（${res.status}）`
      try {
        const data = await res.json()
        if (typeof data?.detail === 'string') detail = data.detail
      } catch {
        // 忽略非 JSON 响应体
      }
      throw new ApiError(res.status, detail)
    }
    return (await res.json()) as UploadResult
  },
}

// ---------- 设置 ----------
export const settingsApi = {
  getSearch: () => request<SearchSettings>('/api/settings/search'),
  updateSearch: (body: SearchSettingsUpdateInput) =>
    request<SearchSettings>('/api/settings/search', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getRouting: () => request<RoutingSettings>('/api/settings/routing'),
  updateRouting: (body: RoutingSettings) =>
    request<RoutingSettings>('/api/settings/routing', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}

// ---------- 长期记忆 ----------
export const memoryApi = {
  getSettings: () => request<MemorySettings>('/api/settings/memory'),
  updateSettings: (body: MemorySettings) =>
    request<MemorySettings>('/api/settings/memory', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  list: (params?: { since?: string; type?: MemoryItem['memoryType'] }) => {
    const query = new URLSearchParams()
    if (params?.since) query.set('since', params.since)
    if (params?.type) query.set('type', params.type)
    const qs = query.toString()
    return request<MemoryItem[]>(`/api/memories${qs ? `?${qs}` : ''}`)
  },
  create: (body: { content: string; type?: MemoryItem['memoryType']; tags?: string[] }) =>
    request<MemoryItem>('/api/memories', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: { content?: string; tags?: string[]; isEnabled?: boolean }) =>
    request<MemoryItem>(`/api/memories/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  remove: (id: string) => request<void>(`/api/memories/${id}`, { method: 'DELETE' }),
}

// ---------- 流式聊天 ----------
export async function streamChat(
  params: StreamChatParams,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(params),
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    onEvent({ type: 'error', message: '连接失败，请检查后端服务是否已启动' })
    return
  }

  if (!res.ok || !res.body) {
    let message = `请求失败（${res.status}）`
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') message = data.detail
    } catch {
      // 忽略
    }
    onEvent({ type: 'error', message })
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const handleFrame = (frame: string) => {
    for (const line of frame.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue
      const payload = trimmed.slice(5).trim()
      if (!payload) continue
      try {
        onEvent(JSON.parse(payload) as StreamEvent)
      } catch {
        // 跳过无法解析的帧
      }
    }
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        handleFrame(frame)
      }
    }
    buffer += decoder.decode()
    if (buffer.trim()) handleFrame(buffer)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    onEvent({ type: 'error', message: '连接中断' })
  }
}
