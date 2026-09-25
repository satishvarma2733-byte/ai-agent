import { api } from './client'
import type { Schema } from './types'

export type LeadField = Schema<'LeadFieldOut'>
export type LeadFieldType = Schema<'LeadFieldIn'>['field_type']

export const leadFieldsApi = {
  list: () => api.get<LeadField[]>('/api/crm/fields'),
  create: (body: Schema<'LeadFieldIn'>) => api.post<LeadField>('/api/crm/fields', body),
  update: (id: string, body: Schema<'LeadFieldUpdate'>) => api.patch<LeadField>(`/api/crm/fields/${id}`, body),
  remove: (id: string) => api.delete<void>(`/api/crm/fields/${id}`),
}
