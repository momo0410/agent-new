export type TaskPhase = 'init' | 'recon' | 'web' | 'exploit' | 'post' | 'lateral' | 'reflection' | 'done'

export interface EventEnvelope {
  schema_version: string
  event_id: string
  task_id: string
  sequence: number
  timestamp: string
  event_type: string
  actor: string
  payload: Record<string, unknown>
  previous_hash?: string
  event_hash?: string
}

export interface TaskSnapshot {
  task_id: string
  phase: TaskPhase | string
  status: 'running' | 'paused' | 'stopped' | 'done' | 'failed'
  sequence: number
  findings: number
  evidence: number
  budget: Record<string, number>
  warnings: string[]
  lastEventId?: string
}

export interface TaskStoreState {
  tasks: Record<string, TaskSnapshot>
  ignoredEvents: Array<{ event_id: string; schema_version: string; reason: string }>
}
