/**
 * @tauri-apps/api/webviewWindow shim
 * 在纯 Web/Python 模式下，使用浏览器窗口提供接近 Tauri 的窗口行为。
 */

type WindowOptions = {
  url?: string;
  title?: string;
  width?: number;
  height?: number;
  minWidth?: number;
  minHeight?: number;
  resizable?: boolean;
  maximizable?: boolean;
  minimizable?: boolean;
  closable?: boolean;
  center?: boolean;
  skipTaskbar?: boolean;
  alwaysOnTop?: boolean;
  decorations?: boolean;
  _internalSkipOpen?: boolean;
  [key: string]: any;
};

const windowRegistry = new Map<string, WebviewWindow>();

function buildFeatures(options?: WindowOptions): string {
  const width = options?.width ?? 1000;
  const height = options?.height ?? 700;
  const left = options?.center ? Math.max(0, Math.floor((window.screen.width - width) / 2)) : undefined;
  const top = options?.center ? Math.max(0, Math.floor((window.screen.height - height) / 2)) : undefined;

  return [
    `width=${width}`,
    `height=${height}`,
    `resizable=${options?.resizable === false ? 'no' : 'yes'}`,
    `scrollbars=yes`,
    `status=yes`,
    left != null ? `left=${left}` : '',
    top != null ? `top=${top}` : '',
  ]
    .filter(Boolean)
    .join(',');
}

export class WebviewWindow {
  private _label: string;
  private _window: Window | null = null;

  constructor(label: string, options?: WindowOptions) {
    this._label = label;

    const existing = windowRegistry.get(label);
    if (existing && existing.isAlive()) {
      this._window = existing._window;
      return;
    }

    if (!options?._internalSkipOpen) {
      this._window = window.open(options?.url || '/', label, buildFeatures(options));
      if (this._window && options?.title) {
        try {
          this._window.document.title = options.title;
        } catch {
          // ignore cross-window timing issues
        }
      }
      if (this._window) {
        windowRegistry.set(label, this);
      }
    }
  }

  private isAlive(): boolean {
    return !!this._window && !this._window.closed;
  }

  static async getByLabel(label: string): Promise<WebviewWindow | null> {
    const existing = windowRegistry.get(label);
    if (!existing) {
      return null;
    }
    if (!existing.isAlive()) {
      windowRegistry.delete(label);
      return null;
    }
    return existing;
  }

  async setFocus(): Promise<void> {
    if (this.isAlive()) {
      this._window!.focus();
    }
  }

  async unminimize(): Promise<void> {
    if (this.isAlive()) {
      this._window!.focus();
    }
  }

  once(event: string, callback: (data: any) => void): void {
    if (event === 'tauri://created' && this.isAlive()) {
      setTimeout(() => callback({ label: this._label }), 0);
      return;
    }
    if (event === 'tauri://error' && !this.isAlive()) {
      setTimeout(() => callback(new Error(`窗口创建失败: ${this._label}`)), 0);
    }
  }

  listen(_event: string, _callback: (data: any) => void): () => void {
    return () => {};
  }

  get label(): string {
    return this._label;
  }

  async setDecorations(_decorations: boolean): Promise<void> {}

  async setSize(size: { width: number; height: number; type?: string }): Promise<void> {
    if (this.isAlive()) {
      this._window!.resizeTo(size.width, size.height);
    }
  }

  async minimize(): Promise<void> {
    if (this.isAlive()) {
      this._window!.blur();
    }
  }

  async maximize(): Promise<void> {
    if (this.isAlive()) {
      this._window!.moveTo(0, 0);
      this._window!.resizeTo(window.screen.availWidth, window.screen.availHeight);
      this._window!.focus();
    }
  }

  async close(): Promise<void> {
    if (this.isAlive()) {
      this._window!.close();
    }
    windowRegistry.delete(this._label);
  }
}

export function getCurrentWebviewWindow(): WebviewWindow {
  return new WebviewWindow('main', { _internalSkipOpen: true });
}
