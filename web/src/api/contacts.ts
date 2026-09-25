import { api } from './client'
import type { Contact } from '../types'

export const contactsApi = {
  list: () => api.get<Contact[]>('/api/contacts'),
}
