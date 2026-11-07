import { create } from 'zustand'

export interface PptRefFile {
  id: string // 上传后的服务端 ID
  fileName: string
  url: string // 服务端返回的文件 URL
  mimeType: string
  content?: string // 文本类文件的内容（用于预览）
}

interface PptState {
  referenceFiles: PptRefFile[]
  selectedFileId: string | null
  referenceText: string

  addFile: (file: PptRefFile) => void
  removeFile: (id: string) => void
  selectFile: (id: string | null) => void
  setReferenceText: (text: string) => void
  reset: () => void
}

export const usePptStore = create<PptState>((set) => ({
  referenceFiles: [],
  selectedFileId: null,
  referenceText: '',

  addFile: (file) =>
    set((state) => ({
      referenceFiles: [...state.referenceFiles.filter((item) => item.id !== file.id), file],
    })),

  removeFile: (id) =>
    set((state) => ({
      referenceFiles: state.referenceFiles.filter((file) => file.id !== id),
      selectedFileId: state.selectedFileId === id ? null : state.selectedFileId,
    })),

  selectFile: (id) => set({ selectedFileId: id }),

  setReferenceText: (text) => set({ referenceText: text }),

  reset: () =>
    set({
      referenceFiles: [],
      selectedFileId: null,
      referenceText: '',
    }),
}))
