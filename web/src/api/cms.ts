import { api } from './client'
import type { CMSPage, CMSPrompt, CMSFaq } from '../types'

function graceful<T>(promise: Promise<T>, fallback: T): Promise<T> {
  return promise.catch(() => fallback)
}

export const cmsApi = {
  pages: {
    list: () => graceful(api.get<CMSPage[]>('/api/cms/pages'), []),
    create: (data: Partial<CMSPage>) => api.post<{ status: string; page: CMSPage }>('/api/cms/pages', data),
    update: (id: string, data: Partial<CMSPage>) => api.patch<{ status: string; page: CMSPage }>(`/api/cms/pages/${id}`, data),
    delete: (id: string) => api.delete<{ status: string }>(`/api/cms/pages/${id}`),
  },

  prompts: {
    list: () => graceful(api.get<CMSPrompt[]>('/api/cms/agent-prompts'), []),
    create: (data: Partial<CMSPrompt>) => api.post<{ status: string; prompt: CMSPrompt }>('/api/cms/agent-prompts', data),
    update: (id: string, data: Partial<CMSPrompt>) => api.patch<{ status: string; prompt: CMSPrompt }>(`/api/cms/agent-prompts/${id}`, data),
  },

  faqs: {
    list: () => graceful(api.get<CMSFaq[]>('/api/cms/faqs'), []),
    create: (data: Partial<CMSFaq>) => api.post<{ status: string; faq: CMSFaq }>('/api/cms/faqs', data),
    update: (id: string, data: Partial<CMSFaq>) => api.patch<{ status: string; faq: CMSFaq }>(`/api/cms/faqs/${id}`, data),
    delete: (id: string) => api.delete<{ status: string }>(`/api/cms/faqs/${id}`),
  },

  media: {
    list: () => graceful(api.get<{ id: string; filename: string; url: string; mime_type: string; size_bytes: number; created_at: string }[]>('/api/cms/media'), []),
    upload: (form: FormData) => api.upload<{ status: string }>('/api/cms/media/upload', form),
  },
}
