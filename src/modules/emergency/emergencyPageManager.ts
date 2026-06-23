import { emergencyCategories, type EmergencyCategory, type EmergencyCommand } from './commands';
import { CommandHistoryManager } from '../utils/commandHistoryManager';
import { SystemDetector, type SystemInfo } from '../utils/systemDetector';
import { CommandAdapter } from './commandAdapter';
import { EmergencyResultModal } from '../ui/emergencyModal';
import { invoke as appInvoke } from '../../shims/@tauri-apps/api/core';

class EmergencyPageManager {
  private categories: EmergencyCategory[] = emergencyCategories;
  private byId: Map<string, EmergencyCommand> = new Map();
  private initialized = false;
  private systemInfo: SystemInfo | null = null;
  private eventsBound = false;
  private debounceTimer: number | null = null;

  constructor() {
    this.rebuildIndex();
  }

  /**
   * 处理搜索输入
   */
  handleSearch(query: string): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    this.debounceTimer = window.setTimeout(() => {
      this.performSearch(query.trim().toLowerCase());
    }, 300);
  }

  /**
   * 执行搜索过滤
   */
  private performSearch(query: string): void {
    const buttons = document.querySelectorAll('.em-cmd-btn');
    const categories = document.querySelectorAll('.em-category-section');

    buttons.forEach((btn) => {
      const button = btn as HTMLElement;
      const nameEl = button.querySelector('.em-cmd-name');
      const descEl = button.querySelector('.em-cmd-desc');
      
      const name = nameEl?.textContent?.toLowerCase() || '';
      const desc = descEl?.textContent?.toLowerCase() || '';
      
      const match = !query || name.includes(query) || desc.includes(query);
      button.style.display = match ? 'flex' : 'none';
    });

    // 处理分类显示
    categories.forEach((cat) => {
      const category = cat as HTMLElement;
      // 如果没有明确设置 style 或者 display: flex 的都算可见（初始状态可能没有 style 属性）
      const allItems = category.querySelectorAll('.em-cmd-btn');
      let hasVisible = false;
      
      allItems.forEach(item => {
        const style = (item as HTMLElement).style.display;
        if (style !== 'none') hasVisible = true;
      });

      category.style.display = hasVisible ? 'block' : 'none';
    });
  }

  private rebuildIndex(): void {
    this.byId.clear();
    for (const cat of this.categories) {
      for (const item of cat.items) {
        this.byId.set(item.id, item);
      }
    }
  }

  getCategories(): EmergencyCategory[] {
    return this.categories;
  }

  async initialize(): Promise<void> {
    console.log('🔧 EmergencyPageManager.initialize 被调用，initialized:', this.initialized, 'eventsBound:', this.eventsBound);

    if (this.initialized) {
      console.log('⏭️ EmergencyPageManager 已初始化，跳过');
      // 即使已初始化，也重新加载账号列表（可能已更新）
      await this.loadAccountList();
      // 重新显示系统信息（解决切换页面后显示"检测中..."的问题）
      if (this.systemInfo) {
        this.displaySystemInfo();
      }
      return;
    }

    // 检测系统类型
    await this.detectSystem();

    // 加载账号列表
    await this.loadAccountList();

    // 只绑定一次事件
    if (!this.eventsBound) {
      console.log('🔗 绑定 EmergencyPageManager 事件监听器');
      this.bindEvents();
      this.eventsBound = true;
    }

    this.initialized = true;
    (window as any).emergencyPageManager = this;
  }

  /**
   * 检测系统类型
   */
  private async detectSystem(): Promise<void> {
    try {
      console.log('🔍 开始检测系统类型...');
      this.systemInfo = await SystemDetector.detectSystem();
      console.log('✅ 系统检测完成:', this.systemInfo);

      // 显示系统信息
      this.displaySystemInfo();
    } catch (error) {
      console.error('❌ 系统检测失败:', error);
      // 使用默认系统信息
      this.systemInfo = {
        type: 'generic',
        name: 'Linux',
        version: '',
        prettyName: 'Generic Linux',
        packageManager: 'unknown',
        initSystem: 'unknown'
      };
    }
  }

  /**
   * 显示系统信息
   */
  private displaySystemInfo(): void {
    if (!this.systemInfo) return;

    const systemDisplayName = SystemDetector.getSystemDisplayName(this.systemInfo.type);
    const systemInfoText = `${systemDisplayName} ${this.systemInfo.version}`.trim();

    // 在页面上显示系统信息
    const systemInfoEl = document.getElementById('detected-system-info');
    if (systemInfoEl) {
      systemInfoEl.textContent = systemInfoText;
      systemInfoEl.title = `系统: ${this.systemInfo.prettyName}\n包管理器: ${this.systemInfo.packageManager}\nInit系统: ${this.systemInfo.initSystem}`;
    }

    // 显示通知
    (window as any).showNotification?.(
      `已检测到系统: ${systemInfoText}`,
      'success'
    );
  }

  /**
   * 获取系统信息
   */
  getSystemInfo(): SystemInfo | null {
    return this.systemInfo;
  }

  /**
   * 加载账号列表
   */
  private async loadAccountList(): Promise<void> {
    try {
      const connections = (await appInvoke('load_ssh_connections')) as any[];
      if (connections.length === 0) {
        console.log('📋 没有可用的SSH连接');
        return;
      }

      // 假设使用第一个连接的账号列表（在实际应用中，应该获取当前活动连接）
      const connection = connections[0];
      const accounts = connection.accounts || [];

      // 更新账号下拉列表
      const select = document.getElementById('emergency-account-select') as HTMLSelectElement;
      if (!select) {
        console.warn('⚠️ 账号选择下拉框未找到');
        return;
      }

      // 清空现有选项
      select.innerHTML = '<option value="">默认账号</option>';

      // 添加账号选项
      accounts.forEach((account: any) => {
        const option = document.createElement('option');
        option.value = account.username;
        option.textContent = `${account.username}${account.description ? ` (${account.description})` : ''}${account.is_default ? ' [默认]' : ''}`;
        select.appendChild(option);
      });

      console.log(`✅ 应急命令页面加载了 ${accounts.length} 个账号`);
    } catch (error) {
      console.error('❌ 加载账号列表失败:', error);
    }
  }

  private bindEvents(): void {
    document.addEventListener('click', async (event) => {
      const currentPage = (window as any).app?.stateManager?.getState()?.currentPage;
      if (currentPage !== 'emergency-commands') {
        // 不在应急命令页面，不处理
        return;
      }

      const target = event.target as HTMLElement;
      const btn = target.closest('[data-em-id]') as HTMLElement | null;
      if (!btn) {
        // 不是应急命令按钮，不处理
        return;
      }

      // 防止重复点击
      if ((btn as HTMLButtonElement).disabled) {
        console.log('⚠️ 按钮已禁用，忽略点击');
        return;
      }

      const id = btn.getAttribute('data-em-id') || '';
      const cmd = this.byId.get(id);
      if (!cmd) {
        console.warn('⚠️ 未找到命令:', id);
        return;
      }

      console.log('🖱️ 点击执行命令:', cmd.name, id);
      await this.executeCommand(btn as HTMLButtonElement, cmd);
    });
  }

  private async executeCommand(btn: HTMLButtonElement, cmd: EmergencyCommand): Promise<void> {
    console.log('🚀 开始执行命令:', cmd.name, cmd.id);

    const app = (window as any).app;
    const sshManager = app?.sshManager;
    const sshConnectionManager = (window as any).sshConnectionManager;

    const hasCoordinatorConn = sshManager?.isConnected?.() ?? false;
    const hasDirectConn = sshConnectionManager?.isConnected?.() ?? false;

    console.log('🔍 连接状态检查:', { hasCoordinatorConn, hasDirectConn });

    if (!hasCoordinatorConn && !hasDirectConn) {
      console.warn('⚠️ 未连接到服务器');
      (window as any).showNotification?.('未连接到服务器，无法执行命令', 'warning');
      return;
    }

    // 获取选中的账号
    const accountSelect = document.getElementById('emergency-account-select') as HTMLSelectElement;
    const selectedUsername = accountSelect?.value || '';
    if (selectedUsername) {
      console.log('👤 使用账号执行:', selectedUsername);
    } else {
      console.log('👤 使用默认账号执行');
    }

    // 如果还没有检测系统，先检测
    if (!this.systemInfo) {
      await this.detectSystem();
    }

    // 根据系统类型适配命令
    let adaptedCommand: string;
    try {
      adaptedCommand = CommandAdapter.getAdaptedCommand(cmd, this.systemInfo!);
      console.log(`📝 适配后的命令 (${this.systemInfo!.type}):`, adaptedCommand);
    } catch (error) {
      console.error('命令适配失败:', error);
      (window as any).showNotification?.(`命令适配失败: ${error}`, 'error');
      return;
    }

    // Helper: timeout wrapper to avoid indefinite pending state
    const withTimeout = <T>(p: Promise<T>, ms = 30000): Promise<T> => {
      return new Promise<T>((resolve, reject) => {
        const t = setTimeout(() => reject(new Error('执行超时，请稍后重试或关闭终端重试')), ms);
        p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
      });
    };

    btn.disabled = true;
    const originalHTML = btn.innerHTML;
    // 暂时替换内容，保持结构
    const nameEl = btn.querySelector('.em-cmd-name');
    const descEl = btn.querySelector('.em-cmd-desc');
    if (nameEl) nameEl.textContent = '执行中...';
    if (descEl) descEl.textContent = '请稍候';

    let output = '';
    let displayedCommand = adaptedCommand;

    const showResult = () => {
      const title = `${cmd.name} · ${cmd.id}`;
      CommandHistoryManager.saveCommand(displayedCommand, title, output ?? '');
      let modal = (window as any).emergencyResultModal;
      if (!modal) {
        console.warn('⚠️ emergencyResultModal 未初始化，正在创建...');
        try {
          modal = new EmergencyResultModal();
          (window as any).emergencyResultModal = modal;
          console.log('✅ EmergencyResultModal 创建成功');
        } catch (e) {
          console.error('❌ 创建 EmergencyResultModal 失败:', e);
        }
      }
      if (modal?.show) {
        console.log('🪟 显示命令结果模态框');
        modal.show(title, displayedCommand, output ?? '');
      } else {
        console.error('❌ 无法显示命令结果模态框，modal:', modal);
      }
    };

    try {
      // 优先使用应急响应专用通道（直连 session / Python 后端）
      if (hasDirectConn) {
        console.log('🚨 [应急响应] 使用专用 session 快速执行命令');
        try {
          const invokeParams: any = { command: adaptedCommand };
          if (selectedUsername) {
            invokeParams.username = selectedUsername;
            console.log('👤 使用指定账号执行:', selectedUsername);
          }
          const result: any = await withTimeout(appInvoke('ssh_execute_emergency_command_direct', invokeParams));
          console.log('✅ [应急响应] 专用 session 执行完成');
          if (result && typeof result === 'object') {
            if (typeof result.command === 'string' && result.command.length > 0) displayedCommand = result.command;
            if (typeof result.output === 'string') output = result.output;
            else if (typeof result.stdout === 'string') output = result.stdout;
            else output = JSON.stringify(result, null, 2);
          } else if (typeof result === 'string') {
            output = result;
          } else {
            output = String(result ?? '');
          }
        } catch (e: any) {
          console.error('❌ [应急响应] 专用 session 执行失败:', e);
          // 如果专用 session 失败，尝试使用协调器通道
          if (hasCoordinatorConn && sshManager?.executeCommand) {
            console.warn('⚠️ 专用 session 失败，尝试切换到协调器通道...');
            (window as any).showNotification?.('正在切换备用执行通道...', 'warning');
            // 注意：协调器通道暂不支持账号参数，使用默认账号
            output = await withTimeout(sshManager.executeCommand(adaptedCommand), 20000);
          } else {
            throw e;
          }
        }
      } else if (hasCoordinatorConn && sshManager?.executeCommand) {
        console.log('📡 使用协调器通道执行命令');
        // 注意：协调器通道暂不支持账号参数，使用默认账号
        if (selectedUsername) {
          console.warn('⚠️ 协调器通道暂不支持账号切换，将使用默认账号执行');
          (window as any).showNotification?.('当前通道不支持账号切换，使用默认账号', 'warning');
        }
        output = await withTimeout(sshManager.executeCommand(adaptedCommand));
      } else {
        throw new Error('当前连接状态不支持执行命令');
      }

      console.log('✅ 命令执行完成，输出长度:', output.length);
      (window as any).showNotification?.('命令执行完成', 'success');
      showResult();
    } catch (err) {
      console.error('❌ 执行应急命令失败', err);
      output = `命令执行失败: ${err}`;
      (window as any).showNotification?.(String(output), 'error');
      showResult();
    } finally {
      console.log('🔄 恢复按钮状态');
      btn.innerHTML = originalHTML;
      btn.disabled = false;
    }

  }
}

export const emergencyPageManager = new EmergencyPageManager();
