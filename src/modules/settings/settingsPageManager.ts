/**
 * AI 配置页面管理器
 * 负责独立 AI 配置菜单的交互逻辑和表单同步
 */

import { SettingsManager, type AIProviderSettings, type AISettings } from './settingsManager';
import { aiService, AIProvider } from '../ai/aiService';

type ProxyType = 'http' | 'https' | 'socks5';

export class SettingsPageManager {
  private settingsManager: SettingsManager;
  private readonly presetProviders = ['openai', 'deepseek', 'claude', 'qwen', 'ollama', 'custom'];
  private activeProviderKey = 'openai';

  constructor(settingsManager: SettingsManager) {
    this.settingsManager = settingsManager;
  }

  async initialize(): Promise<void> {
    try {
      console.log('🔧 初始化 AI 配置页面...');
      this.bindEventListeners();
      await this.settingsManager.loadSettings();
      this.loadSettingsToForm();
      console.log('✅ AI 配置页面初始化完成');
    } catch (error) {
      console.error('❌ AI 配置页面初始化失败:', error);
    }
  }

  private bindEventListeners(): void {
    document.getElementById('save-settings')?.addEventListener('click', () => {
      this.saveSettings();
    });

    const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
    aiProviderSelect?.addEventListener('change', () => {
      this.switchAIProvider();
    });

    const configuredModelsList = document.getElementById('configured-models-list');
    configuredModelsList?.addEventListener('click', (event) => {
      const switchButton = (event.target as HTMLElement | null)?.closest('[data-provider-switch]');
      if (!switchButton) {
        return;
      }

      const providerKey = switchButton.getAttribute('data-provider-switch');
      if (providerKey) {
        this.selectProvider(providerKey);
      }
    });

    const useProxyCheckbox = document.getElementById('ai-use-proxy') as HTMLInputElement | null;
    useProxyCheckbox?.addEventListener('change', () => {
      this.toggleProxySettings();
    });

    document.getElementById('test-ai-connection')?.addEventListener('click', () => {
      this.testAIConnection();
    });

    document.getElementById('add-ai-provider')?.addEventListener('click', () => {
      this.showAddProviderModal();
    });

    document.getElementById('delete-ai-provider')?.addEventListener('click', () => {
      this.deleteCurrentProvider();
    });

    document.getElementById('close-add-provider-modal')?.addEventListener('click', () => {
      this.hideAddProviderModal();
    });

    document.getElementById('cancel-add-provider')?.addEventListener('click', () => {
      this.hideAddProviderModal();
    });

    document.getElementById('add-provider-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      this.saveNewProvider();
    });

    const addProviderModal = document.getElementById('add-provider-modal');
    addProviderModal?.addEventListener('click', (event) => {
      if (event.target === addProviderModal) {
        this.hideAddProviderModal();
      }
    });
  }

  private loadSettingsToForm(): void {
    const settings = this.settingsManager.getSettings();
    const aiSettings = this.ensureAISettings(settings);

    this.updateProviderSelector();

    const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
    if (aiProviderSelect && aiSettings.currentProvider) {
      aiProviderSelect.value = aiSettings.currentProvider;
    }

    this.activeProviderKey = aiSettings.currentProvider || 'openai';
    this.loadCurrentProviderConfig();
    this.renderConfiguredModels();
    this.updateDeleteButtonVisibility();
  }

  private async saveSettings(): Promise<void> {
    const saveButton = document.getElementById('save-settings') as HTMLButtonElement | null;

    try {
      console.log('💾 正在保存 AI 配置...');
      this.persistCurrentFormToSettings();

      if (saveButton) {
        saveButton.disabled = true;
        saveButton.textContent = '保存中...';
      }

      const formData = this.collectFormData();
      this.settingsManager.updateSettings(formData);
      await this.settingsManager.saveSettings();

      const currentProvider = formData.ai?.currentProvider || 'openai';
      const providerConfig = formData.ai?.providers?.[currentProvider];

      if (providerConfig) {
        const mappedProvider = this.mapProviderKeyToType(currentProvider);
        aiService.saveConfig({
          provider: mappedProvider,
          name: providerConfig.name,
          apiKey: providerConfig.apiKey,
          baseUrl: providerConfig.baseUrl || '',
          model: providerConfig.model || '',
          useProxy: providerConfig.useProxy || false,
          proxyType: providerConfig.proxyType || 'http',
          proxyUrl: providerConfig.proxyUrl || '',
        });

        this.syncAIConfigToBackend(mappedProvider, providerConfig).catch((error) => {
          console.warn('⚠️ 同步 AI 配置到后端失败（不影响前端功能）:', error);
        });
      }

      (window as any).app?.modernUIRenderer?.syncSettingsDropdownState?.();
      this.showMessage('AI 配置保存成功！', 'success');

      setTimeout(() => {
        (window as any).hideSettingsOverlay?.();
      }, 800);
    } catch (error) {
      console.error('❌ 保存 AI 配置失败:', error);
      this.showMessage(`保存失败: ${error}`, 'error');
    } finally {
      if (saveButton) {
        saveButton.disabled = false;
        saveButton.textContent = '保存配置';
      }
    }
  }

  private async syncAIConfigToBackend(provider: string, config: any): Promise<void> {
    try {
      const baseUrl = import.meta.env.DEV ? '/api/v1' : 'http://127.0.0.1:3001/api/v1';
      const settingsResp = await fetch(`${baseUrl}/settings`);
      const settingsObj = await settingsResp.json();

      if (!settingsObj.ai) {
        settingsObj.ai = { primary_model: {} };
      }
      if (!settingsObj.ai.primary_model) {
        settingsObj.ai.primary_model = {};
      }

      settingsObj.ai.primary_model.provider = provider;
      settingsObj.ai.primary_model.model = config.model || 'gpt-4o-mini';
      settingsObj.ai.primary_model.api_key = config.apiKey;
      if (config.baseUrl) {
        settingsObj.ai.primary_model.base_url = config.baseUrl;
      } else {
        delete settingsObj.ai.primary_model.base_url;
      }

      if (!settingsObj.agent) settingsObj.agent = {};
      if (!settingsObj.agent.planner_model) settingsObj.agent.planner_model = {};

      settingsObj.agent.planner_model.provider = provider;
      settingsObj.agent.planner_model.model_name = config.model || 'gpt-4o-mini';
      settingsObj.agent.planner_model.api_key = config.apiKey;
      if (config.baseUrl) {
        settingsObj.agent.planner_model.base_url = config.baseUrl;
      } else {
        delete settingsObj.agent.planner_model.base_url;
      }

      await fetch(`${baseUrl}/settings/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: settingsObj }),
      });

      console.log('✅ AI 配置已同步到后端（ai.primary_model + agent.planner_model）');
    } catch (error) {
      console.warn('⚠️ 同步 AI 配置到后端失败（不影响聊天功能）:', error);
    }
  }

  private collectFormData(): any {
    const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
    const apiKeyInput = document.getElementById('ai-api-key') as HTMLInputElement | null;
    const modelInput = document.getElementById('ai-model') as HTMLInputElement | null;
    const baseUrlInput = document.getElementById('ai-base-url') as HTMLInputElement | null;
    const useProxyCheckbox = document.getElementById('ai-use-proxy') as HTMLInputElement | null;
    const proxyTypeSelect = document.getElementById('ai-proxy-type') as HTMLSelectElement | null;
    const proxyUrlInput = document.getElementById('ai-proxy-url') as HTMLInputElement | null;

    const currentProvider = aiProviderSelect?.value || 'openai';
    const settings = this.settingsManager.getSettings();
    const aiSettings = this.ensureAISettings(settings);

    const updatedProviders = { ...aiSettings.providers };
    if (updatedProviders[currentProvider]) {
      updatedProviders[currentProvider] = {
        ...updatedProviders[currentProvider],
        apiKey: apiKeyInput?.value || '',
        model: modelInput?.value || '',
        baseUrl: baseUrlInput?.value || '',
        useProxy: useProxyCheckbox?.checked || false,
        proxyType: (proxyTypeSelect?.value as ProxyType) || 'http',
        proxyUrl: proxyUrlInput?.value || '',
      };
    }

    return {
      ai: {
        currentProvider,
        providers: updatedProviders,
      },
    };
  }

  private switchAIProvider(): void {
    const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
    const nextProvider = aiProviderSelect?.value || 'openai';
    this.selectProvider(nextProvider);
  }

  private loadCurrentProviderConfig(): void {
    const settings = this.settingsManager.getSettings();
    const aiSettings = this.ensureAISettings(settings);

    const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
    const currentProvider = aiProviderSelect?.value || aiSettings.currentProvider;
    const providerConfig = aiSettings.providers[currentProvider];

    if (!providerConfig) {
      return;
    }

    this.activeProviderKey = currentProvider;

    const apiKeyInput = document.getElementById('ai-api-key') as HTMLInputElement | null;
    const modelInput = document.getElementById('ai-model') as HTMLInputElement | null;
    const baseUrlInput = document.getElementById('ai-base-url') as HTMLInputElement | null;
    const useProxyCheckbox = document.getElementById('ai-use-proxy') as HTMLInputElement | null;
    const proxyTypeSelect = document.getElementById('ai-proxy-type') as HTMLSelectElement | null;
    const proxyUrlInput = document.getElementById('ai-proxy-url') as HTMLInputElement | null;

    if (apiKeyInput) apiKeyInput.value = providerConfig.apiKey || '';
    if (modelInput) modelInput.value = providerConfig.model || '';
    if (baseUrlInput) baseUrlInput.value = providerConfig.baseUrl || '';
    if (useProxyCheckbox) useProxyCheckbox.checked = providerConfig.useProxy || false;
    if (proxyTypeSelect) proxyTypeSelect.value = providerConfig.proxyType || 'http';
    if (proxyUrlInput) proxyUrlInput.value = providerConfig.proxyUrl || '';

    this.updateInputPlaceholders(currentProvider, apiKeyInput, modelInput, baseUrlInput);
    this.toggleProxySettings();
  }

  private updateInputPlaceholders(
    provider: string,
    apiKeyInput: HTMLInputElement | null,
    modelInput: HTMLInputElement | null,
    baseUrlInput: HTMLInputElement | null
  ): void {
    if (!apiKeyInput || !modelInput || !baseUrlInput) {
      return;
    }

    switch (provider) {
      case 'openai':
        apiKeyInput.placeholder = '输入您的 OpenAI API Key (sk-...)';
        modelInput.placeholder = '例如: gpt-4o-mini';
        baseUrlInput.placeholder = '例如: https://api.openai.com/v1';
        break;
      case 'deepseek':
        apiKeyInput.placeholder = '输入您的 DeepSeek API Key';
        modelInput.placeholder = '例如: deepseek-chat';
        baseUrlInput.placeholder = '例如: https://api.deepseek.com/v1';
        break;
      case 'claude':
        apiKeyInput.placeholder = '输入您的 Claude API Key (sk-ant-...)';
        modelInput.placeholder = '例如: claude-3-5-sonnet-latest';
        baseUrlInput.placeholder = '例如: https://api.anthropic.com/v1';
        break;
      case 'qwen':
        apiKeyInput.placeholder = '输入您的通义千问 API Key';
        modelInput.placeholder = '例如: qwen-turbo';
        baseUrlInput.placeholder = '例如: https://dashscope.aliyuncs.com/compatible-mode/v1';
        break;
      case 'ollama':
        apiKeyInput.placeholder = 'Ollama 通常无需 API Key，可留空';
        modelInput.placeholder = '例如: llama3.1';
        baseUrlInput.placeholder = '例如: http://localhost:11434/api';
        break;
      case 'custom':
        apiKeyInput.placeholder = '输入您的自定义 API Key';
        modelInput.placeholder = '例如: 自定义模型名';
        baseUrlInput.placeholder = '例如: https://your-endpoint/v1';
        break;
      default:
        apiKeyInput.placeholder = '输入您的 AI API Key';
        modelInput.placeholder = '例如: 自定义模型名';
        baseUrlInput.placeholder = '例如: https://your-endpoint/v1';
        break;
    }
  }

  private toggleProxySettings(): void {
    const useProxyCheckbox = document.getElementById('ai-use-proxy') as HTMLInputElement | null;
    const proxySettingsDiv = document.getElementById('ai-proxy-settings') as HTMLDivElement | null;

    if (useProxyCheckbox && proxySettingsDiv) {
      proxySettingsDiv.style.display = useProxyCheckbox.checked ? 'block' : 'none';
    }
  }

  private async testAIConnection(): Promise<void> {
    const testButton = document.getElementById('test-ai-connection') as HTMLButtonElement | null;
    const statusSpan = document.getElementById('ai-test-status') as HTMLSpanElement | null;
    const resultDiv = document.getElementById('ai-test-result') as HTMLDivElement | null;

    if (!testButton || !statusSpan || !resultDiv) {
      return;
    }

    try {
      testButton.disabled = true;
      testButton.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="animation: spin 1s linear infinite;">
          <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z"/>
        </svg>
        测试中...
      `;
      statusSpan.textContent = '正在测试连接...';
      statusSpan.style.color = 'var(--text-secondary)';
      resultDiv.style.display = 'none';

      const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
      const apiKeyInput = document.getElementById('ai-api-key') as HTMLInputElement | null;
      const modelInput = document.getElementById('ai-model') as HTMLInputElement | null;
      const baseUrlInput = document.getElementById('ai-base-url') as HTMLInputElement | null;

      const provider = aiProviderSelect?.value || 'openai';
      const apiKey = apiKeyInput?.value || '';
      const model = modelInput?.value || '';
      const baseUrl = baseUrlInput?.value || '';

      if (!apiKey && provider !== 'ollama') {
        throw new Error('请先输入 API Key');
      }

      const testResult = await this.performAITest(provider, apiKey, model, baseUrl);

      statusSpan.textContent = '连接测试成功！';
      statusSpan.style.color = '#22c55e';
      resultDiv.textContent = `AI回复: ${testResult}`;
      resultDiv.style.display = 'block';
      resultDiv.style.borderColor = '#22c55e';
    } catch (error) {
      statusSpan.textContent = '连接测试失败';
      statusSpan.style.color = '#ef4444';
      resultDiv.textContent = `错误: ${error}`;
      resultDiv.style.display = 'block';
      resultDiv.style.borderColor = '#ef4444';
    } finally {
      testButton.disabled = false;
      testButton.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
        </svg>
        测试连接
      `;
    }
  }

  private async performAITest(provider: string, apiKey: string, model: string, baseUrl: string): Promise<string> {
    const previousConfig = aiService.getConfig();

    try {
      const mappedProvider = this.mapProviderKeyToType(provider);
      aiService.saveConfig({
        provider: mappedProvider,
        apiKey,
        baseUrl: baseUrl || '',
        model: model || '',
      });

      return await aiService.testConnection();
    } catch (error: any) {
      throw new Error(error.message || 'AI API 连接失败');
    } finally {
      if (previousConfig) {
        aiService.saveConfig(previousConfig);
      } else {
        aiService.clearConfig();
      }
    }
  }

  private showMessage(message: string, type: 'success' | 'error'): void {
    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 12px 20px;
      border-radius: 6px;
      color: white;
      font-size: 14px;
      z-index: 10002;
      animation: slideIn 0.3s ease-out;
      background: ${type === 'success' ? '#22c55e' : '#ef4444'};
    `;

    if (!document.getElementById('settings-animations')) {
      const style = document.createElement('style');
      style.id = 'settings-animations';
      style.textContent = `
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `;
      document.head.appendChild(style);
    }

    messageDiv.textContent = message;
    document.body.appendChild(messageDiv);

    setTimeout(() => {
      messageDiv.remove();
    }, 3000);
  }

  private updateProviderSelector(): void {
    const settings = this.settingsManager.getSettings();
    const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;

    if (!aiProviderSelect) {
      return;
    }

    const currentValue = aiProviderSelect.value;
    aiProviderSelect.innerHTML = '';
    const aiSettings = this.ensureAISettings(settings);

    Object.entries(aiSettings.providers).forEach(([key, provider]) => {
      const option = document.createElement('option');
      option.value = key;
      option.textContent = provider.name;
      aiProviderSelect.appendChild(option);
    });

    if (currentValue && aiSettings.providers[currentValue]) {
      aiProviderSelect.value = currentValue;
    } else {
      aiProviderSelect.value = aiSettings.currentProvider;
    }
  }

  private ensureAISettings(settings: { ai?: AISettings }): AISettings {
    if (!settings.ai) {
      settings.ai = { currentProvider: 'openai', providers: {} };
    }

    if (!settings.ai.providers) {
      settings.ai.providers = {};
    }

    if (!settings.ai.currentProvider) {
      settings.ai.currentProvider = 'openai';
    }

    return settings.ai;
  }

  private selectProvider(providerKey: string): void {
    const settings = this.settingsManager.getSettings();
    const aiSettings = this.ensureAISettings(settings);

    if (!aiSettings.providers[providerKey]) {
      return;
    }

    this.persistCurrentFormToSettings();

    aiSettings.currentProvider = providerKey;
    this.syncPrimaryModelSelection(aiSettings, providerKey);
    this.settingsManager.updateSettings({ ai: aiSettings });

    const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
    if (aiProviderSelect) {
      aiProviderSelect.value = providerKey;
    }

    this.activeProviderKey = providerKey;
    this.loadCurrentProviderConfig();
    this.renderConfiguredModels();
    this.updateDeleteButtonVisibility();
  }

  private persistCurrentFormToSettings(): void {
    const settings = this.settingsManager.getSettings();
    const aiSettings = this.ensureAISettings(settings);
    const providerKey = this.activeProviderKey || aiSettings.currentProvider;

    if (!providerKey || !aiSettings.providers[providerKey]) {
      return;
    }

    const apiKeyInput = document.getElementById('ai-api-key') as HTMLInputElement | null;
    const modelInput = document.getElementById('ai-model') as HTMLInputElement | null;
    const baseUrlInput = document.getElementById('ai-base-url') as HTMLInputElement | null;
    const useProxyCheckbox = document.getElementById('ai-use-proxy') as HTMLInputElement | null;
    const proxyTypeSelect = document.getElementById('ai-proxy-type') as HTMLSelectElement | null;
    const proxyUrlInput = document.getElementById('ai-proxy-url') as HTMLInputElement | null;

    aiSettings.providers[providerKey] = {
      ...aiSettings.providers[providerKey],
      apiKey: apiKeyInput?.value || '',
      model: modelInput?.value || '',
      baseUrl: baseUrlInput?.value || '',
      useProxy: useProxyCheckbox?.checked || false,
      proxyType: (proxyTypeSelect?.value as ProxyType) || 'http',
      proxyUrl: proxyUrlInput?.value || '',
    };

    aiSettings.currentProvider = providerKey;
    this.syncPrimaryModelSelection(aiSettings, providerKey);
    this.settingsManager.updateSettings({ ai: aiSettings });
  }

  private renderConfiguredModels(): void {
    const container = document.getElementById('configured-models-list');
    const countBadge = document.getElementById('configured-models-count');

    if (!container || !countBadge) {
      return;
    }

    const settings = this.settingsManager.getSettings();
    const aiSettings = this.ensureAISettings(settings);
    const currentProvider = this.activeProviderKey || aiSettings.currentProvider;
    const providerEntries = Object.entries(aiSettings.providers)
      .filter(([key, config]) => this.shouldDisplayProviderCard(key, config, currentProvider))
      .sort(([leftKey, leftConfig], [rightKey, rightConfig]) => {
        if (leftKey === currentProvider) {
          return -1;
        }
        if (rightKey === currentProvider) {
          return 1;
        }
        const leftReady = this.isProviderConfigured(leftKey, leftConfig);
        const rightReady = this.isProviderConfigured(rightKey, rightConfig);
        if (leftReady !== rightReady) {
          return leftReady ? -1 : 1;
        }
        return leftConfig.name.localeCompare(rightConfig.name, 'zh-CN');
      });

    countBadge.textContent = `${providerEntries.length} 个`;

    if (providerEntries.length === 0) {
      container.innerHTML = `
        <div style="
          padding: 14px 16px;
          border: 1px dashed var(--border-color);
          border-radius: var(--border-radius);
          background: var(--bg-primary);
          color: var(--text-secondary);
          font-size: 13px;
          line-height: 1.6;
        ">当前还没有可展示的模型配置。填写下方表单并保存后，这里会自动显示模型详情。</div>
      `;
      return;
    }

    container.innerHTML = providerEntries.map(([key, config]) => {
      const isCurrent = key === currentProvider;
      const isConfigured = this.isProviderConfigured(key, config);
      const readinessStyle = isConfigured
        ? 'background: rgba(34, 197, 94, 0.14); color: #16a34a;'
        : 'background: rgba(245, 158, 11, 0.14); color: #d97706;';
      const currentStyle = isCurrent
        ? 'background: rgba(59, 130, 246, 0.14); color: #2563eb;'
        : 'background: var(--bg-primary); color: var(--text-secondary); border: 1px solid var(--border-color);';
      const switchButtonStyle = isCurrent
        ? 'background: var(--bg-secondary); color: var(--text-secondary); cursor: default;'
        : 'background: var(--primary-color); color: white; cursor: pointer;';

      return `
        <div style="
          border: 1px solid ${isCurrent ? 'rgba(59, 130, 246, 0.35)' : 'var(--border-color)'};
          border-radius: var(--border-radius-lg);
          background: var(--bg-primary);
          padding: 14px 16px;
          box-shadow: ${isCurrent ? '0 8px 20px rgba(59, 130, 246, 0.08)' : 'none'};
        ">
          <div style="
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 12px;
            flex-wrap: wrap;
          ">
            <div style="min-width: 0; flex: 1;">
              <div style="
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 6px;
                flex-wrap: wrap;
              ">
                <strong style="
                  color: var(--text-primary);
                  font-size: 14px;
                ">${this.escapeHtml(config.name)}</strong>
                <span style="
                  padding: 2px 8px;
                  border-radius: 999px;
                  font-size: 11px;
                  font-weight: 600;
                  ${readinessStyle}
                ">${isConfigured ? '可直接使用' : '待完善'}</span>
                <span style="
                  padding: 2px 8px;
                  border-radius: 999px;
                  font-size: 11px;
                  font-weight: 600;
                  ${currentStyle}
                ">${isCurrent ? '当前使用' : '备用模型'}</span>
              </div>
              <div style="
                color: var(--text-primary);
                font-size: 13px;
                font-weight: 600;
                word-break: break-all;
              ">${this.escapeHtml(config.model || '未填写模型名称')}</div>
            </div>
            <button
              type="button"
              data-provider-switch="${this.escapeHtml(key)}"
              ${isCurrent ? 'disabled' : ''}
              style="
                border: none;
                border-radius: var(--border-radius);
                padding: 8px 12px;
                font-size: 12px;
                font-weight: 600;
                white-space: nowrap;
                ${switchButtonStyle}
              "
            >${isCurrent ? '当前编辑中' : '切换并编辑'}</button>
          </div>

          <div style="
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px 12px;
          ">
            ${this.renderProviderDetail('提供商', config.name)}
            ${this.renderProviderDetail('Base URL', config.baseUrl || '未填写')}
            ${this.renderProviderDetail('API Key', this.maskApiKey(config.apiKey))}
            ${this.renderProviderDetail(
              '代理',
              config.useProxy
                ? `${config.proxyType.toUpperCase()} · ${config.proxyUrl || '未填写代理地址'}`
                : '未启用'
            )}
          </div>
        </div>
      `;
    }).join('');
  }

  private renderProviderDetail(label: string, value: string): string {
    return `
      <div style="
        min-width: 0;
        padding: 10px 12px;
        border-radius: var(--border-radius);
        background: var(--bg-secondary);
      ">
        <div style="
          color: var(--text-secondary);
          font-size: 12px;
          margin-bottom: 4px;
        ">${this.escapeHtml(label)}</div>
        <div style="
          color: var(--text-primary);
          font-size: 12px;
          line-height: 1.5;
          word-break: break-all;
        ">${this.escapeHtml(value)}</div>
      </div>
    `;
  }

  private shouldDisplayProviderCard(
    key: string,
    config: AIProviderSettings,
    currentProvider: string
  ): boolean {
    return this.hasExplicitProviderConfig(key, config)
      || (key === currentProvider && this.isProviderConfigured(key, config));
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

  private isProviderConfigured(key: string, config: AIProviderSettings): boolean {
    return Boolean(
      config.model
      && config.baseUrl
      && (this.mapProviderKeyToType(key) === 'ollama' || config.apiKey)
    );
  }

  private syncPrimaryModelSelection(aiSettings: AISettings, providerKey: string): void {
    const providerConfig = aiSettings.providers[providerKey];
    if (!providerConfig) {
      return;
    }

    aiSettings.primary_model = {
      provider: this.mapProviderKeyToType(providerKey),
      model: providerConfig.model || '',
      api_key: providerConfig.apiKey || undefined,
      base_url: providerConfig.baseUrl || undefined,
    };
  }

  private maskApiKey(apiKey: string): string {
    if (!apiKey) {
      return '未填写';
    }

    if (apiKey.length <= 8) {
      return `${apiKey.slice(0, 2)}***${apiKey.slice(-2)}`;
    }

    return `${apiKey.slice(0, 4)}••••••${apiKey.slice(-4)}`;
  }

  private escapeHtml(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  private showAddProviderModal(): void {
    const modal = document.getElementById('add-provider-modal');
    if (!modal) {
      return;
    }

    modal.style.display = 'flex';
    const form = document.getElementById('add-provider-form') as HTMLFormElement | null;
    form?.reset();

    const nameInput = document.getElementById('new-provider-name') as HTMLInputElement | null;
    if (nameInput) {
      setTimeout(() => nameInput.focus(), 100);
    }
  }

  private hideAddProviderModal(): void {
    const modal = document.getElementById('add-provider-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  private async saveNewProvider(): Promise<void> {
    try {
      const nameInput = document.getElementById('new-provider-name') as HTMLInputElement | null;
      const apiKeyInput = document.getElementById('new-provider-api-key') as HTMLInputElement | null;
      const modelInput = document.getElementById('new-provider-model') as HTMLInputElement | null;
      const baseUrlInput = document.getElementById('new-provider-base-url') as HTMLInputElement | null;

      const name = nameInput?.value?.trim();
      const apiKey = apiKeyInput?.value?.trim() || '';
      const model = modelInput?.value?.trim() || '';
      const baseUrl = baseUrlInput?.value?.trim() || '';

      if (!name) {
        this.showMessage('请输入提供商名称', 'error');
        return;
      }

      const settings = this.settingsManager.getSettings();
      const aiSettings = this.ensureAISettings(settings);
      const existingNames = Object.values(aiSettings.providers).map((provider) => provider.name.toLowerCase());

      if (existingNames.includes(name.toLowerCase())) {
        this.showMessage('提供商名称已存在', 'error');
        return;
      }

      const key = this.generateProviderKey(name);
      aiSettings.providers[key] = {
        name,
        apiKey,
        model,
        baseUrl,
        useProxy: false,
        proxyType: 'http',
        proxyUrl: '',
      };
      aiSettings.currentProvider = key;
      this.syncPrimaryModelSelection(aiSettings, key);

      this.settingsManager.updateSettings({ ai: aiSettings });
      await this.settingsManager.saveSettings();

      this.updateProviderSelector();
      this.activeProviderKey = key;
      this.loadCurrentProviderConfig();
      this.renderConfiguredModels();
      this.updateDeleteButtonVisibility();
      this.hideAddProviderModal();
      (window as any).app?.modernUIRenderer?.syncSettingsDropdownState?.();

      this.showMessage(`提供商 "${name}" 添加成功！`, 'success');
    } catch (error) {
      console.error('❌ 保存新提供商失败:', error);
      this.showMessage(`保存失败: ${error}`, 'error');
    }
  }

  private generateProviderKey(name: string): string {
    const base = name.toLowerCase()
      .replace(/[^a-z0-9]/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_|_$/g, '');

    return `${base}_${Date.now().toString().slice(-6)}`;
  }

  private isPresetProvider(key: string): boolean {
    return this.presetProviders.includes(key);
  }

  private mapProviderKeyToType(key: string): AIProvider {
    if (this.isPresetProvider(key)) {
      return key as AIProvider;
    }
    return 'custom';
  }

  private updateDeleteButtonVisibility(): void {
    const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
    const deleteButton = document.getElementById('delete-ai-provider') as HTMLButtonElement | null;

    if (!aiProviderSelect || !deleteButton) {
      return;
    }

    deleteButton.style.display = this.isPresetProvider(aiProviderSelect.value) ? 'none' : 'flex';
  }

  private async deleteCurrentProvider(): Promise<void> {
    try {
      const aiProviderSelect = document.getElementById('ai-provider') as HTMLSelectElement | null;
      if (!aiProviderSelect) {
        return;
      }

      const currentProvider = aiProviderSelect.value;
      if (this.isPresetProvider(currentProvider)) {
        this.showMessage('预设提供商不能删除', 'error');
        return;
      }

      const settings = this.settingsManager.getSettings();
      const aiSettings = this.ensureAISettings(settings);
      const providerName = aiSettings.providers[currentProvider]?.name || currentProvider;

      if (!confirm(`确定要删除提供商 "${providerName}" 吗？此操作不可撤销。`)) {
        return;
      }

      delete aiSettings.providers[currentProvider];
      aiSettings.currentProvider = 'openai';
      this.syncPrimaryModelSelection(aiSettings, 'openai');

      this.settingsManager.updateSettings({ ai: aiSettings });
      await this.settingsManager.saveSettings();

      this.updateProviderSelector();
      this.activeProviderKey = 'openai';
      this.loadCurrentProviderConfig();
      this.renderConfiguredModels();
      this.updateDeleteButtonVisibility();
      (window as any).app?.modernUIRenderer?.syncSettingsDropdownState?.();

      this.showMessage(`提供商 "${providerName}" 已删除`, 'success');
    } catch (error) {
      console.error('❌ 删除提供商失败:', error);
      this.showMessage(`删除失败: ${error}`, 'error');
    }
  }
}
