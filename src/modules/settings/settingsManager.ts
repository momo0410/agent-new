/**
 * 设置管理器
 * 负责应用设置的管理和持久化
 */

import { EventEmitter } from '../utils/EventEmitter';
import { aiService, type AIProvider } from '../ai/aiService';

export interface AIProviderSettings {
  name: string;
  apiKey: string;
  model: string;
  baseUrl: string;
  useProxy: boolean;
  proxyType: 'http' | 'https' | 'socks5';
  proxyUrl: string;
}

export interface AIPrimaryModelSettings {
  provider: string;
  model: string;
  api_key?: string;
  base_url?: string;
}

export interface AISettings {
  currentProvider: string;
  providers: Record<string, AIProviderSettings>;
  primary_model?: AIPrimaryModelSettings;
}

export interface AppSettings {
  theme: 'light' | 'dark';
  language: 'zh-CN' | 'en-US';
  autoConnect: boolean;
  defaultSSHPort: number;
  terminalFont: string;
  terminalFontSize: number;
  maxLogLines: number;
  autoSaveInterval: number;
  notifications: {
    enabled: boolean;
    connectionStatus: boolean;
    commandCompletion: boolean;
    errorAlerts: boolean;
  };
  security: {
    savePasswords: boolean;
    sessionTimeout: number;
    requireConfirmation: boolean;
  };
  ui: {
    sidebarWidth: number;
    showStatusBar: boolean;
    compactMode: boolean;
    animationsEnabled: boolean;
  };
  ssh: {
    keepAliveInterval: number;
    connectionTimeout: number;
    maxRetries: number;
  };
  ai: AISettings;
}

export class SettingsManager extends EventEmitter<AppSettings> {
  private settings: AppSettings;

  constructor() {
    super();
    this.settings = this.getDefaultSettings();
  }

  /**
   * 获取默认设置
   */
  private getDefaultSettings(): AppSettings {
    // 检测操作系统：Windows 下默认隐藏状态栏，macOS 下默认显示
    const isWindows = navigator.userAgent.toLowerCase().includes('windows');
    const showStatusBar = !isWindows; // Windows: false, 其他: true

    return {
      theme: 'light',
      language: 'zh-CN',
      autoConnect: false,
      defaultSSHPort: 22,
      terminalFont: 'Monaco, Consolas, monospace',
      terminalFontSize: 14,
      maxLogLines: 1000,
      autoSaveInterval: 30000, // 30秒
      notifications: {
        enabled: true,
        connectionStatus: true,
        commandCompletion: false,
        errorAlerts: true
      },
      security: {
        savePasswords: false,
        sessionTimeout: 86400000, // 24小时 - 大幅增加避免频繁超时
        requireConfirmation: false // 关闭确认要求，减少操作限制
      },
      ui: {
        sidebarWidth: 280,
        showStatusBar,
        compactMode: false,
        animationsEnabled: true
      },
      ssh: {
        keepAliveInterval: 30000, // 30秒
        connectionTimeout: 0, // 0 = 禁用超时，避免长时间操作被中断
        maxRetries: 3
      },
      // 新增：AI设置默认值
      ai: {
        currentProvider: 'openai',
        providers: {
          openai: {
            name: 'OpenAI',
            apiKey: '',
            model: 'gpt-4o-mini',
            baseUrl: 'https://api.openai.com/v1',
            useProxy: false,
            proxyType: 'http',
            proxyUrl: ''
          },
          deepseek: {
            name: 'DeepSeek',
            apiKey: '',
            model: 'deepseek-chat',
            baseUrl: 'https://api.deepseek.com/v1',
            useProxy: false,
            proxyType: 'http',
            proxyUrl: ''
          },
          claude: {
            name: 'Claude',
            apiKey: '',
            model: 'claude-3-5-sonnet-latest',
            baseUrl: 'https://api.anthropic.com/v1',
            useProxy: false,
            proxyType: 'http',
            proxyUrl: ''
          },
          qwen: {
            name: 'Qwen',
            apiKey: '',
            model: 'qwen-turbo',
            baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            useProxy: false,
            proxyType: 'http',
            proxyUrl: ''
          },
          ollama: {
            name: 'Ollama',
            apiKey: '',
            model: 'llama3.1',
            baseUrl: 'http://localhost:11434/api',
            useProxy: false,
            proxyType: 'http',
            proxyUrl: ''
          },
          custom: {
            name: '自定义 API',
            apiKey: '',
            model: '',
            baseUrl: '',
            useProxy: false,
            proxyType: 'http',
            proxyUrl: ''
          }
        }
      }
    };
  }

  /**
   * 初始化设置管理器
   */
  async initialize(): Promise<void> {
    try {
      await this.loadSettings();
      console.log('✅ 设置管理器初始化完成');
    } catch (error) {
      console.error('❌ 设置管理器初始化失败:', error);
    }
  }

  /**
   * 加载设置
   */
  async loadSettings(): Promise<void> {
    try {
      // 从本地存储加载
      const localSettings = this.loadFromLocalStorage();

      // 从后端加载（如果有的话）
      const backendSettings = await this.loadFromBackend();

      // 使用深度合并，避免嵌套对象（如ai.providers）被覆盖
      this.settings = this.deepMerge(
        this.getDefaultSettings(),
        localSettings,
        backendSettings
      ) as AppSettings;
      this.settings = this.normalizeAISettings(this.settings);

      this.syncAIServiceCache(false);

      // 通知监听器
      this.notifyListeners();

    } catch (error) {
      console.error('加载设置失败:', error);
    }
  }

  /**
   * 从本地存储加载设置
   */
  private loadFromLocalStorage(): Partial<AppSettings> {
    try {
      const saved = localStorage.getItem('LERT-settings');
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (error) {
      console.error('从本地存储加载设置失败:', error);
    }
    return {};
  }

  /**
   * 从后端加载设置
   */
  private async loadFromBackend(): Promise<Partial<AppSettings>> {
    try {
      const { invoke } = await import('../../shims/@tauri-apps/api/core');
      const settingsContent = await invoke('read_settings_file') as string;

      if (settingsContent) {
        const settings = JSON.parse(settingsContent);
        console.log('✅ 从settings.json加载设置成功');
        return settings;
      }

      return {};
    } catch (error) {
      console.error('从后端加载设置失败:', error);
      return {};
    }
  }

  /**
   * 保存设置
   */
  async saveSettings(): Promise<void> {
    try {
      this.settings = this.normalizeAISettings(this.settings);

      // 保存到本地存储
      this.saveToLocalStorage();
      
      // 保存到后端
      await this.saveToBackend();

      this.syncAIServiceCache(true);
      
      // 通知监听器
      this.notifyListeners();
      
      console.log('设置已保存');
    } catch (error) {
      console.error('保存设置失败:', error);
      throw error;
    }
  }

  /**
   * 保存到本地存储
   */
  private saveToLocalStorage(): void {
    try {
      localStorage.setItem('LERT-settings', JSON.stringify(this.settings));
    } catch (error) {
      console.error('保存设置到本地存储失败:', error);
    }
  }

  private syncAIServiceCache(allowIncompleteOverride: boolean): void {
    try {
      const currentProvider = this.settings.ai?.currentProvider;
      const providerConfig = currentProvider
        ? this.settings.ai?.providers?.[currentProvider]
        : null;

      if (!currentProvider || !providerConfig) {
        if (allowIncompleteOverride) {
          aiService.clearConfig();
        }
        return;
      }

      const mappedProvider = this.mapProviderKeyToType(currentProvider);
      const hasRunnableConfig = Boolean(
        providerConfig.model
        && providerConfig.baseUrl
        && (mappedProvider === 'ollama' || providerConfig.apiKey)
      );

      if (!allowIncompleteOverride && !hasRunnableConfig) {
        return;
      }

      aiService.saveConfig({
        provider: mappedProvider,
        name: providerConfig.name,
        apiKey: providerConfig.apiKey || '',
        model: providerConfig.model || '',
        baseUrl: providerConfig.baseUrl || '',
        useProxy: providerConfig.useProxy || false,
        proxyType: providerConfig.proxyType || 'http',
        proxyUrl: providerConfig.proxyUrl || ''
      });
    } catch (error) {
      console.warn('同步 AI 服务缓存失败:', error);
    }
  }

  private mapProviderKeyToType(key: string): AIProvider {
    if (['openai', 'deepseek', 'claude', 'ollama', 'qwen', 'custom'].includes(key)) {
      return key as AIProvider;
    }
    return 'custom';
  }

  /**
   * 保存到后端
   */
  private async saveToBackend(): Promise<void> {
    try {
      const { invoke } = await import('../../shims/@tauri-apps/api/core');
      const settingsJson = JSON.stringify(this.settings, null, 2);
      await invoke('write_settings_file', { content: settingsJson });
      console.log('✅ 设置保存到settings.json成功');
    } catch (error) {
      console.error('保存设置到后端失败:', error);
      throw error;
    }
  }

  /**
   * 获取设置
   */
  getSettings(): AppSettings {
    return { ...this.settings };
  }

  /**
   * 更新设置（使用深度合并，避免嵌套对象被覆盖）
   */
  updateSettings(updates: Partial<AppSettings>): void {
    this.settings = this.normalizeAISettings(
      this.deepMerge(this.settings, updates) as AppSettings
    );
  }

  /**
   * 获取特定设置值
   */
  get<K extends keyof AppSettings>(key: K): AppSettings[K] {
    return this.settings[key];
  }

  /**
   * 设置特定值
   */
  set<K extends keyof AppSettings>(key: K, value: AppSettings[K]): void {
    this.settings[key] = value;
  }

  /**
   * 重置设置到默认值
   */
  resetToDefaults(): void {
    this.settings = this.getDefaultSettings();
  }

  /**
   * 导出设置
   */
  exportSettings(): string {
    return JSON.stringify(this.settings, null, 2);
  }

  /**
   * 导入设置（使用深度合并）
   */
  importSettings(settingsJson: string): boolean {
    try {
      const importedSettings = JSON.parse(settingsJson);

      // 验证设置格式
      if (this.validateSettings(importedSettings)) {
        this.settings = this.normalizeAISettings(
          this.deepMerge(
            this.getDefaultSettings(),
            importedSettings
          ) as AppSettings
        );
        return true;
      }

      return false;
    } catch (error) {
      console.error('导入设置失败:', error);
      return false;
    }
  }

  /**
   * 深度合并对象，避免嵌套对象被覆盖
   */
  private deepMerge(...objects: any[]): any {
    const isObject = (obj: any) => obj && typeof obj === 'object' && !Array.isArray(obj);

    return objects.reduce((prev, obj) => {
      if (!obj) return prev;

      Object.keys(obj).forEach(key => {
        const prevValue = prev[key];
        const objValue = obj[key];

        if (isObject(prevValue) && isObject(objValue)) {
          // 递归合并嵌套对象
          prev[key] = this.deepMerge(prevValue, objValue);
        } else if (objValue !== undefined) {
          // 直接赋值（包括数组）
          prev[key] = objValue;
        }
      });

      return prev;
    }, {});
  }

  private normalizeAISettings(settings: AppSettings): AppSettings {
    const ai = settings.ai || this.getDefaultSettings().ai;
    const mergedProviders = this.mergeProviderSettings(ai.providers || {});
    const resolvedPrimaryProvider = this.resolvePrimaryProviderStorageKey(
      ai.primary_model?.provider,
      ai.currentProvider
    );
    const cachedConfig = aiService.getConfig();
    const cachedProviderKey = this.resolveCachedProviderStorageKey(cachedConfig?.provider, ai.currentProvider);

    const explicitProviderKeys = Object.keys(mergedProviders).filter((key) => {
      const providerConfig = mergedProviders[key];
      return providerConfig ? this.hasExplicitProviderConfig(key, providerConfig) : false;
    });

    if (explicitProviderKeys.length === 0 && cachedConfig && cachedProviderKey && (cachedConfig.apiKey || cachedConfig.provider === 'ollama')) {
      mergedProviders[cachedProviderKey] = {
        ...(mergedProviders[cachedProviderKey] || this.createProviderSettings(cachedProviderKey)),
        name: cachedConfig.name || this.getProviderDisplayName(cachedProviderKey),
        apiKey: cachedConfig.apiKey || '',
        model: cachedConfig.model || '',
        baseUrl: cachedConfig.baseUrl || '',
        useProxy: cachedConfig.useProxy || false,
        proxyType: cachedConfig.proxyType || 'http',
        proxyUrl: cachedConfig.proxyUrl || '',
      };
    }

    const primaryProviderKey = resolvedPrimaryProvider || ai.currentProvider || '';
    const currentProvider = this.resolvePreferredProvider(
      primaryProviderKey,
      mergedProviders,
      cachedProviderKey
    );
    const activeProviderConfig = mergedProviders[currentProvider] || this.createProviderSettings(currentProvider);

    mergedProviders[currentProvider] = {
      ...activeProviderConfig,
      name: activeProviderConfig.name || this.getProviderDisplayName(currentProvider),
      model: primaryProviderKey === currentProvider ? (ai.primary_model?.model ?? activeProviderConfig.model) : activeProviderConfig.model,
      baseUrl: primaryProviderKey === currentProvider ? (ai.primary_model?.base_url ?? activeProviderConfig.baseUrl) : activeProviderConfig.baseUrl,
      apiKey: primaryProviderKey === currentProvider ? (ai.primary_model?.api_key ?? activeProviderConfig.apiKey) : activeProviderConfig.apiKey,
    };

    settings.ai = {
      currentProvider,
      providers: mergedProviders,
      primary_model: this.buildPrimaryModelSettings(
        currentProvider,
        mergedProviders[currentProvider]
      ),
    };

    return settings;
  }

  private mergeProviderSettings(providers: Record<string, Partial<AIProviderSettings>>): Record<string, AIProviderSettings> {
    const defaultProviders = this.getDefaultSettings().ai.providers;
    const mergedProviders: Record<string, AIProviderSettings> = {};

    Object.entries(defaultProviders).forEach(([key, config]) => {
      mergedProviders[key] = {
        ...config,
        ...(providers[key] || {}),
      };
    });

    Object.entries(providers).forEach(([key, config]) => {
      mergedProviders[key] = {
        ...(mergedProviders[key] || this.createProviderSettings(key)),
        ...config,
        name: config.name || mergedProviders[key]?.name || this.getProviderDisplayName(key),
      };
    });

    return mergedProviders;
  }

  private buildPrimaryModelSettings(providerKey: string, config: AIProviderSettings | undefined): AIPrimaryModelSettings {
    const resolvedConfig = config || this.createProviderSettings(providerKey);
    const mappedProvider = this.mapProviderKeyToType(providerKey);

    return {
      provider: mappedProvider,
      model: resolvedConfig.model || '',
      api_key: resolvedConfig.apiKey || undefined,
      base_url: resolvedConfig.baseUrl || undefined,
    };
  }

  private createProviderSettings(key: string): AIProviderSettings {
    const defaultProvider = this.getDefaultSettings().ai.providers[key];
    if (defaultProvider) {
      return { ...defaultProvider };
    }

    return {
      name: this.getProviderDisplayName(key),
      apiKey: '',
      model: '',
      baseUrl: '',
      useProxy: false,
      proxyType: 'http',
      proxyUrl: '',
    };
  }

  private getProviderDisplayName(key: string): string {
    const normalizedKey = key.trim().toLowerCase();

    switch (normalizedKey) {
      case 'openai':
        return 'OpenAI';
      case 'deepseek':
        return 'DeepSeek';
      case 'claude':
        return 'Claude';
      case 'qwen':
        return 'Qwen';
      case 'ollama':
        return 'Ollama';
      case 'custom':
        return '自定义 API';
      default:
        return key || '自定义模型';
    }
  }

  private resolvePrimaryProviderStorageKey(primaryProvider: string | undefined, currentProvider: string | undefined): string {
    const normalizedPrimaryProvider = String(primaryProvider || '').trim().toLowerCase();

    if (!normalizedPrimaryProvider) {
      return currentProvider || '';
    }

    if (['openai', 'deepseek', 'claude', 'ollama', 'qwen', 'custom'].includes(normalizedPrimaryProvider)) {
      if (normalizedPrimaryProvider === 'custom' && currentProvider && !this.isPresetProvider(currentProvider)) {
        return currentProvider;
      }
      return normalizedPrimaryProvider;
    }

    if (currentProvider && !this.isPresetProvider(currentProvider)) {
      return currentProvider;
    }

    return 'custom';
  }

  private resolveCachedProviderStorageKey(provider: string | undefined, currentProvider: string | undefined): string {
    const normalizedProvider = String(provider || '').trim().toLowerCase();

    if (!normalizedProvider) {
      return '';
    }

    if (normalizedProvider !== 'custom') {
      return normalizedProvider;
    }

    if (currentProvider && !this.isPresetProvider(currentProvider)) {
      return currentProvider;
    }

    return 'custom';
  }

  private resolvePreferredProvider(
    primaryProviderKey: string,
    providers: Record<string, AIProviderSettings>,
    cachedProviderKey: string
  ): string {
    const candidates = [
      primaryProviderKey,
      ...Object.keys(providers),
      cachedProviderKey,
    ].filter(Boolean);

    for (const candidate of candidates) {
      const providerConfig = providers[candidate];
      if (providerConfig && this.hasExplicitProviderConfig(candidate, providerConfig)) {
        return candidate;
      }
    }

    return primaryProviderKey || cachedProviderKey || 'openai';
  }

  private hasExplicitProviderConfig(key: string, config: AIProviderSettings): boolean {
    const defaultConfig = this.getDefaultProviderConfig(key);
    const providerType = this.mapProviderKeyToType(key);

    if (providerType === 'ollama') {
      return Boolean(
        config.model !== defaultConfig.model
        || config.baseUrl !== defaultConfig.baseUrl
        || config.useProxy
        || config.proxyUrl
      );
    }

    return Boolean(config.apiKey.trim());
  }

  private getDefaultProviderConfig(key: string): Pick<AIProviderSettings, 'model' | 'baseUrl'> {
    switch (key) {
      case 'openai':
        return { model: 'gpt-4o-mini', baseUrl: 'https://api.openai.com/v1' };
      case 'deepseek':
        return { model: 'deepseek-chat', baseUrl: 'https://api.deepseek.com/v1' };
      case 'claude':
        return { model: 'claude-3-5-sonnet-latest', baseUrl: 'https://api.anthropic.com/v1' };
      case 'qwen':
        return { model: 'qwen-turbo', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' };
      case 'ollama':
        return { model: 'llama3.1', baseUrl: 'http://localhost:11434/api' };
      default:
        return { model: '', baseUrl: '' };
    }
  }

  private isPresetProvider(key: string): boolean {
    return ['openai', 'deepseek', 'claude', 'ollama', 'qwen', 'custom'].includes(key);
  }

  /**
   * 验证设置格式
   */
  private validateSettings(settings: any): boolean {
    // 基本验证
    if (typeof settings !== 'object' || settings === null) {
      return false;
    }

    // 验证主题
    if (settings.theme && !['light', 'dark'].includes(settings.theme)) {
      return false;
    }

    // 验证语言
    if (settings.language && !['zh-CN', 'en-US'].includes(settings.language)) {
      return false;
    }

    // 验证数字类型
    const numberFields = ['defaultSSHPort', 'terminalFontSize', 'maxLogLines', 'autoSaveInterval'];
    for (const field of numberFields) {
      if (settings[field] !== undefined && typeof settings[field] !== 'number') {
        return false;
      }
    }

    return true;
  }

  private notifyListeners(): void {
    this.emit(this.getSettings());
    this.applySettingsToUI();
  }

  /**
   * 应用设置到界面
   */
  private applySettingsToUI(): void {
    try {
      const defaultFontStack = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif';
      const selectedFont = this.settings.terminalFont && this.settings.terminalFont !== 'system'
        ? `"${this.settings.terminalFont}", ${defaultFontStack}`
        : defaultFontStack;
      const fontSize = `${this.settings.terminalFontSize || 14}px`;

      document.documentElement.style.setProperty(
        '--font-family',
        selectedFont
      );
      document.documentElement.style.setProperty('--font-size', fontSize);
      document.body.style.fontFamily = selectedFont;
      document.body.style.fontSize = fontSize;

      let style = document.getElementById('LERT-user-font-settings') as HTMLStyleElement | null;
      if (!style) {
        style = document.createElement('style');
        style.id = 'LERT-user-font-settings';
        document.head.appendChild(style);
      }
      style.textContent = `
        body,
        button,
        input,
        select,
        textarea,
        .main-workspace,
        .workspace-content,
        .settings-page,
        .modern-btn {
          font-family: var(--font-family) !important;
          font-size: var(--font-size) !important;
        }
      `;

      console.log('✅ 设置已应用到界面');
    } catch (error) {
      console.error('❌ 应用设置失败:', error);
    }
  }

  applyCurrentSettingsToUI(): void {
    this.applySettingsToUI();
  }

  /**
   * 获取主题相关设置
   */
  getThemeSettings() {
    return {
      theme: this.settings.theme,
      animationsEnabled: this.settings.ui.animationsEnabled,
      compactMode: this.settings.ui.compactMode
    };
  }

  /**
   * 获取UI相关设置
   */
  getUISettings() {
    return {
      ...this.settings.ui,
      theme: this.settings.theme,
      language: this.settings.language
    };
  }

  /**
   * 获取安全相关设置
   */
  getSecuritySettings() {
    return { ...this.settings.security };
  }

  /**
   * 获取通知相关设置
   */
  getNotificationSettings() {
    return { ...this.settings.notifications };
  }

  /**
   * 获取SSH相关设置
   */
  getSSHSettings() {
    return {
      ...this.settings.ssh,
      defaultPort: this.settings.defaultSSHPort,
      autoConnect: this.settings.autoConnect
    };
  }

  /**
   * 获取Docker相关设置
   */
  getDockerSettings() {
    return {};
  }

  /**
   * 获取终端相关设置
   */
  getTerminalSettings() {
    return {
      font: this.settings.terminalFont,
      fontSize: this.settings.terminalFontSize,
      maxLogLines: this.settings.maxLogLines
    };
  }

  /**
   * 检查是否启用了特定功能
   */
  isFeatureEnabled(feature: string): boolean {
    switch (feature) {
      case 'notifications':
        return this.settings.notifications.enabled;
      case 'animations':
        return this.settings.ui.animationsEnabled;
      case 'autoConnect':
        return this.settings.autoConnect;
      default:
        return false;
    }
  }

  /**
   * 切换功能开关
   */
  toggleFeature(feature: string): boolean {
    switch (feature) {
      case 'notifications':
        this.settings.notifications.enabled = !this.settings.notifications.enabled;
        return this.settings.notifications.enabled;
      case 'animations':
        this.settings.ui.animationsEnabled = !this.settings.ui.animationsEnabled;
        return this.settings.ui.animationsEnabled;
      case 'autoConnect':
        this.settings.autoConnect = !this.settings.autoConnect;
        return this.settings.autoConnect;
      default:
        return false;
    }
  }
}
