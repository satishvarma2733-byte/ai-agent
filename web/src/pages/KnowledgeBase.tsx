import { useEffect, useState, useCallback } from 'react'
import {
  Plus, RefreshCw, Trash2, Globe, FileText, Search as SearchIcon,
  Clock, Upload, BookOpen, Zap,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import PageHeader from '../components/layout/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import Input from '../components/ui/Input'
import Toggle from '../components/ui/Toggle'
import Textarea from '../components/ui/Textarea'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { LoadingState, ErrorState, EmptyState } from '../components/ui/States'
import { kbApi } from '../api/kb'
import type { KbStatus, KbSource, KbJob, KbSearchResult } from '../types'

// ─── Status helpers ─────────────────────────────────────────
function sourceStatusBadge(s: string) {
  if (s === 'ready') return <Badge variant="success" dot>Ready</Badge>
  if (s === 'pending') return <Badge variant="warning" dot>Pending</Badge>
  if (s === 'processing') return <Badge variant="info" dot>Processing</Badge>
  return <Badge variant="danger" dot>{s}</Badge>
}
function jobStatusBadge(s: string) {
  if (s === 'completed') return <Badge variant="success" dot>Completed</Badge>
  if (s === 'pending') return <Badge variant="warning" dot>Pending</Badge>
  if (s === 'running') return <Badge variant="info" dot>Running</Badge>
  return <Badge variant="danger" dot>{s}</Badge>
}

export default function KnowledgeBase() {
  const [kbStatus, setKbStatus] = useState<KbStatus | null>(null)
  const [sources, setSources] = useState<KbSource[]>([])
  const [jobs, setJobs] = useState<KbJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create source modal
  const [createOpen, setCreateOpen] = useState(false)
  const [createType, setCreateType] = useState<'web_url' | 'pdf_upload' | 'text'>('web_url')
  const [createText, setCreateText] = useState('')
  const [reindexing, setReindexing] = useState(false)
  const [createTitle, setCreateTitle] = useState('')
  const [createUrl, setCreateUrl] = useState('')
  const [createEnabled, setCreateEnabled] = useState(true)
  const [createFile, setCreateFile] = useState<File | null>(null)
  const [creating, setCreating] = useState(false)
  const [createErr, setCreateErr] = useState('')

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<KbSource | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Edit modal
  const [editTarget, setEditTarget] = useState<KbSource | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editEnabled, setEditEnabled] = useState(true)
  const [editUrl, setEditUrl] = useState('')
  const [saving, setSaving] = useState(false)

  // Search playground
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResult, setSearchResult] = useState<KbSearchResult | null>(null)
  const [searching, setSearching] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statusRes, sourcesRes, jobsRes] = await Promise.allSettled([
        kbApi.status(),
        kbApi.sources(),
        kbApi.jobs(),
      ])
      if (statusRes.status === 'fulfilled') setKbStatus(statusRes.value)
      if (sourcesRes.status === 'fulfilled') setSources(sourcesRes.value.items ?? [])
      if (jobsRes.status === 'fulfilled') setJobs(jobsRes.value.items ?? [])

      if (statusRes.status === 'rejected') {
        const e = statusRes.reason
        const msg = e instanceof Error ? e.message : String(e)
        if (msg.includes('setup_required') || msg.includes('not_configured')) {
          setKbStatus({ status: msg.includes('setup_required') ? 'setup_required' : 'not_configured', kb_enabled: false, backend: '—', runtime: '—', embedding_provider: '—', embedding_model: '—', index_kind: '—', data_dir: '—' })
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load KB')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleCreate() {
    setCreateErr('')
    if (!createTitle.trim()) { setCreateErr('Title is required'); return }
    if (createType === 'web_url' && !createUrl.trim()) { setCreateErr('URL is required'); return }
    if (createType === 'pdf_upload' && !createFile) { setCreateErr('File is required'); return }
    if (createType === 'text' && !createText.trim()) { setCreateErr('Text is required'); return }
    setCreating(true)
    try {
      if (createType === 'web_url') {
        const res = await kbApi.createSource({ source_type: 'web_url', title: createTitle, source_url: createUrl, enabled: createEnabled })
        setSources(prev => [res.source, ...prev])
        toast.success('Source created')
      } else if (createType === 'text') {
        const res = await kbApi.createSource({ source_type: 'text', title: createTitle, raw_text: createText, enabled: createEnabled })
        setSources(prev => [res.source, ...prev])
        setCreateText('')
        toast.success('Text added; indexing now')
      } else if (createFile) {
        const res = await kbApi.upload(createFile)
        setSources(prev => [res.source, ...prev])
        toast.success('File uploaded')
      }
      setCreateOpen(false)
      setCreateTitle(''); setCreateUrl(''); setCreateFile(null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to create source')
    } finally {
      setCreating(false)
    }
  }

  async function handleReindex() {
    setReindexing(true)
    try {
      const res = await kbApi.reindex()
      toast.success(res.queued ? `Re-indexing ${res.queued} source(s)` : 'Everything is already up to date')
      void load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Re-index failed')
    } finally {
      setReindexing(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await kbApi.deleteSource(deleteTarget.id)
      setSources(prev => prev.filter(s => s.id !== deleteTarget.id))
      setDeleteTarget(null)
      toast.success('Source deleted')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete')
    } finally {
      setDeleting(false)
    }
  }

  async function handleSync(source: KbSource) {
    try {
      const res = await kbApi.syncSource(source.id)
      setJobs(prev => [res.job, ...prev])
      toast.success('Sync job dispatched')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Sync failed')
    }
  }

  async function handleSaveEdit() {
    if (!editTarget) return
    setSaving(true)
    try {
      const payload: Partial<KbSource> = { title: editTitle, enabled: editEnabled }
      if (editTarget.source_type === 'web_url') payload.source_url = editUrl
      const res = await kbApi.updateSource(editTarget.id, payload)
      setSources(prev => prev.map(s => s.id === editTarget.id ? res.source : s))
      setEditTarget(null)
      toast.success('Source updated')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to update')
    } finally {
      setSaving(false)
    }
  }

  async function handleSearch() {
    if (!searchQuery.trim()) return
    setSearching(true)
    setSearchResult(null)
    try {
      const res = await kbApi.search(searchQuery)
      setSearchResult(res)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Search failed')
    } finally {
      setSearching(false)
    }
  }

  if (loading) return <div style={{ padding: 32 }}><LoadingState /></div>
  if (error) return <div style={{ padding: 32 }}><ErrorState message={error} onRetry={load} /></div>

  const isSetupRequired = kbStatus?.status === 'setup_required' || kbStatus?.status === 'not_configured'

  return (
    <div className="animate-fade-in" style={{ padding: '0 0 60px' }}>
      <PageHeader
        title="Knowledge Base"
        subtitle="Manage sources, upload files, monitor ingest jobs, and test search"
        actions={
          <Button variant="primary" icon={<Plus size={14} />} onClick={() => { setCreateOpen(true); setCreateType('web_url'); setCreateTitle(''); setCreateUrl(''); setCreateFile(null); setCreateEnabled(true); setCreateErr('') }}>
            Add Source
          </Button>
        }
      />

      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* KB Status Panel */}
        {kbStatus && (
          <Card>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <BookOpen size={15} color="#7c6fcd" />
              <span style={{ fontSize: 13.5, fontWeight: 600, color: '#e8ecf0' }}>System Status</span>
              <Badge
                variant={
                  kbStatus.status === 'ok' ? 'success'
                  : kbStatus.status === 'setup_required' ? 'warning'
                  : 'danger'
                }
                dot
              >
                {kbStatus.status}
              </Badge>
            </div>
            {isSetupRequired ? (
              <p style={{ fontSize: 13, color: '#8891a8' }}>
                The knowledge base could not be loaded. Check that the API is running and the database is reachable.
              </p>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 16 }}>
                {[
                  ['Backend', kbStatus.backend],
                  ['Embedding', `${kbStatus.embedding_provider} / ${kbStatus.embedding_model}`],
                  ['Languages', 'Multilingual (auto)'],
                  ['Vectors', String(kbStatus.vector_count ?? kbStatus.index_status?.vector_count ?? '—')],
                  ['Sources', String(kbStatus.counts?.sources ?? '—')],
                  ['Chunks', String(kbStatus.counts?.chunks ?? '—')],
                ].map(([label, val]) => (
                  <div key={label}>
                    <div style={{ fontSize: 11, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
                    <div style={{ fontSize: 14, color: 'var(--color-text-primary)', fontWeight: 500 }}>{val}</div>
                  </div>
                ))}
              </div>
            )}
            {!isSetupRequired && kbStatus.embedding_ready === false && (
              <p role="alert" style={{ marginTop: 14, fontSize: 13, color: '#F5C26B' }}>
                {kbStatus.embedding_issue ?? 'Embeddings are not configured.'} New documents can't be indexed for
                multilingual search until this is fixed (Configuration → Google API key).
              </p>
            )}
            {!isSetupRequired && (kbStatus.stale_vector_count ?? 0) > 0 && (
              <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 13, color: '#F5C26B' }}>
                  {kbStatus.stale_vector_count} chunk(s) were indexed with a different embedding model and are only
                  found by keyword until re-indexed.
                </span>
                <Button variant="secondary" size="sm" loading={reindexing} onClick={handleReindex}>Re-index now</Button>
              </div>
            )}
          </Card>
        )}

        {/* Sources Table */}
        <Card padding={0}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid #1e2236', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 13.5, fontWeight: 600, color: '#e8ecf0' }}>Sources ({sources.length})</span>
            <Button variant="ghost" size="sm" icon={<RefreshCw size={13} />} onClick={load}>Refresh</Button>
          </div>
          {sources.length === 0 ? (
            <EmptyState
              icon={<FileText size={32} />}
              title="No KB sources"
              description="Add a website URL, sitemap, or upload a PDF to start building the knowledge base."
              action={<Button variant="primary" icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>Add Source</Button>}
            />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr>
                    {['Type', 'Title', 'URL / Path', 'Status', 'Enabled', 'Last Synced', ''].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', whiteSpace: 'nowrap', background: 'var(--color-bg-card)' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sources.map(src => (
                    <tr key={src.id} style={{ borderBottom: '1px solid #131625' }} onMouseOver={e => (e.currentTarget.style.background = '#181c2e')} onMouseOut={e => (e.currentTarget.style.background = '')}>
                      <td style={{ padding: '11px 14px' }}>
                        {src.source_type === 'web_url'
                          ? <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#38bdf8', fontSize: 12 }}><Globe size={13} />URL</span>
                          : <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#f59e0b', fontSize: 12 }}><FileText size={13} />PDF</span>}
                      </td>
                      <td style={{ padding: '11px 14px', color: '#e8ecf0', fontWeight: 500, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {src.title}
                      </td>
                      <td style={{ padding: '11px 14px', color: '#8891a8', fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {src.source_url || src.storage_path || '—'}
                      </td>
                      <td style={{ padding: '11px 14px' }}>{sourceStatusBadge(src.status)}</td>
                      <td style={{ padding: '11px 14px' }}>
                        <Badge variant={src.enabled ? 'success' : 'default'}>{src.enabled ? 'Yes' : 'No'}</Badge>
                      </td>
                      <td style={{ padding: '11px 14px', color: '#8891a8', fontSize: 12, whiteSpace: 'nowrap' }}>
                        {src.last_synced_at ? format(new Date(src.last_synced_at), 'MMM d, HH:mm') : '—'}
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <Button variant="ghost" size="sm" icon={<RefreshCw size={12} />} onClick={() => handleSync(src)}>Sync</Button>
                          <Button variant="ghost" size="sm" icon={<Zap size={12} />} onClick={() => { setEditTarget(src); setEditTitle(src.title); setEditEnabled(src.enabled); setEditUrl(src.source_url ?? '') }}>Edit</Button>
                          <Button variant="danger" size="sm" icon={<Trash2 size={12} />} onClick={() => setDeleteTarget(src)}>Delete</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Upload Area */}
        <Card>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: '#e8ecf0', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Upload size={15} color="#7c6fcd" /> Quick PDF Upload
          </div>
          <FileDropZone
            onFile={async (file) => {
              try {
                const res = await kbApi.upload(file)
                setSources(prev => [res.source, ...prev])
                toast.success(`Uploaded: ${file.name}`)
              } catch (e) {
                toast.error(e instanceof Error ? e.message : 'Upload failed')
              }
            }}
          />
        </Card>

        {/* Jobs Table */}
        <Card padding={0}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid #1e2236', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 13.5, fontWeight: 600, color: '#e8ecf0' }}>Ingest Jobs ({jobs.length})</span>
            <Button variant="ghost" size="sm" icon={<RefreshCw size={13} />} onClick={load}>Refresh</Button>
          </div>
          {jobs.length === 0 ? (
            <EmptyState icon={<Clock size={32} />} title="No jobs yet" description="Sync a source to trigger an ingest job." />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr>
                    {['ID', 'Source ID', 'Type', 'Job Type', 'Status', 'Updated'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', background: 'var(--color-bg-card)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {jobs.slice(0, 30).map(job => (
                    <tr key={job.id} style={{ borderBottom: '1px solid #131625' }}>
                      <td style={{ padding: '10px 14px', color: '#8891a8' }}>#{job.id}</td>
                      <td style={{ padding: '10px 14px', color: '#8891a8' }}>#{job.source_id}</td>
                      <td style={{ padding: '10px 14px', color: 'var(--color-text-primary)' }}>{job.source_type}</td>
                      <td style={{ padding: '10px 14px', color: 'var(--color-text-primary)' }}>{job.job_type}</td>
                      <td style={{ padding: '10px 14px' }}>{jobStatusBadge(job.status)}</td>
                      <td style={{ padding: '10px 14px', color: '#8891a8', fontSize: 12, whiteSpace: 'nowrap' }}>
                        {format(new Date(job.updated_at), 'MMM d, HH:mm:ss')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Search Playground */}
        <Card>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: '#e8ecf0', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <SearchIcon size={15} color="#7c6fcd" /> Search Playground
          </div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Enter a question to search the knowledge base…"
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              style={{
                flex: 1,
                padding: '9px 14px',
                background: 'var(--color-bg-card)',
                border: '1px solid #2a2f47',
                borderRadius: 8,
                color: '#e8ecf0',
                fontSize: 13.5,
                outline: 'none',
              }}
            />
            <Button variant="primary" loading={searching} icon={<SearchIcon size={14} />} onClick={handleSearch}>
              Search
            </Button>
          </div>
          {searchResult && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(searchResult.result?.chunk_hits ?? []).length === 0 ? (
                <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>No results found</div>
              ) : (
                searchResult.result?.chunk_hits.map((hit, i) => (
                  <div key={i} style={{ background: 'var(--color-bg-card)', border: '1px solid #1e2236', borderRadius: 10, padding: '14px 16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                      <span style={{ fontWeight: 600, fontSize: 13, color: '#e8ecf0' }}>{hit.title}</span>
                      <Badge variant="info">Score: {hit.score.toFixed(2)}</Badge>
                    </div>
                    {hit.source_url && (
                      <div style={{ fontSize: 11.5, color: '#7c6fcd', marginBottom: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {hit.source_url}
                      </div>
                    )}
                    <p style={{ fontSize: 12.5, color: '#8891a8', lineHeight: 1.65, margin: 0 }}>
                      {hit.preview || hit.content?.slice(0, 300)}
                    </p>
                  </div>
                ))
              )}
            </div>
          )}
        </Card>
      </div>

      {/* Add Source Modal */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Add Knowledge Base Source" width={500}>
        <div style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
            <button
              onClick={() => setCreateType('web_url')}
              style={{
                flex: 1,
                padding: '10px',
                borderRadius: 8,
                border: `1px solid ${createType === 'web_url' ? '#7c6fcd' : '#2a2f47'}`,
                background: createType === 'web_url' ? '#7c6fcd20' : '#111422',
                color: createType === 'web_url' ? '#9183e0' : '#8891a8',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                justifyContent: 'center',
              }}
            >
              <Globe size={14} /> Web URL / Sitemap
            </button>
            <button
              onClick={() => setCreateType('pdf_upload')}
              style={{
                flex: 1,
                padding: '10px',
                borderRadius: 8,
                border: `1px solid ${createType === 'pdf_upload' ? '#f59e0b' : '#2a2f47'}`,
                background: createType === 'pdf_upload' ? '#f59e0b18' : '#111422',
                color: createType === 'pdf_upload' ? '#f59e0b' : '#8891a8',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                justifyContent: 'center',
              }}
            >
              <FileText size={14} /> File Upload
            </button>
            <button
              onClick={() => setCreateType('text')}
              style={{
                flex: 1,
                padding: '10px',
                borderRadius: 8,
                border: `1px solid ${createType === 'text' ? '#22D3A5' : '#2a2f47'}`,
                background: createType === 'text' ? '#22D3A518' : '#111422',
                color: createType === 'text' ? '#22D3A5' : '#8891a8',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                justifyContent: 'center',
              }}
            >
              <FileText size={14} /> Paste Text
            </button>
          </div>
          <Input
            label="Title"
            id="src-title"
            value={createTitle}
            onChange={e => setCreateTitle(e.target.value)}
            placeholder="e.g. Company FAQ"
          />
          {createType === 'web_url' ? (
            <Input
              label="URL"
              id="src-url"
              value={createUrl}
              onChange={e => setCreateUrl(e.target.value)}
              placeholder="https://example.com/faq or sitemap.xml"
              hint="Normal page URL or sitemap URL — the backend handles both."
            />
          ) : createType === 'text' ? (
            <Textarea
              label="Text"
              id="src-text"
              rows={8}
              value={createText}
              onChange={e => setCreateText(e.target.value)}
              placeholder="Paste FAQs, prices, policies… in any language"
              hint="Up to 200,000 characters. Callers can ask about it in any supported language."
            />
          ) : (
            <div>
              <label style={{ fontSize: 12.5, fontWeight: 500, color: '#8891a8', display: 'block', marginBottom: 5 }}>File (PDF, TXT, or Markdown)</label>
              <input
                type="file"
                accept=".pdf,.txt,.md"
                onChange={e => setCreateFile(e.target.files?.[0] ?? null)}
                style={{ fontSize: 13, color: 'var(--color-text-primary)' }}
              />
            </div>
          )}
          <Toggle
            id="src-enabled"
            checked={createEnabled}
            onChange={setCreateEnabled}
            label="Enabled"
            hint="Enable this source immediately after creation"
          />
          {createErr && <span style={{ fontSize: 12, color: '#ef4444' }}>{createErr}</span>}
        </div>
        <div style={{ padding: '12px 20px 20px', display: 'flex', gap: 8, justifyContent: 'flex-end', borderTop: '1px solid #1e2236' }}>
          <Button variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={creating} onClick={handleCreate}>
            {createType === 'pdf_upload' ? 'Upload & Create' : 'Create Source'}
          </Button>
        </div>
      </Modal>

      {/* Edit Source Modal */}
      <Modal open={!!editTarget} onClose={() => setEditTarget(null)} title="Edit Source" width={460}>
        <div style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Input label="Title" id="edit-title" value={editTitle} onChange={e => setEditTitle(e.target.value)} />
          {editTarget?.source_type === 'web_url' && (
            <Input label="URL" id="edit-url" value={editUrl} onChange={e => setEditUrl(e.target.value)} />
          )}
          <Toggle id="edit-enabled" checked={editEnabled} onChange={setEditEnabled} label="Enabled" />
        </div>
        <div style={{ padding: '12px 20px 20px', display: 'flex', gap: 8, justifyContent: 'flex-end', borderTop: '1px solid #1e2236' }}>
          <Button variant="ghost" onClick={() => setEditTarget(null)}>Cancel</Button>
          <Button variant="primary" loading={saving} onClick={handleSaveEdit}>Save</Button>
        </div>
      </Modal>

      {/* Delete Confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Source"
        message={<>Delete <strong style={{ color: '#e8ecf0' }}>{deleteTarget?.title}</strong>? This will remove all indexed chunks from this source.</>}
        confirmLabel="Delete"
        destructive
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}

// ─── File Drop Zone ──────────────────────────────────────────
function FileDropZone({ onFile }: { onFile: (f: File) => Promise<void> }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)

  async function handle(file: File) {
    if (!file.name.endsWith('.pdf')) { toast.error('Only PDF files are supported'); return }
    setUploading(true)
    await onFile(file).finally(() => setUploading(false))
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={async e => {
        e.preventDefault()
        setDragging(false)
        const file = e.dataTransfer.files[0]
        if (file) await handle(file)
      }}
      style={{
        border: `2px dashed ${dragging ? '#7c6fcd' : '#2a2f47'}`,
        borderRadius: 10,
        padding: '28px 20px',
        textAlign: 'center',
        background: dragging ? '#7c6fcd10' : '#0b0d14',
        transition: 'all 0.2s',
        cursor: 'pointer',
      }}
      onClick={() => {
        if (uploading) return
        const inp = document.createElement('input')
        inp.type = 'file'
        inp.accept = '.pdf'
        inp.onchange = async () => { if (inp.files?.[0]) await handle(inp.files[0]) }
        inp.click()
      }}
    >
      {uploading ? (
        <div style={{ fontSize: 13.5, color: '#7c6fcd' }}>Uploading…</div>
      ) : (
        <>
          <Upload size={28} color="#3b4260" style={{ margin: '0 auto 10px' }} />
          <div style={{ fontSize: 13.5, color: '#8891a8', fontWeight: 500 }}>Drag & drop a PDF here, or click to browse</div>
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>Only PDF files are supported</div>
        </>
      )}
    </div>
  )
}
