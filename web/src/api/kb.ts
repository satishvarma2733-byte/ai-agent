import { api } from './client'
import type {
  KbStatus,
  KbSource,
  KbJob,
  KbSearchResult,
} from '../types'

interface KbSourcesResponse {
  status: string
  items: KbSource[]
}
interface KbJobsResponse {
  status: string
  items: KbJob[]
}
interface KbSourceResponse {
  status: string
  source: KbSource
}
interface KbDeleteResponse {
  status: string
  deleted: boolean
}
interface KbJobResponse {
  status: string
  job: KbJob
}

export const kbApi = {
  status: () => api.get<KbStatus>('/api/kb/status'),
  sources: () => api.get<KbSourcesResponse>('/api/kb/sources'),
  createSource: (payload: {
    source_type: string
    title: string
    source_url?: string
    raw_text?: string
    enabled?: boolean
    metadata?: Record<string, unknown>
  }) => api.post<KbSourceResponse>('/api/kb/sources', payload),
  updateSource: (
    id: number | string,
    payload: Partial<KbSource>
  ) => api.patch<KbSourceResponse>(`/api/kb/sources/${id}`, payload),
  deleteSource: (id: number | string) =>
    api.delete<KbDeleteResponse>(`/api/kb/sources/${id}`),
  syncSource: (id: number | string) =>
    api.post<KbJobResponse>(`/api/kb/sources/${id}/sync`),
  upload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.upload<KbSourceResponse>('/api/kb/upload', fd)
  },
  jobs: () => api.get<KbJobsResponse>('/api/kb/jobs'),
  reindex: () => api.post<{ status: string; queued: number }>('/api/kb/reindex'),
  search: (query: string) =>
    api.post<KbSearchResult>('/api/kb/search', { query }),
}
