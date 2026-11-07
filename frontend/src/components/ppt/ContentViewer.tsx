// PPT 内容预览面板：按文件类型渲染选中的参考文件（文本 Monaco 只读 / 图片 / PDF）
import MonacoEditor from '@monaco-editor/react'
import { usePptStore, type PptRefFile } from '../../stores/pptStore'
import { useSettingsStore } from '../../stores/settingsStore'

const LANGUAGE_BY_EXT: Record<string, string> = {
  md: 'markdown',
  markdown: 'markdown',
  py: 'python',
  js: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  xml: 'xml',
  sql: 'sql',
  sh: 'shell',
  html: 'html',
  css: 'css',
  java: 'java',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  cs: 'csharp',
  go: 'go',
  rs: 'rust',
  rb: 'ruby',
  php: 'php',
}

function langFromExt(fileName: string): string {
  const i = fileName.lastIndexOf('.')
  const ext = i >= 0 ? fileName.slice(i + 1).toLowerCase() : ''
  return LANGUAGE_BY_EXT[ext] ?? 'plaintext'
}

const isPdf = (file: PptRefFile) =>
  file.mimeType === 'application/pdf' || file.fileName.toLowerCase().endsWith('.pdf')

function FileBody({ file }: { file: PptRefFile }) {
  const theme = useSettingsStore((state) => state.theme)

  if (file.content !== undefined) {
    return (
      <MonacoEditor
        height="100%"
        value={file.content}
        language={langFromExt(file.fileName)}
        theme={theme === 'dark' ? 'vs-dark' : 'vs'}
        options={{
          readOnly: true,
          domReadOnly: true,
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          automaticLayout: true,
        }}
        loading={
          <div className="flex h-full items-center justify-center text-sm text-neutral-500">
            加载预览...
          </div>
        }
      />
    )
  }

  if (file.mimeType.startsWith('image/')) {
    return (
      <div className="flex h-full items-center justify-center overflow-auto bg-[radial-gradient(circle,rgb(0_0_0/0.06)_1px,transparent_1px)] bg-[length:16px_16px] p-6 dark:bg-[radial-gradient(circle,rgb(255_255_255/0.06)_1px,transparent_1px)]">
        <img
          src={file.url}
          alt={file.fileName}
          className="max-h-full max-w-full rounded-lg object-contain shadow-lg"
        />
      </div>
    )
  }

  if (isPdf(file)) {
    return <iframe src={file.url} title={file.fileName} className="h-full w-full border-0 bg-white" />
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-neutral-400 dark:text-neutral-500">
      此文件类型暂不支持预览
      <a
        href={file.url}
        target="_blank"
        rel="noreferrer"
        className="rounded-lg px-3 py-1 text-xs text-violet-500 transition-colors hover:bg-violet-50 dark:hover:bg-violet-500/10"
      >
        在新窗口打开
      </a>
    </div>
  )
}

export function ContentViewer() {
  const selectedFileId = usePptStore((state) => state.selectedFileId)
  const referenceFiles = usePptStore((state) => state.referenceFiles)
  const file = referenceFiles.find((item) => item.id === selectedFileId)

  if (!file) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center gap-3 bg-neutral-50 text-sm text-neutral-400 dark:bg-neutral-950 dark:text-neutral-500">
        <span className="flex size-12 items-center justify-center rounded-2xl border border-neutral-200 bg-white text-neutral-300 shadow-sm dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-600">
          <svg viewBox="0 0 24 24" className="size-6 fill-none stroke-current" strokeWidth="1.6">
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
            <path d="M14 3v5h5M9 13h6M9 17h4" />
          </svg>
        </span>
        从左侧选择参考文件查看内容
      </div>
    )
  }

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-white dark:bg-neutral-950">
      <header className="relative flex h-10 shrink-0 items-center gap-2 border-b border-neutral-200 bg-neutral-50 px-3 dark:border-neutral-800 dark:bg-neutral-900">
        <span className="absolute inset-x-0 bottom-0 h-0.5 bg-gradient-to-r from-violet-500 to-blue-500" />
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-neutral-800 dark:text-neutral-100" title={file.fileName}>
          {file.fileName}
        </span>
        <button
          type="button"
          onClick={() => usePptStore.getState().selectFile(null)}
          aria-label="关闭预览"
          title="关闭预览"
          className="rounded px-1 text-sm leading-5 text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-700 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
        >
          ×
        </button>
      </header>
      <div className="min-h-0 flex-1">
        <FileBody file={file} />
      </div>
    </section>
  )
}
