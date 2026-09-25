import { api } from './client'
import type { Schema } from './types'

export type Agent = Schema<'AgentOut'>
export type AgentVersion = Schema<'VersionOut'>
export type AgentChange = Schema<'ChangeOut'>
export type AgentLifecycleEvent = Schema<'LifecycleEventOut'>
export type AgentNumber = Schema<'PhoneNumberOut'>
export type VersionAction = 'submit' | 'evaluate' | 'approve' | 'reject' | 'activate' | 'rollback'

export const agentsApi = {
  list: () => api.get<Agent[]>('/api/agents'),
  get: (id: string) => api.get<Agent>(`/api/agents/${id}`),
  create: (agent: Schema<'AgentCreate'>) => api.post<Agent>('/api/agents', agent),
  update: (id: string, agent: Schema<'AgentUpdate'>) => api.put<Agent>(`/api/agents/${id}`, agent),
  delete: (id: string) => api.delete<{ status: string; success: boolean }>(`/api/agents/${id}`),
  versions: (id: string) => api.get<AgentVersion[]>(`/api/agents/${id}/versions`),
  changes: (id: string) => api.get<AgentChange[]>(`/api/agents/${id}/changes`),
  events: (id: string) => api.get<AgentLifecycleEvent[]>(`/api/agents/${id}/events`),
  compare: (id: string, from: number, to: number) => api.get<Schema<'VersionDiffOut'>>(`/api/agents/${id}/compare?from=${from}&to=${to}`),
  patchDraft: (id: string, patch: Record<string, unknown>, reason: string) =>
    api.patch<Schema<'DraftPatchOut'>>(`/api/agents/${id}/draft`, { patch, reason }),
  discardDraft: (id: string) => api.delete<void>(`/api/agents/${id}/draft`),
  versionAction: (id: string, number: number, action: VersionAction, note?: string) =>
    api.post<AgentVersion>(`/api/agents/${id}/versions/${number}/${action}`, { note }),
  disable: (id: string, note?: string) => api.post<Agent>(`/api/agents/${id}/disable`, { note }),
  numbers: (id: string) => api.get<AgentNumber[]>(`/api/agents/${id}/numbers`),
  addNumber: (id: string, phoneNumber: string) => api.post<AgentNumber>(`/api/agents/${id}/numbers`, { phone_number: phoneNumber }),
  removeNumber: (id: string, numberId: string) => api.delete<void>(`/api/agents/${id}/numbers/${numberId}`),
  enable: (id: string) => api.post<Agent>(`/api/agents/${id}/enable`),
}
