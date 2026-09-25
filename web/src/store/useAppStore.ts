import { create } from 'zustand'
import type { AppNotification } from '../types'

type Environment = 'LIVE' | 'STAGING' | 'DEV'

interface AppState {
  sidebarCollapsed: boolean
  environment: Environment
  notifications: AppNotification[]
  unreadCount: number

  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  setEnvironment: (env: Environment) => void
  addNotification: (n: Omit<AppNotification, 'id' | 'created_at' | 'read'>) => void
  setNotifications: (items: AppNotification[], unread: number) => void
  markAllRead: () => void
  clearNotifications: () => void
}

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  environment: 'LIVE',
  notifications: [],
  unreadCount: 0,

  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setEnvironment: (environment) => set({ environment }),

  addNotification: (n) => {
    const notification: AppNotification = {
      ...n,
      id: Math.random().toString(36).slice(2),
      created_at: new Date().toISOString(),
      read: false,
    }
    set((s) => ({
      notifications: [notification, ...s.notifications].slice(0, 20),
      unreadCount: s.unreadCount + 1,
    }))
  },

  setNotifications: (items, unread) => set({ notifications: items, unreadCount: unread }),

  markAllRead: () =>
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),

  clearNotifications: () => set({ notifications: [], unreadCount: 0 }),
}))

// Selector hooks
export const useSidebarCollapsed = () => useAppStore((s) => s.sidebarCollapsed)
export const useEnvironment = () => useAppStore((s) => s.environment)
export const useNotifications = () => useAppStore((s) => s.notifications)
export const useUnreadCount = () => useAppStore((s) => s.unreadCount)
