/**
 * SDIT 核心应用类
 * 负责应用初始化、状态管理和模块协调
 */
import { invoke } from '../../shims/@tauri-apps/api/core';
import { StateManager } from './stateManager';
import { ModernUIRenderer } from '../ui/modernUIRenderer';
import { ThemeManager } from '../ui/theme';
import { SSHManager } from '../ssh/sshManager';
import { SettingsManager } from '../settings/settingsManager';
import { SystemInfoManager } from '../system/systemInfoManager';
import { sshConnectionManager } from '../remote/sshConnectionManager';
import { sshTerminalManager } from '../ssh/sshTerminalManager';
import { mountWorkspaceRoot } from '../ui/workspace/mountWorkspaceRoot';
// 统一从 pageTypes 导入所有类型，移除本地重复定义
// @ts-ignore - 类型被重新导出供其他模块使用
import type { AppPage, UIMode, AppState, ServerInfo } from '../ui/pageTypes';
export type { AppPage, UIMode, AppState, ServerInfo } from '../ui/pageTypes';
export class SDITApp {
  private stateManager: StateManager;
  private modernUIRenderer: ModernUIRenderer;
  private themeManager: ThemeManager;
  public sshManager: SSHManager;
  private settingsManager: SettingsManager;
  private systemInfoManager: SystemInfoManager;
  constructor() {
    this.stateManager = new StateManager();
    this.modernUIRenderer = new ModernUIRenderer(this.stateManager);
    this.themeManager = new ThemeManager();
    this.sshManager = new SSHManager();
    this.settingsManager = new SettingsManager();
    this.systemInfoManager = new SystemInfoManager();
    // 暴露管理器和应用实例给全局对象，供 UI 使用
    (window as any).app = {
      sshManager: this.sshManager,
      systemInfoManager: this.systemInfoManager,
      stateManager: this.stateManager,
      modernUIRenderer: this.modernUIRenderer,
      render: () => this.render() // 暴露 render 方法
    };
  }
  /**
   * 初始化应用
   */
  async initialize(): Promise<void> {
    try {
      console.log('SDIT 应用初始化开始...');
      
      // 初始化状态管理器
      await this.stateManager.initialize();
      // 设置 UI 渲染器到状态管理器
      this.stateManager.setUIRenderer(this.modernUIRenderer);
      // 初始化主题
      await this.initializeTheme();
      
      // 初始化设置
      await this.settingsManager.initialize();
      // 初始化 SSH 终端管理器
      await sshTerminalManager.initialize();
      // 检查是否存在已有的 SSH 连接（浏览器刷新后恢复页面状态）
      await this.checkAndRestoreConnection();
      // 渲染 UI
      this.render();
      // 绑定事件
      this.bindEvents();
      
      console.log('SDIT 应用初始化完成');
    } catch (error) {
      console.error('应用初始化失败:', error);
      throw error;
    }
  }
  /**
   * 初始化主题系统
   */
  private async initializeTheme(): Promise<void> {
    try {
      // 从后端加载主题设置
      const savedTheme = await this.loadThemeFromBackend();
      if (savedTheme && (savedTheme === 'light' || savedTheme === 'dark')) {
        this.stateManager.setTheme(savedTheme);
      }
      
      // 应用主题
      this.themeManager.setTheme(this.stateManager.getState().theme);
    } catch (error) {
      console.error('主题初始化失败:', error);
      // 使用默认主题
      this.themeManager.setTheme('light');
    }
  }
  /**
   * 从后端加载主题设置
   */
  private async loadThemeFromBackend(): Promise<string | null> {
    try {
      const themeSettings = await invoke('get_theme_settings') as any;
      return themeSettings?.current_theme || null;
    } catch (error) {
      console.error('从后端加载主题设置失败:', error);
      return null;
    }
  }
  /**
   * 检查并恢复已有的 SSH 连接状态（浏览器刷新后恢复页面状态）
   */
  private async checkAndRestoreConnection(): Promise<void> {
    try {
      const status = await sshConnectionManager.checkConnectionStatus();
      if (status && status.connected) {
        this.stateManager.setConnected(true, status.host, {
          host: status.host,
          port: status.port,
          username: status.username
        });
        this.stateManager.setCurrentPage('dashboard');
        // 预加载仪表盘数据，避免渲染时闪现"正在加载监控数据"
        try {
          await this.sshManager.fetchSystemSummary();
        } catch (e) {
          console.warn('预加载系统摘要失败（将在页面激活时重试）:', e);
        }
        console.log('已恢复 SSH 连接状态，跳转到仪表盘页面');
      }
    } catch (error) {
      console.error('检查 SSH 连接状态失败:', error);
    }
  }
  /**
   * 设置主题
   */
  async setTheme(theme: 'light' | 'dark'): Promise<void> {
    const themeNames = {
      'light': '浅色',
      'dark': '深色',
    };
    // 如果已经在该主题，不进行操作
    if (this.stateManager.getState().theme === theme) {
      return;
    }
    try {
      // 保存主题设置到后端
      await invoke('set_current_theme', { theme });
      console.log(`主题已保存到设置：${theme}`);
      
      this.showMessage(`已切换到${themeNames[theme] || '未知'}模式`, 'success');
    } catch (error) {
      console.error('保存主题设置失败:', error);
      // 即使保存失败也继续切换 UI
    }
    // 更新状态管理器
    this.stateManager.setTheme(theme);
    // 应用主题
    this.themeManager.setTheme(theme);
    
    // 更新 UI
    this.modernUIRenderer.updateState(this.stateManager.getState());
    this.updateTitleBar();
  }
  /**
   * 切换主题
   */
  async toggleTheme(): Promise<void> {
    const currentTheme = this.stateManager.getState().theme;
    const themes: ('light' | 'dark')[] = ['light', 'dark'];
    const nextIndex = (themes.indexOf(currentTheme) + 1) % themes.length;
    await this.setTheme(themes[nextIndex]);
  }
  /**
   * 渲染应用界面
   */
  render(): void {
    const app = document.getElementById('app');
    if (app) {
      this.modernUIRenderer.hideMiniSidebarTooltip();
      const hideSidebar = this.modernUIRenderer.shouldHideSidebar();
      app.innerHTML = `
        <div class="app-layout">
          <div class="main-container">
            ${hideSidebar ? '' : this.modernUIRenderer.renderSidebar()}
            ${this.modernUIRenderer.renderMainWorkspace()}
          </div>
        </div>
      `;
      // 为 mini-sidebar 绑定 JS tooltip
      if (!hideSidebar) {
        setTimeout(() => this.modernUIRenderer.bindMiniSidebarTooltips(), 0);
      }
      setTimeout(() => {
        mountWorkspaceRoot(this.stateManager, this.modernUIRenderer);
      }, 0);
      // 加载样式
      this.loadStyles();
    }
  }

  /**
   * 更新导航栏激活状态
   */
  private updateNavActiveState(navId: string): void {
    document.querySelectorAll('.nav-item').forEach(item => {
      const htmlItem = item as HTMLElement;
      const id = htmlItem.getAttribute('data-nav-id');
      if (id) {
        const isActive = id === navId;
        htmlItem.classList.toggle('active', isActive);
        if (isActive) {
          if (!htmlItem.querySelector('.nav-item-indicator')) {
            const indicator = document.createElement('div');
            indicator.className = 'nav-item-indicator';
            htmlItem.insertBefore(indicator, htmlItem.firstChild);
          }
        } else {
          const indicator = htmlItem.querySelector('.nav-item-indicator');
          if (indicator) indicator.remove();
        }
      }
    });
  }

  /**
   * 切换页面（保留 DOM 状态）
   */
  switchToPage(pageId: AppPage): void {
    this.stateManager.setCurrentPage(pageId);
    this.modernUIRenderer.updateState(this.stateManager.getState());
    this.modernUIRenderer.switchToPage(pageId);
    this.updateNavActiveState(pageId);
  }

  /**
   * 加载样式文件
   */
  private loadStyles(): void {
    const existingLink = document.querySelector('link[href*="base.css"]');
    if (!existingLink) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/src/css/base.css';
      document.head.appendChild(link);
    }
  }
  /**
   * 绑定事件
   */
  private bindEvents(): void {
    // 定义全局窗口函数
    this.defineGlobalFunctions();
    // 注入全局模态框 HTML
    this.injectGlobalModals();
    // 全局点击事件处理
    document.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      
      // 主题切换 - 分段控制器
      const themeBtn = target.closest('.segmented-btn');
      if (themeBtn && themeBtn.closest('.theme-switcher')) {
        const theme = themeBtn.getAttribute('data-theme-value');
        if (theme && ['light', 'dark'].includes(theme)) {
          this.setTheme(theme as 'light' | 'dark');
        }
      }
      // 导航点击事件
      const navItem = target.closest('.nav-item');
      // 排除设置按钮（它也有 nav-item 类，但没有 data-nav-id 或 id 不同）
      if (navItem && navItem.getAttribute('data-nav-id')) {
        const navId = navItem.getAttribute('data-nav-id');
        if (navId) {
            const pageId = navId as AppPage;
            this.modernUIRenderer.hideMiniSidebarTooltip();
            this.stateManager.setCurrentPage(pageId);
            this.modernUIRenderer.updateState(this.stateManager.getState());
            this.modernUIRenderer.switchToPage(pageId);
            this.updateNavActiveState(pageId);
        }
      }
      // 点击外部关闭下拉菜单
      if (!target.closest('.sidebar-settings-container')) {
        (window as any).hideSettingsDropdown && (window as any).hideSettingsDropdown();
      }
      if (!target.closest('.connection-card-wrapper')) {
        (window as any).hideConnectionDropdown && (window as any).hideConnectionDropdown();
      }
    });
    // 窗口控制事件
    this.bindWindowControls();
    
    // SSH 连接事件
    this.bindSSHEvents();
  }
  /**
   * 定义全局窗口函数
   */
  private defineGlobalFunctions(): void {
    // 设置下拉菜单
    (window as any).toggleSettingsDropdown = () => {
      const menu = document.getElementById('settings-dropdown-menu');
      if (menu) {
        const willShow = !menu.classList.contains('show');
        if (willShow) {
          this.modernUIRenderer.syncSettingsDropdownState();
        }
        menu.classList.toggle('show');
      }
    };
    (window as any).hideSettingsDropdown = () => {
      const menu = document.getElementById('settings-dropdown-menu');
      if (menu) {
        menu.classList.remove('show');
      }
    };
    // 连接下拉菜单
    (window as any).toggleConnectionDropdown = () => {
      const menu = document.getElementById('connection-dropdown-menu');
      if (menu) {
        menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
      }
    };
    (window as any).hideConnectionDropdown = () => {
      const menu = document.getElementById('connection-dropdown-menu');
      if (menu) {
        menu.style.display = 'none';
      }
    };
    // Debug 工具
    (window as any).toggleDevTools = async () => {
      try {
        await invoke('open_devtools');
      } catch (e) {
        console.error('Failed to open devtools:', e);
      }
    };
    // 菜单操作
    (window as any).handleUserMenuAction = (action: string) => {
        if (action === 'settings') {
            (window as any).toggleSettingsDropdown?.();
        }
    };
  }

  /**
   * 注入全局模态框 HTML 到页面 body
   */
  private injectGlobalModals(): void {
    const modalsHTML = this.modernUIRenderer.renderGlobalModals();
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = modalsHTML;
    
    while (tempDiv.firstChild) {
      document.body.appendChild(tempDiv.firstChild);
    }
  }

  /**
   * 显示消息
   */
  private showMessage(message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info'): void {
    const bgColorMap: Record<'success' | 'error' | 'info' | 'warning', string> = {
      success: '#22c55e',
      error: '#ef4444',
      info: '#3b82f6',
      warning: '#f59e0b',
    };
    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 12px 20px;
      border-radius: 6px;
      color: white;
      font-size: 14px;
      z-index: 10000;
      background: ${bgColorMap[type]};
      transition: opacity 0.3s ease;
    `;
    messageDiv.textContent = message;
    document.body.appendChild(messageDiv);
    setTimeout(() => {
      messageDiv.style.opacity = '0';
      setTimeout(() => messageDiv.remove(), 300);
    }, 2500);
  }
  /**
   * 绑定窗口控制事件
   */
  private bindWindowControls(): void {
    document.addEventListener('click', async (e) => {
      const target = e.target as HTMLElement;
      
      if (target.classList.contains('minimize-btn')) {
        await invoke('minimize_window');
      } else if (target.classList.contains('maximize-btn')) {
        await invoke('toggle_maximize');
      } else if (target.classList.contains('close-btn')) {
        await invoke('close_window');
      }
    });
  }
  /**
   * 绑定 SSH 事件
   */
  private bindSSHEvents(): void {
    // SSH 连接按钮
    document.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      if (target.classList.contains('ssh-connect-btn')) {
        this.handleSSHConnect();
        return;
      }
      if (target.classList.contains('disconnect-btn') || target.closest('.disconnect-btn')) {
        this.handleSSHDisconnect();
      }
    });
  }
  /**
   * 处理 SSH 连接
   */
  private async handleSSHConnect(): Promise<void> {
    try {
      this.stateManager.setLoading(true);
      // 获取连接列表，如果有连接则连接第一个
      const connections = this.sshManager.getConnections();
      if (connections.length === 0) {
        this.showMessage('请先添加 SSH 连接配置', 'warning');
        return;
      }
      // 连接到第一个配置的服务器
      await this.sshManager.connect(connections[0].id);
      this.stateManager.setConnected(true, connections[0].name);
      // 连接成功后自动跳转到仪表板
      this.stateManager.setCurrentPage('dashboard');
      this.render();
      this.showMessage('SSH 连接成功', 'success');
    } catch (error) {
      console.error('SSH 连接失败:', error);
      this.showMessage('SSH 连接失败', 'error');
    } finally {
      this.stateManager.setLoading(false);
    }
  }
  /**
   * 处理 SSH 断开
   */
  private async handleSSHDisconnect(): Promise<void> {
    try {
      this.stateManager.setLoading(true);
      await this.sshManager.disconnect();
      await sshConnectionManager.disconnect();
      this.stateManager.setConnected(false);
      this.render();
      this.showMessage('已断开 SSH 连接', 'info');
      const cache = (window as any).systemInfoCache;
      if (cache) {
        cache.detailedInfo = null;
        cache.lastUpdate = null;
        cache.isLoading = false;
      }
      (window as any).stopDashboardAutoRefresh?.();
      (window as any).refreshServerList?.();
      (window as any).refreshSidebar?.();
      (window as any).refreshDashboard?.();
    } catch (error) {
      console.error('SSH 断开失败:', error);
      this.showMessage('SSH 断开失败', 'error');
    } finally {
      this.stateManager.setLoading(false);
    }
  }
  /**
   * 更新标题栏
   */
  private updateTitleBar(): void {
    // 只更新主题切换按钮，避免重新渲染整个标题栏
    this.updateThemeToggleButton();
  }
  /**
   * 更新主题切换按钮
   */
  private updateThemeToggleButton(): void {
    const currentTheme = this.stateManager.getState().theme;
    const buttons = document.querySelectorAll('.theme-switcher .segmented-btn');
    
    buttons.forEach(btn => {
      const themeValue = btn.getAttribute('data-theme-value');
      if (themeValue === currentTheme) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }
  /**
   * 获取应用状态
   */
  getState(): AppState {
    return this.stateManager.getState();
  }
  /**
   * 获取状态管理器
   */
  getStateManager(): StateManager {
    return this.stateManager;
  }
  /**
   * 获取 SSH 管理器
   */
  getSSHManager(): SSHManager {
    return this.sshManager;
  }
}
