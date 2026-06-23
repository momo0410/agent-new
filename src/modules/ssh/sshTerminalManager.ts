/**
 * SSH 终端管理器
 * 负责管理 SSH 终端组件的生命周期和状态
 */

import { createApp, App } from 'vue'
import SSHTerminal from '../../components/SSHTerminal.vue'

export class SSHTerminalManager {
  private vueApp: App | null = null
  private isInitialized = false
  private containerElement: HTMLElement | null = null
  private isVisible: boolean = false

  /**
   * 初始化 SSH 终端管理器
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) {
      console.log('SSH 终端管理器已初始化')
      return
    }

    console.log('🔧 初始化 SSH 终端管理器...')
    this.isInitialized = true
    console.log('✅ SSH 终端管理器初始化完成')
  }

  /**
   * 挂载 SSH 终端组件（带重试机制，确保容器可用时再挂载）
   */
  mountTerminal(retry = 0): void {
    try {
      // 如果已经挂载且容器仍然存在，不重复挂载（保持会话持久性）
      if (this.isMounted()) {
        console.log('✅ SSH 终端组件已存在，保持现有会话')
        return
      }

      // 查找容器元素
      this.containerElement = document.getElementById('ssh-terminal-container')
      if (!this.containerElement) {
        if (retry < 20) {
          const delay = 50;
          console.warn(`⚠️ 未找到 SSH 终端容器元素，${delay}ms 后重试（第 ${retry + 1}/20 次）`)
          setTimeout(() => this.mountTerminal(retry + 1), delay)
          return
        } else {
          console.error('❌ 未找到 SSH 终端容器元素，多次重试仍失败')
          return
        }
      }

      // 创建 Vue 应用实例
      this.vueApp = createApp(SSHTerminal)

      // 挂载到容器
      this.vueApp.mount(this.containerElement)
      this.isVisible = true

      const childCount = this.containerElement.childElementCount
      console.log(`✅ SSH 终端组件已挂载，容器子元素数量: ${childCount}`)
    } catch (error) {
      console.error('❌ 挂载 SSH 终端组件失败:', error)
    }
  }

  /**
   * 卸载 SSH 终端组件
   */
  unmountTerminal(): void {
    try {
      if (this.vueApp && this.containerElement) {
        this.vueApp.unmount()
        this.vueApp = null

        // 清空容器内容
        this.containerElement.innerHTML = ''

        console.log('✅ SSH 终端组件已卸载')
      }
    } catch (error) {
      console.error('❌ 卸载 SSH 终端组件失败:', error)
    }
  }

  /**
   * 显示 SSH 终端组件（内嵌方案，手动控制显示以保持会话持久性）
   */
  showTerminal(): void {
    const container = this.containerElement || document.getElementById('ssh-terminal-container');
    if (container) {
      (container as HTMLElement).style.display = 'flex';
      (container as HTMLElement).style.flexDirection = 'column';
    } else {
      console.error('❌ 未找到SSH容器，无法显示');
    }

    this.isVisible = true;

    // 触发一次 resize，帮助 xterm 自适应
    setTimeout(() => {
      try { window.dispatchEvent(new Event('resize')); } catch {}
    }, 100); // 稍微延长延迟，确保CSS已生效
  }

  /**
   * 隐藏 SSH 终端组件（内嵌方案，手动控制隐藏以保持会话持久性）
   */
  hideTerminal(): void {
    const container = this.containerElement || document.getElementById('ssh-terminal-container');
    if (container) {
      (container as HTMLElement).style.display = 'none';
    }

    this.isVisible = false;
  }

  /**
   * 检查终端是否已挂载（同时校验 DOM 容器是否存在且包含内容）
   */
  isMounted(): boolean {
    const container = document.getElementById('ssh-terminal-container');
    const hasContent = !!container && container.childElementCount > 0;
    return this.vueApp !== null && !!container && hasContent;
  }

  /**
   * 检查终端是否可见
   */
  isTerminalVisible(): boolean {
    const container = this.containerElement || document.getElementById('ssh-terminal-container');
    if (!container) return false;
    const style = getComputedStyle(container as HTMLElement);
    return style.display !== 'none' && this.isVisible;
  }

  /**
   * 刷新终端组件
   */
  refresh(): void {
    this.unmountTerminal();
    // 延迟一点时间再重新挂载，确保 DOM 清理完成
    setTimeout(() => {
      this.mountTerminal();
    }, 50);
  }

  /**
   * 确保终端可用：若容器被重新渲染或内容丢失则自动重挂载
   */
  ensureTerminalReady(retry = 0): void {
    let container = document.getElementById('ssh-terminal-container');
    if (!container) {
      if (retry < 20) {
        setTimeout(() => this.ensureTerminalReady(retry + 1), 50);
      } else {
        console.error('❌ 未找到 SSH 终端容器（ensureTerminalReady 超过重试次数）');
      }
      return;
    }

    // 检查容器是否为空或Vue应用是否丢失
    const emptyContainer = container.childElementCount === 0 || !container.querySelector('.xterm');
    const noVueApp = this.vueApp === null;
    const containerChanged = this.containerElement !== container;


    if (noVueApp || emptyContainer) {
      // 如果Vue应用存在但容器为空，先卸载再重新挂载
      if (this.vueApp && emptyContainer) {
        this.unmountTerminal();
      }
      this.mountTerminal();
      return;
    }

    // 更新容器引用
    this.containerElement = container;

    if (containerChanged || emptyContainer) {
      this.unmountTerminal();
      setTimeout(() => this.mountTerminal(), 0);
      return;
    }

    if (!this.isTerminalVisible()) {
      this.showTerminal();
    }
  }



  /**
   * 销毁管理器
   */
  destroy(): void {
    this.unmountTerminal()
    this.isInitialized = false
    this.containerElement = null
    console.log('✅ SSH 终端管理器已销毁')
  }
}

// 创建全局实例
export const sshTerminalManager = new SSHTerminalManager()
