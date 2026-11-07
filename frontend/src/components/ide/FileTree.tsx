import clsx from 'clsx'
import { useIdeStore, type TreeNode } from '../../stores/ideStore'

interface FileTreeProps {
  onChangeWorkspace: () => void
}

interface TreeNodeRowProps {
  node: TreeNode
  activePath?: string
  depth?: number
}

function FolderIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 20 20" className="size-4 shrink-0 fill-current" aria-hidden>
      {open ? (
        <path d="M2.2 7.5h15.6a1 1 0 0 1 .95 1.32l-2.15 6.45A2.5 2.5 0 0 1 14.23 17H4.5A2.5 2.5 0 0 1 2 14.5v-7ZM2 6V5a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2H3a2 2 0 0 0-1 .27V6Z" />
      ) : (
        <path d="M2 5a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5Z" />
      )}
    </svg>
  )
}

function FileIcon() {
  return (
    <svg viewBox="0 0 20 20" className="size-4 shrink-0 fill-current" aria-hidden>
      <path d="M5 2a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.4a2 2 0 0 0-.59-1.41l-3.4-3.4A2 2 0 0 0 11.6 2H5Zm6 1.75c.26.06.5.2.7.4l3.15 3.15c.2.2.34.44.4.7H12a1 1 0 0 1-1-1V3.75Z" />
    </svg>
  )
}

function TreeNodeRow({ node, activePath, depth = 0 }: TreeNodeRowProps) {
  const isFolder = node.type === 'dir'
  const active = !isFolder && node.path === activePath

  const handleClick = () => {
    if (isFolder) void useIdeStore.getState().toggleTreeNode(node.path)
    else void useIdeStore.getState().openFile(node.path)
  }

  return (
    <div className={clsx(depth > 0 && 'pl-4')}>
      <button
        type="button"
        onClick={handleClick}
        title={node.path}
        aria-expanded={isFolder ? Boolean(node.expanded) : undefined}
        className={clsx(
          'group flex w-full min-w-0 items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-xs transition-colors',
          active
            ? 'bg-violet-100 font-medium text-violet-700 dark:bg-violet-500/20 dark:text-violet-300'
            : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-300 dark:hover:bg-neutral-800 dark:hover:text-neutral-100',
        )}
      >
        {isFolder ? (
          <>
            <svg
              viewBox="0 0 20 20"
              className={clsx('size-3 shrink-0 fill-current text-neutral-400 transition-transform duration-150', node.expanded && 'rotate-90')}
              aria-hidden
            >
              <path d="m7 4 6 6-6 6V4Z" />
            </svg>
            <span className="text-amber-500/90 dark:text-amber-400/80">
              <FolderIcon open={Boolean(node.expanded)} />
            </span>
          </>
        ) : (
          <>
            <span className="size-3 shrink-0" />
            <span className="text-neutral-400 dark:text-neutral-500">
              <FileIcon />
            </span>
          </>
        )}
        <span className="truncate">{node.name}</span>
      </button>

      {isFolder && node.expanded && (
        <div className="grid transition-all duration-150">
          {node.children?.length ? (
            node.children.map((child) => (
              <TreeNodeRow key={child.path} node={child} activePath={activePath} depth={depth + 1} />
            ))
          ) : (
            <p className="py-1 pl-10 text-[11px] text-neutral-400">空文件夹</p>
          )}
        </div>
      )}
    </div>
  )
}

export function FileTree({ onChangeWorkspace }: FileTreeProps) {
  const fileTree = useIdeStore((state) => state.fileTree)
  const fileTreeLoading = useIdeStore((state) => state.fileTreeLoading)
  const workspacePath = useIdeStore((state) => state.workspacePath)
  const openFiles = useIdeStore((state) => state.openFiles)
  const activeFileIndex = useIdeStore((state) => state.activeFileIndex)
  const activePath = activeFileIndex === null ? undefined : openFiles[activeFileIndex]?.path

  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900">
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-neutral-200 px-3 dark:border-neutral-800">
        <svg viewBox="0 0 20 20" className="size-4 shrink-0 fill-current text-violet-500" aria-hidden>
          <path d="M2 5a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5Z" />
        </svg>
        <span
          title={workspacePath ?? ''}
          className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-xs font-medium text-neutral-700 dark:text-neutral-200"
        >
          {workspacePath ?? '未选择工作区'}
        </span>
        <button
          type="button"
          onClick={onChangeWorkspace}
          className="shrink-0 rounded-md px-1.5 py-1 text-[11px] text-violet-500 transition-colors hover:bg-violet-50 hover:text-violet-700 dark:text-violet-300 dark:hover:bg-violet-500/10"
        >
          切换
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {fileTreeLoading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-xs text-neutral-400">
            <span className="size-3.5 animate-spin rounded-full border-2 border-neutral-300 border-t-violet-500 dark:border-neutral-700 dark:border-t-violet-400" />
            正在加载
          </div>
        ) : fileTree.length > 0 ? (
          fileTree.map((node) => <TreeNodeRow key={node.path} node={node} activePath={activePath} />)
        ) : (
          <p className="py-8 text-center text-xs text-neutral-400">工作区为空</p>
        )}
      </div>
    </aside>
  )
}
