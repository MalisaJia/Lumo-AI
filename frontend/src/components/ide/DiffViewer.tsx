import { DiffEditor } from '@monaco-editor/react'
import { useSettingsStore } from '../../stores/settingsStore'

interface DiffViewerProps {
  path: string
  oldContent: string
  newContent: string
}

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  c: 'c',
  cc: 'cpp',
  cpp: 'cpp',
  cs: 'csharp',
  css: 'css',
  go: 'go',
  html: 'html',
  java: 'java',
  js: 'javascript',
  json: 'json',
  jsx: 'javascript',
  md: 'markdown',
  py: 'python',
  rs: 'rust',
  scss: 'scss',
  sh: 'shell',
  sql: 'sql',
  ts: 'typescript',
  tsx: 'typescript',
  vue: 'html',
  xml: 'xml',
  yaml: 'yaml',
  yml: 'yaml',
}

function detectLanguage(filePath: string): string {
  const extension = filePath.split('.').pop()?.toLowerCase() ?? ''
  return LANGUAGE_BY_EXTENSION[extension] ?? 'plaintext'
}

export function DiffViewer({ path, oldContent, newContent }: DiffViewerProps) {
  const theme = useSettingsStore((state) => state.theme)

  return (
    <DiffEditor
      height="100%"
      original={oldContent}
      modified={newContent}
      language={detectLanguage(path)}
      theme={theme === 'dark' ? 'vs-dark' : 'vs'}
      options={{
        readOnly: true,
        originalEditable: false,
        renderSideBySide: true,
        automaticLayout: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineHeight: 21,
        renderOverviewRuler: false,
        diffWordWrap: 'on',
        padding: { top: 12, bottom: 12 },
      }}
    />
  )
}
