import { describe, expect, it } from 'vitest'
import { parsePorts, toTaskCreationPayload, validateTaskCreation, type TaskCreationDraft } from './taskCreation'

const draft: TaskCreationDraft = {
  authorizationBasis: 'fixture course policy',
  target: 'fixture.local',
  allowedPorts: '443, 80, 443',
  riskAcknowledged: true,
  maxDurationSeconds: 600,
  maxCommands: 20,
  maxNetworkRequests: 100,
  maxBruteforceAttempts: 10,
  maxConcurrency: 2,
  autonomyMode: 'supervised',
}

describe('task creation boundary', () => {
  it('normalizes ports and builds a structured scope/budget payload', () => {
    expect(parsePorts(draft.allowedPorts)).toEqual([80, 443])
    expect(validateTaskCreation(draft)).toEqual([])
    expect(toTaskCreationPayload(draft)).toMatchObject({
      target: 'fixture.local',
      allowed_ports: [80, 443],
      max_commands: 20,
      max_concurrency: 2,
    })
  })

  it('requires authorization, scope, risk acknowledgement, and positive budgets', () => {
    const invalid = { ...draft, authorizationBasis: '', target: '', riskAcknowledged: false, maxCommands: 0 }
    expect(validateTaskCreation(invalid).length).toBeGreaterThanOrEqual(4)
  })
})
