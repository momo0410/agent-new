/**
 * SSH管理器 - 协调器
 * 负责协调SSH连接管理器和系统信息管理器
 */

import { invoke } from '../../shims/@tauri-apps/api/core';
import { SSHConnectionManager, type SSHConnection } from './connectionManager';
import { SystemInfoManager, type SystemInfo } from '../system/systemInfoManager';
import { generateId } from '../utils/idGenerator';

export type { SystemInfo };

export interface SSHCommand {
  id: string;
  name: string;
  command: string;
  description: string;
  category: string;
  favorite: boolean;
}

export class SSHManager {
  private connectionManager: SSHConnectionManager;
  private systemInfoManager: SystemInfoManager;
  private commands: SSHCommand[] = [];

  constructor() {
    this.connectionManager = new SSHConnectionManager();
    this.systemInfoManager = new SystemInfoManager();
    this.initializeDefaultCommands();
  }

  // ===== 连接管理代理方法 =====

  /**
   * 获取所有SSH连接
   */
  getConnections(): SSHConnection[] {
    return this.connectionManager.getConnections();
  }

  /**
   * 获取单个SSH连接
   */
  getConnection(id: string): SSHConnection | undefined {
    return this.connectionManager.getConnection(id);
  }

  /**
   * 添加SSH连接
   */
  async addConnection(connection: Omit<SSHConnection, 'id' | 'isConnected' | 'lastConnected'>): Promise<SSHConnection> {
    return this.connectionManager.addConnection(connection);
  }

  /**
   * 更新SSH连接
   */
  async updateConnection(id: string, updates: Partial<SSHConnection>): Promise<SSHConnection> {
    return this.connectionManager.updateConnection(id, updates);
  }

  /**
   * 删除SSH连接
   */
  async deleteConnection(id: string): Promise<void> {
    return this.connectionManager.deleteConnection(id);
  }

  /**
   * 连接到服务器
   */
  async connectToServer(id: string): Promise<void> {
    // 委托给连接管理器处理具体的连接逻辑和状态更新
    await this.connectionManager.connect(id);

    // 连接成功后立即获取轻量系统摘要信息
    try {
      await this.systemInfoManager.fetchSystemSummary();
      
      // 启动自动更新
      this.systemInfoManager.startAutoUpdate(30000, false); 
    } catch (error) {
    }
  }

  /**
   * 断开服务器连接
   */
  async disconnectFromServer(_id: string): Promise<void> {
    // 停止系统信息自动更新
    this.systemInfoManager.stopAutoUpdate();
    
    // 委托给连接管理器处理具体的断开逻辑和状态更新
    await this.connectionManager.disconnect();
  }

  /**
   * 连接到SSH服务器 (兼容旧接口或特定场景)
   */
  async connect(id: string): Promise<void> {
    return this.connectToServer(id);
  }

  /**
   * 断开SSH连接 (兼容旧接口或特定场景)
   */
  async disconnect(): Promise<void> {
    return this.disconnectFromServer(''); // ID在此处可能不被需要，取决于connectionManager实现
  }

  /**
   * 获取当前活动连接
   */
  getActiveConnection(): SSHConnection | undefined {
    return this.connectionManager.getActiveConnection();
  }

  /**
   * 检查是否已连接
   */
  isConnected(): boolean {
    return this.connectionManager.isConnected();
  }

  /**
   * 测试连接
   */
  async testConnection(connection: Omit<SSHConnection, 'id' | 'isConnected' | 'lastConnected'>): Promise<boolean> {
    return this.connectionManager.testConnection(connection);
  }

  // ===== 系统信息代理方法 =====

  /**
   * 获取系统信息（全量，包含详细进程/网络/服务等）
   */
  async fetchSystemInfo(): Promise<SystemInfo> {
    return this.systemInfoManager.fetchSystemInfo();
  }

  /**
   * 获取系统摘要信息（轻量版，仅基础指标）
   * 用于连接成功后快速初始化，避免全量加载
   */
  async fetchSystemSummary(forceRefresh = false): Promise<SystemInfo> {
    const status = await invoke('ssh_get_connection_status').catch(() => null) as any;
    if (!status?.connected) {
      throw new Error('没有活动的 SSH 连接');
    }
    return this.systemInfoManager.fetchSystemSummary(forceRefresh);
  }

  /**
   * 获取当前系统信息
   */
  getSystemInfo(): SystemInfo | undefined {
    return this.systemInfoManager.getSystemInfo();
  }

  /**
   * 按 tab 懒加载详细系统信息（仅获取指定 tab 的数据）
   */
  async fetchTabDetail(tabId: string, forceRefresh = false): Promise<any> {
    const status = await invoke('ssh_get_connection_status').catch(() => null) as any;
    if (!status?.connected) {
      throw new Error('没有活动的 SSH 连接');
    }
    return this.systemInfoManager.fetchTabDetail(tabId, forceRefresh);
  }

  /**
   * 获取当前已缓存的详细系统信息摘要（合并 tabCache + 旧缓存）
   */
  getCachedDetailedInfo(): any {
    return this.systemInfoManager.getCachedDetailedInfo();
  }

  /**
   * 开始自动更新系统信息
   */
  startSystemInfoAutoUpdate(intervalMs: number = 30000): void {
    this.systemInfoManager.startAutoUpdate(intervalMs);
  }

  /**
   * 停止自动更新系统信息
   */
  stopSystemInfoAutoUpdate(): void {
    this.systemInfoManager.stopAutoUpdate();
  }

  // ===== 命令管理 =====

  /**
   * 执行SSH命令
   */
  async executeCommand(command: string): Promise<string> {
    if (!this.isConnected()) {
      throw new Error('没有活动的SSH连接');
    }

    try {
      const result = await invoke('ssh_execute_command', { command });
      return result as string;
    } catch (error) {
      console.error(`❌ 命令执行失败: ${command}`, error);
      throw new Error(`命令执行失败: ${error}`);
    }
  }

  /**
   * 获取所有SSH命令
   */
  getCommands(): SSHCommand[] {
    return [...this.commands];
  }

  /**
   * 初始化默认命令
   */
  private initializeDefaultCommands(): void {
    const defaultCommands: Omit<SSHCommand, 'id'>[] = [
      {
        name: '查看系统信息',
        command: 'uname -a',
        description: '显示系统内核信息',
        category: '系统信息',
        favorite: true
      },
      {
        name: '查看内存使用',
        command: 'free -h',
        description: '显示内存使用情况',
        category: '系统监控',
        favorite: true
      },
      {
        name: '查看磁盘使用',
        command: 'df -h',
        description: '显示磁盘使用情况',
        category: '系统监控',
        favorite: true
      }
    ];

    this.commands = defaultCommands.map(cmd => ({
      ...cmd,
      id: generateId()
    }));

  }

  /**
   * 清理资源
   */
  destroy(): void {
    this.systemInfoManager.destroy();
  }
}
