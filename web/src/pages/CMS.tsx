import { useEffect, useState, useRef, type ElementType } from 'react'
import {
  FileText, Cpu, HelpCircle, ImageIcon, Globe, Plus, Pencil, Trash2, ChevronDown, ChevronUp, Search, Upload, Copy, ExternalLink,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Textarea from '../components/ui/Textarea'
import Modal from '../components/ui/Modal'
import { LoadingState } from '../components/ui/States'
import { cmsApi } from '../api/cms'
import type { CMSPage, CMSPrompt, CMSFaq } from '../types'
import toast from 'react-hot-toast'

type CMSTab = 'pages' | 'prompts' | 'faqs' | 'media'

const TABS: { id: CMSTab; label: string; icon: ElementType }[] = [
  { id: 'pages', label: 'Pages', icon: Globe },
  { id: 'prompts', label: 'Agent Prompts', icon: Cpu },
  { id: 'faqs', label: 'FAQs', icon: HelpCircle },
  { id: 'media', label: 'Media', icon: ImageIcon },
]

export default function CMS() {
  const [tab, setTab] = useState<CMSTab>('pages')
  const [loading, setLoading] = useState(true)

  // Data lists
  const [pages, setPages] = useState<CMSPage[]>([])
  const [prompts, setPrompts] = useState<CMSPrompt[]>([])
  const [faqs, setFaqs] = useState<CMSFaq[]>([])
  const [media, setMedia] = useState<any[]>([])

  // Search filter states
  const [pagesSearch, setPagesSearch] = useState('')
  const [faqsSearch, setFaqsSearch] = useState('')
  const [faqsExpanded, setFaqsExpanded] = useState<string | null>(null)

  // Modal open states
  const [isPageModalOpen, setIsPageModalOpen] = useState(false)
  const [isFaqModalOpen, setIsFaqModalOpen] = useState(false)

  // Editing targets
  const [activePage, setActivePage] = useState<Partial<CMSPage> | null>(null)
  const [activeFaq, setActiveFaq] = useState<Partial<CMSFaq> | null>(null)
  const [editingPromptId, setEditingPromptId] = useState<string | null>(null)
  const [promptContent, setPromptContent] = useState('')

  // Media upload input reference
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadingMedia, setUploadingMedia] = useState(false)

  const loadData = async () => {
    setLoading(true)
    try {
      const [pagesData, promptsData, faqsData, mediaData] = await Promise.all([
        cmsApi.pages.list(),
        cmsApi.prompts.list(),
        cmsApi.faqs.list(),
        cmsApi.media.list(),
      ])
      setPages(pagesData)
      setPrompts(promptsData)
      setFaqs(faqsData)
      setMedia(mediaData)
    } catch {
      toast.error('Failed to load content management data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Page Actions
  const handleOpenCreatePage = () => {
    setActivePage({
      title: '',
      slug: '',
      content: '',
      status: 'draft',
      category: 'Marketing',
      seo_title: '',
      seo_description: '',
    })
    setIsPageModalOpen(true)
  }

  const handleOpenEditPage = (page: CMSPage) => {
    setActivePage({ ...page })
    setIsPageModalOpen(true)
  }

  const handleSavePage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activePage || !activePage.title || !activePage.slug) {
      toast.error('Title and Slug are required')
      return
    }
    try {
      if (activePage.id) {
        // Update
        const res = await cmsApi.pages.update(activePage.id, activePage)
        if (res.status === 'ok') {
          toast.success('Page updated successfully')
          setPages(prev => prev.map(p => p.id === activePage.id ? res.page : p))
        }
      } else {
        // Create
        const res = await cmsApi.pages.create(activePage)
        if (res.status === 'ok') {
          toast.success('Page created successfully')
          setPages(prev => [res.page, ...prev])
        }
      }
      setIsPageModalOpen(false)
      setActivePage(null)
    } catch (err: any) {
      toast.error(err.message || 'Failed to save page')
    }
  }

  const handleDeletePage = async (id: string) => {
    if (!confirm('Are you sure you want to delete this page?')) return
    try {
      const res = await cmsApi.pages.delete(id)
      if (res.status === 'ok') {
        toast.success('Page deleted successfully')
        setPages(prev => prev.filter(p => p.id !== id))
      }
    } catch {
      toast.error('Failed to delete page')
    }
  }

  // Prompt Actions
  const handleStartEditPrompt = (prompt: CMSPrompt) => {
    setEditingPromptId(prompt.id)
    setPromptContent(prompt.content)
  }

  const handleSavePrompt = async (prompt: CMSPrompt) => {
    try {
      const res = await cmsApi.prompts.update(prompt.id, { ...prompt, content: promptContent })
      if (res.status === 'ok') {
        toast.success('Agent prompt updated successfully')
        setPrompts(prev => prev.map(p => p.id === prompt.id ? res.prompt : p))
        setEditingPromptId(null)
      }
    } catch {
      toast.error('Failed to save prompt')
    }
  }

  const handleTogglePromptStatus = async (prompt: CMSPrompt) => {
    try {
      const res = await cmsApi.prompts.update(prompt.id, { ...prompt, active: !prompt.active })
      if (res.status === 'ok') {
        toast.success(`Prompt ${res.prompt.active ? 'activated' : 'deactivated'}`)
        setPrompts(prev => prev.map(p => p.id === prompt.id ? res.prompt : p))
      }
    } catch {
      toast.error('Failed to update prompt status')
    }
  }

  // FAQ Actions
  const handleOpenCreateFaq = () => {
    setActiveFaq({
      question: '',
      answer: '',
      category: 'General',
    })
    setIsFaqModalOpen(true)
  }

  const handleOpenEditFaq = (faq: CMSFaq) => {
    setActiveFaq({ ...faq })
    setIsFaqModalOpen(true)
  }

  const handleSaveFaq = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeFaq || !activeFaq.question || !activeFaq.answer) {
      toast.error('Question and Answer are required')
      return
    }
    try {
      if (activeFaq.id) {
        const res = await cmsApi.faqs.update(activeFaq.id, activeFaq)
        if (res.status === 'ok') {
          toast.success('FAQ updated successfully')
          setFaqs(prev => prev.map(f => f.id === activeFaq.id ? res.faq : f))
        }
      } else {
        const res = await cmsApi.faqs.create(activeFaq)
        if (res.status === 'ok') {
          toast.success('FAQ created successfully')
          setFaqs(prev => [...prev, res.faq])
        }
      }
      setIsFaqModalOpen(false)
      setActiveFaq(null)
    } catch (err: any) {
      toast.error(err.message || 'Failed to save FAQ')
    }
  }

  const handleDeleteFaq = async (id: string) => {
    if (!confirm('Are you sure you want to delete this FAQ?')) return
    try {
      const res = await cmsApi.faqs.delete(id)
      if (res.status === 'ok') {
        toast.success('FAQ deleted successfully')
        setFaqs(prev => prev.filter(f => f.id !== id))
      }
    } catch {
      toast.error('Failed to delete FAQ')
    }
  }

  // Media Actions
  const handleMediaUploadClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    const file = files[0]

    const formData = new FormData()
    formData.append('file', file)

    setUploadingMedia(true)
    toast.loading(`Uploading file ${file.name}...`)
    try {
      const res = await cmsApi.media.upload(formData)
      toast.dismiss()
      if (res.status === 'ok') {
        toast.success('File uploaded successfully!')
        // Refresh media list
        const mList = await cmsApi.media.list()
        setMedia(mList)
      }
    } catch (err: any) {
      toast.dismiss()
      toast.error(err.message || 'Media upload failed')
    } finally {
      setUploadingMedia(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const copyMediaUrl = (url: string) => {
    // Resolve absolute URL
    const fullUrl = `${window.location.protocol}//${window.location.host}${url}`
    navigator.clipboard.writeText(fullUrl)
    toast.success('Media URL copied to clipboard')
  }

  // Filtered lists
  const filteredPages = pages.filter(p =>
    p.title.toLowerCase().includes(pagesSearch.toLowerCase()) ||
    (p.category && p.category.toLowerCase().includes(pagesSearch.toLowerCase())) ||
    p.slug.toLowerCase().includes(pagesSearch.toLowerCase())
  )

  const filteredFaqs = faqs.filter(f =>
    f.question.toLowerCase().includes(faqsSearch.toLowerCase()) ||
    f.answer.toLowerCase().includes(faqsSearch.toLowerCase()) ||
    (f.category && f.category.toLowerCase().includes(faqsSearch.toLowerCase()))
  )

  return (
    <div className="page-wrapper">
      {/* Header */}
      <div style={{ padding: '32px 32px 0', marginBottom: 28 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(123,97,255,0.08), rgba(94,230,255,0.04))',
          border: '1px solid rgba(123,97,255,0.12)',
          borderRadius: 18,
          padding: '24px 28px',
        }}>
          <div style={{
            fontFamily: 'Satoshi, Inter, sans-serif',
            fontSize: 26,
            fontWeight: 700,
            letterSpacing: '-0.03em',
            background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #9580FF)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            marginBottom: 6,
          }}>
            Content Management
          </div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
            Manage web pages · AI receptionist prompts · FAQs · Media assets
          </div>
        </div>
      </div>

      <div style={{ padding: '0 32px' }}>
        {/* Tabs switcher */}
        <div style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.03)', padding: 4, borderRadius: 12, border: '1px solid rgba(255,255,255,0.06)', marginBottom: 20, width: 'fit-content' }}>
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                padding: '8px 16px',
                borderRadius: 9,
                border: 'none',
                background: tab === id ? 'rgba(123,97,255,0.18)' : 'transparent',
                color: tab === id ? '#9580FF' : 'var(--color-text-muted)',
                fontSize: 13,
                fontWeight: tab === id ? 600 : 400,
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>

        {loading ? <LoadingState /> : (
          <>
            {/* 1. Pages Tab */}
            {tab === 'pages' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <div style={{ position: 'relative', flex: 1, maxWidth: 300 }}>
                    <Search size={13} color="#4B5675" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
                    <input
                      value={pagesSearch}
                      onChange={e => setPagesSearch(e.target.value)}
                      placeholder="Search pages…"
                      className="avn-input"
                      style={{ paddingLeft: 34, height: 36 }}
                    />
                  </div>
                  <Button variant="primary" icon={<Plus size={14} />} onClick={handleOpenCreatePage}>
                    New Page
                  </Button>
                </div>

                <Card padding={0}>
                  <table className="avn-table">
                    <thead>
                      <tr>
                        <th>Title</th>
                        <th>Category</th>
                        <th>Status</th>
                        <th>Updated</th>
                        <th style={{ textAlign: 'right' }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredPages.length === 0 ? (
                        <tr>
                          <td colSpan={5} style={{ textAlign: 'center', padding: 32, color: 'var(--color-text-muted)' }}>
                            No pages found.
                          </td>
                        </tr>
                      ) : (
                        filteredPages.map((page, i) => (
                          <tr key={page.id} style={{ animation: `fadeInUp 0.3s cubic-bezier(0.22,1,0.36,1) ${i * 40}ms both` }}>
                            <td>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <FileText size={13} color="#7B61FF" />
                                <span style={{ color: 'var(--color-text-primary)', fontWeight: 500 }}>{page.title}</span>
                                <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>/{page.slug}</span>
                              </div>
                            </td>
                            <td><span className="avn-chip avn-chip-gray" style={{ fontSize: 11 }}>{page.category || 'General'}</span></td>
                            <td>
                              <Badge variant={page.status === 'published' ? 'success' : 'warning'} dot>
                                {page.status}
                              </Badge>
                            </td>
                            <td style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{new Date(page.updated_at).toLocaleDateString()}</td>
                            <td>
                              <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                                <button aria-label="Edit page"
                                  onClick={() => handleOpenEditPage(page)}
                                  style={{ width: 28, height: 28, borderRadius: 7, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--color-text-muted)' }}
                                >
                                  <Pencil size={12} />
                                </button>
                                <button aria-label="Delete page"
                                  onClick={() => handleDeletePage(page.id)}
                                  style={{ width: 28, height: 28, borderRadius: 7, background: 'rgba(255,77,106,0.08)', border: '1px solid rgba(255,77,106,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#FF4D6A' }}
                                >
                                  <Trash2 size={12} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </Card>
              </div>
            )}

            {/* 2. Prompts Tab */}
            {tab === 'prompts' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {prompts.map((p, i) => (
                  <Card
                    key={p.id}
                    style={{ animation: `fadeInUp 0.3s cubic-bezier(0.22,1,0.36,1) ${i * 60}ms both` }}
                  >
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text-primary)' }}>{p.name}</span>
                          <button
                            onClick={() => handleTogglePromptStatus(p)}
                            style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer' }}
                          >
                            <Badge variant={p.active ? 'success' : 'default'} dot>{p.active ? 'Active' : 'Inactive'}</Badge>
                          </button>
                          {p.tags && p.tags.map(t => <span key={t} className="avn-chip avn-chip-violet" style={{ fontSize: 10 }}>{t}</span>)}
                        </div>
                        {editingPromptId === p.id ? (
                          <textarea
                            value={promptContent}
                            onChange={e => setPromptContent(e.target.value)}
                            style={{
                              width: '100%',
                              minHeight: 120,
                              background: 'var(--color-bg-card)',
                              border: '1px solid rgba(123,97,255,0.3)',
                              borderRadius: 10,
                              color: 'var(--color-text-primary)',
                              fontSize: 13,
                              padding: '10px 14px',
                              fontFamily: 'inherit',
                              resize: 'vertical',
                              outline: 'none',
                            }}
                          />
                        ) : (
                          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                            {p.content}
                          </div>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                        {editingPromptId === p.id ? (
                          <button
                            onClick={() => handleSavePrompt(p)}
                            style={{ width: 30, height: 30, borderRadius: 8, background: 'rgba(34,211,165,0.15)', border: '1px solid rgba(34,211,165,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#22D3A5' }}
                          >
                            Save
                          </button>
                        ) : (
                          <button aria-label="Edit prompt"
                            onClick={() => handleStartEditPrompt(p)}
                            style={{ width: 30, height: 30, borderRadius: 8, background: 'rgba(123,97,255,0.1)', border: '1px solid rgba(123,97,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#9580FF' }}
                          >
                            <Pencil size={13} />
                          </button>
                        )}
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}

            {/* 3. FAQs Tab */}
            {tab === 'faqs' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <div style={{ position: 'relative', flex: 1, maxWidth: 300 }}>
                    <Search size={13} color="#4B5675" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
                    <input
                      value={faqsSearch}
                      onChange={e => setFaqsSearch(e.target.value)}
                      placeholder="Search FAQs…"
                      className="avn-input"
                      style={{ paddingLeft: 34, height: 36 }}
                    />
                  </div>
                  <Button variant="primary" icon={<Plus size={14} />} onClick={handleOpenCreateFaq}>
                    Add FAQ
                  </Button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {filteredFaqs.length === 0 ? (
                    <Card style={{ textAlign: 'center', padding: 24, color: 'var(--color-text-muted)' }}>
                      No FAQs found.
                    </Card>
                  ) : (
                    filteredFaqs.map((faq, i) => (
                      <Card
                        key={faq.id}
                        padding={0}
                        style={{ animation: `fadeInUp 0.3s cubic-bezier(0.22,1,0.36,1) ${i * 50}ms both`, overflow: 'hidden' }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                          <button
                            onClick={() => setFaqsExpanded(faqsExpanded === faq.id ? null : faq.id)}
                            style={{
                              flex: 1,
                              padding: '14px 18px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 12,
                              background: 'transparent',
                              border: 'none',
                              color: 'var(--color-text-primary)',
                              cursor: 'pointer',
                              textAlign: 'left',
                            }}
                          >
                            <HelpCircle size={14} color="#7B61FF" style={{ flexShrink: 0 }} />
                            <span style={{ flex: 1, fontSize: 13.5, fontWeight: 500 }}>{faq.question}</span>
                            {faq.category && <span className="avn-chip avn-chip-gray" style={{ fontSize: 10, marginRight: 8 }}>{faq.category}</span>}
                            {faqsExpanded === faq.id ? <ChevronUp size={14} color="#4B5675" /> : <ChevronDown size={14} color="#4B5675" />}
                          </button>

                          <div style={{ display: 'flex', gap: 6, paddingRight: 18 }}>
                            <button aria-label="Edit FAQ"
                              onClick={() => handleOpenEditFaq(faq)}
                              style={{ width: 28, height: 28, borderRadius: 7, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--color-text-muted)' }}
                            >
                              <Pencil size={11} />
                            </button>
                            <button aria-label="Delete FAQ"
                              onClick={() => handleDeleteFaq(faq.id)}
                              style={{ width: 28, height: 28, borderRadius: 7, background: 'rgba(255,77,106,0.08)', border: '1px solid rgba(255,77,106,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#FF4D6A' }}
                            >
                              <Trash2 size={11} />
                            </button>
                          </div>
                        </div>
                        {faqsExpanded === faq.id && (
                          <div style={{ padding: '0 18px 16px 44px', fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.7, borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                            {faq.answer}
                          </div>
                        )}
                      </Card>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* 4. Media Tab */}
            {tab === 'media' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    style={{ display: 'none' }}
                    accept="image/*,audio/*,application/pdf"
                  />
                  <Button
                    variant="primary"
                    icon={<Upload size={14} />}
                    loading={uploadingMedia}
                    onClick={handleMediaUploadClick}
                  >
                    Upload Files
                  </Button>
                </div>

                {media.length === 0 ? (
                  <Card style={{ textAlign: 'center', padding: '48px 24px' }}>
                    <div style={{ width: 56, height: 56, borderRadius: 16, background: 'rgba(123,97,255,0.08)', border: '1px solid rgba(123,97,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', color: '#7B61FF' }}>
                      <ImageIcon size={24} />
                    </div>
                    <div style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 8 }}>Media Library</div>
                    <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 20 }}>Upload images, documents, and assets for use in your content</div>
                    <Button variant="outline" icon={<Upload size={13} />} onClick={handleMediaUploadClick}>Upload Files</Button>
                  </Card>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 14 }}>
                    {media.map((item, i) => (
                      <Card key={item.id} padding={12} style={{ animation: `scaleIn 0.3s ease ${i * 40}ms both`, overflow: 'hidden' }}>
                        {item.mime_type.startsWith('image/') ? (
                          <div style={{ height: 110, borderRadius: 10, background: 'var(--color-bg-card)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.03)', marginBottom: 10 }}>
                            <img src={item.url} alt={item.filename} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          </div>
                        ) : (
                          <div style={{ height: 110, borderRadius: 10, background: 'rgba(123,97,255,0.05)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(123,97,255,0.1)', marginBottom: 10, color: '#9580FF' }}>
                            <FileText size={32} />
                            <span style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 8 }}>{item.mime_type}</span>
                          </div>
                        )}
                        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--color-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 4 }}>
                          {item.filename}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, color: 'var(--color-text-muted)' }}>
                          <span>{(item.size_bytes / 1024).toFixed(1)} KB</span>
                          <div style={{ display: 'flex', gap: 4 }}>
                            <button
                              onClick={() => copyMediaUrl(item.url)}
                              title="Copy URL"
                              style={{ width: 22, height: 22, borderRadius: 5, background: 'rgba(255,255,255,0.04)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-secondary)', cursor: 'pointer' }}
                            >
                              <Copy size={11} />
                            </button>
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                              title="Open link"
                              style={{ width: 22, height: 22, borderRadius: 5, background: 'rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-secondary)' }}
                            >
                              <ExternalLink size={11} />
                            </a>
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Pages Add/Edit Modal */}
      <Modal
        open={isPageModalOpen}
        onClose={() => { setIsPageModalOpen(false); setActivePage(null) }}
        title={activePage?.id ? 'Edit Page Details' : 'New Web Page'}
        width={560}
      >
        {activePage && (
          <form onSubmit={handleSavePage} style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '20px 24px' }}>
            <Input
              label="Page Title"
              id="page-title"
              value={activePage.title || ''}
              onChange={e => setActivePage(p => ({ ...p, title: e.target.value }))}
            />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <Input
                label="Slug Path"
                id="page-slug"
                value={activePage.slug || ''}
                placeholder="e.g. hero"
                onChange={e => setActivePage(p => ({ ...p, slug: e.target.value }))}
              />
              <Input
                label="Category"
                id="page-category"
                value={activePage.category || ''}
                onChange={e => setActivePage(p => ({ ...p, category: e.target.value }))}
              />
            </div>

            <Select
              label="Status"
              id="page-status"
              value={activePage.status || 'draft'}
              options={[
                { value: 'published', label: 'Published' },
                { value: 'draft', label: 'Draft' },
                { value: 'archived', label: 'Archived' },
              ]}
              onChange={e => setActivePage(p => ({ ...p, status: e.target.value as any }))}
            />

            <Textarea
              label="Page Content"
              id="page-content"
              value={activePage.content || ''}
              rows={4}
              onChange={e => setActivePage(p => ({ ...p, content: e.target.value }))}
            />

            <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 14, marginTop: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: '#7B61FF', display: 'block', marginBottom: 10 }}>SEO Meta Configuration</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <Input
                  label="SEO Title Tag"
                  id="page-seo-title"
                  value={activePage.seo_title || ''}
                  onChange={e => setActivePage(p => ({ ...p, seo_title: e.target.value }))}
                />
                <Textarea
                  label="Meta Description"
                  id="page-seo-desc"
                  value={activePage.seo_description || ''}
                  rows={2}
                  onChange={e => setActivePage(p => ({ ...p, seo_description: e.target.value }))}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
              <Button variant="ghost" onClick={() => { setIsPageModalOpen(false); setActivePage(null) }}>Cancel</Button>
              <Button variant="primary" type="submit">Save Page</Button>
            </div>
          </form>
        )}
      </Modal>

      {/* FAQ Add/Edit Modal */}
      <Modal
        open={isFaqModalOpen}
        onClose={() => { setIsFaqModalOpen(false); setActiveFaq(null) }}
        title={activeFaq?.id ? 'Edit FAQ Item' : 'New FAQ'}
        width={500}
      >
        {activeFaq && (
          <form onSubmit={handleSaveFaq} style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '20px 24px' }}>
            <Input
              label="Question"
              id="faq-question"
              value={activeFaq.question || ''}
              onChange={e => setActiveFaq(f => ({ ...f, question: e.target.value }))}
            />

            <Input
              label="Category"
              id="faq-category"
              value={activeFaq.category || ''}
              placeholder="e.g. General"
              onChange={e => setActiveFaq(f => ({ ...f, category: e.target.value }))}
            />

            <Textarea
              label="Answer content"
              id="faq-answer"
              value={activeFaq.answer || ''}
              rows={4}
              onChange={e => setActiveFaq(f => ({ ...f, answer: e.target.value }))}
            />

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
              <Button variant="ghost" onClick={() => { setIsFaqModalOpen(false); setActiveFaq(null) }}>Cancel</Button>
              <Button variant="primary" type="submit">Save FAQ</Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
