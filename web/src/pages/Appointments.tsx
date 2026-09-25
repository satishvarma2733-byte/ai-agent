import { useEffect, useState, useMemo } from 'react'
import { Plus, CalendarDays, Edit2, XCircle, Search, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react'
import toast from 'react-hot-toast'
import CalendarIntegrations from '../components/appointments/CalendarIntegrations'
import { format } from 'date-fns'
import PageHeader from '../components/layout/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Textarea from '../components/ui/Textarea'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { LoadingState, ErrorState, EmptyState } from '../components/ui/States'
import { appointmentsApi } from '../api/appointments'
import type { Appointment, AppointmentStatus, CreateAppointmentPayload } from '../types'

const STATUS_VARIANTS: Record<AppointmentStatus, 'success' | 'default' | 'warning'> = {
  scheduled: 'success',
  cancelled: 'default',
  completed: 'warning',
}

const SOURCE_VARIANTS: Record<string, 'violet' | 'info' | 'default'> = {
  voice_agent: 'violet',
  manual_ui: 'info',
  backend_api: 'default',
}

const SOURCE_LABELS: Record<string, string> = {
  voice_agent: 'Voice AI',
  manual_ui: 'Manual UI',
  backend_api: 'API',
}

const TZ_OPTIONS = [
  'UTC', 'Asia/Kolkata', 'America/New_York', 'America/Los_Angeles',
  'Europe/London', 'Europe/Paris', 'Asia/Tokyo', 'Australia/Sydney',
].map(v => ({ value: v, label: v }))

interface FormFieldsProps {
  form: CreateAppointmentPayload
  formErrors: Partial<Record<keyof CreateAppointmentPayload, string>>
  setForm: React.Dispatch<React.SetStateAction<CreateAppointmentPayload>>
}

function FormFields({ form, formErrors, setForm }: FormFieldsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '18px 20px' }}>
      <Input
        label="Title"
        id="apt-title"
        value={form.title}
        onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Input
          label="Contact Name"
          id="apt-name"
          value={form.contact_name}
          error={formErrors.contact_name}
          onChange={e => setForm(f => ({ ...f, contact_name: e.target.value }))}
        />
        <Input
          label="Contact Phone"
          id="apt-phone"
          value={form.contact_phone}
          error={formErrors.contact_phone}
          placeholder="+91…"
          onChange={e => setForm(f => ({ ...f, contact_phone: e.target.value }))}
        />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Input
          label="Start Time"
          id="apt-start"
          type="datetime-local"
          value={form.scheduled_start}
          error={formErrors.scheduled_start}
          onChange={e => setForm(f => ({ ...f, scheduled_start: e.target.value }))}
        />
        <Input
          label="End Time"
          id="apt-end"
          type="datetime-local"
          value={form.scheduled_end}
          error={formErrors.scheduled_end}
          onChange={e => setForm(f => ({ ...f, scheduled_end: e.target.value }))}
        />
      </div>
      <Select
        label="Timezone"
        id="apt-tz"
        value={form.timezone}
        options={TZ_OPTIONS}
        onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))}
      />
      <Select
        label="Status"
        id="apt-status"
        value={form.status}
        options={[
          { value: 'scheduled', label: 'Scheduled' },
          { value: 'completed', label: 'Completed' },
          { value: 'cancelled', label: 'Cancelled' },
        ]}
        onChange={e => setForm(f => ({ ...f, status: e.target.value as AppointmentStatus }))}
      />
      <Textarea
        label="Notes"
        id="apt-notes"
        value={form.notes ?? ''}
        rows={3}
        onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
      />
    </div>
  )
}

// <input type="datetime-local"> takes local wall-clock time, not UTC.
function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function browserTimezone(): string {
  let tz = ''
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone } catch { /* older browsers */ }
  return TZ_OPTIONS.some(o => o.value === tz) ? tz : 'Asia/Kolkata'
}

function initialForm(): CreateAppointmentPayload {
  const now = new Date()
  const start = new Date(now.getTime() + 60 * 60 * 1000)
  const end = new Date(start.getTime() + 30 * 60 * 1000)
  return {
    title: 'Appointment',
    contact_name: '',
    contact_phone: '',
    scheduled_start: toLocalInput(start),
    scheduled_end: toLocalInput(end),
    timezone: browserTimezone(),
    status: 'scheduled',
    notes: '',
  }
}

// ── Mini Calendar Widget ──────────────────────────────────────────
function MiniCalendar({ appointments }: { appointments: Appointment[] }) {
  const today = new Date()
  const [viewDate, setViewDate] = useState(new Date(today.getFullYear(), today.getMonth(), 1))

  const year = viewDate.getFullYear()
  const month = viewDate.getMonth()
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const apptDays = new Set(
    appointments
      .filter(a => {
        const d = new Date(a.scheduled_start)
        return d.getFullYear() === year && d.getMonth() === month
      })
      .map(a => new Date(a.scheduled_start).getDate())
  )

  const prevMonth = () => setViewDate(new Date(year, month - 1, 1))
  const nextMonth = () => setViewDate(new Date(year, month + 1, 1))

  const dayNames = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <button aria-label="Previous month" onClick={prevMonth} style={{ width: 26, height: 26, borderRadius: 7, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
          <ChevronLeft size={12} />
        </button>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-text-primary)' }}>
          {format(viewDate, 'MMMM yyyy')}
        </span>
        <button aria-label="Next month" onClick={nextMonth} style={{ width: 26, height: 26, borderRadius: 7, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
          <ChevronRight size={12} />
        </button>
      </div>

      {/* Day names */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, marginBottom: 4 }}>
        {dayNames.map(d => (
          <div key={d} style={{ fontSize: 9.5, fontWeight: 700, color: 'var(--color-text-muted)', textAlign: 'center', padding: '2px 0', letterSpacing: '0.04em' }}>{d}</div>
        ))}
      </div>

      {/* Days grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2 }}>
        {Array.from({ length: firstDay }, (_, i) => <div key={`e${i}`} />)}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const day = i + 1
          const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear()
          const hasAppt = apptDays.has(day)
          return (
            <div key={day} style={{
              height: 28, borderRadius: 7, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', fontSize: 11.5,
              fontWeight: isToday ? 700 : 400, cursor: hasAppt ? 'pointer' : 'default',
              background: isToday ? 'linear-gradient(135deg, #7B61FF, #5EE6FF)' : hasAppt ? 'rgba(34,211,165,0.1)' : 'transparent',
              border: isToday ? 'none' : hasAppt ? '1px solid rgba(34,211,165,0.25)' : '1px solid transparent',
              color: isToday ? '#fff' : hasAppt ? '#22D3A5' : '#94A3B8',
              boxShadow: isToday ? '0 0 10px rgba(123,97,255,0.4)' : 'none',
              transition: 'all 0.15s',
              position: 'relative',
            }}>
              {day}
              {hasAppt && !isToday && (
                <div style={{ position: 'absolute', bottom: 2, width: 4, height: 4, borderRadius: '50%', background: '#22D3A5' }} />
              )}
            </div>
          )
        })}
      </div>

      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--color-text-muted)' }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#22D3A5' }} />
        {appointments.filter(a => {
          const d = new Date(a.scheduled_start)
          return d.getFullYear() === year && d.getMonth() === month
        }).length} appointments this month
      </div>
    </Card>
  )
}

export default function Appointments() {
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Search & Filter States
  const [search, setSearch] = useState('')
  const [dateFilter, setDateFilter] = useState<'all' | 'today' | 'upcoming' | 'past'>('all')
  const [sortBy, setSortBy] = useState<'start_asc' | 'start_desc'>('start_asc')

  // Modal open states
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Appointment | null>(null)
  const [cancelTarget, setCancelTarget] = useState<Appointment | null>(null)
  const [cancelReason, setCancelReason] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [form, setForm] = useState<CreateAppointmentPayload>(initialForm())
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof CreateAppointmentPayload, string>>>({})

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await appointmentsApi.list()
      setAppointments(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load appointments')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function openCreate() {
    setForm(initialForm())
    setFormErrors({})
    setCreateOpen(true)
  }

  function openEdit(apt: Appointment) {
    setForm({
      title: apt.title,
      contact_name: apt.contact_name,
      contact_phone: apt.contact_phone,
      scheduled_start: toLocalInput(new Date(apt.scheduled_start)),
      scheduled_end: toLocalInput(new Date(apt.scheduled_end)),
      timezone: apt.timezone,
      status: apt.status,
      notes: apt.notes ?? '',
    })
    setFormErrors({})
    setEditTarget(apt)
  }

  function validate(): boolean {
    const errs: typeof formErrors = {}
    if (!form.contact_name.trim()) errs.contact_name = 'Name is required'
    if (!form.contact_phone.trim()) errs.contact_phone = 'Phone is required'
    if (!form.scheduled_start) errs.scheduled_start = 'Start time is required'
    if (!form.scheduled_end) errs.scheduled_end = 'End time is required'
    if (form.scheduled_start && form.scheduled_end && form.scheduled_end <= form.scheduled_start) {
      errs.scheduled_end = 'End must be after start'
    }
    setFormErrors(errs)
    return Object.keys(errs).length === 0
  }

  async function handleCreate() {
    if (!validate()) return
    setSubmitting(true)
    try {
      const payload = {
        ...form,
        scheduled_start: new Date(form.scheduled_start).toISOString(),
        scheduled_end: new Date(form.scheduled_end).toISOString(),
      }
      const res = await appointmentsApi.create(payload)
      setAppointments(prev => [res.appointment, ...prev])
      setCreateOpen(false)
      toast.success('Appointment created')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create appointment'
      if (msg.includes('409') || msg.toLowerCase().includes('conflict')) {
        toast.error('Scheduling conflict — this slot overlaps with an existing appointment')
      } else {
        toast.error(msg)
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleEdit() {
    if (!editTarget || !validate()) return
    setSubmitting(true)
    try {
      const payload = {
        ...form,
        scheduled_start: new Date(form.scheduled_start).toISOString(),
        scheduled_end: new Date(form.scheduled_end).toISOString(),
      }
      const res = await appointmentsApi.update(editTarget.id, payload)
      setAppointments(prev => prev.map(a => a.id === editTarget.id ? res.appointment : a))
      setEditTarget(null)
      toast.success('Appointment updated')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to update')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCancel() {
    if (!cancelTarget) return
    setSubmitting(true)
    try {
      const res = await appointmentsApi.cancel(cancelTarget.id, cancelReason)
      setAppointments(prev => prev.map(a => a.id === cancelTarget.id ? res.appointment : a))
      setCancelTarget(null)
      setCancelReason('')
      toast.success('Appointment cancelled')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to cancel')
    } finally {
      setSubmitting(false)
    }
  }

  // Memoized filtered and sorted lists
  const processedAppointments = useMemo(() => {
    let result = [...appointments]

    // 1. Search Filter
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(a =>
        a.contact_name.toLowerCase().includes(q) ||
        a.contact_phone.includes(q) ||
        (a.notes && a.notes.toLowerCase().includes(q)) ||
        a.title.toLowerCase().includes(q)
      )
    }

    // 2. Date Filter
    const todayStr = format(new Date(), 'yyyy-MM-dd')
    const now = new Date().getTime()
    if (dateFilter === 'today') {
      result = result.filter(a => format(new Date(a.scheduled_start), 'yyyy-MM-dd') === todayStr)
    } else if (dateFilter === 'upcoming') {
      result = result.filter(a => new Date(a.scheduled_start).getTime() >= now)
    } else if (dateFilter === 'past') {
      result = result.filter(a => new Date(a.scheduled_end).getTime() < now)
    }

    // 3. Sorting
    result.sort((a, b) => {
      const timeA = new Date(a.scheduled_start).getTime()
      const timeB = new Date(b.scheduled_start).getTime()
      return sortBy === 'start_asc' ? timeA - timeB : timeB - timeA
    })

    return result
  }, [appointments, search, dateFilter, sortBy])

  const grouped = useMemo(() => {
    const scheduled = processedAppointments.filter(a => a.status === 'scheduled')
    const other = processedAppointments.filter(a => a.status !== 'scheduled')
    return { scheduled, other }
  }, [processedAppointments])

  function AptRow({ apt }: { apt: Appointment }) {
    const sourceLabel = SOURCE_LABELS[apt.source || 'manual_ui']
    const sourceVariant = SOURCE_VARIANTS[apt.source || 'manual_ui']
    
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '14px 20px',
          borderBottom: '1px solid #131625',
          transition: 'background 0.1s',
        }}
        onMouseOver={e => (e.currentTarget.style.background = '#181c2e')}
        onMouseOut={e => (e.currentTarget.style.background = '')}
      >
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            background: 'rgba(123,97,255,0.06)',
            border: '1px solid rgba(123,97,255,0.15)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 10, color: '#7c6fcd', fontWeight: 700, lineHeight: 1 }}>
            {format(new Date(apt.scheduled_start), 'MMM').toUpperCase()}
          </span>
          <span style={{ fontSize: 14, color: '#e8ecf0', fontWeight: 700, lineHeight: 1.2, marginTop: 1 }}>
            {format(new Date(apt.scheduled_start), 'd')}
          </span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#e8ecf0' }}>{apt.contact_name}</span>
            <Badge variant={sourceVariant} style={{ fontSize: 10, padding: '2px 6px', height: 18 }}>{sourceLabel}</Badge>
          </div>
          <div style={{ fontSize: 12, color: '#8891a8', marginTop: 3 }}>
            {apt.contact_phone} · {format(new Date(apt.scheduled_start), 'h:mm a')} – {format(new Date(apt.scheduled_end), 'h:mm a')} ({apt.timezone})
          </div>
          {apt.notes && (
            <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 460 }}>
              {apt.notes}
            </div>
          )}
        </div>
        <Badge variant={STATUS_VARIANTS[apt.status]} dot>{apt.status}</Badge>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <Button variant="ghost" size="sm" icon={<Edit2 size={13} />} onClick={() => openEdit(apt)}>Edit</Button>
          {apt.status === 'scheduled' && (
            <Button variant="danger" size="sm" icon={<XCircle size={13} />} onClick={() => { setCancelTarget(apt); setCancelReason('') }}>
              Cancel
            </Button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="animate-fade-in" style={{ padding: '0 0 40px' }}>
      <PageHeader
        title="Appointments"
        subtitle={`${appointments.length} total appointments configured`}
        actions={
          <Button variant="primary" icon={<Plus size={15} />} onClick={openCreate}>
            New Appointment
          </Button>
        }
      />

      <div style={{ padding: '24px 32px', display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'start' }}>
        {/* Left column: List & Search Filters */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          
          {/* Filters Bar */}
          <Card padding={12}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
                <Search size={14} color="#555e78" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search contact, phone or notes…"
                  style={{
                    width: '100%',
                    padding: '7px 12px 7px 32px',
                    background: 'var(--color-bg-card)',
                    border: '1px solid #2a2f47',
                    borderRadius: 8,
                    color: '#e8ecf0',
                    fontSize: 13,
                    outline: 'none',
                  }}
                />
              </div>

              {/* Date Filter Dropdown */}
              <select aria-label="Filter by date"
                value={dateFilter}
                onChange={e => setDateFilter(e.target.value as any)}
                style={{
                  padding: '7px 12px',
                  background: 'var(--color-bg-card)',
                  border: '1px solid #2a2f47',
                  borderRadius: 8,
                  color: '#e8ecf0',
                  fontSize: 13,
                  outline: 'none',
                }}
              >
                <option value="all">Date: All</option>
                <option value="today">Today</option>
                <option value="upcoming">Upcoming</option>
                <option value="past">Past</option>
              </select>

              {/* Sort Dropdown */}
              <button
                onClick={() => setSortBy(s => s === 'start_asc' ? 'start_desc' : 'start_asc')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '7px 12px',
                  background: 'var(--color-bg-card)',
                  border: '1px solid #2a2f47',
                  borderRadius: 8,
                  color: 'var(--color-text-secondary)',
                  fontSize: 13,
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                <ArrowUpDown size={13} />
                Sort: {sortBy === 'start_asc' ? 'Date Asc' : 'Date Desc'}
              </button>
            </div>
          </Card>

          {loading ? (
            <LoadingState />
          ) : error ? (
            <ErrorState message={error} onRetry={load} />
          ) : processedAppointments.length === 0 ? (
            <Card>
              <EmptyState
                icon={<CalendarDays size={36} />}
                title="No appointments match filters"
                description="Try clearing search queries or altering date range filters."
                action={<Button variant="primary" icon={<Plus size={14} />} onClick={openCreate}>New Appointment</Button>}
              />
            </Card>
          ) : (
            <>
              {grouped.scheduled.length > 0 && (
                <Card padding={0}>
                  <div style={{ padding: '14px 20px', borderBottom: '1px solid #1e2236' }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#e8ecf0' }}>
                      Scheduled ({grouped.scheduled.length})
                    </span>
                  </div>
                  {grouped.scheduled.map(apt => <AptRow key={apt.id} apt={apt} />)}
                </Card>
              )}
              {grouped.other.length > 0 && (
                <Card padding={0}>
                  <div style={{ padding: '14px 20px', borderBottom: '1px solid #1e2236' }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#8891a8' }}>
                      Past &amp; Cancelled ({grouped.other.length})
                    </span>
                  </div>
                  {grouped.other.map(apt => <AptRow key={apt.id} apt={apt} />)}
                </Card>
              )}
            </>
          )}
        </div>

        {/* Right column: Calendar + Integrations */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <CalendarIntegrations onChanged={load} />

          {/* Mini Calendar */}
          <MiniCalendar appointments={appointments} />
        </div>
      </div>

      {/* Create Modal */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New Appointment" width={540}>
        <FormFields form={form} formErrors={formErrors} setForm={setForm} />
        <div style={{ padding: '12px 20px 20px', display: 'flex', gap: 8, justifyContent: 'flex-end', borderTop: '1px solid #1e2236' }}>
          <Button variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={submitting} onClick={handleCreate}>Create Appointment</Button>
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal open={!!editTarget} onClose={() => setEditTarget(null)} title="Edit Appointment" width={540}>
        <FormFields form={form} formErrors={formErrors} setForm={setForm} />
        <div style={{ padding: '12px 20px 20px', display: 'flex', gap: 8, justifyContent: 'flex-end', borderTop: '1px solid #1e2236' }}>
          <Button variant="ghost" onClick={() => setEditTarget(null)}>Cancel</Button>
          <Button variant="primary" loading={submitting} onClick={handleEdit}>Save Changes</Button>
        </div>
      </Modal>

      {/* Cancel Confirm Replaced with Reusable ConfirmDialog */}
      <ConfirmDialog
        open={cancelTarget !== null}
        title="Cancel Appointment"
        message={
          cancelTarget ? (
            <div>
              Cancel appointment for <strong style={{ color: '#e8ecf0' }}>{cancelTarget.contact_name}</strong>?
              <div style={{ marginTop: 14 }}>
                <Textarea
                  label="Reason (optional)"
                  id="cancel-reason"
                  value={cancelReason}
                  rows={2}
                  onChange={e => setCancelReason(e.target.value)}
                />
              </div>
            </div>
          ) : ''
        }
        confirmLabel="Confirm Cancel"
        cancelLabel="Keep Appointment"
        destructive
        loading={submitting}
        onConfirm={handleCancel}
        onCancel={() => setCancelTarget(null)}
      />
    </div>
  )
}
