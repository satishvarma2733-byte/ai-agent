import { api } from './client'
import type { Lead, LeadActivity, Workflow } from '../types'
import type { Schema } from './types'

export type ImportResult = { created: number; skipped: { row: number; reason: string }[]; skipped_count: number }
export type WorkflowRun = Schema<'WorkflowLogOut'> & { workflow_name?: string }

export const crmApi = {
  listLeads: () => api.get<Lead[]>('/api/crm/leads'),
  createLead: (lead: Partial<Lead>) => api.post<Lead>('/api/crm/leads', lead),
  updateLead: (id: string, lead: Partial<Lead>) => api.put<Lead>(`/api/crm/leads/${id}`, lead),
  importLeads: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload<ImportResult>('/api/crm/leads/import', form)
  },
  deleteLead: (id: string) => api.delete<{ status: string; success: boolean }>(`/api/crm/leads/${id}`),
  getTimeline: (leadId: string) => api.get<LeadActivity[]>(`/api/crm/leads/${leadId}/timeline`),
  addTimeline: (leadId: string, activity: Partial<LeadActivity>) =>
    api.post<{ status: string; activity: LeadActivity }>(`/api/crm/leads/${leadId}/timeline`, activity),
  scoreLead: (leadId: string, leadData: Partial<Lead>) =>
    api.post<{ status: string; score: string; explanation: string }>(`/api/crm/leads/${leadId}/score`, leadData),
  listWorkflows: () => api.get<Workflow[]>('/api/crm/workflows'),
  createWorkflow: (wf: Partial<Workflow>) => api.post<{ status: string; workflow: Workflow }>('/api/crm/workflows', wf),
  updateWorkflow: (id: string, wf: Partial<Workflow>) => api.put<{ status: string; workflow: Workflow }>(`/api/crm/workflows/${id}`, wf),
  listRuns: (id: string) => api.get<WorkflowRun[]>(`/api/crm/workflows/${id}/runs`),
  deleteWorkflow: (id: string) => api.delete<{ status: string; success: boolean }>(`/api/crm/workflows/${id}`),
}
