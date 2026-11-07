import { create } from 'zustand'

export type ConfirmationRiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface ConfirmationRequest {
  id: string
  action: string
  description: string
  risk_level: ConfirmationRiskLevel
  screenshot_base64?: string
  timestamp: number
}

interface ConfirmationStore {
  pending: ConfirmationRequest | null
  setPending: (request: ConfirmationRequest | null) => void
}

export const useConfirmationStore = create<ConfirmationStore>((set) => ({
  pending: null,
  setPending: (request) => set({ pending: request }),
}))
