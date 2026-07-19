import type { EventEnvelope, TaskPhase, TaskSnapshot, TaskStoreState } from './contracts'

const PHASES: TaskPhase[] = ['init', 'recon', 'web', 'exploit', 'post', 'lateral', 'reflection', 'done']

function emptyTask(taskId: string): TaskSnapshot {
  return {
    task_id: taskId,
    phase: 'init',
    status: 'running',
    sequence: 0,
    findings: 0,
    evidence: 0,
    budget: {},
    warnings: [],
    candidates: [],
    assets: {},
    evidenceStates: {},
    missionControl: { status: 'running' },
  }
}

/** Event-folding store. Unknown schema versions are surfaced, never silently dropped. */
export class TaskStore {
  private readonly supportedSchemas: ReadonlySet<string>
  private readonly state: TaskStoreState = { tasks: {}, ignoredEvents: [] }
  private readonly seen = new Set<string>()
  private readonly pending = new Map<string, Map<number, EventEnvelope>>()

  constructor(supportedSchemas: ReadonlySet<string> = new Set(['event.v1'])) {
    this.supportedSchemas = supportedSchemas
  }

  get snapshot(): TaskStoreState {
    return {
      tasks: Object.fromEntries(Object.entries(this.state.tasks).map(([id, task]) => [id, {
        ...task,
        budget: { ...task.budget },
        warnings: [...task.warnings],
        candidates: task.candidates.map(item => ({ ...item, expected_evidence: [...item.expected_evidence] })),
        assets: Object.fromEntries(Object.entries(task.assets).map(([id, asset]) => [id, { ...asset }])),
        evidenceStates: { ...task.evidenceStates },
        missionControl: task.missionControl ? { ...task.missionControl } : undefined,
        autonomyHistory: task.autonomyHistory?.map(item => ({ ...item })),
        actionLimitHistory: task.actionLimitHistory?.map(item => ({ ...item })),
        currentAction: task.currentAction ? { ...task.currentAction } : undefined,
      }])),
      ignoredEvents: this.state.ignoredEvents.map(item => ({ ...item })),
    }
  }

  apply(event: EventEnvelope): { applied: boolean; reason?: string } {
    if (!this.supportedSchemas.has(event.schema_version)) {
      const record = { event_id: event.event_id, schema_version: event.schema_version, reason: 'unknown schema version' }
      if (!this.state.ignoredEvents.some(item => item.event_id === event.event_id)) this.state.ignoredEvents.push(record)
      return { applied: false, reason: record.reason }
    }
    if (this.seen.has(event.event_id)) return { applied: false, reason: 'duplicate event' }
    if (!event.task_id || !Number.isInteger(event.sequence) || event.sequence < 1) return { applied: false, reason: 'invalid event envelope' }

    const queue = this.pending.get(event.task_id) ?? new Map<number, EventEnvelope>()
    queue.set(event.sequence, event)
    this.pending.set(event.task_id, queue)
    const task = this.state.tasks[event.task_id] ?? emptyTask(event.task_id)
    let next = task.sequence + 1
    let applied = false
    while (queue.has(next)) {
      const contiguous = queue.get(next)!
      queue.delete(next)
      this.fold(contiguous)
      this.seen.add(contiguous.event_id)
      applied = true
      next += 1
    }
    if (!queue.size) this.pending.delete(event.task_id)
    return applied ? { applied: true } : { applied: false, reason: 'waiting for preceding event' }
  }

  /** Merge a status read-model without advancing the event cursor. */
  applyStatusSnapshot(taskId: string, status: {
    status?: string
    phase?: string
    findings_count?: number
    event_count?: number
    token_usage?: Record<string, unknown>
    mission_control?: TaskSnapshot['missionControl']
    autonomy_mode?: TaskSnapshot['autonomyMode']
    autonomy_history?: TaskSnapshot['autonomyHistory']
    action_limit?: TaskSnapshot['actionLimit']
    action_limit_history?: TaskSnapshot['actionLimitHistory']
  }): TaskSnapshot {
    const task = this.state.tasks[taskId] ?? emptyTask(taskId)
    const rawStatus = String(status.status ?? task.status).toLowerCase()
    const normalizedStatus = rawStatus === 'done' ? 'completed' : rawStatus
    task.status = normalizedStatus as TaskSnapshot['status']
    if (typeof status.phase === 'string' && PHASES.includes(status.phase as TaskPhase)) {
      task.phase = status.phase as TaskPhase
    }
    if (typeof status.findings_count === 'number') task.findings = Math.max(task.findings, status.findings_count)
    if (status.token_usage && typeof status.token_usage === 'object') {
      const numericUsage: Record<string, number> = {}
      for (const [key, value] of Object.entries(status.token_usage)) {
        if (typeof value === 'number') numericUsage[key] = value
      }
      task.budget = { ...task.budget, ...numericUsage }
    }
    if (status.mission_control) task.missionControl = { ...task.missionControl, ...status.mission_control }
    if (status.autonomy_mode) task.autonomyMode = status.autonomy_mode
    if (status.autonomy_history) task.autonomyHistory = status.autonomy_history.map(item => ({ ...item }))
    if (status.action_limit) task.actionLimit = status.action_limit
    if (status.action_limit_history) task.actionLimitHistory = status.action_limit_history.map(item => ({ ...item }))
    this.state.tasks[taskId] = task
    return { ...task, budget: { ...task.budget }, missionControl: task.missionControl ? { ...task.missionControl } : undefined }
  }

  private fold(event: EventEnvelope): void {
    const task = this.state.tasks[event.task_id] ?? emptyTask(event.task_id)
    task.sequence = event.sequence
    task.lastEventId = event.event_id
    const payload = event.payload ?? {}
    switch (event.event_type) {
      case 'phase.changed':
        if (typeof payload.current === 'string' && PHASES.includes(payload.current as TaskPhase)) task.phase = payload.current as TaskPhase
        break
      case 'finding.observed':
      case 'vulnerability.recorded':
      case 'finding.updated':
        task.findings += 1
        break
      case 'evidence.recorded':
        task.evidence += 1
        if (typeof payload.evidence_id === 'string' && typeof payload.status === 'string') {
          task.evidenceStates[payload.evidence_id] = payload.status
        }
        break
      case 'finding.transitioned':
        if (typeof payload.finding_id === 'string' && typeof payload.new_state === 'string') {
          task.evidenceStates[payload.finding_id] = payload.new_state
        }
        break
      case 'candidate.ranked':
        if (Array.isArray(payload.candidates)) {
          task.candidates = payload.candidates
            .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
            .map(item => ({
              action_id: String(item.action_id ?? ''),
              target: String(item.target ?? ''),
              action: String(item.action ?? ''),
              score: Number(item.score ?? 0),
              reason: String(item.reason ?? ''),
              risk: String(item.risk ?? 'low'),
              expected_evidence: Array.isArray(item.expected_evidence) ? item.expected_evidence.map(String) : [],
            }))
        }
        break
      case 'asset.observed':
      case 'asset.updated':
        if (typeof payload.asset_id === 'string') {
          task.assets[payload.asset_id] = {
            asset_id: payload.asset_id,
            kind: String(payload.kind ?? 'asset'),
            label: String(payload.label ?? payload.asset_id),
            status: String(payload.status ?? 'DISCOVERED'),
            confidence: Number(payload.confidence ?? 0),
          }
        }
        break
      case 'action.started':
        task.currentAction = {
          action_id: String(payload.action_id ?? ''),
          plugin: String(payload.plugin ?? payload.tool ?? ''),
          target: String(payload.target ?? ''),
          reason: String(payload.reason ?? payload.intent ?? ''),
          risk: String(payload.risk ?? 'low'),
        }
        task.riskLevel = task.currentAction.risk
        break
      case 'action.finished':
      case 'action.cancelled':
        if (!payload.action_id || payload.action_id === task.currentAction?.action_id) task.currentAction = undefined
        break
      case 'budget.updated':
        for (const [key, value] of Object.entries(payload)) if (typeof value === 'number') task.budget[key] = value
        break
      case 'task.paused': task.status = 'paused'; task.pausedReason = String(payload.reason ?? ''); break
      case 'task.resumed': task.status = 'running'; break
      case 'task.stopped': task.status = 'stopped'; break
      case 'task.failed': task.status = 'failed'; break
      case 'task.completed': task.status = 'done'; task.phase = 'done'; break
      case 'mission.paused':
        task.status = 'paused'
        task.pausedReason = String(payload.reason ?? '')
        task.missionControl = { ...task.missionControl, status: 'paused', reason: task.pausedReason, paused: true }
        break
      case 'mission.running':
        task.status = 'running'
        task.missionControl = { ...task.missionControl, status: 'running', paused: false }
        break
      case 'mission.cancelling':
        task.status = 'cancelling'
        task.lifecycleReason = String(payload.reason ?? '')
        task.missionControl = { ...task.missionControl, status: 'cancelling', reason: task.lifecycleReason, cancel_requested: true }
        break
      case 'mission.cancelled':
        task.status = 'cancelled'
        task.lifecycleReason = String(payload.reason ?? '')
        task.missionControl = { ...task.missionControl, status: 'cancelled', reason: task.lifecycleReason, cancel_requested: true }
        break
      case 'mission.completed':
        task.status = 'completed'
        task.phase = 'done'
        task.missionControl = { ...task.missionControl, status: 'completed', reason: String(payload.reason ?? '') }
        break
      case 'mission.failed':
        task.status = 'failed'
        task.lifecycleReason = String(payload.reason ?? '')
        task.missionControl = { ...task.missionControl, status: 'failed', reason: task.lifecycleReason }
        break
      case 'policy.denied':
        task.warnings.push(String(payload.reason ?? 'policy denied'))
        break
      case 'autonomy.changed': {
        const current = String(payload.current ?? '').toLowerCase()
        if (['advisory', 'supervised', 'unattended'].includes(current)) {
          task.autonomyMode = current as TaskSnapshot['autonomyMode']
          task.autonomyHistory = [
            ...(task.autonomyHistory ?? []),
            {
              previous: String(payload.previous ?? ''),
              current,
              actor: event.actor,
              reason: String(event.reason ?? ''),
              at: event.timestamp,
            },
          ].slice(-100)
        }
        break
      }
      case 'action_limit.changed': {
        const current = String(payload.current ?? '').toLowerCase()
        if (['observe', 'probe', 'credential_test', 'exploit', 'session_verify', 'post_verify'].includes(current)) {
          task.actionLimit = current as TaskSnapshot['actionLimit']
          task.actionLimitHistory = [
            ...(task.actionLimitHistory ?? []),
            {
              previous: String(payload.previous ?? ''),
              current,
              actor: event.actor,
              reason: String(event.reason ?? ''),
              at: event.timestamp,
            },
          ].slice(-100)
        }
        break
      }
      default:
        // Forward-compatible events still advance sequence and remain auditable.
        task.warnings.push(`unhandled event: ${event.event_type}`)
    }
    this.state.tasks[event.task_id] = task
  }
}

export const taskStore = new TaskStore()
