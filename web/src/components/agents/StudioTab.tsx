import { useCallback, useEffect, useRef, useState } from 'react'
import type { Room } from 'livekit-client'
import { Mic, MicOff, Play, Send, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import Button from '../ui/Button'
import { agentsApi, type Agent, type AgentTestCase, type AgentTestRun, type AgentVersion, type TestTurn } from '../../api/agents'

type TestLanguage = 'en' | 'te' | 'hi' | 'ta' | 'kn' | 'ml'
// Languages a test can require: the ones the reply's script identifies.
const LANGUAGE_NAMES: Record<TestLanguage, string> = { en: 'English', te: 'Telugu', hi: 'Hindi', ta: 'Tamil', kn: 'Kannada', ml: 'Malayalam' }

const field = { width: '100%', padding: '7px 10px', fontSize: 12.5 } as const
const label = { fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 } as const
const lines = (text: string) => text.split(/\n/).map(t => t.trim()).filter(Boolean)

// Agent Studio: try a version by text or voice, and keep a set of test cases it must pass before evaluation.
export default function StudioTab({ agent, versions, canBuild }: { agent: Agent; versions: AgentVersion[]; canBuild: boolean }) {
  const preferred = versions.find(v => v.status === 'testing') ?? versions.find(v => v.status === 'draft')
    ?? versions.find(v => v.status === 'production') ?? versions[0]
  const [number, setNumber] = useState<number>(preferred?.number ?? 1)
  const [turns, setTurns] = useState<TestTurn[]>([])
  const [message, setMessage] = useState('')
  const [thinking, setThinking] = useState(false)
  const [cases, setCases] = useState<AgentTestCase[]>([])
  const [run, setRun] = useState<AgentTestRun | null>(null)
  const [running, setRunning] = useState(false)
  const [draft, setDraft] = useState({ name: '', caller: '', must: '', mustNot: '', language: '' as '' | TestLanguage })
  const [voice, setVoice] = useState<'off' | 'connecting' | 'on'>('off')
  const roomRef = useRef<Room | null>(null)
  const audioRef = useRef<HTMLElement[]>([])

  const loadCases = useCallback(() => { agentsApi.testCases(agent.id).then(setCases).catch(() => setCases([])) }, [agent.id])
  useEffect(loadCases, [loadCases])
  useEffect(() => {
    agentsApi.testRuns(agent.id, number).then(r => setRun(r[0] ?? null)).catch(() => setRun(null))
  }, [agent.id, number])

  const stopVoice = useCallback(async () => {
    audioRef.current.forEach(el => el.remove())
    audioRef.current = []
    const room = roomRef.current
    roomRef.current = null
    setVoice('off')
    if (room) await room.disconnect()
  }, [])
  useEffect(() => () => { void stopVoice() }, [stopVoice])

  const send = async () => {
    const text = message.trim()
    if (!text) return
    const next: TestTurn[] = [...turns, { role: 'caller', text }]
    setTurns(next)
    setMessage('')
    setThinking(true)
    try {
      const { reply } = await agentsApi.testChat(agent.id, number, next)
      setTurns([...next, { role: 'agent', text: reply }])
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'The agent did not answer')
      setTurns(turns)
    } finally {
      setThinking(false)
    }
  }

  const startVoice = async () => {
    setVoice('connecting')
    try {
      const grant = await agentsApi.voiceTest(agent.id, number)
      const { Room: LiveKitRoom, RoomEvent, Track } = await import('livekit-client')
      const room = new LiveKitRoom()
      room.on(RoomEvent.TrackSubscribed, track => {
        if (track.kind !== Track.Kind.Audio) return
        const el = track.attach()
        el.style.display = 'none'
        document.body.appendChild(el)
        audioRef.current.push(el)
      })
      room.on(RoomEvent.Disconnected, () => { void stopVoice() })
      await room.connect(grant.url, grant.token)
      await room.localParticipant.setMicrophoneEnabled(true)
      await room.startAudio()
      roomRef.current = room
      setVoice('on')
      toast.success(`Connected to v${grant.version}. Say hello; the agent answers in a moment.`)
    } catch (e) {
      await stopVoice()
      toast.error(e instanceof Error ? e.message : 'Could not start the voice test (is your microphone allowed?)')
    }
  }

  const addCase = async () => {
    try {
      await agentsApi.addTestCase(agent.id, { name: draft.name, caller_turns: lines(draft.caller),
        must_include: lines(draft.must), must_not_include: lines(draft.mustNot), expected_language: draft.language || null })
      setDraft({ name: '', caller: '', must: '', mustNot: '', language: '' })
      loadCases()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not add the test')
    }
  }

  const removeCase = async (id: string) => {
    try {
      await agentsApi.deleteTestCase(agent.id, id)
      loadCases()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not delete the test')
    }
  }

  const runTests = async () => {
    setRunning(true)
    try {
      const result = await agentsApi.runTests(agent.id, number)
      setRun(result)
      if (result.passed === result.total) toast.success(`All ${result.total} tests passed on v${number}`)
      else toast.error(`${result.total - result.passed} of ${result.total} tests failed on v${number}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not run the tests')
    } finally {
      setRunning(false)
    }
  }

  if (!canBuild) return <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>Managers and admins can test agents.</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxHeight: 520, overflowY: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <label htmlFor="studio-version" style={{ ...label, marginBottom: 0 }}>Test version</label>
        <select id="studio-version" className="avn-input" value={number} onChange={e => { setNumber(Number(e.target.value)); setTurns([]) }} style={{ height: 32 }}>
          {versions.map(v => <option key={v.id} value={v.number}>v{v.number} · {v.status}</option>)}
        </select>
        <Button size="sm" variant={voice === 'on' ? 'danger' : 'secondary'} loading={voice === 'connecting'}
          icon={voice === 'on' ? <MicOff size={12} /> : <Mic size={12} />} onClick={voice === 'on' ? stopVoice : startVoice}
          style={{ marginLeft: 'auto' }}>
          {voice === 'on' ? 'End voice test' : 'Talk by voice'}
        </Button>
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: -8 }}>
        Tests never dial a phone, book appointments or save call logs. Text replies use the same brief and knowledge base as calls.
      </div>

      <section aria-label="Text test" style={{ border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10, padding: 12 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto', marginBottom: 8 }}>
          {turns.length === 0 && <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Type what a caller would say.</div>}
          {turns.map((t, i) => (
            <div key={i} style={{ alignSelf: t.role === 'caller' ? 'flex-end' : 'flex-start', maxWidth: '85%', padding: '6px 10px', borderRadius: 10,
              fontSize: 12.5, background: t.role === 'caller' ? 'rgba(123,97,255,0.15)' : 'rgba(255,255,255,0.05)', color: 'var(--color-text-primary)' }}>
              {t.text}
            </div>
          ))}
          {thinking && <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Agent is replying…</div>}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <input className="avn-input" aria-label="Message as the caller" value={message} onChange={e => setMessage(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') void send() }} placeholder="e.g. What are your timings on Saturday?" style={field} />
          <Button size="sm" variant="primary" icon={<Send size={12} />} disabled={thinking || !message.trim()} onClick={send}>Send</Button>
          {turns.length > 0 && <Button size="sm" variant="ghost" onClick={() => setTurns([])}>Reset</Button>}
        </div>
      </section>

      <section aria-label="Test cases">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <strong style={{ fontSize: 13, color: 'var(--color-text-primary)' }}>Test cases ({cases.length})</strong>
          <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>A version needs a passing run before it can be marked tested.</span>
          <Button size="sm" variant="primary" icon={<Play size={12} />} loading={running} disabled={!cases.length}
            onClick={runTests} style={{ marginLeft: 'auto' }}>Run on v{number}</Button>
        </div>
        {run && (
          <div role="status" style={{ fontSize: 12.5, marginBottom: 8, color: run.passed === run.total ? '#22D3A5' : 'var(--color-danger)' }}>
            Last run on v{run.version_number}: {run.passed} of {run.total} passed · {new Date(run.created_at).toLocaleString()}
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {cases.map(c => {
            const result = (run?.results as { case_id: string; passed: boolean; missing: string[]; forbidden: string[]; wrong_language_replies?: number[]; error?: string | null }[] | undefined)
              ?.find(r => r.case_id === c.id)
            return (
              <div key={c.id} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.07)', fontSize: 12.5 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {result && <span style={{ fontWeight: 700, color: result.passed ? '#22D3A5' : 'var(--color-danger)' }}>{result.passed ? 'Pass' : 'Fail'}</span>}
                  <strong style={{ color: 'var(--color-text-primary)' }}>{c.name}</strong>
                  <button onClick={() => removeCase(c.id)} aria-label={`Delete test ${c.name}`}
                    style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><Trash2 size={13} /></button>
                </div>
                <div style={{ color: 'var(--color-text-muted)', marginTop: 2 }}>
                  Caller: {c.caller_turns.join(' → ')}
                  {c.must_include.length > 0 && <> · must say: {c.must_include.join(', ')}</>}
                  {c.must_not_include.length > 0 && <> · must not say: {c.must_not_include.join(', ')}</>}
                  {c.expected_language && <> · replies in {LANGUAGE_NAMES[c.expected_language]}</>}
                </div>
                {result && !result.passed && (
                  <div style={{ color: 'var(--color-danger)', marginTop: 2 }}>
                    {result.error ?? [result.missing.length ? `missing: ${result.missing.join(', ')}` : '', result.forbidden.length ? `said: ${result.forbidden.join(', ')}` : '',
                      result.wrong_language_replies?.length ? `wrong language in reply ${result.wrong_language_replies.join(', ')}` : ''].filter(Boolean).join(' · ')}
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <details style={{ marginTop: 10 }}>
          <summary style={{ fontSize: 12.5, cursor: 'pointer', color: 'var(--color-link)' }}>Add a test case</summary>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
            <div style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="tc-name" style={label}>Name</label>
              <input id="tc-name" className="avn-input" value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} style={field} placeholder="Weekend timings" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="tc-caller" style={label}>What the caller says (one message per line)</label>
              <textarea id="tc-caller" className="avn-input" rows={2} value={draft.caller} onChange={e => setDraft(d => ({ ...d, caller: e.target.value }))} style={field} />
            </div>
            <div>
              <label htmlFor="tc-must" style={label}>Replies must mention (one per line)</label>
              <textarea id="tc-must" className="avn-input" rows={2} value={draft.must} onChange={e => setDraft(d => ({ ...d, must: e.target.value }))} style={field} />
            </div>
            <div>
              <label htmlFor="tc-mustnot" style={label}>Replies must never say (one per line)</label>
              <textarea id="tc-mustnot" className="avn-input" rows={2} value={draft.mustNot} onChange={e => setDraft(d => ({ ...d, mustNot: e.target.value }))} style={field} />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="tc-lang" style={label}>Replies must be in</label>
              <select id="tc-lang" className="avn-input" value={draft.language} onChange={e => setDraft(d => ({ ...d, language: e.target.value as '' | TestLanguage }))} style={field}>
                <option value="">Any language</option>
                {(Object.keys(LANGUAGE_NAMES) as TestLanguage[]).map(code => <option key={code} value={code}>{LANGUAGE_NAMES[code]}</option>)}
              </select>
            </div>
          </div>
          <Button size="sm" variant="secondary" onClick={addCase} style={{ marginTop: 8 }}
            disabled={!draft.name.trim() || !lines(draft.caller).length || !(lines(draft.must).length || lines(draft.mustNot).length || draft.language)}>Add test</Button>
        </details>
      </section>
    </div>
  )
}
