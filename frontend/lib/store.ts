/**
 * Zustand store for cross-route UI state.
 *
 * The source panel slides in over the report viewer when the user clicks
 * a citation badge. Keeping it in a global store lets the click handler
 * live in any nested component while the panel stays mounted at the
 * page root.
 */

import { create } from 'zustand'

interface SourcePanelState {
  isOpen: boolean
  selectedSourceId: string | null
  openSource: (id: string) => void
  closeSource: () => void
}

export const useSourcePanel = create<SourcePanelState>((set) => ({
  isOpen: false,
  selectedSourceId: null,
  openSource: (id) => set({ isOpen: true, selectedSourceId: id }),
  closeSource: () => set({ isOpen: false, selectedSourceId: null }),
}))
