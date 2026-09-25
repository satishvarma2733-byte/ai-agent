import { useEffect, useState, useRef } from 'react'
import {
  Users,
  KanbanSquare,
  ListFilter,
  Zap,
  Phone,
  Plus,
  Download,
  Upload,
  Calendar,
  DollarSign,
  GraduationCap,
  ShieldCheck,
  UserCheck,
  Award,
  ChevronRight,
  Clock,
  Play,
  Pause,
  MessageSquare,
  Activity,
  Trash2,
  Save,
  CheckCircle,
  HelpCircle,
} from 'lucide-react'
import { crmApi } from '../api/crm'
import LeadWhatsApp from '../components/crm/LeadWhatsApp'
import { apiUrl } from '../api/client'
import { logsApi } from '../api/logs'
import type { Lead, LeadActivity, Workflow, LeadStatus, LeadScore } from '../types'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import { csvRow } from '../lib/csv'
import { workspaceApi } from '../api/workspace'
import { callsApi } from '../api/calls'
import { teamApi, type Member } from '../api/team'
import { leadFieldsApi, type LeadField } from '../api/leadFields'
import CustomFieldInputs from '../components/crm/CustomFieldInputs'
import Modal from '../components/ui/Modal'
import type { ImportResult } from '../api/crm'

// ─── TRANSLATIONS DICTIONARY ──────────────────────────────────────────
const translations = {
  en: {
    crm: "Voice CRM",
    pipeline: "Pipeline Board",
    listView: "Lead List",
    workflows: "Workflow Automation",
    addLead: "Add Lead",
    exportCsv: "Export CSV",
    searchPlaceholder: "Search by name, phone, company...",
    status: "Status",
    score: "AI Lead Score",
    assigned: "Assigned Agent",
    actions: "Actions",
    noLeads: "No leads found",
    new: "New",
    contacted: "Contacted",
    followUp: "Follow-up",
    interested: "Interested",
    converted: "Converted",
    lost: "Lost",
    hot: "Hot",
    warm: "Warm",
    cold: "Cold",
    name: "Name",
    phone: "Phone",
    email: "Email",
    company: "Company",
    notes: "Notes",
    objections: "Objections",
    neet: "Qualifier score",
    rank: "Rank",
    budget: "Budget",
    parentInvolved: "Parent Involved",
    countryPref: "Country Preference",
    followUpDate: "Follow Up Date",
    save: "Save Details",
    delete: "Delete Lead",
    timeline: "Lead Activity Timeline",
    recordingPlayer: "Recording Player",
    transcription: "Call Transcript",
    counselorRecs: "Auto-University Recommendations",
    workflowName: "Workflow Name",
    trigger: "Trigger Event",
    active: "Active",
    statusText: "Status updated",
    whatsappSent: "WhatsApp reminder queued",
  },
  hi: {
    crm: "वॉइस CRM",
    pipeline: "पाइपलाइन बोर्ड",
    listView: "लीड सूची",
    workflows: "वर्कफ़्लो स्वचालन",
    addLead: "नया लीड जोड़ें",
    exportCsv: "CSV निर्यात करें",
    searchPlaceholder: "नाम, फोन या कंपनी से खोजें...",
    status: "स्थिति",
    score: "AI लीड स्कोर",
    assigned: "सौंपा गया एजेंट",
    actions: "कार्रवाई",
    noLeads: "कोई लीड नहीं मिला",
    new: "नया",
    contacted: "संपर्क किया",
    followUp: "फॉलो-अप",
    interested: "रुचि है",
    converted: "कन्वर्ट हुआ",
    lost: "खो गया",
    hot: "हॉट (उच्च)",
    warm: "वार्म (मध्यम)",
    cold: "कोल्ड (निम्न)",
    name: "नाम",
    phone: "फ़ोन",
    email: "ईमेल",
    company: "कंपनी",
    notes: "काउंसलर नोट्स",
    objections: "आपत्तियां",
    neet: "योग्यता स्कोर",
    rank: "रैंक",
    budget: "बजट",
    parentInvolved: "अभिभावक शामिल",
    countryPref: "देश की प्राथमिकता",
    followUpDate: "फॉलो-अप तिथि",
    save: "विवरण सहेजें",
    delete: "लीड हटाएं",
    timeline: "लीड गतिविधि समयरेखा",
    recordingPlayer: "कॉल रिकॉर्डिंग प्लेयर",
    transcription: "कॉल ट्रांसक्रिप्ट",
    counselorRecs: "ऑटो-यूनिवर्सिटी सिफारिशें",
    workflowName: "वर्कफ़्लो नाम",
    trigger: "ट्रिगर इवेंट",
    active: "सक्रिय",
    statusText: "स्थिति अपडेट की गई",
    whatsappSent: "व्हाट्सएप संदेश कतारबद्ध",
  },
  es: {
    crm: "CRM de Voz",
    pipeline: "Tablero de Pipeline",
    listView: "Lista de Prospectos",
    workflows: "Automatización de Workflows",
    addLead: "Añadir Prospecto",
    exportCsv: "Exportar CSV",
    searchPlaceholder: "Buscar por nombre, teléfono...",
    status: "Estado",
    score: "Puntuación AI",
    assigned: "Agente Asignado",
    actions: "Acciones",
    noLeads: "No se encontraron prospectos",
    new: "Nuevo",
    contacted: "Contactado",
    followUp: "Seguimiento",
    interested: "Interesado",
    converted: "Convertido",
    lost: "Perdido",
    hot: "Caliente",
    warm: "Tibio",
    cold: "Frío",
    name: "Nombre",
    phone: "Teléfono",
    email: "Correo",
    company: "Empresa",
    notes: "Notas del Consejero",
    objections: "Objeciones",
    neet: "Puntaje de calificación",
    rank: "Rango",
    budget: "Presupuesto",
    parentInvolved: "Padre Involucrado",
    countryPref: "País de Preferencia",
    followUpDate: "Fecha de Seguimiento",
    save: "Guardar Detalles",
    delete: "Eliminar Prospecto",
    timeline: "Línea de Tiempo del Prospecto",
    recordingPlayer: "Reproductor de Grabaciones",
    transcription: "Transcripción de la Llamada",
    counselorRecs: "Recomendaciones de Universidad",
    workflowName: "Nombre del Workflow",
    trigger: "Evento Disparador",
    active: "Activo",
    statusText: "Estado actualizado",
    whatsappSent: "Mensaje de WhatsApp en cola",
  }
}

const statusOptions: LeadStatus[] = ['New', 'Contacted', 'Follow-up', 'Interested', 'Converted', 'Lost']
const scoreColors = {
  Hot: 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(245, 158, 11, 0.2))',
  Warm: 'linear-gradient(135deg, rgba(14, 165, 233, 0.2), rgba(94, 230, 255, 0.2))',
  Cold: 'linear-gradient(135deg, rgba(148, 163, 184, 0.15), rgba(148, 163, 184, 0.05))',
}

const scoreTextColors = {
  Hot: '#F87171',
  Warm: '#38BDF8',
  Cold: '#94A3B8',
}

// Follow-ups compare calendar days in the viewer's own timezone.
function localToday(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const CLOSED = ['Converted', 'Lost']
function followUpState(lead: Lead): 'overdue' | 'today' | 'upcoming' | null {
  if (!lead.follow_up_date || CLOSED.includes(lead.status)) return null
  const today = localToday()
  return lead.follow_up_date < today ? 'overdue' : lead.follow_up_date === today ? 'today' : 'upcoming'
}

export default function CRM() {
  const [lang, setLang] = useState(() => localStorage.getItem('language') || 'en')
  const [role, setRole] = useState(() => localStorage.getItem('userRole') || '')
  const [workspaceName, setWorkspaceName] = useState('')
  const [activeTab, setActiveTab] = useState<'pipeline' | 'list' | 'workflows'>('pipeline')
  
  const [leads, setLeads] = useState<Lead[]>([])
  const [filteredLeads, setFilteredLeads] = useState<Lead[]>([])
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  
  const [searchQ, setSearchQ] = useState('')
  const [filterStatus, setFilterStatus] = useState<string>('All')
  const [filterScore, setFilterScore] = useState<string>('All')
  const [onlyMine, setOnlyMine] = useState(false)
  const [filterFollowUp, setFilterFollowUp] = useState<'All' | 'overdue' | 'today' | 'upcoming'>(() => {
    const f = new URLSearchParams(window.location.search).get('follow_up')
    return f === 'overdue' || f === 'today' || f === 'upcoming' ? f : 'All'
  })
  const [importOpen, setImportOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [leadFields, setLeadFields] = useState<LeadField[]>([])
  
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null)
  const [timeline, setTimeline] = useState<LeadActivity[]>([])
  const [newNote, setNewNote] = useState('')
  const [scoringLoading, setScoringLoading] = useState(false)
  
  // Call recording player state
  const [callLogs, setCallLogs] = useState<any[]>([])
  const [activeCall, setActiveCall] = useState<any | null>(null)
  const [transcript, setTranscript] = useState<string>('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [playProgress, setPlayProgress] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  
  // Create lead state
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [newLeadData, setNewLeadData] = useState<Partial<Lead>>({
    name: '',
    phone: '',
    email: '',
    company: '',
    status: 'New',
    score: 'Warm',
    assigned_agent: 'Unassigned',
    neet_score: undefined,
    rank: undefined,
    budget: '',
    parent_involved: false,
    country_preference: '',
    notes: '',
  })

  // Listen for custom events to handle hot-swaps
  useEffect(() => {
    const handleLang = () => setLang(localStorage.getItem('language') || 'en')
    const handleRole = () => setRole(localStorage.getItem('userRole') || '')
    window.addEventListener('languageChanged', handleLang)
    window.addEventListener('roleChanged', handleRole)
    return () => {
      window.removeEventListener('languageChanged', handleLang)
      window.removeEventListener('roleChanged', handleRole)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    workspaceApi.get().then(w => { if (!cancelled) setWorkspaceName(w.name) }).catch(() => {})
    teamApi.members().then(m => { if (!cancelled) setMembers(m) }).catch(() => {})
    leadFieldsApi.list().then(f => { if (!cancelled) setLeadFields(f) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  const t = translations[lang as 'en'|'hi'|'es'] || translations.en

  // Load leads and workflows
  const loadData = async () => {
    try {
      const fetchedLeads = await crmApi.listLeads()
      setLeads(fetchedLeads)
      const fetchedWorkflows = await crmApi.listWorkflows()
      setWorkflows(fetchedWorkflows)
    } catch (err) {
      toast.error('Error loading CRM details')
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Filter logic
  useEffect(() => {
    let result = [...leads]
    if (searchQ) {
      const q = searchQ.toLowerCase()
      result = result.filter(
        (l) =>
          l.name.toLowerCase().includes(q) ||
          l.phone.includes(q) ||
          (l.company && l.company.toLowerCase().includes(q))
      )
    }
    if (filterStatus !== 'All') {
      result = result.filter((l) => l.status === filterStatus)
    }
    if (filterScore !== 'All') {
      result = result.filter((l) => l.score === filterScore)
    }
    if (filterFollowUp !== 'All') {
      result = result.filter((l) => followUpState(l) === filterFollowUp)
    }
    if (onlyMine) {
      const me = members.find(m => m.email === localStorage.getItem('userEmail'))
      result = result.filter((l) => !!me && l.assigned_user_id === me.id)
    }
    setFilteredLeads(result)
  }, [leads, searchQ, filterStatus, filterScore, onlyMine, members, filterFollowUp])

  // Lead Detail Select & Timeline Fetch
  const handleSelectLead = async (lead: Lead) => {
    setSelectedLead(lead)
    try {
      const fetchedTimeline = await crmApi.getTimeline(lead.id)
      setTimeline(fetchedTimeline)
      
      // Fetch associated call logs for recording player
      const logs = await logsApi.list()
      const matches = logs.filter((log: any) => log.phone_number === lead.phone)
      setCallLogs(matches)
      if (matches.length > 0) {
        handleSelectCall(matches[0])
      } else {
        setActiveCall(null)
        setTranscript('')
      }
    } catch (err) {
      toast.error('Failed to load lead timeline')
    }
  }

  const handleSelectCall = async (call: any) => {
    setActiveCall(call)
    setIsPlaying(false)
    setPlayProgress(0)
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    try {
      const fullTranscript = await logsApi.transcript(call.id)
      setTranscript(fullTranscript || call.transcript || 'No transcript generated yet.')
    } catch {
      setTranscript(call.transcript || 'No transcript generated.')
    }
  }

  // Recording audio toggle using HTML5 audio element
  const togglePlay = () => {
    if (!audioRef.current) return
    if (isPlaying) {
      audioRef.current.pause()
    } else {
      audioRef.current.play().catch((e) => console.error('Audio playback error:', e))
    }
  }

  // Create lead handler
  const handleCreateLead = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newLeadData.name || !newLeadData.phone) {
      toast.error('Name and Phone are required')
      return
    }
    try {
      await crmApi.createLead(newLeadData)
      toast.success('New lead created successfully!')
      setIsCreateOpen(false)
      loadData()
    } catch (err: any) {
      toast.error(err.message || 'Failed to create lead')
    }
  }

  const handleCardDrop = async (leadId: string, newStatus: LeadStatus) => {
    const targetLead = leads.find((l) => l.id === leadId)
    if (!targetLead) return
    if (targetLead.status === newStatus) return
    await handleStatusChange(targetLead, newStatus)
  }

  // Update lead status handler
  const handleStatusChange = async (lead: Lead, status: LeadStatus) => {
    if (role === 'Agent' && (status === 'Converted' || status === 'Lost')) {
      toast.error('Agent role lacks permissions to close/convert leads')
      return
    }
    try {
      const updated = { ...lead, status }
      // The server records the stage change on the lead's timeline.
      const saved = await crmApi.updateLead(lead.id, updated)
      toast.success(`Pipeline status updated: ${status}`)
      loadData()
      if (selectedLead?.id === lead.id) {
        handleSelectLead(saved)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update pipeline stage')
    }
  }

  // Save full lead updates
  const handleSaveLeadDetails = async () => {
    if (!selectedLead) return
    try {
      await crmApi.updateLead(selectedLead.id, selectedLead)
      toast.success('Lead details saved!')
      loadData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save lead updates')
    }
  }

  // Delete lead handler
  const handleDeleteLead = async (leadId: string) => {
    if (role === 'Agent' || role === 'Manager') {
      toast.error('Role does not have permission to delete leads')
      return
    }
    if (!confirm('Are you sure you want to delete this lead?')) return
    try {
      const res = await crmApi.deleteLead(leadId)
      if (res.success) {
        toast.success('Lead deleted successfully')
        setSelectedLead(null)
        loadData()
      }
    } catch {
      toast.error('Failed to delete lead')
    }
  }

  // Lead auto AI Scoring
  const handleAIScoreLead = async () => {
    if (!selectedLead) return
    setScoringLoading(true)
    try {
      const res = await crmApi.scoreLead(selectedLead.id, selectedLead)
      if (res.status === 'ok') {
        const updated = {
          ...selectedLead,
          score: res.score as LeadScore,
          score_explanation: res.explanation,
        }
        await crmApi.updateLead(selectedLead.id, updated)
        toast.success(`AI Lead Score: ${res.score}`)
        
        await crmApi.addTimeline(selectedLead.id, {
          activity_type: 'crm_update',
          title: 'AI Lead Scored',
          description: `Classified as ${res.score}. Explanation: ${res.explanation}`,
        })
        
        handleSelectLead(updated)
        loadData()
      }
    } catch {
      toast.error('AI lead scoring failed')
    } finally {
      setScoringLoading(false)
    }
  }

  // Write timeline notes handler
  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedLead || !newNote.trim()) return
    try {
      const res = await crmApi.addTimeline(selectedLead.id, {
        activity_type: 'note',
        title: 'Counselor Note added',
        description: newNote,
      })
      if (res.status === 'ok') {
        toast.success('Note added to timeline')
        setNewNote('')
        const timelineList = await crmApi.getTimeline(selectedLead.id)
        setTimeline(timelineList)
      }
    } catch {
      toast.error('Failed to add note')
    }
  }

  // Workflow automation toggle
  const handleToggleWorkflow = async (wf: Workflow) => {
    if (role === 'Agent' || role === 'Manager') {
      toast.error('You do not have permissions to modify workflows')
      return
    }
    try {
      const updated = { ...wf, is_active: !wf.is_active }
      const res = await crmApi.createWorkflow(updated)
      if (res.status === 'ok') {
        toast.success(`Workflow '${wf.name}' ${updated.is_active ? 'Activated' : 'Deactivated'}`)
        loadData()
      }
    } catch {
      toast.error('Failed to toggle workflow')
    }
  }

  // Export filtered lead data to CSV
  const handleImport = async (file: File) => {
    setImporting(true)
    try {
      const result = await crmApi.importLeads(file)
      setImportResult(result)
      if (result.created) loadData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  const handleExportCSV = () => {
    if (role === 'Agent') {
      toast.error('Agent role does not have permission to export lead database')
      return
    }
    // Column names match what Import CSV accepts, so an export can be re-imported.
    const headers = csvRow(['Name', 'Phone', 'Email', 'Company', 'Status', 'Score', 'Follow up', 'Assigned to', 'Notes',
      'Qualifier score', 'Rank', 'Budget', 'Parent Involved', 'Country Preference', ...leadFields.map(f => f.label)])
    const rows = filteredLeads.map(l => csvRow([
      l.name, l.phone, l.email, l.company, l.status, l.score, l.follow_up_date, l.assigned_agent, l.notes,
      l.neet_score, l.rank, l.budget, l.parent_involved ? 'Yes' : 'No', l.country_preference,
      ...leadFields.map(f => {
        const v = l.custom_fields?.[f.key]
        return typeof v === 'boolean' ? (v ? 'Yes' : 'No') : v
      }),
    ]))

    const blob = new Blob([[headers, ...rows].join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.setAttribute('href', url)
    link.setAttribute('download', `avn_leads_${new Date().toISOString().split('T')[0]}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    toast.success('Filtered leads database exported as CSV!')
  }

  // Place a real AI call to the lead (counts toward the per-user hourly call limit).
  const handleInitiateCall = async (phone: string, name: string) => {
    const pending = toast.loading(`Calling ${name}…`)
    try {
      const result = await callsApi.single(phone, name)
      toast.success(`Call placed${result.room ? ` (room ${result.room})` : ''}`, { id: pending })
      loadData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Unable to place the call', { id: pending })
    }
  }

  return (
    <div className="page-wrapper" style={{ padding: '24px 32px' }}>
      {/* ── Page Header ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 24,
      }}>
        <div>
          <div style={{
            fontFamily: 'Satoshi, Inter, sans-serif',
            fontSize: 26,
            fontWeight: 700,
            letterSpacing: '-0.03em',
            background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #9580FF)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}>
            <Users size={24} color="#7B61FF" />
            {workspaceName ? `${workspaceName} · ${t.crm}` : t.crm}
          </div>
          <p style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 4 }}>
            Lead pipeline · Automations · Role: {role}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {role !== 'Agent' && (
            <button onClick={handleExportCSV} className="avn-btn avn-btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, height: 38 }}>
              <Download size={14} />
              {t.exportCsv}
            </button>
          )}
          {(role === 'Owner' || role === 'Admin' || role === 'Manager') && (
            <button onClick={() => { setImportResult(null); setImportOpen(true) }} className="avn-btn avn-btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, height: 38 }}>
              <Upload size={14} />
              Import CSV
            </button>
          )}
          <button onClick={() => setIsCreateOpen(true)} className="avn-btn avn-btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, height: 38 }}>
            <Plus size={15} />
            {t.addLead}
          </button>
        </div>
      </div>

      {/* ── Tabs & Filters ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
        marginBottom: 20,
        gap: 16,
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', gap: 24 }}>
          <button
            onClick={() => setActiveTab('pipeline')}
            style={{
              padding: '12px 4px',
              borderBottom: `2px solid ${activeTab === 'pipeline' ? '#7B61FF' : 'transparent'}`,
              color: activeTab === 'pipeline' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
              background: 'transparent',
              borderLeft: 'none',
              borderRight: 'none',
              borderTop: 'none',
              fontSize: 14,
              fontWeight: activeTab === 'pipeline' ? 600 : 400,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              transition: 'all 0.15s',
            }}
          >
            <KanbanSquare size={15} />
            {t.pipeline}
          </button>
          <button
            onClick={() => setActiveTab('list')}
            style={{
              padding: '12px 4px',
              borderBottom: `2px solid ${activeTab === 'list' ? '#7B61FF' : 'transparent'}`,
              color: activeTab === 'list' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
              background: 'transparent',
              borderLeft: 'none',
              borderRight: 'none',
              borderTop: 'none',
              fontSize: 14,
              fontWeight: activeTab === 'list' ? 600 : 400,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              transition: 'all 0.15s',
            }}
          >
            <ListFilter size={15} />
            {t.listView}
          </button>
          <button
            onClick={() => setActiveTab('workflows')}
            style={{
              padding: '12px 4px',
              borderBottom: `2px solid ${activeTab === 'workflows' ? '#7B61FF' : 'transparent'}`,
              color: activeTab === 'workflows' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
              background: 'transparent',
              borderLeft: 'none',
              borderRight: 'none',
              borderTop: 'none',
              fontSize: 14,
              fontWeight: activeTab === 'workflows' ? 600 : 400,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              transition: 'all 0.15s',
            }}
          >
            <Zap size={15} />
            {t.workflows}
          </button>
        </div>

        {/* Filters Panel */}
        {activeTab !== 'workflows' && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
            <input
              type="text"
              placeholder={t.searchPlaceholder}
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              className="avn-input"
              style={{ width: 220, height: 34, fontSize: 12.5 }}
            />
            <select aria-label="Filter by stage"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="avn-input"
              style={{ width: 110, height: 34, padding: '0 8px', fontSize: 12.5 }}
            >
              <option value="All">Stage: All</option>
              {statusOptions.map((st) => (
                <option key={st} value={st}>{t[st.toLowerCase() as keyof typeof t] || st}</option>
              ))}
            </select>
            <select aria-label="Filter by score"
              value={filterScore}
              onChange={(e) => setFilterScore(e.target.value)}
              className="avn-input"
              style={{ width: 110, height: 34, padding: '0 8px', fontSize: 12.5 }}
            >
              <option value="All">Score: All</option>
              <option value="Hot">{t.hot}</option>
              <option value="Warm">{t.warm}</option>
              <option value="Cold">{t.cold}</option>
            </select>
            <select aria-label="Filter by follow-up"
              value={filterFollowUp}
              onChange={(e) => setFilterFollowUp(e.target.value as typeof filterFollowUp)}
              className="avn-input"
              style={{ width: 150, height: 34, padding: '0 8px', fontSize: 12.5 }}
            >
              <option value="All">Follow-up: All</option>
              <option value="overdue">Follow-up overdue</option>
              <option value="today">Follow-up today</option>
              <option value="upcoming">Follow-up upcoming</option>
            </select>
            <button
              onClick={() => setOnlyMine(v => !v)}
              aria-pressed={onlyMine}
              className="avn-input"
              style={{ height: 34, padding: '0 12px', fontSize: 12.5, cursor: 'pointer', width: 'auto',
                background: onlyMine ? 'rgba(123,97,255,0.18)' : undefined, color: onlyMine ? '#9580FF' : undefined }}
            >
              Assigned to me
            </button>
          </div>
        )}
      </div>

      {/* ── Tab Content ── */}
      <div style={{ position: 'relative' }}>
        {/* 1. Kanban Pipeline Board */}
        {activeTab === 'pipeline' && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(6, 1fr)',
            gap: 12,
            overflowX: 'auto',
            alignItems: 'start',
            minHeight: '60vh',
            paddingBottom: 24,
          }}>
            {statusOptions.map((status) => {
              const statusLeads = filteredLeads.filter((l) => l.status === status)
              return (
                <div
                  key={status}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    const leadId = e.dataTransfer.getData('text/plain')
                    handleCardDrop(leadId, status)
                  }}
                  style={{
                    background: 'var(--color-bg-card)',
                    border: '1px solid rgba(255,255,255,0.03)',
                    borderRadius: 14,
                    padding: 10,
                    minWidth: 160,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                  }}
                >
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '4px 6px',
                    borderBottom: '1px solid rgba(255,255,255,0.04)',
                    marginBottom: 4,
                  }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      {t[status.toLowerCase() as keyof typeof t] || status}
                    </span>
                    <span style={{ fontSize: 11, background: 'rgba(255,255,255,0.05)', color: 'var(--color-text-muted)', padding: '1px 6px', borderRadius: 4, fontWeight: 600 }}>
                      {statusLeads.length}
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '65vh', overflowY: 'auto' }}>
                    {statusLeads.map((lead) => (
                      <div
                        key={lead.id}
                        onClick={() => handleSelectLead(lead)}
                        draggable
                        onDragStart={(e) => e.dataTransfer.setData('text/plain', lead.id)}
                        style={{
                          background: 'var(--color-bg-card)',
                          border: `1px solid ${selectedLead?.id === lead.id ? 'rgba(123,97,255,0.4)' : 'rgba(255,255,255,0.05)'}`,
                          borderRadius: 10,
                          padding: 12,
                          cursor: 'pointer',
                          transition: 'all 0.15s',
                          boxShadow: selectedLead?.id === lead.id ? '0 0 12px rgba(123,97,255,0.2)' : 'none',
                        }}
                        onMouseOver={(e) => {
                          if (selectedLead?.id !== lead.id) e.currentTarget.style.border = '1px solid rgba(255,255,255,0.1)'
                        }}
                        onMouseOut={(e) => {
                          if (selectedLead?.id !== lead.id) e.currentTarget.style.border = '1px solid rgba(255,255,255,0.05)'
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: 6,
                            fontSize: 9.5,
                            fontWeight: 700,
                            letterSpacing: '0.05em',
                            textTransform: 'uppercase',
                            background: scoreColors[lead.score] || '#0E1420',
                            color: scoreTextColors[lead.score] || 'var(--color-text-primary)',
                          }}>
                            {t[lead.score.toLowerCase() as keyof typeof t] || lead.score}
                          </span>
                          <span style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                            Score: {lead.neet_score || 'N/A'}
                          </span>
                        </div>

                        <h4 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
                          {lead.name}
                          {/* Sentiment indicator dot */}
                          <span style={{
                            width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                            background: lead.score === 'Hot' ? '#22D3A5' : lead.score === 'Warm' ? '#F5A623' : 'var(--color-text-muted)',
                            boxShadow: lead.score === 'Hot' ? '0 0 6px rgba(34,211,165,0.6)' : 'none',
                          }} />
                        </h4>
                        <p style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{lead.company}</p>
                        {followUpState(lead) === 'overdue' && (
                          <span style={{ display: 'inline-block', fontSize: 10, fontWeight: 700, color: '#FF4D6A', background: 'rgba(255,77,106,0.1)', borderRadius: 4, padding: '1px 6px', marginBottom: 4 }}>
                            Follow-up overdue · {lead.follow_up_date}
                          </span>
                        )}
                        {followUpState(lead) === 'today' && (
                          <span style={{ display: 'inline-block', fontSize: 10, fontWeight: 700, color: '#F5A623', background: 'rgba(245,166,35,0.1)', borderRadius: 4, padding: '1px 6px', marginBottom: 4 }}>
                            Follow up today
                          </span>
                        )}

                        {/* Mini transcript snippet */}
                        {lead.notes && (
                          <p style={{
                            fontSize: 10, color: 'var(--color-text-muted)', fontStyle: 'italic',
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            maxWidth: '100%', marginBottom: 4,
                          }}>
                            "{lead.notes.slice(0, 60)}{lead.notes.length > 60 ? '…' : ''}"
                          </p>
                        )}

                        {/* Last interaction + assigned agent */}
                        <div style={{
                          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6,
                          fontSize: 10, color: 'var(--color-text-muted)',
                        }}>
                          <Clock size={9} />
                          <span>{lead.updated_at ? formatDistanceToNow(new Date(lead.updated_at), { addSuffix: true }) : 'No activity'}</span>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.03)' }}>
                          <span style={{ fontSize: 10, color: '#9580FF', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <GraduationCap size={10} />
                            {lead.country_preference || 'Global'}
                          </span>
                          
                          {/* Mini Dial Button */}
                          <button aria-label={`Call ${lead.name}`}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleInitiateCall(lead.phone, lead.name)
                            }}
                            style={{
                              width: 20,
                              height: 20,
                              borderRadius: 4,
                              background: 'rgba(34,211,165,0.1)',
                              border: 'none',
                              color: '#22D3A5',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              cursor: 'pointer',
                              transition: 'all 0.15s',
                            }}
                            onMouseOver={e => e.currentTarget.style.background = 'rgba(34,211,165,0.2)'}
                            onMouseOut={e => e.currentTarget.style.background = 'rgba(34,211,165,0.1)'}
                          >
                            <Phone size={10} />
                          </button>
                        </div>
                      </div>
                    ))}
                    {statusLeads.length === 0 && (
                      <div style={{ textAlign: 'center', padding: '24px 8px', color: 'var(--color-text-muted)', fontSize: 11 }}>
                        Drag leads here
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* 2. Grid Table View */}
        {activeTab === 'list' && (
          <div style={{ background: 'var(--color-bg-card)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 14, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 13 }}>
              <thead>
                <tr style={{ background: 'rgba(7,11,20,0.6)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <th style={{ padding: '12px 18px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{t.name}</th>
                  <th style={{ padding: '12px 18px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{t.phone}</th>
                  <th style={{ padding: '12px 18px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{t.status}</th>
                  <th style={{ padding: '12px 18px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{t.score}</th>
                  <th style={{ padding: '12px 18px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{t.neet}</th>
                  <th style={{ padding: '12px 18px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{t.budget}</th>
                  <th style={{ padding: '12px 18px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{t.countryPref}</th>
                  <th style={{ padding: '12px 18px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{t.actions}</th>
                </tr>
              </thead>
              <tbody>
                {filteredLeads.map((lead) => (
                  <tr
                    key={lead.id}
                    onClick={() => handleSelectLead(lead)}
                    style={{
                      borderBottom: '1px solid rgba(255,255,255,0.03)',
                      cursor: 'pointer',
                      background: selectedLead?.id === lead.id ? 'rgba(123,97,255,0.05)' : 'transparent',
                      transition: 'all 0.15s',
                    }}
                    onMouseOver={e => { if (selectedLead?.id !== lead.id) e.currentTarget.style.background = 'rgba(255,255,255,0.02)' }}
                    onMouseOut={e => { if (selectedLead?.id !== lead.id) e.currentTarget.style.background = 'transparent' }}
                  >
                    <td style={{ padding: '12px 18px', fontWeight: 600, color: 'var(--color-text-primary)' }}>{lead.name}</td>
                    <td style={{ padding: '12px 18px', color: 'var(--color-text-secondary)' }}>{lead.phone}</td>
                    <td style={{ padding: '12px 18px' }}>
                      <select aria-label={`Stage for ${lead.name}`}
                        value={lead.status}
                        onChange={(e) => handleStatusChange(lead, e.target.value as LeadStatus)}
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          background: 'var(--color-bg-card)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          borderRadius: 8,
                          color: 'var(--color-text-primary)',
                          fontSize: 12,
                          padding: '3px 8px',
                          outline: 'none',
                          cursor: 'pointer',
                        }}
                      >
                        {statusOptions.map((st) => (
                          <option key={st} value={st}>{t[st.toLowerCase() as keyof typeof t] || st}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ padding: '12px 18px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 6,
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: '0.03em',
                        background: scoreColors[lead.score],
                        color: scoreTextColors[lead.score],
                      }}>
                        {t[lead.score.toLowerCase() as keyof typeof t] || lead.score}
                      </span>
                    </td>
                    <td style={{ padding: '12px 18px', color: 'var(--color-text-secondary)' }}>{lead.neet_score || 'N/A'}</td>
                    <td style={{ padding: '12px 18px', color: 'var(--color-text-secondary)' }}>{lead.budget || 'N/A'}</td>
                    <td style={{ padding: '12px 18px', color: '#9580FF', display: 'flex', alignItems: 'center', gap: 6, height: 42 }}>
                      <GraduationCap size={13} />
                      {lead.country_preference || 'Global'}
                    </td>
                    <td style={{ padding: '12px 18px' }} onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          onClick={() => handleInitiateCall(lead.phone, lead.name)}
                          style={{
                            padding: '4px 8px',
                            background: 'rgba(34,211,165,0.12)',
                            color: '#22D3A5',
                            border: '1px solid rgba(34,211,165,0.2)',
                            borderRadius: 6,
                            cursor: 'pointer',
                            fontSize: 11,
                          }}
                        >
                          Call
                        </button>
                        {role === 'Admin' && (
                          <button aria-label={`Delete ${lead.name}`}
                            onClick={() => handleDeleteLead(lead.id)}
                            style={{
                              padding: '4px 6px',
                              background: 'rgba(255,77,106,0.08)',
                              color: '#FF4D6A',
                              border: '1px solid rgba(255,77,106,0.15)',
                              borderRadius: 6,
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                            }}
                          >
                            <Trash2 size={12} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {filteredLeads.length === 0 && (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'center', padding: 48, color: 'var(--color-text-muted)' }}>
                      {t.noLeads}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* 3. Workflow Automations Tab */}
        {activeTab === 'workflows' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
            {workflows.map((wf) => (
              <div
                key={wf.id}
                style={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid rgba(123,97,255,0.15)',
                  borderRadius: 14,
                  padding: 20,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 16,
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                <div style={{ position: 'absolute', top: -30, right: -30, width: 80, height: 80, borderRadius: '50%', background: wf.is_active ? 'rgba(34,211,165,0.05)' : 'transparent', filter: 'blur(30px)' }} />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                  <div>
                    <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: 4 }}>{wf.name}</h3>
                    <span style={{ fontSize: 11, background: 'rgba(123,97,255,0.1)', color: '#9580FF', padding: '2px 8px', borderRadius: 6, fontWeight: 600 }}>
                      Trigger: {wf.trigger_event}
                    </span>
                  </div>
                  
                  {/* Toggle Switch */}
                  <button role="switch" aria-checked={wf.is_active} aria-label={`${wf.name} active`}
                    onClick={() => handleToggleWorkflow(wf)}
                    disabled={role === 'Agent' || role === 'Manager'}
                    style={{
                      width: 44,
                      height: 24,
                      borderRadius: 100,
                      background: wf.is_active ? '#22D3A5' : 'rgba(255,255,255,0.1)',
                      border: 'none',
                      position: 'relative',
                      cursor: (role === 'Agent' || role === 'Manager') ? 'not-allowed' : 'pointer',
                      transition: 'all 0.2s',
                    }}
                  >
                    <div style={{
                      width: 18,
                      height: 18,
                      borderRadius: '50%',
                      background: 'var(--color-bg-card)',
                      position: 'absolute',
                      top: 3,
                      left: wf.is_active ? 23 : 3,
                      transition: 'all 0.2s',
                    }} />
                  </button>
                </div>

                <div style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: 12 }}>
                  <span style={{ fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Actions Chain</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
                    {wf.actions.map((act, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          background: 'rgba(255,255,255,0.02)',
                          border: '1px solid rgba(255,255,255,0.04)',
                          borderRadius: 8,
                          padding: '8px 12px',
                        }}
                      >
                        <div style={{ fontSize: 11, background: 'rgba(123,97,255,0.15)', color: '#9580FF', width: 20, height: 20, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, paddingLeft: 6 }}>
                          {idx + 1}
                        </div>
                        <div>
                          <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--color-text-primary)', textTransform: 'capitalize' }}>
                            {act.type === 'ai_call' ? '📞 Auto AI Voice Call' : act.type === 'whatsapp' ? '💬 WhatsApp Dispatch' : act.type === 'reminder' ? '📅 Schedule CRM Task' : '✏️ Update Lead Field'}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                            {JSON.stringify(act.config)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── LEAD DETAIL SLIDING PANEL DRAWER ──────────────────────────────── */}
      {selectedLead && (
        <div style={{
          position: 'fixed',
          top: 0,
          right: 0,
          width: '580px',
          height: '100vh',
          background: 'var(--color-bg-card)',
          borderLeft: '1px solid rgba(123,97,255,0.25)',
          boxShadow: '-10px 0 40px rgba(0,0,0,0.6)',
          zIndex: 100,
          display: 'flex',
          flexDirection: 'column',
          animation: 'slideIn 0.3s cubic-bezier(0.22,1,0.36,1) both',
          backdropFilter: 'blur(20px)',
        }}>
          {/* Drawer Header */}
          <div style={{
            padding: '20px 24px',
            borderBottom: '1px solid rgba(255,255,255,0.05)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'rgba(7,11,20,0.5)',
          }}>
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text-primary)' }}>{selectedLead.name}</h2>
              <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Registered: {new Date(selectedLead.created_at).toLocaleString()}</span>
            </div>
            
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={handleAIScoreLead}
                disabled={scoringLoading}
                className="avn-btn avn-btn-secondary"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  height: 32,
                  fontSize: 11.5,
                  background: 'rgba(123,97,255,0.12)',
                  borderColor: 'rgba(123,97,255,0.25)',
                  color: '#9580FF',
                }}
              >
                {scoringLoading ? 'Scoring...' : '🤖 AI Lead Score'}
              </button>
              <button onClick={() => setSelectedLead(null)} style={{ background: 'transparent', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: 18, padding: 4 }}>×</button>
            </div>
          </div>

          {/* Drawer Body Scroll */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
            
            {/* AI SCORE ANALYSIS CARD */}
            {selectedLead.score_explanation && (
              <div style={{
                background: 'linear-gradient(135deg, rgba(123,97,255,0.06), rgba(94,230,255,0.02))',
                border: '1px solid rgba(123,97,255,0.15)',
                borderRadius: 12,
                padding: 16,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <Award size={14} color="#7B61FF" />
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#9580FF', textTransform: 'uppercase', letterSpacing: '0.05em' }}>AI Scoring Analysis</span>
                </div>
                <p style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>{selectedLead.score_explanation}</p>
              </div>
            )}

            {/* GENERAL DETAILS FORM */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.email}</label>
                <input
                  type="email"
                  value={selectedLead.email || ''}
                  onChange={(e) => setSelectedLead({ ...selectedLead, email: e.target.value })}
                  className="avn-input"
                  style={{ height: 34, fontSize: 12.5 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.phone}</label>
                <input
                  type="text"
                  value={selectedLead.phone}
                  onChange={(e) => setSelectedLead({ ...selectedLead, phone: e.target.value })}
                  className="avn-input"
                  style={{ height: 34, fontSize: 12.5 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.neet}</label>
                <input
                  type="number"
                  value={selectedLead.neet_score || ''}
                  onChange={(e) => setSelectedLead({ ...selectedLead, neet_score: e.target.value ? Number(e.target.value) : undefined })}
                  className="avn-input"
                  style={{ height: 34, fontSize: 12.5 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.rank}</label>
                <input
                  type="number"
                  value={selectedLead.rank || ''}
                  onChange={(e) => setSelectedLead({ ...selectedLead, rank: e.target.value ? Number(e.target.value) : undefined })}
                  className="avn-input"
                  style={{ height: 34, fontSize: 12.5 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.budget}</label>
                <input
                  value={selectedLead.budget || ''}
                  onChange={(e) => setSelectedLead({ ...selectedLead, budget: e.target.value })}
                  className="avn-input"
                  style={{ height: 34, fontSize: 12.5 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.parentInvolved}</label>
                <select aria-label={t.parentInvolved}
                  value={selectedLead.parent_involved ? 'Yes' : 'No'}
                  onChange={(e) => setSelectedLead({ ...selectedLead, parent_involved: e.target.value === 'Yes' })}
                  className="avn-input"
                  style={{ height: 34, padding: '0 8px', fontSize: 12.5 }}
                >
                  <option value="Yes">Yes</option>
                  <option value="No">No</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.countryPref}</label>
                <input
                  value={selectedLead.country_preference || ''}
                  onChange={(e) => setSelectedLead({ ...selectedLead, country_preference: e.target.value })}
                  className="avn-input"
                  style={{ height: 34, fontSize: 12.5 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.assigned}</label>
                <select aria-label={t.assigned}
                  value={selectedLead.assigned_user_id || ''}
                  onChange={(e) => setSelectedLead({ ...selectedLead, assigned_user_id: e.target.value || null })}
                  className="avn-input"
                  style={{ height: 34, padding: '0 8px', fontSize: 12.5 }}
                >
                  <option value="">Unassigned</option>
                  {members.filter(m => m.status === 'active').map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
              </div>
            </div>

            <CustomFieldInputs fields={leadFields} values={selectedLead.custom_fields}
              onChange={custom_fields => setSelectedLead({ ...selectedLead, custom_fields })} />

            <div>
              <label htmlFor="lead-follow-up" style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>Follow-up date</label>
              <input
                id="lead-follow-up"
                type="date"
                value={selectedLead.follow_up_date || ''}
                onChange={(e) => setSelectedLead({ ...selectedLead, follow_up_date: e.target.value || undefined })}
                className="avn-input"
                style={{ height: 34, fontSize: 12.5 }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{t.notes}</label>
              <textarea
                value={selectedLead.notes || ''}
                onChange={(e) => setSelectedLead({ ...selectedLead, notes: e.target.value })}
                className="avn-input"
                style={{ height: 60, fontSize: 12.5, padding: '8px 12px', resize: 'none' }}
              />
            </div>

            <div style={{ display: 'flex', gap: 10, borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 16 }}>
              <button onClick={handleSaveLeadDetails} className="avn-btn avn-btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, height: 36, fontSize: 13 }}>
                <Save size={14} />
                {t.save}
              </button>
              {role === 'Admin' && (
                <button onClick={() => handleDeleteLead(selectedLead.id)} className="avn-btn avn-btn-secondary" style={{ background: 'rgba(255,77,106,0.12)', borderColor: 'rgba(255,77,106,0.2)', color: '#FF4D6A', display: 'flex', alignItems: 'center', gap: 6, height: 36, fontSize: 13 }}>
                  <Trash2 size={14} />
                  {t.delete}
                </button>
              )}
            </div>

            {/* RECORDING PLAYER WITH TRANSCRIPT AND NOTES */}
            {callLogs.length > 0 && (
              <div style={{
                background: 'var(--color-bg-card)',
                border: '1px solid rgba(123,97,255,0.2)',
                borderRadius: 14,
                padding: 16,
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Play size={14} color="#22D3A5" />
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{t.recordingPlayer}</span>
                  </div>
                  <span style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Found {callLogs.length} calls</span>
                </div>

                {/* Call Log selector */}
                <select aria-label="Call recording"
                  value={activeCall?.id || ''}
                  onChange={(e) => {
                    const match = callLogs.find((c) => String(c.id) === e.target.value)
                    if (match) handleSelectCall(match)
                  }}
                  className="avn-input"
                  style={{ height: 32, padding: '0 8px', fontSize: 11.5 }}
                >
                  {callLogs.map((log) => (
                    <option key={log.id} value={log.id}>
                      Call {new Date(log.created_at).toLocaleDateString()} ({log.duration_seconds}s)
                    </option>
                  ))}
                </select>

                {activeCall && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {/* Controls */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: 'rgba(255,255,255,0.02)', padding: 10, borderRadius: 10 }}>
                      <audio
                        ref={audioRef}
                        src={activeCall.recording_url ? apiUrl(activeCall.recording_url) : undefined}
                        onPlay={() => setIsPlaying(true)}
                        onPause={() => setIsPlaying(false)}
                        onEnded={() => {
                          setIsPlaying(false)
                          setPlayProgress(0)
                        }}
                        onTimeUpdate={(e) => {
                          const aud = e.currentTarget
                          if (aud.duration) {
                            setPlayProgress((aud.currentTime / aud.duration) * 100)
                          }
                        }}
                        style={{ display: 'none' }}
                      />
                      <button
                        onClick={togglePlay}
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: '50%',
                          background: '#7B61FF',
                          border: 'none',
                          color: '#fff',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          cursor: 'pointer',
                          boxShadow: '0 0 10px rgba(123,97,255,0.4)',
                        }}
                      >
                        {isPlaying ? <Pause size={12} fill="#fff" /> : <Play size={12} fill="#fff" style={{ marginLeft: 2 }} />}
                      </button>

                      {/* Slider timeline */}
                      <div style={{ flex: 1, height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 2, position: 'relative' }}>
                        <div style={{ width: `${playProgress}%`, height: '100%', background: '#22D3A5', borderRadius: 2 }} />
                      </div>

                      {/* Simulated wave animation */}
                      {isPlaying && (
                        <div style={{ display: 'flex', gap: 2, alignItems: 'center', height: 16 }}>
                          {[4, 12, 8, 16, 10, 6].map((h, i) => (
                            <div
                              key={i}
                              style={{
                                width: 2,
                                height: h,
                                background: '#22D3A5',
                                borderRadius: 1,
                                animation: 'avn-wave 0.5s ease infinite alternate',
                                animationDelay: `${i * 0.1}s`,
                              }}
                            />
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Transcripts bubble stream */}
                    <div style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: 10 }}>
                      <span style={{ fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 600, display: 'block', marginBottom: 8 }}>{t.transcription}</span>
                      <div style={{
                        maxHeight: 140,
                        overflowY: 'auto',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 8,
                        background: 'rgba(7,11,20,0.4)',
                        padding: 10,
                        borderRadius: 8,
                        fontSize: 11.5,
                      }}>
                        {transcript.split('\n').map((line, i) => {
                          const isAss = line.toLowerCase().startsWith('assistant:') || line.toLowerCase().startsWith('ai:')
                          const clean = line.replace(/^(assistant|user|ai):/i, '').trim()
                          if (!clean) return null
                          return (
                            <div
                              key={i}
                              style={{
                                alignSelf: isAss ? 'flex-start' : 'flex-end',
                                background: isAss ? 'rgba(123,97,255,0.1)' : 'rgba(255,255,255,0.05)',
                                color: isAss ? '#C0B3FF' : '#E2E8F0',
                                padding: '6px 10px',
                                borderRadius: 8,
                                maxWidth: '80%',
                              }}
                            >
                              {clean}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            <LeadWhatsApp leadId={selectedLead.id} onSent={() => { crmApi.getTimeline(selectedLead.id).then(setTimeline).catch(() => {}) }} />

            {/* TIMELINE ACTIVITIES FEED */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Activity size={15} color="#22D3A5" />
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{t.timeline}</span>
              </div>

              {/* Add Custom note form */}
              <form onSubmit={handleAddNote} style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  placeholder="Write a custom activity note..."
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                  className="avn-input"
                  style={{ height: 32, fontSize: 12 }}
                />
                <button type="submit" className="avn-btn avn-btn-primary" style={{ padding: '0 12px', height: 32, fontSize: 12 }}>
                  Add Note
                </button>
              </form>

              {/* Feed items */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingLeft: 10, borderLeft: '1px solid rgba(255,255,255,0.05)', marginTop: 8 }}>
                {timeline.map((act) => (
                  <div key={act.id} style={{ position: 'relative', paddingLeft: 14 }}>
                    {/* Ring Dot */}
                    <div style={{
                      position: 'absolute',
                      left: -15,
                      top: 4,
                      width: 9,
                      height: 9,
                      borderRadius: '50%',
                      background: act.activity_type === 'call' ? '#22D3A5' : act.activity_type === 'whatsapp' ? '#38BDF8' : '#7B61FF',
                      border: '2.5px solid #070B14',
                    }} />
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                      <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--color-text-primary)' }}>{act.title}</span>
                      <span style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                        {new Date(act.created_at).toLocaleDateString()} {new Date(act.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <p style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{act.description}</p>
                  </div>
                ))}
                {timeline.length === 0 && (
                  <div style={{ color: 'var(--color-text-muted)', fontSize: 12, paddingLeft: 4 }}>No timeline actions logged yet.</div>
                )}
              </div>
            </div>

          </div>
        </div>
      )}

      {/* ── CREATE LEAD DIALOG MODAL ────────────────────────────────────── */}
      <Modal open={importOpen} onClose={() => setImportOpen(false)} title="Import leads from CSV" width={520}>
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
            The first row must be a header with <strong>name</strong> and <strong>phone</strong> columns (phone with country code).
            Optional: email, company, status, notes, follow up (YYYY-MM-DD). Numbers that are already leads are skipped.
            Imported leads do not trigger workflows. Up to 5,000 rows or 2 MB.
          </div>
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={importing}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleImport(f); e.target.value = '' }}
            className="avn-input"
            style={{ padding: 8 }}
          />
          {importing && <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>Importing…</div>}
          {importResult && (
            <div style={{ fontSize: 13, color: 'var(--color-text-primary)' }}>
              <div style={{ marginBottom: 8 }}><strong>{importResult.created}</strong> leads created, <strong>{importResult.skipped_count}</strong> rows skipped.</div>
              {importResult.skipped.length > 0 && (
                <div style={{ maxHeight: 180, overflowY: 'auto', fontSize: 12, color: 'var(--color-text-muted)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '8px 10px' }}>
                  {importResult.skipped.map((row, i) => <div key={i}>Row {row.row}: {row.reason}</div>)}
                </div>
              )}
            </div>
          )}
        </div>
      </Modal>

      {isCreateOpen && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 110,
        }}>
          <div style={{
            background: 'var(--color-bg-card)',
            border: '1px solid rgba(123,97,255,0.2)',
            borderRadius: 18,
            width: 500,
            padding: 24,
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
            animation: 'scaleIn 0.2s cubic-bezier(0.22,1,0.36,1) both',
          }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)' }}>{t.addLead}</h3>
            
            <form onSubmit={handleCreateLead} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{t.name}</label>
                  <input
                    type="text"
                    required
                    value={newLeadData.name}
                    onChange={(e) => setNewLeadData({ ...newLeadData, name: e.target.value })}
                    className="avn-input"
                    style={{ height: 34, fontSize: 12.5 }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{t.phone}</label>
                  <input
                    type="text"
                    required
                    value={newLeadData.phone}
                    onChange={(e) => setNewLeadData({ ...newLeadData, phone: e.target.value })}
                    className="avn-input"
                    style={{ height: 34, fontSize: 12.5 }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{t.neet}</label>
                  <input
                    type="number"
                    value={newLeadData.neet_score || ''}
                    onChange={(e) => setNewLeadData({ ...newLeadData, neet_score: e.target.value ? Number(e.target.value) : undefined })}
                    className="avn-input"
                    style={{ height: 34, fontSize: 12.5 }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{t.budget}</label>
                  <input
                    value={newLeadData.budget || ''}
                    onChange={(e) => setNewLeadData({ ...newLeadData, budget: e.target.value })}
                    className="avn-input"
                    style={{ height: 34, fontSize: 12.5 }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{t.countryPref}</label>
                  <input
                    value={newLeadData.country_preference || ''}
                    onChange={(e) => setNewLeadData({ ...newLeadData, country_preference: e.target.value })}
                    className="avn-input"
                    style={{ height: 34, fontSize: 12.5 }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{t.parentInvolved}</label>
                  <select aria-label={t.parentInvolved}
                    value={newLeadData.parent_involved ? 'Yes' : 'No'}
                    onChange={(e) => setNewLeadData({ ...newLeadData, parent_involved: e.target.value === 'Yes' })}
                    className="avn-input"
                    style={{ height: 34, padding: '0 8px', fontSize: 12.5 }}
                  >
                    <option value="Yes">Yes</option>
                    <option value="No">No</option>
                  </select>
                </div>
              </div>

              <CustomFieldInputs fields={leadFields} values={newLeadData.custom_fields}
                onChange={custom_fields => setNewLeadData({ ...newLeadData, custom_fields })} />

              <div>
                <label htmlFor="new-follow-up" style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>Follow-up date</label>
                <input
                  id="new-follow-up"
                  type="date"
                  value={newLeadData.follow_up_date || ''}
                  onChange={(e) => setNewLeadData({ ...newLeadData, follow_up_date: e.target.value || undefined })}
                  className="avn-input"
                  style={{ height: 34, fontSize: 12.5 }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{t.notes}</label>
                <textarea
                  value={newLeadData.notes}
                  onChange={(e) => setNewLeadData({ ...newLeadData, notes: e.target.value })}
                  className="avn-input"
                  style={{ height: 60, fontSize: 12.5, padding: '8px 12px', resize: 'none' }}
                />
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                <button type="submit" className="avn-btn avn-btn-primary" style={{ flex: 1, height: 36 }}>Save Lead</button>
                <button type="button" onClick={() => setIsCreateOpen(false)} className="avn-btn avn-btn-secondary" style={{ flex: 1, height: 36 }}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
