/**
 * 快速检测管理器
 * 负责执行安全和性能检测，管理检测状态和历史记录
 */

import { invoke } from '../../shims/@tauri-apps/api/core';
import { aiService } from '../ai/aiService';
import {
  CheckOne,
  CloseOne,
  Time,
  Tips,
  Robot,
  ListBottom,
  Caution,
  Stopwatch,
  Code
} from '@icon-park/svg';

// 评分规则常量
const SCORING_RULES = {
  CRITICAL_DEDUCTION: 40,
  HIGH_DEDUCTION: 20,
  MEDIUM_DEDUCTION: 10,
  LOW_DEDUCTION: 5
};

// 检测项目类型
export interface DetectionItem {
  id: string;
  name: string;
  description: string;
  category: 'security' | 'performance';
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: DetectionResult;
}

// 检测结果
export interface DetectionResult {
  passed: boolean;
  score: number; // 0-100
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  findings: Finding[];
  duration: number; // 执行时间（毫秒）
  timestamp: Date;
  rawOutput?: any; // 原始命令返回结果
}

// 检测发现
export interface Finding {
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  recommendation?: string;
  details?: any;
}

// 检测报告
export interface DetectionReport {
  id: string;
  timestamp: Date;
  server: string;
  overallScore: number;
  totalDuration: number;
  items: DetectionItem[];
  summary: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    info: number;
  };
}

export class QuickDetectionManager {
  private currentReport: DetectionReport | null = null;
  private detectionHistory: DetectionReport[] = [];
  private isRunning: boolean = false;
  private progressCallback?: (progress: number, current: string) => void;

  constructor() {
    this.loadHistory();
  }

  /**
   * 开始全面扫描
   */
  async startFullScan(selectedIds?: string[]): Promise<DetectionReport> {
    if (this.isRunning) {
      throw new Error('检测已在进行中');
    }

    if (!(await this.hasActiveSshConnection())) {
      alert('未检测到活动的 SSH 连接，请先连接目标主机后再执行快速检测。');
      return {
        id: this.generateReportId(),
        timestamp: new Date(),
        server: '未连接服务器',
        overallScore: 0,
        totalDuration: 0,
        items: [],
        summary: {
          critical: 0,
          high: 0,
          medium: 0,
          low: 0,
          info: 0
        }
      };
    }

    this.isRunning = true;
    this.showProgressPanel();

    // 获取选中的检测项
    const itemsToRun = selectedIds || this.getAllCheckIds();
    const totalItems = itemsToRun.length;
    let completedItems = 0;

    // 初始化报告
    this.currentReport = {
      id: this.generateReportId(),
      timestamp: new Date(),
      server: this.getCurrentServerInfo(),
      overallScore: 0,
      totalDuration: 0,
      items: [],
      summary: {
        critical: 0,
        high: 0,
        medium: 0,
        low: 0,
        info: 0
      }
    };

    const startTime = Date.now();

    try {
      // 逐个执行检测
      for (const itemId of itemsToRun) {
        this.updateProgress(
          (completedItems / totalItems) * 100,
          `正在执行: ${this.getCheckName(itemId)}`
        );

        this.updateCheckStatus(itemId, 'running');

        try {
          const result = await this.executeDetection(itemId);
          this.updateCheckStatus(itemId, 'completed', result);

          // 添加到报告
          this.currentReport.items.push({
            id: itemId,
            name: this.getCheckName(itemId),
            description: this.getCheckDescription(itemId),
            category: this.getCheckCategory(itemId),
            status: 'completed',
            result
          });

          // 更新摘要
          if (result.findings.length > 0) {
            result.findings.forEach(finding => {
              this.currentReport!.summary[finding.severity]++;
            });
          }
        } catch (error) {
          console.error(`检测失败: ${itemId}`, error);
          this.updateCheckStatus(itemId, 'failed');

          this.currentReport.items.push({
            id: itemId,
            name: this.getCheckName(itemId),
            description: this.getCheckDescription(itemId),
            category: this.getCheckCategory(itemId),
            status: 'failed'
          });
        }

        completedItems++;
        this.updateProgress((completedItems / totalItems) * 100, '');
      }

      // 计算总体评分
      this.currentReport.totalDuration = Date.now() - startTime;
      this.currentReport.overallScore = this.calculateOverallScore(this.currentReport);

      // 显示结果
      this.showSummaryPanel(this.currentReport);

      // 保存到历史
      this.saveToHistory(this.currentReport);

      return this.currentReport;
    } finally {
      this.isRunning = false;
      this.hideProgressPanel();
    }
  }

  /**
   * 执行单个检测
   */
  private async executeDetection(itemId: string): Promise<DetectionResult> {
    const startTime = Date.now();
    let result: DetectionResult;

    switch (itemId) {
      case 'port-scan':
        result = await this.runPortScan();
        break;
      case 'user-audit':
        result = await this.runUserAudit();
        break;
      case 'backdoor-scan':
        result = await this.runBackdoorScan();
        break;
      case 'process-analysis':
        result = await this.runProcessAnalysis();
        break;
      case 'file-permission':
        result = await this.runFilePermissionCheck();
        break;
      case 'ssh-audit':
        result = await this.runSSHAudit();
        break;
      case 'log-analysis':
        result = await this.runLogAnalysis();
        break;
      case 'firewall-check':
        result = await this.runFirewallCheck();
        break;

      // 账号与认证安全
      case 'password-policy':
        result = await this.runPasswordPolicyCheck();
        break;
      case 'sudo-audit':
        result = await this.runSudoAudit();
        break;
      case 'pam-config':
        result = await this.runPAMConfigCheck();
        break;
      case 'account-lockout':
        result = await this.runAccountLockoutCheck();
        break;

      // 系统加固
      case 'selinux-status':
        result = await this.runSELinuxStatusCheck();
        break;
      case 'kernel-params':
        result = await this.runKernelParamsCheck();
        break;
      case 'system-updates':
        result = await this.runSystemUpdatesCheck();
        break;

      // 服务与进程
      case 'unnecessary-services':
        result = await this.runUnnecessaryServicesCheck();
        break;
      case 'auto-start-services':
        result = await this.runAutoStartServicesCheck();
        break;

      // 审计与日志
      case 'audit-config':
        result = await this.runAuditConfigCheck();
        break;
      case 'history-audit':
        result = await this.runHistoryAudit();
        break;

      // 网络与时间
      case 'ntp-config':
        result = await this.runNTPConfigCheck();
        break;
      case 'dns-config':
        result = await this.runDNSConfigCheck();
        break;

      // 性能检测
      case 'cpu-test':
        result = await this.runCPUTest();
        break;
      case 'memory-test':
        result = await this.runMemoryTest();
        break;
      case 'disk-test':
        result = await this.runDiskTest();
        break;
      case 'network-test':
        result = await this.runNetworkTest();
        break;
      default:
        throw new Error(`未知的检测项: ${itemId}`);
    }

    result.duration = Date.now() - startTime;
    result.timestamp = new Date();

    return result;
  }

  /**
   * 端口扫描
   */
  private async runPortScan(): Promise<DetectionResult> {
    try {
      const scanResult = await invoke('detect_port_scan') as any;

      const findings: Finding[] = [];
      let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';
      const openPorts = Array.isArray(scanResult?.open_ports)
        ? scanResult.open_ports
        : (Array.isArray(scanResult?.ports) ? scanResult.ports : []);

      // 分析开放端口
      if (openPorts.length > 0) {
        openPorts.forEach((port: any) => {
          const portNo = typeof port?.port === 'number'
            ? port.port
            : parseInt(String(port?.port ?? ''), 10);
          if (!Number.isNaN(portNo) && this.isHighRiskPort(portNo)) {
            findings.push({
              title: `高危端口开放: ${portNo}`,
              description: `端口 ${portNo} (${port?.service || '未知服务'}) 处于开放状态`,
              severity: 'high',
              recommendation: '检查该端口的服务配置，确认是否需要对外开放',
              details: port
            });
            severity = 'high';
          }
        });
      }

      return {
        passed: findings.length === 0,
        score: this.calculateScore(findings),
        severity,
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: scanResult
      };
    } catch (error) {
      console.error('端口扫描失败:', error);
      return this.createErrorResult('端口扫描失败', error);
    }
  }

  /**
   * 用户权限审计
   */
  private async runUserAudit(): Promise<DetectionResult> {
    try {
      const auditResult = await invoke('detect_user_audit') as any;

      const findings: Finding[] = [];
      let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';

      // 检查 root 用户
      if (auditResult.root_users && auditResult.root_users.length > 1) {
        findings.push({
          title: '存在多个 root 权限用户',
          description: `发现 ${auditResult.root_users.length} 个具有 root 权限的用户`,
          severity: 'medium',
          recommendation: '审核 root 权限用户列表，移除不必要的高权限账号',
          details: auditResult.root_users
        });
        severity = 'medium';
      }

      // 检查空密码账号
      if (auditResult.empty_password_users && auditResult.empty_password_users.length > 0) {
        const userList = auditResult.empty_password_users.slice(0, 5).join(', ');
        const more = auditResult.empty_password_users.length > 5 ? ` 等 ${auditResult.empty_password_users.length} 个账号` : '';
        findings.push({
          title: '存在空密码账号',
          description: `发现空密码账号: ${userList}${more}`,
          severity: 'critical',
          recommendation: '立即为这些账号设置强密码或禁用账号',
          details: auditResult.empty_password_users
        });
        severity = 'critical';
      }

      // 检查最近创建的用户
      if (auditResult.recent_users && auditResult.recent_users.length > 0) {
        const userList = auditResult.recent_users.slice(0, 3).map((u: any) => u.username || u).join(', ');
        const more = auditResult.recent_users.length > 3 ? ` 等 ${auditResult.recent_users.length} 个` : '';
        findings.push({
          title: '最近创建的用户',
          description: `最近 7 天内创建的新用户: ${userList}${more}`,
          severity: 'info',
          recommendation: '审核这些新用户是否为授权创建',
          details: auditResult.recent_users
        });
      }

      return {
        passed: findings.filter(f => f.severity === 'critical' || f.severity === 'high').length === 0,
        score: this.calculateScore(findings),
        severity,
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: auditResult
      };
    } catch (error) {
      console.error('用户审计失败:', error);
      return this.createErrorResult('用户审计失败');
    }
  }

  /**
   * 后门检测
   */
  private async runBackdoorScan(): Promise<DetectionResult> {
    try {
      const scanResult = await invoke('detect_backdoor') as any;

      const findings: Finding[] = [];
      let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';

      // Python 后端返回 suspicious_files/risk_level/details
      const suspiciousFiles: any[] = Array.isArray(scanResult.suspicious_files)
        ? scanResult.suspicious_files
        : [];
      if (suspiciousFiles.length > 0) {
        const sample = suspiciousFiles
          .slice(0, 3)
          .map((f: any) => typeof f === 'string' ? f : (f.path || f.file || JSON.stringify(f)))
          .join(', ');
        const more = suspiciousFiles.length > 3 ? ` 等 ${suspiciousFiles.length} 个` : '';
        findings.push({
          title: '发现可疑后门痕迹',
          description: `可疑项: ${sample}${more}`,
          severity: scanResult.risk_level === 'high' ? 'high' : 'medium',
          recommendation: '逐项核查来源，移除未授权任务/启动项/密钥',
          details: suspiciousFiles
        });
        severity = scanResult.risk_level === 'high' ? 'high' : 'medium';
      }

      return {
        passed: findings.filter(f => f.severity === 'critical' || f.severity === 'high').length === 0,
        score: this.calculateScore(findings),
        severity,
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: scanResult
      };
    } catch (error) {
      console.error('后门检测失败:', error);
      return this.createErrorResult('后门检测失败');
    }
  }

  /**
   * 进程分析
   */
  private async runProcessAnalysis(): Promise<DetectionResult> {
    try {
      const analysisResult = await invoke('detect_process_analysis') as any;

      const findings: Finding[] = [];
      let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';

      // 检查可疑进程
      if (analysisResult.suspicious_processes && analysisResult.suspicious_processes.length > 0) {
        const processList = analysisResult.suspicious_processes.slice(0, 3).map((p: any) => {
          const name = p.name || p.command || p.cmd || JSON.stringify(p);
          return name.split(' ')[0].split('/').pop();
        }).join(', ');
        const more = analysisResult.suspicious_processes.length > 3 ? ` 等 ${analysisResult.suspicious_processes.length} 个` : '';
        findings.push({
          title: '发现可疑进程',
          description: `可疑进程: ${processList}${more}`,
          severity: 'high',
          recommendation: '调查这些进程的来源和用途',
          details: analysisResult.suspicious_processes
        });
        severity = 'high';
      }

      // 检查高资源占用进程
      if (analysisResult.high_resource_processes && analysisResult.high_resource_processes.length > 0) {
        findings.push({
          title: '高资源占用进程',
          description: `发现 ${analysisResult.high_resource_processes.length} 个高资源占用进程`,
          severity: 'medium',
          recommendation: '检查这些进程是否正常',
          details: analysisResult.high_resource_processes
        });
      }

      return {
        passed: findings.filter(f => f.severity === 'critical' || f.severity === 'high').length === 0,
        score: this.calculateScore(findings),
        severity,
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: analysisResult
      };
    } catch (error) {
      console.error('进程分析失败:', error);
      return this.createErrorResult('进程分析失败');
    }
  }

  /**
   * 文件权限检测
   */
  private async runFilePermissionCheck(): Promise<DetectionResult> {
    try {
      const checkResult = await invoke('detect_file_permission') as any;

      const findings: Finding[] = [];
      let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';

      // Python 后端返回 risky_files/risk_level/details
      const riskyFiles: any[] = Array.isArray(checkResult.risky_files)
        ? checkResult.risky_files
        : [];
      if (riskyFiles.length > 0) {
        findings.push({
          title: '文件权限风险',
          description: `发现 ${riskyFiles.length} 条权限风险项`,
          severity: checkResult.risk_level === 'high' ? 'high' : 'medium',
          recommendation: '核查并收紧敏感文件权限，移除不必要的 SUID',
          details: riskyFiles
        });
        severity = checkResult.risk_level === 'high' ? 'high' : 'medium';
      }

      return {
        passed: findings.filter(f => f.severity === 'critical' || f.severity === 'high').length === 0,
        score: this.calculateScore(findings),
        severity,
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: checkResult
      };
    } catch (error) {
      console.error('文件权限检测失败:', error);
      return this.createErrorResult('文件权限检测失败');
    }
  }

  /**
   * SSH 安全审计
   */
  private async runSSHAudit(): Promise<DetectionResult> {
    try {
      const auditResult = await invoke('detect_ssh_audit') as any;

      const findings: Finding[] = [];
      let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';

      // 检查 root 登录
      if (auditResult.permit_root_login) {
        findings.push({
          title: 'SSH 允许 root 登录',
          description: 'SSH 配置允许 root 用户直接登录',
          severity: 'high',
          recommendation: '建议禁用 root 直接登录，使用普通用户登录后 su 或 sudo',
          details: { config: 'PermitRootLogin yes' }
        });
        severity = 'high';
      }

      // 检查密码认证
      if (auditResult.password_authentication) {
        findings.push({
          title: 'SSH 允许密码认证',
          description: 'SSH 配置允许使用密码认证',
          severity: 'medium',
          recommendation: '建议使用密钥认证替代密码认证',
          details: { config: 'PasswordAuthentication yes' }
        });
        severity = severity === 'high' ? 'high' : 'medium';
      }

      // 检查默认端口
      if (auditResult.default_port) {
        findings.push({
          title: 'SSH 使用默认端口',
          description: 'SSH 服务使用默认的 22 端口',
          severity: 'low',
          recommendation: '建议修改 SSH 端口以减少自动化扫描攻击',
          details: { port: 22 }
        });
      }

      return {
        passed: findings.filter(f => f.severity === 'critical' || f.severity === 'high').length === 0,
        score: this.calculateScore(findings),
        severity,
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: auditResult
      };
    } catch (error) {
      console.error('SSH 审计失败:', error);
      return this.createErrorResult('SSH 审计失败');
    }
  }

  /**
   * 日志分析
   */
  private async runLogAnalysis(): Promise<DetectionResult> {
    try {
      const analysisResult = await invoke('detect_log_analysis') as any;

      const findings: Finding[] = [];
      let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';

      // 检查暴力破解
      if (analysisResult.brute_force_attempts && analysisResult.brute_force_attempts > 0) {
        findings.push({
          title: '检测到暴力破解尝试',
          description: `检测到 ${analysisResult.brute_force_attempts} 次暴力破解尝试`,
          severity: 'high',
          recommendation: '配置 fail2ban 或类似工具防止暴力破解',
          details: analysisResult.brute_force_details
        });
        severity = 'high';
      }

      // 检查异常登录
      if (analysisResult.abnormal_logins && analysisResult.abnormal_logins.length > 0) {
        findings.push({
          title: '发现异常登录记录',
          description: `发现 ${analysisResult.abnormal_logins.length} 条异常登录记录`,
          severity: 'medium',
          recommendation: '审核这些登录记录，确认是否为授权访问',
          details: analysisResult.abnormal_logins
        });
        severity = severity === 'high' ? 'high' : 'medium';
      }

      return {
        passed: findings.filter(f => f.severity === 'critical' || f.severity === 'high').length === 0,
        score: this.calculateScore(findings),
        severity,
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: analysisResult
      };
    } catch (error) {
      console.error('日志分析失败:', error);
      return this.createErrorResult('日志分析失败');
    }
  }

  /**
   * 防火墙检查
   */
  private async runFirewallCheck(): Promise<DetectionResult> {
    try {
      const checkResult = await invoke('detect_firewall_check') as any;

      const findings: Finding[] = [];
      let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';

      // 检查防火墙状态
      if (!checkResult.firewall_active) {
        findings.push({
          title: '防火墙未启用',
          description: '系统防火墙未启用或未运行',
          severity: 'high',
          recommendation: '启用并配置防火墙以保护系统',
          details: checkResult
        });
        severity = 'high';
      } else {
        // 检查高危规则
        if (checkResult.risky_rules && checkResult.risky_rules.length > 0) {
          findings.push({
            title: '存在高危防火墙规则',
            description: `发现 ${checkResult.risky_rules.length} 条高危防火墙规则`,
            severity: 'medium',
            recommendation: '审核这些规则，确保符合安全策略',
            details: checkResult.risky_rules
          });
          severity = 'medium';
        }
      }

      return {
        passed: findings.filter(f => f.severity === 'critical' || f.severity === 'high').length === 0,
        score: this.calculateScore(findings),
        severity,
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: checkResult
      };
    } catch (error) {
      console.error('防火墙检查失败:', error);
      return this.createErrorResult('防火墙检查失败');
    }
  }

  /**
   * CPU 测试
   */
  private async runCPUTest(): Promise<DetectionResult> {
    try {
      const testResult = await invoke('detect_cpu_test') as any;

      const findings: Finding[] = [];

      const cpuText = testResult.cpu_info || testResult.details || '未获取到 CPU 信息';
      findings.push({
        title: 'CPU 性能测试',
        description: `CPU 使用率: ${testResult.cpu_usage ?? 0}%`,
        severity: 'info',
        details: cpuText
      });

      return {
        passed: true,
        score: 100,
        severity: 'info',
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: testResult
      };
    } catch (error) {
      console.error('CPU 测试失败:', error);
      return this.createErrorResult('CPU 测试失败');
    }
  }

  /**
   * 内存测试
   */
  private async runMemoryTest(): Promise<DetectionResult> {
    try {
      const testResult = await invoke('detect_memory_test') as any;

      const findings: Finding[] = [];

      findings.push({
        title: '内存性能测试',
        description: `总内存: ${testResult.total || 'N/A'}, 已用: ${testResult.used || 'N/A'}, 空闲: ${testResult.free || 'N/A'}`,
        severity: 'info',
        details: testResult
      });

      return {
        passed: true,
        score: 100,
        severity: 'info',
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: testResult
      };
    } catch (error) {
      console.error('内存测试失败:', error);
      return this.createErrorResult('内存测试失败');
    }
  }

  /**
   * 磁盘测试
   */
  private async runDiskTest(): Promise<DetectionResult> {
    try {
      const testResult = await invoke('detect_disk_test') as any;

      const findings: Finding[] = [];

      const disks: any[] = Array.isArray(testResult.disks) ? testResult.disks : [];
      findings.push({
        title: '磁盘 I/O 测试',
        description: `磁盘分区数: ${disks.length}`,
        severity: 'info',
        details: testResult
      });

      return {
        passed: true,
        score: 100,
        severity: 'info',
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: testResult
      };
    } catch (error) {
      console.error('磁盘测试失败:', error);
      return this.createErrorResult('磁盘测试失败');
    }
  }

  /**
   * 网络测试
   */
  private async runNetworkTest(): Promise<DetectionResult> {
    try {
      const testResult = await invoke('detect_network_test') as any;

      const findings: Finding[] = [];

      const interfaces: any[] = Array.isArray(testResult.interfaces) ? testResult.interfaces : [];
      const connections: any[] = Array.isArray(testResult.connections) ? testResult.connections : [];
      findings.push({
        title: '网络性能测试',
        description: `网卡信息条数: ${interfaces.length}, 连接信息条数: ${connections.length}`,
        severity: 'info',
        details: testResult
      });

      return {
        passed: true,
        score: 100,
        severity: 'info',
        findings,
        duration: 0,
        timestamp: new Date(),
        rawOutput: testResult
      };
    } catch (error) {
      console.error('网络测试失败:', error);
      return this.createErrorResult('网络测试失败');
    }
  }

  /**
   * 密码策略检查
   */
  private async runPasswordPolicyCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_password_policy') as any;
      return this.processBasicDetectionResult(result, '密码策略');
    } catch (error) {
      console.error('密码策略检查失败:', error);
      return this.createErrorResult('密码策略检查失败');
    }
  }

  /**
   * Sudo 配置审计
   */
  private async runSudoAudit(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_sudo_config') as any;
      return this.processBasicDetectionResult(result, 'Sudo 配置');
    } catch (error) {
      console.error('Sudo 审计失败:', error);
      return this.createErrorResult('Sudo 审计失败');
    }
  }

  /**
   * PAM 配置检查
   */
  private async runPAMConfigCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_pam_config') as any;
      return this.processBasicDetectionResult(result, 'PAM 配置');
    } catch (error) {
      console.error('PAM 配置检查失败:', error);
      return this.createErrorResult('PAM 配置检查失败');
    }
  }

  /**
   * 账号锁定策略检查
   */
  private async runAccountLockoutCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_account_lockout') as any;
      return this.processBasicDetectionResult(result, '账号锁定策略');
    } catch (error) {
      console.error('账号锁定策略检查失败:', error);
      return this.createErrorResult('账号锁定策略检查失败');
    }
  }

  /**
   * SELinux/AppArmor 状态检查
   */
  private async runSELinuxStatusCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_selinux_status') as any;
      return this.processBasicDetectionResult(result, 'SELinux/AppArmor');
    } catch (error) {
      console.error('SELinux 状态检查失败:', error);
      return this.createErrorResult('SELinux 状态检查失败');
    }
  }

  /**
   * 内核参数检查
   */
  private async runKernelParamsCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_kernel_params') as any;
      return this.processBasicDetectionResult(result, '内核参数');
    } catch (error) {
      console.error('内核参数检查失败:', error);
      return this.createErrorResult('内核参数检查失败');
    }
  }

  /**
   * 系统补丁状态检查
   */
  private async runSystemUpdatesCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_system_updates') as any;
      return this.processBasicDetectionResult(result, '系统补丁');
    } catch (error) {
      console.error('系统补丁检查失败:', error);
      return this.createErrorResult('系统补丁检查失败');
    }
  }

  /**
   * 不必要服务检查
   */
  private async runUnnecessaryServicesCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_unnecessary_services') as any;
      return this.processBasicDetectionResult(result, '不必要服务');
    } catch (error) {
      console.error('不必要服务检查失败:', error);
      return this.createErrorResult('不必要服务检查失败');
    }
  }

  /**
   * 自启动服务审计
   */
  private async runAutoStartServicesCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_auto_start_services') as any;
      return this.processBasicDetectionResult(result, '自启动服务');
    } catch (error) {
      console.error('自启动服务审计失败:', error);
      return this.createErrorResult('自启动服务审计失败');
    }
  }

  /**
   * 审计配置检查
   */
  private async runAuditConfigCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_audit_config') as any;
      return this.processBasicDetectionResult(result, '审计配置');
    } catch (error) {
      console.error('审计配置检查失败:', error);
      return this.createErrorResult('审计配置检查失败');
    }
  }

  /**
   * 历史命令审计
   */
  private async runHistoryAudit(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_history_audit') as any;
      return this.processBasicDetectionResult(result, '历史命令');
    } catch (error) {
      console.error('历史命令审计失败:', error);
      return this.createErrorResult('历史命令审计失败');
    }
  }

  /**
   * NTP 配置检查
   */
  private async runNTPConfigCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_ntp_config') as any;
      return this.processBasicDetectionResult(result, 'NTP 配置');
    } catch (error) {
      console.error('NTP 配置检查失败:', error);
      return this.createErrorResult('NTP 配置检查失败');
    }
  }

  /**
   * DNS 配置检查
   */
  private async runDNSConfigCheck(): Promise<DetectionResult> {
    try {
      const result = await invoke('detect_dns_config') as any;
      return this.processBasicDetectionResult(result, 'DNS 配置');
    } catch (error) {
      console.error('DNS 配置检查失败:', error);
      return this.createErrorResult('DNS 配置检查失败');
    }
  }

  /**
   * 处理基础检测结果的通用方法
   */
  private processBasicDetectionResult(result: any, name: string): DetectionResult {
    const findings: Finding[] = [];
    let score = 100;

    const issues = Array.isArray(result.issues) ? result.issues : [];
    const items = Array.isArray(result.items) ? result.items : [];
    const normalizedIssues = issues.length > 0
      ? issues
      : items.map((item: any) => ({
          title: `${name}配置项`,
          description: item.line || item.status || JSON.stringify(item),
          severity: result.status === 'pass' ? 'info' : (result.risk_level || 'medium'),
          recommendation: `请检查${name}配置`,
          details: item
        }));

    if (normalizedIssues.length > 0 && result.status !== 'pass') {
      normalizedIssues.forEach((issue: any) => {
        findings.push({
          title: issue.title || `${name}问题`,
          description: issue.description || issue.message || '发现配置问题',
          severity: issue.severity || 'medium',
          recommendation: issue.recommendation || `请检查${name}`,
          details: issue.details
        });

        // 根据严重程度扣分
        switch (issue.severity) {
          case 'critical':
            score -= SCORING_RULES.CRITICAL_DEDUCTION;
            break;
          case 'high':
            score -= SCORING_RULES.HIGH_DEDUCTION;
            break;
          case 'medium':
            score -= SCORING_RULES.MEDIUM_DEDUCTION;
            break;
          case 'low':
            score -= SCORING_RULES.LOW_DEDUCTION;
            break;
        }
      });
    }

    return {
      passed: findings.length === 0,
      score: Math.max(0, score),
      severity: findings.length > 0 ? findings[0].severity : 'info',
      findings,
      duration: 0,
      timestamp: new Date(),
      rawOutput: result
    };
  }

  /**
   * 工具方法：判断是否为高危端口
   */
  private isHighRiskPort(port: number): boolean {
    const highRiskPorts = [
      3306,  // MySQL
      5432,  // PostgreSQL
      6379,  // Redis
      27017, // MongoDB
      9200,  // Elasticsearch
      2375,  // Docker (未加密)
      2376,  // Docker (TLS)
      5984,  // CouchDB
      7001,  // Cassandra
      8086   // InfluxDB
    ];
    return highRiskPorts.includes(port);
  }

  /**
   * 工具方法：计算评分
   */
  private calculateScore(findings: Finding[]): number {
    if (findings.length === 0) return 100;

    let deduction = 0;
    findings.forEach(finding => {
      switch (finding.severity) {
        case 'critical':
          deduction += SCORING_RULES.CRITICAL_DEDUCTION;
          break;
        case 'high':
          deduction += SCORING_RULES.HIGH_DEDUCTION;
          break;
        case 'medium':
          deduction += SCORING_RULES.MEDIUM_DEDUCTION;
          break;
        case 'low':
          deduction += SCORING_RULES.LOW_DEDUCTION;
          break;
        case 'info':
          deduction += 0;
          break;
      }
    });

    return Math.max(0, 100 - deduction);
  }

  /**
   * 工具方法：计算总体评分
   */
  /**
   * 工具方法：计算总体评分
   */
  private calculateOverallScore(report: DetectionReport): number {
    if (report.items.length === 0) return 0;

    // 检查是否有严重问题
    const hasCriticalIssues = report.items.some(item =>
      item.result?.findings.some(f => f.severity === 'critical')
    );

    const totalScore = report.items.reduce((sum, item) => {
      return sum + (item.result?.score || 0);
    }, 0);

    let overallScore = Math.round(totalScore / report.items.length);

    // 如果有严重问题，总分不能超过 60 分
    if (hasCriticalIssues && overallScore > 60) {
      overallScore = 60;
    }

    return overallScore;
  }

  /**
   * 工具方法：创建错误结果
   */
  private createErrorResult(message: string, error?: unknown): DetectionResult {
    const errorText = error instanceof Error ? error.message : (error ? String(error) : '');
    const desc = errorText ? `${message}: ${errorText}` : message;
    return {
      passed: false,
      score: 0,
      severity: 'info',
      findings: [{
        title: '检测失败',
        description: desc,
        severity: 'info'
      }],
      duration: 0,
      timestamp: new Date(),
      rawOutput: {
        error: message,
        detail: errorText || null,
      }
    };
  }

  /**
   * UI 方法：更新进度
   */
  private updateProgress(progress: number, currentTask: string): void {
    const progressBar = document.getElementById('detection-progress-bar');
    const progressText = document.getElementById('detection-progress-text');
    const currentTaskEl = document.getElementById('detection-current-task');

    if (progressBar) {
      progressBar.style.width = `${progress}%`;
    }
    if (progressText) {
      progressText.textContent = `${Math.round(progress)}%`;
    }
    if (currentTaskEl && currentTask) {
      currentTaskEl.textContent = currentTask;
    }

    if (this.progressCallback) {
      this.progressCallback(progress, currentTask);
    }
  }

  /**
   * UI 方法：更新检测项状态
   */
  private updateCheckStatus(checkId: string, status: string, result?: DetectionResult): void {
    const statusEl = document.getElementById(`status-${checkId}`);
    if (!statusEl) return;

    switch (status) {
      case 'running':
        statusEl.textContent = '检测中...';
        statusEl.style.background = 'rgba(59, 130, 246, 0.2)';
        statusEl.style.color = '#3b82f6';
        break;
      case 'completed':
        if (result) {
          const icon = result.passed ? CheckOne({ theme: 'outline', size: '14', fill: '#22c55e' }) : CloseOne({ theme: 'outline', size: '14', fill: '#ef4444' });
          statusEl.innerHTML = `${icon} <span>${result.score}分</span>`;
          statusEl.style.background = this.getSeverityColor(result.severity, 0.2);
          statusEl.style.color = this.getSeverityColor(result.severity, 1);
        }
        break;
      case 'failed':
        statusEl.textContent = '失败';
        statusEl.style.background = 'rgba(239, 68, 68, 0.2)';
        statusEl.style.color = '#ef4444';
        break;
      default:
        statusEl.textContent = '待检测';
        statusEl.style.background = 'var(--bg-secondary)';
        statusEl.style.color = 'var(--text-secondary)';
    }
  }

  /**
   * UI 方法：显示进度面板
   */
  private showProgressPanel(): void {
    const panel = document.getElementById('detection-progress-panel');
    if (panel) {
      panel.style.display = 'block';
    }
  }

  /**
   * UI 方法：隐藏进度面板
   */
  private hideProgressPanel(): void {
    const panel = document.getElementById('detection-progress-panel');
    if (panel) {
      panel.style.display = 'none';
    }
  }

  /**
   * UI 方法：显示汇总面板
   */
  private showSummaryPanel(report: DetectionReport): void {
    const panel = document.getElementById('detection-summary-panel');
    if (!panel) return;

    panel.style.display = 'block';

    // 更新评分
    const scoreEl = document.getElementById('final-score');
    if (scoreEl) {
      scoreEl.textContent = report.overallScore.toString();
      scoreEl.style.color = this.getScoreColor(report.overallScore);
    }

    // 更新问题统计
    const criticalEl = document.getElementById('critical-count');
    const highEl = document.getElementById('high-count');
    const mediumEl = document.getElementById('medium-count');
    const lowEl = document.getElementById('low-count');

    if (criticalEl) criticalEl.textContent = report.summary.critical.toString();
    if (highEl) highEl.textContent = report.summary.high.toString();
    if (mediumEl) mediumEl.textContent = report.summary.medium.toString();
    if (lowEl) lowEl.textContent = report.summary.low.toString();
  }

  /**
   * 工具方法：获取严重级别颜色
   */
  private getSeverityColor(severity: string, opacity: number): string {
    const colors: Record<string, string> = {
      critical: '#ef4444',
      high: '#f59e0b',
      medium: '#eab308',
      low: '#3b82f6',
      info: '#22c55e'
    };
    const color = colors[severity] || colors.info;

    if (opacity < 1) {
      const hex = color.replace('#', '');
      const r = parseInt(hex.substring(0, 2), 16);
      const g = parseInt(hex.substring(2, 4), 16);
      const b = parseInt(hex.substring(4, 6), 16);
      return `rgba(${r}, ${g}, ${b}, ${opacity})`;
    }

    return color;
  }

  /**
   * 工具方法：获取评分颜色
   */
  private getScoreColor(score: number): string {
    if (score >= 90) return '#22c55e'; // 绿色
    if (score >= 70) return '#eab308'; // 黄色
    if (score >= 50) return '#f59e0b'; // 橙色
    return '#ef4444'; // 红色
  }

  /**
   * 历史记录：保存到历史
   */
  private saveToHistory(report: DetectionReport): void {
    this.detectionHistory.unshift(report);

    // 只保留最近 10 条记录
    if (this.detectionHistory.length > 10) {
      this.detectionHistory = this.detectionHistory.slice(0, 10);
    }

    // 保存到 localStorage
    try {
      localStorage.setItem('detection-history', JSON.stringify(this.detectionHistory));
    } catch (error) {
      console.error('保存历史记录失败:', error);
    }

    // 更新 UI
    this.updateHistoryList();
  }

  /**
   * 历史记录：加载历史
   */
  private loadHistory(): void {
    try {
      const historyStr = localStorage.getItem('detection-history');
      if (historyStr) {
        this.detectionHistory = JSON.parse(historyStr);
      }
    } catch (error) {
      console.error('加载历史记录失败:', error);
      this.detectionHistory = [];
    }
  }

  /**
   * 历史记录：刷新历史列表 UI
   */
  refreshHistoryUI(): void {
    this.updateHistoryList();
  }

  /**
   * 历史记录：更新历史列表UI
   */
  private updateHistoryList(): void {
    const listEl = document.getElementById('detection-history-list');
    if (!listEl) return;

    if (this.detectionHistory.length === 0) {
      listEl.innerHTML = `
        <div style="text-align: center; padding: var(--spacing-lg); color: var(--text-secondary);">
          暂无检测历史
        </div>
      `;
      return;
    }

    listEl.innerHTML = this.detectionHistory.map(report => {
      const uniqueItemCount = new Set((report.items || []).map(item => item.id)).size;
      return `
      <div class="history-item" style="
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px;
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius);
        background: var(--bg-primary);
        cursor: pointer;
        transition: all 0.2s ease;
      " onmouseover="this.style.background='var(--bg-secondary)';"
         onmouseout="this.style.background='var(--bg-primary)';"
         onclick="window.quickDetection?.viewHistoryReport('${report.id}')">
        <div>
          <div style="font-weight: 500; color: var(--text-primary); font-size: 14px;">
            ${new Date(report.timestamp).toLocaleString('zh-CN')}
          </div>
          <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
            ${report.server} · ${uniqueItemCount} 项检测 · ${(report.totalDuration / 1000).toFixed(1)}s
          </div>
        </div>
        <div style="text-align: right;">
          <div style="font-size: 24px; font-weight: 600; color: ${this.getScoreColor(report.overallScore)};">
            ${report.overallScore}
          </div>
          <div style="font-size: 11px; color: var(--text-secondary);">
            ${report.summary.critical + report.summary.high} 个问题
          </div>
        </div>
      </div>
    `;
    }).join('');
  }

  /**
   * 历史记录：清空历史
   */
  async clearHistory(): Promise<void> {
    const confirmed = await this.showConfirm({
      title: '确认清空历史',
      message: '确定要清空所有检测历史吗？',
      description: '此操作不可撤销',
      confirmText: '清空',
      cancelText: '取消',
      dangerous: true
    });

    if (confirmed) {
      this.detectionHistory = [];
      localStorage.removeItem('detection-history');
      this.updateHistoryList();
    }
  }

  /**
   * 历史记录：查看历史报告
   */
  viewHistoryReport(reportId: string): void {
    const report = this.detectionHistory.find(r => r.id === reportId);
    if (report) {
      this.currentReport = report;
      this.viewReport();
    }
  }

  /**
   * 报告：查看报告
   */
  viewReport(): void {
    if (!this.currentReport) {
      alert('暂无检测报告');
      return;
    }

    // 确保模态框存在
    this.ensureReportModalExists();

    // 填充报告数据
    this.fillReportData(this.currentReport);

    // 显示模态框
    const modal = document.getElementById('detection-report-modal');
    if (modal) {
      modal.style.display = 'flex';
    }
  }

  /**
   * 确保报告模态框存在
   */
  private ensureReportModalExists(): void {
    if (document.getElementById('detection-report-modal')) {
      return;
    }

    // 创建模态框 HTML
    const modalHTML = this.renderReportModal();
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = modalHTML;
    document.body.appendChild(tempDiv.firstElementChild!);
  }

  /**
   * 渲染报告模态框 HTML
   */
  private renderReportModal(): string {
    return `
      <div id="detection-report-modal" class="modal" style="
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 10000;
        align-items: center;
        justify-content: center;
      ">
        <div class="modal-overlay" onclick="window.quickDetection?.closeReportModal()" style="
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: rgba(0, 0, 0, 0.5);
        "></div>
        <div class="modal-content detection-report-modal-content" style="
          position: relative;
          max-width: 1000px;
          width: 90%;
          max-height: 90vh;
          overflow-y: auto;
          scrollbar-gutter: stable;
          background: var(--bg-primary);
          border-radius: 18px;
          padding: var(--spacing-lg) calc(var(--spacing-lg) + 10px) var(--spacing-lg) var(--spacing-lg);
          box-shadow: 0 24px 64px rgba(15, 23, 42, 0.22);
        ">
          <!-- 报告头部 -->
          <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: var(--spacing-lg);
            padding-bottom: var(--spacing-md);
            border-bottom: 1px solid var(--border-color);
          ">
            <div>
              <h2 style="margin: 0; font-size: 24px; color: var(--text-primary); font-weight: 600;">🔍 检测报告</h2>
              <p id="report-timestamp" style="margin: 4px 0 0 0; font-size: 14px; color: var(--text-secondary);"></p>
            </div>
            <button onclick="window.quickDetection?.closeReportModal()" style="
              background: transparent;
              border: none;
              font-size: 32px;
              color: var(--text-secondary);
              cursor: pointer;
              padding: 0;
              line-height: 1;
              width: 32px;
              height: 32px;
            ">×</button>
          </div>

          <!-- 评分卡片 -->
          <div style="
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: var(--spacing-lg);
            margin-bottom: var(--spacing-lg);
          ">
            <!-- 总体评分 -->
            <div class="modern-card" style="
              border: 1px solid var(--border-color);
              border-radius: var(--border-radius-lg);
              padding: var(--spacing-lg);
              text-align: center;
              background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(147, 51, 234, 0.1) 100%);
            ">
              <div style="font-size: 14px; color: var(--text-secondary); margin-bottom: 8px;">安全评分</div>
              <div style="display: flex; align-items: baseline; justify-content: center; gap: 4px;">
                <span id="report-overall-score" style="font-size: 64px; font-weight: 700; color: var(--primary-color);">--</span>
                <span style="font-size: 32px; color: var(--text-secondary);">/100</span>
              </div>
              <div id="report-score-label" style="
                margin-top: 8px;
                font-size: 16px;
                font-weight: 600;
                color: var(--primary-color);
              ">优秀</div>
            </div>

            <!-- 问题统计 -->
            <div class="modern-card" style="
              border: 1px solid var(--border-color);
              border-radius: var(--border-radius-lg);
              padding: var(--spacing-lg);
              background: var(--bg-primary);
            ">
              <div style="font-size: 16px; color: var(--text-primary); margin-bottom: var(--spacing-md); font-weight: 600;">问题统计</div>
              <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-sm);">
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-secondary); border-radius: var(--border-radius);">
                  <div style="width: 8px; height: 8px; border-radius: 50%; background: #ef4444;"></div>
                  <div style="flex: 1;">
                    <div style="font-size: 12px; color: var(--text-secondary);">严重</div>
                    <div id="report-critical-count" style="font-size: 24px; font-weight: 600; color: #ef4444;">0</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-secondary); border-radius: var(--border-radius);">
                  <div style="width: 8px; height: 8px; border-radius: 50%; background: #f59e0b;"></div>
                  <div style="flex: 1;">
                    <div style="font-size: 12px; color: var(--text-secondary);">高危</div>
                    <div id="report-high-count" style="font-size: 24px; font-weight: 600; color: #f59e0b;">0</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-secondary); border-radius: var(--border-radius);">
                  <div style="width: 8px; height: 8px; border-radius: 50%; background: #eab308;"></div>
                  <div style="flex: 1;">
                    <div style="font-size: 12px; color: var(--text-secondary);">中危</div>
                    <div id="report-medium-count" style="font-size: 24px; font-weight: 600; color: #eab308;">0</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-secondary); border-radius: var(--border-radius);">
                  <div style="width: 8px; height: 8px; border-radius: 50%; background: #3b82f6;"></div>
                  <div style="flex: 1;">
                    <div style="font-size: 12px; color: var(--text-secondary);">低危</div>
                    <div id="report-low-count" style="font-size: 24px; font-weight: 600; color: #3b82f6;">0</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 检测项目详情 -->
          <div id="report-details-container" style="margin-bottom: var(--spacing-lg);">
            <!-- 将由 JavaScript 动态填充 -->
          </div>

          <!-- 底部操作按钮 -->
          <div style="
            display: flex;
            justify-content: flex-end;
            gap: var(--spacing-sm);
            padding-top: var(--spacing-md);
            border-top: 1px solid var(--border-color);
          ">
            <button class="modern-btn secondary" onclick="window.quickDetection?.interpretReport()">
              AI 解析报告
            </button>
            <button class="modern-btn secondary" onclick="window.quickDetection?.exportReport()">
              📄 导出报告
            </button>
            <button class="modern-btn primary" onclick="window.quickDetection?.closeReportModal()">
              关闭
            </button>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 填充报告数据
   */
  private fillReportData(report: DetectionReport): void {
    // 更新时间戳
    const timestampEl = document.getElementById('report-timestamp');
    if (timestampEl) {
      timestampEl.textContent = `${report.server} · ${new Date(report.timestamp).toLocaleString('zh-CN')} · 耗时 ${(report.totalDuration / 1000).toFixed(1)}s`;
    }

    // 更新评分
    const scoreEl = document.getElementById('report-overall-score');
    const labelEl = document.getElementById('report-score-label');
    if (scoreEl) {
      scoreEl.textContent = report.overallScore.toString();
      scoreEl.style.color = this.getScoreColor(report.overallScore);
    }
    if (labelEl) {
      labelEl.textContent = this.getScoreLabel(report.overallScore);
      labelEl.style.color = this.getScoreColor(report.overallScore);
    }

    // 更新问题统计
    const criticalEl = document.getElementById('report-critical-count');
    const highEl = document.getElementById('report-high-count');
    const mediumEl = document.getElementById('report-medium-count');
    const lowEl = document.getElementById('report-low-count');

    if (criticalEl) criticalEl.textContent = report.summary.critical.toString();
    if (highEl) highEl.textContent = report.summary.high.toString();
    if (mediumEl) mediumEl.textContent = report.summary.medium.toString();
    if (lowEl) lowEl.textContent = report.summary.low.toString();

    // 渲染详细结果
    this.renderReportDetails(report);
  }

  /**
   * 渲染报告详细结果
   */
  private renderReportDetails(report: DetectionReport): void {
    const container = document.getElementById('report-details-container');
    if (!container) return;

    let html = '<div style="display: flex; flex-direction: column; gap: var(--spacing-md);">';

    // 按类别分组
    const securityItems = report.items.filter(item => item.category === 'security');
    const performanceItems = report.items.filter(item => item.category === 'performance');

    if (securityItems.length > 0) {
      html += this.renderReportCategory('🔒 安全检测结果', securityItems);
    }

    if (performanceItems.length > 0) {
      html += this.renderReportCategory('⚡ 性能检测结果', performanceItems);
    }

    html += '</div>';
    container.innerHTML = html;
  }

  /**
   * 渲染报告类别
   */
  private renderReportCategory(title: string, items: DetectionItem[]): string {
    let html = `
      <div class="modern-card" style="
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius-lg);
        padding: var(--spacing-md);
        background: var(--bg-primary);
      ">
        <h3 style="margin: 0 0 var(--spacing-md) 0; font-size: 18px; color: var(--text-primary); font-weight: 600;">${title}</h3>
        <div style="display: flex; flex-direction: column; gap: var(--spacing-sm);">
    `;

    items.forEach(item => {
      html += this.renderReportItem(item);
    });

    html += `
        </div>
      </div>
    `;

    return html;
  }

  /**
   * 渲染单个报告项
   */
  private renderReportItem(item: DetectionItem): string {
    const statusColor = item.status === 'completed' ? '#22c55e' : item.status === 'failed' ? '#ef4444' : '#3b82f6';
    const statusIcon = item.status === 'completed'
      ? CheckOne({ theme: 'outline', size: '16', fill: statusColor })
      : item.status === 'failed'
        ? CloseOne({ theme: 'outline', size: '16', fill: statusColor })
        : Time({ theme: 'outline', size: '16', fill: statusColor });

    let html = `
      <div style="
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius);
        padding: var(--spacing-sm);
        background: var(--bg-secondary);
      ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: ${statusColor}; font-size: 16px;">${statusIcon}</span>
            <span style="font-weight: 500; color: var(--text-primary);">${item.name}</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            ${item.result?.rawOutput ? `
              <button 
                class="modern-btn secondary" 
                style="font-size: 12px; padding: 4px 8px; height: 24px;"
                onclick="window.quickDetection?.showRawOutput('${item.id}')"
                title="查看原始结果"
              >
                ${Code({ theme: 'outline', size: '14', fill: 'currentColor' })}
                <span style="margin-left: 4px;">详情</span>
              </button>
            ` : ''}
            <span style="font-size: 14px; font-weight: 600; color: ${statusColor};">
              ${item.result ? `${item.result.score}分` : '未完成'}
            </span>
          </div>
        </div>
    `;

    if (item.result && item.result.findings.length > 0) {
      html += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border-color);">`;

      item.result.findings.forEach((finding, findingIndex) => {
        const severityColor = this.getSeverityColor(finding.severity, 1);
        const severityBg = this.getSeverityColor(finding.severity, 0.1);

        // 生成唯一的容器ID，使用item.id + 索引
        const uniqueContainerId = `ai-solution-${item.id}-${findingIndex}`;

        html += `
          <div style="
            margin-bottom: 8px;
            padding: 12px;
            border-radius: var(--border-radius);
            background: ${severityBg};
            border-left: 3px solid ${severityColor};
          ">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 4px;">
              <span style="font-weight: 500; color: var(--text-primary); font-size: 14px;">${finding.title}</span>
              <span style="
                font-size: 11px;
                padding: 2px 8px;
                border-radius: 4px;
                background: ${severityColor};
                color: white;
                font-weight: 500;
              ">${this.getSeverityLabel(finding.severity)}</span>
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">
              ${finding.description}
            </div>
            ${finding.recommendation ? `
              <div style="
                margin-top: 8px;
                padding: 8px;
                background: var(--bg-primary);
                border-radius: 4px;
                font-size: 12px;
              ">
                <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 4px; display: flex; align-items: center; gap: 4px;">
                  ${Tips({ theme: 'outline', size: '14', fill: 'var(--text-primary)' })}
                  <span>建议：</span>
                </div>
                <div style="color: var(--text-secondary);">${finding.recommendation}</div>
                <!-- AI解决方案容器包装器，使用相对定位 -->
                <div id="${uniqueContainerId}-wrapper" style="position: relative; margin-top: 8px;">
                  <div id="${uniqueContainerId}"></div>
                </div>
                <button
                  id="${uniqueContainerId}-btn"
                  class="modern-btn secondary"
                  style="margin-top: 8px; font-size: 11px; padding: 4px 12px; display: inline-flex; align-items: center; gap: 4px;"
                  onclick="window.quickDetection?.generateAISolutionStream('${finding.title.replace(/'/g, "\\'")}', '${finding.description.replace(/'/g, "\\'")}', '${finding.severity}', '${uniqueContainerId}')">
                  <span>AI 生成解决方案</span>
                </button>
              </div>
            ` : ''}
          </div>
        `;
      });

      html += `</div>`;
    } else if (item.result && item.result.findings.length === 0) {
      html += `
        <div style="
          margin-top: 8px;
          padding: 12px;
          background: rgba(34, 197, 94, 0.1);
          border-radius: var(--border-radius);
          border-left: 3px solid #22c55e;
        ">
          <span style="color: #22c55e; font-size: 14px; display: inline-flex; align-items: center; gap: 4px;">
            ${CheckOne({ theme: 'outline', size: '14', fill: '#22c55e' })}
            <span>未发现问题</span>
          </span>
        </div>
      `;
    }

    html += `</div>`;
    return html;
  }

  /**
   * 获取评分标签
   */
  private getScoreLabel(score: number): string {
    if (score >= 90) return '优秀';
    if (score >= 70) return '良好';
    if (score >= 50) return '一般';
    return '需改进';
  }

  /**
   * 获取严重级别标签
   */
  private getSeverityLabel(severity: string): string {
    const labels: Record<string, string> = {
      critical: '严重',
      high: '高危',
      medium: '中危',
      low: '低危',
      info: '信息'
    };
    return labels[severity] || severity;
  }

  /**
   * 关闭报告模态框
   */
  closeReportModal(): void {
    const modal = document.getElementById('detection-report-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  /**
   * UI 方法：显示原始输出
   */
  showRawOutput(itemId: string): void {
    if (!this.currentReport) return;

    const item = this.currentReport.items.find(i => i.id === itemId);
    if (!item || !item.result || !item.result.rawOutput) return;

    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10002;
      padding: 20px;
      animation: fadeIn 0.2s ease-out;
    `;

    const jsonStr = JSON.stringify(item.result.rawOutput, null, 2);

    modal.innerHTML = `
      <div style="
        background: var(--bg-primary);
        border-radius: 12px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        max-width: 800px;
        width: 100%;
        max-height: 80vh;
        display: flex;
        flex-direction: column;
        animation: slideUp 0.3s ease-out;
      ">
        <div style="
          padding: 16px 20px;
          border-bottom: 1px solid var(--border-color);
          display: flex;
          justify-content: space-between;
          align-items: center;
        ">
          <div style="display: flex; align-items: center; gap: 8px;">
            <h3 style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text-primary);">${item.name} - 原始结果</h3>
          </div>
          <button class="raw-output-close-btn" style="
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 24px;
            cursor: pointer;
            padding: 0;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
          ">×</button>
        </div>
        <div style="padding: 0; overflow: hidden; flex: 1; position: relative;">
          <pre style="
            margin: 0;
            padding: 20px;
            overflow: auto;
            height: 100%;
            font-family: var(--font-mono, monospace);
            font-size: 12px;
            color: var(--text-primary);
            background: var(--bg-secondary);
            tab-size: 2;
          ">${this.syntaxHighlight(jsonStr)}</pre>
          <button class="copy-btn" style="
            position: absolute;
            top: 10px;
            right: 10px;
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            cursor: pointer;
            color: var(--text-secondary);
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
          ">复制 JSON</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // 绑定事件
    const closeBtn = modal.querySelector('.raw-output-close-btn');
    const copyBtn = modal.querySelector('.copy-btn');

    const cleanup = (e?: Event) => {
      if (e) e.stopPropagation(); // 阻止事件冒泡，防止触发全局关闭
      modal.style.opacity = '0';
      setTimeout(() => {
        if (document.body.contains(modal)) {
          document.body.removeChild(modal);
        }
      }, 200);
    };

    closeBtn?.addEventListener('click', cleanup);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) cleanup();
    });

    copyBtn?.addEventListener('click', () => {
      navigator.clipboard.writeText(jsonStr).then(() => {
        const originalText = copyBtn.textContent;
        copyBtn.textContent = '已复制!';
        setTimeout(() => {
          copyBtn.textContent = originalText;
        }, 2000);
      });
    });
  }

  /**
   * 工具方法：JSON 语法高亮
   */
  private syntaxHighlight(json: string): string {
    json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
      let cls = 'number';
      let style = 'color: #f59e0b;'; // number - orange

      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          cls = 'key';
          style = 'color: #3b82f6;'; // key - blue
        } else {
          cls = 'string';
          style = 'color: #10b981;'; // string - green
        }
      } else if (/true|false/.test(match)) {
        cls = 'boolean';
        style = 'color: #ef4444;'; // boolean - red
      } else if (/null/.test(match)) {
        cls = 'null';
        style = 'color: #6b7280;'; // null - gray
      }
      return `<span class="${cls}" style="${style}">${match}</span>`;
    });
  }

  /**
   * 流式生成 AI 解决方案（简洁版）
   */
  async generateAISolutionStream(title: string, description: string, severity: string, containerId: string): Promise<void> {
    // 检查是否配置了 AI
    if (!aiService.isConfigured()) {
      const goToSettings = await this.showConfirm({
        title: 'AI 服务未配置',
        message: 'AI 服务尚未配置，无法生成解决方案。',
        description: '是否前往设置页面配置 AI API？',
        confirmText: '前往设置',
        cancelText: '取消',
        dangerous: false
      });

      if (goToSettings) {
        (window as any).openAISettingsMenu?.();
      }
      return;
    }

    const container = document.getElementById(containerId);
    if (!container) return;

    // 清空容器并显示加载状态
    container.innerHTML = `
      <div style="
        padding: 12px;
        background: var(--bg-secondary);
        border-radius: 6px;
        border-left: 3px solid var(--accent-color);
      ">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
          <div style="
            width: 12px;
            height: 12px;
            border: 2px solid var(--border-color);
            border-top-color: var(--accent-color);
            border-radius: 50%;
            animation: spin 1s linear infinite;
          "></div>
          <span style="font-weight: 500; color: var(--text-primary); font-size: 13px;">AI 正在生成解决方案...</span>
        </div>
        <div id="${containerId}-content" style="
          font-size: 12px;
          color: var(--text-secondary);
          line-height: 1.6;
          white-space: pre-wrap;
        "></div>
      </div>
    `;

    const contentElement = document.getElementById(`${containerId}-content`);
    if (!contentElement) return;

    let fullText = '';
    const buttonElement = document.getElementById(`${containerId}-btn`) as HTMLButtonElement;
    if (buttonElement) {
      buttonElement.disabled = true;
      buttonElement.style.opacity = '0.5';
      buttonElement.style.cursor = 'not-allowed';
    }

    try {
      // 获取服务器信息（如果可用）
      let serverInfo = '';
      if (this.currentReport) {
        serverInfo = this.currentReport.server;
      }

      // 调用 AI 服务流式生成
      await aiService.generateConciseSolutionStream(
        title,
        description,
        severity,
        serverInfo,
        // onChunk: 每次接收到新内容
        (text: string) => {
          fullText += text;
          // 渲染内容，包括命令按钮
          this.renderStreamContent(contentElement, fullText);
        },
        // onComplete: 生成完成
        (finalText: string) => {
          fullText = finalText;
          // 最终渲染
          this.renderStreamContent(contentElement, fullText);

          // 添加"不满意?点我生成详细方案"按钮
          const detailedBtn = document.createElement('button');
          detailedBtn.className = 'modern-btn secondary';
          detailedBtn.style.cssText = `
            position: absolute;
            bottom: 12px;
            right: 12px;
            font-size: 11px;
            padding: 4px 12px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            z-index: 10;
          `;
          detailedBtn.innerHTML = `
            <span>不满意? 点我生成详细方案</span>
          `;
          detailedBtn.onclick = () => {
            this.generateAISolution(title, description, severity);
          };

          // 将按钮添加到 wrapper 容器（已有相对定位）
          const wrapperContainer = document.getElementById(`${containerId}-wrapper`);
          if (wrapperContainer) {
            // 清除可能已存在的详细按钮
            const existingBtn = wrapperContainer.querySelector('.detailed-solution-btn');
            if (existingBtn) {
              existingBtn.remove();
            }
            detailedBtn.classList.add('detailed-solution-btn');
            wrapperContainer.appendChild(detailedBtn);
            // 添加底部padding为按钮留出空间
            wrapperContainer.style.paddingBottom = '40px';
          }

          // 恢复按钮状态
          if (buttonElement) {
            buttonElement.disabled = false;
            buttonElement.style.opacity = '1';
            buttonElement.style.cursor = 'pointer';
          }
        }
      );
    } catch (error: any) {
      // 显示错误信息
      container.innerHTML = `
        <div style="
          padding: 12px;
          background: rgba(239, 68, 68, 0.1);
          border-radius: 6px;
          border-left: 3px solid #ef4444;
        ">
          <div style="font-weight: 500; color: #ef4444; margin-bottom: 4px; font-size: 13px;">❌ AI 生成失败</div>
          <div style="font-size: 12px; color: var(--text-secondary);">${error.message}</div>
        </div>
      `;

      // 恢复按钮状态
      if (buttonElement) {
        buttonElement.disabled = false;
        buttonElement.style.opacity = '1';
        buttonElement.style.cursor = 'pointer';
      }

      console.error('AI 解决方案生成失败:', error);
    }
  }

  /**
   * 渲染流式内容，包括命令按钮
   */
  private renderStreamContent(element: HTMLElement, text: string): void {
    // 清空当前内容
    element.innerHTML = '';

    // 解析内容，识别命令块
    const parts = text.split(/```/);

    parts.forEach((part, index) => {
      if (index % 2 === 0) {
        // 普通文本
        if (part.trim()) {
          const textNode = document.createElement('div');
          textNode.textContent = part;
          textNode.style.cssText = 'margin-bottom: 8px;';
          element.appendChild(textNode);
        }
      } else {
        // 命令块 - 处理可能的语言标识符（如 bash, sh, shell 等）
        let commandText = part.trim();

        // 去除第一行的语言标识符（如果存在）
        const lines = commandText.split('\n');
        if (lines.length > 0 && /^(bash|sh|shell|zsh|powershell|cmd|console)$/i.test(lines[0].trim())) {
          lines.shift(); // 移除语言标识符行
          commandText = lines.join('\n').trim();
        }

        // 过滤掉命令提示符（如 $, #, > 等）
        commandText = commandText.replace(/^[\$#>]\s*/gm, '');

        if (commandText) {
          const commandContainer = document.createElement('div');
          commandContainer.style.cssText = `
            display: block;
            margin: 8px 0;
            padding: 8px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            border: 1px solid var(--border-color);
          `;

          const commandCode = document.createElement('code');
          commandCode.textContent = commandText;
          commandCode.style.cssText = `
            flex: 1;
            font-family: var(--font-mono, monospace);
            font-size: 11px;
            color: var(--accent-color);
            white-space: pre;
          `;

          commandContainer.appendChild(commandCode);
          element.appendChild(commandContainer);
        }
      }
    });
  }

  /**
   * 显示通用确认对话框
   */
  private showConfirm(options: {
    title: string;
    message: string;
    description?: string;
    confirmText?: string;
    cancelText?: string;
    dangerous?: boolean;
  }): Promise<boolean> {
    return new Promise((resolve) => {
      const modal = document.createElement('div');
      modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10002;
        padding: 20px;
        animation: fadeIn 0.2s ease-out;
      `;

      const iconBg = options.dangerous ? 'rgba(239, 68, 68, 0.1)' : 'rgba(59, 130, 246, 0.1)';
      const confirmBg = options.dangerous ? '#ef4444' : 'var(--primary-color)';

      modal.innerHTML = `
        <style>
          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }
          @keyframes slideUp {
            from { 
              transform: translateY(20px);
              opacity: 0;
            }
            to { 
              transform: translateY(0);
              opacity: 1;
            }
          }
        </style>
        <div style="
          background: var(--bg-primary);
          border-radius: 12px;
          box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
          max-width: 450px;
          width: 100%;
          animation: slideUp 0.3s ease-out;
        ">
          <!-- 头部 -->
          <div style="
            padding: 20px;
            border-bottom: 1px solid var(--border-color);
          ">
            <div style="display: flex; align-items: center; gap: 12px;">
              <div style="
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: ${iconBg};
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 20px;
              ">${options.dangerous ? '⚠️' : 'ℹ️'}</div>
              <div style="flex: 1;">
                <h3 style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text-primary);">${options.title}</h3>
                ${options.description ? `<p style="margin: 4px 0 0 0; font-size: 12px; color: var(--text-secondary);">${options.description}</p>` : ''}
              </div>
            </div>
          </div>

          <!-- 内容 -->
          <div style="padding: 20px;">
            <div style="font-size: 14px; color: var(--text-primary); line-height: 1.6;">${options.message}</div>
          </div>

          <!-- 底部按钮 -->
          <div style="
            padding: 16px 20px;
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: flex-end;
            gap: 12px;
          ">
            <button id="confirm-cancel" class="modern-btn secondary" style="padding: 8px 20px; font-size: 13px;">
              ${options.cancelText || '取消'}
            </button>
            <button id="confirm-execute" class="modern-btn primary" style="padding: 8px 20px; font-size: 13px; background: ${confirmBg};">
              ${options.confirmText || '确认'}
            </button>
          </div>
        </div>
      `;

      document.body.appendChild(modal);

      // 绑定按钮事件
      const cancelBtn = document.getElementById('confirm-cancel');
      const executeBtn = document.getElementById('confirm-execute');

      const cleanup = () => {
        modal.style.opacity = '0';
        setTimeout(() => {
          document.body.removeChild(modal);
        }, 200);
      };

      cancelBtn?.addEventListener('click', () => {
        cleanup();
        resolve(false);
      });

      executeBtn?.addEventListener('click', () => {
        cleanup();
        resolve(true);
      });

      // 点击背景关闭
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          cleanup();
          resolve(false);
        }
      });

      // ESC键关闭
      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          cleanup();
          resolve(false);
          document.removeEventListener('keydown', handleEscape);
        }
      };
      document.addEventListener('keydown', handleEscape);
    });
  }

  /**
   * HTML 转义
   */
  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * AI 生成解决方案（完整版，用于详细方案）
   */
  async generateAISolution(title: string, description: string, severity: string = 'medium'): Promise<void> {
    // 检查是否配置了 AI
    if (!aiService.isConfigured()) {
      const goToSettings = await this.showConfirm({
        title: 'AI 服务未配置',
        message: 'AI 服务尚未配置，无法生成解决方案。',
        description: '是否前往设置页面配置 AI API？',
        confirmText: '前往设置',
        cancelText: '取消',
        dangerous: false
      });

      if (goToSettings) {
        (window as any).openAISettingsMenu?.();
      }
      return;
    }

    // 显示加载提示
    const loadingModal = this.showLoadingModal('正在生成 AI 解决方案...');

    try {
      // 获取服务器信息（如果可用）
      let serverInfo = '';
      if (this.currentReport) {
        serverInfo = this.currentReport.server;
      }

      // 调用 AI 服务生成解决方案
      const solution = await aiService.generateSolution(
        title,
        description,
        severity,
        serverInfo
      );

      // 关闭加载提示
      this.closeLoadingModal(loadingModal);

      // 显示解决方案模态框
      this.showSolutionModal(title, description, solution);
    } catch (error: any) {
      // 关闭加载提示
      this.closeLoadingModal(loadingModal);

      // 显示错误信息
      alert(`AI 解决方案生成失败：\n\n${error.message}\n\n请检查：\n1. AI API 配置是否正确\n2. API Key 是否有效\n3. 网络连接是否正常`);
      console.error('AI 解决方案生成失败:', error);
    }
  }

  /**
   * 显示加载模态框
   */
  private showLoadingModal(message: string): HTMLElement {
    const modal = document.createElement('div');
    modal.id = 'ai-loading-modal';
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10001;
    `;
    modal.innerHTML = `
      <div style="
        background: var(--bg-primary);
        padding: 30px 40px;
        border-radius: 12px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        text-align: center;
      ">
        <div style="
          width: 50px;
          height: 50px;
          border: 3px solid var(--border-color);
          border-top-color: var(--accent-color);
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin: 0 auto 20px;
        "></div>
        <div style="
          font-size: 16px;
          color: var(--text-primary);
          font-weight: 500;
        ">${message}</div>
        <div style="
          font-size: 13px;
          color: var(--text-secondary);
          margin-top: 8px;
        ">这可能需要几秒钟...</div>
      </div>
    `;
    document.body.appendChild(modal);
    return modal;
  }

  /**
   * 关闭加载模态框
   */
  private closeLoadingModal(modal: HTMLElement): void {
    if (modal && modal.parentNode) {
      modal.parentNode.removeChild(modal);
    }
  }

  /**
   * 显示 AI 解决方案模态框
   */
  private showSolutionModal(title: string, description: string, solution: any): void {
    // 创建模态框
    const modal = document.createElement('div');
    modal.id = 'ai-solution-modal';
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10001;
      padding: 20px;
    `;

    modal.innerHTML = `
      <div style="
        background: var(--bg-primary);
        border-radius: 12px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        max-width: 800px;
        width: 100%;
        max-height: 90vh;
        display: flex;
        flex-direction: column;
      ">
        <!-- 头部 -->
        <div style="
          padding: 20px 24px;
          border-bottom: 1px solid var(--border-color);
          display: flex;
          justify-content: space-between;
          align-items: center;
        ">
          <h3 style="
            margin: 0;
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
          " style="display: inline-flex; align-items: center; gap: 8px;">
            ${Robot({ theme: 'outline', size: '20', fill: 'var(--text-primary)' })}
            <span>AI 生成的解决方案</span>
          </h3>
          <button onclick="this.closest('#ai-solution-modal').remove()" style="
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 24px;
            cursor: pointer;
            padding: 0;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 4px;
            transition: all 0.2s;
          " onmouseover="this.style.background='var(--bg-secondary)'" onmouseout="this.style.background='none'">×</button>
        </div>

        <!-- 内容 -->
        <div style="
          padding: 24px;
          overflow-y: auto;
          flex: 1;
        ">
          <!-- 问题信息 -->
          <div style="
            background: var(--bg-secondary);
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 20px;
          ">
            <div style="
              font-size: 14px;
              font-weight: 600;
              color: var(--text-primary);
              margin-bottom: 8px;
            ">问题: ${title}</div>
            <div style="
              font-size: 13px;
              color: var(--text-secondary);
              line-height: 1.5;
            ">${description}</div>
          </div>

          <!-- 解决步骤 -->
          ${solution.steps && solution.steps.length > 0 ? `
            <div style="margin-bottom: 20px;">
              <h4 style="
                font-size: 15px;
                font-weight: 600;
                color: var(--text-primary);
                margin: 0 0 12px 0;
              " style="display: inline-flex; align-items: center; gap: 6px;">
                ${ListBottom({ theme: 'outline', size: '16', fill: 'var(--text-primary)' })}
                <span>解决步骤</span>
              </h4>
              <div style="
                background: var(--bg-secondary);
                padding: 16px;
                border-radius: 8px;
              ">
                <ol style="
                  margin: 0;
                  padding-left: 20px;
                  color: var(--text-primary);
                  line-height: 1.8;
                ">
                  ${solution.steps.map((step: string) => `<li style="margin-bottom: 8px;">${step}</li>`).join('')}
                </ol>
              </div>
            </div>
          ` : ''}

          <!-- 风险提示 -->
          ${solution.risks && solution.risks.length > 0 ? `
            <div style="margin-bottom: 20px;">
              <h4 style="
                font-size: 15px;
                font-weight: 600;
                color: var(--text-primary);
                margin: 0 0 12px 0;
              " style="display: inline-flex; align-items: center; gap: 6px;">
                ${Caution({ theme: 'outline', size: '16', fill: 'var(--text-primary)' })}
                <span>风险提示</span>
              </h4>
              <div style="
                background: #fef3c7;
                border-left: 3px solid #f59e0b;
                padding: 16px;
                border-radius: 8px;
              ">
                <ul style="
                  margin: 0;
                  padding-left: 20px;
                  color: #92400e;
                  line-height: 1.8;
                ">
                  ${solution.risks.map((risk: string) => `<li style="margin-bottom: 8px;">${risk}</li>`).join('')}
                </ul>
              </div>
            </div>
          ` : ''}

          <!-- 预计时间 -->
          ${solution.timeEstimate ? `
            <div style="
              background: var(--bg-secondary);
              padding: 12px 16px;
              border-radius: 8px;
              display: flex;
              align-items: center;
              gap: 8px;
              font-size: 13px;
              color: var(--text-secondary);
            ">
              ${Stopwatch({ theme: 'outline', size: '16', fill: 'var(--text-secondary)' })}
              <span>预计耗时: ${solution.timeEstimate}</span>
            </div>
          ` : ''}

          <!-- 完整方案 -->
          <details style="margin-top: 20px;">
            <summary style="
              cursor: pointer;
              font-size: 14px;
              font-weight: 600;
              color: var(--text-primary);
              padding: 12px;
              background: var(--bg-secondary);
              border-radius: 8px;
              user-select: none;
            ">查看完整 AI 方案</summary>
            <div style="
              margin-top: 12px;
              padding: 16px;
              background: var(--bg-secondary);
              border-radius: 8px;
              font-size: 13px;
              line-height: 1.8;
              color: var(--text-primary);
              white-space: pre-wrap;
              font-family: var(--font-mono, monospace);
              max-height: 300px;
              overflow-y: auto;
            ">${solution.solution}</div>
          </details>
        </div>

        <!-- 底部按钮 -->
        <div style="
          padding: 16px 24px;
          border-top: 1px solid var(--border-color);
          display: flex;
          justify-content: flex-end;
          gap: 12px;
        ">
          <button onclick="navigator.clipboard.writeText(this.dataset.solution).then(() => alert('已复制到剪贴板'))" data-solution="${solution.solution.replace(/"/g, '&quot;')}" style="
            padding: 8px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
          " onmouseover="this.style.background='var(--bg-tertiary)'" onmouseout="this.style.background='var(--bg-secondary)'">复制方案</button>
          <button onclick="this.closest('#ai-solution-modal').remove()" style="
            padding: 8px 16px;
            background: var(--accent-color);
            border: none;
            border-radius: 6px;
            color: white;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
          " onmouseover="this.style.opacity='0.9'" onmouseout="this.style.opacity='1'">关闭</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // 点击背景关闭
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.remove();
      }
    });
  }

  /**
   * AI 解读整个检测报告
   */
  async interpretReport(): Promise<void> {
    if (!this.currentReport) {
      alert('暂无检测报告可解读');
      return;
    }

    if (!aiService.isConfigured()) {
      const goToSettings = await this.showConfirm({
        title: 'AI 服务未配置',
        message: 'AI 服务尚未配置，无法解读报告。',
        description: '是否前往设置页面配置 AI API？',
        confirmText: '前往设置',
        cancelText: '取消',
        dangerous: false
      });

      if (goToSettings) {
        (window as any).openAISettingsMenu?.();
      }
      return;
    }

    const problems = this.currentReport.items
      .filter(item => item.result && item.result.findings.length > 0)
      .map(item => {
        const findingsText = item.result!.findings.map(f =>
          `- [${f.severity}] ${f.title}: ${f.description}`
        ).join('\n');
        return {
          checkName: item.name,
          score: item.result!.score,
          findings: findingsText
        };
      });

    if (problems.length === 0) {
      alert('检测报告显示系统状态良好，未发现问题！');
      return;
    }

    const loadingModal = this.showLoadingModal('AI 正在解读检测报告...');

    try {
      let serverInfo = '';
      if (this.currentReport) {
        serverInfo = this.currentReport.server;
      }

      const reportSummary = problems.map(p =>
        `### ${p.checkName} (评分: ${p.score})\n${p.findings}`
      ).join('\n\n');

      const systemPrompt = `你是一位资深的 Linux 系统安全专家。你的任务是为用户解读安全检测报告，帮助用户理解报告内容和风险。

请提供：
1. **总体安全状况评估** - 基于总体评分和问题分布
2. **关键风险解读** - 解释最严重的问题意味着什么
3. **修复优先级建议** - 哪些问题应该优先处理
4. **通俗易懂的解释** - 避免过于专业的术语，让非专业人士也能理解

使用中文回答，保持专业但易懂。`;

      const userPrompt = `请解读以下安全检测报告：

**服务器**: ${serverInfo}
**总体评分**: ${this.currentReport!.overallScore}/100
**问题统计**:
- 严重: ${this.currentReport!.summary.critical}
- 高危: ${this.currentReport!.summary.high}
- 中危: ${this.currentReport!.summary.medium}
- 低危: ${this.currentReport!.summary.low}

**详细检测结果**:

${reportSummary}

请提供详细的安全状况解读和修复建议。`;

      let interpretation = '';
      await aiService.chatStream(
        [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ],
        (text) => {
          interpretation += text;
        },
        (finalText) => {
          interpretation = finalText;
        }
      );

      this.closeLoadingModal(loadingModal);
      this.showInterpretationModal(interpretation);
    } catch (error: any) {
      this.closeLoadingModal(loadingModal);
      alert(`AI 解读失败：\n\n${error.message}`);
      console.error('AI 解读失败:', error);
    }
  }

  async autoFixRisks(): Promise<void> {
    return this.autoFixRisksLegacy();
  }

  /**
   * 旧版 AI 修复流程
   */
  async autoFixRisksLegacy(): Promise<void> {
    if (!this.currentReport) {
      alert('暂无检测报告可修复');
      return;
    }

    if (!aiService.isConfigured()) {
      const goToSettings = await this.showConfirm({
        title: 'AI 服务未配置',
        message: 'AI 服务尚未配置，无法生成修复方案。',
        description: '是否前往设置页面配置 AI API？',
        confirmText: '前往设置',
        cancelText: '取消',
        dangerous: false
      });

      if (goToSettings) {
        (window as any).openAISettingsMenu?.();
      }
      return;
    }

    const criticalAndHighFindings = this.currentReport.items
      .filter(item => item.result && item.result.findings.some(f =>
        f.severity === 'critical' || f.severity === 'high'
      ))
      .map(item => {
        const relevantFindings = item.result!.findings.filter(f =>
          f.severity === 'critical' || f.severity === 'high'
        );
        return {
          checkName: item.name,
          findings: relevantFindings.map(f => ({
            title: f.title,
            description: f.description,
            severity: f.severity,
            recommendation: f.recommendation
          }))
        };
      });

    if (criticalAndHighFindings.length === 0) {
      alert('当前报告没有严重或高危问题需要修复！');
      return;
    }

    const loadingModal = this.showLoadingModal('AI 正在生成修复方案...');

    try {
      let serverInfo = '';
      if (this.currentReport) {
        serverInfo = this.currentReport.server;
      }

      const problemsText = criticalAndHighFindings.map(p =>
        `### ${p.checkName}\n${p.findings.map(f =>
          `- [${f.severity}] ${f.title}: ${f.description}\n  建议: ${f.recommendation || '无'}`
        ).join('\n')}`
      ).join('\n\n');

      const systemPrompt = `你是一位资深的 Linux 系统安全专家和自动化运维专家。你的任务是为检测到的安全问题提供可自动执行的修复命令。

严格要求：
1. 每个修复步骤必须包含完整的、可直接执行的 shell 命令
2. 命令必须用 \`\`\`bash 包裹，每个代码块只包含一条命令
3. 在命令前简要说明该命令的作用
4. 对于危险操作（如删除文件、修改系统配置），必须添加说明
5. 命令必须安全、准确、可逆（如果可能）
6. 使用中文解释，命令使用英文

示例格式：
步骤1：禁用 root SSH 登录
\`\`\`bash
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
\`\`\`

步骤2：重启 SSH 服务
\`\`\`bash
systemctl restart sshd
\`\`\``;

      const userPrompt = `服务器信息: ${serverInfo}

请为以下安全问题提供修复命令：

${problemsText}

请提供完整的修复方案，包含所有必要的命令。`;

      let fixSolution = '';
      await aiService.chatStream(
        [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ],
        (text) => {
          fixSolution += text;
        },
        (finalText) => {
          fixSolution = finalText;
        }
      );

      this.closeLoadingModal(loadingModal);
      this.showAutoFixModal(fixSolution, criticalAndHighFindings);
    } catch (error: any) {
      this.closeLoadingModal(loadingModal);
      alert(`AI 修复方案生成失败：\n\n${error.message}`);
      console.error('AI 修复方案生成失败:', error);
    }
  }

  /**
   * 显示 AI 解读结果模态框
   */
  private showInterpretationModal(interpretation: string): void {
    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10001;
      padding: 20px;
    `;

    modal.innerHTML = `
      <div style="
        background: var(--bg-primary);
        border-radius: 12px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        max-width: 800px;
        width: 100%;
        max-height: 90vh;
        display: flex;
        flex-direction: column;
      ">
        <div style="
          padding: 20px 24px;
          border-bottom: 1px solid var(--border-color);
          display: flex;
          justify-content: space-between;
          align-items: center;
        ">
          <h3 style="margin: 0; font-size: 18px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
            ${Robot({ theme: 'outline', size: '20', fill: 'var(--text-primary)' })}
            <span>AI 检测报告解析</span>
          </h3>
          <button onclick="this.closest('div[style*=fixed]').remove()" style="
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 24px;
            cursor: pointer;
            padding: 0;
            width: 30px;
            height: 30px;
          ">×</button>
        </div>
        <div style="padding: 24px; overflow-y: auto; flex: 1;">
          <div style="
            font-size: 14px;
            line-height: 1.8;
            color: var(--text-primary);
            white-space: pre-wrap;
          ">${this.renderMarkdown(interpretation)}</div>
        </div>
        <div style="
          padding: 16px 24px;
          border-top: 1px solid var(--border-color);
          display: flex;
          justify-content: flex-end;
          gap: 12px;
        ">
          <button onclick="navigator.clipboard.writeText(this.dataset.text).then(() => alert('已复制'))" data-text="${interpretation.replace(/"/g, '&quot;')}" style="
            padding: 8px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 14px;
            cursor: pointer;
          ">复制解析</button>
          <button onclick="this.closest('div[style*=fixed]').remove()" style="
            padding: 8px 16px;
            background: var(--accent-color);
            border: none;
            border-radius: 6px;
            color: white;
            font-size: 14px;
            cursor: pointer;
          ">关闭</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });
  }

  /**
   * 显示 AI 自动修复模态框
   */
  private showAutoFixModal(fixSolution: string, findings: any[]): void {
    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10001;
      padding: 20px;
    `;

    const findingsList = findings.map(f =>
      f.findings.map((finding: any) =>
        `<li>[${finding.severity}] ${finding.title}</li>`
      ).join('')
    ).join('');

    modal.innerHTML = `
      <div style="
        background: var(--bg-primary);
        border-radius: 12px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        max-width: 900px;
        width: 100%;
        max-height: 90vh;
        display: flex;
        flex-direction: column;
      ">
        <div style="
          padding: 20px 24px;
          border-bottom: 1px solid var(--border-color);
          display: flex;
          justify-content: space-between;
          align-items: center;
        ">
          <h3 style="margin: 0; font-size: 18px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
            ${Robot({ theme: 'outline', size: '20', fill: 'var(--text-primary)' })}
            <span>AI 自动修复方案</span>
          </h3>
          <button onclick="this.closest('div[style*=fixed]').remove()" style="
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 24px;
            cursor: pointer;
            padding: 0;
            width: 30px;
            height: 30px;
          ">×</button>
        </div>
        <div style="padding: 24px; overflow-y: auto; flex: 1;">
          <div style="
            padding: 12px;
            background: rgba(239, 68, 68, 0.1);
            border-left: 3px solid #ef4444;
            border-radius: 6px;
            margin-bottom: 16px;
          ">
            <div style="font-weight: 500; color: #ef4444; margin-bottom: 4px;">⚠️ 重要提示</div>
            <ul style="margin: 0; padding-left: 18px; font-size: 12px; color: var(--text-secondary); line-height: 1.6;">
              <li>以下命令将在远程服务器上执行</li>
              <li>请仔细检查每条命令，确保了解其作用</li>
              <li>建议在执行前备份重要配置文件</li>
              <li>某些操作可能需要 root 权限</li>
            </ul>
          </div>
          <div style="
            margin-bottom: 16px;
            font-size: 13px;
            color: var(--text-secondary);
          ">
            <strong>待修复问题：</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 18px;">
              ${findingsList}
            </ul>
          </div>
          <div style="
            font-size: 14px;
            line-height: 1.8;
            color: var(--text-primary);
            white-space: pre-wrap;
          ">${this.renderMarkdown(fixSolution)}</div>
        </div>
        <div style="
          padding: 16px 24px;
          border-top: 1px solid var(--border-color);
          display: flex;
          justify-content: space-between;
          gap: 12px;
        ">
          <button onclick="this.closest('div[style*=fixed]').remove()" style="
            padding: 8px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 14px;
            cursor: pointer;
          ">取消</button>
          <div style="display: flex; gap: 12px;">
            <button onclick="navigator.clipboard.writeText(this.dataset.text).then(() => alert('已复制'))" data-text="${fixSolution.replace(/"/g, '&quot;')}" style="
              padding: 8px 16px;
              background: var(--bg-secondary);
              border: 1px solid var(--border-color);
              border-radius: 6px;
              color: var(--text-primary);
              font-size: 14px;
              cursor: pointer;
            ">复制方案</button>
            <button id="execute-all-fix-btn" style="
              padding: 8px 16px;
              background: #ef4444;
              border: none;
              border-radius: 6px;
              color: white;
              font-size: 14px;
              cursor: pointer;
              font-weight: 500;
            ">授权执行修复命令</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const executeBtn = document.getElementById('execute-all-fix-btn');
    executeBtn?.addEventListener('click', () => {
      this.executeFixCommands(fixSolution);
    });

    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });
  }

  /**
   * 显示密码授权对话框
   */
  private async showPasswordAuthorizationDialog(): Promise<{ password: string; remember: boolean } | null> {
    return new Promise((resolve) => {
      const modal = document.createElement('div');
      modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10003;
        padding: 20px;
      `;

      const sshConnectionManager = (window as any).sshConnectionManager;
      const connectionStatus = sshConnectionManager?.getConnectionStatus?.();
      const serverInfo = connectionStatus
        ? `${connectionStatus.username}@${connectionStatus.host}:${connectionStatus.port}`
        : '远程服务器';

      modal.innerHTML = `
        <div style="
          background: var(--bg-primary);
          border-radius: 12px;
          box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
          max-width: 450px;
          width: 100%;
          animation: slideUp 0.2s ease-out;
        ">
          <div style="
            padding: 20px 24px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 12px;
          ">
            <div style="
              width: 48px;
              height: 48px;
              border-radius: 50%;
              background: rgba(239, 68, 68, 0.1);
              display: flex;
              align-items: center;
              justify-content: center;
              font-size: 24px;
            ">🔐</div>
            <div>
              <h3 style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text-primary);">授权临时 root 权限</h3>
              <p style="margin: 4px 0 0 0; font-size: 12px; color: var(--text-secondary);">用于执行修复命令</p>
            </div>
          </div>

          <div style="padding: 20px 24px;">
            <div style="
              padding: 12px;
              background: var(--bg-secondary);
              border-radius: 8px;
              margin-bottom: 16px;
              font-size: 13px;
              color: var(--text-secondary);
              line-height: 1.6;
            ">
              <div style="margin-bottom: 8px;"><strong>目标服务器：</strong>${serverInfo}</div>
              <div style="margin-bottom: 8px;"><strong>原因：</strong>AI 修复方案需要 sudo/root 权限才能执行</div>
              <div><strong>说明：</strong>密码仅用于本次会话验证，不会保存到任何地方</div>
            </div>

            <div style="margin-bottom: 16px;">
              <label style="display: block; font-size: 13px; font-weight: 500; color: var(--text-primary); margin-bottom: 8px;">
                输入密码
              </label>
              <input type="password" id="fix-auth-password" placeholder="请输入密码" style="
                width: 100%;
                padding: 10px 12px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border-color);
                border-radius: 6px;
                color: var(--text-primary);
                font-size: 14px;
                outline: none;
                box-sizing: border-box;
              " />
            </div>

            <div style="
              padding: 10px 12px;
              background: rgba(239, 68, 68, 0.1);
              border-left: 3px solid #ef4444;
              border-radius: 4px;
              font-size: 12px;
              color: var(--text-secondary);
              line-height: 1.6;
            ">
              ⚠️ 请确保您信任此服务器和 AI 生成的修复方案。错误的命令可能导致系统故障。
            </div>
          </div>

          <div style="
            padding: 16px 24px;
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: flex-end;
            gap: 12px;
          ">
            <button id="fix-auth-cancel" style="
              padding: 8px 16px;
              background: var(--bg-secondary);
              border: 1px solid var(--border-color);
              border-radius: 6px;
              color: var(--text-primary);
              font-size: 14px;
              cursor: pointer;
            ">取消</button>
            <button id="fix-auth-confirm" style="
              padding: 8px 16px;
              background: #ef4444;
              border: none;
              border-radius: 6px;
              color: white;
              font-size: 14px;
              cursor: pointer;
              font-weight: 500;
            ">确认授权</button>
          </div>
        </div>
      `;

      document.body.appendChild(modal);

      const passwordInput = document.getElementById('fix-auth-password') as HTMLInputElement;
      const cancelBtn = document.getElementById('fix-auth-cancel');
      const confirmBtn = document.getElementById('fix-auth-confirm');

      const cleanup = () => {
        modal.style.opacity = '0';
        modal.style.transition = 'opacity 0.2s';
        setTimeout(() => modal.remove(), 200);
      };

      cancelBtn?.addEventListener('click', () => {
        cleanup();
        resolve(null);
      });

      confirmBtn?.addEventListener('click', () => {
        const password = passwordInput?.value || '';
        if (!password.trim()) {
          passwordInput?.focus();
          return;
        }
        cleanup();
        resolve({ password, remember: false });
      });

      passwordInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          confirmBtn?.click();
        }
      });

      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          cleanup();
          resolve(null);
        }
      });

      setTimeout(() => passwordInput?.focus(), 100);
    });
  }

  /**
   * 执行修复命令（逐条确认）
   */
  private async executeFixCommands(fixSolution: string): Promise<void> {
    const commands = this.extractCommandsFromText(fixSolution);

    if (commands.length === 0) {
      alert('未找到可执行的命令');
      return;
    }

    const confirmed = await this.showConfirm({
      title: '确认批量执行修复命令',
      message: `AI 生成了 ${commands.length} 条修复命令。授权后将自动逐条执行，失败的命令会尝试替代方案。`,
      description: '此操作将在远程服务器上执行命令',
      confirmText: '开始执行',
      cancelText: '取消',
      dangerous: true
    });

    if (!confirmed) return;

    const authResult = await this.showPasswordAuthorizationDialog();
    if (!authResult) return;

    const { password } = authResult;

    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10002;
      padding: 20px;
    `;

    modal.innerHTML = `
      <div style="
        background: var(--bg-primary);
        border-radius: 12px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        max-width: 800px;
        width: 100%;
        max-height: 80vh;
        display: flex;
        flex-direction: column;
      ">
        <div style="
          padding: 16px 20px;
          border-bottom: 1px solid var(--border-color);
          display: flex;
          justify-content: space-between;
          align-items: center;
        ">
          <h3 id="fix-modal-title" style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text-primary);">
            执行修复命令 (${commands.length} 条) - 已授权
          </h3>
          <button onclick="this.closest('div[style*=fixed]').remove()" style="
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 24px;
            cursor: pointer;
            padding: 0;
            width: 30px;
            height: 30px;
          ">×</button>
        </div>
        <div style="padding: 20px; overflow-y: auto; flex: 1;">
          <div id="fix-progress-container"></div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    const container = document.getElementById('fix-progress-container');
    const modalTitle = document.getElementById('fix-modal-title');

    let retryCount = 0;
    const maxRetries = 2;

    for (let i = 0; i < commands.length; i++) {
      const cmd = commands[i];
      const stepEl = document.createElement('div');
      stepEl.style.cssText = `
        margin-bottom: 16px;
        padding: 12px;
        background: var(--bg-secondary);
        border-radius: 8px;
        border-left: 3px solid var(--accent-color);
      `;
      stepEl.innerHTML = `
        <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 8px;">
          步骤 ${i + 1}/${commands.length}: ${cmd.description || '执行命令'}
        </div>
        <div style="
          font-family: var(--font-mono, monospace);
          font-size: 12px;
          background: var(--bg-tertiary);
          padding: 8px;
          border-radius: 4px;
          color: var(--accent-color);
          margin-bottom: 8px;
        ">${this.escapeHtml(cmd.command)}</div>
        <div id="fix-step-${i}-status" style="font-size: 12px; color: var(--text-secondary);">等待执行...</div>
      `;
      container!.appendChild(stepEl);

      const statusEl = document.getElementById(`fix-step-${i}-status`);
      if (statusEl) {
        statusEl.innerHTML = `<span style="color: var(--accent-color);">执行中...</span>`;
      }

      let commandToRun = cmd.command;
      let executedSuccessfully = false;
      let attemptCount = 0;

      while (!executedSuccessfully && attemptCount <= maxRetries) {
        try {
          const commandWithSudo = commandToRun.includes('sudo') ? commandToRun : `echo "${password}" | sudo -S ${commandToRun}`;
          const result = await invoke('execute_detection_command', { command: commandWithSudo });
          const output = result as { output: string; exit_code: number | null };

          if (output.exit_code === 0) {
            if (statusEl) {
              statusEl.innerHTML = `
                <div style="color: #22c55e; margin-top: 4px;">✓ 执行成功</div>
                ${output.output ? `<pre style="margin-top: 4px; font-size: 11px; color: var(--text-secondary); max-height: 100px; overflow: auto; white-space: pre-wrap;">${this.escapeHtml(output.output)}</pre>` : ''}
              `;
            }
            executedSuccessfully = true;
          } else {
            if (attemptCount < maxRetries) {
              if (statusEl) {
                statusEl.innerHTML = `
                  <div style="color: #eab308; margin-top: 4px;">⚠ 尝试 ${attemptCount + 1} 失败，正在获取替代方案...</div>
                `;
              }

              const alternativeCmd = await this.getAlternativeCommand(
                cmd.command,
                output.output || `Exit code: ${output.exit_code}`,
                commandToRun
              );

              if (alternativeCmd) {
                commandToRun = alternativeCmd;
                attemptCount++;
                retryCount++;

                const retryEl = document.createElement('div');
                retryEl.style.cssText = `
                  margin-top: 8px;
                  padding: 8px;
                  background: rgba(234, 179, 8, 0.1);
                  border-radius: 4px;
                  font-size: 11px;
                `;
                retryEl.innerHTML = `
                  <div style="color: #eab308; margin-bottom: 4px;">↻ 尝试替代方案 (${attemptCount}/${maxRetries}):</div>
                  <div style="font-family: var(--font-mono, monospace); color: var(--text-secondary);">${this.escapeHtml(commandToRun)}</div>
                `;
                stepEl.appendChild(retryEl);
              } else {
                if (statusEl) {
                  statusEl.innerHTML = `
                    <div style="color: #f59e0b; margin-top: 4px;">⚠ 未能找到替代方案，跳过此步骤</div>
                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">错误: ${this.escapeHtml(output.output || `Exit code: ${output.exit_code}`)}</div>
                  `;
                }
                break;
              }
            } else {
              if (statusEl) {
                statusEl.innerHTML = `
                  <div style="color: #f59e0b; margin-top: 4px;">⚠ 已尝试所有方案，仍失败</div>
                  <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">${this.escapeHtml(output.output || `Exit code: ${output.exit_code}`)}</div>
                `;
              }
              break;
            }
          }
        } catch (error: any) {
          if (statusEl) {
            statusEl.innerHTML = `<span style="color: #ef4444;">✗ 执行失败: ${this.escapeHtml(error.message)}</span>`;
          }
          break;
        }
      }

      container!.scrollTop = container!.scrollHeight;
    }

    if (retryCount > 0) {
      modalTitle!.textContent = `执行修复命令 - 已完成 (重试 ${retryCount} 次)`;
    }

    const finishEl = document.createElement('div');
    finishEl.style.cssText = `
      margin-top: 16px;
      padding: 12px;
      background: rgba(34, 197, 94, 0.1);
      border-radius: 8px;
      text-align: center;
      color: #22c55e;
      font-weight: 500;
    `;
    finishEl.textContent = '修复命令执行完成！';
    container!.appendChild(finishEl);
  }

  /**
   * 获取替代命令
   */
  private async getAlternativeCommand(
    originalCommand: string,
    errorOutput: string,
    previousAttempt?: string
  ): Promise<string | null> {
    try {
      const systemPrompt = `你是一位资深的 Linux 系统运维专家。当修复命令执行失败时，你需要分析错误原因并提供替代方案。

要求：
1. 分析原始命令失败的原因
2. 提供一个或多个替代命令
3. 替代命令必须用 \`\`\`bash 包裹，只包含一条命令
4. 如果问题无法用命令解决，说明原因

常见失败原因及处理方式：
- 文件/目录不存在 → 检查路径或先创建
- 权限不足 → 使用 sudo 或改变文件权限
- 服务未安装 → 尝试安装或使用替代工具
- 命令语法错误 → 修正语法
- 配置文件格式错误 → 使用正确格式`;

      const userPrompt = `原始修复命令：${originalCommand}
${previousAttempt ? `上次尝试命令：${previousAttempt}` : ''}
执行失败输出/错误：
${errorOutput}

请分析失败原因并提供替代命令（如果可能）。`;

      let alternativeCommand: string | null = null;

      await aiService.chatStream(
        [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ],
        () => {},
        (finalText) => {
          const match = finalText.match(/```bash\n?([\s\S]*?)```/);
          if (match) {
            alternativeCommand = match[1].trim();
          }
        }
      );

      return alternativeCommand;
    } catch (error) {
      console.error('获取替代命令失败:', error);
      return null;
    }
  }

  /**
   * 从文本中提取命令
   */
  private extractCommandsFromText(text: string): Array<{ command: string; description: string }> {
    const commands: Array<{ command: string; description: string }> = [];

    const codeBlockRegex = /```(?:bash|sh|shell)?\s*\n([\s\S]*?)```/g;
    let match;

    while ((match = codeBlockRegex.exec(text)) !== null) {
      const blockContent = match[1];
      const lines = blockContent.split('\n');

      for (const line of lines) {
        const trimmedLine = line.trim();
        if (!trimmedLine || trimmedLine.startsWith('#')) continue;

        const cleanedLine = trimmedLine.replace(/^[\$#>]\s*/gm, '');
        if (this.isValidCommand(cleanedLine)) {
          const description = this.extractDescriptionFromContext(text, match.index, cleanedLine);
          commands.push({ command: cleanedLine, description });
        }
      }
    }

    if (commands.length === 0) {
      const fallbackCommands = this.extractCommandsFallback(text);
      for (const cmd of fallbackCommands) {
        commands.push({ command: cmd, description: '' });
      }
    }

    return commands;
  }

  private isValidCommand(line: string): boolean {
    if (!line || line.length < 2) return false;

    const chineseRegex = /[\u4e00-\u9fa5]/;
    if (chineseRegex.test(line)) return false;

    if (line.includes('（') || line.includes('）') || line.includes('：')) return false;

    if (line.includes('或者') || line.includes('或者使用') || line.includes('或者使用iptables-persistent')) return false;

    const commandPatterns = [
      /^(apt-get|yum|dnf|pacman|apk)\s+/,
      /^(service|systemctl|init)\s+/,
      /^(iptables|ip6tables|ufw|firewall-cmd|nft)\s+/,
      /^(systemctl|service)\s+(enable|disable|start|stop|restart|reload|status)/,
      /^(mkdir|chmod|chown|rm|cp|mv|ln|touch|cat|echo|grep|sed|awk|find|xargs)\s+/,
      /^(ssh|scp|rsync|sftp)\s+/,
      /^(wget|curl|git|svn)\s+/,
      /^(tar|zip|unzip|gzip|bzip2|xz)\s+/,
      /^(kill|pkill|killall|ps|top)\s+/,
      /^(useradd|usermod|userdel|passwd|groupadd|chpasswd)\s+/,
      /^(crontab|sed|cat|tee|dd)\s+/,
      /^(ls|cd|pwd|whoami|id|uname|hostname)\s*/,
      /^(echo|export|source|eval)\s+/,
      /^(tee|dd|blockdev)\s+/,
      /^(netfilter-persistent|iptables-persistent)\s+/,
      /^(save|reload|start|stop)\s*/,
      /^(echo|tee)\s+.*\|/,
      /^\s*echo\s+["']/,
      /^\s*apt-get\s+install/,
      /^\s*yum\s+install/,
      /^\s*dnf\s+install/,
      /^\s*systemctl\s+/,
      /^\s*service\s+/,
      /^\s*systemctl\s+enable/,
      /^\s*systemctl\s+start/,
      /^\s*systemctl\s+restart/,
      /^\s*systemctl\s+reload/,
      /^\s*systemctl\s+status/,
      /^\s*service\s+iptables\s+save/,
      /^\s*netfilter-persistent\s+save/,
      /^\s*netfilter-persistent\s+reload/,
      /^\s*iptables\s+/,
      /^\s*ip6tables\s+/,
      /^\s*ufw\s+/,
      /^\s*firewall-cmd\s+/,
    ];

    return commandPatterns.some(pattern => pattern.test(line));
  }

  private extractDescriptionFromContext(text: string, matchIndex: number, command: string): string {
    const lines = text.substring(0, matchIndex).split('\n');
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();
      if (line && !line.startsWith('#') && line.includes(command.substring(0, 20))) {
        return line.replace(/^步骤\d+[：:]\s*/, '').replace(/[`#*]/g, '').trim();
      }
    }
    return '';
  }

  private extractCommandsFallback(text: string): string[] {
    const lines = text.split('\n');
    const validCommands: string[] = [];

    for (const line of lines) {
      const trimmedLine = line.trim();
      if (this.isValidCommand(trimmedLine)) {
        validCommands.push(trimmedLine);
      }
    }

    return validCommands;
  }

  /**
   * 简单的 Markdown 渲染
   */
  private renderMarkdown(text: string): string {
    let html = this.escapeHtml(text);

    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre style="background: var(--bg-tertiary); padding: 12px; border-radius: 6px; overflow-x: auto; margin: 8px 0;"><code>$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px; font-size: 0.9em;">$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/^### (.+)$/gm, '<h4 style="margin: 16px 0 8px 0; font-size: 16px; font-weight: 600;">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 style="margin: 20px 0 10px 0; font-size: 18px; font-weight: 600;">$1</h3>');
    html = html.replace(/^- (.+)$/gm, '<li style="margin-left: 20px;">$1</li>');
    html = html.replace(/^\d+\. (.+)$/gm, '<li style="margin-left: 20px;">$1</li>');
    html = html.replace(/\n/g, '<br>');

    return html;
  }

  /**
   * 导出报告
   */
  exportReport(): void {
    if (!this.currentReport) {
      alert('暂无可导出的报告');
      return;
    }

    // 生成 Markdown 格式报告
    let markdown = `# 安全检测报告\n\n`;
    markdown += `**服务器**: ${this.currentReport.server}\n`;
    markdown += `**检测时间**: ${new Date(this.currentReport.timestamp).toLocaleString('zh-CN')}\n`;
    markdown += `**总体评分**: ${this.currentReport.overallScore}/100\n`;
    markdown += `**耗时**: ${(this.currentReport.totalDuration / 1000).toFixed(1)}秒\n\n`;

    markdown += `## 问题统计\n\n`;
    markdown += `- 严重问题: ${this.currentReport.summary.critical}\n`;
    markdown += `- 高危问题: ${this.currentReport.summary.high}\n`;
    markdown += `- 中危问题: ${this.currentReport.summary.medium}\n`;
    markdown += `- 低危问题: ${this.currentReport.summary.low}\n\n`;

    // 添加详细结果
    const securityItems = this.currentReport.items.filter(item => item.category === 'security');
    const performanceItems = this.currentReport.items.filter(item => item.category === 'performance');

    if (securityItems.length > 0) {
      markdown += `## 安全检测结果\n\n`;
      securityItems.forEach(item => {
        markdown += `### ${item.name} (${item.result?.score || 0}分)\n\n`;
        if (item.result && item.result.findings.length > 0) {
          item.result.findings.forEach(finding => {
            markdown += `**[${this.getSeverityLabel(finding.severity)}]** ${finding.title}\n\n`;
            markdown += `${finding.description}\n\n`;
            if (finding.recommendation) {
              markdown += `**建议**: ${finding.recommendation}\n\n`;
            }
          });
        } else {
          markdown += `✅ 未发现问题\n\n`;
        }
      });
    }

    if (performanceItems.length > 0) {
      markdown += `## 性能检测结果\n\n`;
      performanceItems.forEach(item => {
        markdown += `### ${item.name}\n\n`;
        if (item.result && item.result.findings.length > 0) {
          item.result.findings.forEach(finding => {
            markdown += `- ${finding.description}\n`;
          });
          markdown += `\n`;
        }
      });
    }

    // 下载文件
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `security-report-${Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  /**
   * UI 方法：全选/取消检测项
   */
  toggleAllChecks(category: 'security' | 'performance'): void {
    const checkboxes = document.querySelectorAll(`.detection-item[data-category="${category}"] input[type="checkbox"]`);
    if (checkboxes.length === 0) return;

    const firstCheckbox = checkboxes[0] as HTMLInputElement;
    const newState = !firstCheckbox.checked;

    checkboxes.forEach(cb => {
      const checkbox = cb as HTMLInputElement;
      checkbox.checked = newState;

      // 更新父元素的视觉样式
      const item = checkbox.closest('.detection-item') as HTMLElement;
      if (item) {
        if (newState) {
          item.classList.add('selected');
          item.style.borderColor = 'var(--primary-color)';
          item.style.background = 'var(--bg-primary)';
          item.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.05)';
        } else {
          item.classList.remove('selected');
          item.style.borderColor = 'var(--border-color)';
          item.style.background = 'var(--bg-secondary)';
          item.style.boxShadow = 'none';
        }
      }
    });
  }

  /**
   * 工具方法：获取选中的检测项 ID
   */
  private getAllCheckIds(): string[] {
    const checkboxes = document.querySelectorAll('.detection-item input[type="checkbox"]:checked');
    return Array.from(new Set(Array.from(checkboxes).map(cb => {
      const parent = cb.closest('.detection-item');
      return parent?.getAttribute('data-check-id') || '';
    }).filter(id => id !== '')));
  }

  /**
   * 工具方法：获取检测项名称
   */
  private getCheckName(id: string): string {
    const names: Record<string, string> = {
      'port-scan': '端口安全扫描',
      'user-audit': '用户权限审计',
      'backdoor-scan': '后门检测',
      'process-analysis': '可疑进程分析',
      'file-permission': '文件权限检测',
      'ssh-audit': 'SSH 安全审计',
      'log-analysis': '日志安全分析',
      'firewall-check': '防火墙状态检查',
      'cpu-test': 'CPU 压力测试',
      'memory-test': '内存性能测试',
      'disk-test': '磁盘 I/O 测试',
      'network-test': '网络性能测试'
    };
    return names[id] || id;
  }

  /**
   * 工具方法：获取检测项描述
   */
  private getCheckDescription(id: string): string {
    const descriptions: Record<string, string> = {
      'port-scan': '检测开放端口和高危服务',
      'user-audit': '检查用户权限和空密码账号',
      'backdoor-scan': '扫描 Webshell 和计划任务',
      'process-analysis': '识别异常进程和网络连接',
      'file-permission': '检查敏感文件和 SUID 文件',
      'ssh-audit': '检查 SSH 配置安全性',
      'log-analysis': '分析异常登录和暴力破解',
      'firewall-check': '检查防火墙规则配置',
      'cpu-test': '测试 CPU 性能和频率',
      'memory-test': '测试内存读写速度',
      'disk-test': '测试磁盘读写性能',
      'network-test': '测试带宽和延迟'
    };
    return descriptions[id] || '';
  }

  /**
   * 工具方法：获取检测项分类
   */
  private getCheckCategory(id: string): 'security' | 'performance' {
    const performanceChecks = ['cpu-test', 'memory-test', 'disk-test', 'network-test'];
    return performanceChecks.includes(id) ? 'performance' : 'security';
  }

  /**
   * 工具方法：生成报告 ID
   */
  private generateReportId(): string {
    return `report-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  }

  /**
   * 工具方法：获取当前服务器信息
   */
  private getCurrentServerInfo(): string {
    const sshConnectionManager = (window as any).sshConnectionManager;
    const connectionStatus = sshConnectionManager?.getConnectionStatus?.();

    if (connectionStatus && connectionStatus.connected) {
      return `${connectionStatus.username}@${connectionStatus.host}:${connectionStatus.port}`;
    }

    return '未知服务器';
  }

  /**
   * 设置进度回调
   */
  private async hasActiveSshConnection(): Promise<boolean> {
    try {
      const status = await invoke('ssh_get_connection_status') as { connected?: boolean } | null;
      return Boolean(status?.connected);
    } catch {
      const sshConnectionManager = (window as any).sshConnectionManager;
      const connectionStatus = sshConnectionManager?.getConnectionStatus?.();
      return Boolean(connectionStatus?.connected);
    }
  }

  setProgressCallback(callback: (progress: number, current: string) => void): void {
    this.progressCallback = callback;
  }
}

// 创建全局实例
export const quickDetectionManager = new QuickDetectionManager();
