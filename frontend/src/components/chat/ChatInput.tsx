// 输入框：自适应高度，Enter 发送 / Shift+Enter 换行，流式中变为停止按钮；
// 支持图片上传（按钮选择/粘贴），缩略图预览后随消息发送
import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { uploadsApi } from '../../api/client'
import type { Attachment } from '../../api/types'
import { useChatStore } from '../../stores/chatStore'
import { toast } from '../../stores/toastStore'

const MAX_IMAGES = 4

// 待发送图片：先本地预览，上传成功后携带服务端 attachment
interface PendingImage {
  localId: string
  fileName: string
  previewUrl: string
  status: 'uploading' | 'done'
  attachment?: Attachment
}

let imageSeq = 1

export function ChatInput() {
  const [value, setValue] = useState('')
  const [images, setImages] = useState<PendingImage[]>([])
  const streaming = useChatStore((s) => s.streaming)
  const webSearchEnabled = useChatStore((s) => s.webSearchEnabled)
  const pendingInput = useChatStore((s) => s.pendingInput)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 卸载时释放所有 objectURL
  const imagesRef = useRef(images)
  imagesRef.current = images
  useEffect(
    () => () => imagesRef.current.forEach((img) => URL.revokeObjectURL(img.previewUrl)),
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

  const removeImage = (localId: string) => {
    setImages((list) => {
      const target = list.find((img) => img.localId === localId)
      if (target) URL.revokeObjectURL(target.previewUrl)
      return list.filter((img) => img.localId !== localId)
    })
  }

  // 选中/粘贴后立即上传；失败 toast 并移除预览
  const addFiles = (files: File[]) => {
    const imageFiles = files.filter((f) => f.type.startsWith('image/'))
    if (!imageFiles.length) return
    const room = MAX_IMAGES - imagesRef.current.length
    if (room <= 0) {
      toast.error(`最多上传 ${MAX_IMAGES} 张图片`)
      return
    }
    if (imageFiles.length > room) toast.error(`最多上传 ${MAX_IMAGES} 张图片`)
    for (const file of imageFiles.slice(0, room)) {
      const localId = `img-${imageSeq++}`
      const previewUrl = URL.createObjectURL(file)
      setImages((list) => [
        ...list,
        { localId, fileName: file.name, previewUrl, status: 'uploading' },
      ])
      uploadsApi
        .upload(file)
        .then((res) => {
          setImages((list) =>
            list.map((img) =>
              img.localId === localId
                ? {
                    ...img,
                    status: 'done',
                    attachment: {
                      id: res.id,
                      url: res.url,
                      fileName: res.fileName,
                      mimeType: res.mimeType,
                    },
                  }
                : img,
            ),
          )
        })
        .catch((err) => {
          toast.error(err instanceof Error ? err.message : '图片上传失败')
          removeImage(localId)
        })
    }
  }

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData?.files ?? [])
    if (files.some((f) => f.type.startsWith('image/'))) {
      e.preventDefault()
      addFiles(files)
    }
  }

  const uploading = images.some((img) => img.status === 'uploading')
  const attachments = images
    .filter((img) => img.status === 'done' && img.attachment)
    .map((img) => img.attachment!)
  const canSend = !streaming && (!!value.trim() || attachments.length > 0)

  const handleSend = () => {
    const content = value.trim()
    if (streaming || (!content && !attachments.length)) return
    if (uploading) {
      toast.error('图片上传中，请稍候')
      return
    }
    setValue('')
    images.forEach((img) => URL.revokeObjectURL(img.previewUrl))
    setImages([])
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
        {/* 图片预览条 */}
        {images.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1 pt-1">
            {images.map((img) => (
              <div
                key={img.localId}
                className="group/thumb relative size-16 overflow-hidden rounded-xl border border-neutral-200 dark:border-neutral-600"
              >
                <img
                  src={img.previewUrl}
                  alt={img.fileName}
                  className="size-full object-cover"
                />
                {img.status === 'uploading' && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <span className="size-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  </div>
                )}
                <button
                  onClick={() => removeImage(img.localId)}
                  title="移除图片"
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
        {/* 工具条：联网搜索开关（激活态为柔和紫蓝渐变）+ 图片上传 */}
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
            disabled={images.length >= MAX_IMAGES}
            title={images.length >= MAX_IMAGES ? `最多上传 ${MAX_IMAGES} 张图片` : '上传图片'}
            className="flex items-center gap-1.5 rounded-full border border-neutral-300 px-2.5 py-1 text-xs text-neutral-500 transition-colors hover:border-neutral-400 hover:text-neutral-600 disabled:cursor-not-allowed disabled:opacity-40 dark:border-neutral-600 dark:text-neutral-400 dark:hover:border-neutral-500 dark:hover:text-neutral-300"
          >
            <svg viewBox="0 0 24 24" className="size-3.5 fill-none stroke-current" strokeWidth="1.8">
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <circle cx="8.5" cy="10" r="1.5" />
              <path d="m21 15-4.5-4.5L9 18M3 17l4-4 3 3" />
            </svg>
            图片
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              addFiles(Array.from(e.target.files ?? []))
              e.target.value = ''
            }}
          />
        </div>
      </div>
      <p className="mx-auto mt-1.5 max-w-3xl text-center text-xs text-neutral-400">
        内容由 AI 生成，请注意甄别
      </p>
    </div>
  )
}
