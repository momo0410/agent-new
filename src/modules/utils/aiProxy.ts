/**
 * AI 代理工具
 * 为前端 UI 和 AI 服务提供统一的后端代理调用能力。
 */

export type AIProviderKind =
  | 'openai'
  | 'deepseek'
  | 'claude'
  | 'ollama'
  | 'qwen'
  | 'custom'
  | string

export interface AIProviderConfig {
  provider?: AIProviderKind
  name?: string
  apiKey: string
  model: string
  baseUrl: string
  useProxy?: boolean
  proxyType?: 'http' | 'https' | 'socks5'
  proxyUrl?: string
  temperature?: number
  maxTokens?: number
  timeoutSeconds?: number
}

export interface AIChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface AIUsageSummary {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

const PYTHON_API_BASE_URL = import.meta.env.DEV
  ? '/api/v1'
  : 'http://127.0.0.1:3001/api/v1'

let lastAIUsage: AIUsageSummary | null = null

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function normalizeProvider(config: Partial<AIProviderConfig>): AIProviderKind {
  const direct = String(config.provider || '').trim().toLowerCase()
  if (direct) return direct

  const fromName = String(config.name || '').trim().toLowerCase()
  if (fromName.includes('claude')) return 'claude'
  if (fromName.includes('deepseek')) return 'deepseek'
  if (fromName.includes('ollama')) return 'ollama'
  if (fromName.includes('qwen')) return 'qwen'
  if (fromName.includes('custom')) return 'custom'

  return 'openai'
}

function hasKnownEndpoint(url: string): boolean {
  return /\/(chat\/completions|messages|chat)$/.test(url)
}

function buildTargetUrl(config: AIProviderConfig, provider: AIProviderKind): string {
  const baseUrl = stripTrailingSlash(config.baseUrl || '')

  if (!baseUrl) {
    throw new Error('AI Base URL 未配置')
  }

  if (hasKnownEndpoint(baseUrl)) {
    return baseUrl
  }

  if (provider === 'claude') {
    return `${baseUrl}/messages`
  }

  if (provider === 'ollama') {
    return `${baseUrl}/chat`
  }

  return `${baseUrl}/chat/completions`
}

function buildHeaders(config: AIProviderConfig, provider: AIProviderKind): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  if (provider === 'claude') {
    if (!config.apiKey) {
      throw new Error('Claude API Key 未配置')
    }
    headers['x-api-key'] = config.apiKey
    headers['anthropic-version'] = '2023-06-01'
    return headers
  }

  if (provider !== 'ollama') {
    if (!config.apiKey) {
      throw new Error('AI API Key 未配置')
    }
    headers['Authorization'] = `Bearer ${config.apiKey}`
  }

  return headers
}

function buildClaudeMessages(messages: AIChatMessage[]): Array<{ role: 'user' | 'assistant'; content: string }> {
  const conversation: Array<{ role: 'user' | 'assistant'; content: string }> = messages
    .filter((message) => message.role !== 'system')
    .map((message) => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: message.content,
    }))

  if (conversation.length > 0) {
    return conversation
  }

  const fallback = messages.map((message) => message.content).join('\n\n').trim()
  return [{ role: 'user', content: fallback || '请开始分析。' }]
}

function buildRequestBody(
  messages: AIChatMessage[],
  config: AIProviderConfig,
  provider: AIProviderKind,
  stream: boolean
): Record<string, unknown> {
  const model = config.model?.trim()
  if (!model) {
    throw new Error('AI 模型未配置')
  }

  const temperature = config.temperature ?? 0.3
  const maxTokens = config.maxTokens ?? 2048

  if (provider === 'claude') {
    const system = messages
      .filter((message) => message.role === 'system')
      .map((message) => message.content)
      .join('\n\n')
      .trim()

    return {
      model,
      system: system || undefined,
      messages: buildClaudeMessages(messages),
      max_tokens: maxTokens,
      stream,
    }
  }

  if (provider === 'ollama') {
    return {
      model,
      messages,
      stream,
      options: {
        temperature,
        num_predict: maxTokens,
      },
    }
  }

  return {
    model,
    messages,
    temperature,
    max_tokens: maxTokens,
    stream,
    stream_options: stream ? { include_usage: true } : undefined,
  }
}

function normalizeUsage(raw: any): AIUsageSummary | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }

  const prompt = Number(raw.prompt_tokens ?? raw.input_tokens ?? 0) || 0
  const completion = Number(raw.completion_tokens ?? raw.output_tokens ?? 0) || 0
  const total = Number(raw.total_tokens ?? (prompt + completion)) || 0

  if (prompt <= 0 && completion <= 0 && total <= 0) {
    return null
  }

  return {
    prompt_tokens: prompt,
    completion_tokens: completion,
    total_tokens: total,
  }
}

function extractTextFromPayload(payload: any, provider: AIProviderKind): string {
  if (!payload || typeof payload !== 'object') {
    return ''
  }

  if (provider === 'claude') {
    if (typeof payload.delta?.text === 'string') {
      return payload.delta.text
    }
    if (typeof payload.content_block?.text === 'string') {
      return payload.content_block.text
    }
    if (Array.isArray(payload.content)) {
      return payload.content
        .map((item: any) => item?.text)
        .filter((item: unknown): item is string => typeof item === 'string')
        .join('')
    }
    return ''
  }

  if (provider === 'ollama') {
    return (
      payload.message?.content ||
      payload.response ||
      ''
    )
  }

  return (
    payload.choices?.[0]?.delta?.content ||
    payload.choices?.[0]?.message?.content ||
    payload.choices?.[0]?.text ||
    ''
  )
}

async function parseProxyError(response: Response): Promise<string> {
  const raw = await response.text().catch(() => '')

  if (!raw) {
    return `HTTP ${response.status}`
  }

  try {
    const parsed = JSON.parse(raw)
    return String(parsed?.detail || parsed?.message || raw)
  } catch {
    return raw
  }
}

function flushStreamBuffer(
  buffer: string,
  provider: AIProviderKind,
  onChunk?: (chunk: string) => void
): { remainder: string; combinedText: string } {
  const lines = buffer.split(/\r?\n/)
  const remainder = lines.pop() ?? ''
  let combinedText = ''

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('event:')) {
      continue
    }

    const payloadText = trimmed.startsWith('data:')
      ? trimmed.slice(5).trim()
      : trimmed

    if (!payloadText || payloadText === '[DONE]') {
      continue
    }

    try {
      const payload = JSON.parse(payloadText)
      const usage = normalizeUsage(payload?.usage)
      if (usage) {
        lastAIUsage = usage
      }
      const text = extractTextFromPayload(payload, provider)
      if (!text) {
        continue
      }
      combinedText += text
      onChunk?.(text)
    } catch {
      // 仅忽略非 JSON 事件，避免打断流式展示。
    }
  }

  return { remainder, combinedText }
}

export async function streamAIProxyMessages(
  messages: AIChatMessage[],
  config: AIProviderConfig,
  onChunk?: (chunk: string) => void,
  signal?: AbortSignal
): Promise<string> {
  lastAIUsage = null
  const provider = normalizeProvider(config)
  const response = await fetch(`${PYTHON_API_BASE_URL}/ai/chat-proxy`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      url: buildTargetUrl(config, provider),
      headers: buildHeaders(config, provider),
      body: buildRequestBody(messages, config, provider, true),
      timeout_seconds: config.timeoutSeconds ?? 90,
    }),
    signal,
  })

  if (!response.ok) {
    throw new Error(await parseProxyError(response))
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('无法获取 AI 响应流')
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let fullText = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const flushed = flushStreamBuffer(buffer, provider, onChunk)
    buffer = flushed.remainder
    fullText += flushed.combinedText
  }

  if (buffer.trim()) {
    const flushed = flushStreamBuffer(`${buffer}\n`, provider, onChunk)
    fullText += flushed.combinedText
  }

  return fullText
}

export function getLastAIUsage(): AIUsageSummary | null {
  return lastAIUsage
}

export async function callAIAnalysisViaProxyStream(
  prompt: string,
  config: AIProviderConfig,
  onChunk?: (chunk: string) => void
): Promise<string> {
  return streamAIProxyMessages(
    [{ role: 'user', content: prompt }],
    config,
    onChunk
  )
}

export function renderAIAnalysisContent(element: HTMLElement, rawText: string): void {
  if (!rawText) {
    element.textContent = ''
    return
  }

  let html = escapeHtml(rawText)

  html = html.replace(/```([\w-]+)?\n?([\s\S]*?)```/g, (_match, lang, code) => {
    const language = lang ? `<div class="ai-code-lang">${escapeHtml(String(lang))}</div>` : ''
    return `<div class="ai-code-block">${language}<pre><code>${code.trim()}</code></pre></div>`
  })

  html = html.replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>')
  html = html.replace(/\n/g, '<br>')

  element.innerHTML = html
}
