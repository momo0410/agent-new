export type TaskPhase = 'init' | 'recon' | 'web' | 'exploit' | 'post' | 'lateral' | 'reflection' | 'done'
export type EvidenceTruthStatus =
  | 'NOT_STARTED' | 'OUT_OF_SCOPE' | 'BLOCKED_BY_POLICY' | 'UNREACHABLE'
  | 'DISCOVERED' | 'ENUMERATED' | 'POTENTIALLY_VULNERABLE'
  | 'VULNERABILITY_CONFIRMED' | 'EXPLOIT_TRIGGERED' | 'SESSION_ESTABLISHED'
  | 'IDENTITY_CONFIRMED' | 'PRIVILEGE_CONFIRMED' | 'OBJECTIVE_COMPLETED'
  | 'FAILED' | 'INCONCLUSIVE' | 'CANCELLED'

export interface CandidateView {
  action_id: string
  target: string
  action: string
  score: number
  reason: string
  risk: string
  expected_evidence: string[]
}

export interface AssetView {
  asset_id: string
  kind: string
  label: string
  status: EvidenceTruthStatus | string
  confidence: number
}

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
  reason?: string
  previous_state?: string
  new_state?: string
}

export interface TaskSnapshot {
  task_id: string
  phase: TaskPhase | string
  status: 'running' | 'paused' | 'cancelling' | 'cancelled' | 'stopped' | 'done' | 'completed' | 'failed'
  sequence: number
  findings: number
  evidence: number
  budget: Record<string, number>
  warnings: string[]
  candidates: CandidateView[]
  assets: Record<string, AssetView>
  evidenceStates: Record<string, EvidenceTruthStatus | string>
  currentAction?: { action_id: string; plugin: string; target: string; reason: string; risk: string }
  riskLevel?: string
  pausedReason?: string
  lifecycleReason?: string
  autonomyMode?: 'advisory' | 'supervised' | 'unattended'
  autonomyHistory?: Array<{previous: string; current: string; actor: string; reason: string; at?: string}>
  actionLimit?: 'observe' | 'probe' | 'credential_test' | 'exploit' | 'session_verify' | 'post_verify'
  actionLimitHistory?: Array<{previous: string; current: string; actor: string; reason: string; at?: string}>
  missionControl?: {
    mission_id?: string
    status?: string
    canonical_status?: string
    reason?: string
    cancel_requested?: boolean
    paused?: boolean
    updated_at?: string
  }
  lastEventId?: string
}

export interface TaskStoreState {
  tasks: Record<string, TaskSnapshot>
  ignoredEvents: Array<{ event_id: string; schema_version: string; reason: string }>
}
