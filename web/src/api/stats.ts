import { api } from './client'
import type { Stats } from '../types'

export const statsApi = {
  get: () => api.get<Stats>('/api/stats'),
  // Returns { status: "ok", timestamp: ISO string, service: string }
  health: () => api.get<{ status: string; timestamp?: string; service?: string }>('/health'),
}
