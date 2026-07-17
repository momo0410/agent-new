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
        break
      case 'budget.updated':
        for (const [key, value] of Object.entries(payload)) if (typeof value === 'number') task.budget[key] = value
        break
      case 'task.paused': task.status = 'paused'; break
      case 'task.resumed': task.status = 'running'; break
      case 'task.stopped': task.status = 'stopped'; break
      case 'task.failed': task.status = 'failed'; break
      case 'task.completed': task.status = 'done'; task.phase = 'done'; break
      case 'policy.denied':
        task.warnings.push(String(payload.reason ?? 'policy denied'))
        break
      default:
        // Forward-compatible events still advance sequence and remain auditable.
        task.warnings.push(`unhandled event: ${event.event_type}`)
    }
    this.state.tasks[event.task_id] = task
  }
}

export const taskStore = new TaskStore()
