<template>
  <div class="w-full h-full flex items-center justify-center relative select-none">
    
    <svg class="absolute inset-0 w-full h-full pointer-events-none" z-index="0">
      <path d="M 25% 50% L 50% 50%" stroke="#334155" stroke-width="2" fill="none" stroke-dasharray="6,6" />
      <path v-if="lineStatus.readerToReviewer" d="M 25% 50% L 50% 50%" stroke="#3b82f6" stroke-width="2" fill="none" stroke-dasharray="6,6" class="animate-dash" />
      
      <path d="M 50% 50% L 75% 50%" stroke="#334155" stroke-width="2" fill="none" stroke-dasharray="6,6" />
      <path v-if="lineStatus.reviewerToCritic" d="M 50% 50% L 75% 50%" stroke="#3b82f6" stroke-width="2" fill="none" stroke-dasharray="6,6" class="animate-dash" />
    </svg>

    <div class="relative z-10 w-full flex justify-around items-center px-8">
      
      <div class="agent-node" :class="getNodeClass('reader')">
        <div class="icon-box bg-slate-800 text-slate-300">📄</div>
        <div class="flex flex-col">
          <span class="font-bold text-slate-200 tracking-wider">Reader</span>
          <span class="text-[10px] uppercase tracking-widest transition-colors duration-300" :class="getStatusTextColor('reader')">
            {{ getStatusText('reader') }}
          </span>
        </div>
        <div v-if="agents.reader === 'active'" class="absolute -inset-1 bg-blue-500/20 blur-md rounded-xl -z-10 animate-pulse"></div>
      </div>

      <div class="agent-node" :class="getNodeClass('reviewer')">
        <div class="icon-box bg-slate-800 text-slate-300">👁️</div>
        <div class="flex flex-col">
          <span class="font-bold text-slate-200 tracking-wider">Reviewer</span>
          <span class="text-[10px] uppercase tracking-widest transition-colors duration-300" :class="getStatusTextColor('reviewer')">
            {{ getStatusText('reviewer') }}
          </span>
        </div>
        <div v-if="agents.reviewer === 'active'" class="absolute -inset-1 bg-blue-500/20 blur-md rounded-xl -z-10 animate-pulse"></div>
      </div>

      <div class="agent-node" :class="getNodeClass('dispatcher')">
        <div class="icon-box bg-slate-800 text-slate-300">⚖️</div>
        <div class="flex flex-col">
          <span class="font-bold text-slate-200 tracking-wider">Dispatcher</span>
          <span class="text-[10px] uppercase tracking-widest transition-colors duration-300" :class="getStatusTextColor('dispatcher')">
            {{ getStatusText('dispatcher') }}
          </span>
        </div>
        <div v-if="agents.dispatcher === 'active'" class="absolute -inset-1 bg-emerald-500/20 blur-md rounded-xl -z-10 animate-pulse"></div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { reactive } from 'vue'

// 节点状态：waiting, active, done, error
const agents = reactive({
  reader: 'waiting',
  reviewer: 'waiting',
  dispatcher: 'waiting'
})

// 连线流动状态
const lineStatus = reactive({
  readerToReviewer: false,
  reviewerToCritic: false
})

// --- 对外暴露的方法：给 App.vue 调用 ---
const setAgentStatus = (agentName, status) => {
  const name = String(agentName || '').toLowerCase()
  if (agents[name] !== undefined) {
    agents[name] = status
    
    // 自动控制连线的流向动画
    if (name === 'reader' && status === 'done') lineStatus.readerToReviewer = true
    if (name === 'reviewer' && status === 'active') lineStatus.readerToReviewer = false
    if (name === 'reviewer' && status === 'done') lineStatus.reviewerToCritic = true
    if (name === 'dispatcher' && status === 'active') lineStatus.reviewerToCritic = false
  }
}

const reset = () => {
  agents.reader = 'waiting'
  agents.reviewer = 'waiting'
  agents.dispatcher = 'waiting'
  lineStatus.readerToReviewer = false
  lineStatus.reviewerToCritic = false
}

// 暴露给父组件
defineExpose({ setAgentStatus, reset })

// --- UI 辅助计算函数 ---
const getNodeClass = (agent) => {
  const status = agents[agent]
  if (status === 'active') return 'border-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.3)] bg-slate-800/80 transform scale-105'
  if (status === 'done') return 'border-emerald-500/50 bg-slate-900/60'
  if (status === 'error') return 'border-red-500/50 bg-red-900/20'
  return 'border-slate-700 bg-slate-900/40 opacity-70' // waiting
}

const getStatusText = (agent) => {
  const status = agents[agent]
  if (status === 'active') return 'Processing...'
  if (status === 'done') return 'Completed'
  if (status === 'error') return 'Failed'
  return 'Pending'
}

const getStatusTextColor = (agent) => {
  const status = agents[agent]
  if (status === 'active') return 'text-blue-400 font-bold animate-pulse'
  if (status === 'done') return 'text-emerald-500'
  if (status === 'error') return 'text-red-400'
  return 'text-slate-500'
}
</script>

<style scoped>
@reference "tailwindcss";

.agent-node {
  @apply flex items-center gap-4 px-5 py-3 rounded-xl border transition-all duration-500 relative;
  min-width: 180px;
}
.icon-box {
  @apply w-10 h-10 flex items-center justify-center rounded-lg text-xl border border-slate-700 shadow-inner;
}

/* 极其关键的 SVG 虚线流动动画 */
.animate-dash {
  animation: dashMove 1s linear infinite;
}
@keyframes dashMove {
  from { stroke-dashoffset: 12; }
  to { stroke-dashoffset: 0; }
}
</style>