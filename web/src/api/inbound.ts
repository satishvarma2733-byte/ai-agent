import { api } from './client'
import type { InboundCall } from '../types'
import type { Schema } from './types'
import { toCallRows } from './calls'

export const inboundApi = {
  async list(): Promise<InboundCall[]> {
    try {
      return await toCallRows(await api.get<Schema<'CallLogOut'>[]>('/api/inbound'))
    } catch {
      return []
    }
  },

  async start(data: { phone: string }): Promise<{ status: string }> {
    return api.post('/api/inbound/start', data)
  },

  async end(id: string): Promise<{ status: string }> {
    return api.post('/api/inbound/end', { id })
  },

  async transfer(id: string, to: string): Promise<{ status: string }> {
    return api.post('/api/inbound/transfer', { id, to })
  },

  async voicemail(id: string): Promise<{ status: string }> {
    return api.post('/api/inbound/voicemail', { id })
  },

  health(): Promise<{ status: string }> {
    return api.get('/health')
  },
}
