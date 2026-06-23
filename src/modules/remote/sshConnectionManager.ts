/**
 * SSH连接管理器
 * 处理实际的SSH连接操作和状态管理
 * 与ssh/connectionManager.ts协同工作
 */

import { SSHConnectionManager as ConfigManager } from '../ssh/connectionManager';
import { invoke } from '../../shims/@tauri-apps/api/core';
import { EventEmitter } from '../utils/EventEmitter';

export interface SSHConnectionInfo {
  id?: string; // 连接配置ID
  host: string;
  port: number;
  username: string;
  connected: boolean;
  lastActivity?: Date;
}

export interface AgentConnectionContext {
  isConnected: boolean;
  host?: string;
  port?: number;
  username?: string;
  connectionId?: string;
}

export class SSHConnectionManager extends EventEmitter<SSHConnectionInfo | null> {
  private connectionStatus: SSHConnectionInfo | null = null;
  private configManager: ConfigManager;

  constructor() {
    super();
    this.configManager = new ConfigManager();
  }

  /**
   * 获取当前连接状态
   */
  getConnectionStatus(): SSHConnectionInfo | null {
    return this.connectionStatus;
  }

  /**
   * 检查是否已连接
   */
  isConnected(): boolean {
    return this.connectionStatus?.connected || false;
  }

  /**
   * 获取当前连接的ID
   */
  getCurrentConnectionId(): string | undefined {
    return this.connectionStatus?.id;
  }

  /**
   * 手动设置连接状态（用于同步主界面连接状态）
   */
  setConnectionStatus(status: SSHConnectionInfo | null): void {
    this.connectionStatus = status;
    this.notifyListeners();
  }

  /**
   * 建立SSH连接
   */
  async connect(host: string, port: number, username: string, password: string): Promise<void> {
    const connectStart = Date.now();
    try {
      console.log('📞 [sshConnectionManager] connect 方法被调用');
      console.log('  参数详情:', {
        host,
        port,
        portType: typeof port,
        portValue: port,
        username,
        passwordLength: password?.length || 0
      });

      // 确保端口是数字类型
      const portNumber = typeof port === 'string' ? parseInt(port, 10) : port;
      if (isNaN(portNumber) || portNumber <= 0 || portNumber > 65535) {
        throw new Error(`无效的端口号: ${port} (类型: ${typeof port})`);
      }

      console.log('  转换后的端口:', portNumber, typeof portNumber);

      // 步骤 1: SSH 连接
      console.log('[SSH connect] step=ssh_connect_direct start');
      const t0 = Date.now();
      await invoke('ssh_connect_direct', {
        host,
        port: portNumber,
        username,
        password
      });
      const t1 = Date.now();
      console.log(`[SSH connect] step=ssh_connect_direct end duration=${t1 - t0} ms`);

      console.log('✅ [sshConnectionManager] Tauri invoke 返回成功');

      // 步骤 2: 更新本地连接状态（暂存）
      const t2 = Date.now();
      this.connectionStatus = {
        host,
        port,
        username,
        connected: true,
        lastActivity: new Date()
      };

      // 步骤 3: 向后端做一次状态校验（非阻断），避免“先通知监听器再触发远程操作”的竞态。
      // 增加短重试，避免后端刚建连时的瞬时状态抖动。
      let verifiedStatus: SSHConnectionInfo | null = null;
      for (let attempt = 1; attempt <= 3; attempt++) {
        verifiedStatus = await this.checkConnectionStatus(false);
        if (verifiedStatus?.connected) break;
        if (attempt < 3) {
          await new Promise(resolve => setTimeout(resolve, 200 * attempt));
        }
      }
      if (!verifiedStatus?.connected) {
        console.warn('[SSH connect] 后端状态校验未通过，主动回收连接并报错');
        const health = await invoke('ssh_get_connection_health').catch(() => null) as any;
        try {
          await invoke('ssh_disconnect_direct');
        } catch {
          // 忽略回收失败
        }
        this.connectionStatus = null;
        const reason = health?.last_note || '后端连接不可用';
        throw new Error(`SSH连接状态校验失败：${reason}`);
      }
      this.connectionStatus = verifiedStatus;

      // 步骤 4: 在校验后统一通知监听器，减少刚连接即触发SFTP/命令探测导致的抖动
      const tNotifyStart = Date.now();
      console.log('[SSH connect] step=notifyListeners start');
      this.notifyListeners();
      console.log(`[SSH connect] step=notifyListeners end duration=${Date.now() - tNotifyStart} ms`);

      console.log(`[SSH connect] step=state_update end duration=${Date.now() - t2} ms`);
      console.log(`[SSH connect] ✅ 连接成功，UI 现已可操作（总耗时 ${Date.now() - connectStart} ms）`);

      // 步骤 5: 后台保存连接配置（不阻塞）
      console.log('[SSH connect] step=saveConnectionConfig start (background)');
      this.saveConnectionConfig(host, port, username, password).catch(err => {
        console.error('[SSH connect] step=saveConnectionConfig error:', err);
      });

      // 步骤 6: 后台初始化终端工作目录（不阻塞）
      console.log('[SSH connect] step=initializeWorkingDirectory scheduled (background)');
      if ((window as any).terminalManager && (window as any).terminalManager.initializeWorkingDirectory) {
        setTimeout(() => {
          console.log('[SSH connect] step=initializeWorkingDirectory start');
          const t3 = Date.now();
          (window as any).terminalManager.initializeWorkingDirectory().then(() => {
            console.log(`[SSH connect] step=initializeWorkingDirectory end duration=${Date.now() - t3} ms`);
          }).catch((err: unknown) => {
            console.error('[SSH connect] step=initializeWorkingDirectory error:', err);
          });
        }, 300); // 从 500ms 减少到 300ms
      }

      console.log(`[SSH connect] ✅ connect() 返回，总耗时 ${Date.now() - connectStart} ms`);

    } catch (error) {
      console.error('SSH连接失败:', error);
      this.connectionStatus = null;
      this.notifyListeners();
      throw error;
    }
  }

  /**
   * 断开SSH连接
   */
  async disconnect(): Promise<void> {
    try {
      if (this.connectionStatus?.connected) {
        await invoke('ssh_disconnect_direct');

        this.connectionStatus = null;
        this.notifyListeners();
      }
    } catch (error) {
      console.error('断开SSH连接失败:', error);
    }
  }

  /**
   * 更新最后活动时间（仅本地更新，不触发全局监听，以避免循环刷新）
   */
  updateLastActivity(): void {
    if (this.connectionStatus) {
      this.connectionStatus.lastActivity = new Date();
      // 不再调用 notifyListeners()，防止触发 UI 刷新循环
    }
  }

  /**
   * 保存连接配置（含加密密码）
   */
  private async saveConnectionConfig(host: string, port: number, username: string, password: string): Promise<void> {
    try {
      // 检查是否已存在相同的连接配置
      const existingConnections = this.configManager.getConnections();
      const existing = existingConnections.find(conn =>
        conn.host === host && conn.port === port && conn.username === username
      );

      let encryptedPassword: string | undefined;
      if (password) {
        try {
          encryptedPassword = await invoke('encrypt_password', { password }) as string;
        } catch (e) {
          console.warn('密码加密失败，将保存无密码配置:', e);
        }
      }

      if (!existing) {
        // 创建新的连接配置
        const connectionName = `${username}@${host}:${port}`;
        await this.configManager.addConnection({
          name: connectionName,
          host,
          port,
          username,
          authType: 'password' as const,
          encryptedPassword,
          tags: ['auto-saved'],
          accounts: [{
            username,
            authType: 'password' as const,
            isDefault: true
          }]
        });
        console.log('✅ 连接配置已自动保存:', connectionName);
      } else if (encryptedPassword && !existing.encryptedPassword) {
        // 更新现有配置的密码
        await this.configManager.updateConnection(existing.id, {
          encryptedPassword
        });
        console.log('✅ 连接配置密码已更新:', existing.name);
      }
    } catch (error) {
      console.error('保存连接配置失败:', error);
      // 不抛出错误，因为这不应该影响连接本身
    }
  }

  /**
   * 通知所有监听器
   */
  private notifyListeners(): void {
    this.emit(this.connectionStatus);
  }

  /**
   * 检查连接状态（从后端获取最新状态）
   */
  async checkConnectionStatus(notify: boolean = true): Promise<SSHConnectionInfo | null> {
    try {
      const status = await invoke('ssh_get_connection_status');
      if (status) {
        const snapshot: SSHConnectionInfo = {
          host: status.host,
          port: status.port,
          username: status.username,
          connected: status.connected,
          lastActivity: new Date(status.last_activity)
        };
        this.connectionStatus = snapshot;
        if (notify) this.notifyListeners();
        return snapshot;
      } else {
        // 在静默校验模式下（notify=false），保留当前本地状态，避免连接建立阶段被瞬时探测结果反向清空。
        if (notify) {
          // 后端返回 null 可能是瞬时会话拥塞导致活性探测失败，不立即清除连接状态。
          // 增加一次重试：等待 500ms 后再次检查，只有连续两次都返回 null 才确认断开。
          await new Promise(resolve => setTimeout(resolve, 500));
          const retryStatus = await invoke('ssh_get_connection_status');
          if (!retryStatus) {
            this.connectionStatus = null;
            this.notifyListeners();
          } else {
            this.connectionStatus = {
              host: retryStatus.host,
              port: retryStatus.port,
              username: retryStatus.username,
              connected: retryStatus.connected,
              lastActivity: new Date(retryStatus.last_activity)
            };
            this.notifyListeners();
            return this.connectionStatus;
          }
        }
        return null;
      }
    } catch (error) {
      console.error('检查SSH连接状态失败:', error);
      return null;
    }
  }

  /**
   * 获取 Agent 所需的连接上下文（轻量增强）
   */
  getAgentConnectionContext(): AgentConnectionContext {
    const status = this.connectionStatus;
    if (!status || !status.connected) {
      return { isConnected: false };
    }
    return {
      isConnected: true,
      host: status.host,
      port: status.port,
      username: status.username,
      connectionId: status.id,
    };
  }
}

// 全局SSH连接管理器实例
export const sshConnectionManager = new SSHConnectionManager();
