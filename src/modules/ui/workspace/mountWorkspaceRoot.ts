import { createApp, type App as VueApp } from 'vue';
import WorkspaceRoot from './WorkspaceRoot.vue';
import type { StateManager } from '../../core/stateManager';
import type { ModernUIRenderer } from '../modernUIRenderer';

let appInstance: VueApp | null = null;
let mountedContainer: HTMLElement | null = null;

export function mountWorkspaceRoot(
  stateManager: StateManager,
  renderer: ModernUIRenderer,
  containerId: string = 'workspace-vue-root'
) {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`WorkspaceRoot: 容器 #${containerId} 未找到`);
    return null;
  }

  const shouldRemount =
    !!appInstance &&
    (!mountedContainer || mountedContainer !== container || !mountedContainer.isConnected);

  try {
    if (appInstance && shouldRemount) {
      appInstance.unmount();
      appInstance = null;
      mountedContainer = null;
    }

    if (appInstance && !shouldRemount) {
      return appInstance;
    }

    appInstance = createApp(WorkspaceRoot, {
      stateManager,
      renderer,
    });
    appInstance.mount(container);
    mountedContainer = container;
    return appInstance;
  } catch (error) {
    console.error('❌ WorkspaceRoot 挂载失败:', error);
    appInstance = null;
    mountedContainer = null;
    return null;
  }
}

export function unmountWorkspaceRoot() {
  if (!appInstance) {
    return;
  }
  try {
    appInstance.unmount();
  } catch (error) {
    console.error('❌ WorkspaceRoot 卸载失败:', error);
  } finally {
    appInstance = null;
    mountedContainer = null;
  }
}
