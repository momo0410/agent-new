/**
 * Python 后端 API 适配层
 * 将 Tauri invoke 调用替换为 HTTP API 调用
 * 
 * 使用方式：在前端代码中，将所有 `invoke('command_name', args)` 
 * 替换为 `pythonApi.commandName(args)`
 */

/** 生产构建：直连本机后端；Vite 开发走同源代理 /api/v1。可用 VITE_API_BASE_URL 覆盖。 */
const API_BASE_URL = (() => {
  const fromEnv = import.meta.env.VITE_API_BASE_URL?.trim();
  if (fromEnv) return fromEnv.replace(/\/$/, '');
  if (import.meta.env.DEV) return '/api/v1';
  return 'http://127.0.0.1:3001/api/v1';
})();

class PythonApi {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T = any>(
    method: string,
    path: string,
    body?: any,
    params?: Record<string, any>
  ): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    
    // 添加查询参数
    if (params) {
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      }
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }

    const options: RequestInit = {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
      mode: 'cors',
      credentials: 'same-origin',
    };

    if (body && method !== 'GET') {
      options.body = JSON.stringify(body);
    }

    try {
      const response = await fetch(url, options);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({})) as {
          detail?: unknown;
          message?: unknown;
        };
        const raw = errorData.detail ?? errorData.message;
        const detailStr = Array.isArray(raw)
          ? raw.map((x: { msg?: string }) => x?.msg || JSON.stringify(x)).join('; ')
          : raw != null && typeof raw === 'object'
            ? JSON.stringify(raw)
            : (typeof raw === 'string' ? raw : raw != null ? String(raw) : '');
        throw new Error(detailStr || `API error: ${response.status}`);
      }

      return await response.json();
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      const m = msg.toLowerCase();
      if (
        m.includes('failed to fetch') ||
        m.includes('networkerror') ||
        m.includes('load failed') ||
        m.includes('network request failed')
      ) {
        throw new Error(
          '无法连接后端（http://127.0.0.1:3001）。请在 src-python 目录执行 python run.py，或使用 npm run python-backend。'
        );
      }
      throw error;
    }
  }

  // ==================== 窗口控制 ====================

  async minimizeWindow() {
    return this.request('POST', '/window/minimize');
  }

  async toggleMaximize() {
    return this.request('POST', '/window/toggle-maximize');
  }

  async closeWindow() {
    return this.request('POST', '/window/close');
  }

  async openDevtools() {
    return this.request('POST', '/window/open-devtools');
  }

  async openDialog(options: {
    multiple?: boolean;
    directory?: boolean;
    filters?: Array<{ name?: string; extensions?: string[] }>;
    defaultPath?: string;
  }) {
    return this.request<{ path: string | string[] | null }>('POST', '/dialog/open', {
      multiple: options.multiple,
      directory: options.directory,
      filters: options.filters,
      default_path: options.defaultPath,
    });
  }

  async saveDialog(options: {
    filters?: Array<{ name?: string; extensions?: string[] }>;
    defaultPath?: string;
  }) {
    return this.request<{ path: string | null }>('POST', '/dialog/save', {
      filters: options.filters,
      default_path: options.defaultPath,
    });
  }

  // ==================== 主题管理 ====================

  async getThemeSettings() {
    return this.request('GET', '/theme/settings');
  }

  async setCurrentTheme(theme: string) {
    return this.request('POST', '/theme/set', { theme });
  }

  // ==================== 设置管理 ====================

  async getAppSettings() {
    return this.request('GET', '/settings');
  }

  async saveAppSettings(settings: any) {
    return this.request('POST', '/settings/save', { settings });
  }

  async readSettingsFile() {
    const result = await this.request('GET', '/settings/file');
    return result.content;
  }

  async writeSettingsFile(content: string) {
    return this.request('POST', '/settings/file/write', { content });
  }

  async getSystemFonts() {
    const result = await this.request('GET', '/system/fonts');
    return result.fonts;
  }

  // ==================== SSH 连接管理 ====================

  async loadSshConnections() {
    return this.request('GET', '/ssh/connections');
  }

  async saveSshConnections(connections: any[]) {
    return this.request('POST', '/ssh/connections/save', connections);
  }

  async encryptPassword(password: string) {
    const result = await this.request('POST', '/ssh/encrypt-password', { password });
    return result.encrypted;
  }

  async decryptPassword(encryptedPassword: string) {
    const result = await this.request('POST', '/ssh/decrypt-password', { encrypted_password: encryptedPassword });
    return result.decrypted;
  }

  async sshConnectWithAuth(params: {
    host: string; port: number; username: string; authType: string;
    password?: string; keyPath?: string; keyPassphrase?: string; certificatePath?: string;
  }) {
    return this.request('POST', '/ssh/connect', {
      host: params.host, port: params.port, username: params.username,
      auth_type: params.authType, password: params.password,
      key_path: params.keyPath, key_passphrase: params.keyPassphrase,
      certificate_path: params.certificatePath,
    });
  }

  async sshTestConnection(params: any) {
    const result = await this.request('POST', '/ssh/test-connection', {
      host: params.host, port: params.port, username: params.username,
      auth_type: params.authType, password: params.password,
      key_path: params.keyPath, key_passphrase: params.keyPassphrase,
    });
    return result.success;
  }

  async sshExecuteCommand(command: string) {
    return this.request('POST', '/ssh/execute-command', { command });
  }

  async sshDisconnect() {
    return this.request('POST', '/ssh/disconnect');
  }

  // ==================== SSH/SFTP 直接命令 ====================

  async sshConnectDirect(host: string, port: number, username: string, password: string) {
    return this.request('POST', '/ssh/connect-direct', { host, port, username, password });
  }

  async sshDisconnectDirect() {
    return this.request('POST', '/ssh/disconnect-direct');
  }

  async sshExecuteCommandDirect(command: string, username?: string) {
    return this.request('POST', '/ssh/execute-command-direct', { command, username });
  }

  async sshExecuteDashboardCommandDirect(command: string) {
    return this.request('POST', '/ssh/execute-dashboard-command', { command });
  }

  async sshExecuteEmergencyCommandDirect(command: string, username?: string) {
    return this.request('POST', '/ssh/execute-emergency-command', { command, username });
  }

  async executeDetectionCommand(command: string) {
    return this.request('POST', '/ssh/execute-detection-command', { command });
  }

  async sshGetConnectionStatus() {
    return this.request('GET', '/ssh/connection-status');
  }

  async sshGetConnectionHealth() {
    return this.request('GET', '/ssh/connection-health');
  }

  async testSshPerformance() {
    const result = await this.request('POST', '/ssh/test-performance');
    return result.result;
  }

  async diagnoseShellPerformance() {
    const result = await this.request('POST', '/ssh/diagnose-shell-performance');
    return result.result;
  }

  async detectSystemType() {
    return this.request('GET', '/ssh/detect-system-type');
  }

  // ==================== SFTP 文件操作 ====================

  async sftpListFiles(path: string) {
    return this.request('POST', '/sftp/list-files', undefined, { path });
  }

  async sftpReadFile(path: string, maxBytes?: number) {
    const result = await this.request('POST', '/sftp/read-file', undefined, { path, max_bytes: maxBytes });
    return result.content;
  }

  async sftpWriteFile(path: string, content: string) {
    return this.request('POST', '/sftp/write-file', { path, content });
  }

  async sftpUpload(localPath: string, remotePath: string) {
    return this.request('POST', '/sftp/upload', { local_path: localPath, remote_path: remotePath });
  }

  async sftpUploadDirect(file: File, remotePath: string, uploadId: string) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('remote_path', remotePath);
    formData.append('upload_id', uploadId);
    formData.append('file_size', String(file.size));

    const url = `${this.baseUrl}/sftp/upload-direct`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      // 不设置 Content-Type，让浏览器自动设置 multipart boundary
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({})) as {
        detail?: unknown;
        message?: unknown;
      };
      const raw = errorData.detail ?? errorData.message;
      const detailStr = Array.isArray(raw)
        ? raw.map((x: { msg?: string }) => x?.msg || JSON.stringify(x)).join('; ')
        : raw != null && typeof raw === 'object'
          ? JSON.stringify(raw)
          : (typeof raw === 'string' ? raw : raw != null ? String(raw) : '');
      throw new Error(detailStr || `API error: ${response.status}`);
    }

    return await response.json();
  }

  async sftpGetUploadProgress(uploadId: string) {
    return this.request<{
      upload_id: string;
      stage: string;
      transferred_bytes: number;
      total_bytes: number;
      percent: number;
      done: boolean;
      success: boolean;
      error?: string | null;
      updated_at: number;
    }>('GET', '/sftp/upload-progress', undefined, { upload_id: uploadId });
  }

  async sftpDownload(remotePath: string, localPath: string) {
    return this.request('POST', '/sftp/download', { remote_path: remotePath, local_path: localPath });
  }

  async sftpCreateDirectory(remotePath: string) {
    return this.request('POST', '/sftp/create-directory', undefined, { remote_path: remotePath });
  }

  async sftpCompress(sourcePath: string, targetPath: string, format: string) {
    return this.request('POST', '/sftp/compress', { source_path: sourcePath, target_path: targetPath, format });
  }

  async sftpExtract(archivePath: string, targetDir: string, overwrite: boolean = true) {
    return this.request('POST', '/sftp/extract', { archive_path: archivePath, target_dir: targetDir, overwrite });
  }

  async sftpChmod(path: string, mode: number) {
    return this.request('POST', '/sftp/chmod', { path, mode });
  }

  async sftpGetFileDetails(path: string) {
    return this.request('POST', '/sftp/get-file-details', undefined, { path });
  }

  async saveTempFile(fileName: string, data: string) {
    // data 已是 base64 编码的字符串
    const result = await this.request('POST', '/sftp/save-temp-file', { file_name: fileName, data });
    return result.path;
  }

  // ==================== 文件安全分析 ====================

  async sftpFileAnalysis(path: string, action?: string) {
    return this.request('POST', '/file-analysis', { path, action });
  }

  async sftpFileAnalysisIndependent(path: string, action?: string) {
    return this.request('POST', '/file-analysis/independent', { path, action });
  }

  // ==================== Bash 环境 & 命令补全 ====================

  async getBashEnvironmentInfo() {
    return this.request('GET', '/bash/environment-info');
  }

  async getCommandCompletion(input: string) {
    return this.request('POST', '/command/completion', undefined, { input });
  }

  // ==================== 安全检测命令 ====================

  async detectPortScan() { return this.request('POST', '/detect/port-scan'); }
  async detectUserAudit() { return this.request('POST', '/detect/user-audit'); }
  async detectBackdoor() { return this.request('POST', '/detect/backdoor'); }
  async detectProcessAnalysis() { return this.request('POST', '/detect/process-analysis'); }
  async detectFilePermission() { return this.request('POST', '/detect/file-permission'); }
  async detectSshAudit() { return this.request('POST', '/detect/ssh-audit'); }
  async detectLogAnalysis() { return this.request('POST', '/detect/log-analysis'); }
  async detectFirewallCheck() { return this.request('POST', '/detect/firewall-check'); }
  async detectCpuTest() { return this.request('POST', '/detect/cpu-test'); }
  async detectMemoryTest() { return this.request('POST', '/detect/memory-test'); }
  async detectDiskTest() { return this.request('POST', '/detect/disk-test'); }
  async detectNetworkTest() { return this.request('POST', '/detect/network-test'); }

  // 基线检测
  async detectPasswordPolicy() { return this.request('POST', '/detect/password-policy'); }
  async detectSudoConfig() { return this.request('POST', '/detect/sudo-config'); }
  async detectPamConfig() { return this.request('POST', '/detect/pam-config'); }
  async detectAccountLockout() { return this.request('POST', '/detect/account-lockout'); }
  async detectSelinuxStatus() { return this.request('POST', '/detect/selinux-status'); }
  async detectKernelParams() { return this.request('POST', '/detect/kernel-params'); }
  async detectSystemUpdates() { return this.request('POST', '/detect/system-updates'); }
  async detectUnnecessaryServices() { return this.request('POST', '/detect/unnecessary-services'); }
  async detectAutoStartServices() { return this.request('POST', '/detect/auto-start-services'); }
  async detectAuditConfig() { return this.request('POST', '/detect/audit-config'); }
  async detectHistoryAudit() { return this.request('POST', '/detect/history-audit'); }
  async detectNtpConfig() { return this.request('POST', '/detect/ntp-config'); }
  async detectDnsConfig() { return this.request('POST', '/detect/dns-config'); }

  // ==================== SSH 终端管理 ====================

  async sshCreateTerminalSession(terminalId: string, cols: number, rows: number) {
    const payload = { terminal_id: terminalId, cols, rows };
    console.log('[PythonAPI] sshCreateTerminalSession called:', payload);
    return this.request('POST', '/ssh/terminal/create', payload);
  }

  async sshCloseTerminalSession(terminalId: string) {
    return this.request('POST', '/ssh/terminal/close', undefined, { terminal_id: terminalId });
  }

  async sshCloseAllTerminalSessions() {
    return this.request('POST', '/ssh/terminal/close-all');
  }

  async sshSendInput(terminalId: string, data: string) {
    return this.request('POST', '/ssh/terminal/send-input', { terminal_id: terminalId, data });
  }

  async sshGetCompletion(input: string) {
    return this.request('POST', '/ssh/terminal/get-completion', undefined, { input });
  }

  // ==================== 日志分析 ====================

  async readSystemLog(params: { logPath: string; page?: number; pageSize?: number; filter?: string; dateFilter?: string; levelFilter?: string }) {
    return this.request('POST', '/log/read-system', {
      log_path: params.logPath, page: params.page, page_size: params.pageSize,
      filter: params.filter, date_filter: params.dateFilter, level_filter: params.levelFilter,
    });
  }

  async readJournalctlLog(params: { page?: number; pageSize?: number; unit?: string; filter?: string; since?: string; until?: string; levelFilter?: string }) {
    return this.request('POST', '/log/read-journalctl', {
      page: params.page, page_size: params.pageSize, unit: params.unit,
      filter: params.filter, since: params.since, until: params.until, level_filter: params.levelFilter,
    });
  }

  async listLogFiles() {
    return this.request('GET', '/log/list-files');
  }

  async getLogFileInfo(logPath: string) {
    return this.request('POST', '/log/file-info', undefined, { log_path: logPath });
  }

  // ==================== 渗透测试 Agent ====================

  async pentestStart(params: {
    target: string;
    max_rounds?: number;
    dry_run?: boolean;
    execution_mode?: 'serial' | 'parallel';
    skill_query?: string;
    skill_limit?: number;
    llm_max_tokens?: number;
    llm_timeout_seconds?: number;
    llm_max_retries?: number;
    llm_retry_backoff_seconds?: number;
    api_key: string;
    model: string;
    base_url: string;
    provider: string;
    temperature?: number;
  }) {
    return this.request<{success: boolean; message: string; target: string; task_id: string}>('POST', '/agent/pentest/start', {
      target: params.target,
      max_rounds: params.max_rounds ?? 30,
      dry_run: params.dry_run ?? false,
      execution_mode: params.execution_mode ?? 'serial',
      skill_query: params.skill_query ?? '',
      skill_limit: params.skill_limit ?? 5,
      llm_max_tokens: params.llm_max_tokens ?? 600,
      llm_timeout_seconds: params.llm_timeout_seconds ?? 60,
      llm_max_retries: params.llm_max_retries ?? 1,
      llm_retry_backoff_seconds: params.llm_retry_backoff_seconds ?? 1.2,
      api_key: params.api_key,
      model: params.model,
      base_url: params.base_url,
      provider: params.provider,
      temperature: params.temperature ?? 0.3,
    });
  }

  async pentestDoctor(refresh: boolean = false) {
    return this.request<{
      generated_at: string;
      summary: { ok: number; warn: number; error: number; total: number };
      tools: Array<{
        tool: string;
        status: 'ok' | 'warn' | 'error';
        binary: string;
        binary_path: string | null;
        version: string;
        help_probe_ok: boolean;
        issues: string[];
        auto_fixes: string[];
      }>;
    }>('GET', '/agent/pentest/doctor', undefined, { refresh });
  }

  async pentestStatus(taskId: string) {
    return this.request<{
      running: boolean;
      phase: string;
      targets: string[];
      findings_count: number;
      vuln_count: number;
      cred_count: number;
      actions_count: number;
      actions: Array<{tool: string; args: string; time: string; result: string}>;
      token_usage?: Record<string, any>;
      task_id: string;
      error?: string;
    }>('GET', '/agent/pentest/status', undefined, { task_id: taskId });
  }

  async pentestStop(taskId: string) {
    return this.request('POST', '/agent/pentest/stop', undefined, { task_id: taskId });
  }

  async pentestGetState(taskId: string) {
    return this.request('GET', '/agent/state', undefined, { task_id: taskId });
  }

  async pentestGetReport(taskId: string) {
    return this.request<{report: string; view?: Record<string, any>; phase: string; task_id: string; token_usage?: Record<string, any>}>('GET', '/agent/report', undefined, { task_id: taskId });
  }

  async pentestRecordTokenUsage(params: {
    task_id: string;
    category: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    model?: string;
    provider?: string;
  }) {
    return this.request<{
      success: boolean;
      task_id: string;
      category: string;
      token_usage?: Record<string, any>;
    }>('POST', '/agent/token-usage', {
      task_id: params.task_id,
      category: params.category,
      prompt_tokens: params.prompt_tokens,
      completion_tokens: params.completion_tokens,
      total_tokens: params.total_tokens,
      model: params.model ?? '',
      provider: params.provider ?? '',
    });
  }

  async pentestLogs(taskId: string) {
    return this.request<{
      phase: string;
      actions_count: number;
      actions: Array<{
        id?: string;
        tool: string;
        args: string;
        time: string;
        result: string;
        full_stdout: string;
        llm_decision: string;
        returncode: number | null;
        error: string;
        status?: string;
        updated_at?: string;
        surface?: string;
        purpose?: string;
        round?: number;
        task_label?: string;
        ports?: number[];
        capabilities?: string[];
        execution_mode?: string;
        pid?: number | null;
        timeout_seconds?: number | null;
        streaming?: boolean;
      }>;
      task_id: string;
    }>('GET', '/agent/pentest/logs', undefined, { task_id: taskId });
  }

  async pentestHistory() {
    return this.request<{
      history: Array<{
        task_id: string;
        target: string;
        start_time: string;
        status: string;
        phase: string;
        findings_count: number;
        vuln_count: number;
        actions_count: number;
      }>;
      total: number;
    }>('GET', '/agent/history');
  }

  async pentestDeleteHistory(taskId: string) {
    return this.request('DELETE', `/agent/history/${taskId}`);
  }

  // ==================== 加密 & 设备信息 ====================

  async getRsaPublicKey() {
    const result = await this.request('GET', '/crypto/rsa-public-key');
    return result.public_key;
  }

  async getDeviceUuid() {
    return this.request('GET', '/device/uuid');
  }

}

// 导出单例
export const pythonApi = new PythonApi();

// 导出类以便自定义配置
export { PythonApi };

export default pythonApi;
