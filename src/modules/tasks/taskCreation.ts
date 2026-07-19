export interface TaskCreationDraft {
  authorizationBasis: string
  target: string
  allowedPorts: string
  riskAcknowledged: boolean
  maxDurationSeconds: number
  maxCommands: number
  maxNetworkRequests: number
  maxBruteforceAttempts: number
  maxConcurrency: number
  autonomyMode: 'advisory' | 'supervised' | 'unattended'
}

export interface TaskCreationPayload {
  target: string
  authorization_basis: string
  allowed_ports: number[]
  max_duration_seconds: number
  max_commands: number
  max_network_requests: number
  max_bruteforce_attempts: number
  max_concurrency: number
  autonomy_mode: TaskCreationDraft['autonomyMode']
}

export function parsePorts(value: string): number[] {
  const ports = value
    .split(/[\s,;]+/)
    .map(item => Number(item.trim()))
    .filter(item => Number.isInteger(item) && item >= 1 && item <= 65535)
  return [...new Set(ports)].sort((left, right) => left - right)
}

export function validateTaskCreation(draft: TaskCreationDraft): string[] {
  const errors: string[] = []
  if (!draft.authorizationBasis.trim()) errors.push('请填写任务依据或授权说明。')
  if (!draft.target.trim()) errors.push('请填写目标范围。')
  if (!draft.riskAcknowledged) errors.push('请确认风险与停止条件。')
  if (!parsePorts(draft.allowedPorts).length) errors.push('请填写至少一个有效端口。')
  const budgets: Array<[string, number]> = [
    ['总时长', draft.maxDurationSeconds],
    ['命令数', draft.maxCommands],
    ['网络请求数', draft.maxNetworkRequests],
    ['验证尝试数', draft.maxBruteforceAttempts],
    ['并发数', draft.maxConcurrency],
  ]
  for (const [label, value] of budgets) {
    if (!Number.isFinite(value) || value <= 0) errors.push(`${label}预算必须大于 0。`)
  }
  return errors
}

export function toTaskCreationPayload(draft: TaskCreationDraft): TaskCreationPayload {
  return {
    target: draft.target.trim(),
    authorization_basis: draft.authorizationBasis.trim(),
    allowed_ports: parsePorts(draft.allowedPorts),
    max_duration_seconds: Math.round(draft.maxDurationSeconds),
    max_commands: Math.round(draft.maxCommands),
    max_network_requests: Math.round(draft.maxNetworkRequests),
    max_bruteforce_attempts: Math.round(draft.maxBruteforceAttempts),
    max_concurrency: Math.round(draft.maxConcurrency),
    autonomy_mode: draft.autonomyMode,
  }
}
