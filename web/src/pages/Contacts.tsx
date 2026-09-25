import { useEffect, useState, useMemo } from 'react'
import { Users, Phone, Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import PageHeader from '../components/layout/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { LoadingState, ErrorState, EmptyState } from '../components/ui/States'
import { contactsApi } from '../api/contacts'
import type { Contact } from '../types'
import { format } from 'date-fns'

export default function Contacts() {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await contactsApi.list()
      setContacts(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load contacts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return contacts.filter(c =>
      !q ||
      c.caller_name?.toLowerCase().includes(q) ||
      c.phone_number?.includes(q)
    )
  }, [contacts, search])

  return (
    <div className="animate-fade-in" style={{ padding: '0 0 40px' }}>
      <PageHeader
        title="Contacts"
        subtitle={`${contacts.length} contacts derived from call history`}
      />

      <div style={{ padding: '24px 32px' }}>
        <Card padding={0}>
          {/* Toolbar */}
          <div style={{ padding: '14px 16px', borderBottom: '1px solid #1e2236', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: '0 0 280px' }}>
              <Search size={14} color="#555e78" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search name or phone…"
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
            <span style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginLeft: 'auto' }}>
              {filtered.length} contact{filtered.length !== 1 ? 's' : ''}
            </span>
          </div>

          {loading ? (
            <LoadingState />
          ) : error ? (
            <ErrorState message={error} onRetry={load} />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<Users size={36} />}
              title="No contacts yet"
              description="Contacts are created automatically from call history."
            />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr>
                    {['Name', 'Phone', 'Calls', 'Appointments', 'Last Seen', 'Status', ''].map(h => (
                      <th
                        key={h}
                        style={{
                          textAlign: 'left',
                          padding: '10px 14px',
                          fontSize: 11.5,
                          fontWeight: 600,
                          color: 'var(--color-text-muted)',
                          letterSpacing: '0.06em',
                          textTransform: 'uppercase',
                          whiteSpace: 'nowrap',
                          background: 'var(--color-bg-card)',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((c, i) => (
                    <tr
                      key={i}
                      style={{ borderBottom: '1px solid #131625', transition: 'background 0.1s' }}
                      onMouseOver={e => (e.currentTarget.style.background = '#181c2e')}
                      onMouseOut={e => (e.currentTarget.style.background = '')}
                    >
                      <td style={{ padding: '11px 14px', color: '#e8ecf0', fontWeight: 500 }}>
                        {c.caller_name || '—'}
                      </td>
                      <td style={{ padding: '11px 14px', color: '#8891a8', fontSize: 12.5 }}>
                        {c.phone_number}
                      </td>
                      <td style={{ padding: '11px 14px', textAlign: 'center' }}>
                        <Badge variant="default">{c.total_calls}</Badge>
                      </td>
                      <td style={{ padding: '11px 14px', textAlign: 'center' }}>
                        <Badge variant={c.appointment_count > 0 ? 'info' : 'default'}>
                          {c.appointment_count}
                        </Badge>
                      </td>
                      <td style={{ padding: '11px 14px', color: '#8891a8', fontSize: 12.5, whiteSpace: 'nowrap' }}>
                        {c.last_seen ? format(new Date(c.last_seen), 'MMM d, yyyy') : '—'}
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        <Badge variant={c.is_booked ? 'success' : 'default'} dot>
                          {c.is_booked ? 'Booked' : 'Not booked'}
                        </Badge>
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={<Phone size={13} />}
                          onClick={() => navigate(`/outbound?phone=${encodeURIComponent(c.phone_number)}&name=${encodeURIComponent(c.caller_name ?? '')}`)}
                        >
                          Call
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
