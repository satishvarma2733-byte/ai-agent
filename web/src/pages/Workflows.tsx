import { useState, useEffect, useRef, type MouseEvent as ReactMouseEvent } from 'react'
import {
  GitBranch, Plus, Play, Pause, Settings2, CheckCircle2, AlertCircle,
  Zap, Mail, Users, Clock, RefreshCw,
  ChevronRight, Eye, Activity, ArrowRight, X, Copy,
  CalendarCheck, Bell, Database, Code, GitMerge, PhoneCall, PhoneMissed, MessageCircle, CalendarClock,
} from 'lucide-react'
import Card from '../components/ui/Card'
import GradientStatCard from '../components/ui/GradientStatCard'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import toast from 'react-hot-toast'
import { crmApi, type WorkflowRun } from '../api/crm'
import { leadFieldsApi } from '../api/leadFields'

// ── Node Types ────────────────────────────────────────────────────
// Only what the workflow engine can actually run (app/services/workflow_engine.py).
const TRIGGER_NODES = [
  { type: 'lead_created', label: 'New Lead', icon: Users, color: '#7B61FF', desc: 'When a lead is added to the CRM' },
  { type: 'lead_status_changed', label: 'Lead Status Changed', icon: GitMerge, color: '#F5A623', desc: 'When a lead moves pipeline stage' },
  { type: 'appointment_booked', label: 'Appointment Booked', icon: CalendarCheck, color: '#5EE6FF', desc: 'When an appointment is booked (the contact becomes a lead if new)' },
  { type: 'appointment_reminder', label: 'Before Appointment', icon: CalendarClock, color: '#5EE6FF', desc: 'A set time before each scheduled appointment; moved appointments are reminded at their new time' },
  { type: 'call_completed', label: 'Call Completed', icon: PhoneCall, color: '#22D3A5', desc: "When a call with a lead's phone ends" },
  { type: 'call_missed', label: 'Missed Call', icon: PhoneMissed, color: '#FF4D6A', desc: 'When an inbound caller hangs up within 15 seconds (creates the lead if new)' },
  { type: 'webhook_received', label: 'Webhook Received', icon: Code, color: '#F5A623', desc: 'When the lead capture webhook receives a lead (Settings → Integrations)' },
]

const ACTION_NODES = [
  { type: 'ai_call', label: 'AI Voice Call', icon: Zap, color: '#7B61FF', desc: 'Call the lead with the AI agent' },
  { type: 'send_email', label: 'Send Email', icon: Mail, color: '#5EE6FF', desc: 'Email the lead (needs an email address)' },
  { type: 'send_whatsapp', label: 'Send WhatsApp', icon: MessageCircle, color: '#22D3A5', desc: 'Message or approved template (Settings → Integrations)' },
  { type: 'update_crm', label: 'Update CRM', icon: Database, color: '#9580FF', desc: 'Set a field on the lead' },
  { type: 'assign_lead', label: 'Assign Lead', icon: Users, color: '#F5A623', desc: 'Assign to a team member' },
  { type: 'create_reminder', label: 'Create Reminder', icon: Bell, color: '#FF4D6A', desc: "Add a reminder to the lead's timeline" },
  { type: 'call_webhook', label: 'Call Webhook', icon: Code, color: '#5EE6FF', desc: 'POST the lead as signed JSON to your URL' },
]

const TRIGGER_TYPES = new Set(TRIGGER_NODES.map(n => n.type))

let nodeSeq = 0
const newNodeId = () => `n${Date.now().toString(36)}${(nodeSeq++).toString(36)}`

// Fit the canvas to its nodes, never zooming in past 1:1 so small flows keep their size
const NODE_W = 150
const NODE_H = 64
function canvasViewBox(nodes: { x: number; y: number }[]) {
  const MIN_W = 900, MIN_H = 420, PAD = 40
  if (nodes.length === 0) return `0 0 ${MIN_W} ${MIN_H}`
  const minX = Math.min(...nodes.map(n => n.x)) - PAD
  const minY = Math.min(...nodes.map(n => n.y)) - PAD
  const contentW = Math.max(...nodes.map(n => n.x)) + NODE_W + PAD - minX
  const contentH = Math.max(...nodes.map(n => n.y)) + NODE_H + PAD - minY
  const w = Math.max(contentW, MIN_W)
  const h = Math.max(contentH, MIN_H)
  return `${minX - (w - contentW) / 2} ${minY - (h - contentH) / 2} ${w} ${h}`
}

const LOGIC_NODES = [
  { type: 'delay', label: 'Wait', icon: Clock, color: 'var(--color-text-secondary)', desc: 'Pause before the next step (max 1 hour)' },
]

// Editable settings per step; the engine reads these keys from each action's config.
const UPDATABLE_FIELDS = ['status', 'score', 'assigned_agent', 'follow_up_date', 'notes', 'objection']
const LEAD_STATUSES = ['New', 'Contacted', 'Follow-up', 'Interested', 'Converted', 'Lost']
type ConfigField = { key: string; label: string; placeholder?: string; options?: string[]; multiline?: boolean }
const CONFIG_FIELDS: Record<string, ConfigField[]> = {
  send_email: [
    { key: 'subject', label: 'Subject', placeholder: 'Following up on your enquiry' },
    { key: 'body', label: 'Message', placeholder: 'Hi, thank you for your interest…', multiline: true },
  ],
  send_whatsapp: [
    { key: 'message', label: 'Message (within 24 h of their last message)', placeholder: 'Hi {{lead.first_name}}, thanks for calling {{workspace.name}}', multiline: true },
    { key: 'template', label: 'Or approved template (Meta name / Twilio HX… SID)', placeholder: 'appointment_confirmation' },
    { key: 'language', label: 'Template language', placeholder: 'en' },
    { key: 'params', label: 'Template values, one per line', placeholder: '{{lead.name}}', multiline: true },
  ],
  update_crm: [
    { key: 'field', label: 'Field', options: UPDATABLE_FIELDS },
    { key: 'value', label: 'New value', placeholder: 'e.g. Contacted' },
  ],
  assign_lead: [{ key: 'agent', label: 'Team member', placeholder: 'Name or email' }],
  create_reminder: [{ key: 'text', label: 'Reminder', placeholder: 'Follow up with lead' }],
  delay: [{ key: 'delay', label: 'Wait (seconds)', placeholder: '60' }],
  call_webhook: [{ key: 'url', label: 'URL (https)', placeholder: 'https://example.com/avn-webhook' }],
}
// How long before the appointment a "Before Appointment" workflow runs (minutes).
const REMINDER_LEAD_TIMES = [
  [15, '15 minutes'], [30, '30 minutes'], [60, '1 hour'], [120, '2 hours'], [180, '3 hours'], [360, '6 hours'],
  [720, '12 hours'], [1440, '1 day'], [2880, '2 days'], [4320, '3 days'], [10080, '1 week'],
] as const
const DEFAULT_REMINDER_MINUTES = 1440

const FIELD_STYLE = {
  width: '100%', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 8, padding: '6px 10px', color: 'var(--color-text-primary)', fontSize: 12, outline: 'none',
} as const

const COMMON_FIELDS: ConfigField[] = [
  { key: 'condition_status', label: 'Only if lead status is', options: ['', ...LEAD_STATUSES] },
]

// ── Template Workflows ────────────────────────────────────────────
const TEMPLATES = [
  {
    id: 't1',
    name: 'New Lead Call',
    desc: 'Call every new lead with the AI agent, then leave a reminder',
    tags: ['sales', 'lead'],
    steps: ['New Lead → AI Voice Call → Create Reminder'],
    color: '#7B61FF',
  },
  {
    id: 't2',
    name: 'Interested Lead Follow-up',
    desc: 'Email and assign leads that move to Interested',
    tags: ['pipeline'],
    steps: ['Lead Status Changed (if Interested) → Send Email → Assign Lead'],
    color: '#F5A623',
  },
  {
    id: 't3',
    name: 'Appointment Confirmation',
    desc: 'Email a confirmation when a booking matches a lead',
    tags: ['appointments'],
    steps: ['Appointment Booked → Send Email → Update CRM (status: Follow-up)'],
    color: '#22D3A5',
  },
]

// ── Workflow Canvas Node ──────────────────────────────────────────
interface WorkflowNode {
  id: string
  type: string
  label: string
  icon: any
  color: string
  x: number
  y: number
  status?: 'success' | 'error' | 'running' | 'pending'
  config?: Record<string, string>
}

const INITIAL_NODES: WorkflowNode[] = [
  { id: 'n1', type: 'lead_created', label: 'New Lead', icon: Users, color: '#7B61FF', x: 60, y: 160 },
  { id: 'n2', type: 'ai_call', label: 'AI Voice Call', icon: Zap, color: '#7B61FF', x: 260, y: 160 },
  { id: 'n3', type: 'create_reminder', label: 'Create Reminder', icon: Bell, color: '#FF4D6A', x: 460, y: 160, config: { text: 'Check how the AI call went' } },
]

const CONNECTIONS = [
  { from: 'n1', to: 'n2' },
  { from: 'n2', to: 'n3' },
]

// ── Canvas Node Component ──────────────────────────────────────────
function CanvasNode({ node, selected, onClick, onMouseDown }: { node: WorkflowNode; selected: boolean; onClick: () => void; onMouseDown: (e: ReactMouseEvent) => void }) {
  const Icon = node.icon
  const statusColors: Record<string, string> = {
    success: '#22D3A5', running: '#7B61FF', error: '#FF4D6A', pending: 'var(--color-text-muted)'
  }
  const statusColor = statusColors[node.status || 'pending']
  const isRunning = node.status === 'running'

  return (
    <g transform={`translate(${node.x},${node.y})`} style={{ cursor: 'grab' }} onClick={onClick} onMouseDown={onMouseDown}>
      {/* Shadow */}
      <rect x={2} y={4} width={150} height={64} rx={12} fill="rgba(0,0,0,0.4)" />
      {/* Card */}
      <rect
        x={0} y={0} width={150} height={64} rx={12}
        fill={selected ? `${node.color}20` : 'var(--color-bg-card)'}
        stroke={selected ? node.color : isRunning ? node.color : 'var(--color-border-strong)'}
        strokeWidth={selected ? 2 : isRunning ? 1.5 : 1}
      />
      {/* Glow if running */}
      {isRunning && (
        <rect x={0} y={0} width={150} height={64} rx={12}
          fill="none" stroke={node.color} strokeWidth={4} opacity={0.15}
        />
      )}
      {/* Icon area */}
      <rect x={10} y={12} width={36} height={36} rx={9}
        fill={`${node.color}18`} stroke={`${node.color}30`} strokeWidth={1}
      />
      <Icon x={19} y={21} size={18} color={node.color} />
      {/* Status dot (only once the node has run) */}
      {node.status && <circle cx={132} cy={14} r={5} fill={statusColor} />}
      {isRunning && <circle cx={132} cy={14} r={8} fill={statusColor} opacity={0.25}>
        <animate attributeName="r" values="5;10;5" dur="1.5s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.25;0;0.25" dur="1.5s" repeatCount="indefinite" />
      </circle>}
      {/* Label */}
      <text x={54} y={30} fill="var(--color-text-primary)" fontSize={12} fontWeight={600} fontFamily="'General Sans', sans-serif">{node.label.slice(0, 14)}{node.label.length > 14 ? '…' : ''}</text>
      <text x={54} y={46} style={{ fill: 'var(--color-text-muted)' }} fontSize={10} fontFamily="'General Sans', sans-serif">{node.type.replace(/_/g, ' ')}</text>
    </g>
  )
}

// ── Connection Arrow ───────────────────────────────────────────────
function Arrow({ from, to, label }: { from: WorkflowNode; to: WorkflowNode; label?: string }) {
  const x1 = from.x + 150
  const y1 = from.y + 32
  const x2 = to.x
  const y2 = to.y + 32
  const mx = (x1 + x2) / 2

  return (
    <g>
      <path
        d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
        fill="none" stroke="rgba(123,97,255,0.3)" strokeWidth={1.5} strokeDasharray={label ? '4,3' : 'none'}
      />
      <polygon points={`${x2},${y2} ${x2 - 8},${y2 - 4} ${x2 - 8},${y2 + 4}`} fill="rgba(123,97,255,0.5)" />
      {label && (
        <text x={(x1 + x2) / 2} y={y2 - 8} fill="#F5A623" fontSize={10} textAnchor="middle" fontFamily="'General Sans', sans-serif" fontWeight={600}>
          {label}
        </text>
      )}
    </g>
  )
}

// ── Node Palette Item ──────────────────────────────────────────────
function PaletteNode({ node, onAdd }: { node: any; onAdd: () => void }) {
  const Icon = node.icon
  return (
    <button
      onClick={onAdd}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', width: '100%',
        background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)',
        borderRadius: 9, cursor: 'pointer', transition: 'all 0.15s', textAlign: 'left',
      }}
      onMouseOver={e => e.currentTarget.style.background = `${node.color}0C`}
      onMouseOut={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
    >
      <div style={{ width: 28, height: 28, borderRadius: 7, background: `${node.color}18`, border: `1px solid ${node.color}28`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon size={13} color={node.color} />
      </div>
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)' }}>{node.label}</div>
        <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)', lineHeight: 1.3 }}>{node.desc}</div>
      </div>
    </button>
  )
}

// ── Main Page ──────────────────────────────────────────────────────
type ViewTab = 'builder' | 'workflows' | 'templates' | 'history'

export default function Workflows() {
  const [tab, setTab] = useState<ViewTab>('workflows')
  const [nodes, setNodes] = useState<WorkflowNode[]>(INITIAL_NODES)
  const [connections, setConnections] = useState<any[]>(CONNECTIONS)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [workflows, setWorkflows] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [showNewModal, setShowNewModal] = useState(false)
  
  // Persistent workflow fields
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string | null>(null)
  const [workflowName, setWorkflowName] = useState('New Lead Call')
  const [triggerEvent, setTriggerEvent] = useState('lead_created')
  const [runs, setRuns] = useState<WorkflowRun[]>([])
  const [customFieldKeys, setCustomFieldKeys] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    leadFieldsApi.list().then(f => { if (!cancelled) setCustomFieldKeys(f.map(x => `custom.${x.key}`)) }).catch(() => {})
    return () => { cancelled = true }
  }, [])
  const [newWfName, setNewWfName] = useState('')

  const loadWorkflows = async () => {
    setIsLoading(true)
    try {
      const res: any = await crmApi.listWorkflows()
      // Map rows
      const rows: any[] = Array.isArray(res) ? res : (res?.data || [])
      const runLists = await Promise.all(rows.map(w => crmApi.listRuns(w.id).catch(() => [] as WorkflowRun[])))
      const allRuns: WorkflowRun[] = []
      const items = rows.map((w: any, i: number) => {
        const wfRuns = runLists[i]
        allRuns.push(...wfRuns.map(r => ({ ...r, workflow_name: w.name })))
        return {
          id: w.id,
          name: w.name,
          status: w.is_active ? 'active' : 'paused',
          runs: wfRuns.length,
          success: wfRuns.filter(r => r.status === 'success').length,
          last: wfRuns[0] ? `Last run ${new Date(wfRuns[0].triggered_at).toLocaleString()}` : 'Never run',
          tags: [TRIGGER_NODES.find(t => t.type === w.trigger_event)?.label ?? w.trigger_event],
          actions: w.actions,
          trigger_event: w.trigger_event
        }
      })
      allRuns.sort((a, b) => b.triggered_at.localeCompare(a.triggered_at))
      setWorkflows(items)
      setRuns(allRuns)
    } catch (err) {
      console.error(err)
      toast.error('Failed to load workflows')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadWorkflows()
  }, [])

  const toggleWorkflow = async (id: string) => {
    const wf = workflows.find(w => w.id === id)
    if (!wf) return
    const newStatus = wf.status === 'active' ? 'paused' : 'active'
    try {
      await crmApi.updateWorkflow(id, {
        name: wf.name,
        trigger_event: wf.trigger_event,
        is_active: newStatus === 'active',
        actions: wf.actions || []
      })
      setWorkflows(prev => prev.map(w => w.id === id ? { ...w, status: newStatus } : w))
      toast.success('Workflow status updated')
    } catch (err) {
      toast.error('Failed to toggle workflow status')
    }
  }

  const addNode = (nodeTemplate: any) => {
    if (TRIGGER_TYPES.has(nodeTemplate.type)) {
      const existing = nodes.find(n => TRIGGER_TYPES.has(n.type))
      if (existing) {
        setNodes(prev => prev.map(n => n.id === existing.id
          ? { ...n, type: nodeTemplate.type, label: nodeTemplate.label, icon: nodeTemplate.icon, color: nodeTemplate.color, status: undefined }
          : n))
      } else {
        setNodes(prev => [{ id: newNodeId(), type: nodeTemplate.type, label: nodeTemplate.label, icon: nodeTemplate.icon, color: nodeTemplate.color, x: 60, y: 160, config: {} }, ...prev])
      }
      setTriggerEvent(nodeTemplate.type)
      toast.success(`Trigger set to "${nodeTemplate.label}"`)
      return
    }
    const lastNode = nodes[nodes.length - 1]
    const newNode: WorkflowNode = {
      id: newNodeId(),
      type: nodeTemplate.type,
      label: nodeTemplate.label,
      icon: nodeTemplate.icon,
      color: nodeTemplate.color,
      x: (lastNode?.x || 0) + 200,
      y: lastNode?.y || 160,
      config: {}
    }
    setNodes(prev => [...prev, newNode])
    if (lastNode) {
      setConnections(prev => [...prev, { from: lastNode.id, to: newNode.id }])
    }
    toast.success(`Added "${nodeTemplate.label}" node`)
  }

  const handleEditWorkflow = (wf: any) => {
    setCurrentWorkflowId(wf.id)
    setWorkflowName(wf.name)
    setTriggerEvent(wf.trigger_event)
    // The server's copy of the trigger settings wins over what the canvas saved.
    const triggerConfig = wf.trigger_config ?? {}
    
    // Parse visual layout if present in the backend actions
    const layoutAction = wf.actions?.find((a: any) => a.type === 'visual_layout')
    if (layoutAction && layoutAction.config) {
      const savedNodes = layoutAction.config.nodes || []
      const mappedNodes = savedNodes.map((sn: any) => {
        const template = [...TRIGGER_NODES, ...ACTION_NODES, ...LOGIC_NODES].find(t => t.type === sn.type)
        return {
          id: sn.id,
          type: sn.type,
          label: sn.label || template?.label || sn.type,
          icon: template?.icon || Code,
          color: sn.color || template?.color || '#94A3B8',
          x: sn.x,
          y: sn.y,
          config: TRIGGER_TYPES.has(sn.type) ? { ...(sn.config || {}), ...triggerConfig } : (sn.config || {})
        }
      })
      setNodes(mappedNodes)
      setConnections(layoutAction.config.connections || [])
    } else {
      // Rebuild a default linear representation for visual builder if no visual_layout was found
      const newNodes: WorkflowNode[] = []
      const newConns: any[] = []
      
      const triggerTemplate = TRIGGER_NODES.find(t => t.type === wf.trigger_event) || TRIGGER_NODES[0]
      newNodes.push({
        id: 'n1',
        type: triggerTemplate.type,
        label: triggerTemplate.label,
        icon: triggerTemplate.icon,
        color: triggerTemplate.color,
        x: 60,
        y: 160,
        config: { ...triggerConfig }
      })
      
      let lastId = 'n1'
      let currentX = 260
      
      wf.actions?.forEach((act: any, idx: number) => {
        if (act.type === 'visual_layout') return
        const template = [...ACTION_NODES, ...LOGIC_NODES].find(t => t.type === act.type) || ACTION_NODES[0]
        const nid = `n${idx + 2}`
        newNodes.push({
          id: nid,
          type: act.type,
          label: act.config?.label || template.label,
          icon: template.icon,
          color: template.color,
          x: currentX,
          y: 160,
          config: act.config || {}
        })
        newConns.push({ from: lastId, to: nid })
        lastId = nid
        currentX += 200
      })
      setNodes(newNodes)
      setConnections(newConns)
    }
    setTab('builder')
  }

  const saveWorkflowCanvas = async () => {
    try {
      // Collect nodes that are actions/logic (excluding trigger)
      const actionsList: any[] = nodes
        .filter(n => !TRIGGER_TYPES.has(n.type))
        .map(n => ({
          type: n.type,
          config: {
            ...n.config,
            id: n.id,
            label: n.label,
            color: n.color,
            x: n.x,
            y: n.y
          }
        }))
        
      // Append visual layout metadata block
      actionsList.push({
        type: 'visual_layout',
        config: {
          nodes: nodes.map(n => ({
            id: n.id,
            type: n.type,
            label: n.label,
            color: n.color,
            x: n.x,
            y: n.y,
            config: n.config || {}
          })),
          connections: connections
        }
      })

      const triggerNode = nodes.find(n => TRIGGER_TYPES.has(n.type))
      const payload = {
        name: workflowName,
        trigger_event: triggerEvent,
        trigger_config: triggerEvent === 'appointment_reminder'
          ? { minutes_before: Number(triggerNode?.config?.minutes_before ?? DEFAULT_REMINDER_MINUTES) }
          : null,
        is_active: true,
        actions: actionsList
      }

      if (currentWorkflowId) {
        await crmApi.updateWorkflow(currentWorkflowId, payload)
        toast.success('Workflow updated')
      } else {
        const res: any = await crmApi.createWorkflow(payload)
        const wId = res?.id
        if (wId) {
          setCurrentWorkflowId(wId)
        }
        toast.success('Workflow created')
      }
      loadWorkflows()
    } catch (err) {
      console.error(err)
      toast.error('Failed to save workflow')
    }
  }

  const handleLoadTemplate = (templateId: string) => {
    setCurrentWorkflowId(null)
    const node = (id: string, type: string, x: number, config?: Record<string, string>): WorkflowNode => {
      const t = [...TRIGGER_NODES, ...ACTION_NODES, ...LOGIC_NODES].find(n => n.type === type)!
      return { id, type, label: t.label, icon: t.icon, color: t.color, x, y: 160, config }
    }
    const chain = (ids: string[]) => ids.slice(1).map((to, i) => ({ from: ids[i], to }))
    if (templateId === 't1') {
      setWorkflowName('New Lead Call')
      setTriggerEvent('lead_created')
      setNodes(INITIAL_NODES)
      setConnections(CONNECTIONS)
    } else if (templateId === 't2') {
      setWorkflowName('Interested Lead Follow-up')
      setTriggerEvent('lead_status_changed')
      setNodes([
        node('n1', 'lead_status_changed', 60),
        node('n2', 'send_email', 260, { condition_status: 'Interested', subject: 'Next steps', body: 'Thanks for your interest. Here is what happens next.' }),
        node('n3', 'assign_lead', 460, { condition_status: 'Interested', agent: '' }),
      ])
      setConnections(chain(['n1', 'n2', 'n3']))
    } else if (templateId === 't3') {
      setWorkflowName('Appointment Confirmation')
      setTriggerEvent('appointment_booked')
      setNodes([
        node('n1', 'appointment_booked', 60),
        node('n2', 'send_email', 260, { subject: 'Your appointment is confirmed', body: 'Thank you for booking. We look forward to speaking with you.' }),
        node('n3', 'update_crm', 460, { field: 'status', value: 'Follow-up' }),
      ])
      setConnections(chain(['n1', 'n2', 'n3']))
    } else {
      setWorkflowName('Blank Workflow')
      setTriggerEvent('lead_created')
      setNodes([node('n1', 'lead_created', 60)])
      setConnections([])
    }
    setTab('builder')
  }

  // Dragging: the view box is frozen while a node moves so the canvas doesn't re-fit under the cursor.
  const svgRef = useRef<SVGSVGElement>(null)
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number; viewBox: string; moved: boolean } | null>(null)
  const toCanvas = (e: ReactMouseEvent) => {
    const svg = svgRef.current
    const ctm = svg?.getScreenCTM()
    if (!svg || !ctm) return { x: 0, y: 0 }
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse())
    return { x: pt.x, y: pt.y }
  }
  const startDrag = (node: WorkflowNode, e: ReactMouseEvent) => {
    const p = toCanvas(e)
    setDrag({ id: node.id, dx: p.x - node.x, dy: p.y - node.y, viewBox: canvasViewBox(nodes), moved: false })
  }
  const onCanvasMove = (e: ReactMouseEvent) => {
    if (!drag) return
    const p = toCanvas(e)
    setNodes(prev => prev.map(n => n.id === drag.id ? { ...n, x: Math.round(p.x - drag.dx), y: Math.round(p.y - drag.dy) } : n))
    if (!drag.moved) setDrag({ ...drag, moved: true })
  }

  // Steps run in list order, so the arrows are rebuilt as a chain after a removal.
  const removeNode = (id: string) => {
    const remaining = nodes.filter(n => n.id !== id)
    setNodes(remaining)
    setConnections(remaining.slice(1).map((n, i) => ({ from: remaining[i].id, to: n.id })))
    setSelectedNode(null)
  }

  const setNodeConfig = (id: string, key: string, value: string) => {
    setNodes(prev => prev.map(n => n.id === id ? { ...n, config: { ...(n.config || {}), [key]: value } } : n))
  }

  const selectedNodeData = nodes.find(n => n.id === selectedNode)

  const TABS: { id: ViewTab; label: string; icon: any }[] = [
    { id: 'workflows', label: 'Workflows', icon: GitBranch },
    { id: 'builder', label: 'Visual Builder', icon: Code },
    { id: 'templates', label: 'Templates', icon: Copy },
    { id: 'history', label: 'Run History', icon: Activity },
  ]

  return (
    <div className="page-wrapper">
      {/* Header */}
      <div style={{ padding: '28px 32px 0', marginBottom: 24 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(94,230,255,0.07), rgba(123,97,255,0.04))',
          border: '1px solid rgba(94,230,255,0.12)',
          borderRadius: 18, padding: '22px 28px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          position: 'relative', overflow: 'hidden',
        }}>
          <div style={{ position: 'absolute', top: -60, right: -60, width: 200, height: 200, borderRadius: '50%', background: 'rgba(94,230,255,0.06)', filter: 'blur(60px)', pointerEvents: 'none' }} />
          <div>
            <div style={{
              fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700,
              letterSpacing: '-0.03em',
              background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #5EE6FF)',
              WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', marginBottom: 6,
            }}>Workflow Automation</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Automations that run on lead and booking events · {workflows.filter(w => w.status === 'active').length} workflows running</div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <Button variant="ghost" icon={<RefreshCw size={13} />}>Refresh</Button>
            <Button variant="primary" icon={<Plus size={14} />} onClick={() => setShowNewModal(true)}>New Workflow</Button>
          </div>
        </div>
      </div>

      <div style={{ padding: '0 32px' }}>
        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
          <GradientStatCard label="Active Workflows" value={workflows.filter(w => w.status === 'active').length} icon={<Activity size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#5851CC)" delay={0} />
          <GradientStatCard label="Runs (latest 50 each)" value={runs.length} icon={<Zap size={20} color="#fff" />} gradient="linear-gradient(135deg,#22D3A5,#15997A)" delay={80} />
          <GradientStatCard label="Success Rate" value={runs.length ? `${Math.round((runs.filter(r => r.status === 'success').length / runs.length) * 100)}%` : '—'} icon={<CheckCircle2 size={20} color="#fff" />} gradient="linear-gradient(135deg,#5EE6FF,#0EA5E9)" delay={160} />
          <GradientStatCard label="Failed runs" value={runs.filter(r => r.status === 'failed').length} icon={<GitBranch size={20} color="#fff" />} gradient="linear-gradient(135deg,#F5A623,#D97706)" delay={240} />
        </div>

        {/* Tab bar */}
        <div style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.03)', padding: 4, borderRadius: 12, border: '1px solid rgba(255,255,255,0.06)', marginBottom: 20, width: 'fit-content' }}>
          {TABS.map(t => {
            const Icon = t.icon
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 7, padding: '7px 16px',
                  borderRadius: 9, border: 'none',
                  background: tab === t.id ? 'rgba(123,97,255,0.18)' : 'transparent',
                  color: tab === t.id ? '#9580FF' : 'var(--color-text-muted)',
                  fontSize: 12.5, fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s',
                }}
              >
                <Icon size={13} />
                {t.label}
              </button>
            )
          })}
        </div>

        {/* ── Workflows Tab ── */}
        {tab === 'workflows' && (
          <Card padding={0}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>Active Workflows</span>
              <Button variant="ghost" size="sm" icon={<Plus size={12} />} onClick={() => setShowNewModal(true)}>Add</Button>
            </div>
            {workflows.map((wf, i) => (
              <div
                key={wf.id}
                style={{
                  display: 'grid', gridTemplateColumns: '1fr auto auto auto auto',
                  alignItems: 'center', gap: 20, padding: '14px 20px',
                  borderBottom: '1px solid rgba(255,255,255,0.03)',
                  animation: `fadeInUp 0.3s cubic-bezier(0.22,1,0.36,1) ${i * 50}ms both`,
                  transition: 'background 0.15s',
                }}
                onMouseOver={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
                onMouseOut={e => (e.currentTarget.style.background = '')}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 38, height: 38, borderRadius: 10,
                    background: wf.status === 'active' ? 'rgba(34,211,165,0.1)' : wf.status === 'paused' ? 'rgba(245,166,35,0.1)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${wf.status === 'active' ? 'rgba(34,211,165,0.25)' : wf.status === 'paused' ? 'rgba(245,166,35,0.2)' : 'rgba(255,255,255,0.06)'}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>
                    <GitBranch size={15} color={wf.status === 'active' ? '#22D3A5' : wf.status === 'paused' ? '#F5A623' : 'var(--color-text-muted)'} />
                  </div>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>{wf.name}</div>
                    <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
                      {wf.tags.map((t: any) => <span key={t} className="avn-chip avn-chip-gray" style={{ fontSize: 10 }}>{t}</span>)}
                    </div>
                  </div>
                </div>

                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)' }}>{wf.runs}</div>
                  <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>Total Runs</div>
                </div>

                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#22D3A5' }}>
                    {wf.runs > 0 ? Math.round((wf.success / wf.runs) * 100) : 0}%
                  </div>
                  <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>Success</div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <Badge
                    variant={wf.status === 'active' ? 'success' : wf.status === 'paused' ? 'warning' : 'default'}
                    dot
                  >
                    {wf.status}
                  </Badge>
                  <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)', marginTop: 3 }}>{wf.last}</div>
                </div>

                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={() => handleEditWorkflow(wf)}
                    style={{ width: 28, height: 28, borderRadius: 7, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--color-text-muted)', transition: 'all 0.15s' }}
                    title="Edit"
                  ><Eye size={12} /></button>
                  <button
                    onClick={() => toggleWorkflow(wf.id)}
                    style={{
                      width: 28, height: 28, borderRadius: 7,
                      background: wf.status === 'active' ? 'rgba(245,166,35,0.1)' : 'rgba(34,211,165,0.1)',
                      border: `1px solid ${wf.status === 'active' ? 'rgba(245,166,35,0.2)' : 'rgba(34,211,165,0.2)'}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', color: wf.status === 'active' ? '#F5A623' : '#22D3A5', transition: 'all 0.15s',
                    }}
                    title={wf.status === 'active' ? 'Pause' : 'Activate'}
                  >
                    {wf.status === 'active' ? <Pause size={11} /> : <Play size={11} />}
                  </button>
                </div>
              </div>
            ))}
          </Card>
        )}

        {/* ── Visual Builder Tab ── */}
        {tab === 'builder' && (
          <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 220px', gap: 16, height: 580 }}>
            {/* Left Palette */}
            <Card style={{ overflowY: 'auto', padding: '14px' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-muted)', letterSpacing: '0.08em', marginBottom: 10 }}>TRIGGERS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 16 }}>
                {TRIGGER_NODES.map(n => <PaletteNode key={n.type} node={n} onAdd={() => addNode(n)} />)}
              </div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-muted)', letterSpacing: '0.08em', marginBottom: 10 }}>ACTIONS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 16 }}>
                {ACTION_NODES.map(n => <PaletteNode key={n.type} node={n} onAdd={() => addNode(n)} />)}
              </div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-muted)', letterSpacing: '0.08em', marginBottom: 10 }}>LOGIC</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {LOGIC_NODES.map(n => <PaletteNode key={n.type} node={n} onAdd={() => addNode(n)} />)}
              </div>
            </Card>

            {/* Canvas */}
            <Card style={{ padding: 0, position: 'relative', overflow: 'hidden', background: 'rgba(7,11,20,0.95)', display: 'flex', flexDirection: 'column' }}>
               {/* Canvas toolbar */}
              <div style={{ padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{workflowName}</span>
                <span style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>— Visual Canvas</span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                  <Button variant="primary" size="sm" icon={<GitBranch size={12} />} onClick={saveWorkflowCanvas}>Save workflow</Button>
                </div>
              </div>

              <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
              {/* Grid background */}
              <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.4 }}>
                <defs>
                  <pattern id="grid" width={24} height={24} patternUnits="userSpaceOnUse">
                    <path d="M 24 0 L 0 0 0 24" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
                  </pattern>
                </defs>
                <rect width="100%" height="100%" fill="url(#grid)" />
              </svg>

              {/* Workflow SVG canvas */}
              <svg ref={svgRef} viewBox={drag?.viewBox ?? canvasViewBox(nodes)} preserveAspectRatio="xMidYMid meet" style={{ width: '100%', height: '100%', position: 'absolute', inset: 0, zIndex: 1, cursor: drag ? 'grabbing' : 'default' }}
                onMouseMove={onCanvasMove} onMouseUp={() => setDrag(null)} onMouseLeave={() => setDrag(null)}>
                {/* Connections */}
                {connections.map((conn, i) => {
                  const fromNode = nodes.find(n => n.id === conn.from)
                  const toNode = nodes.find(n => n.id === conn.to)
                  if (!fromNode || !toNode) return null
                  return <Arrow key={i} from={fromNode} to={toNode} label={conn.label} />
                })}
                {/* Nodes */}
                {nodes.map(node => (
                  <CanvasNode
                    key={node.id}
                    node={node}
                    selected={selectedNode === node.id}
                    onMouseDown={e => startDrag(node, e)}
                    onClick={() => { if (!drag?.moved) setSelectedNode(node.id === selectedNode ? null : node.id) }}
                  />
                ))}
              </svg>
              </div>

            </Card>

            {/* Right Panel — Node Config */}
            <Card style={{ overflowY: 'auto', padding: '14px' }}>
              {selectedNodeData ? (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Node Config</span>
                    <button aria-label="Close node settings" onClick={() => setSelectedNode(null)} style={{ background: 'transparent', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer' }}><X size={13} /></button>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                    <div style={{ width: 36, height: 36, borderRadius: 9, background: `${selectedNodeData.color}18`, border: `1px solid ${selectedNodeData.color}28`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <selectedNodeData.icon size={16} color={selectedNodeData.color} />
                    </div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{selectedNodeData.label}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>{selectedNodeData.type.replace(/_/g, ' ')}</div>
                    </div>
                  </div>
                  {TRIGGER_TYPES.has(selectedNodeData.type) ? (
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', lineHeight: 1.5 }}>
                      {TRIGGER_NODES.find(t => t.type === selectedNodeData.type)?.desc}. Steps run top to bottom in the order they were added.
                      {selectedNodeData.type === 'appointment_reminder' && (
                        <label style={{ display: 'block', marginTop: 12 }}>
                          <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>Run this long before the appointment</div>
                          <select value={String(selectedNodeData.config?.minutes_before ?? DEFAULT_REMINDER_MINUTES)} style={FIELD_STYLE}
                            onChange={e => setNodeConfig(selectedNodeData.id, 'minutes_before', e.target.value)}>
                            {REMINDER_LEAD_TIMES.map(([minutes, label]) => <option key={minutes} value={minutes}>{label}</option>)}
                          </select>
                        </label>
                      )}
                      {selectedNodeData.type === 'appointment_reminder' || selectedNodeData.type === 'appointment_booked'
                        ? <div style={{ marginTop: 10 }}>Messages can use {'{{appointment.time}}'}, {'{{appointment.date}}'} and {'{{appointment.title}}'}.</div>
                        : null}
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {[...(CONFIG_FIELDS[selectedNodeData.type] ?? []), ...COMMON_FIELDS].map(field => {
                        const value = selectedNodeData.config?.[field.key] ?? ''
                        return (
                          <label key={field.key} style={{ display: 'block' }}>
                            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{field.label}</div>
                            {field.options ? (
                              <select value={value} onChange={e => setNodeConfig(selectedNodeData.id, field.key, e.target.value)} style={FIELD_STYLE}>
                                {(field.key === 'field' && selectedNodeData.type === 'update_crm' ? [...field.options, ...customFieldKeys] : field.options)
                                  .map(o => <option key={o} value={o}>{o || 'Any status'}</option>)}
                              </select>
                            ) : field.multiline ? (
                              <textarea rows={4} value={value} placeholder={field.placeholder} onChange={e => setNodeConfig(selectedNodeData.id, field.key, e.target.value)} style={{ ...FIELD_STYLE, resize: 'vertical' }} />
                            ) : (
                              <input value={value} placeholder={field.placeholder} onChange={e => setNodeConfig(selectedNodeData.id, field.key, e.target.value)} style={FIELD_STYLE} />
                            )}
                          </label>
                        )
                      })}
                      <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Changes are kept when you save the workflow.</div>
                      <Button variant="danger" size="sm" onClick={() => removeNode(selectedNodeData.id)}>Remove step</Button>
                    </div>
                  )}
                </>
              ) : (
                <div style={{ textAlign: 'center', padding: '40px 10px' }}>
                  <Settings2 size={24} color="#3B4560" style={{ margin: '0 auto 10px' }} />
                  <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>Click a node to configure it</div>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* ── Templates Tab ── */}
        {tab === 'templates' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
            {TEMPLATES.map((t, i) => (
              <div
                key={t.id}
                className="glass-card"
                style={{ padding: '20px 22px', position: 'relative', overflow: 'hidden', animation: `fadeInUp 0.3s cubic-bezier(0.22,1,0.36,1) ${i * 60}ms both` }}
              >
                <div style={{ position: 'absolute', top: -30, right: -30, width: 100, height: 100, borderRadius: '50%', background: t.color, opacity: 0.06, filter: 'blur(30px)' }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                  <div style={{ width: 38, height: 38, borderRadius: 10, background: `${t.color}18`, border: `1px solid ${t.color}28`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <GitBranch size={17} color={t.color} />
                  </div>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--color-text-primary)' }}>{t.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{t.desc}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 12 }}>
                  {t.tags.map(tag => <span key={tag} className="avn-chip avn-chip-gray" style={{ fontSize: 10 }}>{tag}</span>)}
                </div>
                <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: '10px 12px', marginBottom: 14 }}>
                  {t.steps.map((s, si) => (
                    <div key={si} style={{ fontSize: 11, color: 'var(--color-text-muted)', lineHeight: 1.6, fontFamily: 'monospace' }}>{s}</div>
                  ))}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div />
                  <button
                    onClick={() => { handleLoadTemplate(t.id); toast.success('Template loaded in builder!') }}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', background: `${t.color}18`, border: `1px solid ${t.color}30`, borderRadius: 9, color: t.color, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                  >
                    Use Template <ArrowRight size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── History Tab ── */}
        {tab === 'history' && (
          <Card padding={0}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>
              Recent runs
            </div>
            {!runs.length ? (
              <div style={{ padding: '32px 20px', textAlign: 'center', fontSize: 12.5, color: 'var(--color-text-muted)' }}>
                No runs yet. Active workflows run when their trigger happens, e.g. when a lead is added.
              </div>
            ) : runs.slice(0, 50).map(run => (
              <div key={run.id} style={{
                display: 'grid', gridTemplateColumns: '32px 1fr auto auto',
                alignItems: 'center', gap: 16, padding: '12px 20px',
                borderBottom: '1px solid rgba(255,255,255,0.03)',
              }}>
                {run.status === 'success'
                  ? <CheckCircle2 size={16} color="#22D3A5" />
                  : run.status === 'failed' ? <AlertCircle size={16} color="#FF4D6A" /> : <Clock size={16} color="#F5A623" />}
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)' }}>{run.workflow_name}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', whiteSpace: 'pre-wrap' }}>{run.message}</div>
                </div>
                <Badge variant={run.status === 'success' ? 'success' : run.status === 'failed' ? 'danger' : 'warning'}>{run.status}</Badge>
                <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>{new Date(run.triggered_at).toLocaleString()}</span>
              </div>
            ))}
          </Card>
        )}
      </div>

      {/* New Workflow Modal */}
      <Modal open={showNewModal} onClose={() => setShowNewModal(false)} title="Create New Workflow" width={480}>
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 6 }}>Workflow Name</div>
            <input
              placeholder="e.g. New Lead Outreach Sequence"
              value={newWfName}
              onChange={e => setNewWfName(e.target.value)}
              style={{ width: '100%', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 9, padding: '8px 12px', color: 'var(--color-text-primary)', fontSize: 13, outline: 'none' }}
            />
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 8 }}>Start from Template</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {TEMPLATES.slice(0, 3).map(t => (
                <button
                  key={t.id}
                  onClick={() => { handleLoadTemplate(t.id); setShowNewModal(false); }}
                  style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, cursor: 'pointer', textAlign: 'left' }}
                >
                  <div style={{ width: 30, height: 30, borderRadius: 8, background: `${t.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                     <GitBranch size={13} color={t.color} />
                  </div>
                  <div>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--color-text-secondary)' }}>{t.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{t.desc}</div>
                  </div>
                  <ChevronRight size={12} color="#4B5675" style={{ marginLeft: 'auto' }} />
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
            <Button variant="ghost" onClick={() => setShowNewModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={() => {
              setCurrentWorkflowId(null)
              setWorkflowName(newWfName || 'Blank Workflow')
              setTriggerEvent('new_lead')
              setNodes([
                { id: 'n1', type: 'new_lead', label: 'New Lead', icon: Users, color: '#7B61FF', x: 60, y: 160 }
              ])
              setConnections([])
              setNewWfName('')
              setShowNewModal(false)
              setTab('builder')
              toast.success('Blank workflow created')
            }}>
              Start Blank
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
