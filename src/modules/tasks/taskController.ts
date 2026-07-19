import { pythonApi } from '../../config/python-api.config'
import type { EventEnvelope, TaskSnapshot } from './contracts'
import { taskStore, TaskStore } from './taskStore'

type LifecycleResult = {
  success?: boolean
  status?: string
  message?: string
}

export interface TaskLifecycleApi {
  pentestEvents(taskId: string, afterSequence?: number, limit?: number): Promise<{
    events: EventEnvelope[]
    has_more: boolean
    next_sequence: number
  }>
  pentestStatus(taskId: string): Promise<{
    status: string
    phase: string
    findings_count: number
    event_count?: number
    token_usage?: Record<string, unknown>
    mission_control?: TaskSnapshot['missionControl']
    autonomy_mode?: TaskSnapshot['autonomyMode']
    autonomy_history?: TaskSnapshot['autonomyHistory']
    action_limit?: TaskSnapshot['actionLimit']
    action_limit_history?: TaskSnapshot['actionLimitHistory']
  }>
  pentestPause(taskId: string): Promise<LifecycleResult>
  pentestResume(taskId: string): Promise<LifecycleResult>
  pentestStop(taskId: string): Promise<LifecycleResult>
  pentestSetAutonomy(
    taskId: string,
    mode: 'advisory' | 'supervised' | 'unattended',
    reason?: string,
  ): Promise<LifecycleResult>
  pentestSetActionLimit(taskId: string, level: NonNullable<TaskSnapshot['actionLimit']>, reason?: string): Promise<LifecycleResult>
}

export type TaskControllerListener = (snapshot: TaskSnapshot) => void

/** Coordinates the HTTP lifecycle API with the event-folding task store. */
export class TaskController {
  private readonly cursors = new Map<string, number>()
  private readonly listeners = new Set<TaskControllerListener>()
  private readonly api: TaskLifecycleApi
  private readonly store: TaskStore

  constructor(api: TaskLifecycleApi = pythonApi, store: TaskStore = taskStore) {
    this.api = api
    this.store = store
  }

  subscribe(listener: TaskControllerListener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  snapshot(taskId: string): TaskSnapshot | undefined {
    return this.store.snapshot.tasks[taskId]
  }

  async sync(taskId: string): Promise<TaskSnapshot> {
    let cursor = this.cursors.get(taskId) ?? 0
    let hasMore = true
    while (hasMore) {
      const response = await this.api.pentestEvents(taskId, cursor, 200)
      for (const event of response.events) {
        const result = this.store.apply(event)
        if (result.applied || result.reason === 'duplicate event') cursor = Math.max(cursor, event.sequence)
      }
      const next = Number(response.next_sequence ?? cursor)
      cursor = Math.max(cursor, next)
      hasMore = Boolean(response.has_more)
      if (hasMore && next <= (this.cursors.get(taskId) ?? 0)) break
    }
    this.cursors.set(taskId, cursor)
    // The status endpoint supplies counters while the event stream catches up.
    const status = await this.api.pentestStatus(taskId)
    const snapshot = this.store.applyStatusSnapshot(taskId, status)
    this.emit(snapshot)
    return snapshot
  }

  async pause(taskId: string): Promise<TaskSnapshot> {
    await this.requireSuccess(this.api.pentestPause(taskId))
    return this.sync(taskId)
  }

  async resume(taskId: string): Promise<TaskSnapshot> {
    await this.requireSuccess(this.api.pentestResume(taskId))
    return this.sync(taskId)
  }

  async stop(taskId: string): Promise<TaskSnapshot> {
    await this.requireSuccess(this.api.pentestStop(taskId))
    return this.sync(taskId)
  }

  async setAutonomy(
    taskId: string,
    mode: 'advisory' | 'supervised' | 'unattended',
    reason?: string,
  ): Promise<TaskSnapshot> {
    await this.requireSuccess(this.api.pentestSetAutonomy(taskId, mode, reason))
    return this.sync(taskId)
  }

  async setActionLimit(taskId: string, level: NonNullable<TaskSnapshot['actionLimit']>, reason?: string): Promise<TaskSnapshot> {
    await this.requireSuccess(this.api.pentestSetActionLimit(taskId, level, reason))
    return this.sync(taskId)
  }

  async watch(taskId: string, options: { intervalMs?: number; signal?: AbortSignal } = {}): Promise<void> {
    const intervalMs = Math.max(100, options.intervalMs ?? 1000)
    while (!options.signal?.aborted) {
      await this.sync(taskId)
      const snapshot = this.snapshot(taskId)
      if (snapshot && ['cancelled', 'completed', 'failed', 'done', 'stopped'].includes(snapshot.status)) return
      await new Promise<void>(resolve => {
        const timer = setTimeout(resolve, intervalMs)
        options.signal?.addEventListener('abort', () => {
          clearTimeout(timer)
          resolve()
        }, { once: true })
      })
    }
  }

  private async requireSuccess(result: Promise<LifecycleResult>): Promise<void> {
    const response = await result
    if (response.success === false) throw new Error(response.message || '任务生命周期操作未执行')
  }

  private emit(snapshot: TaskSnapshot): void {
    for (const listener of this.listeners) listener(snapshot)
  }
}

export const taskController = new TaskController()
