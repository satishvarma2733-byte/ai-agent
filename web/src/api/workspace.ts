import { api } from './client'
import type { Schema } from './types'

export type Workspace = Schema<'WorkspaceOut'>
export type SignedInSession = Schema<'SessionOut'>
export type CallSummarySettings = Schema<'CallSummarySettingsOut'>
export type CallSummarySettingsInput = Schema<'CallSummarySettingsIO'>

export const workspaceApi = {
  get: () => api.get<Workspace>('/api/workspace'),
  rename: (name: string) => api.patch<Workspace>('/api/workspace', { name }),
  sessions: () => api.get<SignedInSession[]>('/api/auth/sessions'),
  endSession: (id: string) => api.delete<void>(`/api/auth/sessions/${id}`),
  callSummaries: () => api.get<CallSummarySettings>('/api/workspace/call-summaries'),
  saveCallSummaries: (body: CallSummarySettingsInput) => api.put<CallSummarySettings>('/api/workspace/call-summaries', body),
  testCallSummary: () => api.post<Schema<'CallSummaryTestOut'>>('/api/workspace/call-summaries/test'),
}
