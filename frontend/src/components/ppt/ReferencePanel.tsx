// PPT 参考资料面板：按钮/拖拽上传参考文件（文本类本地读取内容供预览）、文件列表选中/删除、参考文本输入
import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { uploadsApi } from '../../api/client'
import { useChatStore } from '../../stores/chatStore'
import { usePptStore, type PptRefFile } from '../../stores/pptStore'
import { toast } from '../../stores/toastStore'

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 单文件 10MB（与后端一致）

// 可本地读取为文本并用 Monaco 预览的扩展名
const TEXT_EXTENSIONS = [
  '.md', '.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.yaml', '.yml',
  '.xml', '.sql', '.csv', '.log', '.sh', '.html', '.css',
]

// 上传放行列表（与后端 /api/uploads 白名单一致）
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
const isTextFile = (f: File) => f.type.startsWith('text/') || TEXT_EXTENSIONS.includes(extOf(f.name))

const readAsText = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '')
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })

// 上传中的占位项（记录发起时的会话，仅在该会话下展示）
interface UploadingFile {
  localId: string
  fileName: string
  sessionId: string | null
}

let uploadSeq = 1

function FileIcon({ isImage, className }: { isImage: boolean; className?: string }) {
  return isImage ? (
    <svg viewBox="0 0 24 24" className={clsx('fill-none stroke-current', className)} strokeWidth="1.6">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="m21 16-5-5-8 9" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" className={clsx('fill-none stroke-current', className)} strokeWidth="1.6">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  )
}

function ReferenceRow({ file, active }: { file: PptRefFile; active: boolean }) {
  const isImage = file.mimeType.startsWith('image/')
  return (
    <div
      className={clsx(
        'group relative flex items-center rounded-xl transition-colors',
        active
          ? 'bg-violet-50 dark:bg-violet-500/15'
          : 'hover:bg-neutral-100 dark:hover:bg-neutral-800',
      )}
    >
      {active && (
        <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-gradient-to-b from-violet-500 to-blue-500" />
      )}
      <button
        type="button"
        onClick={() => usePptStore.getState().selectFile(file.id)}
        title={file.fileName}
        className={clsx(
          'flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left text-sm',
          active
            ? 'font-medium text-violet-700 dark:text-violet-300'
            : 'text-neutral-700 dark:text-neutral-300',
        )}
      >
        <FileIcon
          isImage={isImage}
          className={clsx(
            'size-4 shrink-0',
            active ? 'text-violet-500 dark:text-violet-400' : 'text-neutral-400',
          )}
        />
        <span className="min-w-0 flex-1 truncate">{file.fileName}</span>
        <span className="shrink-0 text-[10px] text-neutral-400 uppercase group-hover:hidden">
          {extOf(file.fileName).slice(1) || (isImage ? '图片' : '文件')}
        </span>
      </button>
      <button
        type="button"
        onClick={() => usePptStore.getState().removeFile(file.id)}
        title="移除"
        className="mr-1 hidden shrink-0 rounded-md p-1 text-neutral-400 transition-colors group-hover:block hover:bg-red-100 hover:text-red-500 dark:hover:bg-red-950"
      >
        <svg viewBox="0 0 20 20" className="size-3.5 fill-current">
          <path d="M7 3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1h3a1 1 0 1 1 0 2h-1l-.8 11.1A2 2 0 0 1 12.2 18H7.8a2 2 0 0 1-2-1.9L5 5H4a1 1 0 0 1 0-2h3zm2 4a1 1 0 0 1 2 0v7a1 1 0 1 1-2 0V7z" />
        </svg>
      </button>
    </div>
  )
}

export function ReferencePanel() {
  const referenceFiles = usePptStore((state) => state.referenceFiles)
  const selectedFileId = usePptStore((state) => state.selectedFileId)
  const referenceText = usePptStore((state) => state.referenceText)
  const [uploading, setUploading] = useState<UploadingFile[]>([])
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragDepthRef = useRef(0)
  const currentId = useChatStore((state) => state.currentId)
  const currentIdRef = useRef(currentId)
  currentIdRef.current = currentId
  // 组件卸载后标记为 stale，丢弃仍在途的上传回调
  const staleRef = useRef(false)

  useEffect(() => {
    staleRef.current = false
    return () => {
      staleRef.current = true
    }
  }, [])

  const uploadOne = async (file: File) => {
    const localId = `ref-${uploadSeq++}`
    const sessionId = currentIdRef.current
    setUploading((list) => [...list, { localId, fileName: file.name, sessionId }])
    try {
      const [res, content] = await Promise.all([
        uploadsApi.upload(file),
        isTextFile(file) ? readAsText(file).catch(() => undefined) : Promise.resolve(undefined),
      ])
      // 会话已切换（pptStore 已 reset）或组件已卸载：丢弃结果，避免写入其他会话
      if (staleRef.current || useChatStore.getState().currentId !== sessionId) {
        if (!staleRef.current) toast.info(`「${file.name}」上传完成时会话已切换，已丢弃`)
        return
      }
      usePptStore.getState().addFile({
        id: res.id,
        fileName: res.fileName,
        url: res.url,
        mimeType: res.mimeType,
        content,
      })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `「${file.name}」上传失败`)
    } finally {
      setUploading((list) => list.filter((item) => item.localId !== localId))
    }
  }

  const addFiles = (candidates: File[]) => {
    const rejected = candidates.filter((file) => !isAcceptedFile(file))
    if (rejected.length) toast.error(`不支持的文件类型：${rejected.map((f) => f.name).join('、')}`)
    for (const file of candidates.filter(isAcceptedFile)) {
      if (file.size > MAX_FILE_SIZE) {
        toast.error(`「${file.name}」超过 10MB，已跳过`)
        continue
      }
      void uploadOne(file)
    }
  }

  const visibleUploading = uploading.filter((item) => item.sessionId === currentId)
  const hasFiles = referenceFiles.length > 0 || visibleUploading.length > 0

  return (
    <section
      onDragEnter={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        dragDepthRef.current += 1
        setDragging(true)
      }}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'copy'
      }}
      onDragLeave={() => {
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
        if (dragDepthRef.current === 0) setDragging(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        dragDepthRef.current = 0
        setDragging(false)
        addFiles(Array.from(e.dataTransfer.files ?? []))
      }}
      className="relative flex h-full min-h-0 flex-col border-r border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900"
    >
      {/* 标题栏 */}
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-neutral-200 px-3 dark:border-neutral-800">
        <span className="text-xs font-semibold tracking-wide text-neutral-600 dark:text-neutral-300">参考资料</span>
        {referenceFiles.length > 0 && (
          <span className="rounded-full bg-violet-50 px-1.5 py-0.5 text-[10px] leading-none text-violet-500 dark:bg-violet-500/15 dark:text-violet-300">
            {referenceFiles.length}
          </span>
        )}
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          title="添加参考文件（图片 / PDF / 文本 / 代码）"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-violet-600 transition-colors hover:bg-violet-50 dark:text-violet-300 dark:hover:bg-violet-500/10"
        >
          <svg viewBox="0 0 20 20" className="size-3.5 fill-current">
            <path d="M10 3a1 1 0 0 1 1 1v5h5a1 1 0 1 1 0 2h-5v5a1 1 0 1 1-2 0v-5H4a1 1 0 1 1 0-2h5V4a1 1 0 0 1 1-1z" />
          </svg>
          添加
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
      </header>

      {/* 文件列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {hasFiles ? (
          <div className="flex flex-col gap-0.5">
            {referenceFiles.map((file) => (
              <ReferenceRow key={file.id} file={file} active={file.id === selectedFileId} />
            ))}
            {visibleUploading.map((item) => (
              <div
                key={item.localId}
                className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-neutral-400"
              >
                <span className="size-4 shrink-0 animate-spin rounded-full border-2 border-violet-200 border-t-violet-500 dark:border-violet-500/30 dark:border-t-violet-400" />
                <span className="min-w-0 flex-1 truncate">{item.fileName}</span>
                <span className="shrink-0 text-[10px]">上传中</span>
              </div>
            ))}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="group/empty flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-neutral-300 px-3 py-8 text-center transition-colors hover:border-violet-400 hover:bg-violet-50/50 dark:border-neutral-700 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/5"
          >
            <span className="flex size-9 items-center justify-center rounded-xl bg-white text-neutral-400 shadow-sm transition-colors group-hover/empty:text-violet-500 dark:bg-neutral-800">
              <svg viewBox="0 0 24 24" className="size-4.5 fill-none stroke-current" strokeWidth="1.8">
                <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
              </svg>
            </span>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">点击或拖拽文件到此处</span>
            <span className="text-[11px] leading-4 text-neutral-400">支持图片、PDF、文本与代码，单个不超过 10MB</span>
          </button>
        )}
      </div>

      {/* 参考文本 */}
      <div className="flex shrink-0 flex-col gap-1.5 border-t border-neutral-200 p-3 dark:border-neutral-800">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium tracking-wide text-neutral-400 uppercase">参考文本</span>
          {referenceText && (
            <span className="text-[10px] text-neutral-400">{referenceText.length} 字</span>
          )}
        </div>
        <textarea
          value={referenceText}
          onChange={(e) => usePptStore.getState().setReferenceText(e.target.value)}
          placeholder="粘贴或输入参考材料..."
          rows={6}
          className="w-full resize-none rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm leading-5 text-neutral-800 outline-none transition-colors placeholder:text-neutral-400 focus:border-violet-400 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200 dark:focus:border-violet-500"
        />
      </div>

      {/* 拖拽上传遮罩 */}
      {dragging && (
        <div className="pointer-events-none absolute inset-2 z-10 flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-violet-400 bg-violet-50/90 text-violet-600 backdrop-blur-sm dark:border-violet-500 dark:bg-violet-950/80 dark:text-violet-300">
          <svg viewBox="0 0 24 24" className="size-7 fill-none stroke-current" strokeWidth="1.8">
            <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
          </svg>
          <span className="text-sm font-medium">松开以添加参考文件</span>
        </div>
      )}
    </section>
  )
}
