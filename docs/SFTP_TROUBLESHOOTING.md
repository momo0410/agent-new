# SFTP "Failed to fetch" 错误解决方案

## 问题描述

访问 SFTP 页面时报错：`获取文件列表失败：TypeError: Failed to fetch`

## 根本原因

SFTP 功能依赖于 SSH 连接。在没有建立 SSH 连接的情况下访问 SFTP 页面，后端会返回 500 错误。

## 解决方案

### 方案 1：先建立 SSH 连接（推荐）

1. **连接到 SSH 服务器**
   - 打开应用
   - 进入 SSH 连接管理页面
   - 添加或选择一个 SSH 连接
   - 点击"连接"按钮

2. **验证连接状态**
   - 确保 SSH 连接成功
   - 查看状态栏显示已连接

3. **访问 SFTP 页面**
   - 现在可以正常访问 SFTP 页面了

### 方案 2：检查后端服务

如果已经建立 SSH 连接但仍然报错，请检查 Python 后端是否正常运行：

```bash
# Windows PowerShell
cd src-python
python run.py
```

后端应该运行在 `http://127.0.0.1:3001`

### 方案 3：使用诊断工具

运行诊断脚本检查 SFTP 连接：

```bash
cd src-python
python diagnose_sftp.py
```

## 技术细节

### API 调用流程

```
前端 SFTP 页面
    ↓
sftpManager.refreshFileList()
    ↓
invoke('sftp_list_files', { path: '/' })
    ↓
shims/@tauri-apps/api/core.ts (invoke adapter)
    ↓
python-api.config.ts (HTTP POST /api/v1/sftp/list-files)
    ↓
Python FastAPI Backend (src-python/app/routers/api.py)
    ↓
SSHManager.list_sftp_files()
    ↓
AsyncSSH SFTP Client
    ↓
远程服务器文件系统
```

### 错误处理

当前代码在以下情况会报错：

1. **没有 SSH 连接**: `ConnectionError("没有活动的 SSH 连接")`
2. **路径不存在**: `FileNotFoundError`
3. **权限不足**: `PermissionError`
4. **后端未运行**: `ConnectionError` (Failed to fetch)

### 改进建议

建议在 `sftpManager.ts` 中添加更友好的错误提示：

```typescript
async refreshFileList(): Promise<void> {
  if (!sshConnectionManager.isConnected()) {
    console.warn('SSH 未连接，无法刷新 SFTP 文件列表');
    // 显示友好的提示信息
    (window as any).showNotification?.(
      '请先建立 SSH 连接，然后再访问 SFTP 页面',
      'warning'
    );
    return;
  }

  try {
    const files = await invoke('sftp_list_files', {
      path: this.currentPath
    });
    // ... 处理文件列表
  } catch (error) {
    console.error('获取 SFTP 文件列表失败:', error);
    
    // 根据错误类型显示不同的提示
    let message = '获取文件列表失败';
    if (error.message?.includes('没有活动的 SSH 连接')) {
      message = 'SSH 连接已断开，请重新连接';
    } else if (error.message?.includes('Failed to fetch')) {
      message = '无法连接到后端服务，请确保 Python 后端正在运行';
    }
    
    (window as any).showNotification?.(message, 'error');
  }
}
```

## 快速测试

使用以下命令快速测试 API：

```bash
cd src-python
python test_sftp_api.py
```

## 常见问题

### Q: 如何知道后端是否正在运行？

A: 检查端口 3001 是否被监听：

```bash
# Windows
netstat -ano | findstr :3001

# Linux/Mac
lsof -i :3001
```

### Q: 后端启动失败怎么办？

A: 检查 Python 依赖是否安装：

```bash
cd src-python
pip install -r requirements.txt
```

### Q: 连接超时怎么办？

A: 检查防火墙设置，确保允许端口 3001 的入站连接。

### Q: 能看到 SSH 连接但 SFTP 不可用？

A: 某些 SSH 服务器可能禁用了 SFTP 子系统。检查远程服务器的 SSH 配置：

```bash
# 在远程服务器上执行
sudo grep -i sftp /etc/ssh/sshd_config
```

确保包含以下行：
```
Subsystem sftp /usr/lib/openssh/sftp-server
```

---

**最后更新**: 2026-04-15
