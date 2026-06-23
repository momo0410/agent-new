import {
  streamAIProxyMessages,
  getLastAIUsage,
  type AIUsageSummary,
  type AIChatMessage,
  type AIProviderConfig,
  type AIProviderKind,
} from '../utils/aiProxy'

export type AIProvider = AIProviderKind

export interface AIServiceConfig extends AIProviderConfig {
  provider: AIProvider
}

const STORAGE_KEY = 'LERT-ai-config'

const DEFAULT_PROVIDER_CONFIGS: Record<string, Omit<AIServiceConfig, 'provider'>> = {
  openai: {
    name: 'OpenAI',
    apiKey: '',
    model: 'gpt-4o-mini',
    baseUrl: 'https://api.openai.com/v1',
  },
  deepseek: {
    name: 'DeepSeek',
    apiKey: '',
    model: 'deepseek-chat',
    baseUrl: 'https://api.deepseek.com/v1',
  },
  claude: {
    name: 'Claude',
    apiKey: '',
    model: 'claude-3-5-sonnet-latest',
    baseUrl: 'https://api.anthropic.com/v1',
  },
  qwen: {
    name: 'Qwen',
    apiKey: '',
    model: 'qwen-turbo',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  },
  ollama: {
    name: 'Ollama',
    apiKey: '',
    model: 'llama3.1',
    baseUrl: 'http://localhost:11434/api',
  },
  custom: {
    name: 'Custom',
    apiKey: '',
    model: 'gpt-4o-mini',
    baseUrl: '',
  },
}

function normalizeProviderKey(value: unknown): AIProvider {
  const provider = String(value || 'openai').trim().toLowerCase()
  return provider || 'openai'
}

function buildDefaultConfig(provider: AIProvider): AIServiceConfig {
  const preset = DEFAULT_PROVIDER_CONFIGS[provider] || DEFAULT_PROVIDER_CONFIGS.openai
  return {
    provider,
    ...preset,
  }
}

function normalizeConfig(raw: any): AIServiceConfig | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }

  const provider = normalizeProviderKey(raw.provider || raw.currentProvider || raw.name)
  const defaults = buildDefaultConfig(provider)

  return {
    ...defaults,
    provider,
    name: raw.name || defaults.name,
    apiKey: String(raw.apiKey ?? raw.api_key ?? defaults.apiKey ?? ''),
    model: String(raw.model ?? raw.model_name ?? defaults.model ?? ''),
    baseUrl: String(raw.baseUrl ?? raw.base_url ?? defaults.baseUrl ?? ''),
    useProxy: typeof raw.useProxy === 'boolean' ? raw.useProxy : defaults.useProxy,
    proxyType: raw.proxyType ?? defaults.proxyType,
    proxyUrl: raw.proxyUrl ?? defaults.proxyUrl,
    temperature: typeof raw.temperature === 'number' ? raw.temperature : defaults.temperature,
    maxTokens: typeof raw.maxTokens === 'number'
      ? raw.maxTokens
      : typeof raw.max_tokens === 'number'
        ? raw.max_tokens
        : defaults.maxTokens,
    timeoutSeconds: typeof raw.timeoutSeconds === 'number'
      ? raw.timeoutSeconds
      : typeof raw.timeout === 'number'
        ? raw.timeout
        : defaults.timeoutSeconds,
  }
}

function readJsonFromLocalStorage(key: string): any | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) {
      return null
    }
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function readConfigFromLegacySettings(): AIServiceConfig | null {
  const settings = readJsonFromLocalStorage('LERT-settings')
  const currentProvider = settings?.ai?.currentProvider
  const providerConfig = currentProvider
    ? settings?.ai?.providers?.[currentProvider]
    : null

  if (!currentProvider || !providerConfig) {
    return null
  }

  return normalizeConfig({
    provider: currentProvider,
    ...providerConfig,
  })
}

function readConfigFromCommandCenter(): AIServiceConfig | null {
  const cfg = readJsonFromLocalStorage('LERT-ai-config-v2')
  const models = Array.isArray(cfg?.models) ? cfg.models : []
  const activeModel = models.find((item: any) => item?.id === cfg?.activeModelId)
    || models.find((item: any) => item?.isDefault)
    || models[0]

  if (!activeModel) {
    return null
  }

  return normalizeConfig(activeModel)
}

function readStoredConfig(): AIServiceConfig | null {
  return (
    normalizeConfig(readJsonFromLocalStorage(STORAGE_KEY))
    || readConfigFromLegacySettings()
    || readConfigFromCommandCenter()
  )
}

function ensureConfig(config: AIServiceConfig | null): AIServiceConfig {
  if (!config) {
    throw new Error('AI 服务未配置，请先在设置中填写模型信息')
  }

  if (!config.model) {
    throw new Error('AI 模型未配置')
  }

  if (!config.baseUrl) {
    throw new Error('AI Base URL 未配置')
  }

  if (!config.apiKey && config.provider !== 'ollama') {
    throw new Error('AI API Key 未配置')
  }

  return config
}

function buildSolutionMessages(
  title: string,
  description: string,
  severity: string,
  serverInfo: string,
  concise: boolean
): AIChatMessage[] {
  const systemPrompt = concise
    ? '你是一位资深 Linux 运维和安全专家。请给出简洁、准确、可执行的修复思路，优先输出关键步骤。'
    : '你是一位资深 Linux 运维和安全专家。请输出完整、结构化、可执行的修复方案，并明确风险和验证步骤。'

  const userPrompt = `问题标题：${title}
风险等级：${severity}
服务器信息：${serverInfo || '未知'}

问题描述：
${description}

${concise ? '请给出精炼修复建议。' : '请给出详细修复方案。'}`

  return [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ]
}

export class AIService {
  private config: AIServiceConfig | null = readStoredConfig()

  getConfig(): AIServiceConfig | null {
    if (!this.config) {
      this.config = readStoredConfig()
    }
    return this.config
  }

  saveConfig(config: AIServiceConfig): void {
    const normalized = normalizeConfig(config)
    if (!normalized) {
      throw new Error('无效的 AI 配置')
    }

    this.config = normalized
    localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  }

  clearConfig(): void {
    this.config = null
    localStorage.removeItem(STORAGE_KEY)
  }

  getLastUsage(): AIUsageSummary | null {
    return getLastAIUsage()
  }

  isConfigured(): boolean {
    try {
      const config = this.getConfig()
      return Boolean(
        config
        && config.model
        && config.baseUrl
        && (config.provider === 'ollama' || config.apiKey)
      )
    } catch {
      return false
    }
  }

  async testConnection(): Promise<string> {
    const config = ensureConfig(this.getConfig())
    const result = await streamAIProxyMessages(
      [{ role: 'user', content: '请只回复"连接成功"。' }],
      {
        ...config,
        maxTokens: 64,
      }
    )

    return result || '连接成功'
  }

  async generateSolution(
    title: string,
    description: string,
    severity: string,
    serverInfo: string = ''
  ): Promise<string> {
    const config = ensureConfig(this.getConfig())
    return streamAIProxyMessages(
      buildSolutionMessages(title, description, severity, serverInfo, false),
      config
    )
  }

  async generateConciseSolutionStream(
    title: string,
    description: string,
    severity: string,
    serverInfo: string = '',
    onChunk?: (text: string) => void,
    onComplete?: (finalText: string) => void,
    signal?: AbortSignal
  ): Promise<string> {
    const config = ensureConfig(this.getConfig())
    const finalText = await streamAIProxyMessages(
      buildSolutionMessages(title, description, severity, serverInfo, true),
      config,
      onChunk,
      signal
    )

    onComplete?.(finalText)
    return finalText
  }

  async chatStream(
    messages: AIChatMessage[],
    onChunk?: (text: string) => void,
    onComplete?: (finalText: string) => void,
    signal?: AbortSignal
  ): Promise<string> {
    const config = ensureConfig(this.getConfig())
    const finalText = await streamAIProxyMessages(messages, config, onChunk, signal)
    onComplete?.(finalText)
    return finalText
  }

  async analyzeLogStream(
    logContent: string,
    logSource?: string,
    onChunk?: (chunk: string) => void,
    onComplete?: (finalText: string) => void,
    signal?: AbortSignal
  ): Promise<string> {
    const messages: AIChatMessage[] = [
      {
        role: 'system',
        content: '你是一位资深日志分析专家。请用中文输出：1. 摘要 2. 异常与风险 3. 可能原因 4. 建议排查步骤。',
      },
      {
        role: 'user',
        content: `日志来源：${logSource || '未指定'}\n\n日志内容：\n${logContent}`,
      },
    ]

    return this.chatStream(messages, onChunk, onComplete, signal)
  }

  async analyzeCommandOutputStream(
    command: string,
    output: string,
    title: string,
    onChunk?: (chunk: string) => void,
    onComplete?: (finalText: string) => void
  ): Promise<string> {
    const messages: AIChatMessage[] = [
      {
        role: 'system',
        content: `你是一位资深 Linux 安全运维专家。请分析以下命令输出结果，给出专业的安全评估和建议。
请用中文输出，结构如下：
1. 执行摘要（简要说明命令目的和输出概况）
2. 安全风险分析（识别潜在的安全隐患、异常配置、权限问题等）
3. 影响评估（评估问题的严重程度和影响范围）
4. 修复建议（给出具体、可执行的修复命令或配置修改方案）
5. 最佳实践（相关的安全加固建议）`,
      },
      {
        role: 'user',
        content: `检查项：${title || '未指定'}\n\n执行命令：\n\`\`\`bash\n${command}\n\`\`\`\n\n命令输出：\n\`\`\`\n${output}\n\`\`\`\n\n请基于以上输出进行专业分析。`,
      },
    ]

    return this.chatStream(messages, onChunk, onComplete)
  }
}

export const aiService = new AIService()
