import {
  Analysis,
  Cpu,
  FileText,
  History,
  Key,
  LinkCloud,
  Lock,
  Memory,
  Rocket,
  SettingConfig,
  Shield,
  Speed,
  System,
  Time,
  User
} from '@icon-park/svg';
import { Code, Config, NetworkTree } from '@icon-park/svg';

type CheckItem = {
  id: string;
  name: string;
  description: string;
  iconFunc: (props: any) => string;
};

const securityChecks: CheckItem[] = [
  { id: 'port-scan', name: '端口安全扫描', description: '检测开放端口和高危服务', iconFunc: NetworkTree },
  { id: 'user-audit', name: '用户权限审计', description: '检查用户权限和空密码账号', iconFunc: User },
  { id: 'backdoor-scan', name: '后门检测', description: '扫描 Webshell 和计划任务', iconFunc: Code },
  { id: 'process-analysis', name: '可疑进程分析', description: '识别异常进程和网络连接', iconFunc: Config },
  { id: 'file-permission', name: '文件权限检测', description: '检查敏感文件和 SUID 文件', iconFunc: FileText },
  { id: 'ssh-audit', name: 'SSH 安全审计', description: '检查 SSH 配置安全性', iconFunc: Lock },
  { id: 'log-analysis', name: '日志安全分析', description: '分析异常登录和暴力破解', iconFunc: Analysis },
  { id: 'firewall-check', name: '防火墙状态检查', description: '检查防火墙规则配置', iconFunc: Shield },
  { id: 'password-policy', name: '密码策略检查', description: '检查密码复杂度和过期策略', iconFunc: Key },
  { id: 'sudo-audit', name: 'Sudo 配置审计', description: '检查 sudo 权限配置安全性', iconFunc: Shield },
  { id: 'pam-config', name: 'PAM 配置检查', description: '检查 PAM 认证配置', iconFunc: Lock },
  { id: 'account-lockout', name: '账号锁定策略', description: '检查登录失败锁定机制', iconFunc: Lock },
  { id: 'selinux-status', name: 'SELinux/AppArmor', description: '检查强制访问控制状态', iconFunc: Shield },
  { id: 'kernel-params', name: '内核参数检查', description: '检查安全相关内核参数', iconFunc: System },
  { id: 'system-updates', name: '系统补丁状态', description: '检查系统更新和漏洞补丁', iconFunc: System },
  { id: 'unnecessary-services', name: '不必要服务检查', description: '检测运行的不必要服务', iconFunc: SettingConfig },
  { id: 'auto-start-services', name: '自启动服务审计', description: '审计开机自启动服务', iconFunc: SettingConfig },
  { id: 'audit-config', name: '审计配置检查', description: '检查系统审计(auditd)配置', iconFunc: Analysis },
  { id: 'history-audit', name: '历史命令审计', description: '检查可疑历史命令', iconFunc: FileText },
  { id: 'ntp-config', name: '时间同步检查', description: '检查 NTP 时间同步配置', iconFunc: Time },
  { id: 'dns-config', name: 'DNS 配置检查', description: '检查 DNS 解析配置安全', iconFunc: LinkCloud }
];

const performanceChecks: CheckItem[] = [
  { id: 'cpu-test', name: 'CPU 压力测试', description: '测试 CPU 性能和频率', iconFunc: Cpu },
  { id: 'memory-test', name: '内存性能测试', description: '测试内存读写速度', iconFunc: Memory },
  { id: 'disk-test', name: '磁盘 I/O 测试', description: '测试磁盘读写性能', iconFunc: System },
  { id: 'network-test', name: '网络性能测试', description: '测试带宽和延迟', iconFunc: Speed }
];

function renderCheckItem(check: CheckItem, category: string): string {
  const iconSVG = check.iconFunc({ theme: 'filled', size: '20', fill: 'currentColor' });

  return `
    <div class="detection-item" data-check-id="${check.id}" data-category="${category}" style="
      display: flex;
      align-items: flex-start;
      gap: 16px;
      padding: 16px;
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius-lg);
      background: var(--bg-secondary);
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
    " onclick="
      const checkbox = this.querySelector('input[type=checkbox]');
      checkbox.checked = !checkbox.checked;
      this.classList.toggle('selected', checkbox.checked);
      if(checkbox.checked) {
        this.style.borderColor = 'var(--primary-color)';
        this.style.background = 'var(--bg-primary)';
        this.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.05)';
      } else {
        this.style.borderColor = 'var(--border-color)';
        this.style.background = 'var(--bg-secondary)';
        this.style.boxShadow = 'none';
      }
    " onmouseover="if(!this.classList.contains('selected')) { this.style.background='var(--bg-primary)'; this.style.borderColor='var(--border-hover)'; }"
       onmouseout="if(!this.classList.contains('selected')) { this.style.background='var(--bg-secondary)'; this.style.borderColor='var(--border-color)'; }">
      
      <div style="
        display: flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        border-radius: 8px;
        background: var(--bg-tertiary);
        color: var(--primary-color);
        flex-shrink: 0;
        margin-top: 2px;
      ">
        ${iconSVG}
      </div>

      <div style="flex: 1;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div style="font-weight: 600; color: var(--text-primary); font-size: 14px; margin-bottom: 4px;">${check.name}</div>
          <input type="checkbox" id="check-${check.id}" checked style="
            width: 16px;
            height: 16px;
            accent-color: var(--primary-color);
            cursor: pointer;
            margin-top: 2px;
          " onclick="event.stopPropagation();">
        </div>
        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.4; margin-bottom: 8px;">${check.description}</div>
        
        <div id="status-${check.id}" class="check-status" style="
          display: inline-flex;
          align-items: center;
          font-size: 11px;
          color: var(--text-secondary);
          padding: 2px 8px;
          border-radius: 4px;
          background: var(--bg-tertiary);
        ">
          <span style="width: 6px; height: 6px; background: var(--text-disabled); border-radius: 50%; margin-right: 6px;"></span>
          待检测
        </div>
      </div>
  </div>
  `;
}

export function renderQuickDetectionPage(): string {
  return `
    <div class="quick-detection-page" style="
      max-width: 1200px;
      margin: 0 auto;
      padding: var(--spacing-lg) var(--spacing-md);
      min-height: 100%;
    ">
      <div style="
        background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-primary) 100%);
        border-radius: var(--border-radius-xl);
        padding: 32px;
        margin-bottom: var(--spacing-xl);
        border: 1px solid var(--border-color);
        position: relative;
        overflow: hidden;
        box-shadow: var(--shadow-sm);
      ">
        <div style="position: relative; z-index: 1; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <h2 style="margin: 0 0 8px 0; font-size: 24px; color: var(--text-primary); font-weight: 700;">安全评估中心</h2>
            <p style="margin: 0; font-size: 14px; color: var(--text-secondary); max-width: 500px;">
              全方位服务器安全漏洞扫描与性能体检，护航系统稳定运行
            </p>
          </div>
          
          <div style="display: flex; gap: 12px;">
            <button id="quick-scan-all-btn" class="modern-btn primary large" style="
              padding: 10px 24px;
              font-size: 14px;
              font-weight: 600;
              box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
            " onclick="window.quickDetection?.startFullScan()">
              ${Rocket({ theme: 'filled', size: '18', fill: 'currentColor' })}
              <span style="margin-left: 8px;">一键全面扫描</span>
            </button>
            
            <button id="quick-view-report-btn" class="modern-btn secondary large" style="
              padding: 10px 24px;
              font-size: 14px;
              background: var(--bg-primary);
            " onclick="window.quickDetection?.viewReport()">
              ${Analysis({ theme: 'outline', size: '18', fill: 'currentColor' })}
              <span style="margin-left: 8px;">查看报告</span>
            </button>
          </div>
        </div>

        <div style="
          position: absolute;
          right: -10px;
          top: -30px;
          opacity: 0.03;
          transform: rotate(10deg);
          pointer-events: none;
          color: var(--text-primary);
        ">
          ${Shield({ theme: 'filled', size: '180', fill: 'currentColor' })}
        </div>
      </div>

      <div id="detection-progress-panel" style="
        display: none;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius-lg);
        padding: 24px;
        margin-bottom: var(--spacing-xl);
        box-shadow: var(--shadow-md);
      ">
        <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 16px;">
          <div>
            <div style="font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">
              <span class="pulse-dot" style="display: inline-block; width: 8px; height: 8px; background: var(--primary-color); border-radius: 50%; margin-right: 8px;"></span>
              正在进行检测...
            </div>
            <div id="detection-current-task" style="color: var(--text-secondary); font-size: 13px; margin-left: 16px;">正在初始化检测引擎...</div>
          </div>
          <div id="detection-score-display" style="font-size: 32px; font-weight: 700; color: var(--primary-color); font-family: monospace;">--</div>
        </div>
        
        <div style="width: 100%; height: 8px; background: var(--bg-secondary); border-radius: 4px; overflow: hidden; margin-bottom: 8px;">
          <div id="detection-progress-bar" style="
            width: 0%;
            height: 100%;
            background: linear-gradient(90deg, var(--primary-color), #8b5cf6);
            transition: width 0.3s ease;
            border-radius: 4px;
          "></div>
        </div>
        
        <div style="display: flex; justify-content: space-between; color: var(--text-secondary); font-size: 12px;">
          <span id="detection-progress-text">0%</span>
          <span id="detection-items-count">0/0 项</span>
        </div>
      </div>

      <div id="detection-summary-panel" style="
        display: none;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius-lg);
        padding: 24px;
        margin-bottom: var(--spacing-xl);
        box-shadow: var(--shadow-md);
      ">
        <div style="display: flex; gap: 32px; align-items: center;">
          <div style="text-align: center; padding-right: 32px; border-right: 1px solid var(--border-color);">
            <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">安全评分</div>
            <div style="display: flex; align-items: baseline; gap: 4px;">
              <span id="final-score" style="font-size: 42px; font-weight: 700; color: var(--success-color);">--</span>
              <span style="font-size: 16px; color: var(--text-secondary);">/100</span>
            </div>
          </div>
          
          <div style="flex: 1; display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
            <div style="padding: 16px; background: rgba(239, 68, 68, 0.05); border-radius: var(--border-radius); border: 1px solid rgba(239, 68, 68, 0.1); text-align: center;">
              <div style="font-size: 24px; font-weight: 700; color: #ef4444;" id="critical-count">0</div>
              <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">严重风险</div>
            </div>
            <div style="padding: 16px; background: rgba(245, 158, 11, 0.05); border-radius: var(--border-radius); border: 1px solid rgba(245, 158, 11, 0.1); text-align: center;">
              <div style="font-size: 24px; font-weight: 700; color: #f59e0b;" id="high-count">0</div>
              <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">高危风险</div>
            </div>
            <div style="padding: 16px; background: rgba(234, 179, 8, 0.05); border-radius: var(--border-radius); border: 1px solid rgba(234, 179, 8, 0.1); text-align: center;">
              <div style="font-size: 24px; font-weight: 700; color: #eab308;" id="medium-count">0</div>
              <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">中危风险</div>
            </div>
            <div style="padding: 16px; background: rgba(59, 130, 246, 0.05); border-radius: var(--border-radius); border: 1px solid rgba(59, 130, 246, 0.1); text-align: center;">
              <div style="font-size: 24px; font-weight: 700; color: #3b82f6;" id="low-count">0</div>
              <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">低危建议</div>
            </div>
          </div>
        </div>
      </div>

      <div>
        <div style="margin-bottom: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
            <div style="display: flex; align-items: center; gap: 12px;">
              <div style="padding: 8px; background: rgba(59, 130, 246, 0.1); border-radius: 8px; color: var(--primary-color);">
                ${Speed({ theme: 'filled', size: '20', fill: 'currentColor' })}
              </div>
              <div>
                <h3 style="margin: 0; font-size: 16px; color: var(--text-primary); font-weight: 600;">性能检测</h3>
                <div style="font-size: 12px; color: var(--text-secondary);">${performanceChecks.length} 项性能评估</div>
              </div>
            </div>
            <button class="modern-btn text-only" style="font-size: 12px;" onclick="window.quickDetection?.toggleAllChecks('performance')">全选</button>
          </div>
          <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;">
            ${performanceChecks.map(check => renderCheckItem(check, 'performance')).join('')}
          </div>
        </div>

        <div>
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
            <div style="display: flex; align-items: center; gap: 12px;">
              <div style="padding: 8px; background: rgba(34, 197, 94, 0.1); border-radius: 8px; color: var(--success-color);">
                ${Shield({ theme: 'filled', size: '20', fill: 'currentColor' })}
              </div>
              <div>
                <h3 style="margin: 0; font-size: 16px; color: var(--text-primary); font-weight: 600;">安全检测</h3>
                <div style="font-size: 12px; color: var(--text-secondary);">${securityChecks.length} 项安全检查</div>
              </div>
            </div>
            <button class="modern-btn text-only" style="font-size: 12px;" onclick="window.quickDetection?.toggleAllChecks('security')">全选</button>
          </div>
          <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;">
            ${securityChecks.map(check => renderCheckItem(check, 'security')).join('')}
          </div>
        </div>
      </div>

      <div style="margin-top: 48px; border-top: 1px solid var(--border-color); padding-top: 24px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
          <h3 style="margin: 0; font-size: 16px; color: var(--text-primary); font-weight: 600; display: flex; align-items: center;">
            <span style="margin-right: 8px; display: inline-flex;">
              ${History({ theme: 'outline', size: '18', fill: 'currentColor' })}
            </span>
            检测历史
          </h3>
          <button class="modern-btn secondary small" style="font-size: 12px;" onclick="window.quickDetection?.clearHistory()">清空历史</button>
        </div>
        <div id="detection-history-list" style="display: flex; flex-direction: column; gap: 12px;">
          <div style="text-align: center; padding: 32px; color: var(--text-secondary); background: var(--bg-secondary); border-radius: var(--border-radius); border: 1px dashed var(--border-color); font-size: 13px;">
            暂无历史记录
          </div>
        </div>
      </div>
    </div>
  `;
}
