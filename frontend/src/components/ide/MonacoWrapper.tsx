import Editor from '@monaco-editor/react'
import { useSettingsStore } from '../../stores/settingsStore'

interface MonacoWrapperProps {
  value: string
  language: string
  onChange: (value: string) => void
}

export default function MonacoWrapper({ value, language, onChange }: MonacoWrapperProps) {
  const theme = useSettingsStore((state) => state.theme)

  return (
    <Editor
      height="100%"
      language={language}
      value={value}
      theme={theme === 'dark' ? 'vs-dark' : 'vs'}
      onChange={(nextValue) => onChange(nextValue ?? '')}
      options={{
        minimap: { enabled: false },
        fontSize: 13,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        wordWrap: 'on',
        automaticLayout: true,
        tabSize: 2,
      }}
      loading={
        <div className="flex h-full items-center justify-center text-sm text-neutral-500">
          加载编辑器...
        </div>
      }
    />
  )
}
