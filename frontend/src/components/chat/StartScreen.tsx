// 开始页：品牌 logo + 欢迎语，按 Provider 配置状态展示引导卡片或示例提示词
import { useChatStore } from '../../stores/chatStore'
import { useSettingsStore } from '../../stores/settingsStore'

// 示例提示词：点击即以该内容新建会话并发送
const SAMPLE_PROMPTS = [
  { icon: '✍️', title: '写作', prompt: '帮我写一段自我介绍' },
  { icon: '🧠', title: '解释', prompt: '解释一个复杂概念（比如量子纠缠）' },
  { icon: '💻', title: '编程', prompt: '用 Python 写一个小工具' },
  { icon: '🌍', title: '翻译', prompt: '把一段话翻译成英文并润色' },
]

function PromptCard({ icon, title, prompt, index }: (typeof SAMPLE_PROMPTS)[number] & { index: number }) {
  return (
    <button
      onClick={() => useChatStore.getState().sendMessage(prompt)}
      style={{ animationDelay: `${150 + index * 60}ms` }}
      className="group animate-fade-up flex flex-col items-start gap-2 rounded-2xl border border-neutral-200 bg-white/70 p-4 text-left opacity-0 shadow-sm backdrop-blur transition-all duration-200 hover:-translate-y-1 hover:border-violet-300 hover:shadow-md hover:shadow-violet-500/10 dark:border-neutral-700 dark:bg-neutral-800/60 dark:hover:border-violet-500/50"
    >
      <span className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-400/15 to-blue-400/15 text-lg transition-transform duration-200 group-hover:scale-110">
        {icon}
      </span>
      <span className="text-xs font-medium text-violet-500/80 dark:text-violet-300/80">{title}</span>
      <span className="text-sm leading-relaxed text-neutral-700 transition-colors group-hover:text-neutral-900 dark:text-neutral-300 dark:group-hover:text-neutral-100">
        {prompt}
      </span>
    </button>
  )
}

// 未配置 Provider 时的引导卡片
function SetupGuideCard() {
  return (
    <div className="animate-fade-up w-full max-w-md rounded-2xl border border-violet-200/70 bg-gradient-to-br from-violet-50/80 to-blue-50/80 p-6 text-center opacity-0 [animation-delay:150ms] dark:border-violet-500/25 dark:from-violet-400/10 dark:to-blue-400/10">
      <span className="mx-auto flex size-11 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-400 to-blue-400 text-xl text-white shadow-md shadow-violet-500/20">
        🔑
      </span>
      <p className="mt-3 text-sm font-medium text-neutral-700 dark:text-neutral-200">
        先添加 API Key 才能开始对话
      </p>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        在设置中配置模型服务商（Base URL + API Key），即可开启第一次对话
      </p>
      <button
        onClick={() => useSettingsStore.getState().setSettingsOpen(true)}
        className="mt-4 rounded-xl bg-gradient-to-r from-violet-400 to-blue-400 px-5 py-2 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:opacity-90 hover:shadow-md hover:shadow-violet-500/20"
      >
        去添加服务商
      </button>
    </div>
  )
}

export function StartScreen() {
  const providers = useSettingsStore((s) => s.providers)
  const providersLoading = useSettingsStore((s) => s.providersLoading)

  return (
    <div className="relative flex flex-1 flex-col items-center justify-center overflow-y-auto px-6 py-8">
      {/* 柔和的紫蓝氛围光晕背景 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(560px 320px at 30% 24%, rgb(139 92 246 / 0.08), transparent 70%), radial-gradient(560px 320px at 70% 68%, rgb(59 130 246 / 0.08), transparent 70%)',
        }}
      />

      <div className="relative flex w-full max-w-2xl flex-col items-center gap-4">
        <h1 className="animate-fade-up bg-gradient-to-r from-violet-400 via-indigo-400 to-blue-400 bg-clip-text text-5xl font-bold text-transparent opacity-0">
          Lumo AI
        </h1>
        <p className="animate-fade-up max-w-md text-center text-neutral-500 opacity-0 [animation-delay:80ms] dark:text-neutral-400">
          你的智能对话助手。在下方输入消息开始新对话，或从左侧选择历史会话继续。
        </p>

        <div className="mt-4 flex w-full justify-center">
          {providersLoading ? null : providers.length === 0 ? (
            <SetupGuideCard />
          ) : (
            <div className="grid w-full max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
              {SAMPLE_PROMPTS.map((p, i) => (
                <PromptCard key={p.prompt} {...p} index={i} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
