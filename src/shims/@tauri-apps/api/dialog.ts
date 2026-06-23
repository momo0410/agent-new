/**
 * @tauri-apps/api/dialog shim
 * 优先走 Python 后端原生文件对话框，失败时回退到前端自定义路径输入框。
 */

import pythonApi from '../../../config/python-api.config';
import { openPathDialog, savePathDialog } from '../../../modules/ui/systemDialog';

interface DialogFilter {
  name?: string;
  extensions?: string[];
}

interface OpenDialogOptions {
  multiple?: boolean;
  directory?: boolean;
  filters?: DialogFilter[];
  defaultPath?: string;
}

interface SaveDialogOptions {
  filters?: DialogFilter[];
  defaultPath?: string;
}

export async function open(options?: OpenDialogOptions): Promise<string | string[] | null> {
  try {
    const result = await pythonApi.openDialog({
      multiple: options?.multiple,
      directory: options?.directory,
      filters: options?.filters,
      defaultPath: options?.defaultPath,
    });
    return result.path ?? null;
  } catch (error) {
    console.warn('[dialog-shim] 后端文件对话框不可用，回退到前端实现:', error);
    return openPathDialog(options);
  }
}

export async function save(options?: SaveDialogOptions): Promise<string | null> {
  try {
    const result = await pythonApi.saveDialog({
      filters: options?.filters,
      defaultPath: options?.defaultPath,
    });
    return result.path ?? null;
  } catch (error) {
    console.warn('[dialog-shim] 后端保存对话框不可用，回退到前端实现:', error);
    return savePathDialog(options);
  }
}
