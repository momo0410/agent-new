/**
 * 文件右键菜单和安全分析
 */

import { invoke } from '../../shims/@tauri-apps/api/core'
import { marked } from 'marked'
import { aiService } from '../ai/aiService'

interface CommandHistory {
  timestamp: string
  action: string
  actionName: string
  filePath: string
  fileName: string
  command: string
  result: string
}

const MODAL_ID = 'file-analysis-modal'
const MODAL_TITLE_ID = 'file-analysis-modal-title'
const MODAL_CONTENT_ID = 'file-analysis-modal-content'
const AI_EXPLANATION_ID = 'file-analysis-ai-explanation'
const AI_EXPLANATION_CONTENT_ID = 'file-analysis-ai-explanation-content'
const AI_ANALYZE_BTN_ID = 'file-analysis-ai-analyze-btn'

export class FileContextMenu {
  private commandHistory: CommandHistory[] = []
  private currentFilePath: string = ''
  private currentAnalysisType: string = ''
  private currentAnalysisResult: string = ''
  private modalCreated: boolean = false

  constructor() {
    this.setupEventListeners()
    console.log('FileContextMenu 已加载')
  }

  private ensureModal(): void {
    if (this.modalCreated && document.getElementById(MODAL_ID)) {
      return
    }

    const existing = document.getElementById(MODAL_ID)
    if (existing) {
      existing.remove()
    }

    const modal = document.createElement('div')
    modal.id = MODAL_ID
    modal.style.cssText = `
      display: none;
      position: fixed;
      z-index: 10000;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(0, 0, 0, 0.5);
      align-items: center;
      justify-content: center;
    `

    modal.innerHTML = `
      <div style="
        background: var(--bg-primary, #1e1e2e);
        border: 1px solid var(--border-color, #45475a);
        border-radius: 12px;
        box-shadow: 0 25px 50px rgba(0, 0, 0, 0.3);
        max-width: 800px;
        width: 90vw;
        max-height: 85vh;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      ">
        <div style="
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 20px;
          border-bottom: 1px solid var(--border-color, #45475a);
        ">
          <h3 id="${MODAL_TITLE_ID}" style="
            margin: 0;
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary, #cdd6f4);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            flex: 1;
          "></h3>
          <div style="display: flex; align-items: center; gap: 8px; margin-left: 12px;">
            <button id="${AI_ANALYZE_BTN_ID}" style="
              background: linear-gradient(135deg, #8b5cf6, #6366f1);
              color: white;
              border: none;
              padding: 6px 14px;
              border-radius: 6px;
              cursor: pointer;
              font-size: 12px;
              display: flex;
              align-items: center;
              gap: 4px;
              white-space: nowrap;
            ">🤖 AI解释</button>
            <button id="file-analysis-modal-close" style="
              background: none;
              border: 1px solid var(--border-color, #45475a);
              color: var(--text-secondary, #a6adc8);
              padding: 4px 10px;
              border-radius: 6px;
              cursor: pointer;
              font-size: 13px;
            ">✕</button>
          </div>
        </div>
        <div style="
          flex: 1;
          overflow-y: auto;
          padding: 16px 20px;
        ">
          <pre id="${MODAL_CONTENT_ID}" style="
            margin: 0;
            white-space: pre-wrap;
            word-break: break-all;
            font-family: 'Cascadia Code', 'Fira Code', monospace;
            font-size: 13px;
            line-height: 1.6;
            color: var(--text-primary, #cdd6f4);
            background: var(--bg-secondary, #181825);
            padding: 12px;
            border-radius: 8px;
            border: 1px solid var(--border-color, #45475a);
          "></pre>
          <div id="${AI_EXPLANATION_ID}" style="display: none; margin-top: 12px;">
            <div style="
              display: flex;
              align-items: center;
              gap: 8px;
              margin-bottom: 8px;
              padding-bottom: 8px;
              border-bottom: 1px solid var(--border-color, #45475a);
            ">
              <span style="font-size: 16px;">🤖</span>
              <span style="font-weight: 600; color: var(--text-primary, #cdd6f4);">AI 安全分析</span>
            </div>
            <div id="${AI_EXPLANATION_CONTENT_ID}" style="
              color: var(--text-primary, #cdd6f4);
              font-size: 13px;
              line-height: 1.6;
            "></div>
          </div>
        </div>
      </div>
    `

    document.body.appendChild(modal)

    document.getElementById('file-analysis-modal-close')?.addEventListener('click', () => {
      this.hideModal()
    })

    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        this.hideModal()
      }
    })

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal.style.display === 'flex') {
        this.hideModal()
      }
    })

    this.modalCreated = true
  }

  private setupEventListeners(): void {
    document.addEventListener('click', (e) => {
      const target = e.target as HTMLElement
      if (target.id === AI_ANALYZE_BTN_ID || target.closest(`#${AI_ANALYZE_BTN_ID}`)) {
        const modal = document.getElementById(MODAL_ID)
        if (modal && modal.style.display === 'flex' && this.currentFilePath) {
          this.analyzeWithAI()
        }
      }
    })
  }

  private showModal(title: string, content: string): void {
    this.ensureModal()

    const modal = document.getElementById(MODAL_ID)
    const titleEl = document.getElementById(MODAL_TITLE_ID)
    const contentEl = document.getElementById(MODAL_CONTENT_ID)
    const explanationEl = document.getElementById(AI_EXPLANATION_ID)

    if (!modal || !titleEl || !contentEl) {
      console.error('[FileContextMenu] 模态框元素创建失败')
      return
    }

    titleEl.textContent = title
    contentEl.textContent = content

    if (explanationEl) {
      explanationEl.style.display = 'none'
      const explanationContentEl = document.getElementById(AI_EXPLANATION_CONTENT_ID)
      if (explanationContentEl) {
        explanationContentEl.textContent = ''
      }
    }

    modal.style.display = 'flex'
  }

  public hideModal(): void {
    const modal = document.getElementById(MODAL_ID)
    if (modal) {
      modal.style.display = 'none'
    }
  }

  private async executeAnalysis(action: string, filePath: string): Promise<string> {
    try {
      const result = await invoke('sftp_file_analysis_independent', {
        action,
        path: filePath
      }) as any

      this.addToHistory(result)

      return result.result as string
    } catch (error) {
      throw new Error(`分析失败: ${error}`)
    }
  }

  private addToHistory(data: any): void {
    if (!data || !data.action || !data.file_path) {
      return
    }
    const actionName = this.getActionName(data.action)
    const fileName = data.file_path.split('/').pop() || data.file_path

    const historyItem: CommandHistory = {
      timestamp: data.timestamp || new Date().toISOString(),
      action: data.action,
      actionName: actionName,
      filePath: data.file_path,
      fileName: fileName,
      command: this.getCommandForAction(data.action, data.file_path),
      result: data.result || ''
    }

    this.commandHistory.unshift(historyItem)

    if (this.commandHistory.length > 50) {
      this.commandHistory.pop()
    }
  }

  private getCommandForAction(action: string, filePath: string): string {
    const commands: Record<string, string> = {
      'hash': `md5sum "${filePath}" && sha1sum "${filePath}" && sha256sum "${filePath}"`,
      'signature': `file -b "${filePath}"`,
      'permissions': `ls -lh "${filePath}" && stat -c '%A %a %U:%G' "${filePath}"`,
      'timestamps': `stat "${filePath}"`,
      'inode': `stat -c 'Inode: %i\\nLinks: %h\\nDevice: %d\\nSize: %s bytes' "${filePath}"`,
      'mime-type': `file -b --mime-type "${filePath}"`,
      'file-size': `du -h "${filePath}" && ls -lh "${filePath}"`,
      'strings': `strings -n 8 "${filePath}" | head -100`,
      'hex-dump': `xxd "${filePath}" | head -50`,
      'line-count': `wc -l "${filePath}"`,
      'archive-list': `tar -tzf "${filePath}" 2>/dev/null || unzip -l "${filePath}" 2>/dev/null`,
      'elf-header': `readelf -h "${filePath}"`,
      'processes': `lsof "${filePath}" 2>/dev/null || fuser -v "${filePath}" 2>/dev/null`,
      'package-owner': `dpkg -S "${filePath}" 2>/dev/null || rpm -qf "${filePath}" 2>/dev/null`,
      'hard-links': `find / -samefile "${filePath}" 2>/dev/null`,
      'process-maps': `grep "${filePath}" /proc/*/maps 2>/dev/null`,
      'xattr': `getfattr -d "${filePath}" 2>/dev/null || xattr -l "${filePath}" 2>/dev/null`,
      'capabilities': `getcap "${filePath}"`,
      'selinux-context': `ls -Z "${filePath}"`,
      'dynamic-deps': `ldd "${filePath}" 2>/dev/null`,
      'config-references': `grep -r "${filePath}" /etc/ 2>/dev/null | head -20`,
      'symlink-analysis': `ls -l "${filePath}" && readlink -f "${filePath}"`,
    }
    return commands[action] || `未知命令: ${action}`
  }

  public showHistoryModal(): void {
    let historyHTML = ''

    if (this.commandHistory.length === 0) {
      historyHTML = '<div style="text-align: center; padding: 40px; color: var(--text-tertiary);">暂无历史记录</div>'
    } else {
      historyHTML = '<div style="max-height: 600px; overflow-y: auto;">'
      historyHTML += '<div style="margin-bottom: 20px;">'
      historyHTML += `<button id="clear-history-btn" style="
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        transition: all 0.3s;
      " onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
        清空历史
      </button>`
      historyHTML += '</div>'

      this.commandHistory.forEach((item) => {
        const time = new Date(item.timestamp).toLocaleString('zh-CN')
        historyHTML += `<div style="
          background: var(--panel-bg);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          padding: 16px;
          margin-bottom: 12px;
        ">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 18px;">📁</span>
              <span style="font-weight: 600; color: var(--text-primary);">${this.escapeHtml(item.fileName)}</span>
            </div>
            <span style="font-size: 12px; color: var(--text-tertiary);">${time}</span>
          </div>
          <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 6px;">
            🔍 命令: <span style="color: var(--text-primary);">${item.actionName}</span>
          </div>
          <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 8px;">
            📂 ${this.escapeHtml(item.filePath)}
          </div>
          <div style="font-size: 12px; color: var(--text-tertiary); background: var(--bg-color); padding: 8px; border-radius: 6px; font-family: monospace; max-height: 100px; overflow-y: auto; white-space: pre-wrap;">
            📊 结果: ${this.escapeHtml(item.result.substring(0, 300))}${item.result.length > 300 ? '...' : ''}
          </div>
        </div>`
      })
      historyHTML += '</div>'
    }

    this.showModal('命令执行历史', historyHTML)

    const clearBtn = document.getElementById('clear-history-btn')
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (confirm('确定要清空所有历史记录吗？')) {
          this.commandHistory = []
          this.showHistoryModal()
        }
      })
    }
  }

  private escapeHtml(text: string): string {
    const div = document.createElement('div')
    div.textContent = text
    return div.innerHTML
  }

  private getActionName(action: string): string {
    const names: Record<string, string> = {
      'hash': '哈希值',
      'signature': '文件类型',
      'permissions': '权限',
      'timestamps': '时间戳',
      'inode': 'Inode',
      'mime-type': 'MIME 类型',
      'file-size': '大小',
      'strings': '字符串',
      'hex-dump': 'HEX 转储',
      'line-count': '行数',
      'archive-list': '压缩列表',
      'elf-header': 'ELF头',
      'processes': '进程',
      'package-owner': '所属包',
      'hard-links': '硬链接',
      'process-maps': '内存映射',
      'xattr': '扩展属性',
      'capabilities': '能力',
      'selinux-context': 'SELinux',
      'dynamic-deps': '动态依赖',
      'config-references': '配置引用',
      'symlink-analysis': '符号链接'
    }
    return names[action] || action
  }

  public async handleAction(action: string, filePath: string, menuItem?: HTMLElement): Promise<void> {
    const actionName = this.getActionName(action)
    const originalText = menuItem?.getAttribute('data-original-text') || menuItem?.textContent || actionName

    try {
      if (menuItem) {
        if (!menuItem.getAttribute('data-original-text')) {
          menuItem.setAttribute('data-original-text', originalText)
        }
        menuItem.style.opacity = '0.5'
        menuItem.style.pointerEvents = 'none'
        menuItem.textContent = '⏳ 执行中...'
      }

      const result = await this.executeAnalysis(action, filePath)

      this.currentFilePath = filePath
      this.currentAnalysisType = actionName
      this.currentAnalysisResult = result

      const displayTitle = `${actionName} - ${filePath.split('/').pop()}`
      this.showModal(displayTitle, result)

      if (menuItem) {
        menuItem.style.opacity = '1'
        menuItem.style.pointerEvents = 'auto'
        menuItem.textContent = originalText
      }

    } catch (error) {
      console.error('文件分析失败:', error)
      this.showModal('错误', `文件分析失败: ${error}`)

      if (menuItem) {
        menuItem.style.opacity = '1'
        menuItem.style.pointerEvents = 'auto'
        menuItem.textContent = originalText || '重试'
      }
    }
  }

  private async analyzeWithAI(): Promise<void> {
    if (!this.currentFilePath || !this.currentAnalysisResult) {
      console.warn('没有可分析的内容')
      return
    }

    this.ensureModal()

    const explanationEl = document.getElementById(AI_EXPLANATION_ID)
    const explanationContentEl = document.getElementById(AI_EXPLANATION_CONTENT_ID)

    if (!explanationEl || !explanationContentEl) {
      console.error('找不到 AI 解释区域')
      return
    }

    explanationEl.style.display = 'block'
    explanationContentEl.innerHTML = '<div style="text-align: center; padding: 20px;"><span style="display: inline-block; animation: spin 1s linear infinite;">⏳</span> 正在分析...</div>'

    if (!aiService.isConfigured()) {
      explanationContentEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #ef4444;">⚠️ 请先在设置中配置 AI 模型</div>'
      return
    }

    const prompt = `你是一个 Linux 安全专家和应急响应专家。

## 任务
分析以下文件安全分析结果，并提供专业的解释和建议。

## 文件信息
- 文件路径：${this.currentFilePath}
- 分析类型：${this.currentAnalysisType}

## 分析结果
\`\`\`
${this.currentAnalysisResult}
\`\`\`

## 输出要求
请按照以下顺序提供分析：
1. **结果概要**：简要总结分析结果
2. **关键发现**：列出重要的发现和特征
3. **安全评估**：评估潜在的安全风险（如果适用）
4. **建议操作**：提供具体的操作建议（如果适用）

请使用清晰的 Markdown 格式，确保内容结构化、易读。`

    try {
      explanationContentEl.innerHTML = ''

      let accumulatedContent = ''
      let lastUpdateTime = 0
      const updateUI = (content: string) => {
        const now = Date.now()
        if (now - lastUpdateTime >= 100) {
          explanationContentEl.innerHTML = this.renderMarkdown(content)
          lastUpdateTime = now
        }
      }

      await aiService.chatStream(
        [
          { role: 'system', content: '你是一个专业的 Linux 安全分析专家，擅长分析系统文件和提供安全建议。请使用中文回答。' },
          { role: 'user', content: prompt }
        ],
        (chunk) => {
          accumulatedContent += chunk
          updateUI(accumulatedContent)
        }
      )

      explanationContentEl.innerHTML = this.renderMarkdown(accumulatedContent)

    } catch (error) {
      console.error('AI 分析失败:', error)
      explanationContentEl.innerHTML = `<div style="text-align: center; padding: 20px; color: #ef4444;">
        ❌ AI分析失败: ${error}<br><br>
        提示：请在设置中配置AI，或者检查AI服务是否可用。
      </div>`
    }
  }

  private renderMarkdown(text: string): string {
    try {
      if (typeof marked === 'undefined') {
        console.warn('marked.js 未加载，使用简单渲染')
        return this.simpleMarkdownRender(text)
      }

      marked.setOptions({
        gfm: true,
        breaks: true,
      })

      const html = marked.parse(text)

      return `<style>
        .ai-content h1, .ai-content h2, .ai-content h3 { color: var(--text-primary); margin: 12px 0 8px 0; }
        .ai-content h1 { font-size: 1.4em; }
        .ai-content h2 { font-size: 1.2em; }
        .ai-content h3 { font-size: 1.1em; }
        .ai-content p { margin: 8px 0; line-height: 1.6; }
        .ai-content ul, .ai-content ol { margin: 8px 0 8px 20px; }
        .ai-content li { margin: 4px 0; }
        .ai-content code { background: var(--bg-color); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
        .ai-content pre { background: var(--bg-color); padding: 12px; border-radius: 8px; overflow-x: auto; margin: 12px 0; }
        .ai-content pre code { background: none; padding: 0; }
        .ai-content blockquote { border-left: 3px solid var(--primary-color); padding-left: 12px; margin: 12px 0; color: var(--text-secondary); }
        .ai-content strong { color: var(--text-primary); font-weight: 600; }
        .ai-content a { color: var(--primary-color); text-decoration: underline; }
        .ai-content hr { border: none; border-top: 1px solid var(--border-color); margin: 16px 0; }
        .ai-content table { width: 100%; border-collapse: collapse; margin: 12px 0; }
        .ai-content th, .ai-content td { border: 1px solid var(--border-color); padding: 8px; text-align: left; }
        .ai-content th { background: var(--bg-color); font-weight: 600; }
      </style>
      <div class="ai-content">${html}</div>`
    } catch (e) {
      console.error('Markdown 渲染失败:', e)
      return this.simpleMarkdownRender(text)
    }
  }

  private simpleMarkdownRender(text: string): string {
    return text
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>')
  }
}

declare global {
  interface Window {
    fileContextMenu: FileContextMenu
  }
}

export const fileContextMenu = new FileContextMenu()
if (typeof window !== 'undefined') {
  window.fileContextMenu = fileContextMenu
}
