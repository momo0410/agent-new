// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TaskCreationWizard from './TaskCreationWizard.vue'

describe('TaskCreationWizard', () => {
  it('keeps submission gated until authorization, scope, risk, and budgets are complete', async () => {
    const wrapper = mount(TaskCreationWizard)
    const submit = wrapper.get('button[type="submit"]')
    expect(submit.attributes('disabled')).toBeDefined()
    await wrapper.get('#task-authorization').setValue('fixture course policy')
    await wrapper.get('#task-target').setValue('fixture.local')
    await wrapper.get('#task-risk').setValue(true)
    expect(submit.attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    const payload = wrapper.emitted('submit')?.[0]?.[0] as Record<string, unknown>
    expect(payload).toMatchObject({ target: 'fixture.local', authorization_basis: 'fixture course policy' })
    expect(payload.allowed_ports).toEqual([80, 443])
  })
})
