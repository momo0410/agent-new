import { describe, expect, it, vi } from 'vitest'
import { TaskController, type TaskLifecycleApi } from './taskController'
import { TaskStore } from './taskStore'

const event = (sequence: number, event_type: string, payload: Record<string, unknown> = {}) => ({
  schema_version: 'event.v1', event_id: `evt-${sequence}`, task_id: 'task-controller', sequence,
  timestamp: '2026-07-18T00:00:00Z', event_type, actor: 'test', payload,
})

function fakeApi(events: ReturnType<typeof event>[]): TaskLifecycleApi & { calls: string[] } {
  const calls: string[] = []
  return {
    calls,
    async pentestEvents(_taskId, after = 0) {
      calls.push(`events:${after}`)
      const selected = events.filter(item => item.sequence > after)
      return { events: selected, has_more: false, next_sequence: selected[selected.length - 1]?.sequence ?? after }
    },
    async pentestStatus() {
      calls.push('status')
      return { status: 'paused', phase: 'recon', findings_count: 1, event_count: events.length,
        mission_control: { status: 'paused', reason: 'operator' } }
    },
    async pentestPause() { calls.push('pause'); return { success: true } },
    async pentestResume() { calls.push('resume'); return { success: true } },
    async pentestStop() { calls.push('stop'); return { success: true } },
    async pentestSetAutonomy(_taskId, mode) { calls.push(`autonomy:${mode}`); return { success: true } },
    async pentestSetActionLimit(_taskId, level) { calls.push(`action-limit:${level}`); return { success: true } },
  }
}

describe('TaskController', () => {
  it('hydrates the event store before merging the status read model', async () => {
    const api = fakeApi([
      event(1, 'mission.running'),
      event(2, 'phase.changed', { current: 'recon' }),
      event(3, 'mission.paused', { reason: 'operator' }),
    ])
    const controller = new TaskController(api, new TaskStore())
    const snapshot = await controller.sync('task-controller')
    expect(snapshot.phase).toBe('recon')
    expect(snapshot.status).toBe('paused')
    expect(snapshot.sequence).toBe(3)
    expect(api.calls).toEqual(['events:0', 'status'])
  })

  it('routes lifecycle commands through the API and emits snapshots', async () => {
    const api = fakeApi([event(1, 'mission.running')])
    const controller = new TaskController(api, new TaskStore())
    const listener = vi.fn()
    controller.subscribe(listener)
    await controller.pause('task-controller')
    await controller.resume('task-controller')
    await controller.stop('task-controller')
    await controller.setAutonomy('task-controller', 'advisory')
    await controller.setActionLimit('task-controller', 'probe')
    expect(api.calls.filter(item => ['pause', 'resume', 'stop'].includes(item))).toEqual(['pause', 'resume', 'stop'])
    expect(api.calls).toContain('autonomy:advisory')
    expect(api.calls).toContain('action-limit:probe')
    expect(listener).toHaveBeenCalledTimes(5)
  })
})
