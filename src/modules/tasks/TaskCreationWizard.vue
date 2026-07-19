<template>
  <form class="task-wizard" @submit.prevent="submit">
    <header class="wizard-header">
      <div>
        <p class="eyebrow">任务创建向导</p>
        <h2 id="task-wizard-title">先确认边界，再启动任务</h2>
      </div>
      <span class="step-count" aria-label="已完成四个必填区块">4 个必填区块</span>
    </header>

    <div v-if="errors.length" class="wizard-errors" role="alert" tabindex="-1">
      <strong>启动前还需要补充：</strong>
      <ul>
        <li v-for="error in errors" :key="error">{{ error }}</li>
      </ul>
    </div>

    <fieldset>
      <legend>一、授权与依据</legend>
      <label for="task-authorization">授权说明</label>
      <textarea
        id="task-authorization"
        v-model="draft.authorizationBasis"
        rows="3"
        required
        placeholder="例如：课程实验单元 3，教师发布的本地 fixture"
      />
      <p class="field-hint">该说明会进入任务审计与报告来源链。</p>
    </fieldset>

    <fieldset>
      <legend>二、范围</legend>
      <label for="task-target">目标、域名或 CIDR</label>
      <input id="task-target" v-model="draft.target" required autocomplete="off" placeholder="TARGET" />
      <label for="task-ports">允许端口</label>
      <input id="task-ports" v-model="draft.allowedPorts" required inputmode="numeric" placeholder="80, 443, 8080" />
      <p class="field-hint">只会提交解析后的端口集合，范围外地址由后端策略再次检查。</p>
    </fieldset>

    <fieldset>
      <legend>三、风险与自治等级</legend>
      <label class="check-row" for="task-risk">
        <input id="task-risk" v-model="draft.riskAcknowledged" type="checkbox" />
        <span>我已阅读风险、停止条件和证据确认规则。</span>
      </label>
      <label for="task-autonomy">自治等级</label>
      <select id="task-autonomy" v-model="draft.autonomyMode">
        <option value="advisory">建议模式</option>
        <option value="supervised">监督模式</option>
        <option value="unattended">无人值守模式</option>
      </select>
    </fieldset>

    <fieldset>
      <legend>四、预算</legend>
      <div class="budget-grid">
        <label>总时长（秒）<input v-model.number="draft.maxDurationSeconds" type="number" min="1" /></label>
        <label>命令数<input v-model.number="draft.maxCommands" type="number" min="1" /></label>
        <label>网络请求数<input v-model.number="draft.maxNetworkRequests" type="number" min="1" /></label>
        <label>验证尝试数<input v-model.number="draft.maxBruteforceAttempts" type="number" min="1" /></label>
        <label>最大并发<input v-model.number="draft.maxConcurrency" type="number" min="1" max="64" /></label>
      </div>
    </fieldset>

    <footer class="wizard-actions">
      <span class="validation-hint" aria-live="polite">{{ canSubmit ? '边界检查通过，可提交任务。' : '完成四个区块后才能提交。' }}</span>
      <button type="submit" :disabled="!canSubmit || submitting">{{ submitting ? '提交中…' : '创建任务' }}</button>
    </footer>
  </form>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { toTaskCreationPayload, validateTaskCreation, type TaskCreationDraft, type TaskCreationPayload } from './taskCreation'

const props = withDefaults(defineProps<{ submitting?: boolean }>(), { submitting: false })
const emit = defineEmits<{ submit: [payload: TaskCreationPayload] }>()

const draft = reactive<TaskCreationDraft>({
  authorizationBasis: '',
  target: '',
  allowedPorts: '80, 443',
  riskAcknowledged: false,
  maxDurationSeconds: 3600,
  maxCommands: 1000,
  maxNetworkRequests: 10000,
  maxBruteforceAttempts: 100,
  maxConcurrency: 1,
  autonomyMode: 'supervised',
})

const errors = computed(() => validateTaskCreation(draft))
const canSubmit = computed(() => errors.value.length === 0 && !props.submitting)

function submit(): void {
  if (!canSubmit.value) return
  emit('submit', toTaskCreationPayload(draft))
}
</script>

<style scoped>
.task-wizard { display: grid; gap: 16px; max-width: 760px; padding: 22px; color: #172033; background: #fff; border: 1px solid #d7deea; border-radius: 14px; }
.wizard-header, .wizard-actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.eyebrow { margin: 0 0 4px; color: #3157a6; font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
h2 { margin: 0; font-size: 21px; }
.step-count { padding: 5px 9px; border-radius: 999px; color: #164e63; background: #cffafe; font-size: 12px; font-weight: 700; }
fieldset { display: grid; gap: 8px; margin: 0; padding: 14px; border: 1px solid #d7deea; border-radius: 10px; }
legend { padding: 0 6px; color: #1d4ed8; font-weight: 800; }
label { display: grid; gap: 5px; font-size: 13px; font-weight: 700; }
input, textarea, select { width: 100%; box-sizing: border-box; padding: 9px 10px; border: 1px solid #9aa8bd; border-radius: 7px; color: #172033; background: #fff; font: inherit; }
textarea { resize: vertical; }
.field-hint, .validation-hint { margin: 0; color: #526174; font-size: 12px; line-height: 1.5; }
.check-row { display: flex; grid-template-columns: none; align-items: flex-start; font-weight: 600; }
.check-row input { width: auto; margin-top: 2px; }
.budget-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; }
.wizard-errors { padding: 10px 12px; border: 1px solid #b91c1c; border-radius: 8px; color: #7f1d1d; background: #fef2f2; }
.wizard-errors ul { margin: 6px 0 0 18px; padding: 0; }
button { padding: 9px 16px; border: 0; border-radius: 8px; color: #fff; background: #1d4ed8; font: inherit; font-weight: 800; cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .5; }
:is(input, textarea, select, button):focus-visible { outline: 3px solid #f59e0b; outline-offset: 2px; }
@media (max-width: 600px) { .wizard-header, .wizard-actions { align-items: flex-start; flex-direction: column; } }
</style>
