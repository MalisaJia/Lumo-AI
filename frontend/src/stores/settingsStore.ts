// 设置：主题（localStorage 持久化 + documentElement class 同步）、Provider 列表与模型路由设置
import { create } from 'zustand'
import { providersApi, settingsApi } from '../api/client'
import type { Provider, RoutingSettings } from '../api/types'
import { toast } from './toastStore'

type Theme = 'light' | 'dark'

const THEME_KEY = 'lumo-theme'

function readTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  localStorage.setItem(THEME_KEY, theme)
}

interface SettingsState {
  theme: Theme
  providers: Provider[]
  providersLoading: boolean
  providersError: string | null
  settingsOpen: boolean
  // 模型路由设置（ModelSelector 据此决定是否展示「自动」项），未加载成功时为 null
  routingSettings: RoutingSettings | null
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  loadProviders: () => Promise<void>
  loadRoutingSettings: () => Promise<void>
  // 设置面板保存后同步，让 ModelSelector 立即感知开关变化
  setRoutingSettings: (settings: RoutingSettings) => void
  setSettingsOpen: (open: boolean) => void
}

const initialTheme = readTheme()
applyTheme(initialTheme)

export const useSettingsStore = create<SettingsState>((set, get) => ({
  theme: initialTheme,
  providers: [],
  providersLoading: false,
  providersError: null,
  settingsOpen: false,
  routingSettings: null,
  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },
  toggleTheme: () => {
    get().setTheme(get().theme === 'dark' ? 'light' : 'dark')
  },
  loadProviders: async () => {
    set({ providersLoading: true, providersError: null })
    try {
      const providers = await providersApi.list()
      set({ providers, providersLoading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : '加载模型服务商失败'
      set({ providersLoading: false, providersError: message })
      toast.error(message)
    }
  },
  loadRoutingSettings: async () => {
    try {
      const routingSettings = await settingsApi.getRouting()
      set({ routingSettings })
    } catch {
      // 启动时静默失败：仅影响「自动」项展示，设置面板打开时会再次加载并提示
    }
  },
  setRoutingSettings: (settings) => set({ routingSettings: settings }),
  setSettingsOpen: (open) => set({ settingsOpen: open }),
}))
