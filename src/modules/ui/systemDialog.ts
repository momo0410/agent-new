interface DialogFilter {
  name?: string;
  extensions?: string[];
}

interface BaseDialogOptions {
  title: string;
  description: string;
  confirmText: string;
  placeholder?: string;
  defaultValue?: string;
  filters?: DialogFilter[];
}

function buildHint(filters?: DialogFilter[]): string {
  if (!filters || filters.length === 0) {
    return '';
  }

  return filters
    .map((item) => {
      const extensions = item.extensions?.join(', ');
      return item.name && extensions ? `${item.name}: ${extensions}` : item.name || extensions || '';
    })
    .filter(Boolean)
    .join(' | ');
}

function showPathDialog(options: BaseDialogOptions & { multiple?: boolean }): Promise<string | string[] | null> {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.style.cssText = [
      'position: fixed',
      'inset: 0',
      'background: rgba(15, 23, 42, 0.48)',
      'backdrop-filter: blur(6px)',
      'display: flex',
      'align-items: center',
      'justify-content: center',
      'z-index: 10000',
      'padding: 24px',
    ].join(';');

    const card = document.createElement('div');
    card.style.cssText = [
      'width: min(640px, 100%)',
      'background: var(--bg-primary, #fff)',
      'color: var(--text-primary, #111827)',
      'border: 1px solid var(--border-color, rgba(148,163,184,0.35))',
      'border-radius: 16px',
      'box-shadow: 0 24px 80px rgba(15, 23, 42, 0.24)',
      'padding: 20px',
    ].join(';');

    const title = document.createElement('h3');
    title.textContent = options.title;
    title.style.cssText = 'margin: 0 0 8px; font-size: 18px;';

    const description = document.createElement('p');
    description.textContent = options.description;
    description.style.cssText = 'margin: 0 0 12px; color: var(--text-secondary, #64748b); line-height: 1.5;';

    const hint = buildHint(options.filters);
    const hintEl = document.createElement('div');
    hintEl.textContent = hint ? `支持类型: ${hint}` : '可直接输入完整路径';
    hintEl.style.cssText = 'margin-bottom: 12px; font-size: 12px; color: var(--text-tertiary, #94a3b8);';

    const input = options.multiple ? document.createElement('textarea') : document.createElement('input');
    input.value = options.defaultValue || '';
    input.setAttribute('placeholder', options.placeholder || '请输入路径');
    input.style.cssText = [
      'width: 100%',
      'border-radius: 10px',
      'border: 1px solid var(--border-color, #cbd5e1)',
      'background: var(--bg-secondary, #f8fafc)',
      'color: inherit',
      'padding: 12px 14px',
      'font-size: 14px',
      'box-sizing: border-box',
      options.multiple ? 'min-height: 120px; resize: vertical' : '',
    ].join(';');

    const actions = document.createElement('div');
    actions.style.cssText = 'display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = '取消';
    cancelBtn.className = 'modern-btn secondary';

    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.textContent = options.confirmText;
    confirmBtn.className = 'modern-btn primary';

    const cleanup = (result: string | string[] | null) => {
      document.removeEventListener('keydown', onKeydown, true);
      overlay.remove();
      resolve(result);
    };

    const getValue = () => {
      const raw = input.value.trim();
      if (!raw) {
        return null;
      }
      if (options.multiple) {
        return raw
          .split(/\r?\n|,/) 
          .map((item) => item.trim())
          .filter(Boolean);
      }
      return raw;
    };

    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        cleanup(null);
      }
      if (event.key === 'Enter' && !event.shiftKey && !options.multiple) {
        event.preventDefault();
        cleanup(getValue());
      }
    };

    cancelBtn.onclick = () => cleanup(null);
    confirmBtn.onclick = () => cleanup(getValue());
    overlay.onclick = (event) => {
      if (event.target === overlay) {
        cleanup(null);
      }
    };

    actions.append(cancelBtn, confirmBtn);
    card.append(title, description, hintEl, input, actions);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    document.addEventListener('keydown', onKeydown, true);
    input.focus();
  });
}

export function openPathDialog(options?: {
  multiple?: boolean;
  directory?: boolean;
  filters?: DialogFilter[];
  defaultPath?: string;
}): Promise<string | string[] | null> {
  return showPathDialog({
    title: options?.directory ? '选择目录' : '选择文件',
    description: options?.multiple ? '请输入一个或多个路径，使用换行或逗号分隔。' : '请输入目标路径。',
    confirmText: '确定',
    placeholder: options?.directory ? '例如: C:/Users/you/Documents' : '例如: C:/Users/you/file.txt',
    defaultValue: options?.defaultPath,
    filters: options?.filters,
    multiple: options?.multiple,
  });
}

export function savePathDialog(options?: {
  filters?: DialogFilter[];
  defaultPath?: string;
}): Promise<string | null> {
  return showPathDialog({
    title: '保存文件',
    description: '请输入要保存到的本地路径。',
    confirmText: '保存',
    placeholder: '例如: C:/Users/you/Downloads/output.txt',
    defaultValue: options?.defaultPath,
    filters: options?.filters,
  }) as Promise<string | null>;
}
