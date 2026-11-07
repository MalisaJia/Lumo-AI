import { useState } from 'react'

declare global {
  interface Window {
    lumoDesktop?: {
      pickFolder: () => Promise<string | null>
    }
  }
}

interface WorkspacePickerProps {
  onSelect: (path: string) => void
}

const RECENT_WORKSPACES_KEY = 'lumo-recent-workspaces'

function readRecentWorkspaces(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(RECENT_WORKSPACES_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((path): path is string => typeof path === 'string').slice(0, 5) : []
  } catch {
    return []
  }
}

export function WorkspacePicker({ onSelect }: WorkspacePickerProps) {
  const [path, setPath] = useState('')
  const [recentWorkspaces, setRecentWorkspaces] = useState(readRecentWorkspaces)

  const selectWorkspace = (workspacePath: string) => {
    const trimmedPath = workspacePath.trim()
    if (!trimmedPath) return

    const updatedRecent = [trimmedPath, ...recentWorkspaces.filter((item) => item !== trimmedPath)].slice(0, 5)
    setRecentWorkspaces(updatedRecent)
    localStorage.setItem(RECENT_WORKSPACES_KEY, JSON.stringify(updatedRecent))
    onSelect(trimmedPath)
  }

  const pickFolder = async () => {
    if (window.lumoDesktop) {
      const selectedPath = await window.lumoDesktop.pickFolder()
      if (selectedPath) selectWorkspace(selectedPath)
      return
    }
    // Browser fallback: call backend API
    try {
      const res = await fetch('/api/workspace/pick-folder')
      const data = await res.json()
      if (data.path) selectWorkspace(data.path)
    } catch {
      // Ignore picker failures; manual path entry remains available.
    }
  }

  return (
    <div className="relative flex flex-1 items-center justify-center overflow-y-auto px-6 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(520px 280px at 34% 30%, rgb(139 92 246 / 0.09), transparent 72%), radial-gradient(500px 300px at 72% 70%, rgb(59 130 246 / 0.08), transparent 72%)',
        }}
      />
      <section className="animate-fade-up relative w-full max-w-lg rounded-xl border border-neutral-200 bg-white p-6 shadow-xl shadow-neutral-900/5 dark:border-neutral-700 dark:bg-neutral-800 dark:shadow-black/20">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex size-11 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 text-white shadow-md shadow-violet-500/20">
            <svg viewBox="0 0 24 24" className="size-5 fill-current" aria-hidden>
              <path d="M3 5.75A2.75 2.75 0 0 1 5.75 3h4.1c.73 0 1.42.29 1.94.8l1.16 1.17c.14.14.33.22.53.22h4.77A2.75 2.75 0 0 1 21 7.94v8.31A2.75 2.75 0 0 1 18.25 19H5.75A2.75 2.75 0 0 1 3 16.25V5.75Z" />
            </svg>
          </div>
          <h1 className="bg-gradient-to-r from-violet-500 to-blue-500 bg-clip-text text-2xl font-semibold text-transparent">
            选择工作区
          </h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">打开项目文件夹以开始编码</p>
        </div>

        <button
          type="button"
          onClick={pickFolder}
          className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-500 to-blue-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:opacity-90 hover:shadow-md hover:shadow-violet-500/20"
        >
          <svg viewBox="0 0 20 20" className="size-4 fill-current" aria-hidden>
            <path d="M2 5a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v1H2V5Zm0 5h16l-1.35 5.4A2 2 0 0 1 14.7 17H4a2 2 0 0 1-2-2v-5Z" />
          </svg>
          选择文件夹
        </button>

        <form
          onSubmit={(event) => {
            event.preventDefault()
            selectWorkspace(path)
          }}
          className="flex gap-2"
        >
          <input
            value={path}
            onChange={(event) => setPath(event.target.value)}
            placeholder="输入工作区路径"
            aria-label="工作区路径"
            className="min-w-0 flex-1 rounded-xl border border-neutral-200 bg-neutral-50 px-3 py-2.5 text-sm text-neutral-800 outline-none transition-colors placeholder:text-neutral-400 focus:border-violet-400 dark:border-neutral-700 dark:bg-neutral-900/60 dark:text-neutral-200 dark:focus:border-violet-500"
          />
          <button
            type="submit"
            disabled={!path.trim()}
            className="rounded-xl bg-neutral-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white"
          >
            打开
          </button>
        </form>

        {recentWorkspaces.length > 0 && (
          <div className="mt-6 border-t border-neutral-100 pt-4 dark:border-neutral-700">
            <p className="mb-2 px-1 text-[11px] font-medium tracking-wide text-neutral-400 uppercase">最近使用</p>
            <div className="space-y-1">
              {recentWorkspaces.map((workspacePath) => (
                <button
                  key={workspacePath}
                  type="button"
                  onClick={() => selectWorkspace(workspacePath)}
                  title={workspacePath}
                  className="group flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-neutral-600 transition-colors hover:bg-violet-50 hover:text-violet-700 dark:text-neutral-300 dark:hover:bg-violet-500/10 dark:hover:text-violet-300"
                >
                  <svg viewBox="0 0 20 20" className="size-4 shrink-0 fill-current text-neutral-400 group-hover:text-violet-500" aria-hidden>
                    <path d="M2 5a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5Z" />
                  </svg>
                  <span className="truncate">{workspacePath}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
