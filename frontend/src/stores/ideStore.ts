import { create } from 'zustand'
import { workspaceApi, type FileContent, type FileEntry } from '../api/client'

export interface TreeNode {
  name: string
  path: string
  type: 'file' | 'dir'
  size?: number
  children?: TreeNode[]
  expanded?: boolean
}

export interface DiffFile {
  path: string
  oldContent: string
  newContent: string
}

export interface OpenFile {
  path: string
  name: string
  content: string
  language: string
  isDirty: boolean
  originalContent: string
}

interface IdeState {
  workspacePath: string | null
  fileTree: TreeNode[]
  openFiles: OpenFile[]
  activeFileIndex: number | null
  diffFile: DiffFile | null
  terminalLines: string[]
  fileTreeLoading: boolean
  fileLoading: boolean

  setWorkspace: (path: string) => Promise<void>
  refreshFileTree: () => Promise<void>
  loadTreeNode: (dirPath: string) => Promise<void>
  toggleTreeNode: (nodePath: string) => Promise<void>
  openFile: (path: string) => Promise<void>
  closeFile: (index: number) => void
  setActiveFile: (index: number) => void
  showDiff: (diff: DiffFile) => void
  closeDiff: () => void
  saveFile: (index: number) => Promise<void>
  updateFileContent: (index: number, content: string) => void
  appendTerminalOutput: (lines: string[]) => void
  clearTerminal: () => void
  reset: () => void
}

const MAX_OPEN_FILES = 10
const MAX_TERMINAL_LINES = 1000

function entriesToNodes(entries: FileEntry[], parentPath: string): TreeNode[] {
  return entries.map((entry) => ({
    name: entry.name,
    path:
      parentPath.endsWith('/') || parentPath.endsWith('\\')
        ? parentPath + entry.name
        : parentPath + '/' + entry.name,
    type: entry.type,
    size: entry.size,
    children: undefined,
    expanded: false,
  }))
}

function updateNodeInTree(
  nodes: TreeNode[],
  targetPath: string,
  updater: (node: TreeNode) => TreeNode,
): TreeNode[] {
  return nodes.map((node) => {
    if (node.path === targetPath) return updater(node)
    if (node.children) {
      return { ...node, children: updateNodeInTree(node.children, targetPath, updater) }
    }
    return node
  })
}

function preserveLoadedRootState(nodes: TreeNode[], currentNodes: TreeNode[]): TreeNode[] {
  return nodes.map((node) => {
    if (node.type !== 'dir') return node
    const currentNode = currentNodes.find(
      (candidate) => candidate.type === 'dir' && candidate.path === node.path,
    )
    return currentNode
      ? { ...node, children: currentNode.children, expanded: currentNode.expanded }
      : node
  })
}

export const useIdeStore = create<IdeState>((set, get) => ({
  workspacePath: null,
  fileTree: [],
  openFiles: [],
  activeFileIndex: null,
  diffFile: null,
  terminalLines: [],
  fileTreeLoading: false,
  fileLoading: false,

  setWorkspace: async (path) => {
    set({
      workspacePath: path,
      fileTree: [],
      openFiles: [],
      activeFileIndex: null,
      diffFile: null,
      fileTreeLoading: true,
    })
    await get().refreshFileTree()
  },

  refreshFileTree: async () => {
    const workspacePath = get().workspacePath
    if (!workspacePath) return

    set({ fileTreeLoading: true })
    try {
      const entries = await workspaceApi.tree(workspacePath)
      if (get().workspacePath !== workspacePath) return
      set((state) => ({
        fileTree: preserveLoadedRootState(
          entriesToNodes(entries, workspacePath),
          state.fileTree,
        ),
        fileTreeLoading: false,
      }))
    } catch {
      if (get().workspacePath === workspacePath) set({ fileTreeLoading: false })
    }
  },

  loadTreeNode: async (dirPath) => {
    try {
      const entries = await workspaceApi.tree(dirPath)
      const children = entriesToNodes(entries, dirPath)
      set((state) => ({
        fileTree: updateNodeInTree(state.fileTree, dirPath, (node) => ({
          ...node,
          children,
          expanded: true,
        })),
      }))
    } catch {
      // Ignore workspace tree loading failures until the UI adds error feedback.
    }
  },

  toggleTreeNode: async (nodePath) => {
    const { fileTree, loadTreeNode } = get()
    const findNode = (nodes: TreeNode[]): TreeNode | undefined => {
      for (const node of nodes) {
        if (node.path === nodePath) return node
        if (node.children) {
          const found = findNode(node.children)
          if (found) return found
        }
      }
      return undefined
    }
    const node = findNode(fileTree)
    if (!node) return

    if (node.expanded) {
      set((state) => ({
        fileTree: updateNodeInTree(state.fileTree, nodePath, (currentNode) => ({
          ...currentNode,
          expanded: false,
        })),
      }))
    } else {
      await loadTreeNode(nodePath)
    }
  },

  openFile: async (path) => {
    const { openFiles } = get()
    const existingIndex = openFiles.findIndex((file) => file.path === path)
    if (existingIndex >= 0) {
      set({ activeFileIndex: existingIndex, diffFile: null })
      return
    }

    const files = [...openFiles]
    if (files.length >= MAX_OPEN_FILES) {
      const cleanIndex = files.findIndex((file) => !file.isDirty)
      if (cleanIndex >= 0) files.splice(cleanIndex, 1)
      else files.shift()
    }

    set({ fileLoading: true })
    try {
      const data: FileContent = await workspaceApi.readFile(path)
      const name = path.split(/[\\/]/).pop() || path
      const newFile: OpenFile = {
        path,
        name,
        content: data.content,
        language: data.language,
        isDirty: false,
        originalContent: data.content,
      }
      files.push(newFile)
      set({
        openFiles: files,
        activeFileIndex: files.length - 1,
        diffFile: null,
        fileLoading: false,
      })
    } catch {
      set({ fileLoading: false })
    }
  },

  closeFile: (index) => {
    set((state) => {
      const files = state.openFiles.filter((_, fileIndex) => fileIndex !== index)
      let activeIndex = state.activeFileIndex
      if (activeIndex !== null) {
        if (index === activeIndex) {
          activeIndex = files.length > 0 ? Math.min(index, files.length - 1) : null
        } else if (index < activeIndex) {
          activeIndex -= 1
        }
      }
      return { openFiles: files, activeFileIndex: activeIndex }
    })
  },

  setActiveFile: (index) => set({ activeFileIndex: index, diffFile: null }),

  showDiff: (diff) => set({ diffFile: diff }),

  closeDiff: () => set({ diffFile: null }),

  saveFile: async (index) => {
    const file = get().openFiles[index]
    if (!file) return
    try {
      await workspaceApi.saveFile(file.path, file.content)
      set((state) => ({
        openFiles: state.openFiles.map((openFile, fileIndex) =>
          fileIndex === index
            ? { ...openFile, isDirty: false, originalContent: openFile.content }
            : openFile,
        ),
      }))
    } catch {
      // The IDE UI will surface save errors in a later phase.
    }
  },

  updateFileContent: (index, content) => {
    set((state) => ({
      openFiles: state.openFiles.map((file, fileIndex) =>
        fileIndex === index
          ? { ...file, content, isDirty: content !== file.originalContent }
          : file,
      ),
    }))
  },

  appendTerminalOutput: (lines) => {
    set((state) => {
      const newLines = [...state.terminalLines, ...lines]
      return { terminalLines: newLines.slice(-MAX_TERMINAL_LINES) }
    })
  },

  clearTerminal: () => set({ terminalLines: [] }),

  reset: () =>
    set({
      workspacePath: null,
      fileTree: [],
      openFiles: [],
      activeFileIndex: null,
      diffFile: null,
      terminalLines: [],
      fileTreeLoading: false,
      fileLoading: false,
    }),
}))
