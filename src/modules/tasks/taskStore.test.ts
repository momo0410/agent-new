import { describe, expect, it } from 'vitest'
import { TaskStore } from './taskStore'

const event = (sequence: number, event_type: string, payload: Record<string, unknown> = {}) => ({
  schema_version: 'event.v1', event_id: `e-${sequence}`, task_id: 'task-1', sequence,
  timestamp: '2026-07-18T00:00:00Z', event_type, actor: 'test', payload,
})

describe('TaskStore', () => {
  it('folds out-of-order events after the missing predecessor arrives', () => {
    const store = new TaskStore()
    expect(store.apply(event(2, 'phase.changed', { current: 'recon' })).applied).toBe(false)
    expect(store.apply(event(1, 'finding.observed')).applied).toBe(true)
    expect(store.snapshot.tasks['task-1'].sequence).toBe(2)
    expect(store.snapshot.tasks['task-1'].phase).toBe('recon')
  })

  it('surfaces unknown schema versions without dropping them silently', () => {
    const store = new TaskStore()
    const result = store.apply({ ...event(1, 'task.created'), schema_version: 'event.v99' })
    expect(result.applied).toBe(false)
    expect(store.snapshot.ignoredEvents[0].reason).toBe('unknown schema version')
  })

  it('deduplicates event ids and preserves policy warnings', () => {
    const store = new TaskStore()
    const denied = event(1, 'policy.denied', { reason: 'outside scope' })
    expect(store.apply(denied).applied).toBe(true)
    expect(store.apply(denied).reason).toBe('duplicate event')
    expect(store.snapshot.tasks['task-1'].warnings).toContain('outside scope')
  })
})
