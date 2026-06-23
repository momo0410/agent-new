/**
 * 现代化UI渲染器
 * 负责渲染应用的各个UI组件
 */

import type { StateManager } from '../core/stateManager';
import type { AppState } from '../ui/pageTypes';
import { aiService } from '../ai/aiService';
import { DashboardRenderer } from './dashboardRenderer';
import { sftpManager } from '../remote/sftpManager';
import { sshConnectionManager } from '../remote/sshConnectionManager';

import { SftpContextMenuRenderer } from './sftpContextMenu';
import { LogAnalysisRenderer } from './logAnalysisRenderer';
import { DatabaseRenderer } from './databaseRenderer';
import {
  List,
  Peoples,
  Earth,
  Rocket,
  Calendar,
  SettingTwo,
  ApplicationMenu,
  FolderOpen,
  CheckOne,
  CloseOne,
  Dashboard,
  Code,
  Plus,
  LinkInterrupt,
  Connection,
  User,
  Key,
  Refresh,
  Lock,
  Shield,
  Analysis,
  Fire,
  FileText,
  Config,
  NetworkTree,
  System,
  Time,
  SettingConfig,
  Cpu,
  Memory,
  Speed,
  LinkCloud,
  BookOpen,
  Log,
  Data,
  Left,
  Right,
  Message,
  Send,
  Loading,
  Copy
} from '@icon-park/svg';

import {
  getNavigationItemsForMode,
  type IconKey
} from './navigationConfig';
import { renderWorkspaceShell } from './layout/workspaceShell';
import { renderDashboardPage } from './pages/dashboardPage';
import { renderEmergencyCommandsPage } from './pages/emergencyCommandsPage';
import { getPageDefinitionMap, type PageDefinition } from './pages/pageRegistry';
import { renderQuickDetectionPage } from './pages/quickDetectionPage';
import { renderRemoteOperationsPage } from './pages/remoteOperationsPage';
import { renderSystemInfoPage } from './pages/systemInfoPage';
import type { AppPage } from './pageTypes';

const ICON_MAP: Record<IconKey, any> = {
  Dashboard,
  ApplicationMenu,
  FolderOpen,
  Code,
  Rocket,
  Data,
  Log,
  Calendar,
  SettingTwo,
  User,
  Lock,
  Shield,
  Analysis,
  Fire,
  FileText,
  Config,
  NetworkTree,
  System,
  Time,
  SettingConfig,
  Cpu,
  Memory,
  Speed,
  LinkCloud,
  BookOpen,
  Message,
  CheckOne,
  CloseOne,
  Refresh,
  Copy,
  Loading,
  Send
};

// 添加系统信息页面的样式
const systemInfoStyles = `
  <style>
    /* 基础样式已移至 system-info.css */
  </style>
`;

export class ModernUIRenderer {
  private stateManager: StateManager;
  private state: AppState;
  private dashboardRenderer: DashboardRenderer;
  public logAnalysisRenderer: LogAnalysisRenderer;
  public sftpContextMenuRenderer: SftpContextMenuRenderer;
  public databaseRenderer: DatabaseRenderer;
  private currentVisiblePage: AppPage = 'dashboard';

  constructor(stateManager: StateManager) {
    this.stateManager = stateManager;
    this.state = stateManager.getState();
    this.dashboardRenderer = new DashboardRenderer();
    this.logAnalysisRenderer = new LogAnalysisRenderer();
    this.sftpContextMenuRenderer = new SftpContextMenuRenderer();
    this.databaseRenderer = new DatabaseRenderer();

    // 注入系统信息页面样式
    if (!document.querySelector('#system-info-styles')) {
      const styleElement = document.createElement('div');
      styleElement.id = 'system-info-styles';
      styleElement.innerHTML = systemInfoStyles;
      document.head.appendChild(styleElement.firstElementChild!);
    }

    // 注册 System Info Header 切换函数
    (window as any).toggleSystemInfoHeader = () => {
      const header = document.querySelector('.system-info-header');
      const content = document.querySelector('.system-info-content');
      const toggleBtn = document.querySelector('.header-toggle-icon');
      
      if (header && content) {
        header.classList.toggle('collapsed');
        content.classList.toggle('expanded');
        
        // 保存状态到 localStorage
        const isCollapsed = header.classList.contains('collapsed');
        localStorage.setItem('system-info-header-collapsed', String(isCollapsed));
        
        // 更新按钮图标
        if (toggleBtn) {
          toggleBtn.innerHTML = isCollapsed 
            ? Right({ theme: 'outline', size: '16', fill: 'currentColor' })
            : Left({ theme: 'outline', size: '16', fill: 'currentColor' });
        }
      }
    };

    // 监听状态变化
    this.stateManager.addListener((newState) => {
      const oldTheme = this.state.theme;
      const oldConnected = this.state.isConnected;

      this.state = newState;

      // 如果主题或连接状态发生变化，重新渲染连接面板
      if (oldTheme !== newState.theme || oldConnected !== newState.isConnected) {
        console.log('🎨 状态监听器检测到变化，重新渲染连接面板', {
          oldTheme,
          newTheme: newState.theme,
          oldConnected,
          newConnected: newState.isConnected
        });
        this.rerenderConnectionPanel();

        // 如果是从未连接变为已连接，触发状态变化动画
        if (!oldConnected && newState.isConnected) {
          console.log('🎉 连接成功，触发状态变化动画');
          setTimeout(() => {
            const connectionCard = document.querySelector('.connection-card');
            if (connectionCard) {
              connectionCard.classList.add('status-change');
              setTimeout(() => {
                connectionCard.classList.remove('status-change');
              }, 800);
            }
          }, 50); // 等待DOM更新
        }
      }
    });

  }


  /**
   * 更新状态
   */
  updateState(newState: AppState): void {
    const oldTheme = this.state.theme;
    this.state = newState;

    console.log('🔄 ModernUIRenderer.updateState - 主题变化:', { oldTheme, newTheme: newState.theme });

    // 如果主题发生变化，重新渲染连接面板
    if (oldTheme !== newState.theme) {
      console.log('🎨 主题已变化，重新渲染连接面板');
      this.rerenderConnectionPanel();
    }
  }

  /**
   * 重新渲染连接面板
   */
  private rerenderConnectionPanel(): void {
    console.log('🔄 开始重新渲染连接面板，当前主题:', this.state.theme);

    const panelSlot = document.querySelector('.connection-panel-slot') as HTMLElement | null;
    if (panelSlot) {
      panelSlot.innerHTML = this.renderConnectionPanel();
      return;
    }

    const sidebar = document.querySelector('.modern-sidebar, .workspace-toolbar');
    if (!sidebar) {
      console.warn('⚠️ 未找到连接面板宿主');
      return;
    }

    // 查找连接卡片包装器
    let targetElement = sidebar.querySelector('.connection-card-wrapper');
    
    // 如果没找到 wrapper，尝试查找 card (兼容旧结构)
    if (!targetElement) {
        targetElement = sidebar.querySelector('.connection-card');
    }

    console.log('📍 找到连接卡片元素:', !!targetElement);

    if (targetElement) {
      // 创建临时容器
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = this.renderConnectionPanel();
      const newElement = tempDiv.firstElementChild;

      if (newElement) {
        console.log('✅ 替换连接卡片');
        // 替换旧元素
        targetElement.replaceWith(newElement);
      } else {
        console.warn('⚠️ 未能创建新卡片');
      }
    }
  }

  /**
   * 检测是否为 macOS
   */
  private isMacOS(): boolean {
    return navigator.platform.toUpperCase().indexOf('MAC') >= 0;
  }

  /**
   * 更新系统信息标签页的计数
   */
  public updateSystemInfoTabs(detailedInfo: any): void {
    if (!detailedInfo) return;

    const counts = {
      processes: detailedInfo.processes?.length || 0,
      network: detailedInfo.networkDetails?.length || 0,
      services: detailedInfo.services?.length || 0,
      users: detailedInfo.users?.length || 0,
      autostart: detailedInfo.autostart?.length || 0,
      cron: detailedInfo.cronJobs?.length || 0,
      firewall: detailedInfo.firewallRules?.length || 0
    };

    const tabNames: Record<string, string> = {
      processes: '进程详情',
      network: '网络详情',
      services: '系统服务',
      users: '用户列表',
      autostart: '自启动',
      cron: '计划任务',
      firewall: '防火墙'
    };

    const countKeys: Record<string, string> = {
      processes: 'processes',
      network: 'networkDetails',
      services: 'services',
      users: 'users',
      autostart: 'autostart',
      cron: 'cronJobs',
      firewall: 'firewallRules'
    };

    Object.keys(counts).forEach(key => {
      const tabBtn = document.querySelector(`.tab-btn[data-tab="${key}"]`);
      if (tabBtn) {
        const count = counts[key as keyof typeof counts];
        const hasLoadedData = Array.isArray(detailedInfo[countKeys[key]]);
        const label = tabBtn.querySelector('.tab-label');
        const existingBadge = tabBtn.querySelector('.count-badge');

        if (label) {
          label.textContent = tabNames[key] || key;
        }

        if (count > 0 || hasLoadedData) {
          if (existingBadge) {
            existingBadge.textContent = String(count);
            existingBadge.classList.remove('count-badge-loading');
          } else {
            tabBtn.insertAdjacentHTML('beforeend', `<span class="count-badge">${count}</span>`);
          }
        } else {
          existingBadge?.remove();
        }
      }
    });
  }

  /**
   * 渲染标题栏
   */
  renderTitleBar(): string {
    const isMac = this.isMacOS();

    return `
      <div class="modern-title-bar" data-tauri-drag-region>
        <div class="title-bar-left">
          <div class="app-logo">
            <div class="logo-icon" style="width: 30px; height: 30px; border-radius: var(--border-radius-lg); display: flex; align-items: center; justify-content: center; overflow: hidden;">
              <img src="/logo.png" alt="SDIT Logo" style="width: 100%; height: 100%; object-fit: contain;" />
            </div>
            <div class="app-info">
              <div class="app-name">安御智测</div>
            </div>
          </div>

        </div>

        <div class="title-bar-right">
          ${!isMac ? `
          <div class="window-controls">
            <button class="control-button minimize-btn" title="最小化">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                <rect x="2" y="5.5" width="8" height="1"/>
              </svg>
            </button>
            <button class="control-button maximize-btn" title="最大化">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                <rect x="2" y="2" width="8" height="8" stroke="currentColor" stroke-width="1" fill="none"/>
              </svg>
            </button>
            <button class="control-button close-btn close" title="关闭">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                <path d="M2.5 2.5L9.5 9.5M9.5 2.5L2.5 9.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </button>
          </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  /**
   * 渲染侧边栏
   */
  renderSidebar(): string {
    return `
      <div class="modern-sidebar mini-sidebar">
        <div class="sidebar-content">
          ${this.renderNavigationMenu()}
        </div>

        <!-- 右下角控制区 -->
        <div class="sidebar-right-controls">
          <div class="sidebar-settings-container">
            ${this.renderSettingsMenu()}
            <!-- 终端按钮 -->
            ${this.renderSSHTerminalTitleButton()}
            <button class="nav-item settings-btn" data-tooltip="设置" onclick="window.toggleSettingsDropdown()">
              <span class="nav-item-icon">
                ${SettingTwo({ theme: 'outline', size: '18', fill: 'currentColor' })}
              </span>
              <span class="nav-item-text">设置</span>
            </button>
          </div>
          <div>
            ${this.renderConnectionPanel()}
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 判断当前页面是否应隐藏左侧导航栏
   */
  public shouldHideSidebar(): boolean {
    return !this.state.isConnected;
  }

  /**
   * 渲染设置菜单
   */
  private renderSettingsMenu(): string {
    const currentTheme = this.state.theme;
    const aiQuickSummary = this.getAIQuickSummary();
    
    return `
      <div id="settings-dropdown-menu" class="settings-dropdown-menu">
        <div class="settings-group">
            <div class="settings-group-title">主题设置</div>
            <div class="segmented-control theme-switcher" style="width: 100%; padding: 3px;">
                <button type="button" class="segmented-btn ${currentTheme === 'light' ? 'active' : ''}" style="flex: 1; padding: 8px 10px;" data-theme-value="light" onclick="event.stopPropagation(); window.app?.setTheme('light')" title="浅色">浅色</button>
                <button type="button" class="segmented-btn ${currentTheme === 'dark' ? 'active' : ''}" style="flex: 1; padding: 8px 10px;" data-theme-value="dark" onclick="event.stopPropagation(); window.app?.setTheme('dark')" title="深色">深色</button>
            </div>
        </div>

        <div class="dropdown-divider"></div>

        <div class="settings-group">
            <div class="settings-group-title">基础设置</div>
            <div class="settings-field" style="margin-bottom: 12px;">
                <label style="font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px;">全局字体</label>
                <select id="dropdown-global-font" style="width: 100%; padding: 6px 8px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-primary); color: var(--text-primary); font-size: 13px;" onchange="window.app?.modernUIRenderer?.applyDropdownFont?.(this.value)">
                    <option value="system">系统默认</option>
                    <option value="Microsoft YaHei">微软雅黑</option>
                    <option value="SimSun">宋体</option>
                    <option value="Consolas">Consolas</option>
                    <option value="JetBrains Mono">JetBrains Mono</option>
                </select>
            </div>
        </div>

        <div class="dropdown-divider"></div>

        <div class="settings-group">
            <div class="settings-group-title">AI 配置</div>
            <button
                type="button"
                style="
                    width: 100%;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 12px;
                    padding: 12px;
                    border: 1px solid var(--border-color);
                    border-radius: 10px;
                    background: var(--bg-primary);
                    color: inherit;
                    cursor: pointer;
                    text-align: left;
                "
                onclick="event.stopPropagation(); window.openAISettingsMenu?.()"
            >
                <div style="min-width: 0; flex: 1;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap;">
                        <span style="font-size: 13px; font-weight: 600; color: var(--text-primary);">AI 配置菜单</span>
                        <span id="dropdown-ai-status-badge" style="padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; ${aiQuickSummary.configured ? 'background: rgba(34, 197, 94, 0.14); color: #16a34a;' : 'background: rgba(245, 158, 11, 0.14); color: #d97706;'}">${aiQuickSummary.badgeText}</span>
                    </div>
                    <div id="dropdown-ai-provider-summary" style="font-size: 13px; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${aiQuickSummary.providerName}</div>
                    <div id="dropdown-ai-model-summary" style="font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${aiQuickSummary.modelName}</div>
                    <div id="dropdown-ai-description" style="font-size: 12px; color: var(--text-secondary); line-height: 1.5; margin-top: 6px;">${aiQuickSummary.description}</div>
                </div>
                <div style="flex-shrink: 0; color: var(--text-secondary);">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M10 17l5-5-5-5v10z"/>
                    </svg>
                </div>
            </button>
        </div>


      </div>
    `;
  }

  /**
   * 渲染连接面板
   */
  private renderConnectionPanel(): string {
    const isConnected = this.state.isConnected;
    
    // 从状态中获取服务器信息
    let mainText = '连接服务器';
    let subText = '点击选择';

    if (isConnected && this.state.serverInfo) {
      mainText = this.state.serverInfo.name || this.state.serverInfo.host;
      subText = `${this.state.serverInfo.host}`;
    }

    return `
      <div class="connection-card-wrapper">
        <!-- 向上弹出的菜单 -->
        <div id="connection-dropdown-menu" class="connection-dropdown-menu">
          ${this.renderConnectionDropdownContent()}
        </div>

        <div class="connection-card ${isConnected ? 'connected' : ''}" onclick="window.toggleConnectionDropdown()" data-tooltip="${mainText}">
          
          <!-- Icon Area -->
          <div class="connection-card-icon">
             ${isConnected 
               ? Connection({ theme: 'filled', size: '16', fill: 'currentColor' }) 
               : Plus({ theme: 'outline', size: '16', fill: 'currentColor' })
             }
             ${isConnected ? `<div class="connection-status-dot"></div>` : ''}
          </div>

          <!-- Text Info -->
          <div class="connection-card-info">
             <div class="connection-card-title" title="${mainText}">
                ${mainText}
             </div>
             <div class="connection-card-subtitle" title="${subText}">
                ${subText}
             </div>
          </div>
          
          <!-- Settings/Menu Icon -->
          <div class="connection-card-action">
             ${SettingConfig({ theme: 'outline', size: '16', fill: 'currentColor' })}
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 渲染导航菜单
   */
  private renderNavigationMenu(): string {
    const currentPage = this.state.currentPage;
    const uiMode = this.state.uiMode;
    const navItems = getNavigationItemsForMode(uiMode);

    return `
      <div class="nav-category">
        ${navItems.map(item => {
            const isActive = item.id === currentPage;
            const iconFn = ICON_MAP[item.iconKey];
            const fallbackIcon = iconFn ? iconFn({ theme: 'outline', size: '22', fill: 'currentColor' }) : '';
            const customIconSrc = item.id === 'dashboard'
              ? '/icons/dashboard.png'
              : item.id === 'system-info'
                ? '/icons/system-info.png'
                : item.id === 'remote-operations'
                  ? '/icons/sftp-file.png'
                  : item.id === 'emergency-commands'
                    ? '/icons/command-execute.png'
                    : item.id === 'quick-detection'
                      ? '/icons/quick-detection.png'
                      : item.id === 'database'
                        ? '/icons/database.png'
                        : item.id === 'payloader'
                            ? '/icons/payload-tool.png'
                : '';
            const icon = customIconSrc
              ? `
                <img
                  class="nav-custom-icon nav-custom-icon-${item.id}"
                  src="${customIconSrc}"
                  alt=""
                  onload="this.nextElementSibling.classList.add('hidden')"
                  onerror="this.classList.add('hidden')"
                />
                <span class="nav-icon-fallback">${fallbackIcon}</span>
              `
              : fallbackIcon;
            const tooltipText = item.title;

            return `
              <div class="nav-item ${isActive ? 'active' : ''}" data-nav-id="${item.id}" data-tooltip="${tooltipText}">

                ${isActive ? `<div class="nav-item-indicator"></div>` : ''}

                <span class="nav-item-icon">
                    ${icon}
                </span>
                <span class="nav-item-text">${item.title}</span>
              </div>
            `;
        }).join('')}
      </div>
    `;
  }

  /**
   * macOS Dock magnification effect - 推开相邻图标
   */
  private dockMagnify = (e: MouseEvent): void => {
    const navItems = Array.from(document.querySelectorAll('.modern-sidebar.mini-sidebar .nav-item, .modern-sidebar.mini-sidebar .connection-card')) as HTMLElement[];
    if (navItems.length === 0) return;

    const mouseX = e.clientX;
    const maxScale = 1.6; // 最大放大1.6倍
    const baseSize = 44; // 基础尺寸
    const range = 180; // 影响范围

    navItems.forEach((item) => {
      const rect = item.getBoundingClientRect();
      const itemCenterX = rect.left + rect.width / 2;
      const distance = Math.abs(mouseX - itemCenterX);

      // 获取图标元素（SVG或IMG）
      const iconElement = item.querySelector('.nav-item-icon svg, .nav-item-icon img');
      
      if (distance < range) {
        const ratio = 1 - distance / range;
        const easedRatio = Math.pow(ratio, 2); // 二次方缓动
        const scale = 1 + (maxScale - 1) * easedRatio;
        const newSize = baseSize * scale;
        
        // 动态修改容器尺寸，让flexbox自动推开相邻元素
        item.style.width = `${newSize}px`;
        item.style.height = `${newSize}px`;
        item.style.transition = 'all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)';
        item.style.zIndex = Math.round(easedRatio * 10).toString();
        item.classList.add('dock-magnified');
        
        // 同时放大内部图标元素
        if (iconElement) {
          const iconEl = iconElement as HTMLElement;
          iconEl.style.transform = `scale(${scale})`;
          iconEl.style.transition = 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)';
        }
      } else {
        // 恢复原始尺寸
        item.style.width = `${baseSize}px`;
        item.style.height = `${baseSize}px`;
        item.style.transition = '';
        item.style.zIndex = '';
        item.classList.remove('dock-magnified');
        
        // 恢复图标原始尺寸
        if (iconElement) {
          const iconEl = iconElement as HTMLElement;
          iconEl.style.transform = '';
          iconEl.style.transition = '';
        }
      }
    });
  }

  private dockReset = (): void => {
    const navItems = document.querySelectorAll('.modern-sidebar.mini-sidebar .nav-item, .modern-sidebar.mini-sidebar .connection-card');
    navItems.forEach(item => {
      const el = item as HTMLElement;
      // 恢复容器原始尺寸
      el.style.width = '44px';
      el.style.height = '44px';
      el.style.transition = '';
      el.style.zIndex = '';
      el.classList.remove('dock-magnified');
      
      // 恢复图标原始尺寸
      const iconElement = el.querySelector('.nav-item-icon svg, .nav-item-icon img');
      if (iconElement) {
        const iconEl = iconElement as HTMLElement;
        iconEl.style.transform = '';
        iconEl.style.transition = '';
      }
    });
  }

  /**
   * 为 mini-sidebar 的导航项绑定 JS tooltip 和 Dock 动效
   */
  public bindMiniSidebarTooltips(): void {
    const navItems = document.querySelectorAll(
      '.modern-sidebar.mini-sidebar .nav-item[data-tooltip], .modern-sidebar.mini-sidebar .connection-card[data-tooltip]'
    );

    const sidebar = document.querySelector('.modern-sidebar.mini-sidebar') as HTMLElement;
    if (sidebar) {
      sidebar.removeEventListener('mousemove', this.dockMagnify);
      sidebar.removeEventListener('mouseleave', this.dockReset);
      sidebar.addEventListener('mousemove', this.dockMagnify);
      sidebar.addEventListener('mouseleave', this.dockReset);
    }

    navItems.forEach((el) => {
      const item = el as HTMLElement;
      item.addEventListener('mouseenter', (e: MouseEvent) => {
        this.showTooltip(e.currentTarget as HTMLElement);
      });
      item.addEventListener('mouseleave', () => {
        this.hideTooltip();
      });
    });
  }

  private tooltipEl?: HTMLElement;

  private showTooltip(el: HTMLElement): void {
    const text = el.getAttribute('data-tooltip');
    if (!text) return;

    if (!this.tooltipEl) {
      this.tooltipEl = document.createElement('div');
      this.tooltipEl.className = 'mini-sidebar-tooltip';
      document.body.appendChild(this.tooltipEl);
    }

    this.tooltipEl.textContent = text;
    this.tooltipEl.style.display = 'block';

    const rect = el.getBoundingClientRect();
    const tooltipWidth = this.tooltipEl.offsetWidth;
    const viewportPadding = 12;
    const centeredLeft = rect.left + rect.width / 2;
    const minLeft = tooltipWidth / 2 + viewportPadding;
    const maxLeft = window.innerWidth - tooltipWidth / 2 - viewportPadding;
    const tooltipLeft = maxLeft > minLeft
      ? Math.min(Math.max(centeredLeft, minLeft), maxLeft)
      : window.innerWidth / 2;

    this.tooltipEl.style.top = `${rect.top - 10}px`;
    this.tooltipEl.style.left = `${tooltipLeft}px`;
  }

  private hideTooltip(): void {
    if (this.tooltipEl) {
      this.tooltipEl.style.display = 'none';
    }
  }

  public hideMiniSidebarTooltip(): void {
    this.hideTooltip();
  }

  private getAIQuickSummary(): {
    configured: boolean;
    providerName: string;
    modelName: string;
    badgeText: string;
    description: string;
  } {
    const config = aiService.getConfig();
    const configured = aiService.isConfigured();
    const providerName = config?.name?.trim()
      || this.getAIProviderDisplayName(config?.provider || '');
    const modelName = config?.model?.trim() || '未配置模型';

    return {
      configured,
      providerName,
      modelName,
      badgeText: configured ? '已配置' : '未配置',
      description: configured
        ? '日志分析、检测报告、文件分析等页面会统一使用这里的模型'
        : '配置后，各个页面的 AI 分析都会统一使用这里的模型',
    };
  }

  private getAIProviderDisplayName(provider: string): string {
    const normalized = provider.trim().toLowerCase();
    switch (normalized) {
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
        return '自定义模型';
      default:
        return normalized || '未配置提供商';
    }
  }

  public syncSettingsDropdownState(): void {
    const fontSelect = document.getElementById('dropdown-global-font') as HTMLSelectElement | null;
    const storedFont = localStorage.getItem('LERT-font') || 'system';
    if (fontSelect) {
      fontSelect.value = Array.from(fontSelect.options).some((option) => option.value === storedFont)
        ? storedFont
        : 'system';
    }

    const fontSizeInput = document.getElementById('dropdown-font-size') as HTMLInputElement | null;
    const fontSizeLabel = document.getElementById('dropdown-font-size-value');
    const storedFontSize = localStorage.getItem('LERT-font-size') || '14';
    if (fontSizeInput) {
      fontSizeInput.value = storedFontSize;
    }
    if (fontSizeLabel) {
      fontSizeLabel.textContent = `${storedFontSize}px`;
    }

    const summary = this.getAIQuickSummary();
    const providerEl = document.getElementById('dropdown-ai-provider-summary');
    const modelEl = document.getElementById('dropdown-ai-model-summary');
    const badgeEl = document.getElementById('dropdown-ai-status-badge');
    const descEl = document.getElementById('dropdown-ai-description');

    if (providerEl) {
      providerEl.textContent = summary.providerName;
    }
    if (modelEl) {
      modelEl.textContent = summary.modelName;
    }
    if (badgeEl) {
      badgeEl.textContent = summary.badgeText;
      badgeEl.setAttribute(
        'style',
        `padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; ${
          summary.configured
            ? 'background: rgba(34, 197, 94, 0.14); color: #16a34a;'
            : 'background: rgba(245, 158, 11, 0.14); color: #d97706;'
        }`
      );
    }
    if (descEl) {
      descEl.textContent = summary.description;
    }
  }

  /**
   * 应用下拉菜单中的字体设置
   */
  public applyDropdownFont(font: string): void {
    if (font && font !== 'system') {
      document.documentElement.style.setProperty('--font-family', font);
      localStorage.setItem('LERT-font', font);
    } else {
      document.documentElement.style.removeProperty('--font-family');
      localStorage.removeItem('LERT-font');
    }
  }

  /**
   * 应用下拉菜单中的字体大小设置
   */
  public applyDropdownFontSize(size: string): void {
    const px = parseInt(size, 10);
    if (!isNaN(px)) {
      document.documentElement.style.setProperty('--base-font-size', `${px}px`);
      localStorage.setItem('LERT-font-size', String(px));
    }
  }

  /**
   * 渲染主工作区
   */
  renderMainWorkspace(): string {
    this.currentVisiblePage = this.state.currentPage;
    return renderWorkspaceShell('<div id="workspace-vue-root" class="workspace-pages-host"></div>');
  }

  /**
   * 激活当前页面（触发数据加载等初始化逻辑）
   * 用于初始渲染后激活默认页面
   */
  activateCurrentPage(): void {
    const pageId = this.currentVisiblePage;
    if (pageId) {
      this.onPageActivated(pageId);
    }
  }

  /**
   * 切换页面（仅切换 display，不重建 DOM）
   */
  switchToPage(pageId: AppPage): void {
    this.currentVisiblePage = pageId;
  }

  /**
   * 刷新单个页面的容器内容（保留容器外层，只替换内部 HTML）
   */
  refreshPageContainer(pageId: AppPage): void {
    window.dispatchEvent(new CustomEvent('workspace-page-refresh', {
      detail: { pageId }
    }));
  }

  /**
   * 页面激活钩子
   */
  private onPageActivated(pageId: AppPage): void {
    this.applyPageScrollMode(pageId, true);

    switch (pageId) {
      case 'dashboard':
        setTimeout(() => {
          const app = (window as any).app;
          if (app?.sshManager && !app.sshManager.getSystemInfo()) {
            void (async () => {
              try {
                const liveStatus = await sshConnectionManager.checkConnectionStatus(false);
                if (!liveStatus?.connected) {
                  console.debug('跳过 dashboard 摘要加载：后端连接状态不可用');
                  return;
                }
                await app.sshManager.fetchSystemSummary();
                this.refreshPageContainer('dashboard');
              } catch (error) {
                console.warn('⚠️ 获取系统摘要失败:', error);
              }
            })();
          }
          const inst = (window as any).dashboardRendererInstance;
          if (inst?.initCharts) {
            inst.initCharts(false);
          }
          (window as any).adjustDashboardLayout?.();
          this.scheduleLayoutStabilization('dashboard');
          (window as any).startDashboardAutoRefresh?.();
        }, 50);
        break;
      case 'system-info':
        setTimeout(() => {
          const cache = (window as any).systemInfoCache;
          if (cache) {
            cache.isLoading = false;
          }
          this.scheduleLayoutStabilization('system-info');
          (window as any).loadSystemDetailedInfo?.(false);
        }, 50);
        break;
      case 'remote-operations':
        setTimeout(() => {
          (window as any).initRemoteOperationsPage?.();
        }, 50);
        break;
      case 'emergency-commands':
        setTimeout(() => {
          (window as any).emergencyPageManager?.initialize();
        }, 50);
        break;
      case 'quick-detection':
        setTimeout(() => {
          (window as any).quickDetection?.refreshHistoryUI?.();
        }, 50);
        break;
      case 'log-analysis':
        setTimeout(() => {
          (window as any).refreshLogAnalysis?.();
        }, 200);
        break;
      case 'database':
        break;
    }
  }

  /**
   * 页面失活钩子
   */
  private onPageDeactivated(pageId: AppPage): void {
    this.savePageUIState(pageId);
    this.applyPageScrollMode(pageId, false);

    switch (pageId) {
      case 'dashboard':
        (window as any).stopDashboardAutoRefresh?.();
        break;
    }
  }

  public getPageHTMLForVue(pageId: AppPage): string {
    return this.getPageHTML(pageId);
  }

  public activatePageForVue(pageId: AppPage): void {
    this.currentVisiblePage = pageId;
    this.onPageActivated(pageId);
  }

  public deactivatePageForVue(pageId: AppPage): void {
    this.onPageDeactivated(pageId);
  }

  public renderLoadingStateForVue(): string {
    return this.renderLoadingState();
  }

  private scheduleLayoutStabilization(pageId: AppPage): void {
    const run = () => {
      if (this.currentVisiblePage !== pageId) return;

      const pageEl = document.getElementById(`page-${pageId}`) as HTMLElement | null;
      if (!pageEl || pageEl.offsetParent === null) return;

      // Force a reflow before resize so percentage/flex heights settle on first paint.
      void pageEl.offsetHeight;

      try {
        window.dispatchEvent(new Event('resize'));
      } catch {
        // ignore
      }
    };

    const raf = window.requestAnimationFrame || ((cb: FrameRequestCallback) => window.setTimeout(cb, 16));

    raf(() => {
      run();
      raf(() => run());
    });

    window.setTimeout(run, 80);
    window.setTimeout(run, 180);
  }

  private applyPageScrollMode(pageId: AppPage, active: boolean): void {
    const workspaceContent = document.getElementById('workspace-content') as HTMLElement | null;
    const pageEl = document.getElementById(`page-${pageId}`) as HTMLElement | null;

    if (pageId === 'system-info') {
      if (workspaceContent) {
        workspaceContent.style.overflowY = active ? 'hidden' : '';
      }
      if (pageEl) {
        pageEl.style.overflowY = active ? 'hidden' : '';
      }
      return;
    }

    if (active && workspaceContent && !workspaceContent.style.overflowY) {
      workspaceContent.style.overflowY = '';
    }
  }

  public renderConnectionPromptForVue(): string {
    return this.renderConnectionPrompt();
  }

  private savePageUIState(pageId: AppPage): void {
    const container = document.getElementById(`page-${pageId}`);
    if (!container) return;

    const state: Record<string, any> = {};

    const activeTab = container.querySelector('.tab-btn.active');
    if (activeTab) {
      state.activeTab = activeTab.getAttribute('data-tab') || '';
    }

    const searchInput = container.querySelector<HTMLInputElement>('input[type="search"], .search-input, input.search-box');
    if (searchInput) {
      state.searchQuery = searchInput.value;
    }

    const filterSelect = container.querySelector<HTMLSelectElement>('select.filter-select, [id$="-filter"]');
    if (filterSelect) {
      state.filterValue = filterSelect.value;
    }

    const scrollContainer = container.querySelector('.page-content, .tab-content, .log-list, .table-container, .sftp-main-content');
    if (scrollContainer) {
      state.scrollTop = scrollContainer.scrollTop;
    }

    const sortSelect = container.querySelector<HTMLSelectElement>('#sftp-sort-mode, [id$="-sort"]');
    if (sortSelect) {
      state.sortMode = sortSelect.value;
    }

    this.stateManager.savePageState(pageId, state);
  }

  /**
   * 获取指定页面的 HTML 内容
   */
  getPageHTML(pageId: AppPage): string {
    const page = this.getPageDefinitions()[pageId];
    return page ? page.render() : this.renderDashboard();
  }

  private getPageDefinitions(): Record<AppPage, PageDefinition> {
    return getPageDefinitionMap([
      { id: 'dashboard', render: () => this.renderDashboard() },
      { id: 'system-info', render: () => this.renderSystemInfo() },
      { id: 'ssh-terminal', render: () => this.renderSSHTerminalRedirect() },
      { id: 'remote-operations', render: () => this.renderRemoteOperationsPage() },
      { id: 'emergency-commands', render: () => this.renderEmergencyCommandsPage() },
      { id: 'quick-detection', render: () => this.renderQuickDetectionPage() },
      { id: 'database', render: () => this.databaseRenderer.render() },
      { id: 'log-analysis', render: () => this.logAnalysisRenderer.render() },
      { id: 'payloader', render: () => this.renderPayloaderPage() }
    ]);
  }



  /**
   * 渲染连接下拉菜单内容
   */
  renderConnectionDropdownContent(): string {
    const sshManager = (window as any).app?.sshManager;
    const connections = sshManager ? sshManager.getConnections() : [];
    // 优先使用 getActiveConnection，如果不行则遍历 connections 找一个已连接的
    const activeConnection = (sshManager ? sshManager.getActiveConnection() : null) 
        || connections.find((c: any) => c.isConnected);

    let menuItems = '';

    // 如果已连接，显示断开连接选项
    if (activeConnection) {
      const disconnectIcon = LinkInterrupt({ theme: 'outline', size: '16', fill: 'currentColor' });
      menuItems += `
        <div class="dropdown-item danger" onclick="window.disconnectServer('${activeConnection.id}'); window.hideConnectionDropdown();">
          <div class="dropdown-item-icon danger">
              ${disconnectIcon}
          </div>
          <div class="dropdown-item-content">
            <span class="dropdown-item-title">断开当前连接</span>
            <span class="dropdown-item-subtitle">${activeConnection.name}</span>
          </div>
        </div>
        <div class="dropdown-divider"></div>
      `;
    }

    // 添加新连接选项 - 放在顶部作为主要操作
    menuItems += `
      <div class="dropdown-item primary" onclick="window.showServerModal(); window.hideConnectionDropdown();">
        <div class="dropdown-item-icon primary">
            ${Plus({ theme: 'outline', size: '16', fill: 'currentColor' })}
        </div>
        <div class="dropdown-item-content">
            <span class="dropdown-item-title">添加新服务器</span>
            <span class="dropdown-item-subtitle">配置 SSH 连接</span>
        </div>
      </div>
      <div class="dropdown-divider"></div>
    `;

    if (connections.length > 0) {
      menuItems += `
        <div class="dropdown-section-title">
          <span>快速连接</span>
          <span class="count-badge">${connections.length}</span>
        </div>
        <div class="dropdown-scroll-area">
      `;

      connections.forEach((conn: any) => {
        const isConnected = conn.isConnected;
        
        menuItems += `
          <div class="dropdown-item ${isConnected ? 'active' : ''}" onclick="window.connectServer('${conn.id}'); window.hideConnectionDropdown();">
            
            <div class="dropdown-item-icon ${isConnected ? 'success' : 'default'}">
                ${isConnected 
                    ? CheckOne({ theme: 'filled', size: '16', fill: 'currentColor' }) 
                    : System({ theme: 'outline', size: '16', fill: 'currentColor' })
                }
                ${isConnected ? `<div class="status-dot"></div>` : ''}
            </div>

            <div class="dropdown-item-content">
              <span class="dropdown-item-title">${conn.name}</span>
              <span class="dropdown-item-subtitle">${conn.username}@${conn.host}</span>
            </div>
            
            ${isConnected ? `
                <div class="status-badge">运行中</div>
            ` : ''}
          </div>
        `;
      });
      
      menuItems += `</div>`; // Close scroll container
    } else {
      menuItems += `
        <div class="dropdown-empty-state">
          <div class="empty-icon">
            ${Connection({ theme: 'outline', size: '24', fill: 'currentColor' })}
          </div>
          <div class="empty-text">暂无已保存的服务器</div>
        </div>
      `;
    }

    return menuItems;
  }


  /**
   * 渲染系统信息页面
   */
  private renderSystemInfo(): string {
    const { counts, knownTabs } = this.getSystemInfoTabCounts();
    return renderSystemInfoPage({
      counts,
      knownTabs,
      renderInitialTab: () => this.renderSystemInfoTab('processes')
    });
  }

  private getSystemInfoTabCounts(): {
    counts: Record<'processes' | 'network' | 'services' | 'users' | 'autostart' | 'cron' | 'firewall', number>;
    knownTabs: Set<string>;
  } {
    const detailedInfo = this.state.serverInfo?.detailedInfo || {};
    const tabCache = (window as any).systemInfoCache?.tabs || {};
    const knownTabs = new Set<string>();
    const countArray = (value: unknown): number => Array.isArray(value) ? value.length : 0;

    const counts = {
      processes: countArray(detailedInfo.processes),
      network: countArray(detailedInfo.networkDetails),
      services: countArray(detailedInfo.services),
      users: countArray(detailedInfo.users),
      autostart: countArray(detailedInfo.autostart),
      cron: countArray(detailedInfo.cronJobs),
      firewall: countArray(detailedInfo.firewallRules)
    };

    const cacheMap: Record<keyof typeof counts, string> = {
      processes: 'processes',
      network: 'networkDetails',
      services: 'services',
      users: 'users',
      autostart: 'autostart',
      cron: 'cronJobs',
      firewall: 'firewallRules'
    };

    (Object.keys(cacheMap) as Array<keyof typeof counts>).forEach((tabId) => {
      const detailKey = cacheMap[tabId];
      const cachedData = tabCache[tabId]?.data?.[detailKey];
      if (Array.isArray(cachedData)) {
        counts[tabId] = cachedData.length;
        knownTabs.add(tabId);
      } else if (Array.isArray(detailedInfo[detailKey])) {
        knownTabs.add(tabId);
      }
    });

    return { counts, knownTabs };
  }

  /**
   * 渲染系统信息标签页内容
   */
  private renderSystemInfoTab(tab: string): string {
    // 这里暂时返回占位内容，实际数据需要从系统信息管理器获取
    switch (tab) {
      case 'processes':
        return this.renderProcessesTable();
      case 'network':
        return this.renderNetworkTable();
      case 'services':
        return this.renderServicesTable();
      case 'users':
        return this.renderUsersTable();
      case 'autostart':
        return this.renderAutostartTable();
      case 'cron':
        return this.renderCronTable();
      case 'firewall':
        return this.renderFirewallTable();
      default:
        return '<p>选择一个标签页查看详细信息</p>';
    }
  }

  /**
   * 渲染进程表格
   */
  private renderSystemInfoRefreshButton(): string {
    return `
      <button class="page-refresh-btn system-info-inline-refresh" onclick="window.refreshAllSystemInfo()" title="刷新当前系统信息">
        ${Refresh({ theme: 'outline', size: '16', fill: 'currentColor' })}
        <span>刷新数据</span>
      </button>
    `;
  }

  /**
   * 渲染进程表格
   */
  private renderProcessesTable(): string {
    return `
      <div class="info-table-container">
        <div class="table-header-toolbar">
          <span class="table-title">
            ${List({ theme: 'outline', size: '20', fill: 'currentColor' })}
            运行中的进程
          </span>
          <div class="search-container">
            ${this.renderSystemInfoRefreshButton()}
            <select
              id="processes-filter"
              class="system-select"
              style="width: 100px;"
              onchange="window.filterTableByCategory('processes', this.value)"
            >
              <option value="">所有用户</option>
            </select>
            <select
              id="processes-stat-filter"
              class="system-select"
              style="width: 100px;"
              onchange="window.filterTableByStatus('processes', this.value)"
            >
              <option value="">所有状态</option>
              <option value="R">运行中 (R)</option>
              <option value="S">休眠 (S)</option>
              <option value="D">不可中断 (D)</option>
              <option value="Z">僵尸 (Z)</option>
              <option value="T">停止 (T)</option>
            </select>
            <input
              type="text"
              id="processes-search"
              class="system-input"
              placeholder="搜索进程..."
              style="width: 120px;"
              oninput="window.filterTable('processes', this.value)"
            />
            <button
              class="system-btn"
              onclick="document.getElementById('processes-search').value = ''; document.getElementById('processes-filter').value = ''; document.getElementById('processes-stat-filter').value = ''; window.filterTable('processes', '');"
            >清除</button>
          </div>
        </div>
        <div class="table-content">
          <table class="system-table">
            <thead>
              <tr>
                <th>PID</th>
                <th>用户</th>
                <th>状态</th>
                <th>CPU%</th>
                <th>内存%</th>
                <th>命令</th>
              </tr>
            </thead>
            <tbody id="processes-table-body">
              <tr>
                <td colspan="6" style="padding: var(--spacing-lg); text-align: center; color: var(--text-secondary);">
                  正在加载进程信息...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div id="processes-pagination" class="table-pagination-container"></div>
      </div>
    `;
  }

  /**
   * 渲染网络表格
   */
  private renderNetworkTable(): string {
    return `
      <div class="info-table-container">
        <div class="table-header-toolbar">
          <span class="table-title">
            ${Earth({ theme: 'outline', size: '20', fill: 'currentColor' })}
            网络连接详情
          </span>
          <div class="search-container">
            ${this.renderSystemInfoRefreshButton()}
            <select
              id="network-filter"
              class="system-select"
              style="width: 120px;"
              onchange="window.filterTableByCategory('network', this.value)"
            >
              <option value="">所有状态</option>
              <option value="LISTEN">LISTEN</option>
              <option value="ESTAB">ESTAB</option>
              <option value="TIME_WAIT">TIME_WAIT</option>
              <option value="CLOSE_WAIT">CLOSE_WAIT</option>
              <option value="SYN_SENT">SYN_SENT</option>
              <option value="SYN_RECV">SYN_RECV</option>
              <option value="FIN_WAIT1">FIN_WAIT1</option>
              <option value="FIN_WAIT2">FIN_WAIT2</option>
              <option value="CLOSED">CLOSED</option>
            </select>
            <input
              type="text"
              id="network-search"
              class="system-input"
              placeholder="搜索连接..."
              style="width: 150px;"
              oninput="window.filterTable('network', this.value)"
            />
            <button
              class="system-btn"
              onclick="document.getElementById('network-search').value = ''; document.getElementById('network-filter').value = ''; window.filterTable('network', '');"
            >清除</button>
          </div>
        </div>
        <div class="table-content">
          <table class="system-table">
            <thead>
              <tr>
                <th>协议</th>
                <th>本地地址</th>
                <th>远程地址</th>
                <th>状态</th>
                <th>PID</th>
                <th>进程</th>
              </tr>
            </thead>
            <tbody id="network-table-body">
              <tr>
                <td colspan="6" style="padding: var(--spacing-lg); text-align: center; color: var(--text-secondary);">
                  正在加载网络连接信息...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div id="network-pagination" class="table-pagination-container"></div>
      </div>
    `;
  }

  /**
   * 渲染系统服务表格
   */
  private renderServicesTable(): string {
    return `
      <div class="info-table-container">
        <div class="table-header-toolbar">
          <span class="table-title">
            ${SettingTwo({ theme: 'outline', size: '20', fill: 'currentColor' })}
            系统服务状态
          </span>
          <div class="search-container">
            ${this.renderSystemInfoRefreshButton()}
            <select
              id="services-filter"
              class="system-select"
              style="width: 100px;"
              onchange="window.filterTableByCategory('services', this.value)"
            >
              <option value="">所有状态</option>
              <option value="active">active</option>
              <option value="inactive">inactive</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
              <option value="stopped">stopped</option>
            </select>
            <input
              type="text"
              id="services-search"
              class="system-input"
              placeholder="搜索服务..."
              style="width: 120px;"
              oninput="window.filterTable('services', this.value)"
            />
            <button
              class="system-btn"
              onclick="document.getElementById('services-search').value = ''; document.getElementById('services-filter').value = ''; window.filterTable('services', '');"
            >清除</button>
          </div>
        </div>
        <div class="table-content">
          <table class="system-table">
            <thead>
              <tr>
                <th>服务名</th>
                <th>状态</th>
                <th>启用状态</th>
                <th>描述</th>
              </tr>
            </thead>
            <tbody id="services-table-body">
              <tr>
                <td colspan="4" style="padding: var(--spacing-lg); text-align: center; color: var(--text-secondary);">
                  正在加载系统服务信息...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div id="services-pagination" class="table-pagination-container"></div>
      </div>
    `;
  }

  /**
   * 渲染用户列表表格
   */
  private renderUsersTable(): string {
    return `
      <div class="info-table-container">
        <div class="table-header-toolbar">
          <span class="table-title">
            ${Peoples({ theme: 'outline', size: '20', fill: 'currentColor' })}
            系统用户列表
          </span>
          <div class="search-container">
            ${this.renderSystemInfoRefreshButton()}
            <select
              id="users-filter"
              class="system-select"
              style="width: 120px;"
              onchange="window.filterTableByCategory('users', this.value)"
            >
              <option value="">所有Shell</option>
              <option value="/bin/bash">/bin/bash</option>
              <option value="/bin/sh">/bin/sh</option>
              <option value="/usr/sbin/nologin">/usr/sbin/nologin</option>
              <option value="/bin/false">/bin/false</option>
              <option value="/usr/bin/zsh">/usr/bin/zsh</option>
              <option value="/bin/dash">/bin/dash</option>
            </select>
            <input
              type="text"
              id="users-search"
              class="system-input"
              placeholder="搜索用户..."
              style="width: 100px;"
              oninput="window.filterTable('users', this.value)"
            />
            <button
              class="system-btn"
              onclick="document.getElementById('users-search').value = ''; document.getElementById('users-filter').value = ''; window.filterTable('users', '');"
            >清除</button>
          </div>
        </div>
        <div class="table-content">
          <table class="system-table">
            <thead>
              <tr>
                <th>用户名</th>
                <th>UID</th>
                <th>GID</th>
                <th>主目录</th>
                <th>Shell</th>
              </tr>
            </thead>
            <tbody id="users-table-body">
              <tr>
                <td colspan="5" style="padding: var(--spacing-lg); text-align: center; color: var(--text-secondary);">
                  正在加载用户信息...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div id="users-pagination" class="table-pagination-container"></div>
      </div>
    `;
  }

  /**
   * 渲染自启动服务表格
   */
  private renderAutostartTable(): string {
    return `
      <div class="info-table-container">
        <div class="table-header-toolbar">
          <span class="table-title">
            ${Rocket({ theme: 'outline', size: '20', fill: 'currentColor' })}
            自启动服务
          </span>
          <div class="search-container">
            ${this.renderSystemInfoRefreshButton()}
            <input
              type="text"
              id="autostart-search"
              class="system-input"
              placeholder="搜索服务..."
              style="width: 150px;"
              oninput="window.filterTable('autostart', this.value)"
            />
            <button
              class="system-btn"
              onclick="document.getElementById('autostart-search').value = ''; window.filterTable('autostart', '');"
            >清除</button>
          </div>
        </div>
        <div class="table-content">
          <table class="system-table">
            <thead>
              <tr>
                <th>服务名</th>
                <th>命令</th>
                <th>状态</th>
                <th>类型</th>
              </tr>
            </thead>
            <tbody id="autostart-table-body">
              <tr>
                <td colspan="4" style="padding: var(--spacing-lg); text-align: center; color: var(--text-secondary);">
                  正在加载自启动服务信息...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div id="autostart-pagination" class="table-pagination-container"></div>
      </div>
    `;
  }

  /**
   * 渲染计划任务表格
   */
  private renderCronTable(): string {
    return `
      <div class="info-table-container">
        <div class="table-header-toolbar">
          <span class="table-title">
            ${Calendar({ theme: 'outline', size: '20', fill: 'currentColor' })}
            计划任务 (Cron Jobs)
          </span>
          <div class="search-container">
            ${this.renderSystemInfoRefreshButton()}
            <input
              type="text"
              id="cron-search"
              class="system-input"
              placeholder="搜索任务..."
              style="width: 150px;"
              oninput="window.filterTable('cron', this.value)"
            />
            <button
              class="system-btn"
              onclick="document.getElementById('cron-search').value = ''; window.filterTable('cron', '');"
            >清除</button>
          </div>
        </div>
        <div class="table-content">
          <table class="system-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>时间表</th>
                <th>命令</th>
              </tr>
            </thead>
            <tbody id="cron-table-body">
              <tr>
                <td colspan="3" style="padding: var(--spacing-lg); text-align: center; color: var(--text-secondary);">
                  正在加载计划任务信息...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div id="cron-pagination" class="table-pagination-container"></div>
      </div>
    `;
  }

  /**
   * 渲染防火墙表格
   */
  private renderFirewallTable(): string {
    return `
      <div class="info-table-container">
        <div class="table-header-toolbar">
          <span class="table-title">
            ${Fire({ theme: 'outline', size: '20', fill: 'currentColor' })}
            防火墙规则
          </span>
          <div class="search-container">
            ${this.renderSystemInfoRefreshButton()}
            <select
              id="firewall-type-filter"
              class="system-select"
              style="width: 100px;"
              onchange="window.filterTableByCategory('firewall', this.value)"
            >
              <option value="">所有规则</option>
              <option value="iptables">iptables</option>
              <option value="firewalld">firewalld</option>
              <option value="ufw">UFW</option>
            </select>
            <input
              type="text"
              id="firewall-search"
              class="system-input"
              placeholder="搜索规则..."
              style="width: 150px;"
              oninput="window.filterTable('firewall', this.value)"
            />
            <button
              class="system-btn"
              onclick="document.getElementById('firewall-search').value = ''; document.getElementById('firewall-type-filter').value = ''; window.filterTable('firewall', '');"
            >清除</button>
          </div>
        </div>
        <div class="table-content">
          <table class="system-table">
            <thead>
              <tr>
                <th>链</th>
                <th>目标</th>
                <th>协议</th>
                <th>源地址</th>
                <th>目标地址</th>
                <th>选项</th>
              </tr>
            </thead>
            <tbody id="firewall-table-body">
              <tr>
                <td colspan="6" style="padding: var(--spacing-lg); text-align: center; color: var(--text-secondary);">
                  正在加载防火墙规则信息...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div id="firewall-pagination" class="table-pagination-container"></div>
      </div>
    `;
  }

  /**
   * 渲染加载状态
   */
  /**
   * 渲染加载状态
   */
  private renderLoadingState(): string {
    const steps = [
      '建立 TCP 连接到服务器...',
      '执行 SSH 握手协议...',
      '验证用户凭据...',
      '创建 SSH 通道...',
      '正在获取系统信息...'
    ];

    const stepsHtml = steps.map((step, index) => `
          <div class="loading-step-item" style="animation-delay: ${index * 0.8}s;">
            <div class="step-indicator">
              <div class="step-dot"></div>
              <div class="step-line"></div>
            </div>
            <span class="step-label">${step}</span>
          </div>
        `).join('');

    return `
      <div class="workspace-loading-overlay">
        <div class="loading-container">
          <div class="loading-visual-area">
            <div class="server-node local">
              <div class="node-icon">
                ${System({ theme: 'filled', size: '24', fill: 'currentColor' })}
              </div>
              <div class="node-pulse"></div>
            </div>
            
            <div class="connection-stream">
              <div class="stream-line"></div>
              <div class="stream-particles"></div>
            </div>

            <div class="server-node remote">
              <div class="node-icon">
                ${LinkCloud({ theme: 'filled', size: '24', fill: 'currentColor' })}
              </div>
              <div class="node-pulse"></div>
            </div>
          </div>

          <div class="loading-status-area">
            <h3 class="loading-main-text">正在建立安全连接</h3>
            <p class="loading-sub-text">安御智测 正在初始化远程环境</p>
            
            <div class="loading-steps-list">
              ${stepsHtml}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 渲染服务器管理模态框
   */
  renderServerModal(): string {
    return `
      <div id="server-modal" class="modal-overlay" style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(4px);
        display: none;
        align-items: center;
        justify-content: center;
        z-index: 1000;
        opacity: 0;
        transition: opacity 0.2s ease;
      ">
        <div class="modal-content modern-modal-content">
          <div class="modern-modal-header">
            <div class="header-left">
                <div class="header-icon-box">
                    ${LinkCloud({ theme: 'filled', size: '18', fill: 'currentColor' })}
                </div>
                <div class="header-title-group">
                    <h2>服务器管理</h2>
                </div>
            </div>
            <button class="close-modal-btn" onclick="window.hideServerModal()" title="关闭">
              ${CloseOne({ theme: 'outline', size: '18', fill: 'currentColor' })}
            </button>
          </div>

          <div class="modal-body modern-modal-body">
            <div id="server-list-container" class="server-list-container">
                <div class="manager-toolbar">
                  <div class="search-filter-area">
                    <div class="modern-search-input-wrapper">
                      <span class="search-icon">
                         <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                      </span>
                      <input type="text" placeholder="搜索服务器..." class="modern-search-input" oninput="window.filterServerList(this.value)">
                    </div>
                  </div>

                  <div class="toolbar-actions">
                      <button class="page-refresh-btn" onclick="window.refreshServerList()" title="刷新列表">
                        ${Refresh({ theme: 'outline', size: '16', fill: 'currentColor' })}
                        <span>刷新</span>
                      </button>
                      <button class="modern-btn primary compact" onclick="window.showAddServerForm()">
                        ${Plus({ theme: 'outline', size: '14', fill: 'currentColor' })}
                        <span>添加服务器</span>
                      </button>
                  </div>
                </div>

                <div id="server-list" class="server-grid-modern">
                  ${this.renderServerList()}
                </div>
            </div>

            <div id="add-server-form" class="add-server-form" style="display: none; padding: var(--spacing-xl);">
              ${this.renderAddServerForm()}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 渲染 Skills 管理模态框
   */
  renderSkillsModal(): string {
    return `
      <div id="skills-modal" class="modal-overlay" style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(4px);
        display: none;
        align-items: center;
        justify-content: center;
        z-index: 1000;
        opacity: 0;
        transition: opacity 0.2s ease;
      ">
        <div class="modal-content modern-modal-content" style="max-width: 640px; width: 90vw; max-height: 80vh; display: flex; flex-direction: column;">
          <div class="modern-modal-header">
            <div class="header-left">
                <div class="header-icon-box">
                    ${Rocket({ theme: 'filled', size: '18', fill: 'currentColor' })}
                </div>
                <div class="header-title-group">
                    <h2>Skills 管理</h2>
                </div>
            </div>
            <button class="close-modal-btn" onclick="window.hideSkillsModal()" title="关闭">
              ${CloseOne({ theme: 'outline', size: '18', fill: 'currentColor' })}
            </button>
          </div>

          <div style="padding: 12px 20px; display: flex; gap: 10px; border-bottom: 1px solid var(--border-color-light);">
            <button class="modern-btn danger" style="font-size: 12px; padding: 6px 12px;" onclick="window.deleteSelectedSkills()">删除</button>
            <button class="modern-btn primary" style="font-size: 12px; padding: 6px 12px;" onclick="window.addSkillPrompt()">增加</button>
          </div>

          <div class="modal-body modern-modal-body" style="overflow-y: auto; flex: 1;">
            <div id="skills-list-container" style="padding: 12px 0;">
              <div style="text-align: center; color: var(--text-secondary); padding: 40px;">加载中...</div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 渲染本地知识库管理模态框
   */
  renderKnowledgeBaseModal(): string {
    return `
      <div id="knowledge-base-modal" class="modal-overlay" style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(4px);
        display: none;
        align-items: center;
        justify-content: center;
        z-index: 1000;
        opacity: 0;
        transition: opacity 0.2s ease;
      ">
        <div class="modal-content modern-modal-content" style="max-width: 640px; width: 90vw; max-height: 80vh; display: flex; flex-direction: column;">
          <div class="modern-modal-header">
            <div class="header-left">
                <div class="header-icon-box">
                    ${BookOpen({ theme: 'filled', size: '18', fill: 'currentColor' })}
                </div>
                <div class="header-title-group">
                    <h2>本地知识库管理</h2>
                </div>
            </div>
            <button class="close-modal-btn" onclick="window.hideKnowledgeBaseModal()" title="关闭">
              ${CloseOne({ theme: 'outline', size: '18', fill: 'currentColor' })}
            </button>
          </div>

          <div style="padding: 12px 20px; display: flex; gap: 10px; border-bottom: 1px solid var(--border-color-light);">
            <button class="modern-btn danger" style="font-size: 12px; padding: 6px 12px;" onclick="window.deleteSelectedKnowledgeBase()">删除</button>
            <button class="modern-btn primary" style="font-size: 12px; padding: 6px 12px;" onclick="window.addKnowledgeBasePrompt()">增加</button>
          </div>

          <div class="modal-body modern-modal-body" style="overflow-y: auto; flex: 1;">
            <div id="knowledge-base-list-container" style="padding: 12px 0;">
              <div style="text-align: center; color: var(--text-secondary); padding: 40px;">加载中...</div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 渲染服务器列表
   */
  private renderServerList(): string {
    // 从SSH管理器获取真实的服务器数据
    const sshManager = (window as any).app?.sshManager;
    const servers = sshManager ? sshManager.getConnections().map((conn: any) => ({
      id: conn.id,
      name: conn.name,
      host: conn.host,
      port: conn.port,
      username: conn.username,
      authType: conn.authType,
      status: conn.isConnected ? 'connected' : 'disconnected',
      accounts: conn.accounts || [],
      accountCount: conn.accounts ? conn.accounts.length : 0
    })) : [];

    if (servers.length === 0) {
      return `
        <div class="empty-state" style="
          grid-column: 1 / -1;
          text-align: center;
          padding: 60px 20px;
          color: var(--text-secondary);
          background: var(--bg-tertiary);
          border-radius: var(--border-radius-lg);
          border: 1px dashed var(--border-color);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
        ">
          <div style="
            width: 64px;
            height: 64px;
            border-radius: 50%;
            background: var(--bg-secondary);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: var(--spacing-md);
            color: var(--text-tertiary);
          ">
             ${LinkCloud({ theme: 'filled', size: '32', fill: 'currentColor' })}
          </div>
          <p style="margin: 0 0 8px 0; font-weight: 600; color: var(--text-primary); font-size: 14px;">暂无服务器配置</p>
          <p style="font-size: 12px; margin: 0; max-width: 200px; line-height: 1.5;">
            点击右上角 "添加服务器" 按钮，配置您的第一个 Linux 服务器连接
          </p>
        </div>
      `;
    }

    return servers.map((server: any) => `
      <div class="server-card ${server.status}" style="
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius-lg);
        padding: var(--spacing-md);
        transition: all 0.2s;
        position: relative;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        gap: 12px;
      " onmouseover="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='var(--shadow-md)'; this.style.transform='translateY(-2px)';" 
         onmouseout="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none'; this.style.transform='translateY(0)';">
        
        ${server.status === 'connected' ? `
            <div style="
                position: absolute; 
                top: 0; 
                right: 0; 
                padding: 4px 10px; 
                background: rgba(34, 197, 94, 0.1); 
                color: var(--success-color); 
                font-size: 10px; 
                border-bottom-left-radius: 10px; 
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 4px;
            ">
                <span style="width: 6px; height: 6px; background: currentColor; border-radius: 50%; display: inline-block;"></span>
                已连接
            </div>
        ` : ''}

        <div style="display: flex; align-items: flex-start; gap: 12px;">
            <div style="
                width: 42px;
                height: 42px;
                border-radius: 10px;
                background: ${server.status === 'connected' ? 'rgba(34, 197, 94, 0.1)' : 'var(--bg-tertiary)'};
                color: ${server.status === 'connected' ? 'var(--success-color)' : 'var(--text-tertiary)'};
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                transition: all 0.3s;
            ">
                 ${server.status === 'connected' 
                    ? LinkInterrupt({ theme: 'filled', size: '22', fill: 'currentColor' }) 
                    : System({ theme: 'filled', size: '22', fill: 'currentColor' })}
            </div>
            <div style="flex: 1; min-width: 0; padding-right: 60px;">
                <div style="font-weight: 600; color: var(--text-primary); font-size: 14px; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${server.name}">
                    ${server.name}
                </div>
                <div style="font-size: 12px; color: var(--text-secondary); font-family: monospace; display: flex; align-items: center; gap: 6px;">
                    <span style="opacity: 0.8;">${server.username}@${server.host}:${server.port}</span>
                </div>
            </div>
        </div>

        <div style="
            display: flex; 
            align-items: center; 
            gap: 8px; 
            padding-top: 12px; 
            border-top: 1px solid var(--border-color-light);
            margin-top: auto;
        ">
            <div style="flex: 1; display: flex; gap: 6px; align-items: center;">
                <span style="
                    padding: 2px 8px;
                    background: var(--bg-tertiary);
                    color: var(--text-secondary);
                    border-radius: 4px;
                    font-size: 10px;
                    border: 1px solid var(--border-color);
                    display: flex;
                    align-items: center;
                    gap: 4px;
                ">
                    ${server.authType === 'password' ? Key({ theme: 'outline', size: '10', fill: 'currentColor' }) : Shield({ theme: 'outline', size: '10', fill: 'currentColor' })}
                    ${server.authType === 'password' ? '密码' : '密钥'}
                </span>
                ${server.accountCount > 0 ? `
                <span style="
                    padding: 2px 8px;
                    background: rgba(168, 85, 247, 0.1);
                    color: rgb(168, 85, 247);
                    border-radius: 4px;
                    font-size: 10px;
                    border: 1px solid rgba(168, 85, 247, 0.2);
                    display: flex;
                    align-items: center;
                    gap: 4px;
                ">
                    ${Peoples({ theme: 'outline', size: '10', fill: 'currentColor' })}
                    ${server.accountCount}
                </span>
                ` : ''}
            </div>

            <div style="display: flex; gap: 6px;">
                <button class="modern-btn ${server.status === 'connected' ? 'danger' : 'primary'}" style="
                    padding: 4px 12px; 
                    font-size: 11px; 
                    height: 28px;
                    border-radius: 6px;
                " onclick="window.${server.status === 'connected' ? 'disconnectServer' : 'connectServer'}('${server.id}')">
                    ${server.status === 'connected' ? '断开' : '连接'}
                </button>
                
                <button class="modern-btn secondary icon-only" style="
                    width: 28px; 
                    height: 28px; 
                    padding: 0; 
                    border-radius: 6px;
                    background: var(--bg-tertiary);
                " onclick="window.editServer('${server.id}')" title="编辑配置">
                    ${SettingConfig({ theme: 'outline', size: '14', fill: 'currentColor' })}
                </button>
                
                <button class="modern-btn secondary icon-only" style="
                    width: 28px; 
                    height: 28px; 
                    padding: 0; 
                    color: var(--error-color);
                    border-radius: 6px;
                    background: rgba(239, 68, 68, 0.1);
                    border-color: transparent;
                " onclick="window.deleteServer('${server.id}')" title="删除服务器"
                  onmouseover="this.style.background='var(--error-color)'; this.style.color='white';"
                  onmouseout="this.style.background='rgba(239, 68, 68, 0.1)'; this.style.color='var(--error-color)';">
                    ${CloseOne({ theme: 'outline', size: '14', fill: 'currentColor' })}
                </button>
            </div>
        </div>
      </div>
    `).join('');
  }

  /**
   * 渲染添加服务器表单
   */
  private renderAddServerForm(): string {
    return `
      <div class="form-container" style="
        background: var(--bg-secondary);
        border-radius: var(--border-radius-lg);
      ">
        <style>
        .auth-radio-label {
          flex: 1;
          cursor: pointer;
          text-align: center;
          padding: 8px;
          border-radius: 4px;
          font-size: 12px;
          font-weight: 500;
          transition: all 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          color: var(--text-secondary);
          border: 1px solid transparent;
        }
        .auth-radio-input:checked + .auth-radio-label {
          background: var(--bg-primary);
          color: var(--primary-color);
          box-shadow: var(--shadow-sm);
          border-color: var(--border-color);
        }
        </style>
        <div class="form-header" style="
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: var(--spacing-xl);
          padding-bottom: var(--spacing-md);
          border-bottom: 1px dashed var(--border-color);
        ">
          <div>
            <h3 style="margin: 0; color: var(--text-primary); font-size: 18px; font-weight: 600;">
              添加新服务器
            </h3>
            <p style="margin: 4px 0 0; font-size: 12px; color: var(--text-secondary);">配置远程 Linux 服务器的连接信息</p>
          </div>
          <button class="cancel-add-btn" style="
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 6px 12px;
            border-radius: var(--border-radius);
            transition: all 0.2s;
          " onclick="window.hideAddServerForm()" onmouseover="this.style.background='var(--bg-tertiary)'; this.style.color='var(--text-primary)'" onmouseout="this.style.background='transparent'; this.style.color='var(--text-secondary)'">
            ${CloseOne({ theme: 'outline', size: '14', fill: 'currentColor' })} 取消
          </button>
        </div>

        <form id="add-server-form-element" class="server-form" onsubmit="event.preventDefault(); window.handleServerFormSubmit(event)">
          
          <!-- 基础信息 -->
          <div style="margin-bottom: var(--spacing-xl);">
            <h4 style="font-size: 12px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: var(--spacing-md); font-weight: 600;">基础信息</h4>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-lg); margin-bottom: var(--spacing-md);">
                <div class="form-group">
                  <label style="display: block; font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;">服务器名称</label>
                  <div style="position: relative;">
                    <input type="text" name="name" placeholder="例如：生产服务器" style="
                      width: 100%;
                      padding: 10px 12px 10px 36px;
                      border: 1px solid var(--border-color);
                      border-radius: var(--border-radius);
                      background: var(--bg-primary);
                      color: var(--text-primary);
                      font-size: 13px;
                      transition: all 0.2s;
                    " required onfocus="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='0 0 0 2px var(--primary-color-alpha-10)'" onblur="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none'">
                    <div style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-tertiary);">
                        ${LinkCloud({ theme: 'outline', size: '14', fill: 'currentColor' })}
                    </div>
                  </div>
                </div>
                
                <div class="form-group">
                  <label style="display: block; font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;">主机地址 (IP/域名)</label>
                  <div style="position: relative;">
                    <input type="text" name="host" placeholder="192.168.1.100" style="
                      width: 100%;
                      padding: 10px 12px 10px 36px;
                      border: 1px solid var(--border-color);
                      border-radius: var(--border-radius);
                      background: var(--bg-primary);
                      color: var(--text-primary);
                      font-size: 13px;
                      transition: all 0.2s;
                    " required onfocus="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='0 0 0 2px var(--primary-color-alpha-10)'" onblur="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none'">
                     <div style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-tertiary);">
                        ${Earth({ theme: 'outline', size: '14', fill: 'currentColor' })}
                    </div>
                  </div>
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 120px 1fr; gap: var(--spacing-lg);">
                <div class="form-group">
                  <label style="display: block; font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;">SSH 端口</label>
                  <div style="position: relative;">
                    <input type="number" name="port" value="22" style="
                      width: 100%;
                      padding: 10px 12px 10px 36px;
                      border: 1px solid var(--border-color);
                      border-radius: var(--border-radius);
                      background: var(--bg-primary);
                      color: var(--text-primary);
                      font-size: 13px;
                      transition: all 0.2s;
                    " required onfocus="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='0 0 0 2px var(--primary-color-alpha-10)'" onblur="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none'">
                    <div style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-tertiary);">
                        ${NetworkTree({ theme: 'outline', size: '14', fill: 'currentColor' })}
                    </div>
                  </div>
                </div>
                <div class="form-group">
                  <label style="display: block; font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;">用户名</label>
                  <div style="position: relative;">
                    <input type="text" name="username" placeholder="root" style="
                      width: 100%;
                      padding: 10px 12px 10px 36px;
                      border: 1px solid var(--border-color);
                      border-radius: var(--border-radius);
                      background: var(--bg-primary);
                      color: var(--text-primary);
                      font-size: 13px;
                      transition: all 0.2s;
                    " required onfocus="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='0 0 0 2px var(--primary-color-alpha-10)'" onblur="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none'">
                    <div style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-tertiary);">
                        ${User({ theme: 'outline', size: '14', fill: 'currentColor' })}
                    </div>
                  </div>
                </div>
            </div>
          </div>

          <!-- 认证信息 -->
          <div style="margin-bottom: var(--spacing-xl);">
            <h4 style="font-size: 12px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: var(--spacing-md); font-weight: 600;">认证方式</h4>
            
            <div class="form-group" style="margin-bottom: var(--spacing-md);">
                <div style="
                    display: flex; 
                    background: var(--bg-tertiary); 
                    padding: 4px; 
                    border-radius: var(--border-radius); 
                    border: 1px solid var(--border-color);
                    gap: 4px;
                ">
                    <input type="radio" id="auth-type-password" name="authType" value="password" checked class="auth-radio-input" style="display: none;" onchange="window.toggleAuthFields(this.value)">
                    <label for="auth-type-password" class="auth-radio-label">
                        ${Key({ theme: 'outline', size: '14', fill: 'currentColor' })} 密码认证
                    </label>
                    
                    <input type="radio" id="auth-type-key" name="authType" value="key" class="auth-radio-input" style="display: none;" onchange="window.toggleAuthFields(this.value)">
                    <label for="auth-type-key" class="auth-radio-label">
                        ${Shield({ theme: 'outline', size: '14', fill: 'currentColor' })} SSH 密钥
                    </label>
                </div>
            </div>

            <div id="password-auth" class="auth-fields" style="animation: fadeIn 0.3s ease;">
              <div class="form-group">
                <label style="display: block; font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;">服务器密码</label>
                <div style="position: relative;">
                    <input type="password" name="password" placeholder="请输入服务器密码" style="
                      width: 100%;
                      padding: 10px 12px 10px 36px;
                      border: 1px solid var(--border-color);
                      border-radius: var(--border-radius);
                      background: var(--bg-primary);
                      color: var(--text-primary);
                      font-size: 13px;
                      transition: all 0.2s;
                    " onfocus="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='0 0 0 2px var(--primary-color-alpha-10)'" onblur="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none'">
                    <div style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-tertiary);">
                        ${Lock({ theme: 'outline', size: '14', fill: 'currentColor' })}
                    </div>
                </div>
              </div>
            </div>

            <div id="key-auth" class="auth-fields" style="display: none; animation: fadeIn 0.3s ease;">
              <div class="form-group" style="margin-bottom: var(--spacing-md);">
                <label style="display: block; font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;">私钥文件路径</label>
                <div style="display: flex; gap: 8px;">
                    <div style="position: relative; flex: 1;">
                        <input type="text" name="keyPath" placeholder="/Users/username/.ssh/id_rsa" style="
                          width: 100%;
                          padding: 10px 12px 10px 36px;
                          border: 1px solid var(--border-color);
                          border-radius: var(--border-radius);
                          background: var(--bg-primary);
                          color: var(--text-primary);
                          font-size: 13px;
                          transition: all 0.2s;
                        " onfocus="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='0 0 0 2px var(--primary-color-alpha-10)'" onblur="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none'">
                        <div style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-tertiary);">
                            ${FileText({ theme: 'outline', size: '14', fill: 'currentColor' })}
                        </div>
                    </div>
                    <button type="button" class="modern-btn secondary" style="padding: 0 12px;" onclick="window.selectPrivateKeyFile()" title="选择文件">
                        ${FolderOpen({ theme: 'outline', size: '16', fill: 'currentColor' })}
                    </button>
                </div>
              </div>
              <div class="form-group">
                <label style="display: block; font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;">密钥密码 (可选)</label>
                <div style="position: relative;">
                    <input type="password" name="keyPassphrase" placeholder="如果私钥设置了密码" style="
                      width: 100%;
                      padding: 10px 12px 10px 36px;
                      border: 1px solid var(--border-color);
                      border-radius: var(--border-radius);
                      background: var(--bg-primary);
                      color: var(--text-primary);
                      font-size: 13px;
                      transition: all 0.2s;
                    " onfocus="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='0 0 0 2px var(--primary-color-alpha-10)'" onblur="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none'">
                    <div style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-tertiary);">
                        ${Lock({ theme: 'outline', size: '14', fill: 'currentColor' })}
                    </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 多账号管理区域 -->
          <div class="form-group" style="
            margin-bottom: var(--spacing-md); 
            margin-top: var(--spacing-lg); 
            padding: var(--spacing-md); 
            border: 1px dashed var(--border-color);
            border-radius: var(--border-radius);
            background: var(--bg-tertiary);
          ">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--spacing-sm);">
              <div style="display: flex; align-items: center; gap: 8px;">
                  ${Peoples({ theme: 'filled', size: '16', fill: 'var(--primary-color)' })}
                  <label style="
                    font-size: 13px;
                    font-weight: 600;
                    color: var(--text-primary);
                    margin: 0;
                  ">多账号管理</label>
              </div>
              <button type="button" class="add-account-btn modern-btn secondary" style="
                padding: 4px 10px;
                font-size: 11px;
                height: 24px;
              " onclick="window.addServerAccount()">
                ${Plus({ theme: 'outline', size: '12', fill: 'currentColor' })} 添加账号
              </button>
            </div>
            <div style="
              font-size: 11px;
              color: var(--text-secondary);
              margin-bottom: var(--spacing-md);
              line-height: 1.4;
            ">
              您可以为同一台服务器添加多个登录账号（例如 root、superuser 等），连接时可快速切换。
            </div>
            <div id="additional-accounts-list" style="
              display: flex;
              flex-direction: column;
              gap: var(--spacing-md);
            ">
              <!-- 额外账号列表将动态插入这里 -->
            </div>
          </div>

          <div class="form-actions" style="
            display: flex;
            gap: var(--spacing-md);
            justify-content: space-between;
            margin-top: var(--spacing-xl);
            padding-top: var(--spacing-lg);
            border-top: 1px solid var(--border-color);
          ">
            <button type="button" id="test-connection-btn" class="modern-btn secondary" style="
              padding: 10px 20px;
              font-size: 13px;
              justify-content: center;
            " onclick="window.testConnection()">
              测试连接
            </button>
            <div style="display: flex; gap: var(--spacing-md);">
              <button type="button" class="cancel-btn modern-btn secondary" style="
                padding: 10px 20px;
                font-size: 13px;
                width: 100px;
                justify-content: center;
              " onclick="window.hideAddServerForm()">
                取消
              </button>
              <button type="submit" class="save-btn modern-btn primary" style="
                padding: 10px 24px;
                font-size: 13px;
                width: 120px;
                justify-content: center;
                box-shadow: 0 4px 12px var(--primary-color-alpha-30);
              ">
                保存配置
              </button>
            </div>
          </div>
        </form>
      </div>
    `;
  }

  /**
   * 渲染连接提示
   */
  private renderConnectionPrompt(): string {
    return `
      <div class="connection-prompt">
        <div class="connection-prompt-bg"></div>
        <div class="connection-prompt-card glass-effect hover-lift">
          <div class="prompt-badge">
            <img src="/logo.png" alt="SDIT Logo" style="width: 100%; height: 100%; object-fit: contain;" />
          </div>
          
          <div class="prompt-header-content">
            <h2 class="prompt-title">Welcome to <span class="luxe-text">安御智测</span></h2>
          </div>

          <div class="prompt-actions-container">
            <button class="modern-btn primary large pulse-effect" onclick="window.showServerModal()" style="width: 100%; justify-content: center; padding: 12px;">
              <span style="margin-right: 8px;">${Plus({ theme: 'outline', size: '18', fill: 'currentColor' })}</span>
              连接服务器
            </button>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 渲染仪表板
   */
  private renderDashboard(): string {
    return renderDashboardPage({
      dashboardRenderer: this.dashboardRenderer,
      systemInfo: this.getSystemInfo(),
      theme: this.state.theme
    });
  }

  /**
   * 获取系统信息
   */
  private getSystemInfo() {
    // 从状态管理器获取SSH管理器的系统信息
    const systemInfo = (window as any).app?.sshManager?.getSystemInfo();

    // 如果有缓存的详细信息，将其合并到系统信息中
    const cache = (window as any).systemInfoCache;
    if (systemInfo && cache?.detailedInfo) {
      systemInfo.detailedInfo = cache.detailedInfo;
    }

    setTimeout(() => {
      if ((window as any).dashboardRendererInstance) {
        (window as any).dashboardRendererInstance.initCharts(false);
      }
    }, 100);

    return systemInfo;
  }



  /**
   * 渲染远程操作页面（SFTP + SSH终端分屏）
   */
  private static remoteOperationsInitTimer: number | null = null;

  private renderRemoteOperationsPage(): string {
    return renderRemoteOperationsPage({
      isConnected: this.state.isConnected,
      fileListHtml: sftpManager.renderFileListHTML(),
      contextMenuHtml: this.sftpContextMenuRenderer.renderContextMenu(),
      scheduleInit: () => {
        if (ModernUIRenderer.remoteOperationsInitTimer) {
          clearTimeout(ModernUIRenderer.remoteOperationsInitTimer);
        }
        ModernUIRenderer.remoteOperationsInitTimer = window.setTimeout(() => {
          (window as any).initRemoteOperationsPage?.();
          ModernUIRenderer.remoteOperationsInitTimer = null;
        }, 100);
      }
    });
  }



  /**
   * 渲染应急命令页面
   */
  private renderEmergencyCommandsPage(): string {
    const sshManager = (window as any).app?.sshManager;
    const sshConnectionManager = (window as any).sshConnectionManager;
    const currentConnectionId = sshConnectionManager?.getCurrentConnectionId?.();
    let accountsOptions = '<option value="">默认账号</option>';

    if (currentConnectionId && sshManager) {
      const connection = sshManager.getConnection(currentConnectionId);
      if (connection && connection.accounts && connection.accounts.length > 0) {
        connection.accounts.forEach((account: any) => {
          const label = account.description
            ? `${account.username} (${account.description})`
            : account.username;
          accountsOptions += `<option value="${account.username}">${label}</option>`;
        });
      }
    }

    return renderEmergencyCommandsPage({
      accountsOptionsHtml: accountsOptions
    });
  }

  /**
   * 渲染快速检测页面
   */
  private renderQuickDetectionPage(): string {
    return renderQuickDetectionPage();
  }

  /**
   * 渲染快速检测报告模态框
   */
  renderDetectionReportModal(): string {
    return `
      <div id="detection-report-modal" class="modal" style="display: none;">
        <div class="modal-overlay" onclick="window.quickDetection?.closeReportModal()"></div>
        <div class="modal-content" style="
          max-width: 1000px;
          max-height: 90vh;
          overflow-y: auto;
          background: var(--bg-primary);
          border-radius: var(--border-radius-lg);
          padding: var(--spacing-lg);
        ">
          <!-- 报告头部 -->
          <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: var(--spacing-lg);
            padding-bottom: var(--spacing-md);
            border-bottom: 1px solid var(--border-color);
          ">
            <div>
              <h2 style="margin: 0; font-size: 24px; color: var(--text-primary); font-weight: 600;">检测报告</h2>
              <p id="report-timestamp" style="margin: 4px 0 0 0; font-size: 14px; color: var(--text-secondary);"></p>
            </div>
            <button onclick="window.quickDetection?.closeReportModal()" style="
              background: transparent;
              border: none;
              font-size: 24px;
              color: var(--text-secondary);
              cursor: pointer;
              padding: 4px 8px;
            ">×</button>
          </div>

          <!-- 评分卡片 -->
          <div style="
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: var(--spacing-lg);
            margin-bottom: var(--spacing-lg);
          ">
            <!-- 总体评分 -->
            <div class="modern-card" style="
              border: 1px solid var(--border-color);
              border-radius: var(--border-radius-lg);
              padding: var(--spacing-lg);
              text-align: center;
              background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(147, 51, 234, 0.1) 100%);
            ">
              <div style="font-size: 14px; color: var(--text-secondary); margin-bottom: 8px;">安全评分</div>
              <div style="display: flex; align-items: baseline; justify-content: center; gap: 4px;">
                <span id="report-overall-score" style="font-size: 64px; font-weight: 700; color: var(--primary-color);">--</span>
                <span style="font-size: 32px; color: var(--text-secondary);">/100</span>
              </div>
              <div id="report-score-label" style="
                margin-top: 8px;
                font-size: 16px;
                font-weight: 600;
                color: var(--primary-color);
              ">优秀</div>
            </div>

            <!-- 问题统计 -->
            <div class="modern-card" style="
              border: 1px solid var(--border-color);
              border-radius: var(--border-radius-lg);
              padding: var(--spacing-lg);
              background: var(--bg-primary);
            ">
              <div style="font-size: 16px; color: var(--text-primary); margin-bottom: var(--spacing-md); font-weight: 600;">问题统计</div>
              <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-sm);">
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-secondary); border-radius: var(--border-radius);">
                  <div style="width: 8px; height: 8px; border-radius: 50%; background: #ef4444;"></div>
                  <div style="flex: 1;">
                    <div style="font-size: 12px; color: var(--text-secondary);">严重</div>
                    <div id="report-critical-count" style="font-size: 24px; font-weight: 600; color: #ef4444;">0</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-secondary); border-radius: var(--border-radius);">
                  <div style="width: 8px; height: 8px; border-radius: 50%; background: #f59e0b;"></div>
                  <div style="flex: 1;">
                    <div style="font-size: 12px; color: var(--text-secondary);">高危</div>
                    <div id="report-high-count" style="font-size: 24px; font-weight: 600; color: #f59e0b;">0</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-secondary); border-radius: var(--border-radius);">
                  <div style="width: 8px; height: 8px; border-radius: 50%; background: #eab308;"></div>
                  <div style="flex: 1;">
                    <div style="font-size: 12px; color: var(--text-secondary);">中危</div>
                    <div id="report-medium-count" style="font-size: 24px; font-weight: 600; color: #eab308;">0</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-secondary); border-radius: var(--border-radius);">
                  <div style="width: 8px; height: 8px; border-radius: 50%; background: #3b82f6;"></div>
                  <div style="flex: 1;">
                    <div style="font-size: 12px; color: var(--text-secondary);">低危</div>
                    <div id="report-low-count" style="font-size: 24px; font-weight: 600; color: #3b82f6;">0</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 检测项目详情 -->
          <div id="report-details-container" style="margin-bottom: var(--spacing-lg);">
            <!-- 将由 JavaScript 动态填充 -->
          </div>

          <!-- 底部操作按钮 -->
          <div style="
            display: flex;
            justify-content: flex-end;
            gap: var(--spacing-sm);
            padding-top: var(--spacing-md);
            border-top: 1px solid var(--border-color);
          ">
            <button class="modern-btn secondary" onclick="window.quickDetection?.exportReport()">
              导出报告
            </button>
            <button class="modern-btn primary" onclick="window.quickDetection?.closeReportModal()">
              关闭
            </button>
          </div>
        </div>
      </div>
    `;
  }


  /**
   * 渲染状态栏
   */
  renderStatusBar(): string {
    const connectedIcon = CheckOne({ theme: 'filled', size: '12', fill: '#22c55e' });
    const disconnectedIcon = CloseOne({ theme: 'filled', size: '12', fill: '#ef4444' });

    return `
      <div class="status-bar">
        <div class="status-left">
          ${this.state.isConnected ? `<span style="margin-left: var(--spacing-md); display: flex; align-items: center; gap: 4px;">${connectedIcon} 已连接</span>` : `<span style="margin-left: var(--spacing-md); display: flex; align-items: center; gap: 4px;">${disconnectedIcon} 未连接</span>`}
        </div>

        <div class="status-right">
          <span>LERT v0.60</span>
        </div>
      </div>
    `;
  }

  /**
   * 渲染 SSH 终端重定向页面
   */
  private renderSSHTerminalRedirect(): string {
    return `
      <div class="ssh-terminal-redirect" style="
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100%;
        text-align: center;
        padding: 2rem;
      ">
        <div style="
          background: var(--bg-secondary);
          border: 1px solid var(--border-color);
          border-radius: 8px;
          padding: 2rem;
          max-width: 500px;
          width: 100%;
        ">
          <div style="
            font-size: 48px;
            margin-bottom: 1rem;
            color: var(--text-secondary);
          ">🖥️</div>

          <h2 style="
            color: var(--text-primary);
            margin-bottom: 1rem;
            font-size: 1.5rem;
          ">SSH 终端已在新窗口中打开</h2>

          <p style="
            color: var(--text-secondary);
            margin-bottom: 1.5rem;
            line-height: 1.6;
          ">
            SSH 终端现在在独立窗口中运行，这样可以：<br>
            • 保持会话持久性<br>
            • 不影响主界面操作<br>
            • 提供更好的终端体验
          </p>

          <button
            onclick="openSSHTerminalWindow()"
            style="
              background: var(--primary-color);
              color: white;
              border: none;
              padding: 0.75rem 1.5rem;
              border-radius: 6px;
              cursor: pointer;
              font-size: 1rem;
              transition: all 0.2s;
            "
            onmouseover="this.style.opacity='0.9'"
            onmouseout="this.style.opacity='1'"
          >
            重新打开 SSH 终端
          </button>
        </div>
      </div>
    `;
  }



  /**
   * 渲染设置页面（覆盖层模式）
   */
  renderSettingsPage(): string {
    return `
      <div class="settings-overlay" style="
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        backdrop-filter: blur(4px);
      ">
        <div class="settings-page" style="
          width: min(92vw, 760px);
          max-height: 90vh;
          padding: var(--spacing-lg);
          background: var(--bg-primary);
          border-radius: var(--border-radius-lg);
          box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
          overflow-y: auto;
          position: relative;
        ">
          <button class="settings-close-btn" style="
            position: absolute;
            top: var(--spacing-md);
            right: var(--spacing-md);
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 20px;
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            transition: all 0.2s;
          " title="关闭 AI 配置">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>

          <div class="settings-header" style="
            margin-bottom: var(--spacing-xl);
            padding-bottom: var(--spacing-lg);
            border-bottom: 1px solid var(--border-color);
          ">
            <h1 style="
              font-size: 24px;
              font-weight: 600;
              color: var(--text-primary);
              margin: 0 0 var(--spacing-sm) 0;
            ">AI 配置</h1>
            <p style="
              color: var(--text-secondary);
              margin: 0;
              font-size: 14px;
            ">统一管理 AI 模型、API Key、Base URL 与代理连接</p>
          </div>

          <div class="settings-section" style="
            background: var(--bg-secondary);
            border-radius: var(--border-radius-lg);
            padding: var(--spacing-lg);
          ">
            <div class="setting-item" style="margin-bottom: var(--spacing-xl);">
              <div style="
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--spacing-sm);
                margin-bottom: 8px;
                flex-wrap: wrap;
              ">
                <label style="
                  font-size: 14px;
                  font-weight: 600;
                  color: var(--text-primary);
                  display: block;
                ">已配置模型</label>
                <span id="configured-models-count" style="
                  padding: 4px 10px;
                  border-radius: 999px;
                  background: var(--bg-primary);
                  border: 1px solid var(--border-color);
                  color: var(--text-secondary);
                  font-size: 12px;
                  font-weight: 600;
                ">0 个</span>
              </div>
              <p style="
                margin: 0 0 12px 0;
                color: var(--text-secondary);
                font-size: 13px;
                line-height: 1.6;
              ">这里会显示已保存的模型详情。点击“切换并编辑”可快速切到下方表单，调整后保存即可生效。</p>
              <div id="configured-models-list" style="
                display: grid;
                gap: 12px;
              "></div>
            </div>

            <div class="setting-item" style="margin-bottom: var(--spacing-lg);">
              <label style="
                font-size: 14px;
                font-weight: 500;
                color: var(--text-primary);
                display: block;
                margin-bottom: 8px;
              ">AI提供商</label>
              <div style="display: flex; gap: var(--spacing-sm); align-items: flex-end;">
                <div style="flex: 1; position: relative;">
                  <select id="ai-provider" style="
                    width: 100%;
                    padding: 10px 12px;
                    border: 1px solid var(--border-color);
                    border-radius: var(--border-radius);
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    font-size: 14px;
                    box-sizing: border-box;
                  ">
                    <option value="openai">OpenAI (GPT-4o/GPT-3.5)</option>
                    <option value="deepseek">DeepSeek (国产大模型)</option>
                    <option value="claude">Claude (Anthropic)</option>
                    <option value="qwen">Qwen (通义千问)</option>
                    <option value="ollama">Ollama (本地模型)</option>
                    <option value="custom">自定义 API</option>
                  </select>
                </div>
                <button id="delete-ai-provider" class="modern-btn danger" style="
                  padding: 10px 12px;
                  font-size: 13px;
                  white-space: nowrap;
                  display: none;
                  align-items: center;
                  gap: 6px;
                ">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                  </svg>
                  删除
                </button>
                <button id="add-ai-provider" class="modern-btn secondary" style="
                  padding: 10px 16px;
                  font-size: 13px;
                  white-space: nowrap;
                  display: flex;
                  align-items: center;
                  gap: 6px;
                ">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                  </svg>
                  新增
                </button>
              </div>
            </div>

            <div id="ai-provider-config">
              <div class="setting-item" style="margin-bottom: var(--spacing-md);">
                <label style="
                  font-size: 14px;
                  font-weight: 500;
                  color: var(--text-primary);
                  display: block;
                  margin-bottom: 8px;
                ">API Key</label>
                <input type="password" id="ai-api-key" placeholder="输入您的 AI API Key" style="
                  width: 100%;
                  padding: 10px 12px;
                  border: 1px solid var(--border-color);
                  border-radius: var(--border-radius);
                  background: var(--bg-primary);
                  color: var(--text-primary);
                  font-size: 14px;
                  box-sizing: border-box;
                ">
              </div>

              <div class="setting-item" style="margin-bottom: var(--spacing-md);">
                <label style="
                  font-size: 14px;
                  font-weight: 500;
                  color: var(--text-primary);
                  display: block;
                  margin-bottom: 8px;
                ">模型</label>
                <input type="text" id="ai-model" placeholder="例如: gpt-4o-mini" style="
                  width: 100%;
                  padding: 10px 12px;
                  border: 1px solid var(--border-color);
                  border-radius: var(--border-radius);
                  background: var(--bg-primary);
                  color: var(--text-primary);
                  font-size: 14px;
                  box-sizing: border-box;
                ">
              </div>

              <div class="setting-item" style="margin-bottom: var(--spacing-lg);">
                <label style="
                  font-size: 14px;
                  font-weight: 500;
                  color: var(--text-primary);
                  display: block;
                  margin-bottom: 8px;
                ">Base URL</label>
                <input type="url" id="ai-base-url" placeholder="例如: https://api.openai.com/v1" style="
                  width: 100%;
                  padding: 10px 12px;
                  border: 1px solid var(--border-color);
                  border-radius: var(--border-radius);
                  background: var(--bg-primary);
                  color: var(--text-primary);
                  font-size: 14px;
                  box-sizing: border-box;
                ">
              </div>

              <div class="setting-item" style="margin-bottom: var(--spacing-lg);">
                <label style="
                  display: flex;
                  align-items: center;
                  gap: 8px;
                  font-size: 14px;
                  font-weight: 500;
                  color: var(--text-primary);
                  margin-bottom: 12px;
                  cursor: pointer;
                ">
                  <input type="checkbox" id="ai-use-proxy" style="
                    width: 18px;
                    height: 18px;
                    cursor: pointer;
                  ">
                  使用代理
                </label>

                <div id="ai-proxy-settings" style="
                  display: none;
                  padding: 12px;
                  border: 1px solid var(--border-color);
                  border-radius: var(--border-radius);
                  background: var(--bg-primary);
                ">
                  <div style="margin-bottom: 12px;">
                    <label style="
                      font-size: 13px;
                      color: var(--text-secondary);
                      display: block;
                      margin-bottom: 6px;
                    ">代理类型</label>
                    <select id="ai-proxy-type" style="
                      width: 100%;
                      padding: 8px 10px;
                      border: 1px solid var(--border-color);
                      border-radius: var(--border-radius);
                      background: var(--bg-primary);
                      color: var(--text-primary);
                      font-size: 14px;
                      cursor: pointer;
                    ">
                      <option value="http">HTTP</option>
                      <option value="https">HTTPS</option>
                      <option value="socks5">SOCKS5</option>
                    </select>
                  </div>

                  <div>
                    <label style="
                      font-size: 13px;
                      color: var(--text-secondary);
                      display: block;
                      margin-bottom: 6px;
                    ">代理地址</label>
                    <input type="text" id="ai-proxy-url" placeholder="例如: 127.0.0.1:7890" style="
                      width: 100%;
                      padding: 8px 10px;
                      border: 1px solid var(--border-color);
                      border-radius: var(--border-radius);
                      background: var(--bg-primary);
                      color: var(--text-primary);
                      font-size: 14px;
                      box-sizing: border-box;
                    ">
                    <div style="
                      font-size: 12px;
                      color: var(--text-secondary);
                      margin-top: 4px;
                    ">格式: 主机:端口 或 协议://主机:端口</div>
                  </div>
                </div>
              </div>

              <div class="setting-item">
                <div style="
                  display: flex;
                  align-items: center;
                  gap: var(--spacing-md);
                  margin-bottom: var(--spacing-sm);
                  flex-wrap: wrap;
                ">
                  <button id="test-ai-connection" class="modern-btn secondary" style="
                    padding: 10px 18px;
                    font-size: 13px;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                  ">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                    </svg>
                    测试连接
                  </button>
                  <button id="save-settings" class="modern-btn primary" style="
                    padding: 10px 18px;
                    font-size: 13px;
                  ">保存配置</button>
                  <span id="ai-test-status" style="
                    font-size: 13px;
                    color: var(--text-secondary);
                  ">点击测试 AI 连接状态</span>
                </div>
                <div id="ai-test-result" style="
                  padding: 10px;
                  border-radius: var(--border-radius);
                  background: var(--bg-primary);
                  border: 1px solid var(--border-color);
                  font-size: 13px;
                  color: var(--text-secondary);
                  display: none;
                  max-height: 100px;
                  overflow-y: auto;
                "></div>
              </div>
            </div>
          </div>

          <div id="add-provider-modal" style="
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(4px);
            z-index: 10001;
            align-items: center;
            justify-content: center;
          ">
            <div style="
              background: var(--bg-primary);
              border-radius: var(--border-radius-lg);
              padding: var(--spacing-xl);
              width: 90%;
              max-width: 500px;
              box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
              border: 1px solid var(--border-color);
            ">
              <div style="
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--spacing-lg);
              ">
                <h3 style="
                  font-size: 18px;
                  font-weight: 600;
                  color: var(--text-primary);
                  margin: 0;
                ">新增AI提供商</h3>
                <button id="close-add-provider-modal" style="
                  background: none;
                  border: none;
                  color: var(--text-secondary);
                  cursor: pointer;
                  padding: 4px;
                  border-radius: var(--border-radius);
                  transition: all 0.2s;
                ">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                  </svg>
                </button>
              </div>

              <form id="add-provider-form">
                <div class="setting-item" style="margin-bottom: var(--spacing-md);">
                  <label style="
                    font-size: 14px;
                    font-weight: 500;
                    color: var(--text-primary);
                    display: block;
                    margin-bottom: 8px;
                  ">提供商名称 *</label>
                  <input type="text" id="new-provider-name" placeholder="例如: 我的Claude、公司AI等" required style="
                    width: 100%;
                    padding: 10px 12px;
                    border: 1px solid var(--border-color);
                    border-radius: var(--border-radius);
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    font-size: 14px;
                    box-sizing: border-box;
                  ">
                </div>

                <div class="setting-item" style="margin-bottom: var(--spacing-md);">
                  <label style="
                    font-size: 14px;
                    font-weight: 500;
                    color: var(--text-primary);
                    display: block;
                    margin-bottom: 8px;
                  ">API Key</label>
                  <input type="password" id="new-provider-api-key" placeholder="输入 API Key" style="
                    width: 100%;
                    padding: 10px 12px;
                    border: 1px solid var(--border-color);
                    border-radius: var(--border-radius);
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    font-size: 14px;
                    box-sizing: border-box;
                  ">
                </div>

                <div class="setting-item" style="margin-bottom: var(--spacing-md);">
                  <label style="
                    font-size: 14px;
                    font-weight: 500;
                    color: var(--text-primary);
                    display: block;
                    margin-bottom: 8px;
                  ">模型</label>
                  <input type="text" id="new-provider-model" placeholder="例如: gpt-4、claude-3等" style="
                    width: 100%;
                    padding: 10px 12px;
                    border: 1px solid var(--border-color);
                    border-radius: var(--border-radius);
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    font-size: 14px;
                    box-sizing: border-box;
                  ">
                </div>

                <div class="setting-item" style="margin-bottom: var(--spacing-lg);">
                  <label style="
                    font-size: 14px;
                    font-weight: 500;
                    color: var(--text-primary);
                    display: block;
                    margin-bottom: 8px;
                  ">Base URL</label>
                  <input type="url" id="new-provider-base-url" placeholder="例如: https://api.anthropic.com/v1" style="
                    width: 100%;
                    padding: 10px 12px;
                    border: 1px solid var(--border-color);
                    border-radius: var(--border-radius);
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    font-size: 14px;
                    box-sizing: border-box;
                  ">
                </div>

                <div style="
                  display: flex;
                  gap: var(--spacing-md);
                  justify-content: flex-end;
                ">
                  <button type="button" id="cancel-add-provider" class="modern-btn secondary" style="
                    padding: 10px 20px;
                    font-size: 14px;
                  ">取消</button>
                  <button type="submit" id="save-new-provider" class="modern-btn primary" style="
                    padding: 10px 20px;
                    font-size: 14px;
                  ">保存</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 渲染全局模态框
   */
  renderGlobalModals(): string {
    return '';
  }

  /**
   * 渲染SSH终端标题栏按钮
   */
  renderSSHTerminalTitleButton(): string {
    return `
      <button id="ssh-terminal-title-btn" class="nav-item terminal-btn" data-tooltip="终端" title="打开SSH终端">
        <span class="nav-item-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <!-- 顶部窗口栏 -->
            <rect x="2" y="2" width="20" height="6" rx="1" fill="currentColor" opacity="0.9"/>
            <!-- 三个圆点 -->
            <circle cx="5" cy="5" r="1.5" fill="var(--bg-primary)"/>
            <circle cx="9" cy="5" r="1.5" fill="var(--bg-primary)"/>
            <circle cx="13" cy="5" r="1.5" fill="var(--bg-primary)"/>
            <!-- 终端主体 -->
            <rect x="2" y="9" width="20" height="13" rx="1" fill="currentColor" opacity="0.9"/>
            <!-- 命令行提示符 > -->
            <path d="M6 14L9 17.5L6 21" stroke="var(--bg-primary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <!-- 光标/下划线 -->
            <rect x="11" y="19" width="6" height="1.5" rx="0.75" fill="var(--bg-primary)"/>
          </svg>
        </span>
        <span class="nav-item-text">终端</span>
      </button>
    `;
  }

  /**
   * 渲染 Payloader 页面
   */
  private renderPayloaderPage(): string {
    return `
      <div id="payloader-vue-root" class="payloader-vue-root"></div>
    `;
  }
}
