<template>
  <div class="w-full h-full relative">
    <svg class="absolute inset-0 w-full h-full pointer-events-none" style="z-index: 0;">
      <line x1="15%" y1="50%" x2="50%" y2="50%" class="stroke-slate-700" stroke-width="2" stroke-dasharray="4 4" />
      <line v-if="activeLine === 'reader-reviewer'" x1="15%" y1="50%" x2="50%" y2="50%" class="stroke-blue-500 animate-[dash_1s_linear_infinite]" stroke-width="2" stroke-dasharray="4 4" />

      <line x1="50%" y1="50%" x2="85%" y2="50%" class="stroke-slate-700" stroke-width="2" stroke-dasharray="4 4" />
      <line v-if="activeLine === 'reviewer-critic'" x1="50%" y1="50%" x2="85%" y2="50%" class="stroke-blue-500 animate-[dash_1s_linear_infinite]" stroke-width="2" stroke-dasharray="4 4" />

      <path v-if="showRejectLine" d="M 85% 40% Q 67% -10% 50% 40%" fill="none" class="stroke-red-500 animate-[dash-reverse_1s_linear_infinite]" stroke-width="2" stroke-dasharray="6 6" />
    </svg>

    <div class="absolute inset-0 w-full h-full z-10">
      
      <div :class="['node-card absolute left-[15%] top-1/2 -translate-x-1/2 -translate-y-1/2', nodes.reader.status]">
        <div class="node-icon">📄</div>
        <div class="node-info">
          <div class="node-name">Reader</div>
          <div class="node-text">{{ nodes.reader.text }}</div>
        </div>
      </div>

      <div :class="['node-card absolute left-[50%] top-1/2 -translate-x-1/2 -translate-y-1/2', nodes.reviewer.status, { 'animate-shake': isShaking }]">
        <div class="node-icon">👁️</div>
        <div class="node-info">
          <div class="node-name">Reviewer</div>
          <div class="node-text">{{ nodes.reviewer.text }}</div>
        </div>
      </div>

      <div :class="['node-card absolute left-[85%] top-1/2 -translate-x-1/2 -translate-y-1/2', nodes.critic.status]">
        <div class="node-icon">⚖️</div>
        <div class="node-info">
          <div class="node-name">Critic</div>
          <div class="node-text">{{ nodes.critic.text }}</div>
        </div>
        <div v-if="showRejectLine" class="absolute -top-10 left-1/2 -translate-x-1/2 bg-red-500/20 border border-red-500 text-red-400 text-[10px] px-2 py-1 rounded whitespace-nowrap animate-bounce shadow-[0_0_10px_rgba(239,68,68,0.3)]">
          🚨 触发重审：要素缺失
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'

// 节点状态管理字典
const nodes = reactive({
  reader: { status: 'idle', text: '等待分配' },
  reviewer: { status: 'idle', text: '等待分配' },
  critic: { status: 'idle', text: '等待分配' }
})

const activeLine = ref('')
const showRejectLine = ref(false)
const isShaking = ref(false)

// 【向外暴露的方法】用于演示极具震撼力的反思重做流程
const playDemo = async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms))
  
  // 0. 状态归位
  Object.keys(nodes).forEach(k => { nodes[k].status = 'idle'; nodes[k].text = '等待分配' })
  showRejectLine.value = false; activeLine.value = ''; isShaking.value = false

  // 1. Reader 启动
  nodes.reader.status = 'active'; nodes.reader.text = '要素抽取中...'
  await sleep(1500)
  nodes.reader.status = 'done'; nodes.reader.text = '抽取完成'
  activeLine.value = 'reader-reviewer'
  await sleep(600)

  // 2. Reviewer 启动
  activeLine.value = ''
  nodes.reviewer.status = 'active'; nodes.reviewer.text = '交叉比对中...'
  await sleep(1500)
  nodes.reviewer.status = 'done'; nodes.reviewer.text = '比对完成'
  activeLine.value = 'reviewer-critic'
  await sleep(600)

  // 3. Critic 质检 & 触发打回重做 (高潮部分)
  activeLine.value = ''
  nodes.critic.status = 'active'; nodes.critic.text = '合规性校验...'
  await sleep(1200)
  nodes.critic.status = 'error'; nodes.critic.text = '发现高危风险'
  showRejectLine.value = true // 亮起红色抛物线
  
  nodes.reviewer.status = 'error'; nodes.reviewer.text = '接收驳回指令'
  isShaking.value = true // 让 Reviewer 卡片剧烈抖动
  await sleep(500)
  isShaking.value = false
  await sleep(1500)

  // 4. Reviewer 重新修正
  showRejectLine.value = false
  nodes.critic.status = 'idle'; nodes.critic.text = '等待重新校验'
  nodes.reviewer.status = 'active'; nodes.reviewer.text = '二次修正中...'
  await sleep(1800)
  nodes.reviewer.status = 'done'; nodes.reviewer.text = '修正完成'
  activeLine.value = 'reviewer-critic'
  await sleep(600)

  // 5. Critic 最终通过
  activeLine.value = ''
  nodes.critic.status = 'active'; nodes.critic.text = '二次校验中...'
  await sleep(1500)
  nodes.critic.status = 'done'; nodes.critic.text = '安全通过'
}

// 暴露出去给 App.vue 调用
defineExpose({ playDemo })
</script>

<style scoped>
@reference "../style.css"; /* 这一行是解决 v4 报错的唯一钥匙！ */

/* 节点基础卡片 */
.node-card {
  @apply flex items-center gap-3 bg-slate-900 border-2 border-slate-700 rounded-xl p-3 transition-all duration-300 w-36 shadow-lg;
}
.node-icon {
  @apply text-2xl bg-slate-800 rounded-lg p-2;
}
.node-name {
  @apply text-sm font-bold text-slate-200 tracking-wider;
}
.node-text {
  @apply text-[10px] text-slate-500 mt-1;
}

/* 运行中状态 (发蓝光) */
.node-card.active {
  @apply border-blue-500 shadow-[0_0_20px_rgba(59,130,246,0.5)];
}
.node-card.active .node-text {
  @apply text-blue-400;
}

/* 完成状态 (发绿光) */
.node-card.done {
  @apply border-green-500;
}
.node-card.done .node-text {
  @apply text-green-400;
}

/* 报错打回状态 (发红光) */
.node-card.error {
  @apply border-red-500 shadow-[0_0_20px_rgba(239,68,68,0.5)];
}
.node-card.error .node-text {
  @apply text-red-400;
}

/* SVG 连线流光动画 */
@keyframes dash { to { stroke-dashoffset: -8; } }
@keyframes dash-reverse { to { stroke-dashoffset: 12; } }

/* 剧烈抖动动画 (评委视觉冲击) */
@keyframes shake {
  0%, 100% { transform: translate(-50%, -50%); }
  25% { transform: translate(calc(-50% - 6px), -50%); }
  75% { transform: translate(calc(-50% + 6px), -50%); }
}
.animate-shake {
  animation: shake 0.15s ease-in-out 3;
}
</style>