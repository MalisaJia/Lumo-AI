import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import { useIdeStore } from '../../stores/ideStore'
import { DiffViewer } from './DiffViewer'

const MonacoWrapper = lazy(() => import('./MonacoWrapper'))

function highlightCode(code: string, language: string): string {
  try {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(code, { language }).value
    }
    return hljs.highlightAuto(code).value
  } catch {
    return hljs.highlightAuto(code).value
  }
}

export function CodeViewer() {
  const openFiles = useIdeStore((state) => state.openFiles)
  const activeFileIndex = useIdeStore((state) => state.activeFileIndex)
  const diffFile = useIdeStore((state) => state.diffFile)
  const closeDiff = useIdeStore((state) => state.closeDiff)
  const setActiveFile = useIdeStore((state) => state.setActiveFile)
  const closeFile = useIdeStore((state) => state.closeFile)
  const saveFile = useIdeStore((state) => state.saveFile)
  const updateFileContent = useIdeStore((state) => state.updateFileContent)
  const [editing, setEditing] = useState(false)

  const activeFile = activeFileIndex === null ? undefined : openFiles[activeFileIndex]
  const lineCount = activeFile ? activeFile.content.split('\n').length : 0
  const highlightedCode = useMemo(
    () => (activeFile ? highlightCode(activeFile.content, activeFile.language) : ''),
    [activeFile],
  )

  useEffect(() => {
    setEditing(false)
  }, [activeFileIndex])

  useEffect(() => {
    if (!editing || activeFileIndex === null) return

    const handleSaveShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        void saveFile(activeFileIndex)
      }
    }

    window.addEventListener('keydown', handleSaveShortcut)
    return () => window.removeEventListener('keydown', handleSaveShortcut)
  }, [activeFileIndex, editing, saveFile])

  if (diffFile) {
    const fileName = diffFile.path.split(/[\\/]/).pop() || diffFile.path
    return (
      <section className="flex h-full min-h-0 flex-col overflow-hidden bg-white dark:bg-neutral-950">
        <header className="flex h-11 shrink-0 items-center gap-3 border-b border-neutral-200 bg-neutral-50 px-3 dark:border-neutral-800 dark:bg-neutral-900">
          <span className="flex size-7 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
            <svg viewBox="0 0 24 24" className="size-4 fill-none stroke-current" strokeWidth="1.7">
              <path d="M8 7 4 11l4 4M16 7l4 4-4 4M14 4l-4 16" />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-neutral-800 dark:text-neutral-100">
              {fileName}
            </p>
            <p className="truncate font-mono text-[10px] text-neutral-400" title={diffFile.path}>
              {diffFile.path}
            </p>
          </div>
          <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-semibold tracking-wide text-emerald-700 uppercase dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300">
            Diff
          </span>
          <button
            type="button"
            onClick={closeDiff}
            className="rounded-md border border-neutral-200 px-2.5 py-1 text-xs text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-800 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
          >
            关闭
          </button>
        </header>
        <div className="min-h-0 flex-1">
          <DiffViewer
            path={diffFile.path}
            oldContent={diffFile.oldContent}
            newContent={diffFile.newContent}
          />
        </div>
      </section>
    )
  }

  if (!activeFile || activeFileIndex === null) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center bg-neutral-50 text-sm text-neutral-400 dark:bg-neutral-950 dark:text-neutral-500">
        选择文件开始浏览
      </div>
    )
  }

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-white dark:bg-neutral-950">
      <div className="flex shrink-0 overflow-x-auto whitespace-nowrap border-b border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900">
        {openFiles.map((file, index) => {
          const isActive = index === activeFileIndex
          return (
            <div
              key={file.path}
              className={`group relative flex h-10 shrink-0 items-center border-r border-neutral-200 text-xs transition-colors dark:border-neutral-800 ${
                isActive
                  ? 'bg-white font-medium text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100'
                  : 'text-neutral-500 hover:bg-white/70 hover:text-neutral-800 dark:text-neutral-400 dark:hover:bg-neutral-800/70 dark:hover:text-neutral-200'
              }`}
            >
              {isActive && (
                <span className="absolute inset-x-0 bottom-0 h-0.5 bg-gradient-to-r from-violet-500 to-blue-500" />
              )}
              <button
                type="button"
                onClick={() => setActiveFile(index)}
                title={file.path}
                className="flex h-full min-w-0 items-center gap-2 pl-3"
              >
                <span className="max-w-44 truncate">{file.name}</span>
                {file.isDirty && <span className="text-[9px] text-violet-500">●</span>}
              </button>
              <button
                type="button"
                aria-label={`关闭 ${file.name}`}
                onClick={() => closeFile(index)}
                className="mx-1 rounded px-1 text-sm leading-5 text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-700 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
              >
                ×
              </button>
            </div>
          )
        })}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex h-10 shrink-0 items-center justify-end gap-2 border-b border-neutral-200 bg-white px-3 dark:border-neutral-800 dark:bg-neutral-950">
          {editing ? (
            <>
              <button
                type="button"
                onClick={() => void saveFile(activeFileIndex)}
                className="rounded-md bg-gradient-to-r from-violet-600 to-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:brightness-110"
              >
                保存
                <span className="ml-1.5 text-[10px] text-white/70">Ctrl+S</span>
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-md border border-neutral-200 px-3 py-1.5 text-xs text-neutral-600 transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
              >
                取消
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-md border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs font-medium text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-300 dark:hover:bg-violet-500/20"
            >
              编辑
            </button>
          )}
        </div>

        {editing ? (
          <Suspense
            fallback={
              <div className="flex flex-1 items-center justify-center text-sm text-neutral-500">
                加载编辑器...
              </div>
            }
          >
            <div className="min-h-0 flex-1">
              <MonacoWrapper
                value={activeFile.content}
                language={activeFile.language}
                onChange={(value) => updateFileContent(activeFileIndex, value)}
              />
            </div>
          </Suspense>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto bg-[#0d1117]">
            <div className="flex min-w-max py-4 font-mono text-[13px] leading-6">
              <div aria-hidden="true" className="select-none border-r border-white/10 px-3 text-right text-neutral-600">
                {Array.from({ length: lineCount }, (_, index) => (
                  <span key={index} className="block min-w-8">
                    {index + 1}
                  </span>
                ))}
              </div>
              <pre className="m-0 px-4 text-neutral-200">
                <code
                  className={`hljs language-${activeFile.language} block !overflow-visible !bg-transparent !p-0`}
                  dangerouslySetInnerHTML={{ __html: highlightedCode }}
                />
              </pre>
            </div>
          </div>
        )}
      </div>

      <footer className="flex h-7 shrink-0 items-center justify-between gap-4 border-t border-neutral-200 bg-neutral-50 px-3 font-mono text-[11px] text-neutral-500 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
        <span className="min-w-0 truncate" title={activeFile.path}>
          {activeFile.path}
        </span>
        <span className="shrink-0">
          {lineCount} 行&nbsp;&nbsp;·&nbsp;&nbsp;{activeFile.language || 'text'}
        </span>
      </footer>
    </section>
  )
}
