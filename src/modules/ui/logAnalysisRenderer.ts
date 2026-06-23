/**
 * 日志审计页面渲染器
 * 负责渲染日志审计界面和处理日志数据展示
 */

import {
  Log,
  FileText,
  Refresh,
  Search,
  Down,
  Calendar,
  Left,
  Right
} from '@icon-park/svg';

interface LogEntry {
  timestamp: string;
  level: string;
  service: string;
  message: string;
  raw: string;
  highlighted: boolean;
}

export class LogAnalysisRenderer {
  private currentLogPath: string = '/var/log/tuned/tuned.log';
  private currentLines: number = 100;
  private currentFilter: string = '';
  private useJournalctl: boolean = false;
  private journalUnit: string = '';
  
  private currentPage: number = 1;
  private currentDate: string = '';
  private multiSelectEnabled: boolean = false;
  private currentLevelFilter: string = '';

  /**
   * 渲染日志审计页面
   */
  render(): string {
    return `
      <div class="log-analysis-page">
        <div class="log-analysis-container">
          ${this.renderToolbar()}
          ${this.renderBatchActionBar()}
          ${this.renderLogContent()}
          ${this.renderPagination()}
        </div>
      </div>
    `;
  }

  /**
   * 渲染工具栏
   */
  private renderToolbar(): string {
    const today = new Date().toISOString().split('T')[0];
    
    return `
      <div class="log-toolbar">
        <div class="toolbar-left">
          <div class="toolbar-title">
            ${Log({ theme: 'outline', size: '20', fill: 'currentColor' })}
            <span class="text">日志审计</span>
          </div>
          <div class="toolbar-divider"></div>
          
          <div class="log-source-group">
            <button class="source-btn ${!this.useJournalctl ? 'active' : ''}" 
                    onclick="window.switchLogSource('file')"
                    title="查看文件日志">
              ${FileText({ theme: 'outline', size: '16', fill: 'currentColor' })}
              文件
            </button>
            <button class="source-btn ${this.useJournalctl ? 'active' : ''}" 
                    onclick="window.switchLogSource('journalctl')"
                    title="查看 Journalctl 日志">
              <svg width="16" height="16" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M14 41V7H34V41H14Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M14 15H34" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M14 23H34" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              Journal
            </button>
          </div>

          ${!this.useJournalctl ? this.renderFileSelector() : this.renderJournalInput()}

          <div class="toolbar-divider"></div>

          <div class="level-filter-wrapper">
            <select 
              class="toolbar-select level-select" 
              id="log-level-select"
              onchange="window.updateLogLevelFilter(this.value)"
            >
              <option value="" ${!this.currentLevelFilter ? 'selected' : ''}>全部级别</option>
              <option value="error" ${this.currentLevelFilter === 'error' ? 'selected' : ''}>ERROR</option>
              <option value="warning" ${this.currentLevelFilter === 'warning' ? 'selected' : ''}>WARNING</option>
              <option value="info" ${this.currentLevelFilter === 'info' ? 'selected' : ''}>INFO</option>
              <option value="debug" ${this.currentLevelFilter === 'debug' ? 'selected' : ''}>DEBUG</option>
            </select>
          </div>
        </div>

        <div class="toolbar-right">
          <button
            class="modern-btn log-multi-select-btn ${this.multiSelectEnabled ? 'active' : ''}"
            id="log-multi-select-btn"
            onclick="window.toggleLogMultiSelect()"
            title="多选模式 (Ctrl/Shift 快捷键)"
          >
            <svg width="14" height="14" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="6" y="6" width="36" height="36" rx="4" stroke="currentColor" stroke-width="4"/>
              <path d="M16 24L22 30L34 18" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            多选
          </button>

          <div class="date-picker-wrapper">
            ${Calendar({ theme: 'outline', size: '16', fill: 'currentColor' })}
            <input 
              type="date" 
              class="toolbar-input date-input" 
              id="log-date-input"
              value="${this.currentDate}"
              max="${today}"
              onchange="window.updateLogDate(this.value)"
              title="筛选日期"
            />
          </div>

          <div class="search-box">
            <input 
              type="text" 
              class="transparent-input" 
              id="log-filter-input"
              placeholder="搜索关键词..."
              value="${this.currentFilter}"
              onkeydown="if(event.key==='Enter')window.executeLogSearch()"
            />
            ${this.currentFilter ? `
              <button class="clear-btn" onclick="window.clearLogFilter()">
                ${Down({ theme: 'outline', size: '14', fill: 'currentColor', strokeWidth: 4 })}
              </button>
            ` : ''}
          </div>
          <button class="search-btn" onclick="window.executeLogSearch()" title="搜索">
            ${Search({ theme: 'outline', size: '16', fill: 'currentColor' })}
          </button>

          <button class="page-refresh-btn" onclick="window.refreshLogAnalysis()" title="刷新日志">
            ${Refresh({ theme: 'outline', size: '16', fill: 'currentColor' })}
            <span>刷新</span>
          </button>
        </div>
      </div>
    `;
  }

  /**
   * 渲染分页控件
   */
  private renderPagination(): string {
    return `
      <div class="log-pagination">
        <div class="pagination-info">
          <span class="text-secondary">每页显示:</span>
          <select 
            class="mini-select" 
            id="log-lines-select"
            value="${this.currentLines}"
            onchange="window.updateLogLines(this.value)"
          >
            <option value="50">50条</option>
            <option value="100" ${this.currentLines === 100 ? 'selected' : ''}>100条</option>
            <option value="200">200条</option>
            <option value="500">500条</option>
            <option value="1000">1000条</option>
          </select>
        </div>

        <div class="pagination-controls">
          <button class="pagination-btn" 
                  onclick="window.changeLogPage(-1)" 
                  ${this.currentPage <= 1 ? 'disabled' : ''}
                  title="上一页">
            ${Left({ theme: 'outline', size: '16', fill: 'currentColor' })}
          </button>
          
          <span class="page-display">第 ${this.currentPage} 页</span>
          
          <button class="pagination-btn" 
                  onclick="window.changeLogPage(1)"
                  title="下一页">
            ${Right({ theme: 'outline', size: '16', fill: 'currentColor' })}
          </button>
        </div>
      </div>
    `;
  }

  /**
   * 渲染批量操作栏
   */
  private renderBatchActionBar(): string {
    return `
      <div class="log-batch-action-bar" id="log-batch-action-bar" style="display: none;">
        <div class="batch-action-left">
          <span class="batch-select-count" id="batch-select-count">已选择 0 条</span>
          <button class="batch-action-link" onclick="window.selectAllLogEntries()">全选</button>
          <button class="batch-action-link" onclick="window.clearLogSelection()">取消选择</button>
        </div>
        <div class="batch-action-right">
          <button class="modern-btn batch-btn" onclick="window.copySelectedLogEntries()" title="复制选中日志">
            <svg width="14" height="14" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="16" y="16" width="24" height="24" rx="4" stroke="currentColor" stroke-width="4"/>
              <path d="M32 12V10C32 7.79 30.21 6 28 6H10C7.79 6 6 7.79 6 10V28C6 30.21 7.79 32 10 32H12" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
            </svg>
            复制
          </button>
          <button class="modern-btn batch-btn batch-ai-btn" onclick="window.analyzeSelectedLogEntries()" title="AI分析选中日志">
            AI分析选中
          </button>
        </div>
      </div>
    `;
  }

  /**
   * 渲染文件选择器
   */
  private renderFileSelector(): string {
    const options = [
      { value: '/var/log/auth.log', label: '认证日志 (auth.log)' },
      { value: '/var/log/secure', label: '安全日志 (secure)' },
      { value: '/var/log/syslog', label: '系统日志 (syslog)' },
      { value: '/var/log/messages', label: '系统消息 (messages)' },
      { value: '/var/log/kern.log', label: '内核日志 (kern.log)' },
      { value: '/var/log/cron', label: '计划任务日志 (cron)' },
      { value: '/var/log/audit/audit.log', label: '审计日志 (audit.log)' },
      { value: '/var/log/boot.log', label: '启动日志 (boot.log)' },
      { value: '/var/log/dmesg', label: '设备消息 (dmesg)' },
      { value: '/var/log/faillog', label: '失败登录 (faillog)' },
      { value: '/var/log/tuned/tuned.log', label: '调优日志 (tuned.log)' },
    ];

    return `
      <div class="selector-wrapper">
        <select 
          class="toolbar-select" 
          id="log-file-select"
          onchange="window.updateLogPath(this.value)"
        >
          <optgroup label="系统日志">
            ${options.map(opt => 
              `<option value="${opt.value}" ${opt.value === this.currentLogPath ? 'selected' : ''}>${opt.label}</option>`
            ).join('')}
          </optgroup>
        </select>
      </div>
    `;
  }

  /**
   * 渲染 Journal 输入框
   */
  private renderJournalInput(): string {
    return `
      <div class="input-wrapper">
        <input 
          type="text" 
          class="toolbar-input" 
          id="journal-unit-input"
          list="journal-units"
          placeholder="服务单元 (如 sshd)"
          value="${this.journalUnit}"
          onchange="window.updateJournalUnit(this.value)"
        />
        <datalist id="journal-units">
          <option value="sshd">SSH 服务</option>
          <option value="nginx">Nginx Web 服务器</option>
          <option value="docker">Docker 容器服务</option>
          <option value="cron">定时任务服务</option>
          <option value="rsyslog">系统日志服务</option>
          <option value="NetworkManager">网络管理器</option>
          <option value="systemd-journald">Journal 日志服务</option>
          <option value="firewalld">防火墙服务</option>
          <option value="mariadb">MariaDB 数据库</option>
          <option value="mysqld">MySQL 数据库</option>
          <option value="redis">Redis 服务</option>
        </datalist>
      </div>
    `;
  }

  /**
   * 渲染日志内容区域
   */
  private renderLogContent(): string {
    return `
      <div class="log-content-wrapper">
        <div class="log-stats-bar">
          <div class="stat-group">
            <span class="stat-label">来源:</span>
            <span class="stat-value mono" id="current-source">-</span>
          </div>
          <div class="stat-divider"></div>
          <div class="stat-group">
            <span class="stat-label">总计:</span>
            <span class="stat-value" id="total-logs">0</span>
          </div>
        </div>

        <div class="log-ai-panel" id="log-ai-explanation" style="display: none;">
          <div class="log-ai-panel-header">
            <span class="log-ai-title">AI分析（当前页已加载日志）</span>
            <button class="log-ai-toggle-btn" onclick="window.toggleLogAIExplanation()">
              折叠
            </button>
          </div>
          <pre class="log-ai-content" id="log-ai-content"></pre>
        </div>
        
        <div class="log-viewer" id="log-container">
          <div class="loading-placeholder">
            <div class="spinner"></div>
            <p>正在获取日志数据...</p>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 渲染日志条目列表
   */
  renderLogEntries(entries: LogEntry[]): string {
    if (entries.length === 0) {
      return `
        <div class="empty-state">
          ${Log({ theme: 'outline', size: '48', fill: 'currentColor' })}
          <p>没有找到日志记录</p>
          <small>请检查日志文件路径或调整过滤条件</small>
        </div>
      `;
    }

    return `
      <div class="log-entries">
        ${entries.map(entry => this.renderLogEntry(entry)).join('')}
      </div>
    `;
  }

  /**
   * 渲染单条日志
   */
  private renderLogEntry(entry: LogEntry): string {
    const levelClass = this.getLevelClass(entry.level);
    const highlightClass = entry.highlighted ? 'highlighted' : '';

    return `
      <div class="log-entry ${levelClass} ${highlightClass}">
        <div class="log-header">
          <span class="log-timestamp">
            ${Calendar({ theme: 'outline', size: '14', fill: 'currentColor' })}
            ${entry.timestamp || 'Unknown'}
          </span>
          <span class="log-level ${levelClass}">${entry.level}</span>
          <span class="log-service">${entry.service}</span>
        </div>
        <div class="log-message">${this.escapeHtml(entry.message)}</div>
        ${entry.highlighted ? '<div class="log-highlight-badge">⚠️ 包含关键词</div>' : ''}
      </div>
    `;
  }

  /**
   * 获取日志级别对应的 CSS 类
   */
  private getLevelClass(level: string): string {
    const levelUpper = level.toUpperCase();
    if (levelUpper.includes('ERROR') || levelUpper.includes('FAIL')) return 'level-error';
    if (levelUpper.includes('WARN')) return 'level-warn';
    if (levelUpper.includes('INFO')) return 'level-info';
    if (levelUpper.includes('DEBUG')) return 'level-debug';
    return 'level-info';
  }

  /**
   * HTML 转义
   */
  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * 设置当前日志路径
   */
  setLogPath(path: string): void {
    this.currentLogPath = path;
  }

  /**
   * 设置显示行数
   */
  setLines(lines: number): void {
    this.currentLines = lines;
  }

  /**
   * 设置过滤器
   */
  setFilter(filter: string): void {
    this.currentFilter = filter;
  }

  /**
   * 设置是否使用 journalctl
   */
  setUseJournalctl(use: boolean): void {
    this.useJournalctl = use;
  }

  /**
   * 设置 journal 单元
   */
  setJournalUnit(unit: string): void {
    this.journalUnit = unit;
  }

  setMultiSelectEnabled(enabled: boolean): void {
    this.multiSelectEnabled = enabled;
  }

  setLevelFilter(level: string): void {
    this.currentLevelFilter = level;
  }
}
