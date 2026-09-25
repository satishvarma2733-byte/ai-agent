import { api } from './client'
import type { Schema } from './types'
import type { AppNotification } from '../types'

type Inbox = Schema<'NotificationsOut'>

const TYPE_BY_KIND: Record<string, AppNotification['type']> = {
  call_missed: 'warning', workflow_failed: 'error', appointment_booked: 'success', lead_assigned: 'info',
}

export type InboxItem = AppNotification & { link?: string | null }

export const notificationsApi = {
  async list(): Promise<{ items: InboxItem[]; unread: number }> {
    const inbox = await api.get<Inbox>('/api/notifications')
    return {
      unread: inbox.unread,
      items: inbox.items.map(n => ({
        id: n.id, title: n.title, message: n.body ?? '', type: TYPE_BY_KIND[n.kind] ?? 'info',
        read: n.read, created_at: n.created_at, link: n.link,
      })),
    }
  },
  readAll: () => api.post<void>('/api/notifications/read-all'),
  clear: () => api.delete<void>('/api/notifications'),
}
