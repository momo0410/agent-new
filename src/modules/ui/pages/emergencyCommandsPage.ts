import { emergencyCategories } from '../../emergency/commands';

export interface EmergencyCommandsPageContext {
  accountsOptionsHtml: string;
}

export function renderEmergencyCommandsPage(context: EmergencyCommandsPageContext): string {
  const renderCategory = (cat: any) => {
    const items = cat.items.map((item: any) => `
        <button class="em-cmd-btn" data-em-id="${item.id}" title="${item.desc || ''}">
          <div class="em-cmd-content">
            <span class="em-cmd-name">${item.name}</span>
            <span class="em-cmd-desc">${item.desc || '点击执行此命令'}</span>
          </div>
          <div class="em-cmd-icon">
            <svg width="20" height="20" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M14 12L26 24L14 36" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M26 36H42" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
        </button>
      `).join('');

    return `
    <div class="em-category-section">
      <div class="em-category-header">
        <h3 class="em-category-title">${cat.title}</h3>
        ${cat.hint ? `<div class="em-category-hint">${cat.hint}</div>` : ''}
      </div>
      <div class="em-grid">
        ${items}
      </div>
    </div>
  `;
  };

  const body = emergencyCategories.map(renderCategory).join('');

  return `
    <div class="emergency-commands-page" style="display:flex; flex-direction:column; gap: var(--spacing-lg); min-height: 100%;">
      <div class="em-header-container">
        <div class="em-system-card">
          <div class="em-system-icon">
            <img src="/icons/command-execute.png" alt="检测到的系统" />
          </div>
          <div class="em-system-info">
            <div class="em-system-label">检测到的系统</div>
            <div id="detected-system-info" class="em-system-value">检测中...</div>
          </div>
        </div>

        <div class="em-actions-card">
          <div class="em-search-wrapper">
             <svg width="16" height="16" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M21 38C30.3888 38 38 30.3888 38 21C38 11.6112 30.3888 4 21 4C11.6112 4 4 11.6112 4 21C4 30.3888 11.6112 38 21 38Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
                <path d="M33.2218 33.2218L41.7071 41.7071" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
             </svg>
             <input type="text" class="em-search-input" placeholder="搜索命令..." oninput="window.emergencyPageManager?.handleSearch(this.value)">
          </div>

          <div class="em-account-select-wrapper">
            <label style="font-size: 12px; color: var(--text-secondary); margin: 0;">执行账号:</label>
            <select id="emergency-account-select" class="em-account-select" title="选择执行应急命令的账号">
              ${context.accountsOptionsHtml}
            </select>
          </div>

          <button id="view-command-history-btn" class="modern-btn primary" style="height: 36px;" onclick="(window).commandHistoryModal?.show()">
            <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 8px;">
              <path d="M24 44C35.0457 44 44 35.0457 44 24C44 12.9543 35.0457 4 24 4C12.9543 4 4 12.9543 4 24C4 35.0457 12.9543 44 24 44Z" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
              <path d="M24 12V24L32 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>查看命令历史</span>
          </button>
        </div>
      </div>
      ${body}
    </div>
  `;
}
