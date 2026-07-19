// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TaskMissionConsole from './TaskMissionConsole.vue'
import type { TaskSnapshot } from './contracts'

function snapshot(): TaskSnapshot {
  return {
    task_id: 'task-fixture',
    phase: 'web',
    status: 'running',
    sequence: 5,
    findings: 2,
    evidence: 3,
    budget: { commands: 4, network_requests: 9 },
    warnings: [],
    candidates: [{
      action_id: 'a1', target: 'fixture.local', action: 'role-check', score: 0.9,
      reason: 'paired role responses available', risk: 'low', expected_evidence: ['role difference'],
    }],
    assets: {
      host: { asset_id: 'host', kind: 'host', label: 'fixture.local', status: 'DISCOVERED', confidence: 0.8 },
    },
    evidenceStates: {},
    currentAction: { action_id: 'a1', plugin: 'web-runtime', target: 'fixture.local', reason: 'paired role responses available', risk: 'low' },
    autonomyMode: 'supervised',
  }
}

describe('TaskMissionConsole', () => {
  it('renders labeled tables and emits keyboard-accessible lifecycle controls', async () => {
    const wrapper = mount(TaskMissionConsole, { props: { snapshot: snapshot() } })
    expect(wrapper.findAll('table caption')).toHaveLength(2)
    expect(wrapper.findAll('th[scope="col"]').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('选择原因：paired role responses available')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('pause')).toHaveLength(1)
    const selects = wrapper.findAll('select')
    await selects[0].setValue('advisory')
    expect(wrapper.emitted('autonomy')?.[0]).toEqual(['advisory'])

    await wrapper.get('button.danger').trigger('click')
    expect(wrapper.find('[role="alertdialog"]').exists()).toBe(true)
    expect(wrapper.emitted('stop')).toBeUndefined()
    await wrapper.find('[role="alertdialog"] button.danger').trigger('click')
    expect(wrapper.emitted('stop')).toHaveLength(1)
  })
})
