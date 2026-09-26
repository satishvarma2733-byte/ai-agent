import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Circle, ListTodo, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import { LoadingState } from '../components/ui/States'
import { tasksApi, type Task } from '../api/tasks'
import { teamApi } from '../api/team'

type Member = { id: string; name?: string | null; email: string; status?: string }

// Tasks: to-dos for the team, optionally about a lead. Assigning one to someone notifies them.
export default function Tasks() {
  const [mine, setMine] = useState(true)
  const [status, setStatus] = useState<'open' | 'done'>('open')
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [form, setForm] = useState({ title: '', due_date: '', assigned_user_id: '' })
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    tasksApi.list({ mine, status }).then(setTasks).catch(e => { setTasks([]); toast.error(e instanceof Error ? e.message : 'Could not load tasks') })
  }, [mine, status])
  useEffect(load, [load])
  useEffect(() => { teamApi.members().then(m => setMembers((m as Member[]).filter(x => x.status !== 'inactive'))).catch(() => setMembers([])) }, [])

  const add = async () => {
    setSaving(true)
    try {
      await tasksApi.create({ title: form.title.trim(), due_date: form.due_date || null, assigned_user_id: form.assigned_user_id || null })
      setForm({ title: '', due_date: '', assigned_user_id: '' })
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not add the task')
    } finally {
      setSaving(false)
    }
  }
  const toggle = async (t: Task) => {
    try { await tasksApi.update(t.id, { status: t.status === 'open' ? 'done' : 'open' }); load() } catch (e) { toast.error(e instanceof Error ? e.message : 'Could not update') }
  }
  const remove = async (t: Task) => {
    if (!confirm(`Delete "${t.title}"?`)) return
    try { await tasksApi.remove(t.id); load() } catch (e) { toast.error(e instanceof Error ? e.message : 'Could not delete') }
  }

  const pill = (active: boolean) => ({
    padding: '5px 12px', borderRadius: 7, border: 'none', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
    background: active ? 'rgba(123,97,255,0.2)' : 'transparent', color: active ? '#9580FF' : 'var(--color-text-muted)',
  } as const)

  return (
    <div className="page-wrapper">
      <div style={{ padding: '28px 32px 0', marginBottom: 20 }}>
        <div style={{ background: 'linear-gradient(135deg, rgba(123,97,255,0.08), rgba(34,211,165,0.04))', border: '1px solid rgba(123,97,255,0.14)',
          borderRadius: 18, padding: '22px 28px' }}>
          <div style={{ fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--color-text-primary)', marginBottom: 6 }}>Tasks</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Follow-ups and to-dos for the team. Mention someone in a lead note with @name to get their attention.</div>
        </div>
      </div>
      <div style={{ padding: '0 32px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Card>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ flex: '2 1 240px' }}>
              <label htmlFor="task-title" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>New task</label>
              <input id="task-title" className="avn-input" value={form.title} maxLength={200} placeholder="e.g. Send the price list to Asha"
                onChange={e => setForm(f => ({ ...f, title: e.target.value }))} onKeyDown={e => { if (e.key === 'Enter' && form.title.trim()) void add() }}
                style={{ width: '100%', height: 34 }} />
            </div>
            <div>
              <label htmlFor="task-due" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>Due</label>
              <input id="task-due" type="date" className="avn-input" value={form.due_date} onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} style={{ height: 34 }} />
            </div>
            <div>
              <label htmlFor="task-assignee" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>For</label>
              <select id="task-assignee" className="avn-input" value={form.assigned_user_id} onChange={e => setForm(f => ({ ...f, assigned_user_id: e.target.value }))} style={{ height: 34 }}>
                <option value="">Me</option>
                {members.map(m => <option key={m.id} value={m.id}>{m.name || m.email}</option>)}
              </select>
            </div>
            <Button variant="primary" icon={<Plus size={13} />} loading={saving} disabled={!form.title.trim()} onClick={add}>Add</Button>
          </div>
        </Card>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div role="group" aria-label="Whose tasks" style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.04)', padding: 4, borderRadius: 10 }}>
            <button style={pill(mine)} aria-pressed={mine} onClick={() => setMine(true)}>Mine</button>
            <button style={pill(!mine)} aria-pressed={!mine} onClick={() => setMine(false)}>Everyone</button>
          </div>
          <div role="group" aria-label="Task status" style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.04)', padding: 4, borderRadius: 10 }}>
            <button style={pill(status === 'open')} aria-pressed={status === 'open'} onClick={() => setStatus('open')}>Open</button>
            <button style={pill(status === 'done')} aria-pressed={status === 'done'} onClick={() => setStatus('done')}>Done</button>
          </div>
        </div>
        <Card padding={0}>
          {tasks === null ? <LoadingState /> : tasks.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 16px', color: 'var(--color-text-muted)', fontSize: 13 }}>
              <ListTodo size={26} style={{ margin: '0 auto 10px', display: 'block' }} />{status === 'open' ? 'Nothing to do. Nice.' : 'No finished tasks yet.'}
            </div>
          ) : tasks.map(t => (
            <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 18px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <button onClick={() => toggle(t)} aria-label={t.status === 'open' ? `Mark "${t.title}" done` : `Reopen "${t.title}"`}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.status === 'done' ? '#22D3A5' : 'var(--color-text-muted)', padding: 0 }}>
                {t.status === 'done' ? <CheckCircle2 size={18} /> : <Circle size={18} />}
              </button>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, color: 'var(--color-text-primary)', textDecoration: t.status === 'done' ? 'line-through' : 'none' }}>{t.title}</div>
                <div style={{ fontSize: 11.5, color: t.overdue ? 'var(--color-danger)' : 'var(--color-text-muted)' }}>
                  {[t.due_date ? `${t.overdue ? 'Overdue · ' : 'Due '}${t.due_date}` : null, t.lead_name ? `Lead: ${t.lead_name}` : null, !mine && t.assigned_name ? `For ${t.assigned_name}` : null]
                    .filter(Boolean).join(' · ') || 'No due date'}
                </div>
              </div>
              <button onClick={() => remove(t)} aria-label={`Delete "${t.title}"`} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><Trash2 size={14} /></button>
            </div>
          ))}
        </Card>
      </div>
    </div>
  )
}
