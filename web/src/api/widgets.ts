import { api } from './client'
import type { Schema } from './types'

export type Widget = Schema<'WidgetOut'>
export type WidgetInput = Schema<'WidgetIn'>
export type ApiKey = Schema<'ApiKeyOut'>
export type ChatConversation = Schema<'ChatSessionOut'>

export const widgetsApi = {
  list: () => api.get<Widget[]>('/api/widgets'),
  create: (body: WidgetInput) => api.post<Widget>('/api/widgets', body),
  update: (id: string, body: Schema<'WidgetPatch'>) => api.patch<Widget>(`/api/widgets/${id}`, body),
  rotateKey: (id: string) => api.post<Widget>(`/api/widgets/${id}/rotate-key`),
  remove: (id: string) => api.delete<void>(`/api/widgets/${id}`),
  apiKeys: () => api.get<ApiKey[]>('/api/api-keys'),
  createApiKey: (name: string) => api.post<Schema<'ApiKeyCreatedOut'>>('/api/api-keys', { name }),
  revokeApiKey: (id: string) => api.delete<void>(`/api/api-keys/${id}`),
  conversations: (limit = 50) => api.get<ChatConversation[]>(`/api/chat-sessions?limit=${limit}`),
}
