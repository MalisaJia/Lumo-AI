// Provider 添加/编辑表单：name/baseUrl/apiKey/模型列表 + Key 验证与模型导入
import { useState } from 'react'
import clsx from 'clsx'
import { providersApi } from '../../api/client'
import type { CapabilityTag, Provider, ProviderModelInput } from '../../api/types'
import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'

interface ProviderFormProps {
  provider: Provider | null // null = 新增
  onClose: () => void
}

const inputCls =
  'w-full rounded-xl border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-800 outline-none transition-colors placeholder:text-neutral-400 focus:border-violet-400 dark:border-neutral-600 dark:bg-neutral-700 dark:text-neutral-100 dark:focus:border-violet-500'

// 能力标签选项（智能选模用，中文 ↔ 契约枚举值）
const CAPABILITY_OPTIONS: { value: CapabilityTag; label: string }[] = [
  { value: 'code', label: '代码' },
  { value: 'writing', label: '文案' },
  { value: 'long_text', label: '长文' },
  { value: 'reasoning', label: '推理' },
  { value: 'vision', label: '视觉' },
  { value: 'general', label: '通用' },
]

export function ProviderForm({ provider, onClose }: ProviderFormProps) {
  const isEdit = provider !== null
  const [name, setName] = useState(provider?.name ?? '')
  const [baseUrl, setBaseUrl] = useState(provider?.baseUrl ?? '')
  const [apiKey, setApiKey] = useState('')
  const [models, setModels] = useState<ProviderModelInput[]>(
    provider?.models.map((m) => ({
      name: m.name,
      label: m.label,
      isDefault: m.isDefault,
      capabilityTags: m.capabilityTags ?? null,
    })) ?? [],
  )
  const [newModelName, setNewModelName] = useState('')
  const [validating, setValidating] = useState(false)
  const [validatedModels, setValidatedModels] = useState<string[] | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const addModel = (modelName: string) => {
    const n = modelName.trim()
    if (!n || models.some((m) => m.name === n)) return
    setModels((prev) => [...prev, { name: n, isDefault: prev.length === 0 }])
  }

  const removeModel = (modelName: string) => {
    setModels((prev) => prev.filter((m) => m.name !== modelName))
  }

  const setDefaultModel = (modelName: string) => {
    setModels((prev) => prev.map((m) => ({ ...m, isDefault: m.name === modelName })))
  }

  // 切换模型能力标签；空数组归一化为 null（表示用内置默认）
  const toggleCapability = (modelName: string, tag: CapabilityTag) => {
    setModels((prev) =>
      prev.map((m) => {
        if (m.name !== modelName) return m
        const current = m.capabilityTags ?? []
        const next = current.includes(tag)
          ? current.filter((t) => t !== tag)
          : [...current, tag]
        return { ...m, capabilityTags: next.length > 0 ? next : null }
      }),
    )
  }

  const handleValidate = async () => {
    if (!baseUrl.trim() || !apiKey.trim()) {
      toast.error('请先填写 Base URL 和 API Key')
      return
    }
    setValidating(true)
    setValidatedModels(null)
    try {
      const result = await providersApi.validate({ baseUrl: baseUrl.trim(), apiKey: apiKey.trim() })
      if (result.valid) {
        toast.success('验证通过')
        if (result.models?.length) setValidatedModels(result.models)
      } else {
        toast.error(result.error || '验证失败')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '验证失败')
    } finally {
      setValidating(false)
    }
  }

  const handleSave = async () => {
    if (!name.trim() || !baseUrl.trim()) {
      toast.error('请填写名称和 Base URL')
      return
    }
    if (!isEdit && !apiKey.trim()) {
      toast.error('请填写 API Key')
      return
    }
    if (models.length === 0) {
      toast.error('请至少添加一个模型')
      return
    }
    setSaving(true)
    setSaveError(null)
    try {
      if (isEdit) {
        await providersApi.update(provider.id, {
          name: name.trim(),
          baseUrl: baseUrl.trim(),
          ...(apiKey.trim() ? { apiKey: apiKey.trim() } : {}),
          models,
        })
        toast.success('服务商已更新')
      } else {
        await providersApi.create({
          name: name.trim(),
          baseUrl: baseUrl.trim(),
          apiKey: apiKey.trim(),
          models,
        })
        toast.success('服务商已添加')
      }
      await useSettingsStore.getState().loadProviders()
      // 仅保存成功时关闭表单
      onClose()
    } catch (err) {
      // 保存失败：不关闭表单，表单内展示后端返回的错误信息，同时弹 toast
      const message = err instanceof Error ? err.message : '保存失败'
      setSaveError(message)
      toast.error(message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-base font-semibold">{isEdit ? '编辑服务商' : '添加服务商'}</h3>

      <div>
        <label className="mb-1 block text-xs font-medium text-neutral-500 dark:text-neutral-400">名称</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 OpenAI" className={inputCls} />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-neutral-500 dark:text-neutral-400">Base URL</label>
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" className={inputCls} />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-neutral-500 dark:text-neutral-400">
          API Key{isEdit && <span className="ml-1 text-neutral-400">（留空保留原值：{provider.maskedKey}）</span>}
        </label>
        <div className="flex gap-2">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={isEdit ? '不修改请留空' : 'sk-…'}
            className={inputCls}
          />
          <button
            onClick={handleValidate}
            disabled={validating}
            className="shrink-0 rounded-xl border border-violet-300 px-3 py-2 text-sm font-medium text-violet-600 transition-colors hover:bg-violet-50 disabled:opacity-50 dark:border-violet-700 dark:text-violet-300 dark:hover:bg-violet-500/10"
          >
            {validating ? '验证中…' : '验证'}
          </button>
        </div>
      </div>

      {/* 验证返回模型可勾选导入 */}
      {validatedModels && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-800 dark:bg-emerald-950">
          <p className="mb-2 text-xs font-medium text-emerald-700 dark:text-emerald-300">验证成功，勾选导入可用模型：</p>
          <div className="flex max-h-40 flex-col gap-1 overflow-y-auto">
            {validatedModels.map((m) => {
              const added = models.some((x) => x.name === m)
              return (
                <label key={m} className="flex cursor-pointer items-center gap-2 text-sm text-neutral-700 dark:text-neutral-200">
                  <input
                    type="checkbox"
                    checked={added}
                    onChange={() => (added ? removeModel(m) : addModel(m))}
                    className="accent-violet-500"
                  />
                  <span className="truncate font-mono text-xs">{m}</span>
                </label>
              )
            })}
          </div>
        </div>
      )}

      <div>
        <label className="mb-1 block text-xs font-medium text-neutral-500 dark:text-neutral-400">模型列表</label>
        <div className="flex flex-col gap-1.5">
          {models.map((m) => (
            <div key={m.name} className="flex flex-col gap-1.5 rounded-xl border border-neutral-200 px-3 py-1.5 dark:border-neutral-600">
              <div className="flex items-center gap-2">
                <span className="flex-1 truncate font-mono text-xs text-neutral-700 dark:text-neutral-200">{m.name}</span>
                <button
                  onClick={() => setDefaultModel(m.name)}
                  className={clsx(
                    'rounded-md px-1.5 py-0.5 text-xs transition-colors',
                    m.isDefault
                      ? 'bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-300'
                      : 'text-neutral-400 hover:text-violet-500',
                  )}
                >
                  {m.isDefault ? '默认' : '设默认'}
                </button>
                <button
                  onClick={() => removeModel(m.name)}
                  className="rounded-md p-0.5 text-neutral-400 transition-colors hover:text-red-500"
                  title="移除"
                >
                  <svg viewBox="0 0 20 20" className="size-3.5 fill-current">
                    <path d="M5.3 5.3a1 1 0 0 1 1.4 0L10 8.6l3.3-3.3a1 1 0 1 1 1.4 1.4L11.4 10l3.3 3.3a1 1 0 0 1-1.4 1.4L10 11.4l-3.3 3.3a1 1 0 0 1-1.4-1.4L8.6 10 5.3 6.7a1 1 0 0 1 0-1.4z" />
                  </svg>
                </button>
              </div>
              {/* 能力标签多选 chip（智能选模用） */}
              <div className="flex flex-wrap items-center gap-1">
                {CAPABILITY_OPTIONS.map((opt) => {
                  const selected = (m.capabilityTags ?? []).includes(opt.value)
                  return (
                    <button
                      key={opt.value}
                      onClick={() => toggleCapability(m.name, opt.value)}
                      className={clsx(
                        'rounded-full border px-2 py-0.5 text-xs transition-colors',
                        selected
                          ? 'border-violet-300 bg-violet-100 text-violet-600 dark:border-violet-700 dark:bg-violet-500/20 dark:text-violet-300'
                          : 'border-neutral-200 text-neutral-400 hover:border-violet-300 hover:text-violet-500 dark:border-neutral-600',
                      )}
                    >
                      {opt.label}
                    </button>
                  )
                })}
                {(m.capabilityTags ?? []).length === 0 && (
                  <span className="text-xs text-neutral-400 dark:text-neutral-500">留空使用内置默认</span>
                )}
              </div>
            </div>
          ))}
          <div className="flex gap-2">
            <input
              value={newModelName}
              onChange={(e) => setNewModelName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  addModel(newModelName)
                  setNewModelName('')
                }
              }}
              placeholder="输入模型名后回车添加，如 gpt-4o"
              className={inputCls}
            />
            <button
              onClick={() => {
                addModel(newModelName)
                setNewModelName('')
              }}
              className="shrink-0 rounded-xl border border-neutral-300 px-3 py-2 text-sm text-neutral-600 transition-colors hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-700"
            >
              添加
            </button>
          </div>
        </div>
      </div>

      {/* 保存失败警示条 */}
      {saveError && (
        <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 dark:border-red-800 dark:bg-red-950">
          <svg viewBox="0 0 20 20" className="mt-0.5 size-4 shrink-0 fill-red-500 dark:fill-red-400">
            <path d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm0 4a1 1 0 0 1 1 1v3.5a1 1 0 1 1-2 0V7a1 1 0 0 1 1-1zm0 8.5a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5z" />
          </svg>
          <p className="text-sm break-all text-red-600 dark:text-red-300">保存失败：{saveError}</p>
        </div>
      )}

      <div className="mt-1 flex justify-end gap-2">
        <button
          onClick={onClose}
          className="rounded-xl px-4 py-2 text-sm text-neutral-500 transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-700"
        >
          取消
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-xl bg-gradient-to-r from-violet-500 to-blue-500 px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  )
}
