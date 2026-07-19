<template>
  <section class="task-workspace" aria-label="自主安全任务工作台">
    <div v-if="errorMessage" class="workspace-error" role="alert">{{ errorMessage }}</div>
    <TaskCreationWizard
      v-if="!taskId"
      :submitting="submitting"
      @submit="createTask"
    />
    <TaskMissionConsole
      v-else-if="snapshot"
      :snapshot="snapshot"
      @pause="runControl(() => controller.pause(taskId))"
      @resume="runControl(() => controller.resume(taskId))"
      @stop="runControl(() => controller.stop(taskId))"
      @takeover="takeOver"
      @autonomy="setAutonomy"
      @action-limit="setActionLimit"
    />
    <div v-else class="workspace-loading" role="status">正在装载任务事件流…</div>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { pythonApi } from '../../config/python-api.config'
import { aiService } from '../ai/aiService'
import type { TaskSnapshot } from './contracts'
import { TaskController, type TaskLifecycleApi } from './taskController'
import type { TaskCreationPayload } from './taskCreation'
import { TaskStore } from './taskStore'
import TaskCreationWizard from './TaskCreationWizard.vue'
import TaskMissionConsole from './TaskMissionConsole.vue'

export interface TaskWorkspaceApi extends TaskLifecycleApi {
  pentestStart(params: Record<string, unknown>): Promise<{success: boolean; task_id: string; message?: string}>
  pentestStoreModelSecret?(apiKey: string, provider?: string): Promise<{secret_ref: string}>
}

const props = defineProps<{
  api?: TaskWorkspaceApi
  modelConfig?: {api_key?: string; model?: string; base_url?: string; provider?: string; temperature?: number}
}>()
const emit = defineEmits<{started: [taskId: string]}>()

const api = props.api ?? (pythonApi as TaskWorkspaceApi)
const controller = new TaskController(api, new TaskStore())
const taskId = ref('')
const snapshot = ref<TaskSnapshot>()
const submitting = ref(false)
const errorMessage = ref('')
let watcher: AbortController | undefined

const unsubscribe = controller.subscribe(value => {
  if (value.task_id === taskId.value) snapshot.value = value
})

function loadModelConfig() {
  if (props.modelConfig) return props.modelConfig
  const value = aiService.getConfig()
  return {
    api_key: String(value?.apiKey ?? ''),
    model: String(value?.model ?? 'gpt-4o-mini'),
    base_url: String(value?.baseUrl ?? 'https://api.openai.com/v1'),
    provider: String(value?.provider ?? 'openai'),
    temperature: Number(value?.temperature ?? 0.3),
  }
}

async function createTask(payload: TaskCreationPayload): Promise<void> {
  submitting.value = true
  errorMessage.value = ''
  try {
    const modelConfig = loadModelConfig()
    const modelApiKey = modelConfig.api_key && !modelConfig.api_key.startsWith('secret_')
      ? (api.pentestStoreModelSecret
        ? (await api.pentestStoreModelSecret(modelConfig.api_key, modelConfig.provider)).secret_ref
        : modelConfig.api_key)
      : modelConfig.api_key
    const response = await api.pentestStart({
      ...payload,
      ...modelConfig,
      api_key: modelApiKey,
      execution_mode: payload.max_concurrency > 1 ? 'parallel' : 'serial',
      max_rounds: 30,
      dry_run: false,
    })
    if (!response.success || !response.task_id) throw new Error(response.message || '任务启动结果缺少任务标识')
    taskId.value = response.task_id
    emit('started', response.task_id)
    snapshot.value = await controller.sync(response.task_id)
    watcher?.abort()
    watcher = new AbortController()
    void controller.watch(response.task_id, {signal: watcher.signal}).catch(showError)
  } catch (error) {
    showError(error)
  } finally {
    submitting.value = false
  }
}

async function runControl(operation: () => Promise<TaskSnapshot>): Promise<void> {
  errorMessage.value = ''
  try {
    snapshot.value = await operation()
  } catch (error) {
    showError(error)
  }
}

function setAutonomy(mode: 'advisory' | 'supervised' | 'unattended'): void {
  void runControl(() => controller.setAutonomy(taskId.value, mode, 'workspace autonomy control'))
}

function setActionLimit(level: NonNullable<TaskSnapshot['actionLimit']>): void {
  void runControl(() => controller.setActionLimit(taskId.value, level, 'workspace live action ceiling'))
}

async function takeOver(): Promise<void> {
  await runControl(() => controller.setAutonomy(taskId.value, 'advisory', 'operator takeover'))
  if (snapshot.value?.status === 'running') await runControl(() => controller.pause(taskId.value))
}

function showError(error: unknown): void {
  errorMessage.value = error instanceof Error ? error.message : String(error)
}

onBeforeUnmount(() => {
  watcher?.abort()
  unsubscribe()
})
</script>

<style scoped>
.task-workspace { display: grid; gap: 12px; width: min(1120px, 94vw); max-height: 86vh; overflow: auto; padding: 4px; }
.workspace-error { padding: 10px 12px; border: 1px solid #b91c1c; border-radius: 8px; color: #7f1d1d; background: #fef2f2; }
.workspace-loading { padding: 28px; color: #334155; text-align: center; }
</style>
