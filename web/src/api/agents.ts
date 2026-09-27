import { api } from './client'
import type { Schema } from './types'

export type Agent = Schema<'AgentOut'>
export type AgentVersion = Schema<'VersionOut'>
export type AgentChange = Schema<'ChangeOut'>
export type AgentLifecycleEvent = Schema<'LifecycleEventOut'>
export type AgentNumber = Schema<'PhoneNumberOut'>
export type AgentTestCase = Schema<'TestCaseOut'>
export type AgentTestRun = Schema<'TestRunOut'>
export type TestTurn = { role: 'caller' | 'agent'; text: string }
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
  // Agent Studio
  testChat: (id: string, number: number, turns: TestTurn[]) =>
    api.post<{ reply: string }>(`/api/agents/${id}/versions/${number}/test/chat`, { turns }),
  testCases: (id: string) => api.get<AgentTestCase[]>(`/api/agents/${id}/tests`),
  addTestCase: (id: string, body: Schema<'TestCaseIn'>) => api.post<AgentTestCase>(`/api/agents/${id}/tests`, body),
  deleteTestCase: (id: string, caseId: string) => api.delete<void>(`/api/agents/${id}/tests/${caseId}`),
  runTests: (id: string, number: number) => api.post<AgentTestRun>(`/api/agents/${id}/versions/${number}/test/run`),
  testRuns: (id: string, number: number) => api.get<AgentTestRun[]>(`/api/agents/${id}/versions/${number}/test/runs`),
  copilot: (id: string, request: string) => api.post<Schema<'CopilotProposalOut'>>(`/api/agents/${id}/copilot`, { request }),
  copilotApply: (id: string, request: string, patch: Record<string, unknown>) =>
    api.post<Schema<'DraftPatchOut'>>(`/api/agents/${id}/copilot/apply`, { request, patch }),
  voiceTest: (id: string, number: number) =>
    api.post<{ url: string; token: string; room: string; version: number }>(`/api/agents/${id}/versions/${number}/test/voice`),
}
