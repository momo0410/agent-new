import { invoke } from '../../shims/@tauri-apps/api/core'
import * as IconPark from '@icon-park/svg'
import { callAIAnalysisViaProxyStream, renderAIAnalysisContent } from '../utils/aiProxy'

export abstract class BaseContextMenu {
  protected contextMenu: HTMLElement | null = null
  protected modal: HTMLElement | null = null
  protected selectedUsername: string = ''
  protected accounts: any[] = []

  protected abstract idPrefix: string
  protected abstract menuId: string
  protected abstract modalId: string
  protected abstract accountSelectId: string
  protected abstract aiExpertRole: string
  protected abstract aiInfoType: string

  protected get modalTitleId() { return `${this.idPrefix}-modal-title` }
  protected get modalContentId() { return `${this.idPrefix}-modal-content` }
  protected get modalCloseId() { return `${this.idPrefix}-modal-close` }
  protected get aiExplainBtnId() { return `${this.idPrefix}-ai-explain-btn` }
  protected get aiExplanationId() { return `${this.idPrefix}-ai-explanation` }
  protected get aiExplanationContentId() { return `${this.idPrefix}-ai-explanation-content` }

  hideContextMenu() {
    if (this.contextMenu) {
      this.contextMenu.style.display = 'none'
    }
  }

  showModal(title: string, content: string) {
    if (!this.modal) return

    const titleEl = document.getElementById(this.modalTitleId)
    const contentEl = document.getElementById(this.modalContentId)
    const explanationEl = document.getElementById(this.aiExplanationId)

    if (titleEl) titleEl.textContent = title
    if (contentEl) contentEl.textContent = content

    if (explanationEl) {
      explanationEl.style.display = 'none'
      const explanationContentEl = document.getElementById(this.aiExplanationContentId)
      if (explanationContentEl) {
        explanationContentEl.textContent = ''
      }
    }

    this.modal.style.display = 'flex'
  }

  hideModal() {
    if (this.modal) {
      this.modal.style.display = 'none'

      const explanationEl = document.getElementById(this.aiExplanationId)
      if (explanationEl) {
        explanationEl.style.display = 'none'
        const explanationContentEl = document.getElementById(this.aiExplanationContentId)
        if (explanationContentEl) {
          explanationContentEl.textContent = ''
        }
      }
    }
  }

  async callAIAPI(prompt: string, config: any, onChunk?: (chunk: string) => void): Promise<string> {
    try {
      console.log('🤖 调用AI API (通过后端代理):', config.name)
      const result = await callAIAnalysisViaProxyStream(prompt, config, onChunk)
      console.log('✅ AI生成的解释:', result)
      return result
    } catch (error) {
      console.error('❌ AI API调用失败:', error)
      throw error
    }
  }

  async explainWithAI() {
    const contentEl = document.getElementById(this.modalContentId)
    const explanationEl = document.getElementById(this.aiExplanationId)
    const explanationContentEl = document.getElementById(this.aiExplanationContentId)
    const titleEl = document.getElementById(this.modalTitleId)

    if (!contentEl || !explanationEl || !explanationContentEl || !titleEl) return

    const content = contentEl.textContent || ''
    const title = titleEl.textContent || ''

    explanationEl.style.display = 'block'
    explanationContentEl.textContent = '🤔 AI正在分析...'

    try {
      const settingsContent = await invoke('read_settings_file') as string
      let settings: any = {}

      if (settingsContent) {
        settings = JSON.parse(settingsContent)
      }

      if (!settings.ai) {
        settings.ai = {
          currentProvider: 'openai',
          providers: {
            openai: {
              name: 'OpenAI',
              apiKey: '',
              model: 'gpt-3.5-turbo',
              baseUrl: 'https://api.openai.com/v1'
            }
          }
        }
      }

      if (!settings.ai || !settings.ai.currentProvider) {
        throw new Error('AI配置异常，请在设置中配置AI')
      }

      const currentProvider = settings.ai.currentProvider
      const providerConfig = settings.ai.providers[currentProvider]

      if (!providerConfig) {
        throw new Error('AI提供商配置不存在')
      }

      if (!providerConfig.apiKey && currentProvider !== 'ollama') {
        throw new Error('请在设置中配置AI API Key')
      }

      const systemPrompt = `你是一个${this.aiExpertRole}。请用简洁专业的语言解释用户提供的信息，重点关注安全风险和异常情况。

请分析并解释${this.aiInfoType}：

标题：${title}

内容：
${content}

请提供：
1. 信息概要
2. 关键发现
3. 安全评估（如果适用）
4. 建议操作（如果适用）`

      explanationContentEl.textContent = ''
      let aiRawText = ''

      await this.callAIAPI(systemPrompt, providerConfig, (chunk: string) => {
        aiRawText += chunk
        renderAIAnalysisContent(explanationContentEl, aiRawText)
      })
    } catch (error) {
      explanationContentEl.textContent = `❌ AI解析失败: ${error}\n\n提示：请在设置中配置AI，或者检查AI服务是否可用。`
    }
  }

  async loadAccountList() {
    try {
      const connections = await invoke('load_ssh_connections') as any[]
      if (connections.length === 0) {
        console.log('📋 没有可用的SSH连接')
        return
      }

      const connection = connections[0]
      this.accounts = connection.accounts || []

      const select = document.getElementById(this.accountSelectId) as HTMLSelectElement
      if (!select) {
        console.warn(`⚠️ ${this.idPrefix}账号选择下拉框未找到`)
        return
      }

      select.innerHTML = '<option value="">默认账号</option>'

      this.accounts.forEach((account: any) => {
        const option = document.createElement('option')
        option.value = account.username
        option.textContent = `${account.username}${account.description ? ` (${account.description})` : ''}${account.is_default ? ' [默认]' : ''}`
        select.appendChild(option)
      })
    } catch (error) {
      console.error(`❌ ${this.idPrefix}右键菜单加载账号列表失败:`, error)
    }
  }

  createModal() {
    const modal = document.createElement('div')
    modal.id = this.modalId
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 10001;
    `

    modal.innerHTML = `
      <div class="modal-content" style="
        background: var(--bg-primary);
        border-radius: var(--border-radius);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        max-width: 900px;
        max-height: 85vh;
        width: 90%;
        display: flex;
        flex-direction: column;
      ">
        <div class="modal-header" style="
          padding: var(--spacing-md);
          border-bottom: 1px solid var(--border-color);
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--spacing-md);
        ">
          <h3 id="${this.modalTitleId}" style="margin: 0; color: var(--text-primary); font-size: 16px; flex: 1;"></h3>
          <button id="${this.aiExplainBtnId}" class="modern-btn secondary" style="
            padding: 6px 12px;
            font-size: 13px;
            gap: 6px;
          ">
            ${IconPark.Brain({ theme: 'outline', size: '16', fill: 'currentColor' })}
            <span>AI解析</span>
          </button>
          <button id="${this.modalCloseId}" style="
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: var(--text-secondary);
            padding: 0;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: var(--border-radius-sm);
          ">&times;</button>
        </div>
        <div class="modal-body" style="
          padding: var(--spacing-md);
          overflow-y: auto;
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        ">
          <div id="${this.modalContentId}" style="
            font-family: var(--font-mono);
            font-size: 12px;
            color: var(--text-primary);
            white-space: pre-wrap;
            word-break: break-all;
            padding: var(--spacing-sm);
            background: var(--bg-secondary);
            border-radius: var(--border-radius-sm);
            border: 1px solid var(--border-color);
          "></div>
          <div id="${this.aiExplanationId}" style="
            display: none;
            padding: var(--spacing-md);
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
            border-radius: var(--border-radius-sm);
            border: 1px solid rgba(102, 126, 234, 0.2);
          ">
            <div style="
              display: flex;
              align-items: center;
              gap: 8px;
              margin-bottom: var(--spacing-sm);
              color: var(--text-primary);
              font-weight: 600;
            ">
              ${IconPark.Brain({ theme: 'outline', size: '18', fill: 'currentColor' })}
              <span>AI解析</span>
            </div>
            <div id="${this.aiExplanationContentId}" style="
              font-size: 13px;
              line-height: 1.6;
              color: var(--text-primary);
              white-space: pre-wrap;
              word-break: break-word;
            "></div>
          </div>
        </div>
      </div>
    `

    document.body.appendChild(modal)
    this.modal = modal
  }

  setupEventListeners() {
    document.addEventListener('change', (e) => {
      const target = e.target as HTMLElement
      if (target.id === this.accountSelectId) {
        const select = target as HTMLSelectElement
        this.selectedUsername = select.value
        console.log(`👤 ${this.idPrefix}菜单选择账号:`, this.selectedUsername || '默认账号')
      }
    })

    this.contextMenu?.querySelectorAll('.menu-parent').forEach(parent => {
      parent.addEventListener('mouseenter', () => {
        const submenu = parent.querySelector('.submenu') as HTMLElement
        if (submenu) {
          submenu.style.top = '0'
          submenu.style.bottom = 'auto'

          setTimeout(() => {
            const submenuRect = submenu.getBoundingClientRect()
            const windowHeight = window.innerHeight

            if (submenuRect.bottom > windowHeight) {
              const overflow = submenuRect.bottom - windowHeight + 10
              submenu.style.top = `-${overflow}px`

              const newRect = submenu.getBoundingClientRect()
              if (newRect.top < 0) {
                submenu.style.top = 'auto'
                submenu.style.bottom = '0'
              }
            }
          }, 10)
        }
      })
    })

    this.contextMenu?.addEventListener('click', (e) => {
      const target = e.target as HTMLElement
      const menuItem = target.closest('.menu-item[data-action]') as HTMLElement
      if (menuItem) {
        const action = menuItem.getAttribute('data-action')
        if (action) {
          console.log(`执行操作: ${action}`)
          this.executeAction(action)
        }
        this.hideContextMenu()
      }
    })

    document.getElementById(this.modalCloseId)?.addEventListener('click', () => {
      this.hideModal()
    })

    document.getElementById(this.aiExplainBtnId)?.addEventListener('click', () => {
      this.explainWithAI()
    })

    this.modal?.addEventListener('click', (e) => {
      if (e.target === this.modal) {
        this.hideModal()
      }
    })

    document.addEventListener('click', (e) => {
      if (this.contextMenu && this.contextMenu.style.display !== 'none') {
        if (!this.contextMenu.contains(e.target as Node)) {
          this.hideContextMenu()
        }
      }
    })

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.hideContextMenu()
        this.hideModal()
      }
    })
  }

  protected async executeCommand(command: string, title: string, actionName: string): Promise<void> {
    if (!actionName) { actionName = '执行命令' }
    try {
      const accountInfo = this.selectedUsername ? ` (账号: ${this.selectedUsername})` : ''
      this.showModal(title, `⏳ 正在执行: ${actionName}${accountInfo}...\n\n命令: ${command.substring(0, 100)}${command.length > 100 ? '...' : ''}`)
      const params: any = { command }
      if (this.selectedUsername) { params.username = this.selectedUsername }
      const result = await invoke('ssh_execute_command_direct', params) as { output: string; exit_code: number }
      this.showModal(title, result.output || '✓ 命令执行完成，无输出')
    } catch (error) {
      this.showModal(title, `❌ 执行失败: ${error}`)
    }
  }

  protected abstract createContextMenu(): void
  protected abstract executeAction(action: string): Promise<void>
}
