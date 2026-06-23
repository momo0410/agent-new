import { invoke } from '../../shims/@tauri-apps/api/core';

export class CreateFolderModal {
  private modal: HTMLElement | null = null;
  private isVisible = false;
  private currentParentDir = '';
  private boundKeydownHandler: ((e: KeyboardEvent) => void) | null = null;

  constructor() {
    this.createModal();
    this.setupEventListeners();
  }

  private createModal(): void {
    this.modal = document.createElement('div');
    this.modal.id = 'create-folder-modal';
    this.modal.style.display = 'none';
    this.modal.innerHTML = `
      <div class="modal-overlay" style="
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
      ">
        <div class="modal-content" style="
          background: var(--bg-primary);
          border: 1px solid var(--border-color);
          border-radius: var(--border-radius-lg);
          width: 400px;
          max-width: 90vw;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        ">
          <div style="
            padding: var(--spacing-md);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
          ">
            <h3 style="
              margin: 0;
              color: var(--text-primary);
              font-size: 16px;
              font-weight: 600;
            ">新建文件夹</h3>
            <button id="create-folder-modal-close" type="button" style="
              background: none;
              border: none;
              color: var(--text-secondary);
              font-size: 18px;
              cursor: pointer;
              padding: 4px;
              border-radius: var(--border-radius-sm);
            " onmouseover="this.style.background='var(--bg-tertiary)'" onmouseout="this.style.background='none'">
              ×
            </button>
          </div>

          <div style="padding: var(--spacing-md);">
            <div style="margin-bottom: var(--spacing-md);">
              <label style="
                display: block;
                margin-bottom: var(--spacing-xs);
                color: var(--text-secondary);
                font-size: 12px;
                font-weight: 500;
              ">创建位置</label>
              <div id="create-folder-parent-dir" style="
                padding: var(--spacing-sm);
                background: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: var(--border-radius-sm);
                color: var(--text-primary);
                font-family: monospace;
                font-size: 12px;
                word-break: break-all;
              "></div>
            </div>

            <div style="margin-bottom: var(--spacing-md);">
              <label for="create-folder-name" style="
                display: block;
                margin-bottom: var(--spacing-xs);
                color: var(--text-secondary);
                font-size: 12px;
                font-weight: 500;
              ">文件夹名称</label>
              <input
                type="text"
                id="create-folder-name"
                placeholder="请输入文件夹名称"
                style="
                  width: 100%;
                  padding: var(--spacing-sm);
                  border: 1px solid var(--border-color);
                  border-radius: var(--border-radius-sm);
                  background: var(--bg-secondary);
                  color: var(--text-primary);
                  font-size: 14px;
                  box-sizing: border-box;
                "
              />
              <div id="create-folder-error" style="
                margin-top: var(--spacing-xs);
                color: var(--error-color);
                font-size: 11px;
                display: none;
              "></div>
            </div>

            <div style="margin-bottom: var(--spacing-lg);">
              <label style="
                display: block;
                margin-bottom: var(--spacing-xs);
                color: var(--text-secondary);
                font-size: 12px;
                font-weight: 500;
              ">完整路径</label>
              <div id="create-folder-full-path" style="
                padding: var(--spacing-sm);
                background: var(--bg-tertiary);
                border: 1px solid var(--border-color);
                border-radius: var(--border-radius-sm);
                color: var(--text-secondary);
                font-family: monospace;
                font-size: 11px;
                word-break: break-all;
                min-height: 20px;
              "></div>
            </div>

            <div style="
              display: flex;
              gap: var(--spacing-sm);
              justify-content: flex-end;
            ">
              <button id="create-folder-cancel-btn" type="button" class="modern-btn secondary" style="
                padding: var(--spacing-sm) var(--spacing-md);
                font-size: 12px;
              ">
                取消
              </button>
              <button id="create-folder-confirm-btn" type="button" class="modern-btn" style="
                padding: var(--spacing-sm) var(--spacing-md);
                background: var(--success-color);
                border: 1px solid var(--success-color);
                color: white;
                font-size: 12px;
                opacity: 0.5;
              " disabled>
                创建
              </button>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(this.modal);
  }

  private setupEventListeners(): void {
    if (!this.modal) return;

    const closeBtn = document.getElementById('create-folder-modal-close');
    const cancelBtn = document.getElementById('create-folder-cancel-btn');
    const confirmBtn = document.getElementById('create-folder-confirm-btn') as HTMLButtonElement | null;
    const nameInput = document.getElementById('create-folder-name') as HTMLInputElement | null;
    const overlay = this.modal.querySelector('.modal-overlay');

    closeBtn?.addEventListener('click', () => this.hide());
    cancelBtn?.addEventListener('click', () => this.hide());
    confirmBtn?.addEventListener('click', () => {
      void this.createFolder();
    });

    if (nameInput) {
      nameInput.addEventListener('input', () => this.validateInput());
      nameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          if (!confirmBtn?.disabled) {
            void this.createFolder();
          }
        }
      });
    }

    overlay?.addEventListener('click', (e) => {
      if (e.target === overlay) {
        this.hide();
      }
    });

    this.boundKeydownHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && this.isVisible) {
        this.hide();
      }
    };
    document.addEventListener('keydown', this.boundKeydownHandler);
  }

  public show(parentDir: string): void {
    if (!this.modal) return;

    this.currentParentDir = parentDir;
    this.isVisible = true;

    const parentDirEl = document.getElementById('create-folder-parent-dir');
    const nameInput = document.getElementById('create-folder-name') as HTMLInputElement | null;

    if (parentDirEl) {
      parentDirEl.textContent = parentDir;
    }

    if (nameInput) {
      nameInput.value = '';
    }

    this.hideError();
    this.validateInput();
    this.modal.style.display = 'block';

    window.setTimeout(() => {
      nameInput?.focus();
      nameInput?.select();
    }, 0);
  }

  public hide(): void {
    if (!this.modal) return;

    this.modal.style.display = 'none';
    this.isVisible = false;
    this.currentParentDir = '';
    this.hideError();
  }

  private validateInput(): void {
    const nameInput = document.getElementById('create-folder-name') as HTMLInputElement | null;
    const confirmBtn = document.getElementById('create-folder-confirm-btn') as HTMLButtonElement | null;
    const fullPathEl = document.getElementById('create-folder-full-path');

    if (!nameInput || !confirmBtn || !fullPathEl) return;

    const folderName = nameInput.value.trim();
    let isValid = true;
    let errorMessage = '';

    if (!folderName) {
      isValid = false;
    } else {
      const invalidChars = /[\/\\:*?"<>|]/;
      if (invalidChars.test(folderName)) {
        isValid = false;
        errorMessage = '文件夹名称不能包含字符: / \\ : * ? " < > |';
      } else if (folderName.startsWith('.') || folderName.endsWith('.')) {
        isValid = false;
        errorMessage = '文件夹名称不能以点开头或结尾';
      } else if (folderName.length > 255) {
        isValid = false;
        errorMessage = '文件夹名称过长，不能超过 255 个字符';
      }
    }

    fullPathEl.textContent = isValid && folderName
      ? this.joinRemotePath(this.currentParentDir, folderName)
      : '';

    confirmBtn.disabled = !isValid;
    confirmBtn.style.opacity = isValid ? '1' : '0.5';

    if (errorMessage) {
      this.showError(errorMessage);
    } else {
      this.hideError();
    }
  }

  private showError(message: string): void {
    const errorEl = document.getElementById('create-folder-error');
    if (!errorEl) return;

    errorEl.textContent = message;
    errorEl.style.display = 'block';
  }

  private hideError(): void {
    const errorEl = document.getElementById('create-folder-error');
    if (!errorEl) return;

    errorEl.textContent = '';
    errorEl.style.display = 'none';
  }

  private joinRemotePath(dir: string, name: string): string {
    const normalizedDir = (dir || '/').replace(/\\/g, '/');
    const base = normalizedDir.endsWith('/') && normalizedDir !== '/'
      ? normalizedDir.slice(0, -1)
      : normalizedDir;
    if (!base || base === '/') return `/${name}`;
    return `${base}/${name}`;
  }

  private async createFolder(): Promise<void> {
    const nameInput = document.getElementById('create-folder-name') as HTMLInputElement | null;
    const confirmBtn = document.getElementById('create-folder-confirm-btn') as HTMLButtonElement | null;
    const cancelBtn = document.getElementById('create-folder-cancel-btn') as HTMLButtonElement | null;

    if (!nameInput || !confirmBtn || !cancelBtn) return;

    const folderName = nameInput.value.trim();
    if (!folderName) return;

    confirmBtn.disabled = true;
    cancelBtn.disabled = true;
    confirmBtn.textContent = '创建中...';
    confirmBtn.style.opacity = '0.5';

    try {
      const fullPath = this.joinRemotePath(this.currentParentDir, folderName);
      await invoke('sftp_create_directory', {
        remotePath: fullPath,
      });

      (window as any).showNotification?.(`文件夹创建成功: ${folderName}`, 'success');
      (window as any).sftpManager?.refreshCurrentDirectory?.();
      this.hide();
    } catch (error) {
      console.error('创建文件夹失败:', error);
      const message = error instanceof Error ? error.message : String(error);
      (window as any).showNotification?.(`创建文件夹失败: ${message}`, 'error');
      this.showError(`创建失败: ${message}`);
    } finally {
      confirmBtn.disabled = false;
      cancelBtn.disabled = false;
      confirmBtn.textContent = '创建';
      confirmBtn.style.opacity = '1';
      this.validateInput();
    }
  }

  public destroy(): void {
    if (this.boundKeydownHandler) {
      document.removeEventListener('keydown', this.boundKeydownHandler);
      this.boundKeydownHandler = null;
    }
    this.modal?.remove();
    this.modal = null;
    this.isVisible = false;
  }
}
