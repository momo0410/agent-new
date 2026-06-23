// EmergencyResultModal - 显示命令执行结果（命令 + 输出 + 搜索高亮）

import { invoke } from '../../shims/@tauri-apps/api/core'
import * as IconPark from '@icon-park/svg'
import { CommandHistoryManager } from '../utils/commandHistoryManager'
import { aiService } from '../ai/aiService'
import { renderAIAnalysisContent } from '../utils/aiProxy'

export class EmergencyResultModal {
  private modal: HTMLElement | null = null;
  private titleEl: HTMLElement | null = null;
  private commandEl: HTMLElement | null = null;
  private outputEl: HTMLElement | null = null;
  private searchInput: HTMLInputElement | null = null;
  private isVisible = false;
  private originalOutput = '';
  private commandText = '';
  private currentTitle = '';
  private isEditMode = false;
  private eventsBound = false;
  private keydownHandler: ((event: KeyboardEvent) => void) | null = null;
  private isAnalyzing = false;
  private aiAbortController: AbortController | null = null;

  constructor() {
    this.createModal();
    if (!this.eventsBound) {
      this.bindEvents();
      this.eventsBound = true;
    }
  }

  private createModal(): void {
    console.log('🧩 创建 EmergencyResultModal DOM');
    const existing = document.getElementById('emergency-result-modal');
    if (existing) {
      console.log('ℹ️ EmergencyResultModal 已存在，跳过创建');
      this.modal = existing;
      this.titleEl = document.getElementById('em-modal-title');
      this.commandEl = document.getElementById('em-modal-command');
      this.outputEl = document.getElementById('em-modal-content');
      this.searchInput = document.getElementById('em-modal-search') as HTMLInputElement | null;
      this.ensureAIOverlayCloseButton();
      return;
    }

    const html = `
      <div id="emergency-result-modal" class="em-result-modal">
        <div class="em-modal-container">
          <div class="em-modal-header">
            <div class="em-modal-title-group">
              <span style="font-size:16px">📄</span>
              <h3 id="em-modal-title" class="em-modal-title">命令输出</h3>
            </div>
            <div class="em-modal-actions">
              <input id="em-modal-search" type="text" class="em-modal-search" placeholder="在输出中搜索..." autocomplete="off">
              <button id="em-modal-ai-btn" class="modern-btn primary" style="font-size:12px; padding:6px 10px; display:flex; align-items:center; gap:4px;">
                ${IconPark.Brain({ theme: 'outline', size: '14', fill: 'currentColor' })}
                <span>AI分析</span>
              </button>
              <button id="em-modal-copy" class="modern-btn secondary" style="font-size:12px; padding:6px 10px;">复制输出</button>
              <button id="em-modal-close" class="modern-btn secondary" style="font-size:12px; padding:6px 10px;">关闭</button>
            </div>
          </div>
          
          <div class="em-modal-body">
            <div class="em-modal-command-card">
              <div class="em-modal-command-header">
                <span class="em-modal-command-label">执行命令</span>
                <div class="em-modal-command-actions">
                  <button id="em-modal-edit-btn" class="modern-btn secondary" style="
                    font-size: 12px;
                    padding: 4px 8px;
                    display: flex;
                    align-items: center;
                    gap: 4px;
                  ">
                    ${IconPark.Edit({ theme: 'outline', size: '14', fill: 'currentColor' })}
                    <span>修改</span>
                  </button>
                  <button id="em-modal-execute-btn" class="modern-btn primary" style="
                    font-size: 12px;
                    padding: 4px 8px;
                    display: flex;
                    align-items: center;
                    gap: 4px;
                  ">
                    ${IconPark.Play({ theme: 'outline', size: '14', fill: 'currentColor' })}
                    <span>执行</span>
                  </button>
                </div>
              </div>
              <code id="em-modal-command" class="em-modal-command-code" contenteditable="false"></code>
            </div>

            <div class="em-modal-output-container">
              <div class="em-modal-output-scroll">
                <pre id="em-modal-content" class="em-modal-output-content"></pre>
              </div>
            </div>

            <div id="em-modal-ai-box" class="em-modal-ai-box">
              <div class="em-modal-ai-header">
                ${IconPark.Brain({ theme: 'filled', size: '16', fill: 'currentColor' })}
                <span>AI 安全分析</span>
                <span id="em-modal-ai-status" class="em-modal-ai-status" style="margin-left:auto;font-size:12px;color:var(--text-secondary);"></span>
              </div>
              <div id="em-modal-ai-content" class="em-modal-ai-content"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', html);
    this.modal = document.getElementById('emergency-result-modal');
    this.titleEl = document.getElementById('em-modal-title');
    this.commandEl = document.getElementById('em-modal-command');
    this.outputEl = document.getElementById('em-modal-content');
    this.searchInput = document.getElementById('em-modal-search') as HTMLInputElement | null;
  }

  private ensureAIOverlayCloseButton(): void {
    // 兼容旧调用点：当前弹窗结构不再需要额外的 AI 关闭按钮。
  }

  private bindEvents(): void {
    console.log('🔗 绑定 EmergencyResultModal 事件监听器');

    document.getElementById('em-modal-close')?.addEventListener('click', () => this.hide());
    this.modal?.addEventListener('click', (event) => {
      if (event.target === this.modal) this.hide();
    });

    // 保存 keydown 处理器的引用，以便后续可以移除
    this.keydownHandler = (event: KeyboardEvent) => {
      if (!this.isVisible) return;
      if (event.key === 'Escape') this.hide();
    };
    document.addEventListener('keydown', this.keydownHandler);
    document.getElementById('em-modal-copy')?.addEventListener('click', () => {
      navigator.clipboard.writeText(this.originalOutput).then(() => {
        (window as any).showNotification?.('命令输出已复制', 'success');
      }).catch((error) => {
        console.error('复制失败', error);
        (window as any).showNotification?.('复制失败', 'error');
      });
    });

    // 修改按钮
    document.getElementById('em-modal-edit-btn')?.addEventListener('click', () => {
      this.toggleEditMode();
    });

    // 执行按钮
    document.getElementById('em-modal-execute-btn')?.addEventListener('click', () => {
      this.executeCommand();
    });

    // AI分析按钮
    document.getElementById('em-modal-ai-btn')?.addEventListener('click', () => {
      this.analyzeWithAI();
    });

    if (this.searchInput) {
      let timer: number | null = null;
      this.searchInput.addEventListener('input', () => {
        if (timer) window.clearTimeout(timer);
        const value = this.searchInput?.value ?? '';
        timer = window.setTimeout(() => {
          this.renderOutput(value.trim() || undefined);
        }, 150);
      });
    }
  }

  show(title: string, command: string, output: unknown): void {
    console.log('\u2728 EmergencyResultModal.show', { title, hasModal: !!this.modal });
    if (!this.modal) {
      console.warn('EmergencyResultModal.show: modal 不存在，尝试重新创建');
      this.createModal();
      this.bindEvents();
      if (!this.modal) {
        console.error('EmergencyResultModal.show: 仍然无法创建 modal');
        return;
      }
    }

    this.originalOutput = this.normalizeOutput(output);
    this.commandText = command || '';
    this.currentTitle = title || '命令输出';
    this.isEditMode = false;

    if (this.titleEl) this.titleEl.textContent = this.currentTitle;
    if (this.commandEl) {
      this.commandEl.textContent = this.commandText || '（无命令）';
      this.commandEl.setAttribute('contenteditable', 'false');
      this.commandEl.classList.remove('editing');
    }
    if (this.searchInput) this.searchInput.value = '';

    // 更新编辑按钮文本
    const editBtn = document.getElementById('em-modal-edit-btn');
    if (editBtn) {
      editBtn.innerHTML = `${IconPark.Edit({ theme: 'outline', size: '14', fill: 'currentColor' })}<span>修改</span>`;
    }

    this.renderOutput();
    this.modal.style.display = 'flex';
    this.isVisible = true;

    // 重置AI分析区域
    this.resetAIAnalysis();

    // 兜底：确保关闭按钮在任何情况下都可关闭窗口
    const closeBtn = document.getElementById('em-modal-close') as HTMLButtonElement | null;
    if (closeBtn) {
      closeBtn.onclick = () => this.hide();
    }
  }

  hide(): void {
    if (!this.modal) return;
    this.modal.style.display = 'none';
    this.isVisible = false;
    this.stopAIAnalysis();
  }

  private renderOutput(searchTerm?: string): void {
    if (!this.outputEl) return;
    const safe = this.escapeHtml(this.originalOutput);
    if (!safe) {
      this.outputEl.innerHTML = '';
      return;
    }
    if (!searchTerm || searchTerm.length === 0) {
      this.outputEl.innerHTML = safe;
      return;
    }
    const regex = new RegExp(this.escapeRegExp(searchTerm), 'gi');
    this.outputEl.innerHTML = safe.replace(regex, (match) => `<mark>${match}</mark>`);
  }

  private normalizeOutput(output: unknown): string {
    if (output == null) {
      return '';
    }
    if (typeof output === 'string') {
      return output;
    }
    if (typeof output === 'number' || typeof output === 'boolean') {
      return String(output);
    }
    if (output instanceof Uint8Array) {
      try {
        return new TextDecoder().decode(output);
      } catch (error) {
        console.warn('无法解码 Uint8Array 输出', error);
        return '[binary data]';
      }
    }
    try {
      return JSON.stringify(output, null, 2);
    } catch (error) {
      console.warn('无法序列化命令输出', error);
      return String(output);
    }
  }

  private escapeHtml(input: string): string {
    return (input || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  private escapeRegExp(input: string): string {
    return input.replace(/[-\^$*+?.()|[\]{}]/g, '\\$&');
  }

  /**
   * 切换编辑模式
   */
  private toggleEditMode(): void {
    this.isEditMode = !this.isEditMode;
    const commandEl = this.commandEl;
    const editBtn = document.getElementById('em-modal-edit-btn');

    if (!commandEl || !editBtn) return;

    if (this.isEditMode) {
      // 进入编辑模式
      commandEl.setAttribute('contenteditable', 'true');
      commandEl.classList.add('editing');
      commandEl.focus();
      editBtn.innerHTML = `${IconPark.Save({ theme: 'outline', size: '14', fill: 'currentColor' })}<span>保存</span>`;
      editBtn.classList.remove('secondary');
      editBtn.classList.add('primary');
    } else {
      // 退出编辑模式，保存修改
      commandEl.setAttribute('contenteditable', 'false');
      commandEl.classList.remove('editing');
      this.commandText = commandEl.textContent || '';
      editBtn.innerHTML = `${IconPark.Edit({ theme: 'outline', size: '14', fill: 'currentColor' })}<span>修改</span>`;
      editBtn.classList.remove('primary');
      editBtn.classList.add('secondary');

      (window as any).showNotification?.('命令已更新', 'success');
    }
  }


  /**
   * 执行命令
   */
  private async executeCommand(): Promise<void> {
    const commandEl = this.commandEl;
    if (!commandEl) return;

    // 如果在编辑模式，先保存
    if (this.isEditMode) {
      this.toggleEditMode();
    }

    const command = commandEl.textContent?.trim() || '';
    if (!command) {
      (window as any).showNotification?.('命令不能为空', 'warning');
      return;
    }

    // 显示执行中状态
    const executeBtn = document.getElementById('em-modal-execute-btn');
    if (executeBtn) {
      executeBtn.textContent = '执行中...';
      (executeBtn as HTMLButtonElement).disabled = true;
    }

    try {
      // 获取SSH连接
      const app = (window as any).app;
      const sshManager = app?.sshManager;
      const sshConnectionManager = (window as any).sshConnectionManager;

      const hasCoordinatorConn = sshManager?.isConnected?.() ?? false;
      const hasDirectConn = sshConnectionManager?.isConnected?.() ?? false;

      if (!hasCoordinatorConn && !hasDirectConn) {
        throw new Error('未连接到服务器');
      }

      let output = '';
      let displayedCommand = command;

      if (hasCoordinatorConn && sshManager?.executeCommand) {
        output = await sshManager.executeCommand(command);
      } else if (hasDirectConn) {
        const result: any = await invoke('ssh_execute_command_direct', { command });
        if (result && typeof result === 'object') {
          if (typeof result.command === 'string' && result.command.length > 0) {
            displayedCommand = result.command;
          }
          if (typeof result.output === 'string') {
            output = result.output;
          } else if (typeof result.stdout === 'string') {
            output = result.stdout;
          } else {
            output = JSON.stringify(result, null, 2);
          }
        } else if (typeof result === 'string') {
          output = result;
        } else {
          output = String(result ?? '');
        }
      }

      // 更新显示
      this.originalOutput = output;
      this.commandText = displayedCommand;
      if (this.commandEl) this.commandEl.textContent = displayedCommand;
      this.renderOutput();

      // 保存到命令历史
      CommandHistoryManager.saveCommand(displayedCommand, this.currentTitle, output);

      (window as any).showNotification?.('命令执行完成', 'success');
    } catch (error) {
      console.error('执行命令失败:', error);
      (window as any).showNotification?.(`执行失败: ${error}`, 'error');
    } finally {
      // 恢复按钮状态
      if (executeBtn) {
        executeBtn.innerHTML = `${IconPark.Play({ theme: 'outline', size: '14', fill: 'currentColor' })}<span>执行</span>`;
        (executeBtn as HTMLButtonElement).disabled = false;
      }
    }
  }

  /**
   * AI 分析命令输出
   */
  private async analyzeWithAI(): Promise<void> {
    if (this.isAnalyzing) {
      this.stopAIAnalysis();
      return;
    }

    if (!aiService.isConfigured()) {
      (window as any).showNotification?.('AI 服务未配置，请先在设置中配置 AI 模型', 'warning');
      return;
    }

    const aiBox = document.getElementById('em-modal-ai-box');
    const aiContent = document.getElementById('em-modal-ai-content');
    const aiStatus = document.getElementById('em-modal-ai-status');
    const aiBtn = document.getElementById('em-modal-ai-btn');

    if (!aiBox || !aiContent) return;

    // 显示AI分析区域
    aiBox.style.display = 'block';
    aiContent.innerHTML = '';
    if (aiStatus) aiStatus.textContent = '分析中...';

    // 更新按钮状态
    this.isAnalyzing = true;
    if (aiBtn) {
      aiBtn.innerHTML = `${IconPark.Close({ theme: 'outline', size: '14', fill: 'currentColor' })}<span>停止分析</span>`;
      (aiBtn as HTMLButtonElement).disabled = false;
    }

    try {
      let accumulatedText = '';
      await aiService.analyzeCommandOutputStream(
        this.commandText,
        this.originalOutput,
        this.currentTitle,
        (chunk: string) => {
          // 实时追加纯文本（避免重复转义）
          accumulatedText += chunk;
          aiContent!.textContent = accumulatedText;
          // 自动滚动到底部
          aiContent!.scrollTop = aiContent!.scrollHeight;
        },
        (finalText: string) => {
          if (aiStatus) aiStatus.textContent = '分析完成';
          this.isAnalyzing = false;
          // 分析完成后，一次性渲染 Markdown 格式
          renderAIAnalysisContent(aiContent!, finalText);
          if (aiBtn) {
            aiBtn.innerHTML = `${IconPark.Brain({ theme: 'outline', size: '14', fill: 'currentColor' })}<span>AI分析</span>`;
          }
        }
      );
    } catch (error) {
      console.error('AI 分析失败:', error);
      if (aiStatus) aiStatus.textContent = '分析失败';
      aiContent.innerHTML = `<span style="color: var(--error-color);">AI 分析失败: ${error}</span>`;
      this.isAnalyzing = false;
      if (aiBtn) {
        aiBtn.innerHTML = `${IconPark.Brain({ theme: 'outline', size: '14', fill: 'currentColor' })}<span>AI分析</span>`;
      }
    }
  }

  /**
   * 停止AI分析
   */
  private stopAIAnalysis(): void {
    if (this.aiAbortController) {
      this.aiAbortController.abort();
      this.aiAbortController = null;
    }
    this.isAnalyzing = false;

    const aiBtn = document.getElementById('em-modal-ai-btn');
    if (aiBtn) {
      aiBtn.innerHTML = `${IconPark.Brain({ theme: 'outline', size: '14', fill: 'currentColor' })}<span>AI分析</span>`;
    }

    const aiStatus = document.getElementById('em-modal-ai-status');
    if (aiStatus) aiStatus.textContent = '已停止';
  }

  /**
   * 重置AI分析区域
   */
  private resetAIAnalysis(): void {
    this.stopAIAnalysis();

    const aiBox = document.getElementById('em-modal-ai-box');
    const aiContent = document.getElementById('em-modal-ai-content');
    const aiStatus = document.getElementById('em-modal-ai-status');

    if (aiBox) aiBox.style.display = 'none';
    if (aiContent) aiContent.innerHTML = '';
    if (aiStatus) aiStatus.textContent = '';
  }
}
