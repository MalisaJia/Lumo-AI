// 设置模态：Provider 管理（列表/添加/编辑/删除/设默认）+ 主题切换 + 联网搜索
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { memoryApi, providersApi, settingsApi } from '../../api/client'
import type { MemoryItem, Provider, SearchProviderName } from '../../api/types'
import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'
import { ProviderForm } from './ProviderForm'

function ProviderCard({ provider, onEdit }: { provider: Provider; onEdit: () => void }) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)

  const handleDelete = async () => {
    setBusy(true)
    try {
      await providersApi.remove(provider.id)
      toast.success('服务商已删除')
      await useSettingsStore.getState().loadProviders()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    } finally {
      setBusy(false)
      setConfirmDelete(false)
    }
  }

  const handleSetDefault = async () => {
    setBusy(true)
    try {
      await providersApi.update(provider.id, { isDefault: true })
      await useSettingsStore.getState().loadProviders()
      toast.success('已设为默认服务商')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '设置失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-neutral-200 p-3 transition-colors dark:border-neutral-700">
      <div className="flex items-center gap-2">
        <span className="font-medium">{provider.name}</span>
        {provider.isDefault && (
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-600 dark:bg-violet-500/20 dark:text-violet-300">
            默认
          </span>
        )}
        <div className="flex-1" />
        {!provider.isDefault && (
          <button
            onClick={handleSetDefault}
            disabled={busy}
            className="rounded-lg px-2 py-1 text-xs text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-violet-500 disabled:opacity-50 dark:hover:bg-neutral-700"
          >
            设默认
          </button>
        )}
        <button
          onClick={onEdit}
          className="rounded-lg px-2 py-1 text-xs text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-700 dark:hover:text-neutral-200"
        >
          编辑
        </button>
        {confirmDelete ? (
          <span className="flex items-center gap-1">
            <button
              onClick={handleDelete}
              disabled={busy}
              className="rounded-lg bg-red-500 px-2 py-1 text-xs font-medium text-white transition-colors hover:bg-red-600 disabled:opacity-50"
            >
              确认删除
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="rounded-lg px-2 py-1 text-xs text-neutral-500 transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-700"
            >
              取消
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="rounded-lg px-2 py-1 text-xs text-neutral-500 transition-colors hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-950"
          >
            删除
          </button>
        )}
      </div>
      <p className="mt-1 truncate text-xs text-neutral-400">
        {provider.baseUrl} · Key: {provider.maskedKey}
      </p>
      <div className="mt-2 flex flex-wrap gap-1">
        {provider.models.map((m) => (
          <span
            key={m.id}
            className={clsx(
              'rounded-full border px-2 py-0.5 font-mono text-xs',
              m.isDefault
                ? 'border-violet-300 text-violet-600 dark:border-violet-700 dark:text-violet-300'
                : 'border-neutral-200 text-neutral-500 dark:border-neutral-700 dark:text-neutral-400',
            )}
          >
            {m.label || m.name}
          </span>
        ))}
      </div>
    </div>
  )
}

// 联网搜索设置：搜索源下拉 + Tavily Key / SearXNG URL 条件输入
function SearchSettingsSection() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [provider, setProvider] = useState<SearchProviderName>('ddgs')
  const [tavilyKey, setTavilyKey] = useState('')
  const [tavilyMaskedKey, setTavilyMaskedKey] = useState<string | null>(null)
  const [searxngUrl, setSearxngUrl] = useState('')

  useEffect(() => {
    settingsApi
      .getSearch()
      .then((s) => {
        setProvider(s.searchProvider)
        setTavilyMaskedKey(s.tavilyMaskedKey)
        setSearxngUrl(s.searxngUrl ?? '')
      })
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : '加载搜索设置失败')
      })
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const updated = await settingsApi.updateSearch({
        searchProvider: provider,
        // 未输入新 Key 则不传，后端保留原 Key
        ...(tavilyKey.trim() ? { tavilyApiKey: tavilyKey.trim() } : {}),
        searxngUrl,
      })
      setTavilyMaskedKey(updated.tavilyMaskedKey)
      setTavilyKey('')
      toast.success('搜索设置已保存')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const inputClass =
    'w-full rounded-lg border border-neutral-300 bg-transparent px-3 py-2 text-sm outline-none transition-colors focus:border-violet-400 dark:border-neutral-600 dark:focus:border-violet-500'

  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold text-neutral-500 dark:text-neutral-400">联网搜索</h3>
      <div className="flex flex-col gap-3 rounded-xl border border-neutral-200 px-3 py-3 dark:border-neutral-700">
        {loading ? (
          <p className="py-2 text-center text-sm text-neutral-400">加载中…</p>
        ) : (
          <>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs text-neutral-500 dark:text-neutral-400">搜索源</span>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value as SearchProviderName)}
                disabled={saving}
                className={clsx(inputClass, 'dark:bg-neutral-800 disabled:opacity-50')}
              >
                <option value="ddgs">DuckDuckGo 免费（默认）</option>
                <option value="tavily">Tavily</option>
                <option value="searxng">SearXNG</option>
              </select>
            </label>
            {provider === 'tavily' && (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs text-neutral-500 dark:text-neutral-400">
                  Tavily API Key{tavilyMaskedKey ? `（已保存：${tavilyMaskedKey}）` : ''}
                </span>
                <input
                  type="password"
                  value={tavilyKey}
                  onChange={(e) => setTavilyKey(e.target.value)}
                  disabled={saving}
                  placeholder={tavilyMaskedKey ? '留空则保留已保存的 Key' : 'tvly-...'}
                  className={clsx(inputClass, 'disabled:opacity-50')}
                />
              </label>
            )}
            {provider === 'searxng' && (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs text-neutral-500 dark:text-neutral-400">SearXNG 实例 URL</span>
                <input
                  type="text"
                  value={searxngUrl}
                  onChange={(e) => setSearxngUrl(e.target.value)}
                  disabled={saving}
                  placeholder="https://searx.example.com"
                  className={clsx(inputClass, 'disabled:opacity-50')}
                />
              </label>
            )}
            <div className="flex justify-end">
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded-lg bg-gradient-to-r from-violet-500 to-blue-500 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

// 模型路由设置：同渠道自动故障转移 + 任务感知智能选模开关
function RoutingSettingsSection() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enabled, setEnabled] = useState(true)
  const [smartSelectionEnabled, setSmartSelectionEnabled] = useState(false)

  useEffect(() => {
    settingsApi
      .getRouting()
      .then((s) => {
        setEnabled(s.enabled)
        setSmartSelectionEnabled(s.smartSelectionEnabled)
        useSettingsStore.getState().setRoutingSettings(s)
      })
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : '加载路由设置失败')
      })
      .finally(() => setLoading(false))
  }, [])

  // PUT 全量提交两个字段；保存后同步 settingsStore 让 ModelSelector 立即感知
  const handleSave = async (next: { enabled: boolean; smartSelectionEnabled: boolean }) => {
    setSaving(true)
    try {
      const updated = await settingsApi.updateRouting(next)
      setEnabled(updated.enabled)
      setSmartSelectionEnabled(updated.smartSelectionEnabled)
      useSettingsStore.getState().setRoutingSettings(updated)
      toast.success('路由设置已保存')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const renderSwitch = (checked: boolean, onToggle: () => void) => (
    <button
      onClick={onToggle}
      disabled={saving}
      className={clsx(
        'relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50',
        checked ? 'bg-gradient-to-r from-violet-500 to-blue-500' : 'bg-neutral-300',
      )}
      role="switch"
      aria-checked={checked}
    >
      <span
        className={clsx(
          'absolute top-0.5 size-5 rounded-full bg-white shadow transition-all',
          checked ? 'left-[22px]' : 'left-0.5',
        )}
      />
    </button>
  )

  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold text-neutral-500 dark:text-neutral-400">模型路由</h3>
      <div className="flex flex-col gap-3 rounded-xl border border-neutral-200 px-3 py-2.5 dark:border-neutral-700">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm">遇到限流或故障时自动切换同渠道其他模型</span>
          {loading ? (
            <span className="text-sm text-neutral-400">加载中…</span>
          ) : (
            renderSwitch(enabled, () => handleSave({ enabled: !enabled, smartSelectionEnabled }))
          )}
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <span className="text-sm">智能选模</span>
            <span className="text-xs text-neutral-400 dark:text-neutral-500">
              根据问题类型自动匹配最擅长的模型，在模型选择器中选择「✨ 自动」后生效
            </span>
          </div>
          {loading ? (
            <span className="text-sm text-neutral-400">加载中…</span>
          ) : (
            renderSwitch(smartSelectionEnabled, () =>
              handleSave({ enabled, smartSelectionEnabled: !smartSelectionEnabled }),
            )
          )}
        </div>
      </div>
    </section>
  )
}

// Agent 工具（skills）：允许模型自动调用计算器/时间/联网搜索/制作 PPT 等工具
function AgentToolsSettingsSection() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enabled, setEnabled] = useState(true)

  useEffect(() => {
    settingsApi
      .getTools()
      .then((s) => setEnabled(s.enabled))
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : '加载工具设置失败')
      })
      .finally(() => setLoading(false))
  }, [])

  const handleToggle = async () => {
    setSaving(true)
    try {
      const updated = await settingsApi.updateTools({ enabled: !enabled })
      setEnabled(updated.enabled)
      toast.success('工具设置已保存')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold text-neutral-500 dark:text-neutral-400">Agent 工具</h3>
      <div className="flex items-center justify-between gap-3 rounded-xl border border-neutral-200 px-3 py-2.5 dark:border-neutral-700">
        <div className="flex flex-col gap-0.5">
          <span className="text-sm">允许模型自动调用工具</span>
          <span className="text-xs text-neutral-400 dark:text-neutral-500">
            计算、查询时间、联网搜索、制作 PPT 等，由模型按需静默调用
          </span>
        </div>
        {loading ? (
          <span className="text-sm text-neutral-400">加载中…</span>
        ) : (
          <button
            onClick={handleToggle}
            disabled={saving}
            className={clsx(
              'relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50',
              enabled ? 'bg-gradient-to-r from-violet-500 to-blue-500' : 'bg-neutral-300',
            )}
            role="switch"
            aria-checked={enabled}
          >
            <span
              className={clsx(
                'absolute top-0.5 size-5 rounded-full bg-white shadow transition-all',
                enabled ? 'left-[22px]' : 'left-0.5',
              )}
            />
          </button>
        )}
      </div>
    </section>
  )
}

// 长期记忆设置：总开关 + 记忆列表（启停/编辑/删除/手动添加）
const MEMORY_TYPE_BADGES: Record<MemoryItem['memoryType'], { label: string; className: string }> = {
  fact: {
    label: '事实',
    className: 'bg-blue-100 text-blue-600 dark:bg-blue-500/20 dark:text-blue-300',
  },
  preference: {
    label: '偏好',
    className: 'bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-300',
  },
  summary: {
    label: '摘要',
    className: 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-300',
  },
}

function MemoryRow({
  memory,
  onChanged,
}: {
  memory: MemoryItem
  onChanged: (next: MemoryItem | null) => void
}) {
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(memory.content)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const badge = MEMORY_TYPE_BADGES[memory.memoryType]

  const handleToggle = async () => {
    setBusy(true)
    try {
      const updated = await memoryApi.update(memory.id, { isEnabled: !memory.isEnabled })
      onChanged(updated)
      toast.success(updated.isEnabled ? '记忆已启用' : '记忆已停用')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const handleSave = async () => {
    const content = draft.trim()
    if (!content) return
    setBusy(true)
    try {
      const updated = await memoryApi.update(memory.id, { content })
      onChanged(updated)
      setEditing(false)
      toast.success('记忆已更新')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    setBusy(true)
    try {
      await memoryApi.remove(memory.id)
      onChanged(null)
      toast.success('记忆已删除')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    } finally {
      setBusy(false)
      setConfirmDelete(false)
    }
  }

  return (
    <div className="rounded-lg border border-neutral-200 px-2.5 py-2 dark:border-neutral-700">
      <div className="flex items-start gap-2">
        <span
          className={clsx(
            'mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs',
            badge.className,
          )}
        >
          {badge.label}
        </span>
        {editing ? (
          <div className="flex flex-1 flex-col gap-1.5">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={busy}
              rows={3}
              className="w-full rounded-lg border border-neutral-300 bg-transparent px-2 py-1.5 text-sm outline-none transition-colors focus:border-violet-400 dark:border-neutral-600 dark:focus:border-violet-500"
            />
            <div className="flex justify-end gap-1">
              <button
                onClick={handleSave}
                disabled={busy || !draft.trim()}
                className="rounded-lg bg-gradient-to-r from-violet-500 to-blue-500 px-2 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                保存
              </button>
              <button
                onClick={() => {
                  setEditing(false)
                  setDraft(memory.content)
                }}
                disabled={busy}
                className="rounded-lg px-2 py-1 text-xs text-neutral-500 transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-700"
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <p
            className={clsx(
              'flex-1 whitespace-pre-wrap break-all text-sm',
              !memory.isEnabled && 'text-neutral-400 line-through dark:text-neutral-500',
            )}
          >
            {memory.content}
          </p>
        )}
        <button
          onClick={handleToggle}
          disabled={busy}
          className={clsx(
            'relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors disabled:opacity-50',
            memory.isEnabled ? 'bg-gradient-to-r from-violet-500 to-blue-500' : 'bg-neutral-300',
          )}
          role="switch"
          aria-checked={memory.isEnabled}
          title={memory.isEnabled ? '停用该记忆' : '启用该记忆'}
        >
          <span
            className={clsx(
              'absolute top-0.5 size-4 rounded-full bg-white shadow transition-all',
              memory.isEnabled ? 'left-[18px]' : 'left-0.5',
            )}
          />
        </button>
      </div>
      {!editing && (
        <div className="mt-1 flex justify-end gap-1">
          <button
            onClick={() => {
              setDraft(memory.content)
              setEditing(true)
            }}
            className="rounded-lg px-2 py-0.5 text-xs text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-700 dark:hover:text-neutral-200"
          >
            编辑
          </button>
          {confirmDelete ? (
            <span className="flex items-center gap-1">
              <button
                onClick={handleDelete}
                disabled={busy}
                className="rounded-lg bg-red-500 px-2 py-0.5 text-xs font-medium text-white transition-colors hover:bg-red-600 disabled:opacity-50"
              >
                确认删除
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="rounded-lg px-2 py-0.5 text-xs text-neutral-500 transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-700"
              >
                取消
              </button>
            </span>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="rounded-lg px-2 py-0.5 text-xs text-neutral-500 transition-colors hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-950"
            >
              删除
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function MemorySettingsSection() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enabled, setEnabled] = useState(true)
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [newContent, setNewContent] = useState('')
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    memoryApi
      .getSettings()
      .then((s) => setEnabled(s.enabled))
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : '加载记忆设置失败')
      })
      .finally(() => setLoading(false))
    memoryApi
      .list()
      .then(setMemories)
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : '加载记忆列表失败')
      })
      .finally(() => setListLoading(false))
  }, [])

  const handleToggle = async () => {
    const next = !enabled
    setSaving(true)
    try {
      const updated = await memoryApi.updateSettings({ enabled: next })
      setEnabled(updated.enabled)
      toast.success('记忆设置已保存')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleAdd = async () => {
    const content = newContent.trim()
    if (!content || adding) return
    setAdding(true)
    try {
      const created = await memoryApi.create({ content })
      setMemories((list) => [created, ...list])
      setNewContent('')
      toast.success('记忆已添加')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '添加失败')
    } finally {
      setAdding(false)
    }
  }

  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold text-neutral-500 dark:text-neutral-400">长期记忆</h3>
      <div className="flex flex-col gap-3 rounded-xl border border-neutral-200 px-3 py-2.5 dark:border-neutral-700">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm">自动记住对话中的用户信息，并在回答时参考</span>
          {loading ? (
            <span className="text-sm text-neutral-400">加载中…</span>
          ) : (
            <button
              onClick={handleToggle}
              disabled={saving}
              className={clsx(
                'relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50',
                enabled ? 'bg-gradient-to-r from-violet-500 to-blue-500' : 'bg-neutral-300',
              )}
              role="switch"
              aria-checked={enabled}
            >
              <span
                className={clsx(
                  'absolute top-0.5 size-5 rounded-full bg-white shadow transition-all',
                  enabled ? 'left-[22px]' : 'left-0.5',
                )}
              />
            </button>
          )}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleAdd()
            }}
            disabled={adding}
            placeholder="手动添加一条记忆（如：我喜欢简洁的回答）"
            className="w-full flex-1 rounded-lg border border-neutral-300 bg-transparent px-3 py-1.5 text-sm outline-none transition-colors focus:border-violet-400 disabled:opacity-50 dark:border-neutral-600 dark:focus:border-violet-500"
          />
          <button
            onClick={handleAdd}
            disabled={adding || !newContent.trim()}
            className="shrink-0 rounded-lg bg-gradient-to-r from-violet-500 to-blue-500 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            添加
          </button>
        </div>
        {listLoading ? (
          <p className="py-2 text-center text-sm text-neutral-400">加载中…</p>
        ) : memories.length === 0 ? (
          <p className="py-2 text-center text-sm text-neutral-400">暂无记忆，随着对话自动积累</p>
        ) : (
          <div className="flex max-h-64 flex-col gap-2 overflow-y-auto">
            {memories.map((m) => (
              <MemoryRow
                key={m.id}
                memory={m}
                onChanged={(next) =>
                  setMemories((list) =>
                    next === null
                      ? list.filter((item) => item.id !== m.id)
                      : list.map((item) => (item.id === m.id ? next : item)),
                  )
                }
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

export function SettingsModal() {
  const providers = useSettingsStore((s) => s.providers)
  const providersLoading = useSettingsStore((s) => s.providersLoading)
  const providersError = useSettingsStore((s) => s.providersError)
  const theme = useSettingsStore((s) => s.theme)
  const [editing, setEditing] = useState<Provider | null>(null)
  const [adding, setAdding] = useState(false)

  const close = () => useSettingsStore.getState().setSettingsOpen(false)
  const showForm = adding || editing !== null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close()
      }}
    >
      <div className="flex max-h-[85vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl dark:bg-neutral-800">
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-3.5 dark:border-neutral-700">
          <h2 className="text-lg font-semibold">设置</h2>
          <button
            onClick={close}
            className="rounded-lg p-1.5 text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-600 dark:hover:bg-neutral-700 dark:hover:text-neutral-200"
            title="关闭"
          >
            <svg viewBox="0 0 20 20" className="size-4.5 fill-current">
              <path d="M5.3 5.3a1 1 0 0 1 1.4 0L10 8.6l3.3-3.3a1 1 0 1 1 1.4 1.4L11.4 10l3.3 3.3a1 1 0 0 1-1.4 1.4L10 11.4l-3.3 3.3a1 1 0 0 1-1.4-1.4L8.6 10 5.3 6.7a1 1 0 0 1 0-1.4z" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {showForm ? (
            <ProviderForm
              provider={editing}
              onClose={() => {
                setAdding(false)
                setEditing(null)
              }}
            />
          ) : (
            <div className="flex flex-col gap-5">
              {/* 主题 */}
              <section>
                <h3 className="mb-2 text-sm font-semibold text-neutral-500 dark:text-neutral-400">外观</h3>
                <div className="flex items-center justify-between rounded-xl border border-neutral-200 px-3 py-2.5 dark:border-neutral-700">
                  <span className="text-sm">深色模式</span>
                  <button
                    onClick={() => useSettingsStore.getState().toggleTheme()}
                    className={clsx(
                      'relative h-6 w-11 rounded-full transition-colors',
                      theme === 'dark' ? 'bg-gradient-to-r from-violet-500 to-blue-500' : 'bg-neutral-300',
                    )}
                    role="switch"
                    aria-checked={theme === 'dark'}
                  >
                    <span
                      className={clsx(
                        'absolute top-0.5 size-5 rounded-full bg-white shadow transition-all',
                        theme === 'dark' ? 'left-[22px]' : 'left-0.5',
                      )}
                    />
                  </button>
                </div>
              </section>

              {/* 联网搜索 */}
              <SearchSettingsSection />

              {/* Provider 管理 */}
              <section>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-neutral-500 dark:text-neutral-400">模型服务商</h3>
                  <button
                    onClick={() => setAdding(true)}
                    className="rounded-lg bg-gradient-to-r from-violet-500 to-blue-500 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
                  >
                    + 添加服务商
                  </button>
                </div>
                {providersLoading ? (
                  <p className="py-6 text-center text-sm text-neutral-400">加载中…</p>
                ) : providersError ? (
                  <div className="py-6 text-center">
                    <p className="text-sm text-red-400">{providersError}</p>
                    <button
                      onClick={() => useSettingsStore.getState().loadProviders()}
                      className="mt-2 rounded-lg px-3 py-1 text-xs text-violet-500 transition-colors hover:bg-violet-50 dark:hover:bg-violet-500/10"
                    >
                      重试
                    </button>
                  </div>
                ) : providers.length === 0 ? (
                  <p className="py-6 text-center text-sm text-neutral-400">
                    暂无服务商，点击右上角添加
                  </p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {providers.map((p) => (
                      <ProviderCard key={p.id} provider={p} onEdit={() => setEditing(p)} />
                    ))}
                  </div>
                )}
              </section>

              {/* 模型路由 */}
              <RoutingSettingsSection />

              {/* Agent 工具 */}
              <AgentToolsSettingsSection />

              {/* 长期记忆 */}
              <MemorySettingsSection />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
