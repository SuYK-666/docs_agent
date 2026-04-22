<template>
  <div class="flex flex-col h-full bg-[#02060d] rounded-lg border border-slate-700/50 shadow-inner font-mono overflow-hidden">
    
    <div class="flex items-center justify-between px-4 py-2 bg-slate-800/80 border-b border-slate-700/50 shrink-0 z-20 shadow-md">
      <div class="flex items-center gap-2">
        <div class="flex gap-1.5">
          <div class="w-2.5 h-2.5 rounded-full bg-red-500/80"></div>
          <div class="w-2.5 h-2.5 rounded-full bg-yellow-500/80"></div>
          <div class="w-2.5 h-2.5 rounded-full bg-green-500/80"></div>
        </div>
        <span class="ml-3 text-[11px] text-slate-400 font-bold tracking-wider">root@docs-agent-core:~/pipeline_monitor</span>
      </div>
      <div class="flex items-center gap-2 text-[10px] tracking-widest uppercase font-bold">
        <span v-if="isSpinning" class="animate-spin text-slate-300">⚙️</span>
        <span :class="statusColor" class="transition-colors duration-300">{{ currentStatus }}</span>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar bg-[#050b14]/50">
      
      <div v-if="systemLogs.length > 0" class="flex flex-col bg-[#050b14] rounded-lg border border-slate-700/50 shadow-lg shrink-0 h-[150px] overflow-hidden">
        <div class="bg-slate-800/80 px-3 py-2 border-b border-slate-700/50 text-[10px] font-bold text-slate-400 flex items-center gap-2">
          <span>🖥️ System Kernel (全局调度)</span>
        </div>
        <div ref="systemScrollRef" class="flex-1 overflow-y-auto p-2 text-[11px] custom-scrollbar leading-relaxed">
          <div v-for="log in systemLogs" :key="log.id" class="mb-1 flex items-start hover:bg-slate-800/30 px-1 py-0.5 rounded transition-colors">
            <span class="text-slate-600 shrink-0 w-16 tabular-nums">[{{ log.time }}]</span>
            <span class="shrink-0 w-24 font-bold text-slate-400">[{{ log.agent.toUpperCase() }}]</span>
            <span class="flex-1 whitespace-pre-wrap break-all" :class="getLogColor(log.type)">{{ formatText(log.content) }}</span>
          </div>
        </div>
      </div>

      <div v-for="(stages, fileName) in fileLogs" :key="fileName" 
           class="flex flex-col bg-[#050b14] rounded-lg border border-slate-700/50 shadow-lg shrink-0 overflow-hidden" 
           style="height: 460px; max-height: 90%;"> <div class="bg-blue-900/20 px-4 py-2 border-b border-blue-900/40 text-[11px] font-bold text-blue-400 flex items-center justify-between shrink-0">
          <div class="flex items-center gap-2">
            <span>📄 {{ fileName }}</span>
            <span v-if="isFileTyping(fileName)" class="w-1.5 h-1.5 rounded-full bg-blue-400 animate-ping"></span>
          </div>
          <span class="text-slate-500 text-[9px] font-normal tracking-widest">PIPELINE VIEW (Shift+Scroll 横向滑动)</span>
        </div>

        <div class="flex-1 overflow-x-auto flex custom-scrollbar-horizontal bg-[#02060d]">
          
          <div class="flex flex-col shrink-0 w-[525px] border-r border-slate-800/50">
            <div class="shrink-0 text-center py-1 bg-slate-900/50 border-b border-slate-800 text-[10px] font-bold text-slate-500 tracking-widest sticky top-0">STAGE 1: READER</div>
            <div :ref="el => setStageScrollRef(fileName, 'reader', el)" class="flex-1 overflow-y-auto p-2 text-[10px] custom-scrollbar">
              <div v-for="log in stages.reader" :key="log.id" class="mb-1.5 flex items-start hover:bg-slate-800/30 px-1 py-0.5 rounded">
                <span class="text-slate-600 shrink-0 w-14 tabular-nums">[{{ log.time }}]</span>
                <span class="flex-1 whitespace-pre-wrap break-all" :class="getAgentColor('reader')">
                  {{ formatText(log.content) }}
                  <span v-if="log.isTyping" class="inline-block w-1.5 h-2.5 ml-0.5 bg-blue-400 animate-pulse align-middle"></span>
                </span>
              </div>
            </div>
          </div>

          <div class="flex flex-col shrink-0 w-[525px] border-r border-slate-800/50 bg-slate-900/10">
            <div class="shrink-0 text-center py-1 bg-slate-900/50 border-b border-slate-800 text-[10px] font-bold text-slate-500 tracking-widest sticky top-0">STAGE 2: REVIEWER & CRITIC</div>
            <div :ref="el => setStageScrollRef(fileName, 'reviewer', el)" class="flex-1 overflow-y-auto p-2 text-[10px] custom-scrollbar">
              <div v-for="log in stages.reviewer" :key="log.id" class="mb-1.5 flex items-start hover:bg-slate-800/30 px-1 py-0.5 rounded">
                <span class="text-slate-600 shrink-0 w-14 tabular-nums">[{{ log.time }}]</span>
                <span class="shrink-0 font-bold mr-1" :class="getAgentColor(log.agent)">[{{ log.agent.slice(0,3).toUpperCase() }}]</span>
                <span class="flex-1 whitespace-pre-wrap break-all" :class="getLogColor(log.type)">
                  {{ formatText(log.content) }}
                  <span v-if="log.isTyping" class="inline-block w-1.5 h-2.5 ml-0.5 bg-purple-400 animate-pulse align-middle"></span>
                </span>
              </div>
            </div>
          </div>

          <div class="flex flex-col shrink-0 w-[525px] bg-slate-900/20">
            <div class="shrink-0 text-center py-1 bg-slate-900/50 border-b border-slate-800 text-[10px] font-bold text-slate-500 tracking-widest sticky top-0">STAGE 3: DISPATCHER</div>
            <div :ref="el => setStageScrollRef(fileName, 'dispatcher', el)" class="flex-1 overflow-y-auto p-2 text-[10px] custom-scrollbar">
              <div v-for="log in stages.dispatcher" :key="log.id" class="mb-1.5 flex items-start hover:bg-slate-800/30 px-1 py-0.5 rounded">
                <span class="text-slate-600 shrink-0 w-14 tabular-nums">[{{ log.time }}]</span>
                <span class="flex-1 whitespace-pre-wrap break-all" :class="getAgentColor('dispatcher')">
                  {{ formatText(log.content) }}
                  <span v-if="log.isTyping" class="inline-block w-1.5 h-2.5 ml-0.5 bg-emerald-400 animate-pulse align-middle"></span>
                </span>
              </div>
            </div>
          </div>

        </div>
      </div>

      <div v-if="systemLogs.length === 0 && Object.keys(fileLogs).length === 0" class="text-slate-600/70 italic flex items-center justify-center h-full gap-2 select-none">
        <span class="inline-block w-1.5 h-4 bg-slate-600 animate-pulse"></span>
        Waiting for internal server streams to initialize...
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({ isDesensitized: { type: Boolean, default: false } })

const systemLogs = ref([])
// 核心数据结构升级：按 文件名 -> 阶段数组 进行强行分轨归类
const fileLogs = ref({}) 
const currentStatus = ref('IDLE')
const isSpinning = ref(false)
const statusColor = ref('text-slate-500')
let logIdCounter = 0

// 滚动条追踪引用
const systemScrollRef = ref(null)
const stageScrollRefs = ref({})

const setStageScrollRef = (fileName, stage, el) => {
  if (el) stageScrollRefs.value[`${fileName}_${stage}`] = el
}

const getAgentColor = (agent) => {
  const a = String(agent).toLowerCase()
  if (a === 'reader') return 'text-blue-400'
  if (a === 'reviewer') return 'text-purple-400'
  if (a === 'critic') return 'text-amber-400'
  if (a === 'dispatcher') return 'text-emerald-400'
  return 'text-slate-400' 
}

const getLogColor = (type) => {
  if (type === 'error') return 'text-red-400 bg-red-900/20 px-1 rounded'
  if (type === 'success') return 'text-green-400 font-bold'
  if (type === 'warning') return 'text-yellow-400'
  return 'text-slate-300'
}

const setStatus = (spinning, text) => {
  isSpinning.value = spinning
  currentStatus.value = text || 'IDLE'
  if (text === 'SUCCESS') statusColor.value = 'text-green-400 drop-shadow-[0_0_5px_rgba(74,222,128,0.8)]'
  else if (text === 'FAILED') statusColor.value = 'text-red-400 drop-shadow-[0_0_5px_rgba(248,113,113,0.8)]'
  else if (text === 'APPROVAL_REQUIRED' || text === 'PENDING_APPROVAL') statusColor.value = 'text-amber-400 drop-shadow-[0_0_5px_rgba(251,191,36,0.8)] animate-pulse'
  else if (spinning) statusColor.value = 'text-blue-400 drop-shadow-[0_0_5px_rgba(96,165,250,0.8)]'
  else statusColor.value = 'text-slate-500'
}

const clearLogs = () => {
  systemLogs.value = []
  fileLogs.value = {}
}

const formatText = (text) => {
  if (!props.isDesensitized || !text) return text;
  let safeText = String(text);
  safeText = safeText.replace(/(\d{3})\d{4}(\d{4})/g, '$1****$2');
  safeText = safeText.replace(/(\d{6})\d{8}(\d{4}|\d{3}[X|x])/g, '$1********$2');
  safeText = safeText.replace(/(^.)(.*)(?=@)/g, (match, p1, p2) => p1 + '*'.repeat(p2.length));
  return safeText;
}

const isFileTyping = (fileName) => {
  const stages = fileLogs.value[fileName]
  if (!stages) return false
  return (stages.reader.length && stages.reader[stages.reader.length-1].isTyping) ||
         (stages.reviewer.length && stages.reviewer[stages.reviewer.length-1].isTyping) ||
         (stages.dispatcher.length && stages.dispatcher[stages.dispatcher.length-1].isTyping)
}

// 供全局调用的系统日志写入
const appendLog = (agent, content, type = 'info') => {
  appendFileLog('Global', agent, content, type)
}

// 核心分流逻辑：根据 Agent 名字强行放入对应的列中
const appendFileLog = (fileName, agent, content, type = 'info') => {
  if (!content) return;
  const now = new Date()
  const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0') + ':' + now.getSeconds().toString().padStart(2, '0')
  
  const isSystem = !fileName || fileName === 'Global' || agent === 'System';
  
  if (isSystem) {
    _pushToLogArray(systemLogs.value, agent, content, type, timeStr)
    scrollToBottom('system')
    return
  }

  // 初始化该文件的 Pipeline 数据结构
  if (!fileLogs.value[fileName]) {
    fileLogs.value[fileName] = { reader: [], reviewer: [], dispatcher: [] }
  }

  // 映射字典：判断当前 Agent 属于哪个阶段的列
  let targetStage = 'reader'
  const a = String(agent).toLowerCase()
  if (a.includes('review') || a.includes('critic')) targetStage = 'reviewer'
  if (a.includes('dispatch') || a.includes('email')) targetStage = 'dispatcher'

  const targetArray = fileLogs.value[fileName][targetStage]
  _pushToLogArray(targetArray, agent, content, type, timeStr)
  
  scrollToBottom(`${fileName}_${targetStage}`)
}

// 内部数组推入逻辑 (支持防刷屏打字机)
const _pushToLogArray = (targetArray, agent, content, type, timeStr) => {
  const lastLog = targetArray.length > 0 ? targetArray[targetArray.length - 1] : null
  if (lastLog && lastLog.agent === agent && lastLog.type === type && type === 'info') {
     lastLog.content += content
     lastLog.isTyping = true
     clearTimeout(lastLog.typingTimer)
     lastLog.typingTimer = setTimeout(() => { lastLog.isTyping = false }, 300)
  } else {
     const newLog = { id: logIdCounter++, time: timeStr, agent, content, type, isTyping: type === 'info' }
     if (newLog.isTyping) newLog.typingTimer = setTimeout(() => { newLog.isTyping = false }, 300)
     targetArray.push(newLog)
  }
}

const scrollToBottom = async (refKey) => {
  await nextTick()
  const el = refKey === 'system' ? systemScrollRef.value : stageScrollRefs.value[refKey]
  if (el) {
    const { scrollTop, scrollHeight, clientHeight } = el
    if (scrollHeight - scrollTop - clientHeight < 150 || scrollTop === 0) {
      el.scrollTop = scrollHeight
    }
  }
}

defineExpose({ appendLog, appendFileLog, clearLogs, setStatus })
</script>

<style scoped>
/* 专属的横向滚动条美化 */
.custom-scrollbar-horizontal::-webkit-scrollbar {
  height: 6px;
}
.custom-scrollbar-horizontal::-webkit-scrollbar-track {
  background: rgba(15, 23, 42, 0.5); 
  border-radius: 4px;
}
.custom-scrollbar-horizontal::-webkit-scrollbar-thumb {
  background: rgba(51, 65, 85, 0.8); 
  border-radius: 4px;
}
.custom-scrollbar-horizontal::-webkit-scrollbar-thumb:hover {
  background: rgba(59, 130, 246, 0.8); 
}
</style>