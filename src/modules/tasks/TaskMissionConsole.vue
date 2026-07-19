<template>
  <section class="mission-console" aria-labelledby="mission-console-title">
    <header class="console-header">
      <div>
        <p class="eyebrow">任务控制台</p>
        <h2 id="mission-console-title">{{ snapshot.task_id }}</h2>
      </div>
      <div class="status-cluster" role="status" aria-live="polite">
        <span class="status-text">{{ snapshot.status }}</span>
        <span class="phase-text">阶段：{{ snapshot.phase }}</span>
      </div>
    </header>

    <div class="control-row" aria-label="任务生命周期控制">
      <button v-if="snapshot.status === 'paused'" type="button" @click="emit('resume')">恢复任务</button>
      <button v-else type="button" :disabled="terminal" @click="emit('pause')">暂停任务</button>
      <button type="button" class="danger" :disabled="terminal" @click="requestConfirmation('stop')">终止任务</button>
      <button type="button" class="secondary" :disabled="terminal" @click="requestConfirmation('takeover')">人工接管</button>
      <label class="inline-control">自治等级
        <select :value="snapshot.autonomyMode ?? 'supervised'" :disabled="terminal" @change="changeAutonomy">
          <option value="advisory">建议模式</option>
          <option value="supervised">监督模式</option>
          <option value="unattended">无人值守模式</option>
        </select>
      </label>
      <label class="inline-control">动作上限
        <select :value="snapshot.actionLimit ?? 'post_verify'" :disabled="terminal" @change="changeActionLimit">
          <option value="observe">观察</option>
          <option value="probe">轻量验证</option>
          <option value="credential_test">凭据测试</option>
          <option value="exploit">漏洞验证</option>
          <option value="session_verify">会话确认</option>
          <option value="post_verify">目标验证</option>
        </select>
      </label>
    </div>

    <div v-if="pendingControl" class="confirm-panel" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
      <h3 id="confirm-title">请确认控制操作</h3>
      <p>{{ pendingControl === 'stop' ? '终止会停止后续调度并进入清理流程。' : '接管会切换到建议模式，并暂停当前任务。' }}</p>
      <div class="confirm-actions">
        <button type="button" class="danger" @click="confirmControl">确认</button>
        <button type="button" class="secondary" @click="pendingControl = ''">取消</button>
      </div>
    </div>

    <div class="summary-grid" aria-label="任务摘要">
      <div><span>发现</span><strong>{{ snapshot.findings }}</strong></div>
      <div><span>证据</span><strong>{{ snapshot.evidence }}</strong></div>
      <div><span>资产节点</span><strong>{{ Object.keys(snapshot.assets).length }}</strong></div>
      <div><span>风险</span><strong>{{ snapshot.riskLevel ?? '未评估' }}</strong></div>
    </div>

    <section class="panel" aria-labelledby="budget-title">
      <h3 id="budget-title">预算与证据状态</h3>
      <dl class="metric-list">
        <template v-for="(value, key) in snapshot.budget" :key="key">
          <dt>{{ key }}</dt><dd>{{ value }}</dd>
        </template>
      </dl>
      <p v-if="!Object.keys(snapshot.budget).length" class="muted">暂无预算事件。</p>
    </section>

    <section class="panel" aria-labelledby="action-title">
      <h3 id="action-title">当前动作</h3>
      <p v-if="snapshot.currentAction" class="action-card">
        <strong>{{ snapshot.currentAction.plugin }}</strong> · {{ snapshot.currentAction.target }}
        <span>选择原因：{{ snapshot.currentAction.reason || '依据当前证据与预算排序' }}</span>
      </p>
      <p v-else class="muted">当前没有正在执行的动作。</p>
    </section>

    <section class="panel" aria-labelledby="candidate-title">
      <h3 id="candidate-title">候选队列</h3>
      <table>
        <caption>候选动作、风险与选择原因</caption>
        <thead><tr><th scope="col">动作</th><th scope="col">目标</th><th scope="col">风险</th><th scope="col">选择原因</th></tr></thead>
        <tbody>
          <tr v-for="candidate in snapshot.candidates" :key="candidate.action_id">
            <td>{{ candidate.action }}</td><td>{{ candidate.target }}</td><td>{{ candidate.risk }}</td><td>{{ candidate.reason }}</td>
          </tr>
          <tr v-if="!snapshot.candidates.length"><td colspan="4" class="muted">暂无候选动作。</td></tr>
        </tbody>
      </table>
    </section>

    <section class="panel" aria-labelledby="asset-title">
      <h3 id="asset-title">目标图谱</h3>
      <table>
        <caption>已观测资产节点与证据状态</caption>
        <thead><tr><th scope="col">节点</th><th scope="col">类型</th><th scope="col">状态</th><th scope="col">置信度</th></tr></thead>
        <tbody>
          <tr v-for="asset in Object.values(snapshot.assets)" :key="asset.asset_id">
            <td>{{ asset.label }}</td><td>{{ asset.kind }}</td><td>{{ asset.status }}</td><td>{{ Math.round(asset.confidence * 100) }}%</td>
          </tr>
          <tr v-if="!Object.keys(snapshot.assets).length"><td colspan="4" class="muted">暂无资产事件。</td></tr>
        </tbody>
      </table>
    </section>

    <div v-if="snapshot.warnings.length" class="warnings" role="alert">
      <strong>需要关注</strong>
      <ul><li v-for="warning in snapshot.warnings" :key="warning">{{ warning }}</li></ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TaskSnapshot } from './contracts'

const props = defineProps<{ snapshot: TaskSnapshot }>()
const pendingControl = ref<'stop' | 'takeover' | ''>('')
const emit = defineEmits<{
  pause: []
  resume: []
  stop: []
  takeover: []
  autonomy: [mode: 'advisory' | 'supervised' | 'unattended']
  actionLimit: [level: NonNullable<TaskSnapshot['actionLimit']>]
}>()

const terminal = computed(() => ['cancelled', 'completed', 'done', 'failed', 'stopped'].includes(props.snapshot.status))

function requestConfirmation(control: 'stop' | 'takeover'): void {
  if (!terminal.value) pendingControl.value = control
}

function confirmControl(): void {
  const control = pendingControl.value
  pendingControl.value = ''
  if (control === 'stop') emit('stop')
  if (control === 'takeover') emit('takeover')
}

function changeAutonomy(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  if (value === 'advisory' || value === 'supervised' || value === 'unattended') emit('autonomy', value)
}

function changeActionLimit(event: Event): void {
  emit('actionLimit', (event.target as HTMLSelectElement).value as NonNullable<TaskSnapshot['actionLimit']>)
}
</script>

<style scoped>
.mission-console { display: grid; gap: 14px; max-width: 1080px; padding: 20px; color: #172033; background: #f8fafc; border: 1px solid #d7deea; border-radius: 14px; }
.console-header, .control-row { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.console-header { justify-content: space-between; }
.eyebrow { margin: 0 0 3px; color: #3157a6; font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
h2, h3 { margin: 0; } h2 { font-size: 20px; } h3 { margin-bottom: 10px; font-size: 15px; color: #1e3a8a; }
.status-cluster { display: grid; gap: 3px; text-align: right; } .status-text { font-weight: 800; } .phase-text, .muted { color: #526174; font-size: 12px; }
button, select { min-height: 36px; padding: 7px 12px; border: 1px solid #1d4ed8; border-radius: 7px; color: #fff; background: #1d4ed8; font: inherit; font-weight: 700; cursor: pointer; }
button.secondary, .inline-control select { color: #172033; background: #fff; border-color: #9aa8bd; } button.danger { border-color: #b91c1c; background: #b91c1c; }
button:disabled, select:disabled { cursor: not-allowed; opacity: .5; }
.inline-control { display: inline-flex; align-items: center; gap: 6px; color: #334155; font-size: 12px; font-weight: 700; } .inline-control select { min-height: 32px; padding: 4px 7px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; } .summary-grid div { display: grid; gap: 3px; padding: 12px; border: 1px solid #d7deea; border-radius: 9px; background: #fff; } .summary-grid span { color: #526174; font-size: 12px; } .summary-grid strong { font-size: 19px; }
.panel { padding: 14px; border: 1px solid #d7deea; border-radius: 10px; background: #fff; overflow-x: auto; }
.metric-list { display: grid; grid-template-columns: repeat(2, minmax(120px, 1fr)); gap: 6px 18px; margin: 0; } .metric-list dt { color: #526174; } .metric-list dd { margin: 0; font-weight: 700; }
.action-card { display: grid; gap: 5px; margin: 0; padding: 10px; border-left: 4px solid #1d4ed8; background: #eff6ff; } .action-card span { color: #334155; font-size: 12px; }
table { width: 100%; border-collapse: collapse; min-width: 620px; font-size: 13px; } caption { margin-bottom: 7px; text-align: left; color: #526174; font-size: 12px; } th, td { padding: 9px; border: 1px solid #cbd5e1; text-align: left; vertical-align: top; } th { color: #172033; background: #e2e8f0; }
.warnings { padding: 10px 12px; border: 1px solid #b45309; border-radius: 8px; color: #78350f; background: #fffbeb; } .warnings ul { margin: 5px 0 0 18px; padding: 0; }
.confirm-panel { padding: 14px; border: 2px solid #b91c1c; border-radius: 10px; background: #fff7f7; } .confirm-panel p { margin: 8px 0 12px; } .confirm-actions { display: flex; gap: 8px; }
:is(button, select):focus-visible { outline: 3px solid #f59e0b; outline-offset: 2px; }
@media (max-width: 700px) { .summary-grid { grid-template-columns: repeat(2, 1fr); } .status-cluster { text-align: left; } }
</style>
