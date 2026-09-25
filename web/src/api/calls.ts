import { api } from './client'
import type { SingleCallResult, BulkCallResult, InboundCall } from '../types'
import type { Schema } from './types'

export type LiveCalls = Schema<'LiveCallsOut'>
export type LiveCall = Schema<'LiveCallOut'>

type CallLogRow = Schema<'CallLogOut'>

/** Call-log rows for the inbound/outbound pages. A call is live only while LiveKit reports its room open. */
export async function toCallRows(logs: CallLogRow[]): Promise<InboundCall[]> {
  let liveRooms = new Set<string>()
  try {
    liveRooms = new Set((await api.get<LiveCalls>('/api/calls/live')).calls.map(c => c.room))
  } catch {
    // Live status unavailable (e.g. LiveKit not configured): show the history only.
  }
  return logs.map(log => ({
    id: log.id,
    phone_number: log.phone_number,
    caller_name: log.caller_name,
    status: log.call_room_id && liveRooms.has(log.call_room_id) ? 'live' : 'completed',
    started_at: log.created_at,
    duration_seconds: log.duration_seconds,
    sentiment: log.sentiment,
    room_id: log.call_room_id ?? undefined,
    agent_id: log.agent_id ?? undefined,
    recording_url: log.recording_url ?? undefined,
    summary: log.summary,
  }))
}

export const callsApi = {
  health: () => api.get<{ status: string }>('/health'),
  single: (phone: string, callerName?: string) =>
    api.post<SingleCallResult>('/api/call/single', {
      phone,
      caller_name: callerName ?? '',
    }),
  bulk: (numbers: string[]) =>
    api.post<BulkCallResult>('/api/call/bulk', { numbers }),
  bulkText: (phoneNumbers: string) =>
    api.post<BulkCallResult>('/api/call/bulk', { phone_numbers: phoneNumbers }),
  async list(): Promise<InboundCall[]> {
    try {
      return await toCallRows(await api.get<CallLogRow[]>('/api/outbound'))
    } catch {
      return []
    }
  },
  /** Calls whose LiveKit room is open right now. */
  live: () => api.get<LiveCalls>('/api/calls/live'),
  async end(id: string): Promise<{ status: string }> {
    return api.post('/api/outbound/end', { id })
  },
  async transfer(id: string, to: string): Promise<{ status: string }> {
    return api.post('/api/outbound/transfer', { id, to })
  },
  async voicemail(id: string): Promise<{ status: string }> {
    return api.post('/api/outbound/voicemail', { id })
  },
}
