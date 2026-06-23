# Vue 3 + FastAPI 开发规范

> **项目**: SDIT - Linux Emergency Response Tool  
> **技术栈**: Vue 3 + TypeScript + Vite + Python FastAPI  
> **版本**: 2.1.0  
> **更新日期**: 2026-04-20

---

## 📋 目录

1. [项目架构](#1-项目架构)
2. [前端开发规范](#2-前端开发规范)
3. [后端开发规范](#3-后端开发规范)
4. [前后端通信规范](#4-前后端通信规范)
5. [状态管理规范](#5-状态管理规范)
6. [UI/UX 规范](#6-uiux 规范)
7. [构建与部署](#7-构建与部署)
8. [最佳实践](#8-最佳实践)

---

## 1. 项目架构

### 1.1 目录结构

```
SDIT/
├── src/                          # 前端源码
│   ├── components/               # Vue 组件
│   │   └── SSHTerminal.vue      # SSH 终端组件
│   ├── modules/                  # 功能模块
│   │   ├── core/                # 核心模块（app, stateManager）
│   │   ├── ssh/                 # SSH 相关模块
│   │   ├── docker/              # Docker 管理模块
│   │   ├── remote/              # 远程操作模块
│   │   ├── settings/            # 设置管理模块
│   │   ├── system/              # 系统信息模块
│   │   ├── ui/                  # UI 渲染模块
│   │   └── utils/               # 工具函数
│   ├── config/                  # 配置文件 & API 适配器
│   │   ├── api.config.ts       # API 配置
│   │   └── invoke-adapter.ts   # API 调用适配器
│   ├── css/                     # 样式文件
│   ├── types/                   # TypeScript 类型定义
│   ├── main.ts                  # 主入口
│   ├── container-terminal.ts    # 容器终端入口
│   └── vite-env.d.ts           # Vite 环境类型
├── src-python/                  # Python 后端
│   ├── app/
│   │   ├── main.py            # FastAPI 主应用
│   │   ├── routers/           # API 路由
│   │   │   └── api.py        # 主路由文件
│   │   ├── services/          # 业务服务
│   │   │   ├── ssh_manager.py
│   │   │   ├── docker_manager.py
│   │   │   └── ...
│   │   ├── models/            # 数据模型
│   │   └── utils/             # 工具函数
│   └── requirements.txt       # Python 依赖
├── dist/                       # 构建产物
├── public/                     # 静态资源
└── docs/                       # 文档
```

### 1.2 技术架构

```
┌─────────────────┐         HTTP/WebSocket         ┌──────────────────┐
│   Frontend      │ ◄──────────────────────────►   │   Backend        │
│   Vue 3 + TS    │                                │   Python FastAPI │
│   Vite          │                                │                  │
└─────────────────┘                                └──────────────────┘
         │                                                   │
         │                                                   │
         ▼                                                   ▼
┌─────────────────┐                                ┌──────────────────┐
│  UI Components  │                                │   SSH/SFTP       │
│  State Manager  │                                │   Docker API     │
│  xterm.js       │                                │   System Cmds    │
└─────────────────┘                                └──────────────────┘
```

### 1.3 核心模块说明

**前端核心模块**:
- `core/app.ts` - 应用初始化和生命周期管理
- `core/stateManager.ts` - 全局状态管理
- `config/invoke-adapter.ts` - 统一的 API 调用接口

**后端核心模块**:
- `app/main.py` - FastAPI 应用入口
- `app/routers/api.py` - 统一的 API 路由
- `app/services/` - 各业务模块的服务实现

---

## 2. 前端开发规范

### 2.1 TypeScript 规范

```typescript
// ✅ 推荐：使用明确的类型定义
interface ServerInfo {
  name: string;
  host: string;
  port: number;
  username?: string;
}

// ✅ 推荐：使用泛型定义 API 响应
interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
}

// ❌ 避免：过度使用 any
const data: any = await fetchData(); // 不推荐
const data: ServerInfo = await fetchData(); // 推荐
```

### 2.2 Vue 组件规范

```vue
<script setup lang="ts">
// ✅ 推荐：使用 Composition API
import { ref, computed, onMounted } from 'vue';

// 响应式状态
const loading = ref(false);
const serverList = ref<ServerInfo[]>([]);

// 计算属性
const serverCount = computed(() => serverList.value.length);

// 生命周期
onMounted(async () => {
  await loadServers();
});

// 方法
async function loadServers() {
  loading.value = true;
  try {
    const response = await fetch('/api/servers');
    serverList.value = await response.json();
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="server-list">
    <div v-if="loading">加载中...</div>
    <div v-else>
      <div v-for="server in serverList" :key="server.name">
        {{ server.name }}
      </div>
    </div>
  </div>
</template>
```

### 2.3 模块组织规范

```typescript
// ✅ 推荐：模块化组织
// src/modules/ssh/sshManager.ts
export class SSHManager {
  private connection: any = null;
  
  async connect(config: SSHConfig): Promise<void> {
    // 实现
  }
  
  async disconnect(): Promise<void> {
    // 实现
  }
}

// 导出单例
export const sshManager = new SSHManager();
```

### 2.4 导入顺序规范

```typescript
// 1. 外部库
import { ref, computed } from 'vue';
import { marked } from 'marked';

// 2. Tauri API (如使用)
import { invoke } from '@tauri-apps/api/core';

// 3. 内部模块
import { sshManager } from '../ssh/sshManager';
import { stateManager } from '../core/stateManager';

// 4. 样式
import './styles/component.css';
```

---

## 3. 后端开发规范

### 3.1 FastAPI 路由规范

```python
# ✅ 推荐：使用路由分类
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.post("/ssh/connect")
async def ssh_connect(config: SSHConfig):
    """建立 SSH 连接"""
    try:
        result = await ssh_manager.connect(config)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ssh/status")
async def ssh_status():
    """获取 SSH 连接状态"""
    return {"connected": ssh_manager.is_connected()}
```

### 3.2 Pydantic 模型规范

```python
# ✅ 推荐：使用 Pydantic 定义数据模型
from pydantic import BaseModel, Field

class SSHConfig(BaseModel):
    host: str = Field(..., description="服务器地址")
    port: int = Field(default=22, ge=1, le=65535)
    username: str
    password: str | None = None
    key_path: str | None = None
    key_passphrase: str | None = None

class SSHResponse(BaseModel):
    success: bool
    data: dict | None = None
    message: str | None = None
```

### 3.3 异步编程规范

```python
# ✅ 推荐：使用 async/await
async def ssh_connect(config: SSHConfig):
    """异步 SSH 连接"""
    async with asyncssh.connect(
        host=config.host,
        port=config.port,
        username=config.username,
        password=config.password,
    ) as conn:
        return await conn.run('uname -a')

# ❌ 避免：阻塞异步操作
def ssh_connect(config):  # 不推荐
    return asyncio.run(async_ssh_connect(config))
```

### 3.4 错误处理规范

```python
# ✅ 推荐：详细的错误处理
from fastapi import HTTPException

async def execute_command(command: str):
    try:
        result = await ssh_manager.execute(command)
        return {"success": True, "data": result}
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail="SSH 连接断开")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail="权限不足")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行失败：{str(e)}")
```

---

## 4. 前后端通信规范

### 4.1 API 调用规范

```typescript
// src/config/invoke-adapter.ts
export async function invoke(cmd: string, args?: Record<string, any>): Promise<any> {
  const response = await fetch('http://127.0.0.1:3001/api/invoke', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cmd, args }),
  });
  
  if (!response.ok) {
    throw new Error(`API 调用失败：${response.statusText}`);
  }
  
  return await response.json();
}
```

### 4.2 WebSocket 通信规范

```typescript
// 终端 WebSocket 连接
class TerminalWebSocket {
  private ws: WebSocket | null = null;
  
  connect(terminalId: string): void {
    this.ws = new WebSocket(`ws://127.0.0.1:3001/ws/terminal/${terminalId}`);
    
    this.ws.onmessage = (event) => {
      // 处理终端输出
      terminal.write(event.data);
    };
  }
  
  send(data: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    }
  }
}
```

### 4.3 错误处理规范

```typescript
// ✅ 推荐：统一的错误处理
async function callAPI(cmd: string, args: any) {
  try {
    return await invoke(cmd, args);
  } catch (error) {
    console.error(`API 调用失败 [${cmd}]:`, error);
    
    // 显示错误提示
    showError(`操作失败：${error.message}`);
    
    // 记录日志
    await logError(cmd, error);
    
    throw error;
  }
}
```

---

## 5. 状态管理规范

### 5.1 StateManager 使用规范

```typescript
// src/modules/core/stateManager.ts
export class StateManager {
  private state: AppState;
  private listeners: Set<() => void> = new Set();
  
  constructor() {
    this.state = {
      theme: 'light',
      isConnected: false,
      currentPage: 'dashboard',
      loading: false,
    };
  }
  
  // 更新状态
  update<K extends keyof AppState>(key: K, value: AppState[K]): void {
    this.state[key] = value;
    this.notify();
  }
  
  // 获取状态
  getState(): AppState {
    return { ...this.state };
  }
  
  // 订阅变化
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  
  // 通知所有订阅者
  private notify(): void {
    this.listeners.forEach(listener => listener());
  }
}
```

### 5.2 状态更新最佳实践

```typescript
// ✅ 推荐：批量更新状态
async function loadServerInfo() {
  stateManager.update('loading', true);
  try {
    const info = await fetchServerInfo();
    stateManager.update('serverInfo', info);
    stateManager.update('isConnected', true);
  } catch (error) {
    stateManager.update('isConnected', false);
    throw error;
  } finally {
    stateManager.update('loading', false);
  }
}

// ❌ 避免：分散的状态更新
async function loadServerInfo() {
  stateManager.update('loading', true);
  // ... 一些代码
  stateManager.update('serverInfo', info); // 可能在异常时不执行
  stateManager.update('loading', false); // 可能在异常时不执行
}
```

---

## 6. UI/UX 规范

### 6.1 组件设计原则

1. **单一职责**: 每个组件只负责一个功能
2. **可复用性**: 通用组件应独立于业务逻辑
3. **性能优化**: 使用虚拟滚动、懒加载等技术
4. **无障碍访问**: 遵循 WCAG 标准

### 6.2 响应式设计

```css
/* ✅ 推荐：移动优先的响应式设计 */
.component {
  /* 移动端样式 (默认) */
  padding: 1rem;
}

@media (min-width: 768px) {
  .component {
    /* 平板端样式 */
    padding: 2rem;
  }
}

@media (min-width: 1024px) {
  .component {
    /* 桌面端样式 */
    padding: 3rem;
  }
}
```

### 6.3 加载状态处理

```typescript
// ✅ 推荐：优雅的加载状态
const LoadingComponent = () => (
  <div class="loading-container">
    <Spinner size="large" />
    <p>加载中...</p>
  </div>
);

// 骨架屏
const Skeleton = () => (
  <div class="skeleton">
    <div class="skeleton-line" />
    <div class="skeleton-line" />
    <div class="skeleton-line" />
  </div>
);
```

---

## 7. 构建与部署

### 7.1 开发环境

```bash
# 1. 启动 Python 后端
cd src-python
python run.py

# 2. 启动前端开发服务器 (新终端)
npm run dev
```

### 7.2 生产构建

```bash
# 1. 构建前端
npm run build

# 2. 构建产物在 dist/ 目录
# - index.html
# - assets/*.js
# - assets/*.css

# 3. 部署
# 方案 A: 使用 Python 后端提供静态文件
# 方案 B: 使用 Nginx 托管 dist/ 目录
```

### 7.3 性能优化

```typescript
// vite.config.ts
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['vue', 'marked'],
          'xterm': ['xterm', 'xterm-addon-fit'],
        },
      },
    },
    chunkSizeWarningLimit: 500,
  },
});
```

---

## 8. 最佳实践

### 8.1 安全最佳实践

1. **输入验证**: 后端验证所有输入
2. **CORS 配置**: 限制跨域请求来源
3. **敏感信息**: 不提交密钥和凭证到版本控制
4. **错误处理**: 不泄露敏感信息

### 8.2 性能最佳实践

1. **代码分割**: 使用动态导入分割大型模块
2. **懒加载**: 按需加载组件和资源
3. **缓存策略**: 合理使用浏览器缓存
4. **WebSocket**: 实时数据使用 WebSocket 而非轮询

### 8.3 调试技巧

**前端调试**:
```typescript
// 启用调试日志
const DEBUG = true;

function debugLog(...args: any[]) {
  if (DEBUG) {
    console.log('[DEBUG]', ...args);
  }
}
```

**后端调试**:
```python
# 使用 logging 模块
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def some_function():
    logger.debug("调试信息")
    logger.info("普通信息")
    logger.error("错误信息")
```

### 8.4 测试建议

**前端测试 (Vitest)**:
```typescript
// __tests__/stateManager.test.ts
import { describe, it, expect } from 'vitest';
import { StateManager } from '../core/stateManager';

describe('StateManager', () => {
  it('should initialize with default state', () => {
    const manager = new StateManager();
    expect(manager.getState().theme).toBe('light');
  });
});
```

**后端测试 (pytest)**:
```python
# tests/test_api.py
import pytest
from app.main import app

@pytest.mark.asyncio
async def test_health_check():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://test/health")
        assert response.status_code == 200
```

---

## 附录

### A. 常用命令

```bash
# 开发
npm run dev              # 启动前端
python run.py           # 启动后端

# 构建
npm run build           # 生产构建
npm run build -- --watch  # 监听构建

# 类型检查
npm run type-check      # TypeScript 检查

# 代码质量
npm run lint            # ESLint 检查
```

### B. 资源链接

- [Vue 3 文档](https://vuejs.org)
- [TypeScript 文档](https://www.typescriptlang.org)
- [FastAPI 文档](https://fastapi.tiangolo.com)
- [Vite 文档](https://vitejs.dev)
- [xterm.js 文档](https://xtermjs.org)

---

**最后更新**: 2026-04-15  
**维护者**: SDIT Team
