import { api } from './client'
import type { Schema } from './types'

export type Task = Schema<'TaskOut'>

export const tasksApi = {
  list: (params: { mine?: boolean; status?: 'open' | 'done' | 'all'; leadId?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.mine) q.set('mine', 'true')
    if (params.status) q.set('status', params.status)
    if (params.leadId) q.set('lead_id', params.leadId)
    return api.get<Task[]>(`/api/tasks?${q.toString()}`)
  },
  create: (body: Schema<'TaskIn'>) => api.post<Task>('/api/tasks', body),
  update: (id: string, body: Schema<'TaskPatch'>) => api.patch<Task>(`/api/tasks/${id}`, body),
  remove: (id: string) => api.delete<void>(`/api/tasks/${id}`),
}
