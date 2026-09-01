// 输入框：自适应高度，Enter 发送 / Shift+Enter 换行，流式中变为停止按钮；
// 支持附件上传（按钮选择/粘贴）：图片缩略图预览、文档文件 chip 预览，随消息发送
import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { uploadsApi } from '../../api/client'
import type { Attachment } from '../../api/types'
import { useChatStore } from '../../stores/chatStore'
import { toast } from '../../stores/toastStore'
import { PptDialog } from './PptDialog'

const MAX_FILES = 4
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 单文件 10MB（与后端一致）

// 文档扩展名白名单（与后端 /api/uploads 放行列表一致）
const DOC_EXTENSIONS = [
  '.pdf', '.txt', '.md', '.markdown',
  '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.c', '.cpp', '.h', '.cs',
  '.go', '.rs', '.rb', '.php', '.html', '.css',
  '.json', '.yaml', '.yml', '.xml', '.sql', '.sh', '.csv', '.log',
]
const FILE_ACCEPT = ['image/*', ...DOC_EXTENSIONS].join(',')

const extOf = (name: string) => {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}
const isAcceptedFile = (f: File) =>
  f.type.startsWith('image/') || DOC_EXTENSIONS.includes(extOf(f.name))

// 待发送附件：图片先本地预览，上传成功后携带服务端 attachment
interface PendingFile {
  localId: string
  fileName: string
  isImage: boolean
  previewUrl?: string // 仅图片有本地预览
  status: 'uploading' | 'done'
  attachment?: Attachment
}

let fileSeq = 1

export function ChatInput() {
  const [value, setValue] = useState('')
  const [files, setFiles] = useState<PendingFile[]>([])
  const [pptDialogOpen, setPptDialogOpen] = useState(false)
  const streaming = useChatStore((s) => s.streaming)
  const webSearchEnabled = useChatStore((s) => s.webSearchEnabled)
  const pendingInput = useChatStore((s) => s.pendingInput)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 卸载时释放所有 objectURL
  const filesRef = useRef(files)
  filesRef.current = files
  useEffect(
    () => () =>
      filesRef.current.forEach((f) => f.previewUrl && URL.revokeObjectURL(f.previewUrl)),
    [],
  )

  const resize = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  // 发送失败且未落库时回填内容，避免用户输入丢失（不覆盖已在输入的新内容）
  useEffect(() => {
    if (pendingInput === null) return
    setValue((v) => v || pendingInput)
    useChatStore.getState().clearPendingInput()
    requestAnimationFrame(resize)
  }, [pendingInput])

  const removeFile = (localId: string) => {
    setFiles((list) => {
      const target = list.find((f) => f.localId === localId)
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl)
      return list.filter((f) => f.localId !== localId)
    })
  }

  // 选中/粘贴后立即上传；失败 toast 并移除预览
  const addFiles = (candidates: File[]) => {
    const accepted = candidates.filter(isAcceptedFile)
    if (!accepted.length) return
    // 超 10MB 的文件提示并跳过
    const valid = accepted.filter((file) => {
      if (file.size > MAX_FILE_SIZE) {
        toast.error(`「${file.name}」超过 10MB，已跳过`)
        return false
      }
      return true
    })
    if (!valid.length) return
    const room = MAX_FILES - filesRef.current.length
    if (room <= 0) {
      toast.error(`最多上传 ${MAX_FILES} 个附件`)
      return
    }
    if (valid.length > room) toast.error(`最多上传 ${MAX_FILES} 个附件`)
    for (const file of valid.slice(0, room)) {
      const localId = `file-${fileSeq++}`
      const isImage = file.type.startsWith('image/')
      const previewUrl = isImage ? URL.createObjectURL(file) : undefined
      setFiles((list) => [
        ...list,
        { localId, fileName: file.name, isImage, previewUrl, status: 'uploading' },
      ])
      uploadsApi
        .upload(file)
        .then((res) => {
          setFiles((list) =>
            list.map((f) =>
              f.localId === localId
                ? {
                    ...f,
                    status: 'done',
                    attachment: {
                      id: res.id,
                      url: res.url,
                      fileName: res.fileName,
                      mimeType: res.mimeType,
                    },
                  }
                : f,
            ),
          )
        })
        .catch((err) => {
          toast.error(err instanceof Error ? err.message : '附件上传失败')
          removeFile(localId)
        })
    }
  }

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = Array.from(e.clipboardData?.files ?? [])
    if (pasted.some(isAcceptedFile)) {
      e.preventDefault()
      addFiles(pasted)
    }
  }

  const uploading = files.some((f) => f.status === 'uploading')
  const attachments = files
    .filter((f) => f.status === 'done' && f.attachment)
    .map((f) => f.attachment!)
  const canSend = !streaming && (!!value.trim() || attachments.length > 0)

  const handleSend = () => {
    const content = value.trim()
    if (streaming || (!content && !attachments.length)) return
    if (uploading) {
      toast.error('附件上传中，请稍候')
      return
    }
    setValue('')
    files.forEach((f) => f.previewUrl && URL.revokeObjectURL(f.previewUrl))
    setFiles([])
    requestAnimationFrame(resize)
    useChatStore.getState().sendMessage(content, attachments)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="border-t border-neutral-200 bg-white/80 px-4 py-3 backdrop-blur dark:border-neutral-800 dark:bg-neutral-900/80">
      <div className="mx-auto flex max-w-3xl flex-col gap-1.5 rounded-2xl border border-neutral-300 bg-white p-2 shadow-sm transition-colors focus-within:border-violet-400 dark:border-neutral-700 dark:bg-neutral-800 dark:focus-within:border-violet-500">
        {/* 附件预览条：图片缩略图 / 文档文件 chip */}
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1 pt-1">
            {files.map((f) => (
              <div
                key={f.localId}
                className={clsx(
                  'group/thumb relative h-16 overflow-hidden rounded-xl border border-neutral-200 dark:border-neutral-600',
                  f.isImage
                    ? 'size-16'
                    : 'flex max-w-[200px] items-center gap-2 bg-neutral-50 px-2.5 dark:bg-neutral-700/40',
                )}
              >
                {f.isImage ? (
                  <img
                    src={f.previewUrl}
                    alt={f.fileName}
                    className="size-full object-cover"
                  />
                ) : (
                  <>
                    <svg
                      viewBox="0 0 24 24"
                      className="size-6 shrink-0 fill-none stroke-violet-500 dark:stroke-violet-400"
                      strokeWidth="1.6"
                    >
                      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
                      <path d="M14 3v5h5" />
                    </svg>
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate text-xs text-neutral-600 dark:text-neutral-300">
                        {f.fileName}
                      </span>
                      <span className="text-[10px] text-neutral-400 uppercase">
                        {extOf(f.fileName).slice(1) || '文件'}
                      </span>
                    </span>
                  </>
                )}
                {f.status === 'uploading' && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <span className="size-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  </div>
                )}
                <button
                  onClick={() => removeFile(f.localId)}
                  title="移除附件"
                  className="absolute top-0.5 right-0.5 flex size-4.5 items-center justify-center rounded-full bg-black/60 text-[11px] leading-none text-white opacity-0 transition-opacity group-hover/thumb:opacity-100 hover:bg-black/80"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              resize()
            }}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            rows={1}
            placeholder="给 Lumo 发送消息…（Enter 发送，Shift+Enter 换行）"
            className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] leading-6 text-neutral-800 outline-none placeholder:text-neutral-400 dark:text-neutral-200"
          />
          {streaming ? (
            <button
              onClick={() => useChatStore.getState().stopStreaming()}
              title="停止生成"
              className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-neutral-800 text-white transition-colors hover:bg-neutral-700 dark:bg-neutral-200 dark:text-neutral-900 dark:hover:bg-neutral-300"
            >
              <span className="block size-3 rounded-[2px] bg-current" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!canSend}
              title="发送"
              className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              <svg viewBox="0 0 24 24" className="size-4 fill-current">
                <path d="M3.4 20.4 21.7 12 3.4 3.6l-.06 6.61L15 12 3.34 13.79z" />
              </svg>
            </button>
          )}
        </div>
        {/* 工具条：联网搜索开关（激活态为柔和紫蓝渐变）+ 附件上传 */}
        <div className="flex items-center gap-1.5 px-1">
          <button
            onClick={() => useChatStore.getState().toggleWebSearch()}
            title={webSearchEnabled ? '关闭联网搜索' : '开启联网搜索'}
            aria-pressed={webSearchEnabled}
            className={clsx(
              'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
              webSearchEnabled
                ? 'border-violet-300/60 bg-gradient-to-r from-violet-400/15 to-blue-400/15 text-violet-600 dark:border-violet-500/40 dark:from-violet-500/15 dark:to-blue-500/15 dark:text-violet-300'
                : 'border-neutral-300 text-neutral-500 hover:border-neutral-400 hover:text-neutral-600 dark:border-neutral-600 dark:text-neutral-400 dark:hover:border-neutral-500 dark:hover:text-neutral-300',
            )}
          >
            <svg viewBox="0 0 24 24" className="size-3.5 fill-none stroke-current" strokeWidth="1.8">
              <circle cx="12" cy="12" r="9" />
              <path d="M3 12h18M12 3c2.5 2.4 3.8 5.6 3.8 9S14.5 18.6 12 21c-2.5-2.4-3.8-5.6-3.8-9S9.5 5.4 12 3z" />
            </svg>
            联网搜索
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={files.length >= MAX_FILES}
            title={files.length >= MAX_FILES ? `最多上传 ${MAX_FILES} 个附件` : '上传附件（图片 / PDF / 文本 / 代码）'}
            className="flex items-center gap-1.5 rounded-full border border-neutral-300 px-2.5 py-1 text-xs text-neutral-500 transition-colors hover:border-neutral-400 hover:text-neutral-600 disabled:cursor-not-allowed disabled:opacity-40 dark:border-neutral-600 dark:text-neutral-400 dark:hover:border-neutral-500 dark:hover:text-neutral-300"
          >
            <svg viewBox="0 0 24 24" className="size-3.5 fill-none stroke-current" strokeWidth="1.8">
              <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57a4 4 0 1 1 5.66 5.66l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
            附件
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept={FILE_ACCEPT}
            multiple
            className="hidden"
            onChange={(e) => {
              addFiles(Array.from(e.target.files ?? []))
              e.target.value = ''
            }}
          />
          <button
            onClick={() => setPptDialogOpen(true)}
            title="制作 PPT"
            className="flex items-center gap-1.5 rounded-full border border-neutral-300 px-2.5 py-1 text-xs text-neutral-500 transition-colors hover:border-neutral-400 hover:text-neutral-600 dark:border-neutral-600 dark:text-neutral-400 dark:hover:border-neutral-500 dark:hover:text-neutral-300"
          >
            <svg viewBox="0 0 24 24" className="size-3.5 fill-none stroke-current" strokeWidth="1.8">
              <rect x="4" y="2" width="16" height="20" rx="2" />
              <path d="M8 7h8M8 11h8M8 15h4" />
            </svg>
            制作 PPT
          </button>
        </div>
      </div>
      <p className="mx-auto mt-1.5 max-w-3xl text-center text-xs text-neutral-400">
        内容由 AI 生成，请注意甄别
      </p>
      {pptDialogOpen && (
        <PptDialog
          initialReference={value}
          onClose={() => setPptDialogOpen(false)}
        />
      )}
    </div>
  )
}
