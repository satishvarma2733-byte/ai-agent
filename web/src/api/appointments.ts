import { api } from './client'
import type {
  Appointment,
  CreateAppointmentPayload,
  UpdateAppointmentPayload,
} from '../types'

interface AppointmentResponse {
  status: string
  appointment: Appointment
}

export const appointmentsApi = {
  list: (start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const qs = params.toString()
    return api.get<Appointment[]>(`/api/appointments${qs ? `?${qs}` : ''}`)
  },
  create: (payload: CreateAppointmentPayload) =>
    api.post<AppointmentResponse>('/api/appointments', payload),
  update: (id: string, payload: UpdateAppointmentPayload) =>
    api.patch<AppointmentResponse>(`/api/appointments/${id}`, payload),
  cancel: (id: string, reason?: string) =>
    api.post<AppointmentResponse>(`/api/appointments/${id}/cancel`, {
      reason: reason ?? '',
    }),
}
