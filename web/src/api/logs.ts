import { api } from './client'
import type { CallLog } from '../types'

export const logsApi = {
  list: () => api.get<CallLog[]>('/api/logs'),
  transcript: (logId: string | number) =>
    api.get<string>(`/api/logs/${String(logId)}/transcript`),
}
