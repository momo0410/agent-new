import {
  Download,
  FolderPlus,
  History,
  Home,
  Refresh,
  Up,
  Upload
} from '@icon-park/svg';

export interface RemoteOperationsPageContext {
  isConnected: boolean;
  fileListHtml: string;
  contextMenuHtml: string;
  scheduleInit: () => void;
}

export function renderRemoteOperationsPage(context: RemoteOperationsPageContext): string {
  context.scheduleInit();

  return `
    <div class="sftp-page-container">
      <div class="sftp-header">
        <div class="sftp-title">
          <div class="sftp-title-icon">
            <img src="/icons/sftp-file.png" alt="SFTP 文件管理" />
          </div>
          <span>SFTP 文件管理</span>
        </div>
        <div class="sftp-actions">
          <button id="sftp-history-btn" class="modern-btn secondary" onclick="window.toggleSftpHistory && window.toggleSftpHistory()" title="传输历史">
            ${History({ theme: 'outline', size: '16', fill: 'currentColor' })}
            <span>历史</span>
          </button>
          <button id="sftp-refresh-btn" class="page-refresh-btn" onclick="window.sftpRefresh && window.sftpRefresh()" title="刷新列表">
            ${Refresh({ theme: 'outline', size: '16', fill: 'currentColor' })}
            <span>刷新</span>
          </button>
          <button id="sftp-create-folder-btn" class="modern-btn secondary" onclick="window.sftpOpenCreateFolder && window.sftpOpenCreateFolder()" title="新建文件夹">
            ${FolderPlus({ theme: 'outline', size: '16', fill: 'currentColor' })}
            <span>新建</span>
          </button>
          <button id="sftp-upload-btn" class="modern-btn primary" onclick="window.sftpOpenUpload && window.sftpOpenUpload()" title="上传文件">
            ${Upload({ theme: 'outline', size: '16', fill: 'currentColor' })}
            <span>上传</span>
          </button>
          <button id="sftp-download-btn" class="modern-btn secondary" onclick="window.sftpOpenDownload && window.sftpOpenDownload()" title="下载文件">
            ${Download({ theme: 'outline', size: '16', fill: 'currentColor' })}
            <span>下载</span>
          </button>
        </div>
      </div>

      <div class="sftp-toolbar">
        <div class="sftp-nav-controls">
          <button class="modern-btn icon-only secondary" onclick="sftpManager.navigateToParent()" title="返回上一级">
            ${Up({ theme: 'outline', size: '16', fill: 'currentColor' })}
          </button>
          <button class="modern-btn icon-only secondary" onclick="sftpManager.navigateToPath('/')" title="返回根目录">
            ${Home({ theme: 'outline', size: '16', fill: 'currentColor' })}
          </button>
        </div>
        
        <div class="sftp-breadcrumb-bar">
          <input
            type="text"
            id="sftp-path-input"
            class="sftp-path-input"
            placeholder="输入路径..."
            onkeydown="if(event.key === 'Enter') sftpManager.navigateToPath(this.value)"
          />
        </div>
      </div>

      <div class="sftp-file-list-container">
        <table class="sftp-table">
          <thead>
            <tr>
              <th style="width: 50%; cursor: pointer;" onclick="window.setSftpSortMode(sftpManager.getSortMode() === 'name-asc' ? 'name-desc' : 'name-asc')">
                名称
              </th>
              <th style="width: 15%; cursor: pointer;" onclick="window.setSftpSortMode(sftpManager.getSortMode() === 'size-asc' ? 'size-desc' : 'size-asc')">
                大小
              </th>
              <th style="width: 15%;">权限</th>
              <th style="width: 20%; cursor: pointer;" onclick="window.setSftpSortMode(sftpManager.getSortMode() === 'modified-asc' ? 'modified-desc' : 'modified-asc')">
                修改时间
              </th>
            </tr>
          </thead>
          <tbody id="sftp-file-list">
            ${context.fileListHtml}
          </tbody>
        </table>
      </div>

      <div class="sftp-status-bar">
        <div class="status-item" id="sftp-status-count">
          <span>0 项</span>
        </div>
        <div class="status-item">
          ${context.isConnected ? '<span style="color: var(--success-color);">● 已连接</span>' : '<span style="color: var(--error-color);">● 未连接</span>'}
        </div>
      </div>
    </div>
    ${context.contextMenuHtml}
  `;
}
