<template>
  <div class="ssh-terminal-container">
    <!-- 终端标签页 -->
    <div class="terminal-tabs" v-if="terminals.length > 0">
      <div class="tabs-left">
        <div
          v-for="terminal in terminals"
          :key="terminal.id"
          :class="['terminal-tab', { active: activeTerminalId === terminal.id }]"
          @click="switchTerminal(terminal.id)"
        >
          <span class="tab-title">{{ terminal.name }}</span>
          <span
            class="tab-close"
            @click.stop="closeTerminal(terminal.id)"
            v-if="terminals.length > 1"
          >×</span>
        </div>
        <div class="terminal-tab add-tab" @click="createNewTerminal">
          <icon-plus
            theme="multi-color"
            size="12"
            :fill="['#cccccc', '#2F88FF', '#FFF', '#43CCF8']"
            strokeLinejoin="bevel"
          />
        </div>
      </div>
      <div class="tabs-right">
        <button
          class="toolbar-btn"
          @click="clearCurrentTerminal"
          title="清屏 (Ctrl+Shift+L)"
        >
          <icon-clear
            theme="multi-color"
            size="12"
            :fill="['#cccccc', '#2F88FF', '#FFF', '#43CCF8']"
            strokeLinejoin="bevel"
          />
        </button>
        <button
          class="toolbar-btn"
          @click="reconnectCurrentTerminal"
          title="重连 (Ctrl+Shift+R)"
        >
          <icon-refresh
            theme="multi-color"
            size="12"
            :fill="['#cccccc', '#2F88FF', '#FFF', '#43CCF8']"
            strokeLinejoin="bevel"
          />
        </button>
        <button
          class="toolbar-btn ai-btn"
          @click="toggleAIInput"
          title="AI助手 (Ctrl+I)"
          :class="{ active: showAIInput }"
        >
          <icon-robot
            theme="multi-color"
            size="12"
            :fill="['#cccccc', '#2F88FF', '#FFF', '#43CCF8']"
            strokeLinejoin="bevel"
          />
        </button>
        <select
          v-model="selectedUsername"
          class="account-selector"
          title="选择执行命令的账号"
          @change="handleAccountChange"
        >
          <option value="">默认账号</option>
          <option
            v-for="account in accounts"
            :key="account.username"
            :value="account.username"
          >
            {{ account.username }}{{ account.description ? ` (${account.description})` : '' }}{{ account.is_default ? ' [默认]' : '' }}
          </option>
        </select>
        <span class="connection-status" :class="connectionStatus">
          {{ connectionStatusText }}
        </span>
      </div>
    </div>



    <!-- 终端内容区域 -->
    <div class="terminal-content" @contextmenu="handleContextMenu">
      <div
        v-for="terminal in terminals"
        :key="terminal.id"
        :data-terminal-id="terminal.id"
        :class="['terminal-instance', { active: activeTerminalId === terminal.id }]"
        :style="{ display: activeTerminalId === terminal.id ? 'block' : 'none' }"
      ></div>

      <!-- 无终端时的提示 -->
      <div v-if="terminals.length === 0" class="no-terminal">
        <div class="no-terminal-content">
          <icon-computer
            theme="multi-color"
            size="48"
            :fill="['#666666', '#2F88FF', '#FFF', '#43CCF8']"
            strokeLinejoin="bevel"
          />
          <h3>暂无终端会话</h3>
          <p>点击下方按钮创建新的 SSH 终端</p>
          <button class="create-terminal-btn" @click="createNewTerminal">
            <icon-plus
              theme="multi-color"
              size="16"
              :fill="['#FFFFFF', '#2F88FF', '#FFF', '#43CCF8']"
              strokeLinejoin="bevel"
            />
            创建终端
          </button>
        </div>
      </div>
    </div>

    <!-- 自定义右键菜单 -->
    <div
      v-if="showContextMenu"
      class="context-menu"
      :style="{ left: contextMenuPosition.x + 'px', top: contextMenuPosition.y + 'px' }"
      @click.stop
    >
      <div class="context-menu-item" @click="copySelection">
        <icon-copy
          theme="multi-color"
          size="12"
          :fill="['#e4e4e7', '#2F88FF', '#FFF', '#43CCF8']"
          strokeLinejoin="bevel"
        />
        复制
      </div>
      <div class="context-menu-item" @click="pasteFromClipboard">
        <icon-clipboard
          theme="multi-color"
          size="12"
          :fill="['#e4e4e7', '#2F88FF', '#FFF', '#43CCF8']"
          strokeLinejoin="bevel"
        />
        粘贴
      </div>
      <div
        v-if="selectedText"
        class="context-menu-item context-menu-ai"
        @click="sendSelectionToAI"
      >
        <icon-robot
          theme="multi-color"
          size="12"
          :fill="['#4ade80', '#2F88FF', '#FFF', '#43CCF8']"
          strokeLinejoin="bevel"
        />
        发送到AI助手
      </div>
    </div>

    <!-- AI输入框 - 悬浮在终端上方 -->
    <div v-if="showAIInput" class="ai-floating-container">
      <!-- 选中内容提示 -->
      <div v-if="selectedContentHint" class="ai-selection-hint">
        <div class="selection-hint-content">
          <icon-check
            theme="multi-color"
            size="10"
            :fill="['#4ade80', '#2F88FF', '#FFF', '#43CCF8']"
            strokeLinejoin="bevel"
          />
          <span>已选取: {{ selectedContentHint }}</span>
          <button class="clear-selection-btn" @click="clearSelection" title="清除选择">
            <icon-close
              theme="multi-color"
              size="8"
              :fill="['#f87171', '#2F88FF', '#FFF', '#43CCF8']"
              strokeLinejoin="bevel"
            />
          </button>
        </div>
      </div>

      <div class="ai-compact-panel">
        <div
          class="ai-header"
          @mousedown="startDragging"
        >
          <div class="ai-status">
            <div class="ai-indicator"></div>
            <span class="ai-text">{{ currentAIProvider }} • Linux专家</span>
          </div>
          <button class="ai-close-btn" @click="toggleAIInput" title="关闭 (Ctrl+I)">
            <icon-close
              theme="multi-color"
              size="10"
              :fill="['#a1a1aa', '#2F88FF', '#FFF', '#43CCF8']"
              strokeLinejoin="bevel"
            />
          </button>
        </div>

        <div class="ai-input-section">
          <textarea
            ref="aiInput"
            v-model="aiInputText"
            class="ai-textarea"
            placeholder="描述需要的Linux命令..."
            @keydown="handleAIInputKeydown"
            rows="2"
          ></textarea>
          <div class="ai-input-controls">
            <span class="ai-hint">Enter发送 • Ctrl+I关闭</span>
            <div class="ai-right-controls">
              <span class="ai-counter">{{ aiInputText.length }}/300</span>
              <button
                class="ai-send-btn"
                @click="sendAIRequest"
                :disabled="!aiInputText.trim() || aiLoading"
                title="发送"
              >
                <icon-send
                  v-if="!aiLoading"
                  theme="multi-color"
                  size="12"
                  :fill="['#FFFFFF', '#2F88FF', '#FFF', '#43CCF8']"
                  strokeLinejoin="bevel"
                />
                <icon-loading
                  v-else
                  theme="multi-color"
                  size="12"
                  :fill="['#FFFFFF', '#2F88FF', '#FFF', '#43CCF8']"
                  strokeLinejoin="bevel"
                  class="ai-loading"
                />
              </button>
            </div>
          </div>
        </div>

        <div v-if="aiResponse" class="ai-response">
          <div class="ai-response-content">
            <code>{{ aiResponse }}</code>
            <div class="ai-action-buttons">
              <button class="ai-insert-btn" @click="insertAIResponse" title="插入到终端">
                <icon-down
                  theme="multi-color"
                  size="10"
                  :fill="['#4ade80', '#2F88FF', '#FFF', '#43CCF8']"
                  strokeLinejoin="bevel"
                />
                插入
              </button>
              <button class="ai-execute-btn" @click="insertAndExecuteAIResponse" title="插入并执行">
                <icon-play
                  theme="multi-color"
                  size="10"
                  :fill="['#60a5fa', '#2F88FF', '#FFF', '#43CCF8']"
                  strokeLinejoin="bevel"
                />
                执行
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 命令自动补全建议面板 -->
    <div
      v-if="showCommandSuggestions && commandSuggestions.length > 0"
      class="command-suggestions-panel"
      :style="{ left: suggestionsPanelPosition.x + 'px', top: suggestionsPanelPosition.y + 'px' }"
    >
      <div class="suggestions-header">
        <icon-light
          theme="multi-color"
          size="16"
          :fill="['#e4e4e7', '#2F88FF', '#FFF', '#43CCF8']"
          strokeLinejoin="bevel"
        />
        <span>命令建议</span>
        <span class="suggestions-count">({{ commandSuggestions.length }})</span>
      </div>
      <div class="suggestions-list">
        <div
          v-for="(suggestion, index) in commandSuggestions"
          :key="suggestion.command"
          class="suggestion-item"
          :class="{ 'selected': index === selectedSuggestionIndex }"
          @click="selectSuggestion(index)"
        >
          <div class="suggestion-command">{{ suggestion.command }}</div>
          <div class="suggestion-description">{{ suggestion.description }}</div>
          <div class="suggestion-category">{{ getCategoryName(suggestion.category) }}</div>
        </div>
      </div>
      <div class="suggestions-footer">
        <span>↑↓ 选择 • Tab/Enter 确认 • Esc 关闭</span>
      </div>
    </div>

    <!-- 命令提示面板 -->
    <div
      v-if="showCommandHint && currentCommandHint"
      class="command-hint-panel"
      :class="{ 'hint-visible': showCommandHint }"
    >
      <div class="hint-header">
        <div class="hint-title">
          <icon-info
            theme="multi-color"
            size="16"
            :fill="['#e4e4e7', '#2F88FF', '#FFF', '#43CCF8']"
            strokeLinejoin="bevel"
          />
          <span class="command-name">{{ currentCommandHint.command }}</span>
          <span class="command-category">{{ getCategoryName(currentCommandHint.category) }}</span>
        </div>
        <button class="hint-close" @click="hideCommandHint">
          <icon-close
            theme="multi-color"
            size="14"
            :fill="['#e4e4e7', '#2F88FF', '#FFF', '#43CCF8']"
            strokeLinejoin="bevel"
          />
        </button>
      </div>

      <div class="hint-content">
        <div class="hint-description">
          {{ currentCommandHint.description }}
        </div>

        <div class="hint-usage">
          <strong>用法:</strong> <code>{{ currentCommandHint.usage }}</code>
        </div>

        <div v-if="currentCommandHint.commonOptions" class="hint-options">
          <strong>常用选项:</strong>
          <div class="options-list">
            <span
              v-for="option in currentCommandHint.commonOptions"
              :key="option"
              class="option-tag"
            >{{ option }}</span>
          </div>
        </div>

        <div class="hint-examples">
          <strong>示例:</strong>
          <div class="examples-list">
            <div
              v-for="(example, index) in currentCommandHint.examples"
              :key="index"
              class="example-item"
            >
              <code>{{ example }}</code>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import { invoke } from '../shims/@tauri-apps/api/core'
import { commandHintsManager, type CommandHint } from '../modules/ssh/commandHints'
import { streamAIProxyMessages, type AIProviderConfig } from '../modules/utils/aiProxy'
import { aiService } from '../modules/ai/aiService'

interface TerminalInstance {
  id: string
  name: string
  terminal: Terminal
  fitAddon: FitAddon
  isConnected: boolean
  connectionInfo?: {
    host: string
    port: number
    username: string
  }
  // 事件反订阅句柄
  unlisten?: () => void
  // 错误计数器用于错误处理
  errorCount?: number
  // ResizeObserver引用，用于清理
  resizeObserver?: ResizeObserver
  // 终端实时 WebSocket
  terminalSocket?: WebSocket
  // WebSocket 自动重连计时器
  outputReconnectTimer?: ReturnType<typeof setTimeout>
  // 当前终端通道的重连次数
  wsReconnectAttempts?: number
  // WebSocket 心跳 ping 定时器
  wsPingTimer?: ReturnType<typeof setInterval>
  // WebSocket 无消息超时看门狗
  wsWatchdogTimer?: ReturnType<typeof setInterval>
  // 最近一次收到 WebSocket 消息的时间戳
  wsLastMessageTime?: number
}

// 响应式数据
const terminals = ref<TerminalInstance[]>([])
const activeTerminalId = ref<string>('')
const connectionStatus = ref<'connected' | 'disconnected' | 'connecting'>('disconnected')
const textEncoder = new TextEncoder()
const TERMINAL_WS_BASE = (() => {
  const fromEnv = import.meta.env.VITE_API_BASE_URL?.trim()
  if (fromEnv && /^https?:\/\//i.test(fromEnv)) {
    return fromEnv
      .replace(/^http/i, 'ws')
      .replace(/\/api\/v1\/?$/i, '')
  }
  return 'ws://127.0.0.1:3001'
})()

// AI助手相关数据
const showAIInput = ref<boolean>(false)
const aiInputText = ref<string>('')
const aiResponse = ref<string>('')
const aiLoading = ref<boolean>(false)
const currentAIProvider = ref<string>('OpenAI')

// AI拖拽相关数据
const isDragging = ref<boolean>(false)
const dragOffset = ref<{ x: number; y: number }>({ x: 0, y: 0 })
const aiPosition = ref<{ x: number; y: number }>({ x: 0, y: 0 })

// 右键菜单相关数据
const showContextMenu = ref<boolean>(false)
const contextMenuPosition = ref<{ x: number; y: number }>({ x: 0, y: 0 })
const selectedText = ref<string>('')
const selectedContentHint = ref<string>('')
const selectedContentPrompt = ref<string>('')

// 账号切换相关数据
const selectedUsername = ref<string>('')
const accounts = ref<any[]>([])

// 发送输入的缓冲（按终端分片，降低高频输入导致的抖动与拥塞）
const inputBuffers = new Map<string, { buf: string; timer: number | null }>()
const reconnecting = ref<boolean>(false)

// 命令提示相关
const showCommandHint = ref<boolean>(false)
const currentCommandHint = ref<CommandHint | null>(null)
const currentInput = ref<string>('')
const hintTimeout = ref<number | null>(null)

// 命令自动补全相关
const showCommandSuggestions = ref<boolean>(false)
const commandSuggestions = ref<CommandHint[]>([])
const selectedSuggestionIndex = ref<number>(-1)
const suggestionsPanelPosition = ref<{ x: number; y: number }>({ x: 0, y: 0 })

const activeTerminal = computed(() =>
  terminals.value.find(t => t.id === activeTerminalId.value)
)

// 计算属性
const connectionStatusText = computed(() => {
  if (connectionStatus.value === 'connected' && activeTerminal.value?.outputReconnectTimer) {
    return 'SSH已连接/通道重连中'
  }

  switch (connectionStatus.value) {
    case 'connected': return '已连接'
    case 'connecting': return '连接中...'
    case 'disconnected': return '未连接'
    default: return '未知状态'
  }
})

// 生成唯一ID
const generateId = (): string => {
  return Date.now().toString(36) + Math.random().toString(36).substring(2)
}

const getTerminalWsUrl = (terminalId: string): string => {
  return `${TERMINAL_WS_BASE}/ws/terminal/${encodeURIComponent(terminalId)}`
}

const isTerminalSocketOpen = (terminalInstance: TerminalInstance): boolean => {
  return terminalInstance.terminalSocket?.readyState === WebSocket.OPEN
}

// 创建新终端
const createNewTerminal = async () => {
  // 如果有其他终端正在创建，等待一下避免并发冲突
  if (terminals.value.length > 0) {
    await new Promise(resolve => setTimeout(resolve, 200))
  }

  const terminalId = generateId()

  // 创建 xterm 实例
  const terminal = new Terminal({
    theme: {
      background: '#1e1e1e',
      foreground: '#d4d4d4',
      cursor: '#ffffff',
      cursorAccent: '#000000',
      selectionBackground: '#264f78',
      selectionForeground: '#ffffff',
      // 标准颜色
      black: '#000000',
      red: '#cd3131',
      green: '#0dbc79',
      yellow: '#e5e510',
      blue: '#2472c8',
      magenta: '#bc3fbc',
      cyan: '#11a8cd',
      white: '#e5e5e5',
      // 高亮颜色
      brightBlack: '#666666',
      brightRed: '#f14c4c',
      brightGreen: '#23d18b',
      brightYellow: '#f5f543',
      brightBlue: '#3b8eea',
      brightMagenta: '#d670d6',
      brightCyan: '#29b8db',
      brightWhite: '#ffffff'
    },
    fontSize: 14,
    fontFamily: '"Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", monospace',
    cursorBlink: true,
    cursorStyle: 'block',
    scrollback: 10000, // 增加滚动缓冲区
    tabStopWidth: 4,
    convertEol: true, // 自动转换行结束符
    allowProposedApi: true, // 允许实验性 API
    macOptionIsMeta: true, // Mac 选项键作为 Meta 键
    rightClickSelectsWord: true, // 右键选择单词
    smoothScrollDuration: 0,
    windowsMode: false
  })

  const fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)

  const terminalInstance: TerminalInstance = {
    id: terminalId,
    name: `终端 ${terminals.value.length + 1}`,
    terminal,
    fitAddon,
    isConnected: false
  }

  terminals.value.push(terminalInstance)
  activeTerminalId.value = terminalId

  // 等待 DOM 更新后初始化终端
  await nextTick()
  initializeTerminal(terminalInstance)
}

// 初始化终端
const initializeTerminal = (terminalInstance: TerminalInstance) => {
  const terminalElement = document.querySelector(`[data-terminal-id="${terminalInstance.id}"]`) as HTMLElement
  if (!terminalElement) {
    console.error('Terminal element not found')
    return
  }

  // 打开终端
  terminalInstance.terminal.open(terminalElement)
  terminalInstance.fitAddon.fit()

  // 显示欢迎信息


  // 设置终端输入处理
  terminalInstance.terminal.onData((data) => {
    handleTerminalInput(terminalInstance.id, data)
  })

  // 监听窗口大小变化
  const resizeObserver = new ResizeObserver(() => {
    try {
      if (terminalInstance.terminal && terminalInstance.fitAddon &&
          terminalInstance.terminal.element &&
          terminalInstance.terminal.element.offsetParent) {
        terminalInstance.fitAddon.fit()
      }
    } catch (error) {
      console.warn('终端 resize 失败:', error)
    }
  })
  resizeObserver.observe(terminalElement)

  // 保存resizeObserver引用以便后续清理
  terminalInstance.resizeObserver = resizeObserver

  // 尝试连接到当前活动的 SSH 连接
  connectToSSH(terminalInstance)
}

// Enhanced input processing with adaptive throttling
interface InputBuffer {
  buf: string
  timer: number | null
  lastFlush: number
  inputRate: number
  priority: 'control' | 'navigation' | 'normal' | 'bulk'
}

// Input classification for priority handling
const classifyInput = (data: string): 'control' | 'navigation' | 'normal' | 'bulk' => {
  if (data.length === 0) return 'normal'

  // Control characters (Ctrl+C, Enter, Backspace, Delete, etc.)
  if (data.length === 1) {
    const code = data.charCodeAt(0)
    if (code === 3 || code === 4 || code === 26) return 'control' // Ctrl+C, Ctrl+D, Ctrl+Z
    if (code === 13 || code === 10) return 'control' // Enter
    if (code === 127 || code === 8) return 'control' // Backspace/Delete - 立即发送避免缓冲
    if (code === 9) return 'control' // Tab
  }

  // Escape sequences (arrow keys, function keys) - 也需要立即发送
  if (data.startsWith('\x1b[') || data.startsWith('\x1bO')) return 'control'

  // Large data (paste operations)
  if (data.length > 50) return 'bulk'

  return 'normal'
}

const stopReceivingOutput = (
  terminalInstance: TerminalInstance,
  options: { closeSocket?: boolean } = {}
) => {
  const { closeSocket = true } = options

  if (terminalInstance.outputReconnectTimer) {
    clearTimeout(terminalInstance.outputReconnectTimer)
    terminalInstance.outputReconnectTimer = undefined
  }

  if (terminalInstance.wsPingTimer) {
    clearInterval(terminalInstance.wsPingTimer)
    terminalInstance.wsPingTimer = undefined
  }

  if (terminalInstance.wsWatchdogTimer) {
    clearInterval(terminalInstance.wsWatchdogTimer)
    terminalInstance.wsWatchdogTimer = undefined
  }

  if (closeSocket && terminalInstance.terminalSocket) {
    try {
      const socket = terminalInstance.terminalSocket as WebSocket & { __expectedClose?: boolean }
      terminalInstance.terminalSocket = undefined
      socket.__expectedClose = true
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close()
      }
    } catch (error) {
      console.warn('关闭终端 WebSocket 失败:', error)
    }
  }
}

const writeTerminalPayload = (terminalInstance: TerminalInstance, payload: unknown) => {
  if (payload == null) return

  if (typeof payload === 'string') {
    if (payload) terminalInstance.terminal.write(payload)
    return
  }

  if (payload instanceof ArrayBuffer) {
    terminalInstance.terminal.write(new TextDecoder().decode(payload))
    return
  }

  if (payload instanceof Blob) {
    payload.text().then(text => {
      if (text) terminalInstance.terminal.write(text)
    }).catch(() => {})
    return
  }

  if (payload instanceof Uint8Array) {
    terminalInstance.terminal.write(new TextDecoder().decode(payload))
  }
}

const tryRestoreBackendSshConnection = async (
  terminalInstance: TerminalInstance
): Promise<boolean> => {
  const sshConnectionManager = (window as any).sshConnectionManager
  const configManager = (window as any).app?.sshManager

  if (!sshConnectionManager || typeof sshConnectionManager.connect !== 'function') {
    return false
  }

  const statusInfo = sshConnectionManager.getConnectionStatus?.() || null
  const fallbackInfo = terminalInstance.connectionInfo || statusInfo
  if (!fallbackInfo?.host || !fallbackInfo?.port || !fallbackInfo?.username) {
    return false
  }

  try {
    // 优先读取持久化配置中的密文密码，确保重连可自动进行
    let encryptedPassword: string | undefined
    if (configManager && typeof configManager.getConnections === 'function') {
      const savedConnection = configManager.getConnections?.().find(
        (conn: any) =>
          conn.host === fallbackInfo.host &&
          Number(conn.port) === Number(fallbackInfo.port) &&
          conn.username === fallbackInfo.username
      )
      encryptedPassword = savedConnection?.encryptedPassword
    }

    if (!encryptedPassword) {
      return false
    }

    const password = await invoke('decrypt_password', { encryptedPassword }) as string
    if (!password) return false

    await sshConnectionManager.connect(
      fallbackInfo.host,
      Number(fallbackInfo.port),
      fallbackInfo.username,
      password
    )

    return true
  } catch (error) {
    console.warn('SSH终端自动恢复主连接失败:', error)
    return false
  }
}

const recoverFromSocketFatalClose = async (
  terminalInstance: TerminalInstance,
  event: CloseEvent
) => {
  // 防止并发恢复导致重连风暴
  if ((terminalInstance as any)._fatalRecoveryInProgress) {
    return
  }
  ;(terminalInstance as any)._fatalRecoveryInProgress = true

  const reason = event.reason || `code=${event.code || 'unknown'}`
  const reasonText = event.reason || ''
  const needsSessionRecreate = ['没有活动的 SSH 连接', 'SSH会话已丢失', 'SSH通道异常', 'SSH写入失败']
    .some(keyword => reasonText.includes(keyword))

  try {
    // 先确认后端SSH主连接是否仍然在线
    const liveStatus = await invoke('ssh_get_connection_status').catch(() => null) as any
    if (liveStatus?.connected) {
      terminalInstance.connectionInfo = {
        host: liveStatus.host,
        port: liveStatus.port,
        username: liveStatus.username
      }
      connectionStatus.value = 'connected'

      // 会话级异常时优先重建终端会话，避免仅重连WS导致循环断开
      if (needsSessionRecreate) {
        terminalInstance.terminal.writeln('\r\n\x1b[33m检测到SSH主连接仍在线，正在自动重建终端会话...\x1b[0m')
        terminalInstance.isConnected = false
        await connectToSSH(terminalInstance)
        return
      }

      terminalInstance.terminal.writeln('\r\n\x1b[33m检测到SSH主连接仍在线，正在自动恢复终端通道...\x1b[0m')
      scheduleOutputReconnect(terminalInstance, reason)
      return
    }

    terminalInstance.terminal.writeln('\r\n\x1b[33m检测到SSH主连接异常，正在尝试自动恢复主连接...\x1b[0m')
    const restored = await tryRestoreBackendSshConnection(terminalInstance)
    if (restored) {
      terminalInstance.isConnected = false
      connectionStatus.value = 'connecting'
      terminalInstance.terminal.writeln('\x1b[32mSSH主连接已恢复，正在重建终端会话...\x1b[0m')
      await connectToSSH(terminalInstance)
      return
    }

    terminalInstance.isConnected = false
    connectionStatus.value = 'disconnected'
    terminalInstance.terminal.writeln('\r\n\x1b[31mSSH 连接已断开，请按 Ctrl+Shift+R 手动重连\x1b[0m')
    console.warn(`SSH终端 WebSocket 关闭(SSH断开): ${terminalInstance.id}, 自动恢复失败`)
  } finally {
    ;(terminalInstance as any)._fatalRecoveryInProgress = false
  }
}

const sendTerminalInputData = async (terminalInstance: TerminalInstance, data: string) => {
  if (isTerminalSocketOpen(terminalInstance)) {
    terminalInstance.terminalSocket!.send(textEncoder.encode(data))
    return
  }

  await invoke('ssh_send_input', { terminalId: terminalInstance.id, data })
}

const scheduleOutputReconnect = (terminalInstance: TerminalInstance, reason: string) => {
  if (!terminalInstance.isConnected) return
  if (terminalInstance.outputReconnectTimer) return
  // 防止重连回调中的竞态：上一个重连尚未完成时不发起新的
  if ((terminalInstance as any)._reconnectInProgress) return

  const now = Date.now()
  const attempt = (terminalInstance.wsReconnectAttempts ?? 0) + 1
  terminalInstance.wsReconnectAttempts = attempt

  // 30 秒内最多允许 5 次重连，超过则冷却 15 秒
  const recent = (terminalInstance as any)._reconnectTimestamps || []
  recent.push(now)
  while (recent.length > 0 && recent[0] < now - 30000) recent.shift()
  ;(terminalInstance as any)._reconnectTimestamps = recent
  if (recent.length > 5) {
    console.warn(`SSH终端重连过于频繁 (${recent.length}次/30s)，冷却15秒`)
    terminalInstance.terminal.writeln('\r\n\x1b[33m终端实时通道重连过于频繁，冷却 15 秒...\x1b[0m')
    terminalInstance.outputReconnectTimer = window.setTimeout(() => {
      terminalInstance.outputReconnectTimer = undefined
      ;(terminalInstance as any)._reconnectTimestamps = []
      terminalInstance.wsReconnectAttempts = 0
      if (terminalInstance.isConnected) {
        scheduleOutputReconnect(terminalInstance, 'cooldown结束')
      }
    }, 15000)
    return
  }

  if (attempt > 20) {
    terminalInstance.isConnected = false
    terminalInstance.outputReconnectTimer = undefined
    terminalInstance.terminal.writeln('\r\n\x1b[31m终端实时通道重连失败，请按 Ctrl+Shift+R 手动重连\x1b[0m')
    console.error(`SSH终端 WebSocket 重连失败: ${terminalInstance.id}, reason=${reason}`)
    return
  }

  const delay = Math.min(500 * (2 ** Math.min(attempt - 1, 5)), 15000)

  if (attempt === 1) {
    terminalInstance.terminal.writeln('\r\n\x1b[33m终端实时通道已断开，SSH 主连接仍在，正在自动重连...\x1b[0m')
  } else if (attempt <= 3) {
    terminalInstance.terminal.writeln(`\x1b[33m重连中(${attempt}/20)...\x1b[0m`)
  }

  console.warn(`SSH终端 WebSocket 已断开，准备重连: ${terminalInstance.id}, attempt=${attempt}, delay=${delay}ms, reason=${reason}`)

  terminalInstance.outputReconnectTimer = window.setTimeout(async () => {
    terminalInstance.outputReconnectTimer = undefined
    if (!terminalInstance.isConnected) return

    ;(terminalInstance as any)._reconnectInProgress = true
    try {
      // 不重建终端会话（保留运行中的 shell），仅重新建立 WebSocket
      startReceivingOutput(terminalInstance)
    } finally {
      ;(terminalInstance as any)._reconnectInProgress = false
    }
  }, delay)
}

// Adaptive input queuing with priority and rate limiting
const queueInput = (terminalId: string, chunk: string) => {
  let entry = inputBuffers.get(terminalId) as InputBuffer
  if (!entry) {
    entry = {
      buf: '',
      timer: null,
      lastFlush: Date.now(),
      inputRate: 0,
      priority: 'normal'
    }
    inputBuffers.set(terminalId, entry)
  }

  const now = Date.now()
  const timeSinceLastFlush = now - entry.lastFlush

  // Calculate input rate (characters per second)
  entry.inputRate = timeSinceLastFlush > 0 ?
    (chunk.length * 1000) / timeSinceLastFlush : 0

  // Classify input priority
  const inputPriority = classifyInput(chunk)
  entry.priority = inputPriority

  entry.buf += chunk

  // Adaptive buffer size based on input rate and priority
  let maxBufferSize = 1024
  if (inputPriority === 'control') {
    maxBufferSize = 1 // Immediate send for control chars
  } else if (inputPriority === 'navigation') {
    maxBufferSize = 16 // Small buffer for navigation
  } else if (entry.inputRate > 100) { // High input rate
    maxBufferSize = 2048 // Larger buffer for fast typing
  }

  // Immediate flush conditions
  if (entry.buf.length >= maxBufferSize || inputPriority === 'control') {
    void flushInput(terminalId)
    return
  }

  // 完全移除延迟，立即发送所有输入
  // 避免任何缓冲导致的会话中断问题
  if (entry.timer) window.clearTimeout(entry.timer)
  entry.timer = null

  // 立即刷新输入，不使用任何延迟
  void flushInput(terminalId)
}

// Enhanced flush with retry logic and better error handling
const flushInput = async (terminalId: string, retryCount = 0) => {
  const entry = inputBuffers.get(terminalId) as InputBuffer
  if (!entry || !entry.buf) return

  const dataToSend = entry.buf
  const priority = entry.priority

  // Clear buffer and timer
  entry.buf = ''
  entry.lastFlush = Date.now()
  if (entry.timer) {
    window.clearTimeout(entry.timer)
    entry.timer = null
  }

  const terminalInstance = terminals.value.find(t => t.id === terminalId)
  if (!terminalInstance) return

  try {
    await sendTerminalInputData(terminalInstance, dataToSend)

    // Reset any error state on successful send
    if (terminalInstance.errorCount) {
      terminalInstance.errorCount = 0
    }
  } catch (error: any) {
    const msg = String(error)
    console.error('发送输入失败:', msg)

    // Track error count for this terminal
    if (!terminalInstance.errorCount) terminalInstance.errorCount = 0
    terminalInstance.errorCount++

    // Classify error type
    const isFlowControlError = /draining\s*incoming\s*flow|flow\s*control/i.test(msg)
    const isConnectionError = /closed|closed\s*channel|not\s*connected|broken\s*pipe|EPIPE|EOF/i.test(msg)
    const isTemporaryError = /would\s*block|eagain|temporarily\s*unavailable/i.test(msg)

    if (isFlowControlError && retryCount < 10) {
      // Flow control error - 立即重试，不使用backoff
      console.warn(`SSH流控错误，立即重试 (尝试 ${retryCount + 1}/10)`)

      // Re-queue the data with higher priority
      entry.buf = dataToSend + entry.buf // Prepend failed data
      entry.priority = priority === 'normal' ? 'navigation' : priority
      void flushInput(terminalId, retryCount + 1)
      return
    }

    if (isTemporaryError && retryCount < 10) {
      // Temporary error - 立即重试
      console.warn(`SSH临时错误，立即重试 (尝试 ${retryCount + 1}/10)`)
      entry.buf = dataToSend + entry.buf
      void flushInput(terminalId, retryCount + 1)
      return
    }

    if (isConnectionError) {
      // Connection error - attempt reconnection
      terminalInstance.isConnected = false
      terminalInstance.terminal.writeln(`\r\n\x1b[31m连接错误: ${msg}\x1b[0m`)
      terminalInstance.terminal.writeln(`\x1b[33m[会话不可用，正在尝试自动重连...]\x1b[0m`)

      if (!reconnecting.value) {
        reconnecting.value = true
        try {
          await reconnectCurrentTerminal()
          // Re-queue failed data after reconnection
          if (terminalInstance.isConnected) {
            entry.buf = dataToSend + entry.buf
            setTimeout(() => void flushInput(terminalId), 100)
          }
        } finally {
          reconnecting.value = false
        }
      }
    } else {
      // Other errors - show to user but don't retry excessively
      if (terminalInstance.errorCount <= 3) {
        terminalInstance.terminal.writeln(`\r\n\x1b[31m输入发送错误: ${msg}\x1b[0m`)
      }

      // If too many errors, suggest reconnection
      if (terminalInstance.errorCount >= 5) {
        terminalInstance.terminal.writeln(`\x1b[33m[检测到多次输入错误，建议重新连接终端]\x1b[0m`)
        terminalInstance.errorCount = 0 // Reset counter
      }
    }
  }
}

const handleTerminalInput = async (terminalId: string, data: string) => {
  const terminalInstance = terminals.value.find(t => t.id === terminalId)
  if (!terminalInstance) {
    console.error('终端实例不存在:', terminalId)
    return
  }

  // 如果连接状态为false，尝试验证是否真的断开
  if (!terminalInstance.isConnected) {
    console.log('终端连接状态为false，尝试重新连接:', terminalId)
    try {
      // 首先尝试重新连接终端会话
      await reconnectCurrentTerminal()
      // 重新获取终端实例
      const updatedInstance = terminals.value.find(t => t.id === terminalId)
      if (!updatedInstance || !updatedInstance.isConnected) {
        console.error('重新连接失败，无法发送输入')
        return
      }
      console.log('✅ 终端已重新连接:', terminalId)
    } catch (error) {
      console.error('重新连接失败:', error)
      terminalInstance.terminal.writeln('\r\n\x1b[31m连接已断开，请重新连接SSH服务器\x1b[0m')
      return
    }
  }

  // 处理命令提示逻辑（可能会阻止某些按键传递到终端）
  const shouldSendToTerminal = handleCommandHintInput(data)
  if (shouldSendToTerminal === false) return

  // Enhanced priority-based input handling
  const inputPriority = classifyInput(data)

  if (inputPriority === 'control') {
    // Control characters get immediate priority
    await flushInput(terminalId) // Flush any pending input first

    try {
      // 确保terminalId和data都不为空
      if (!terminalId || terminalId.trim() === '') {
        throw new Error('终端ID不能为空')
      }
      if (data === undefined || data === null) {
        throw new Error('输入数据不能为空')
      }
      
      console.log('发送控制字符:', { terminalId, data: JSON.stringify(data), charCode: data.charCodeAt(0) })
      await sendTerminalInputData(terminalInstance, data)
      // Reset error count on successful control input
      if (terminalInstance.errorCount) {
        terminalInstance.errorCount = 0
      }
      console.log('控制字符发送成功')
    } catch (error: any) {
      const msg = String(error)
      console.error('控制字符发送失败:', error)
      console.error('错误详情:', { terminalId, data: JSON.stringify(data), error: error.message, stack: error.stack })
      terminalInstance.terminal.writeln(`\r\n\x1b[31m控制字符发送失败: ${error.message || msg}\x1b[0m`)

      // For control characters, show connection issues immediately
      if (/closed|broken\s*pipe|not\s*connected|Field required/i.test(msg)) {
        terminalInstance.isConnected = false
        terminalInstance.terminal.writeln(`\x1b[33m[连接已断开，正在尝试重连...]\x1b[0m`)
        if (!reconnecting.value) {
          reconnecting.value = true
          try { 
            await reconnectCurrentTerminal() 
            terminalInstance.terminal.writeln(`\x1b[32m[重新连接成功]\x1b[0m`)
          } catch (reconnectError) {
            terminalInstance.terminal.writeln(`\x1b[31m[重新连接失败: ${reconnectError}]\x1b[0m`)
          } finally { 
            reconnecting.value = false 
          }
        }
      }
    }
    return
  }

  // All other input goes through the enhanced queuing system
  queueInput(terminalId, data)
}

// 清除当前行（交互式模式由远端处理，不再在前端维护）

// Tab 自动补全处理（交互式PTY模式：补全由远端Shell处理，这里不做前端补全）
//
// （交互式PTY模式下，不需要前端求公共前缀/提示符/本地命令执行）
//

// 连接到 SSH
const connectToSSH = async (terminalInstance: TerminalInstance) => {
  try {
    connectionStatus.value = 'connecting'
    console.log('🔌 [SSH终端] 开始连接流程...')

    // 检查是否有活动的 SSH 连接（优先使用全局连接管理器，缺失则回退到后端状态）
    let isBackendConnected = false
    let connectionInfo: any = null

    const sshConnectionManager = (window as any).sshConnectionManager
    if (sshConnectionManager && typeof sshConnectionManager.isConnected === 'function') {
      console.log('🔌 [SSH终端] 使用全局连接管理器检查状态')
      isBackendConnected = !!sshConnectionManager.isConnected()
      connectionInfo = sshConnectionManager.getConnectionStatus?.() || null
      console.log('🔌 [SSH终端] 全局连接管理器状态:', { isBackendConnected, connectionInfo })
    } else {
      console.log('🔌 [SSH终端] 全局连接管理器不可用，尝试直接调用后端API')
      try {
        const status = await invoke('ssh_get_connection_status')
        console.log('🔌 [SSH终端] 后端API返回状态:', status)
        if (status && (status as any).connected) {
          isBackendConnected = true
          connectionInfo = status
        }
      } catch (e) {
        console.error('❌ [SSH终端] 获取连接状态失败:', e)
      }
    }

    // 二次确认后端真实状态，避免仅依赖前端状态导致“显示在线但后端已断开”
    try {
      const backendStatus = await invoke('ssh_get_connection_status') as any
      if (backendStatus?.connected) {
        isBackendConnected = true
        connectionInfo = backendStatus
      } else if (isBackendConnected) {
        console.warn('⚠️ [SSH终端] 前端状态在线但后端返回未连接，按后端状态处理')
        isBackendConnected = false
      }
    } catch (e) {
      console.warn('⚠️ [SSH终端] 后端状态二次确认失败，保留当前判断:', e)
    }

    if (!isBackendConnected) {
      console.warn('⚠️ [SSH终端] 没有活动的SSH连接，尝试自动恢复')
      terminalInstance.terminal.writeln('\x1b[33m未检测到活动SSH主连接，正在尝试自动恢复...\x1b[0m')
      const restored = await tryRestoreBackendSshConnection(terminalInstance)
      if (restored) {
        isBackendConnected = true
        connectionInfo = sshConnectionManager?.getConnectionStatus?.() || connectionInfo
        terminalInstance.terminal.writeln('\x1b[32mSSH主连接恢复成功，继续建立终端会话...\x1b[0m')
      } else {
        terminalInstance.terminal.writeln('\x1b[31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m')
        terminalInstance.terminal.writeln('\x1b[31m  错误: 没有活动的 SSH 连接\x1b[0m')
        terminalInstance.terminal.writeln('\x1b[31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m')
        terminalInstance.terminal.writeln('')
        terminalInstance.terminal.writeln('\x1b[33m可能的原因:\x1b[0m')
        terminalInstance.terminal.writeln('  1. 主窗口尚未连接到SSH服务器')
        terminalInstance.terminal.writeln('  2. SSH连接已断开')
        terminalInstance.terminal.writeln('')
        terminalInstance.terminal.writeln('\x1b[36m解决方法:\x1b[0m')
        terminalInstance.terminal.writeln('  • 在主窗口左侧边栏连接到SSH服务器')
        terminalInstance.terminal.writeln('  • 连接成功后，关闭此窗口重新打开')
        terminalInstance.terminal.writeln('')
        connectionStatus.value = 'disconnected'
        return
      }
    }

    if (!connectionInfo && sshConnectionManager && typeof sshConnectionManager.getConnectionStatus === 'function') {
      connectionInfo = sshConnectionManager.getConnectionStatus()
    }
    if (connectionInfo) {
      terminalInstance.connectionInfo = {
        host: connectionInfo.host,
        port: connectionInfo.port,
        username: connectionInfo.username
      }
      updateTerminalTitle(terminalInstance)
    }

    stopReceivingOutput(terminalInstance)
    terminalInstance.wsReconnectAttempts = 0

    // 创建终端会话
    console.log('🔌 [SSH终端] 创建终端会话:', terminalInstance.id)
    await invoke('ssh_create_terminal_session', {
      terminal_id: terminalInstance.id,
      cols: terminalInstance.terminal.cols,
      rows: terminalInstance.terminal.rows
    })

    terminalInstance.isConnected = true
    connectionStatus.value = 'connected'

    // 显示连接成功信息
    if (connectionInfo) {
      terminalInstance.terminal.writeln(`\x1b[32m✓ 已连接到 ${connectionInfo.username}@${connectionInfo.host}:${connectionInfo.port}\x1b[0m`)
      terminalInstance.terminal.writeln('')
    }

    console.log('✅ [SSH终端] 连接成功，开始接收输出')

    // 开始接收输出（事件流）
    startReceivingOutput(terminalInstance)

  } catch (error: any) {
    const errorMsg = String(error)
    console.error('SSH 连接失败:', errorMsg)

    // 检查是否是通道创建失败，尝试使用保存的密码重新连接SSH
    if (/创建通道失败|channel.*open|Session.*-7|Unable to send/i.test(errorMsg)) {
      terminalInstance.terminal.writeln('\x1b[31m✗ SSH会话异常，尝试重新连接...\x1b[0m')

      try {
        const restored = await tryRestoreBackendSshConnection(terminalInstance)
        if (restored) {
          terminalInstance.terminal.writeln('\x1b[33m正在重试创建终端会话...\x1b[0m')

          // 重试创建终端会话
          await invoke('ssh_create_terminal_session', {
            terminal_id: terminalInstance.id,
            cols: terminalInstance.terminal.cols,
            rows: terminalInstance.terminal.rows
          })

          terminalInstance.isConnected = true
          connectionStatus.value = 'connected'

          startReceivingOutput(terminalInstance)
          return
        }
      } catch (retryError) {
        console.error('重连失败:', retryError)
        terminalInstance.terminal.writeln(`\x1b[31m重连失败: ${retryError}\x1b[0m`)
      }
    }

    terminalInstance.terminal.writeln(`\x1b[31m连接失败: ${errorMsg}\x1b[0m`)
    terminalInstance.terminal.writeln('\x1b[36m提示: 请检查SSH连接状态，或尝试重新连接SSH服务器\x1b[0m')
    connectionStatus.value = 'disconnected'
  }
}

// 开始接收输出：仅使用 WebSocket 实时双向传输
const startReceivingOutput = (terminalInstance: TerminalInstance) => {
  stopReceivingOutput(terminalInstance)

  const socket = new WebSocket(getTerminalWsUrl(terminalInstance.id)) as WebSocket & {
    __expectedClose?: boolean
  }
  socket.binaryType = 'arraybuffer'
  terminalInstance.terminalSocket = socket

  const connectDeadline = window.setTimeout(() => {
    if (socket.readyState !== WebSocket.OPEN) {
      try { socket.close() } catch {}
    }
  }, 5000)

  socket.onopen = () => {
    clearTimeout(connectDeadline)
    terminalInstance.terminalSocket = socket
    const recovered = (terminalInstance.wsReconnectAttempts ?? 0) > 0
    terminalInstance.wsReconnectAttempts = 0
    ;(terminalInstance as any)._reconnectTimestamps = []
    if (terminalInstance.outputReconnectTimer) {
      clearTimeout(terminalInstance.outputReconnectTimer)
      terminalInstance.outputReconnectTimer = undefined
    }
    if (recovered) {
      terminalInstance.terminal.writeln('\x1b[32m终端实时通道已恢复\x1b[0m')
    }
    console.log(`✅ SSH终端 WebSocket 已连接: ${terminalInstance.id}`)

    // 记录最后一次收到消息的时间
    terminalInstance.wsLastMessageTime = Date.now()

    if (terminalInstance.wsPingTimer) clearInterval(terminalInstance.wsPingTimer)
    terminalInstance.wsPingTimer = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        try { socket.send(JSON.stringify({ type: 'ping' })) } catch {}
      }
    }, 10000)

    // 看门狗：超过 45s 无任何消息则认为连接已死，主动断开触发重连
    if (terminalInstance.wsWatchdogTimer) clearInterval(terminalInstance.wsWatchdogTimer)
    terminalInstance.wsWatchdogTimer = window.setInterval(() => {
      if (socket.readyState !== WebSocket.OPEN) return
      const idle = Date.now() - (terminalInstance.wsLastMessageTime || 0)
      if (idle > 45000) {
        console.warn(`SSH终端 WebSocket 无响应超时: ${terminalInstance.id}, idle=${idle}ms, 主动断开重连`)
        socket.__expectedClose = false
        try { socket.close() } catch {}
      }
    }, 5000)
  }

  socket.onmessage = (event) => {
    terminalInstance.wsLastMessageTime = Date.now()
    // 服务器发来的 ping/pong 文本消息不应输出到终端
    if (typeof event.data === 'string') {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'ping' || msg.type === 'pong') {
          if (msg.type === 'ping') {
            // 响应服务器 ping
            try { socket.send(JSON.stringify({ type: 'pong' })) } catch {}
          }
          return
        }
      } catch {}
    }
    writeTerminalPayload(terminalInstance, event.data)
  }

  socket.onerror = (event) => {
    console.warn(`SSH终端 WebSocket 错误: ${terminalInstance.id}`, event)
  }

  socket.onclose = (event) => {
    clearTimeout(connectDeadline)
    if (terminalInstance.wsPingTimer) {
      clearInterval(terminalInstance.wsPingTimer)
      terminalInstance.wsPingTimer = undefined
    }
    if (terminalInstance.wsWatchdogTimer) {
      clearInterval(terminalInstance.wsWatchdogTimer)
      terminalInstance.wsWatchdogTimer = undefined
    }
    if (terminalInstance.terminalSocket === socket) {
      terminalInstance.terminalSocket = undefined
    }
    if (socket.__expectedClose) {
      return
    }

    console.warn(`SSH终端 WebSocket 已关闭: ${terminalInstance.id}, code=${event.code}, reason=${event.reason || 'n/a'}`)

    // 服务器指示可能存在 SSH/会话级异常：优先尝试自动恢复
    const fatalClose = event.code === 1011 || event.code === 1001
    const fatalReasons = ['没有活动的 SSH 连接', 'SSH会话已丢失', 'SSH通道异常', 'SSH写入失败']
    if (fatalClose && fatalReasons.some(r => event.reason?.includes(r))) {
      void recoverFromSocketFatalClose(terminalInstance, event)
      return
    }

    // WebSocket 层面的断开（非 SSH 断开），重连 WebSocket 即可
    if (terminalInstance.isConnected) {
      scheduleOutputReconnect(
        terminalInstance,
        event.reason || `code=${event.code || 'unknown'}`
      )
    }
  }
}

// 切换终端
const switchTerminal = (terminalId: string) => {
  activeTerminalId.value = terminalId
  const terminalInstance = terminals.value.find(t => t.id === terminalId)
  if (terminalInstance) {
    // 重新调整终端大小
    nextTick(() => {
      try {
        // 确保终端已经挂载到DOM并且可见
        if (terminalInstance.terminal && terminalInstance.fitAddon &&
            terminalInstance.terminal.element &&
            terminalInstance.terminal.element.offsetParent) {
          terminalInstance.fitAddon.fit()
        }
      } catch (error) {
        console.warn('终端 resize 失败:', error)
      }
    })
  }
}

// 关闭终端
const closeTerminal = async (terminalId: string) => {
  const index = terminals.value.findIndex(t => t.id === terminalId)
  if (index === -1) return

  const terminalInstance = terminals.value[index]
  
  // 清理终端资源
  try {
    // 清理输入缓冲区
    const inputBuffer = inputBuffers.get(terminalId)
    if (inputBuffer && inputBuffer.timer) {
      window.clearTimeout(inputBuffer.timer)
    }
    inputBuffers.delete(terminalId)

    // 清理事件监听器
    if (terminalInstance.unlisten) {
      try { terminalInstance.unlisten() } catch {}
    }

    // 清理ResizeObserver
    if (terminalInstance.resizeObserver) {
      try {
        terminalInstance.resizeObserver.disconnect()
        terminalInstance.resizeObserver = undefined
      } catch {}
    }

    stopReceivingOutput(terminalInstance)

    // 关闭SSH会话
    if (terminalInstance.isConnected) {
      await invoke('ssh_close_terminal_session', { terminalId })
    }

    // 释放xterm实例
    terminalInstance.terminal.dispose()
  } catch (error) {
    console.error('关闭终端失败:', error)
  }

  // 从数组中移除
  terminals.value.splice(index, 1)

  // 如果关闭的是当前活动终端，切换到其他终端
  if (activeTerminalId.value === terminalId) {
    if (terminals.value.length > 0) {
      activeTerminalId.value = terminals.value[0].id
    } else {
      activeTerminalId.value = ''
    }
  }
}

// 命令提示相关方法
const handleCommandHintInput = (data: string): boolean => {
  // 处理输入字符
  if (data === '\r' || data === '\n') {
    // 回车键处理
    if (showCommandSuggestions.value && selectedSuggestionIndex.value >= 0) {
      // 如果有选中的建议，应用它
      const selectedCommand = commandSuggestions.value[selectedSuggestionIndex.value]
      if (selectedCommand) {
        // 替换当前输入中的命令（支持管道符）
        const trimmedInput = currentInput.value.trim()
        const pipeSegments = trimmedInput.split('|')
        const lastSegment = pipeSegments[pipeSegments.length - 1].trim()
        const words = lastSegment.split(/\s+/)
        words[0] = selectedCommand.command

        // 重新组合输入
        pipeSegments[pipeSegments.length - 1] = words.join(' ')
        currentInput.value = pipeSegments.join(' | ')
        showCommandHintForCommand(selectedCommand.command)
      }
    }
    // 清空输入并隐藏所有提示
    currentInput.value = ''
    hideCommandHint()
    hideCommandSuggestions()
    return true // 允许回车键传递到终端
  } else if (data === '\u007f' || data === '\b') {
    // 退格键 - 添加防抖处理，避免过快输入导致传输错误
    if (currentInput.value.length > 0) {
      currentInput.value = currentInput.value.slice(0, -1)
      updateCommandSuggestions()
      // 检查当前输入是否还匹配命令提示
      updateCommandHint()
    } else {
      hideCommandSuggestions()
      hideCommandHint()
    }
    // 退格键需要传递到终端，由远端Shell处理删除
    return true
  } else if (data === '\u001b[A') {
    // 上方向键 - 在建议列表中向上选择
    if (showCommandSuggestions.value && commandSuggestions.value.length > 0) {
      selectedSuggestionIndex.value = selectedSuggestionIndex.value <= 0
        ? commandSuggestions.value.length - 1
        : selectedSuggestionIndex.value - 1
    }
  } else if (data === '\u001b[B') {
    // 下方向键 - 在建议列表中向下选择
    if (showCommandSuggestions.value && commandSuggestions.value.length > 0) {
      selectedSuggestionIndex.value = selectedSuggestionIndex.value >= commandSuggestions.value.length - 1
        ? 0
        : selectedSuggestionIndex.value + 1
    }
  } else if (data === '\u001b[C' || data === '\u001b[D') {
    // 左右方向键，隐藏建议
    hideCommandSuggestions()
  } else if (data === '\u001b') {
    // ESC键 - 隐藏建议
    hideCommandSuggestions()
  } else if (data === '\t') {
    // Tab键 - 自动补全
    if (showCommandSuggestions.value && commandSuggestions.value.length > 0) {
      const selectedCommand = selectedSuggestionIndex.value >= 0
        ? commandSuggestions.value[selectedSuggestionIndex.value]
        : commandSuggestions.value[0]

      if (selectedCommand) {
        // 替换当前输入中的命令（支持管道符）
        const trimmedInput = currentInput.value.trim()
        const pipeSegments = trimmedInput.split('|')
        const lastSegment = pipeSegments[pipeSegments.length - 1].trim()
        const words = lastSegment.split(/\s+/)
        words[0] = selectedCommand.command

        // 重新组合输入
        pipeSegments[pipeSegments.length - 1] = words.join(' ')
        currentInput.value = pipeSegments.join(' | ') + ' '
        showCommandHintForCommand(selectedCommand.command)
        hideCommandSuggestions()
      }
    }
    // 允许Tab键传递到终端（交给远端Shell处理）
    return true
  } else if (data === ' ') {
    // 空格键，检查是否需要显示详细提示
    const trimmedInput = currentInput.value.trim()
    if (trimmedInput) {
      const { command } = parseCurrentCommand(trimmedInput)
      if (command) {
        showCommandHintForCommand(command)
      }
    }
    currentInput.value += data
    hideCommandSuggestions()
  } else if (data.length === 1 && data >= ' ' && data <= '~') {
    // 可打印字符
    currentInput.value += data

    // 特殊处理管道符
    if (data === '|') {
      // 管道符后隐藏当前的建议和提示，准备接收新命令
      hideCommandSuggestions()
      hideCommandHint()

      // 延迟显示管道符后的常用命令建议
      setTimeout(() => {
        showPipeCommandSuggestions()
      }, 100)
    } else {
      updateCommandSuggestions()
    }
  }

  // 默认情况下，允许数据传递到终端
  return true
}

// 解析当前输入中的命令，支持管道符
const parseCurrentCommand = (input: string): { command: string, isAfterPipe: boolean, position: number } => {
  const trimmedInput = input.trim()
  if (!trimmedInput) return { command: '', isAfterPipe: false, position: 0 }

  // 按管道符分割命令
  const pipeSegments = trimmedInput.split('|')
  const currentSegment = pipeSegments[pipeSegments.length - 1].trim()
  const words = currentSegment.split(/\s+/)
  const command = words[0] || ''

  return {
    command,
    isAfterPipe: pipeSegments.length > 1,
    position: words.length
  }
}

const updateCommandSuggestions = () => {
  const trimmedInput = currentInput.value.trim()
  if (trimmedInput) {
    const { command, position } = parseCurrentCommand(trimmedInput)

    if (command && position === 1) {
      // 只在输入命令的第一个单词时显示建议
      const suggestions = commandHintsManager.searchCommands(command)
      if (suggestions.length > 0) {
        commandSuggestions.value = suggestions.slice(0, 8) // 最多显示8个建议
        updateSuggestionsPanelPosition()
        showCommandSuggestions.value = true
        selectedSuggestionIndex.value = -1
      } else {
        hideCommandSuggestions()
      }
    } else {
      hideCommandSuggestions()
    }
  } else {
    hideCommandSuggestions()
  }
}

// 获取建议面板位置（基于光标位置）
const updateSuggestionsPanelPosition = () => {
  const terminalInstance = terminals.value.find(t => t.id === activeTerminalId.value)
  if (!terminalInstance) return

  const terminal = terminalInstance.terminal
  const terminalElement = document.querySelector(`[data-terminal-id="${activeTerminalId.value}"]`) as HTMLElement
  if (!terminalElement) return

  // 获取终端光标位置
  const buffer = terminal.buffer.active
  const cursorX = buffer.cursorX
  const cursorY = buffer.cursorY

  // 获取终端元素的边界
  const rect = terminalElement.getBoundingClientRect()
  
  // 计算单个字符的大小（基于终端配置）
  const charWidth = rect.width / terminal.cols
  const charHeight = rect.height / terminal.rows

  // 计算光标的像素位置
  let x = rect.left + (cursorX * charWidth)
  let y = rect.top + ((cursorY + 1) * charHeight) // +1 显示在光标下方

  // 确保面板不会超出视窗
  const panelWidth = 420
  const panelMaxHeight = 400
  
  if (x + panelWidth > window.innerWidth) {
    x = window.innerWidth - panelWidth - 20
  }
  
  if (y + panelMaxHeight > window.innerHeight) {
    y = rect.top + (cursorY * charHeight) - panelMaxHeight - 10 // 显示在光标上方
  }

  suggestionsPanelPosition.value = { x, y }
}

// 显示管道符后的常用命令建议
const showPipeCommandSuggestions = () => {
  // 检查当前输入是否以管道符结尾（可能有空格）
  const trimmedInput = currentInput.value.trim()
  if (trimmedInput.endsWith('|')) {
    // 定义管道符后常用的命令
    const pipeCommands = ['grep', 'sort', 'uniq', 'head', 'tail', 'awk', 'sed', 'cut', 'wc']

    // 获取这些命令的详细信息，过滤掉null值
    const suggestions: CommandHint[] = []
    for (const cmd of pipeCommands) {
      const hint = commandHintsManager.getHint(cmd)
      if (hint) {
        suggestions.push(hint)
      }
    }

    if (suggestions.length > 0) {
      commandSuggestions.value = suggestions
      updateSuggestionsPanelPosition()
      showCommandSuggestions.value = true
      selectedSuggestionIndex.value = -1
    }
  }
}

const updateCommandHint = () => {
  const trimmedInput = currentInput.value.trim()
  if (trimmedInput) {
    const { command, position } = parseCurrentCommand(trimmedInput)

    // 如果当前显示的提示与输入的命令不匹配，则隐藏提示
    if (currentCommandHint.value && currentCommandHint.value.command !== command) {
      hideCommandHint()
    }
    // 如果输入了多个单词，检查是否需要显示命令提示
    else if (position > 1 && command) {
      showCommandHintForCommand(command)
    }
  } else {
    hideCommandHint()
  }
}



const showCommandHintForCommand = (command: string) => {
  const hint = commandHintsManager.getHint(command)
  if (hint) {
    currentCommandHint.value = hint
    showCommandHint.value = true
  } else {
    hideCommandHint()
  }
}

const hideCommandHint = () => {
  showCommandHint.value = false
  currentCommandHint.value = null
  if (hintTimeout.value) {
    clearTimeout(hintTimeout.value)
    hintTimeout.value = null
  }
}

const hideCommandSuggestions = () => {
  showCommandSuggestions.value = false
  commandSuggestions.value = []
  selectedSuggestionIndex.value = -1
}

const selectSuggestion = (index: number) => {
  if (index >= 0 && index < commandSuggestions.value.length) {
    selectedSuggestionIndex.value = index
    const selectedCommand = commandSuggestions.value[index]

    // 应用选中的命令（支持管道符）
    const trimmedInput = currentInput.value.trim()
    const pipeSegments = trimmedInput.split('|')
    const lastSegment = pipeSegments[pipeSegments.length - 1].trim()
    const words = lastSegment.split(/\s+/)
    words[0] = selectedCommand.command

    // 重新组合输入
    pipeSegments[pipeSegments.length - 1] = words.join(' ')
    currentInput.value = pipeSegments.join(' | ') + ' '

    // 显示详细提示
    showCommandHintForCommand(selectedCommand.command)

    // 隐藏建议面板
    hideCommandSuggestions()
  }
}

const getCategoryName = (category: CommandHint['category']): string => {
  const categoryNames = {
    'file': '文件操作',
    'system': '系统信息',
    'network': '网络工具',
    'process': '进程管理',
    'text': '文本处理',
    'archive': '压缩解压',
    'permission': '权限管理',
    'security': '安全审计',
    'other': '其他'
  }
  return categoryNames[category] || '其他'
}

// 清屏
const clearCurrentTerminal = () => {
  const terminalInstance = terminals.value.find(t => t.id === activeTerminalId.value)
  if (terminalInstance) {
    terminalInstance.terminal.clear()
  }
}

// 重连
const reconnectCurrentTerminal = async () => {
  const terminalInstance = terminals.value.find(t => t.id === activeTerminalId.value)
  if (terminalInstance) {
    terminalInstance.isConnected = false
    terminalInstance.terminal.writeln('\x1b[33m正在重新连接...\x1b[0m')
    await connectToSSH(terminalInstance)
  }
}

// 更新终端标题
const updateTerminalTitle = (terminalInstance: TerminalInstance, title?: string) => {
  if (title) {
    terminalInstance.name = title
  } else if (terminalInstance.connectionInfo) {
    const { username, host } = terminalInstance.connectionInfo
    terminalInstance.name = `${username}@${host}`
  }
}



// 快捷键处理
const handleKeydown = (event: KeyboardEvent) => {
  // Ctrl+I - 切换AI助手 (优先处理)
  if (event.ctrlKey && (event.key === 'i' || event.key === 'I')) {
    event.preventDefault()
    event.stopPropagation()
    console.log('🤖 Ctrl+I 快捷键触发，切换AI助手')
    toggleAIInput()
    return
  }

  // Ctrl+Shift+T - 新建终端
  if (event.ctrlKey && event.shiftKey && event.key === 'T') {
    event.preventDefault()
    createNewTerminal()
  }
  // Ctrl+Shift+W - 关闭当前终端
  else if (event.ctrlKey && event.shiftKey && event.key === 'W') {
    event.preventDefault()
    if (activeTerminalId.value && terminals.value.length > 1) {
      closeTerminal(activeTerminalId.value)
    }
  }
  // Ctrl+Shift+R - 重连当前终端
  else if (event.ctrlKey && event.shiftKey && event.key === 'R') {
    event.preventDefault()
    reconnectCurrentTerminal()
  }
  // Ctrl+Shift+L - 清屏
  else if (event.ctrlKey && event.shiftKey && event.key === 'L') {
    event.preventDefault()
    clearCurrentTerminal()
  }
  // Ctrl+Tab - 切换到下一个终端
  else if (event.ctrlKey && event.key === 'Tab') {
    event.preventDefault()
    const currentIndex = terminals.value.findIndex(t => t.id === activeTerminalId.value)
    if (currentIndex !== -1 && terminals.value.length > 1) {
      const nextIndex = (currentIndex + 1) % terminals.value.length
      switchTerminal(terminals.value[nextIndex].id)
    }
  }
}

// AI助手相关方法
const toggleAIInput = () => {
  console.log('🔄 toggleAIInput 被调用，当前状态:', showAIInput.value)


  showAIInput.value = !showAIInput.value
  console.log('🔄 切换后状态:', showAIInput.value)

  if (showAIInput.value) {
    console.log('✅ 显示AI输入框')
    // 显示AI输入框时，聚焦到输入框并加载AI提供商信息
    nextTick(() => {
      const aiInput = document.querySelector('.ai-textarea') as HTMLTextAreaElement
      if (aiInput) {
        aiInput.focus()
        console.log('✅ AI输入框已聚焦')
      } else {
        console.warn('⚠️ 未找到AI输入框元素')
      }
    })
    loadAIProviderInfo()
  } else {
    console.log('❌ 隐藏AI输入框')
    // 隐藏时清空输入和响应
    aiInputText.value = ''
    aiResponse.value = ''
  }
}

const loadAIProviderInfo = async () => {
  try {
    // 优先使用统一 AI 服务配置（与日志审计页一致）
    const serviceConfig = aiService.getConfig()
    if (serviceConfig) {
      currentAIProvider.value = serviceConfig.name || serviceConfig.provider || 'AI助手'
      return
    }

    // 从AppData目录的settings.json读取AI提供商信息
    const settingsContent = await invoke('read_settings_file') as string
    console.log('SSH终端读取到的设置内容长度:', settingsContent.length)
    console.log('SSH终端读取到的设置内容:', settingsContent)

    let settings: any = {}

    if (settingsContent) {
      settings = JSON.parse(settingsContent)
      console.log('SSH终端解析后的设置:', settings)

      // 检查是否包含AI配置
      if (settings.ai) {
        console.log('✅ 发现AI配置:', settings.ai)
      } else {
        console.log('❌ 未发现AI配置，当前设置键:', Object.keys(settings))
      }
    }

    // 如果后端设置文件没有AI配置，使用默认AI配置
    if (!settings.ai) {
      console.log('⚠️ 后端设置文件缺少AI配置，使用默认配置')
      settings.ai = {
        currentProvider: 'openai',
        providers: {
          openai: {
            name: 'OpenAI',
            apiKey: '',
            model: 'gpt-3.5-turbo',
            baseUrl: 'https://api.openai.com/v1'
          },
          qwen: {
            name: 'Qwen',
            apiKey: '',
            model: 'qwen-turbo',
            baseUrl: 'https://dashscope.aliyuncs.com/api/v1'
          },
          ollama: {
            name: 'Ollama',
            apiKey: '',
            model: 'llama2',
            baseUrl: 'http://localhost:11434/api'
          }
        }
      }
    }

    if (settings.ai && settings.ai.currentProvider) {
      const currentProviderKey = settings.ai.currentProvider
      const provider = settings.ai.providers[currentProviderKey]
      console.log('当前AI提供商:', currentProviderKey, provider)

      if (provider && provider.name) {
        currentAIProvider.value = provider.name
        console.log('✅ 成功设置AI提供商名称:', provider.name)
      } else {
        currentAIProvider.value = currentProviderKey || 'AI助手'
        console.log('⚠️ 使用提供商键作为名称:', currentProviderKey)
      }
    } else {
      console.warn('⚠️ AI配置异常，使用默认值')
      currentAIProvider.value = 'AI助手'
    }
  } catch (error) {
    console.error('❌ SSH终端加载AI提供商信息失败:', error)
    currentAIProvider.value = 'AI助手' // 默认值
  }
}

const handleAIInputKeydown = (event: KeyboardEvent) => {
  // Ctrl+I - 关闭AI输入框
  if (event.ctrlKey && event.key === 'i') {
    event.preventDefault()
    toggleAIInput()
  }
  // Enter - 发送AI请求（Shift+Enter换行）
  else if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendAIRequest()
  }
}

const sendAIRequest = async () => {
  if (!aiInputText.value.trim() || aiLoading.value) return

  aiLoading.value = true
  aiResponse.value = ''

  try {
    // 与日志审计页使用同一 AI 配置来源，避免 settings.json 与本地缓存不一致
    const serviceConfig = aiService.getConfig()
    if (!serviceConfig || !aiService.isConfigured()) {
      throw new Error('未检测到可用模型配置，请先在设置中的 AI 模型里完成配置。')
    }
    console.log('AI提供商配置(统一服务):', serviceConfig.provider, serviceConfig)
    currentAIProvider.value = serviceConfig.name || serviceConfig.provider || 'AI助手'

    // 构建提示词：区分system和user消息
    let systemPrompt = ''
    let userMessage = ''

    if (selectedContentPrompt.value && selectedContentHint.value) {
      // 有选中内容时，结合选中内容和用户输入
      systemPrompt = `你是一个Linux命令行专家。用户会描述他们想要完成的任务，或者提供终端输出内容让你分析。

规则：
1. 只返回命令本身，不要任何解释或说明
2. 如果需要多个命令，用 && 或 ; 连接
3. 确保命令的安全性和准确性
4. 优先使用常用的、兼容性好的命令
5. 根据用户需求直接给出可执行的命令`

      userMessage = `选中的终端内容：
${selectedContentPrompt.value.replace('请分析这段终端输出内容并提供相关的Linux命令建议：\n\n', '')}

用户需求：${aiInputText.value.trim() || '请分析这段内容并提供相关命令建议'}`
    } else {
      // 没有选中内容时，使用标准提示词
      systemPrompt = `你是一个Linux命令行专家。用户会描述他们想要完成的任务，请你提供准确的Linux命令。

规则：
1. 只返回命令本身，不要任何解释或说明
2. 如果需要多个命令，用 && 或 ; 连接
3. 确保命令的安全性和准确性
4. 优先使用常用的、兼容性好的命令
5. 根据用户需求直接给出可执行的命令`

      userMessage = `用户需求：${aiInputText.value.trim()}`
    }

    console.log('🤖 System Prompt:', systemPrompt)
    console.log(' User Message:', userMessage)

    // 复用统一 AI 代理工具：自动适配 OpenAI/Claude/Ollama 等提供商
    const proxyConfig: AIProviderConfig = {
      ...serviceConfig,
      provider: serviceConfig.provider,
      temperature: serviceConfig.temperature ?? 0.3,
      maxTokens: serviceConfig.maxTokens ?? 500,
      timeoutSeconds: serviceConfig.timeoutSeconds ?? 60
    }
    const fullContent = await streamAIProxyMessages(
      [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userMessage }
      ],
      proxyConfig,
      (chunk) => {
        aiResponse.value += chunk
      }
    )
    if (!fullContent) {
      throw new Error('AI 返回为空，请检查当前模型配置')
    }

    console.log('✅ AI生成的命令:', fullContent)
    aiResponse.value = fullContent
  } catch (error) {
    console.error('AI请求失败:', error)
    aiResponse.value = `错误: ${error}`
  } finally {
    aiLoading.value = false
  }
}

const insertAIResponse = async () => {
  if (!aiResponse.value || aiResponse.value.startsWith('错误:')) return

  const activeTerminal = terminals.value.find(t => t.id === activeTerminalId.value)
  if (activeTerminal && activeTerminal.terminal) {
    console.log('📝 插入AI命令到终端:', aiResponse.value)

    try {
      const command = aiResponse.value.trim()

      // 方法：一次性发送整个命令，避免触发流控
      await handleTerminalInput(activeTerminal.id, command)

      console.log('✅ AI命令已插入到终端')
    } catch (error) {
      console.error('❌ 插入AI命令失败:', error)

      // 如果模拟输入失败，回退到直接显示在终端上
      activeTerminal.terminal.write('\r\n' + aiResponse.value + '\r\n')
    }

    // 清空AI输入和响应
    aiInputText.value = ''
    aiResponse.value = ''

    // 可选：关闭AI输入框
    // showAIInput.value = false
  }
}

const insertAndExecuteAIResponse = async () => {
  if (!aiResponse.value || aiResponse.value.startsWith('错误:')) return

  const activeTerminal = terminals.value.find(t => t.id === activeTerminalId.value)
  if (activeTerminal && activeTerminal.terminal) {
    console.log('🚀 插入并执行AI命令:', aiResponse.value)

    try {
      const command = aiResponse.value.trim()

      // 发送命令
      await handleTerminalInput(activeTerminal.id, command)

      // 等待一小段时间确保命令已插入
      await new Promise(resolve => setTimeout(resolve, 100))

      // 发送回车键执行命令
      await handleTerminalInput(activeTerminal.id, '\r')

      console.log('✅ AI命令已插入并执行')
    } catch (error) {
      console.error('❌ 插入并执行AI命令失败:', error)

      // 如果失败，回退到直接显示
      activeTerminal.terminal.write('\r\n' + aiResponse.value + '\r\n')
    }

    // 清空AI输入和响应
    aiInputText.value = ''
    aiResponse.value = ''

    // 可选：关闭AI输入框
    // showAIInput.value = false
  }
}

// AI拖拽相关方法
const startDragging = (event: MouseEvent) => {
  // 检查是否点击在可拖拽区域
  const target = event.target as HTMLElement
  if (target.closest('.ai-close-btn')) {
    return // 点击关闭按钮不触发拖拽
  }

  isDragging.value = true
  const container = document.querySelector('.ai-floating-container') as HTMLElement
  if (container) {
    const rect = container.getBoundingClientRect()
    dragOffset.value = {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top
    }
  }

  // 添加全局事件监听器
  document.addEventListener('mousemove', onDragging)
  document.addEventListener('mouseup', stopDragging)

  event.preventDefault()
  console.log('🖱️ 开始拖拽AI面板')
}

const onDragging = (event: MouseEvent) => {
  if (!isDragging.value) return

  const container = document.querySelector('.ai-floating-container') as HTMLElement
  if (container) {
    const terminalContent = document.querySelector('.terminal-content') as HTMLElement
    if (terminalContent) {
      const terminalRect = terminalContent.getBoundingClientRect()

      // 计算新位置（相对于终端内容区域）
      let newX = event.clientX - dragOffset.value.x - terminalRect.left
      let newY = event.clientY - dragOffset.value.y - terminalRect.top

      // 边界限制
      const containerRect = container.getBoundingClientRect()
      const maxX = terminalRect.width - containerRect.width
      const maxY = terminalRect.height - containerRect.height

      newX = Math.max(0, Math.min(newX, maxX))
      newY = Math.max(0, Math.min(newY, maxY))

      // 应用新位置
      container.style.left = `${newX}px`
      container.style.top = `${newY}px`
      container.style.transform = 'none'
      container.style.bottom = 'auto'

      aiPosition.value = { x: newX, y: newY }
    }
  }
  event.preventDefault()
}

const stopDragging = () => {
  if (isDragging.value) {
    isDragging.value = false

    // 移除全局事件监听器
    document.removeEventListener('mousemove', onDragging)
    document.removeEventListener('mouseup', stopDragging)

    console.log('🖱️ 停止拖拽AI面板')
  }
}

// 右键菜单相关方法
const handleContextMenu = (event: MouseEvent) => {
  event.preventDefault()

  // 获取当前选中的文本
  const activeTerminal = terminals.value.find(t => t.id === activeTerminalId.value)
  if (activeTerminal && activeTerminal.terminal) {
    selectedText.value = activeTerminal.terminal.getSelection()
    console.log('🖱️ 右键菜单，选中文本:', selectedText.value)
  }

  // 设置菜单位置
  contextMenuPosition.value = {
    x: event.clientX,
    y: event.clientY
  }

  showContextMenu.value = true

  // 点击其他地方关闭菜单
  const closeMenu = () => {
    showContextMenu.value = false
    document.removeEventListener('click', closeMenu)
  }
  setTimeout(() => {
    document.addEventListener('click', closeMenu)
  }, 0)
}

const copySelection = async () => {
  const activeTerminal = terminals.value.find(t => t.id === activeTerminalId.value)
  if (activeTerminal && activeTerminal.terminal) {
    const selection = activeTerminal.terminal.getSelection()
    if (selection) {
      try {
        await navigator.clipboard.writeText(selection)
        console.log('✅ 已复制到剪贴板:', selection)
      } catch (error) {
        console.error('❌ 复制失败:', error)
      }
    }
  }
  showContextMenu.value = false
}

const pasteFromClipboard = async () => {
  try {
    const text = await navigator.clipboard.readText()
    if (text) {
      const activeTerminal = terminals.value.find(t => t.id === activeTerminalId.value)
      if (activeTerminal) {
        await handleTerminalInput(activeTerminal.id, text)
        console.log('✅ 已粘贴文本:', text)
      }
    }
  } catch (error) {
    console.error('❌ 粘贴失败:', error)
  }
  showContextMenu.value = false
}

const sendSelectionToAI = async () => {
  if (selectedText.value) {
    // 设置选中内容提示
    selectedContentHint.value = "已划选内容"

    // 构建针对选中内容的AI提示词，但不显示在输入框中
    const selectionPrompt = `请分析这段终端输出内容并提供相关的Linux命令建议：\n\n${selectedText.value}`

    // 清空输入框，让用户自己输入问题
    aiInputText.value = ''

    // 显示AI输入框
    showAIInput.value = true

    // 重新加载AI配置以确保使用最新配置
    await loadAIProviderInfo()

    // 存储选中内容的提示词，供后续AI请求使用
    selectedContentPrompt.value = selectionPrompt

    console.log('🤖 发送选中内容到AI助手:', selectedText.value)
  }
  showContextMenu.value = false
}

const clearSelection = () => {
  selectedText.value = ''
  selectedContentHint.value = ''
  selectedContentPrompt.value = ''
  aiInputText.value = ''
  console.log('🗑️ 清除选中内容')
}

// 加载账号列表
const loadAccountList = async () => {
  try {
    const connections = await invoke('load_ssh_connections') as any[]
    if (connections.length === 0) {
      console.log('📋 没有可用的SSH连接')
      return
    }

    // 假设使用第一个连接的账号列表（在实际应用中，应该获取当前活动连接）
    const connection = connections[0]
    accounts.value = connection.accounts || []

    console.log(`✅ SSH终端加载了 ${accounts.value.length} 个账号`)
  } catch (error) {
    console.error('❌ SSH终端加载账号列表失败:', error)
  }
}

// 处理账号切换
const handleAccountChange = () => {
  const activeTerminal = terminals.value.find(t => t.id === activeTerminalId.value)
  if (!activeTerminal || !activeTerminal.isConnected) {
    console.warn('⚠️ 没有活动的终端或终端未连接')
    return
  }

  const username = selectedUsername.value
  if (!username) {
    // 切换回默认账号 - 可以通过输入 exit 退出当前用户会话
    activeTerminal.terminal.write('exit\r')
    console.log('👤 退出当前用户会话，返回默认账号')
  } else {
    // 切换到指定账号 - 使用 sudo -u 或 su
    // 优先使用 sudo -u，因为它不需要目标用户的密码
    const command = `sudo -u ${username} bash || su - ${username}\r`
    activeTerminal.terminal.write(command)
    console.log(`👤 切换到账号: ${username}`)
  }
}

// 组件挂载时创建第一个终端
onMounted(() => {
  createNewTerminal()
  // 添加全局快捷键监听
  document.addEventListener('keydown', handleKeydown, true) // 使用捕获阶段
  console.log('✅ SSH终端快捷键监听器已添加')

  // 添加额外的调试监听器
  document.addEventListener('keydown', (event) => {
    if (event.ctrlKey && (event.key === 'i' || event.key === 'I')) {
      console.log('🔍 调试：检测到Ctrl+I按键', {
        key: event.key,
        ctrlKey: event.ctrlKey,
        target: event.target,
        currentTarget: event.currentTarget
      })
    }
  }, true)

  // 加载账号列表
  loadAccountList()
})

// 组件卸载时清理资源
onUnmounted(() => {
  // 移除快捷键监听
  document.removeEventListener('keydown', handleKeydown, true)
  console.log('✅ SSH终端快捷键监听器已移除')

  // 清理命令提示定时器
  if (hintTimeout.value) {
    clearTimeout(hintTimeout.value)
  }

  // 清理命令建议
  hideCommandSuggestions()

  // 窗口关闭时，清理所有终端会话
  // 注意：这是独立窗口，关闭时应该清理后端会话，避免会话泄漏
  terminals.value.forEach(terminalInstance => {
    try {
      // 清理ResizeObserver
      if (terminalInstance.resizeObserver) {
        try {
          terminalInstance.resizeObserver.disconnect()
          terminalInstance.resizeObserver = undefined
        } catch {}
      }

      // 清理事件监听器
      if (terminalInstance.unlisten) {
        try { terminalInstance.unlisten() } catch {}
      }

      stopReceivingOutput(terminalInstance)

      // 关闭后端终端会话（重要：避免会话泄漏）
      if (terminalInstance.isConnected) {
        try {
          invoke('ssh_close_terminal_session', { terminalId: terminalInstance.id })
            .then(() => console.log(`✅ 已关闭终端会话: ${terminalInstance.id}`))
            .catch(err => console.warn(`⚠️ 关闭终端会话失败: ${terminalInstance.id}`, err))
        } catch (error) {
          console.warn(`⚠️ 调用关闭终端会话失败: ${terminalInstance.id}`, error)
        }
      }

      // 释放前端 xterm 资源
      terminalInstance.terminal.dispose()
    } catch (error) {
      console.error('清理终端资源失败:', error)
    }
  })
})
</script>

<style scoped>
.ssh-terminal-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1e1e1e; /* Match terminal background for seamless look */
  color: #d4d4d4;
}

/* --- Tabs Design --- */
.terminal-tabs {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #252526; /* VS Code like darker header */
  border-bottom: 1px solid #1e1e1e;
  height: 36px;
  user-select: none;
}

.tabs-left {
  display: flex;
  flex: 1;
  overflow-x: auto;
  height: 100%;
  align-items: flex-end; /* Align tabs to bottom */
  padding-left: 0;
}

.tabs-right {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 8px;
  flex-shrink: 0;
  height: 100%;
  background: #252526;
}

.terminal-tab {
  display: flex;
  align-items: center;
  padding: 0 10px;
  height: 32px; /* Slightly shorter than container */
  background: #2d2d2d;
  border-right: 1px solid #1e1e1e;
  cursor: pointer;
  min-width: 140px;
  max-width: 200px;
  font-size: 12px;
  color: #969696;
  transition: background 0.2s, color 0.2s;
  margin-right: 1px;
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
}

.terminal-tab:hover {
  background: #383838;
  color: #e0e0e0;
}

.terminal-tab.active {
  background: #1e1e1e; /* Seamless with content */
  color: #ffffff;
  border-top: 2px solid var(--primary-color, #3b82f6);
  border-right: none;
  height: 36px; /* Full height to cover bottom border */
  z-index: 1;
}

.terminal-tab.add-tab {
  min-width: 32px;
  width: 32px;
  max-width: 32px;
  justify-content: center;
  background: transparent;
  border: none;
  margin-left: 2px;
}

.terminal-tab.add-tab:hover {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.tab-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 6px;
}

.tab-close {
  opacity: 0;
  font-size: 14px;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  transition: all 0.2s;
}

.terminal-tab:hover .tab-close,
.terminal-tab.active .tab-close {
  opacity: 1;
}

.tab-close:hover {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

/* --- Toolbar Actions --- */
.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  color: #cccccc;
  transition: all 0.2s;
}

.toolbar-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
}

.toolbar-btn.ai-btn.active {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
  border-color: rgba(59, 130, 246, 0.3);
}

.account-selector {
  font-size: 11px;
  padding: 4px 8px;
  background: #3c3c3c;
  border: 1px solid #454545;
  border-radius: 4px;
  color: #e0e0e0;
  outline: none;
  cursor: pointer;
  margin-right: 8px;
  min-width: 120px;
  height: 26px;
}

.account-selector:hover {
  border-color: #666;
}

.account-selector:focus {
  border-color: var(--primary-color, #3b82f6);
}

.connection-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.connection-status.connected {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.1);
  border: 1px solid rgba(74, 222, 128, 0.2);
}

.connection-status.connecting {
  color: #facc15;
  background: rgba(250, 204, 21, 0.1);
  border: 1px solid rgba(250, 204, 21, 0.2);
}

.connection-status.disconnected {
  color: #f87171;
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.2);
}

/* --- Terminal Content --- */
.terminal-content {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: #1e1e1e;
  padding: 4px 0 0 4px; /* Small padding for breathing room */
}

.terminal-instance {
  width: 100%;
  height: 100%;
}

.terminal-instance :deep(.xterm) {
  padding: 4px 0 0 8px; /* Padding inside the terminal */
}

.terminal-instance :deep(.xterm-viewport) {
  background: transparent !important;
}

/* Scrollbar refinements */
.terminal-instance :deep(.xterm-viewport)::-webkit-scrollbar {
  width: 10px;
}

.terminal-instance :deep(.xterm-viewport)::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.terminal-instance :deep(.xterm-viewport)::-webkit-scrollbar-thumb {
  background: #424242;
  border: 3px solid #1e1e1e; /* Creates padding effect */
  border-radius: 10px;
}

.terminal-instance :deep(.xterm-viewport)::-webkit-scrollbar-thumb:hover {
  background: #4f4f4f;
}

/* --- Empty State --- */
.no-terminal {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: #1e1e1e;
  color: #858585;
}

.no-terminal-content {
  text-align: center;
  max-width: 400px;
  padding: 40px;
  background: #252526;
  border-radius: 16px;
  border: 1px solid #333;
  box-shadow: 0 20px 40px rgba(0,0,0,0.2);
}

.no-terminal-content h3 {
  margin: 20px 0 8px 0;
  color: #e0e0e0;
  font-size: 18px;
  font-weight: 600;
}

.no-terminal-content p {
  margin: 0 0 30px 0;
  font-size: 14px;
  color: #999;
}

.create-terminal-btn {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 24px;
  background: var(--primary-color, #3b82f6);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.create-terminal-btn:hover {
  background: var(--primary-hover, #2563eb);
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
}

/* --- AI Floating Panel (Glassmorphism) --- */
.ai-floating-container {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  width: 90%;
  max-width: 600px;
  animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  user-select: none;
  filter: drop-shadow(0 12px 40px rgba(0,0,0,0.4));
}

/* AI Selection Hint */
.ai-selection-hint {
  margin-bottom: 8px;
  background: rgba(74, 222, 128, 0.1);
  border: 1px solid rgba(74, 222, 128, 0.3);
  border-radius: 8px;
  padding: 8px 12px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.selection-hint-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #4ade80;
}

.selection-hint-content span {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.clear-selection-btn {
  background: transparent;
  border: none;
  color: #f87171;
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.clear-selection-btn:hover {
  background: rgba(248, 113, 113, 0.2);
}

.ai-compact-panel {
  background: rgba(30, 30, 30, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.ai-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  cursor: move;
}

.ai-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ai-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #10b981;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
  animation: pulse 2s infinite;
}

.ai-text {
  font-size: 12px;
  font-weight: 600;
  color: #e4e4e7;
}

.ai-close-btn {
  color: #a1a1aa;
  background: transparent;
  border: none;
  border-radius: 4px;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.ai-close-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.ai-input-section {
  padding: 0;
  background: transparent;
}

.ai-textarea {
  width: 100%;
  padding: 14px 16px;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.6;
  color: #ffffff;
  font-family: var(--font-mono, monospace);
  min-height: 60px;
}

.ai-textarea::placeholder {
  color: #71717a;
}

.ai-input-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px 12px;
  background: transparent;
}

.ai-hint {
  font-size: 11px;
  color: #71717a;
  font-weight: 500;
}

.ai-right-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-counter {
  font-size: 11px;
  color: #71717a;
  font-weight: 500;
  font-family: 'Consolas', 'Monaco', monospace;
}

.ai-send-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.ai-send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
}

.ai-response {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.2);
  max-height: 300px;
  overflow-y: auto;
}

.ai-response-content {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ai-response-content code {
  display: block;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #4ade80;
  background: rgba(0, 0, 0, 0.3);
  padding: 10px;
  border-radius: 6px;
  border: 1px solid rgba(74, 222, 128, 0.2);
  white-space: pre-wrap;
}

.ai-action-buttons {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.ai-insert-btn, .ai-execute-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.ai-insert-btn {
  background: rgba(255, 255, 255, 0.05);
  color: #e4e4e7;
  border-color: rgba(255, 255, 255, 0.1);
}

.ai-insert-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}

.ai-execute-btn {
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.2);
}

.ai-execute-btn:hover {
  background: rgba(16, 185, 129, 0.2);
  border-color: rgba(16, 185, 129, 0.3);
  box-shadow: 0 0 10px rgba(16, 185, 129, 0.1);
}

/* --- Command Suggestions Panel --- */
.command-suggestions-panel {
  position: fixed;
  width: 420px;
  max-height: 400px;
  background: rgba(37, 37, 38, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  z-index: 900;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: fadeIn 0.15s ease-out;
}

.suggestions-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.suggestions-header span {
  font-size: 13px;
  font-weight: 600;
  color: #e4e4e7;
}

.suggestions-count {
  font-size: 11px;
  color: #71717a;
  font-weight: 500;
}

.suggestions-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  max-height: 320px;
}

.suggestion-item {
  padding: 10px 12px;
  margin-bottom: 6px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.suggestion-item:hover {
  background: rgba(59, 130, 246, 0.15);
  border-color: rgba(59, 130, 246, 0.3);
  transform: translateX(2px);
}

.suggestion-item.selected {
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.4);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}

.suggestion-command {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  font-weight: 600;
  color: #4ade80;
  margin-bottom: 4px;
}

.suggestion-description {
  font-size: 12px;
  color: #a1a1aa;
  line-height: 1.4;
  margin-bottom: 6px;
}

.suggestion-category {
  display: inline-block;
  font-size: 10px;
  padding: 2px 8px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  color: #71717a;
  font-weight: 500;
}

.suggestions-footer {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.02);
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 11px;
  color: #71717a;
  text-align: center;
}

/* --- Command Hint Panel --- */
.command-hint-panel {
  position: absolute;
  top: 50px;
  right: 20px;
  width: 450px;
  max-height: 500px;
  background: rgba(37, 37, 38, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  z-index: 850;
  overflow: hidden;
  opacity: 0;
  transform: translateY(-10px);
  transition: all 0.2s ease-out;
  pointer-events: none;
}

.command-hint-panel.hint-visible {
  opacity: 1;
  transform: translateY(0);
  pointer-events: all;
}

.hint-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: rgba(59, 130, 246, 0.1);
  border-bottom: 1px solid rgba(59, 130, 246, 0.2);
}

.hint-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.command-name {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 15px;
  font-weight: 700;
  color: #60a5fa;
}

.command-category {
  font-size: 10px;
  padding: 3px 8px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  color: #a1a1aa;
  font-weight: 500;
}

.hint-close {
  background: transparent;
  border: none;
  color: #71717a;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.hint-close:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e4e4e7;
}

.hint-content {
  padding: 16px;
  overflow-y: auto;
  max-height: 420px;
}

.hint-description {
  font-size: 13px;
  line-height: 1.6;
  color: #d4d4d4;
  margin-bottom: 16px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  border-left: 3px solid #3b82f6;
}

.hint-usage {
  margin-bottom: 16px;
}

.hint-usage strong {
  display: block;
  font-size: 12px;
  color: #a1a1aa;
  margin-bottom: 8px;
  font-weight: 600;
}

.hint-usage code {
  display: block;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: #4ade80;
  overflow-x: auto;
}

.hint-options {
  margin-bottom: 16px;
}

.hint-options strong {
  display: block;
  font-size: 12px;
  color: #a1a1aa;
  margin-bottom: 8px;
  font-weight: 600;
}

.options-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.option-tag {
  display: inline-block;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  padding: 4px 8px;
  background: rgba(168, 85, 247, 0.15);
  border: 1px solid rgba(168, 85, 247, 0.3);
  border-radius: 4px;
  color: #c084fc;
  font-weight: 500;
}

.hint-examples {
  margin-bottom: 8px;
}

.hint-examples strong {
  display: block;
  font-size: 12px;
  color: #a1a1aa;
  margin-bottom: 8px;
  font-weight: 600;
}

.examples-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.example-item {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  overflow: hidden;
}

.example-item code {
  display: block;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  padding: 8px 10px;
  color: #fbbf24;
  overflow-x: auto;
}

/* --- Context Menu --- */
.context-menu {
  position: fixed;
  background: rgba(37, 37, 38, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  padding: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 9999;
  min-width: 180px;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  color: #e4e4e7;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
}

.context-menu-item:hover {
  background: rgba(59, 130, 246, 0.15);
  color: #ffffff;
}

.context-menu-ai {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  margin-top: 4px;
  padding-top: 12px !important;
}

.context-menu-ai:hover {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

/* --- Animations --- */
@keyframes slideUp {
  from { opacity: 0; transform: translateX(-50%) translateY(20px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

@keyframes fadeIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
  70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.ai-loading {
  animation: rotate 1s linear infinite;
}

/* --- Scrollbars for specific elements --- */
.ai-response::-webkit-scrollbar,
.suggestions-list::-webkit-scrollbar,
.hint-content::-webkit-scrollbar {
  width: 6px;
}

.ai-response::-webkit-scrollbar-track,
.suggestions-list::-webkit-scrollbar-track,
.hint-content::-webkit-scrollbar-track {
  background: transparent;
}

.ai-response::-webkit-scrollbar-thumb,
.suggestions-list::-webkit-scrollbar-thumb,
.hint-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}

.ai-response::-webkit-scrollbar-thumb:hover,
.suggestions-list::-webkit-scrollbar-thumb:hover,
.hint-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}
</style>
