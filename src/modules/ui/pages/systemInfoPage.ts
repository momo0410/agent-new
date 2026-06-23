import {
  Earth,
  Left,
  List,
  Right,
  Rocket,
  Shield,
  System,
  Time,
  User
} from '@icon-park/svg';

type SystemInfoTabId =
  | 'processes'
  | 'network'
  | 'services'
  | 'users'
  | 'autostart'
  | 'cron'
  | 'firewall';

export interface SystemInfoPageContext {
  counts: Record<SystemInfoTabId, number>;
  knownTabs: Set<string>;
  renderInitialTab: () => string;
}

export function renderSystemInfoPage(context: SystemInfoPageContext): string {
  const renderCountBadge = (key: SystemInfoTabId): string => {
    return context.counts[key] > 0 || context.knownTabs.has(key)
      ? `<span class="count-badge">${context.counts[key]}</span>`
      : '';
  };

  const isCollapsed = localStorage.getItem('system-info-header-collapsed') === 'true';
  const collapsedClass = isCollapsed ? 'collapsed' : '';
  const contentExpandedClass = isCollapsed ? 'expanded' : '';
  const toggleIcon = isCollapsed
    ? Right({ theme: 'outline', size: '16', fill: 'currentColor' })
    : Left({ theme: 'outline', size: '16', fill: 'currentColor' });

  return `
    <div class="system-info-container">
      <div class="system-info-sidebar-wrapper">
        <div class="system-info-header ${collapsedClass}">
          <div class="system-info-menu-title">
            <span>系统概览</span>
          </div>

          <div class="system-info-tabs">
            <button class="tab-btn active" data-tab="processes">
              <span class="tab-icon">${List({ theme: 'outline', size: '16', fill: 'currentColor' })}</span>
              <span class="tab-label">进程详情</span>
              ${renderCountBadge('processes')}
            </button>
            <button class="tab-btn" data-tab="network">
              <span class="tab-icon">${Earth({ theme: 'outline', size: '16', fill: 'currentColor' })}</span>
              <span class="tab-label">网络详情</span>
              ${renderCountBadge('network')}
            </button>
            <button class="tab-btn" data-tab="services">
              <span class="tab-icon">${System({ theme: 'outline', size: '16', fill: 'currentColor' })}</span>
              <span class="tab-label">系统服务</span>
              ${renderCountBadge('services')}
            </button>
            <button class="tab-btn" data-tab="users">
              <span class="tab-icon">${User({ theme: 'outline', size: '16', fill: 'currentColor' })}</span>
              <span class="tab-label">用户列表</span>
              ${renderCountBadge('users')}
            </button>
            <button class="tab-btn" data-tab="autostart">
              <span class="tab-icon">${Rocket({ theme: 'outline', size: '16', fill: 'currentColor' })}</span>
              <span class="tab-label">自启动</span>
              ${renderCountBadge('autostart')}
            </button>
            <button class="tab-btn" data-tab="cron">
              <span class="tab-icon">${Time({ theme: 'outline', size: '16', fill: 'currentColor' })}</span>
              <span class="tab-label">计划任务</span>
              ${renderCountBadge('cron')}
            </button>
            <button class="tab-btn" data-tab="firewall">
              <span class="tab-icon">${Shield({ theme: 'outline', size: '16', fill: 'currentColor' })}</span>
              <span class="tab-label">防火墙</span>
              ${renderCountBadge('firewall')}
            </button>
          </div>
        </div>
      </div>

      <div class="header-toggle-btn" onclick="window.toggleSystemInfoHeader()" title="切换菜单">
        <span class="header-toggle-icon">${toggleIcon}</span>
      </div>

      <div class="system-info-content ${contentExpandedClass}" id="system-info-content">
        ${context.renderInitialTab()}
      </div>
    </div>
  `;
}
