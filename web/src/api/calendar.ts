import { api } from './client'
import type { Schema } from './types'

export type CalendarStatus = Schema<'CalendarStatusOut'>
export type CalendarProvider = 'google' | 'zoho'

export const calendarApi = {
  status: () => api.get<CalendarStatus[]>('/api/integrations/calendar'),
  /** The provider's sign-in page; it returns to /appointments?calendar=…&result=… when done. */
  connect: (provider: CalendarProvider) => api.post<Schema<'ConnectOut'>>(`/api/integrations/calendar/${provider}/connect`),
  sync: (provider: CalendarProvider) => api.post<Schema<'SyncOut'>>(`/api/integrations/calendar/${provider}/sync`),
  disconnect: (provider: CalendarProvider) => api.delete<void>(`/api/integrations/calendar/${provider}`),
}
