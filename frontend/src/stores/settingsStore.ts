// 设置：主题（localStorage 持久化 + documentElement class 同步）与 Provider 列表
import { create } from 'zustand'
import { providersApi } from '../api/client'
import type { Provider } from '../api/types'
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
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  loadProviders: () => Promise<void>
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
  setSettingsOpen: (open) => set({ settingsOpen: open }),
}))
