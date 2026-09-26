import { api } from './client'
import type { Schema } from './types'

export type SmsStatus = Schema<'SmsStatusOut'>

export const smsApi = {
  status: () => api.get<SmsStatus>('/api/integrations/sms'),
  connect: (body: Schema<'SmsConnectIn'>) => api.put<SmsStatus>('/api/integrations/sms', body),
  disconnect: () => api.delete<void>('/api/integrations/sms'),
  send: (body: Schema<'SmsSendIn'>) => api.post<Schema<'SmsSentOut'>>('/api/crm/sms', body),
}
