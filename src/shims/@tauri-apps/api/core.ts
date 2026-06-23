/**
 * @tauri-apps/api/core shim
 * # Tauri invoke 替换为 Python FastAPI HTTP 调用
 */

import pythonApi from '../../../config/python-api.config';

/**
 * 兼容 Tauri invoke 的适配器函数 */
export async function invoke<T = any>(cmd: string, args?: Record<string, any>): Promise<T> {
  const authType = args?.authType ?? args?.auth_type;
  const keyPath = args?.keyPath ?? args?.key_path;
  const keyPassphrase = args?.keyPassphrase ?? args?.key_passphrase;
  const certificatePath = args?.certificatePath ?? args?.certificate_path;
  const encryptedPassword = args?.encryptedPassword ?? args?.encrypted_password;

  const commandMap: Record<string, (...params: any[]) => Promise<any>> = {
    // 窗口控制
    minimize_window: () => pythonApi.minimizeWindow(),
    toggle_maximize: () => pythonApi.toggleMaximize(),
    close_window: () => pythonApi.closeWindow(),
    open_devtools: () => pythonApi.openDevtools(),

    // 主题管理
    get_theme_settings: () => pythonApi.getThemeSettings(),
    set_current_theme: () => pythonApi.setCurrentTheme(args?.theme),

    // 设置管理
    get_app_settings: () => pythonApi.getAppSettings(),
    save_app_settings: () => pythonApi.saveAppSettings(args?.new_settings || args),
    read_settings_file: () => pythonApi.readSettingsFile(),
    write_settings_file: () => pythonApi.writeSettingsFile(args?.content),
    get_system_fonts: () => pythonApi.getSystemFonts(),

    // SSH 连接管理
    load_ssh_connections: () => pythonApi.loadSshConnections(),
    save_ssh_connections: () => pythonApi.saveSshConnections(args?.connections),
    encrypt_password: () => pythonApi.encryptPassword(args?.password),
    decrypt_password: () => pythonApi.decryptPassword(encryptedPassword),

    ssh_connect_with_auth: () => pythonApi.sshConnectWithAuth({
      host: args?.host, port: args?.port, username: args?.username,
      authType, password: args?.password,
      keyPath, keyPassphrase,
      certificatePath,
    }),

    ssh_test_connection: () => pythonApi.sshTestConnection({
      host: args?.host, port: args?.port, username: args?.username,
      authType, password: args?.password,
      keyPath, keyPassphrase,
    }),

    ssh_execute_command: () => pythonApi.sshExecuteCommand(args?.command),
    ssh_disconnect: () => pythonApi.sshDisconnect(),

    // SSH/SFTP 直接命令
    ssh_connect_direct: () => pythonApi.sshConnectDirect(args?.host, args?.port, args?.username, args?.password),
    ssh_disconnect_direct: () => pythonApi.sshDisconnectDirect(),
    ssh_execute_command_direct: () => pythonApi.sshExecuteCommandDirect(args?.command, args?.username),
    ssh_execute_dashboard_command_direct: () => pythonApi.sshExecuteDashboardCommandDirect(args?.command),
    ssh_execute_emergency_command_direct: () => pythonApi.sshExecuteEmergencyCommandDirect(args?.command, args?.username),
    execute_detection_command: () => pythonApi.executeDetectionCommand(args?.command),

    ssh_get_connection_status: () => pythonApi.sshGetConnectionStatus(),
    ssh_get_connection_health: () => pythonApi.sshGetConnectionHealth(),
    test_ssh_performance: () => pythonApi.testSshPerformance(),
    diagnose_shell_performance: () => pythonApi.diagnoseShellPerformance(),
    detect_system_type: () => pythonApi.detectSystemType(),

    // SFTP 文件操作
    sftp_list_files: () => pythonApi.sftpListFiles(args?.path),
    sftp_read_file: () => pythonApi.sftpReadFile(args?.path, args?.max_bytes),
    sftp_write_file: () => pythonApi.sftpWriteFile(args?.path, args?.content),
    sftp_upload: () => pythonApi.sftpUpload(args?.local_path ?? args?.localPath, args?.remote_path ?? args?.remotePath),
    sftp_upload_direct: () => pythonApi.sftpUploadDirect(args?.file, args?.remote_path ?? args?.remotePath, args?.upload_id ?? args?.uploadId),
    sftp_download: () => pythonApi.sftpDownload(args?.remote_path ?? args?.remotePath, args?.local_path ?? args?.localPath),
    sftp_create_directory: () => pythonApi.sftpCreateDirectory(args?.remote_path ?? args?.remotePath),
    sftp_compress: () => pythonApi.sftpCompress(args?.source_path ?? args?.sourcePath, args?.target_path ?? args?.targetPath, args?.format),
    sftp_extract: () => pythonApi.sftpExtract(args?.archive_path ?? args?.archivePath, args?.target_dir ?? args?.targetDir, args?.overwrite),
    sftp_chmod: () => pythonApi.sftpChmod(args?.path, args?.mode),
    sftp_get_file_details: () => pythonApi.sftpGetFileDetails(args?.path),
    save_temp_file: () => pythonApi.saveTempFile(args?.file_name ?? args?.fileName, args?.data),

    // 文件安全分析
    sftp_file_analysis: () => pythonApi.sftpFileAnalysis(args?.path),
    sftp_file_analysis_independent: () => pythonApi.sftpFileAnalysisIndependent(args?.path, args?.action),

    // Bash 环境 & 命令补全
    get_bash_environment_info: () => pythonApi.getBashEnvironmentInfo(),
    get_command_completion: () => pythonApi.getCommandCompletion(args?.input),

    // 安全检测命令
    detect_port_scan: () => pythonApi.detectPortScan(),
    detect_user_audit: () => pythonApi.detectUserAudit(),
    detect_backdoor: () => pythonApi.detectBackdoor(),
    detect_process_analysis: () => pythonApi.detectProcessAnalysis(),
    detect_file_permission: () => pythonApi.detectFilePermission(),
    detect_ssh_audit: () => pythonApi.detectSshAudit(),
    detect_log_analysis: () => pythonApi.detectLogAnalysis(),
    detect_firewall_check: () => pythonApi.detectFirewallCheck(),
    detect_cpu_test: () => pythonApi.detectCpuTest(),
    detect_memory_test: () => pythonApi.detectMemoryTest(),
    detect_disk_test: () => pythonApi.detectDiskTest(),
    detect_network_test: () => pythonApi.detectNetworkTest(),

    // 基线检测
    detect_password_policy: () => pythonApi.detectPasswordPolicy(),
    detect_sudo_config: () => pythonApi.detectSudoConfig(),
    detect_pam_config: () => pythonApi.detectPamConfig(),
    detect_account_lockout: () => pythonApi.detectAccountLockout(),
    detect_selinux_status: () => pythonApi.detectSelinuxStatus(),
    detect_kernel_params: () => pythonApi.detectKernelParams(),
    detect_system_updates: () => pythonApi.detectSystemUpdates(),
    detect_unnecessary_services: () => pythonApi.detectUnnecessaryServices(),
    detect_auto_start_services: () => pythonApi.detectAutoStartServices(),
    detect_audit_config: () => pythonApi.detectAuditConfig(),
    detect_history_audit: () => pythonApi.detectHistoryAudit(),
    detect_ntp_config: () => pythonApi.detectNtpConfig(),
    detect_dns_config: () => pythonApi.detectDnsConfig(),

    // SSH 终端管理
    ssh_create_terminal_session: () => {
      console.log('[core.ts] ssh_create_terminal_session called with args:', args);
      return pythonApi.sshCreateTerminalSession(args?.terminal_id, args?.cols, args?.rows);
    },
    ssh_close_terminal_session: () => pythonApi.sshCloseTerminalSession(args?.terminal_id ?? args?.terminalId),
    ssh_close_all_terminal_sessions: () => pythonApi.sshCloseAllTerminalSessions(),
    ssh_send_input: () => pythonApi.sshSendInput(args?.terminal_id ?? args?.terminalId, args?.data),
    ssh_get_completion: () => pythonApi.sshGetCompletion(args?.input),

    // 日志分析
    read_system_log: () => pythonApi.readSystemLog({
      logPath: args?.log_path ?? args?.logPath,
      page: args?.page,
      pageSize: args?.page_size ?? args?.pageSize,
      filter: args?.filter,
      dateFilter: args?.date_filter ?? args?.dateFilter,
      levelFilter: args?.level_filter ?? args?.levelFilter,
    }),
    read_journalctl_log: () => pythonApi.readJournalctlLog({
      page: args?.page,
      pageSize: args?.page_size ?? args?.pageSize,
      unit: args?.unit ?? args?.journalUnit,
      filter: args?.filter,
      since: args?.since,
      until: args?.until,
      levelFilter: args?.level_filter ?? args?.levelFilter,
    }),
    list_log_files: () => pythonApi.listLogFiles(),
    get_log_file_info: () => pythonApi.getLogFileInfo(args?.log_path),

    // 加密 & 设备信息
    get_rsa_public_key: () => pythonApi.getRsaPublicKey(),
    get_device_uuid: () => pythonApi.getDeviceUuid(),

  };

  const handler = commandMap[cmd];
  if (handler) {
    return handler() as Promise<T>;
  }

  console.warn(`[tauri-shim] 未映射的命令: ${cmd}`);
  throw new Error(`未映射的命令: ${cmd}`);
}

export default invoke;

