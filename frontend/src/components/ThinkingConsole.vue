<template>
  <div class="h-full flex flex-col font-mono relative">
    
    <div class="flex items-center gap-2 mb-2 pb-2 border-b border-slate-700/50 shrink-0">
      <div class="flex gap-1.5">
        <div class="w-2.5 h-2.5 rounded-full bg-red-500/80"></div>
        <div class="w-2.5 h-2.5 rounded-full bg-yellow-500/80"></div>
        <div class="w-2.5 h-2.5 rounded-full bg-green-500/80"></div>
      </div>
      <span class="text-[10px] text-slate-500 ml-2">sys/agent/workflow.log</span>
      <span class="ml-auto text-[10px] text-blue-400 border border-blue-400/30 px-1 rounded">{{ statusText }}</span>
    </div>

    <div ref="logContainer" class="flex-1 overflow-y-auto text-xs space-y-1.5 pr-2 custom-scrollbar">
      
      <div v-for="(log, index) in logs" :key="index" class="flex items-start gap-2 break-all">
        <span class="text-slate-600 shrink-0">[{{ log.time }}]</span>
        <span :class="['shrink-0 font-bold', getAgentColor(log.agent)]">[{{ log.agent }}]</span>
        <span :class="getContentColor(log.type)">{{ log.content }}</span>
      </div>

      <div v-if="isRunning" class="flex items-start gap-2">
        <span class="text-slate-600 shrink-0">[{{ currentTime }}]</span>
        <span class="text-blue-400 font-bold shrink-0">[System]</span>
        <span class="text-slate-300">等待下一个指令<span class="animate-pulse font-bold ml-1 text-green-400">_</span></span>
      </div>
      
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'

// 接收父组件传来的脱敏开关状态
const props = defineProps({
  isDesensitized: {
    type: Boolean,
    default: false
  }
})

const logs = ref([])
const isRunning = ref(false)
const logContainer = ref(null)
const statusText = ref('IDLE')
const currentTime = ref('')

let timeInterval = null

onMounted(() => {
  timeInterval = setInterval(() => {
    const now = new Date()
    currentTime.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
  }, 1000)
})

onUnmounted(() => {
  if (timeInterval) clearInterval(timeInterval)
})

const getAgentColor = (agent) => {
  const map = { 'Reader': 'text-amber-200', 'Reviewer': 'text-blue-200', 'Critic': 'text-purple-200', 'System': 'text-slate-400', 'Error': 'text-red-400' }
  return map[agent] || 'text-slate-400'
}
const getContentColor = (type) => {
  if (type === 'error') return 'text-red-400'
  if (type === 'success') return 'text-green-400'
  return 'text-slate-300'
}

const scrollToBottom = async () => {
  await nextTick()
  if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight
}

// 核心：脱敏过滤器
const maskText = (text) => {
  if (!props.isDesensitized || !text) return text;
  let masked = text;
  // 伪脱敏逻辑：替换手机号
  masked = masked.replace(/(\d{3})\d{4}(\d{4})/g, '$1****$2');
  // 伪脱敏逻辑：替换常见姓名（连续2-3个中文字符且包含特定姓氏的，简单处理为替换中间字）
  masked = masked.replace(/([李王张刘陈杨黄赵吴周徐孙马朱胡郭林郑林何高梁][\u4e00-\u9fa5]{1,2})/g, (match) => {
    return match.length === 2 ? match[0] + '*' : match[0] + '*' + match[2];
  });
  return masked;
}

const appendLog = (agent, content, type = 'info') => {
  const now = new Date()
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
  logs.value.push({ time: timeStr, agent, content, type })
  if (logs.value.length > 100) logs.value.shift()
  scrollToBottom()
}

const setStatus = (running, text) => {
  isRunning.value = running
  statusText.value = text
  scrollToBottom()
}
const clearLogs = () => { logs.value = [] }

defineExpose({ appendLog, setStatus, clearLogs })
</script>