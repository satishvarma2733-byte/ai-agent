import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Circle, ListTodo, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import { tasksApi, type Task } from '../../api/tasks'

// Open follow-ups for one lead, shown in the lead drawer.
export default function LeadTasks({ leadId }: { leadId: string }) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [title, setTitle] = useState('')
  const [due, setDue] = useState('')

  const load = useCallback(() => {
    tasksApi.list({ leadId, status: 'open' }).then(setTasks).catch(() => setTasks([]))
  }, [leadId])
  useEffect(load, [load])

  const add = async () => {
    if (!title.trim()) return
    try {
      await tasksApi.create({ title: title.trim(), due_date: due || null, lead_id: leadId })
      setTitle(''); setDue(''); load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Could not add the task') }
  }
  const done = async (t: Task) => {
    try { await tasksApi.update(t.id, { status: 'done' }); load() } catch (e) { toast.error(e instanceof Error ? e.message : 'Could not update') }
  }

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, color: 'var(--color-text-secondary)', marginBottom: 8 }}>
        <ListTodo size={13} /> Follow-ups
      </div>
      {tasks.map(t => (
        <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', fontSize: 12.5 }}>
          <button onClick={() => done(t)} aria-label={`Mark "${t.title}" done`} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--color-text-muted)' }}>
            <Circle size={15} />
          </button>
          <span style={{ flex: 1, color: 'var(--color-text-primary)' }}>{t.title}</span>
          {t.due_date && <span style={{ fontSize: 11, color: t.overdue ? 'var(--color-danger)' : 'var(--color-text-muted)' }}>{t.due_date}</span>}
        </div>
      ))}
      {tasks.length === 0 && <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}><CheckCircle2 size={13} /> No open follow-ups</div>}
      <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
        <input className="avn-input" aria-label="New follow-up" placeholder="Add a follow-up" value={title} maxLength={200}
          onChange={e => setTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void add() }} style={{ flex: 1, height: 32, fontSize: 12.5 }} />
        <input type="date" className="avn-input" aria-label="Due date" value={due} onChange={e => setDue(e.target.value)} style={{ height: 32, fontSize: 12 }} />
        <button className="avn-btn avn-btn-secondary" onClick={add} disabled={!title.trim()} aria-label="Add follow-up" style={{ height: 32, padding: '0 10px' }}><Plus size={13} /></button>
      </div>
    </div>
  )
}
