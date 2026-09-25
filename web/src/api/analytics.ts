import { api } from './client'
import type { Schema } from './types'

export type Overview = Schema<'OverviewOut'>
export type DayPoint = Schema<'DayPoint'>
export type Period = '7d' | '30d' | '90d'

export const PERIOD_DAYS: Record<Period, number> = { '7d': 7, '30d': 30, '90d': 90 }

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

export const analyticsApi = {
  /** Workspace metrics computed on the server from real call, lead and appointment records. */
  overview: (days = 14) =>
    api.get<Overview>(`/api/stats/overview?days=${days}&tz=${encodeURIComponent(browserTimezone())}`),
}
