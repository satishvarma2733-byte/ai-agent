import { api } from './client'
import type { AgentConfig } from '../types'

export const configApi = {
  get: () => api.get<AgentConfig>('/api/config'),
  save: (data: Partial<AgentConfig>) =>
    api.post<{ status: string; config: AgentConfig }>('/api/config', data),
}
