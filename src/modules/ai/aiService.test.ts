// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('AI runtime secret handling', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('migrates legacy model data into memory and scrubs browser storage', async () => {
    localStorage.setItem('LERT-ai-config', JSON.stringify({
      provider: 'openai', model: 'fixture-model', baseUrl: 'http://fixture', apiKey: 'MODEL_SECRET',
    }))
    localStorage.setItem('LERT-settings', JSON.stringify({
      ai: { providers: { openai: { apiKey: 'SECOND_SECRET' } } },
    }))
    const { aiService } = await import('./aiService')
    expect(aiService.getConfig()?.apiKey).toBe('MODEL_SECRET')
    expect(localStorage.getItem('LERT-ai-config')).not.toContain('MODEL_SECRET')
    expect(localStorage.getItem('LERT-settings')).not.toContain('SECOND_SECRET')

    aiService.saveConfig({
      provider: 'openai', name: 'Fixture', apiKey: 'NEW_SECRET', model: 'fixture-model', baseUrl: 'http://fixture',
    })
    expect(aiService.getConfig()?.apiKey).toBe('NEW_SECRET')
    expect(localStorage.getItem('LERT-ai-config')).not.toContain('NEW_SECRET')
  })
})
