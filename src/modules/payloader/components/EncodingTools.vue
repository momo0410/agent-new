<template>
  <div class="encoding-tools">
    <div class="encoding-header">
      <h2>编解码工具</h2>
      <p>支持多种编码格式的转换和解码操作</p>
    </div>

    <div class="encoding-tabs">
      <button
        v-for="option in encodingOptions"
        :key="option.id"
        :class="['encoding-tab', { active: activeEncoding === option.id }]"
        @click="selectEncoding(option.id)"
        :title="option.desc"
      >
        <span class="tab-icon">{{ option.icon }}</span>
        <span class="tab-name">{{ option.name }}</span>
      </button>
    </div>

    <div class="encoding-content">
      <div class="encoding-panel">
        <div class="panel-header">
          <label>输入</label>
          <button class="clear-btn" @click="clearAll">清空</button>
        </div>
        <textarea
          v-model="input"
          :placeholder="activeEncoding === 'jwt' ? '编码请输入 JSON Payload，解码请输入 JWT Token...' : '请输入要编码/解码的内容...'"
          spellcheck="false"
        />
      </div>

      <div class="encoding-actions">
        <button class="action-btn encode" @click="encode">
          编码
        </button>
        <button class="action-btn swap" @click="swapInputOutput">
          交换
        </button>
        <button class="action-btn decode" @click="decode">
          解码
        </button>
      </div>

      <div class="encoding-panel">
        <div class="panel-header">
          <label>输出</label>
          <button
            :class="['copy-btn', { copied: copied }]"
            @click="copyToClipboard"
            :disabled="!output"
          >
            {{ copied ? '已复制' : '复制' }}
          </button>
        </div>
        <textarea
          :value="error || output"
          readonly
          :class="{ error: error }"
          placeholder="结果将显示在这里..."
        />
      </div>
    </div>

    <div class="encoding-info">
      <h4>使用说明</h4>
      <p v-if="activeEncoding === 'url'">
        URL 编码用于对 URL 中的特殊字符进行转义，确保 URL 的正确传输。常用于处理 URL 参数中的中文和特殊符号。
      </p>
      <p v-else-if="activeEncoding === 'base64'">
        Base64 是一种基于 64 个可打印字符来表示二进制数据的编码方法。常用于在文本协议中传输二进制数据。
      </p>
      <p v-else-if="activeEncoding === 'hex'">
        十六进制编码将每个字节转换为两个十六进制字符。常用于查看和编辑二进制数据。
      </p>
      <p v-else-if="activeEncoding === 'html'">
        HTML 实体编码用于在 HTML 文档中显示特殊字符，防止 XSS 攻击。将特殊字符转换为 HTML 实体。
      </p>
      <p v-else-if="activeEncoding === 'unicode'">
        Unicode 编码将字符转换为 Unicode 转义序列（\uXXXX 格式）。常用于国际化文本处理。
      </p>
      <p v-else-if="activeEncoding === 'jwt'">
        JWT (JSON Web Token) 支持编码和解码。编码时请输入 JSON payload，系统会生成一个使用 none 算法的未签名 JWT；解码时请输入完整的 JWT Token。
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { decodeByType, encodeByType, type EncodingType } from '../utils/encoding';

interface EncodingOption {
  id: EncodingType;
  name: string;
  icon: string;
  desc: string;
}

const encodingOptions: EncodingOption[] = [
  { id: 'url', name: 'URL', icon: '🔗', desc: 'URL 编码/解码' },
  { id: 'base64', name: 'Base64', icon: '📦', desc: 'Base64 编码/解码' },
  { id: 'hex', name: 'Hex', icon: '🔢', desc: '十六进制编码/解码' },
  { id: 'html', name: 'HTML', icon: '📄', desc: 'HTML 实体编码/解码' },
  { id: 'unicode', name: 'Unicode', icon: '🌐', desc: 'Unicode 编码/解码' },
  { id: 'jwt', name: 'JWT', icon: '🔑', desc: 'JWT 编码/解码' },
];

const input = ref('');
const output = ref('');
const activeEncoding = ref<EncodingType>('url');
const copied = ref(false);
const error = ref('');

const getErrorMessage = (value: unknown): string => value instanceof Error ? value.message : String(value);

const selectEncoding = (id: EncodingType) => {
  activeEncoding.value = id;
  clearAll();
};

const encode = () => {
  error.value = '';
  try {
    output.value = encodeByType(activeEncoding.value, input.value);
  } catch (value) {
    output.value = '';
    error.value = '编码失败: ' + getErrorMessage(value);
  }
};

const decode = () => {
  error.value = '';
  try {
    output.value = decodeByType(activeEncoding.value, input.value);
  } catch (value) {
    output.value = '';
    error.value = '解码失败: ' + getErrorMessage(value);
  }
};

const swapInputOutput = () => {
  const visibleOutput = error.value || output.value;
  const temp = input.value;
  input.value = visibleOutput;
  output.value = temp;
  error.value = '';
  copied.value = false;
};

const copyToClipboard = async () => {
  await navigator.clipboard.writeText(output.value);
  copied.value = true;
  setTimeout(() => copied.value = false, 2000);
};

const clearAll = () => {
  input.value = '';
  output.value = '';
  error.value = '';
};
</script>

<style scoped>
.encoding-tools {
  padding: 24px;
  max-width: 1000px;
  margin: 0 auto;
}

.encoding-header {
  margin-bottom: 24px;
}

.encoding-header h2 {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 8px 0;
  color: var(--text-primary);
}

.encoding-header p {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.encoding-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 24px;
}

.encoding-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.encoding-tab:hover {
  border-color: var(--primary-color);
  color: var(--text-primary);
}

.encoding-tab.active {
  background: rgba(0, 240, 255, 0.1);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.tab-icon {
  font-size: 16px;
}

.tab-name {
  font-size: 13px;
  font-weight: 500;
}

.encoding-content {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 16px;
  align-items: start;
}

.encoding-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-header label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-tertiary);
}

.clear-btn, .copy-btn {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-tertiary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.clear-btn:hover, .copy-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.copy-btn.copied {
  background: rgba(0, 255, 136, 0.1);
  border-color: var(--success-color, #00ff88);
  color: var(--success-color, #00ff88);
}

.encoding-panel textarea {
  width: 100%;
  min-height: 200px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  resize: none;
  transition: border-color 0.2s ease;
}

.encoding-panel textarea:focus {
  outline: none;
  border-color: var(--primary-color);
}

.encoding-panel textarea.error {
  border-color: var(--danger-color, #ff0055);
  color: var(--danger-color, #ff0055);
}

.encoding-panel textarea::placeholder {
  color: var(--text-tertiary);
}

.encoding-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 32px;
}

.action-btn {
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.action-btn:hover:not(:disabled) {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.encode:hover:not(:disabled) {
  background: rgba(0, 240, 255, 0.1);
}

.action-btn.decode:hover:not(:disabled) {
  background: rgba(255, 0, 255, 0.1);
  border-color: var(--accent-color, #a855f7);
  color: var(--accent-color, #a855f7);
}

.action-btn.swap {
  background: rgba(255, 102, 0, 0.1);
  border-color: var(--warning-color, #ff6600);
  color: var(--warning-color, #ff6600);
}

.encoding-info {
  margin-top: 24px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.encoding-info h4 {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: var(--warning-color, #ffcc00);
}

.encoding-info p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

@media (max-width: 768px) {
  .encoding-content {
    grid-template-columns: 1fr;
  }

  .encoding-actions {
    flex-direction: row;
    justify-content: center;
    padding-top: 0;
  }
}
</style>
