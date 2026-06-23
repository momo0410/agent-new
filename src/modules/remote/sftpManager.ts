/**
 * SFTP文件管理器
 * 处理远程文件操作
 */

import { sshConnectionManager } from './sshConnectionManager';
import { invoke } from '../../shims/@tauri-apps/api/core';
import { EventEmitter } from '../utils/EventEmitter';

export interface SftpFileInfo {
  name: string;
  path: string;
  file_type: string; // "file", "directory", "symlink"
  size: number;
  permissions: string;
  modified?: string;
  owner?: string;
  group?: string;
}

export class SftpManager extends EventEmitter<[SftpFileInfo[], string]> {
  private currentPath: string = '/';  // 默认目录改为根目录
  private fileList: SftpFileInfo[] = [];
  private sortMode: 'name-asc' | 'name-desc' | 'size-asc' | 'size-desc' | 'modified-asc' | 'modified-desc' = 'name-asc';
  private collator = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true, ignorePunctuation: true });
  private hasLoadedOnce = false;
  private lastLoadError: string | null = null;

  /**
   * 设置排序方式，目录始终排在文件之前
   */
  setSortMode(mode: 'name-asc' | 'name-desc' | 'size-asc' | 'size-desc' | 'modified-asc' | 'modified-desc'): void {
    this.sortMode = mode;
    // 不改变数据源，仅通知监听器以触发重渲染
    this.notifyListeners();
  }

  /**
   * 获取当前排序模式
   */
  getSortMode(): string {
    return this.sortMode;
  }

  private sortFiles(files: SftpFileInfo[]): SftpFileInfo[] {
    const isDir = (f: SftpFileInfo) => f.file_type === 'directory';
    const dirFirst = (a: SftpFileInfo, b: SftpFileInfo) => {
      if (isDir(a) && !isDir(b)) return -1;
      if (!isDir(a) && isDir(b)) return 1;
      return 0;
    };

    const nameCmp = (a: SftpFileInfo, b: SftpFileInfo) => this.collator.compare(a.name, b.name);
    const sizeCmp = (a: SftpFileInfo, b: SftpFileInfo) => a.size - b.size;
    const modifiedCmp = (a: SftpFileInfo, b: SftpFileInfo) => {
      const aTime = a.modified ? new Date(a.modified).getTime() : 0;
      const bTime = b.modified ? new Date(b.modified).getTime() : 0;
      return aTime - bTime;
    };

    const withinGroupCmp = (a: SftpFileInfo, b: SftpFileInfo) => {
      let cmp = 0;

      if (this.sortMode.startsWith('name-')) {
        cmp = nameCmp(a, b);
        return this.sortMode === 'name-desc' ? -cmp : cmp;
      } else if (this.sortMode.startsWith('size-')) {
        cmp = sizeCmp(a, b);
        return this.sortMode === 'size-desc' ? -cmp : cmp;
      } else if (this.sortMode.startsWith('modified-')) {
        cmp = modifiedCmp(a, b);
        return this.sortMode === 'modified-desc' ? -cmp : cmp;
      }

      return 0;
    };

    return [...files].sort((a, b) => {
      const group = dirFirst(a, b);
      if (group !== 0) return group;
      return withinGroupCmp(a, b);
    });
  }

  /**
   * 获取当前文件列表
   */
  getCurrentFiles(): SftpFileInfo[] {
    return this.sortFiles(this.fileList);
  }
  /**
   * 刷新当前目录
   */
  async refreshCurrentDirectory(): Promise<boolean> {
    try {
      return await this.refreshFileList();
    } catch (error) {
      console.error('刷新目录失败:', error);
      this.lastLoadError = error instanceof Error ? error.message : String(error);
      this.hasLoadedOnce = false;
      this.notifyListeners();
      return false;
    }
  }

  /**
   * 获取当前路径
   */
  getCurrentPath(): string {
    return this.currentPath;
  }

  /**
   * 获取文件的规范化完整路径，避免根目录下出现 //filename
   */
  getFilePath(file: Pick<SftpFileInfo, 'name' | 'path'>): string {
    if (file.path && file.path.startsWith('/')) {
      return this.normalizePath(file.path);
    }

    const base = this.normalizePath(this.currentPath);
    const childPath = file.path || file.name;
    return this.normalizePath(base === '/' ? `/${childPath}` : `${base}/${childPath}`);
  }


  /**
   * 规范化远程路径：统一为POSIX风格，去重/、去除末尾/、解析..和.
   */
  public normalizePath(p: string): string {
    let np = (p || '/').replace(/\\/g, '/');
    np = np.replace(/\/+/g, '/');
    if (!np.startsWith('/')) np = '/' + np;
    if (np.length > 1 && np.endsWith('/')) np = np.slice(0, -1);

    // 解析 .. 和 . 符号
    const parts: string[] = [];
    np.split('/').forEach(seg => {
      if (!seg || seg === '.') return;
      if (seg === '..') {
        if (parts.length > 0) parts.pop();
      } else {
        parts.push(seg);
      }
    });
    return parts.length === 0 ? '/' : '/' + parts.join('/');
  }


  /**
   * 获取当前文件列表
   */
  getFileList(): SftpFileInfo[] {
    return this.fileList;
  }

  /**
   * 刷新文件列表
   */
  async refreshFileList(): Promise<boolean> {
    if (!sshConnectionManager.isConnected()) {
      console.warn('SSH未连接，无法刷新SFTP文件列表');
      this.fileList = [];
      this.hasLoadedOnce = false;
      this.lastLoadError = 'SSH未连接';
      this.notifyListeners();
      return false;
    }

    try {
      const files = await invoke('sftp_list_files', {
        path: this.currentPath
      });

      this.fileList = this.sortFiles(files);
      this.hasLoadedOnce = true;
      this.lastLoadError = null;
      this.notifyListeners();

      // 更新SSH活动时间
      sshConnectionManager.updateLastActivity();
      return true;

    } catch (error) {
      const errMsg = error instanceof Error ? error.message : String(error);
      const isConnectionError = /SSH connection closed|没有活动的 SSH 连接|not connected|connection lost|broken pipe|EOF|reset/i.test(errMsg);
      // SSH连接关闭/未连接等状态类错误静默处理，同时主动同步一次后端连接状态
      if (isConnectionError) {
        try {
          await sshConnectionManager.checkConnectionStatus(true);
        } catch {
          // 忽略状态同步失败，保持前端降级可用
        }
        this.fileList = [];
        this.hasLoadedOnce = false;
        this.lastLoadError = errMsg;
        this.notifyListeners();
        return false;
      }
      console.error('获取SFTP文件列表失败:', error);
      this.lastLoadError = errMsg;
      this.hasLoadedOnce = false;
      this.notifyListeners();
      (window as any).showNotification && (window as any).showNotification(`获取文件列表失败: ${error}`, 'error');
      return false;
    }
  }


  /**
   * 导航到指定路径
   */
  async navigateToPath(path: string): Promise<void> {
    if (this.isNavigating) {
      console.log('⏳ 正在导航中，忽略新的导航请求');
      return;
    }

    try {
      this.isNavigating = true;
      const normalized = this.normalizePath(path);
      console.log('📂 导航到路径:', normalized);
      this.currentPath = normalized;
      await this.refreshFileList();
    } finally {
      this.isNavigating = false;
    }
  }

  /**
   * 导航到上级目录
   */
  async navigateToParent(): Promise<void> {
    const cur = this.normalizePath(this.currentPath);
    if (cur === '/') return;

    const parentPath = cur.split('/').slice(0, -1).join('/') || '/';
    await this.navigateToPath(parentPath);
  }

  /**
   * 处理文件点击
   */
  async handleFileClick(file: SftpFileInfo): Promise<void> {
    if (file.file_type === 'directory') {
      await this.navigateToPath(this.getFilePath(file));
    } else {
      // 处理文件点击（可以扩展为下载、编辑等功能）
      console.log('点击文件:', file.name);
    }
  }

  /**
   * 渲染文件列表HTML（返回<tr>行，供#sftp-file-list tbody插入）
   */
  renderFileListHTML(): string {
    const updateCount = (count: number) => {
      setTimeout(() => {
        const countEl = document.getElementById('sftp-status-count');
        if (countEl) {
          countEl.innerHTML = `<span>${count} 项</span>`;
        }
      }, 0);
    };

    // 未连接时显示一行提示
    if (!sshConnectionManager.isConnected()) {
      updateCount(0);
      return `
        <tr>
          <td colspan="4" style="padding: 40px; text-align: center; color: var(--text-secondary); font-size: 13px;">
            <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
              <div style="font-size: 24px; opacity: 0.5;">📡</div>
              <span>SSH未连接 — 请先建立连接</span>
            </div>
          </td>
        </tr>
      `;
    }

    if (this.lastLoadError && this.fileList.length === 0) {
      updateCount(0);
      return `
        <tr>
          <td colspan="4" style="padding: 40px; text-align: center; color: var(--warning-color, #e6a23c); font-size: 13px;">
            <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
              <div style="font-size: 24px; opacity: 0.7;">⚠️</div>
              <span>SFTP 列目录失败，请点击“刷新”重试</span>
            </div>
          </td>
        </tr>
      `;
    }

    if (!this.hasLoadedOnce && this.fileList.length === 0) {
      updateCount(0);
      return `
        <tr>
          <td colspan="4" style="padding: 40px; text-align: center; color: var(--text-secondary); font-size: 13px;">
            <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
              <div style="font-size: 24px; opacity: 0.5;">🧭</div>
              <span>尚未加载目录，请点击“刷新”</span>
            </div>
          </td>
        </tr>
      `;
    }

    // 空目录
    if (this.fileList.length === 0) {
      updateCount(0);
      return `
        <tr>
          <td colspan="4" style="padding: 40px; text-align: center; color: var(--text-secondary); font-size: 13px;">
            <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
              <div style="font-size: 24px; opacity: 0.5;">📁</div>
              <span>目录为空</span>
            </div>
          </td>
        </tr>
      `;
    }

    let html = '';

    // 已按规则排序的文件和目录
    const sortedFiles = this.getCurrentFiles();
    sortedFiles.forEach((file, index) => {
      const icon = this.getFileIcon(file);
      const sizeText = file.file_type === 'directory' ? '-' : this.formatFileSize(file.size);
      const perms = this.formatPermissionsSymbolic(file.permissions);
      const modified = this.formatModifiedDate((file as any).modified);

      // Animation delay for staggered fade-in
      const style = `--row-index: ${index}`;

      html += `
        <tr class="sftp-file-row" data-file-index="${index}" 
            onclick="window.sftpSelectFile && window.sftpSelectFile(${index}, this)"
            oncontextmenu="window.showSftpContextMenu(event, ${index}); return false;" 
            ondblclick="sftpManager.handleFileClickByIndex(${index})"
            style="${style}">
          <td class="file-icon-cell">
            <div class="file-icon">${icon}</div>
            <span class="file-name" title="${this.getFilePath(file)}">${file.name}</span>
          </td>
          <td style="font-size: 12px; color: var(--text-secondary);">${sizeText}</td>
          <td style="font-family: monospace; font-size: 11px; color: var(--text-secondary);">${perms}</td>
          <td style="font-size: 12px; color: var(--text-secondary);">${modified}</td>
        </tr>
      `;
    });

    // Update status bar count if element exists
    updateCount(sortedFiles.length);

    return html;
  }

  /**
   * 通过索引处理文件点击（用于HTML onclick）
   */
  async handleFileClickByIndex(index: number): Promise<void> {
    try {
      const files = this.getCurrentFiles();
      if (index >= 0 && index < files.length) {
        const file = files[index];
        console.log('🖱️ 点击文件:', file.name, '类型:', file.file_type);

        // 防止重复点击
        if (this.isNavigating) {
          console.log('⏳ 正在导航中，忽略点击');
          return;
        }

        await this.handleFileClick(file);
      }
    } catch (error) {
      console.error('处理文件点击失败:', error);
    }
  }


  public getFileByIndex(index: number): SftpFileInfo | null {
    const files = this.getCurrentFiles();
    if (index < 0 || index >= files.length) return null;
    return files[index];
  }

  private isNavigating: boolean = false;

  /**
   * 获取文件图标
   */

  private getFileIcon(file: SftpFileInfo): string {
    if (file.file_type === 'directory') return '📁';
    if (file.name.endsWith('.sh')) return '🐧';
    if (file.name.endsWith('.txt') || file.name.endsWith('.log')) return '📄';
    if (file.name.endsWith('.zip') || file.name.endsWith('.tar')) return '📦';
    if (file.name.endsWith('.jpg') || file.name.endsWith('.png')) return '🖼️';
    return '📄';
  }

  /**
   * 格式化文件大小
   */
  private formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  /**
   * 格式化上次修改时间
   */
  private formatModifiedDate(input: any): string {
    if (input === undefined || input === null || input === '') return '';
    let date: Date;
    if (typeof input === 'number') {
      // 既支持秒也支持毫秒（阈值：10^12）
      const ms = input < 1e12 ? input * 1000 : input;
      date = new Date(ms);
    } else if (typeof input === 'string') {
      const num = Number(input);
      if (!isNaN(num)) {
        const ms = num < 1e12 ? num * 1000 : num;
        date = new Date(ms);
      } else {
        date = new Date(input);
      }
    } else {
      return '';
    }
    if (isNaN(date.getTime())) return '';
    try {
      return new Intl.DateTimeFormat(undefined, {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
      }).format(date);
    } catch {
      return date.toLocaleString();
    }
  }

  /**
   * 格式化权限为符号形式 (如 rwxr-xr-x)
   */
  private formatPermissionsSymbolic(input: string): string {
    const value = (input || '').trim();
    if (!value) return '---------';

    // already symbolic: rwxr-xr-x / drwxr-xr-x / lrwxrwxrwx
    if (/^[dl-][rwx-]{9}$/.test(value)) return value;
    if (/^[rwx-]{9}$/.test(value)) return value;

    const digits = value.replace(/^0+/, '').padStart(3, '0').slice(-3);
    if (!/^[0-7]{3}$/.test(digits)) return '---------';
    const toTriplet = (n: number) => {
      const r = (n & 4) ? 'r' : '-';
      const w = (n & 2) ? 'w' : '-';
      const x = (n & 1) ? 'x' : '-';
      return r + w + x;
    };
    const u = parseInt(digits[0], 8);
    const g = parseInt(digits[1], 8);
    const o = parseInt(digits[2], 8);
    return toTriplet(u) + toTriplet(g) + toTriplet(o);
  }


  private notifyListeners(): void {
    this.emit([this.fileList, this.currentPath]);
  }
}

// 全局SFTP管理器实例
export const sftpManager = new SftpManager();
