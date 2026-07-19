// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskWorkspace, { type TaskWorkspaceApi } from './TaskWorkspace.vue'

function fakeApi(): TaskWorkspaceApi {
  const events = [{
    schema_version: 'event.v1', event_id: 'evt-1', task_id: 'task-1', sequence: 1,
    timestamp: '2026-07-18T00:00:00Z', event_type: 'mission.running', actor: 'test', payload: {},
  }]
  return {
    async pentestStart() { return { success: true, task_id: 'task-1' } },
    async pentestEvents() { return { events, has_more: false, next_sequence: 1 } },
    async pentestStatus() { return { status: 'running', phase: 'recon', findings_count: 0, event_count: 1 } },
    async pentestPause() { return { success: true } },
    async pentestResume() { return { success: true } },
    async pentestStop() { return { success: true } },
    async pentestSetAutonomy() { return { success: true } },
    async pentestSetActionLimit() { return { success: true } },
  }
}

describe('TaskWorkspace', () => {
  it('connects the creation wizard to the event-folding mission console', async () => {
    const wrapper = mount(TaskWorkspace, { props: { api: fakeApi() } })
    await wrapper.findComponent({ name: 'TaskCreationWizard' }).vm.$emit('submit', {
      target: 'TARGET', authorization_basis: 'fixture', allowed_ports: [80],
      max_duration_seconds: 60, max_commands: 2, max_network_requests: 5,
      max_bruteforce_attempts: 1, max_concurrency: 1, autonomy_mode: 'supervised',
    })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.findComponent({ name: 'TaskMissionConsole' }).exists()).toBe(true)
    expect(wrapper.text()).toContain('task-1')
    wrapper.unmount()
  })
})
