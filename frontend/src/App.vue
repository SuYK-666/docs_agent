<template>
  <div class="min-h-screen bg-slate-900 text-slate-200 p-4 font-sans overflow-hidden bg-grid-pattern relative">
    <div class="absolute top-[-10%] left-[-5%] w-[30%] h-[30%] bg-blue-600/10 blur-[120px] rounded-full pointer-events-none"></div>
    <div class="absolute bottom-[-10%] right-[-5%] w-[30%] h-[30%] bg-purple-600/10 blur-[120px] rounded-full pointer-events-none"></div>

    <div class="relative z-10 grid grid-cols-12 grid-rows-[70px_1fr] gap-4 h-[calc(100vh-32px)]">

      <header class="col-span-12 bg-slate-800/50 backdrop-blur-md border border-slate-700/50 rounded-xl flex items-center justify-between px-6 shadow-lg">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center text-xl shadow-[0_0_15px_rgba(59,130,246,0.5)]">🗂️</div>
          <h1 class="text-xl font-bold tracking-wider bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            智能公文指挥调度中枢
          </h1>
        </div>
        
        <div class="flex gap-8 items-center">
          <div class="flex flex-col items-end">
            <span class="text-[10px] text-slate-500 uppercase tracking-widest">今日吞吐量 (Docs)</span>
            <span class="text-xl font-mono font-bold text-blue-400 drop-shadow-[0_0_8px_rgba(96,165,250,0.8)]">14,208</span>
          </div>
          <div class="h-8 w-px bg-slate-700/50"></div>
          <div class="flex flex-col items-end">
            <span class="text-[10px] text-slate-500 uppercase tracking-widest">RAG 知识库命中率</span>
            <span class="text-xl font-mono font-bold text-green-400">94.2%</span>
          </div>
          <div class="h-8 w-px bg-slate-700/50"></div>
          <div class="flex flex-col items-end">
            <span class="text-[10px] text-slate-500 uppercase tracking-widest">系统平均置信度</span>
            <span class="text-xl font-mono font-bold text-amber-400">0.98</span>
          </div>
        </div>
      </header>

      <aside class="col-span-3 flex flex-col gap-4 overflow-hidden">
        
        <section class="bg-slate-800/50 backdrop-blur-md border border-slate-700/50 rounded-xl p-4 flex-1 flex flex-col min-h-0 shadow-lg relative">
          
          <div class="flex justify-between items-center mb-3 border-b border-slate-700/50 pb-2">
            <h2 class="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
              <span class="w-1.5 h-1.5 bg-blue-500 rounded-full shadow-[0_0_5px_#3b82f6]"></span> 任务调度序列
            </h2>
            <div class="flex items-center gap-3">
              <div class="flex items-center gap-2">
                <span class="text-[10px] transition-all duration-300" 
                      :class="formState.isDesensitized ? 'text-emerald-400 font-bold drop-shadow-[0_0_5px_#10b981]' : 'text-slate-500'">
                  {{ formState.isDesensitized ? '脱敏已开启' : '全局脱敏' }}
                </span>
                <el-switch v-model="formState.isDesensitized" style="--el-switch-on-color: #10b981;" />
              </div>
              <button @click="uiState.showSettings = true" 
                      class="text-slate-400 hover:text-blue-400 transition-all bg-slate-900 px-2 py-1 rounded border border-slate-700 hover:border-blue-500 hover:shadow-[0_0_10px_rgba(59,130,246,0.3)] active:scale-95" 
                      title="底层安全配置">
                ⚙️ 配置
              </button>
            </div>
          </div>
          
          <el-tabs v-model="formState.inputTab" class="flex-1 flex flex-col overflow-hidden custom-tabs">
            <el-tab-pane label="文件上传" name="upload" class="h-full flex flex-col gap-2">
              <el-upload drag multiple :auto-upload="false" v-model:file-list="fileList" class="upload-dark shrink-0" :show-file-list="false">
                <el-icon class="el-icon--upload mt-2"><UploadFilled /></el-icon>
                <div class="el-upload__text text-[10px]">拖拽或 <em>点击上传</em></div>
              </el-upload>
              <div class="flex-1 overflow-y-auto mt-2 space-y-2 custom-scrollbar">
                <div v-for="(file, index) in fileList" :key="index" class="flex items-center justify-between bg-slate-900/80 border border-slate-700 p-2 rounded cursor-pointer hover:border-blue-500 hover:shadow-[0_0_10px_rgba(59,130,246,0.2)] transition-all" @click="openPreview(file)">
                  <div class="flex items-center gap-2 overflow-hidden">
                    <span class="text-blue-400">📄</span>
                    <span class="text-xs text-slate-300 truncate w-32">{{ file.name }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-[9px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">等待解析</span>
                    <button @click.stop="fileList.splice(index, 1)" class="text-slate-500 hover:text-red-400 transition-colors">×</button>
                  </div>
                </div>
                <div v-if="fileList.length === 0" class="flex flex-col items-center justify-center h-full text-slate-600 text-xs opacity-50">
                  <span class="text-2xl mb-1">📭</span>
                  暂无待处理任务
                </div>
              </div>
            </el-tab-pane>
            <el-tab-pane label="快捷粘贴" name="paste" class="h-full flex flex-col">
              <el-input v-model="formState.pastedText" type="textarea" :rows="8" placeholder="直接粘贴微信/钉钉里的公文正文..." class="flex-1 text-xs" />
            </el-tab-pane>
            <el-tab-pane label="全网抓取" name="crawl" class="h-full flex flex-col gap-3">
              <el-input v-model="formState.crawlUrl" placeholder="输入抓取 URL" size="small" />
              <el-input v-model="formState.crawlKeyword" placeholder="过滤关键词" size="small" />
              <div class="flex items-center justify-between bg-slate-900/50 p-2 rounded border border-slate-700">
                <span class="text-xs text-slate-400">抓取条数：</span>
                <el-input-number v-model="formState.crawlCount" :min="1" :max="20" size="small" />
              </div>
            </el-tab-pane>
          </el-tabs>

          <div class="mt-3 pt-3 border-t border-slate-700/50 shrink-0">
            <el-radio-group v-model="formState.mode" size="small" class="w-full flex">
              <el-radio-button label="仅在线预览" value="preview" class="flex-1 text-center" />
              <el-radio-button label="生成并邮件下发" value="email" class="flex-1 text-center" />
            </el-radio-group>
            
            <div v-if="formState.mode === 'email'" class="mt-2 flex items-center justify-between bg-slate-900/50 p-1.5 rounded border border-slate-700">
               <span class="text-[10px] text-slate-500 pl-1 uppercase tracking-widest">附件格式:</span>
               <el-checkbox-group v-model="formState.emailTypes" size="small" class="flex gap-2">
                 <el-checkbox value="md" class="!mr-0">MD</el-checkbox>
                 <el-checkbox value="docx" class="!mr-0">Word</el-checkbox>
                 <el-checkbox value="ics" class="!mr-0">ICS</el-checkbox>
               </el-checkbox-group>
            </div>
          </div>

          <button @click="handleStartJob" :disabled="uiState.isSubmitting" class="mt-3 shrink-0 w-full bg-gradient-to-r from-blue-600 to-blue-400 hover:from-blue-500 hover:to-blue-300 text-white font-bold py-2.5 rounded-lg shadow-[0_0_15px_rgba(59,130,246,0.5)] hover:shadow-[0_0_25px_rgba(59,130,246,0.7)] transition-all active:scale-95 text-sm tracking-widest flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
            <span v-if="!uiState.isSubmitting">🚀 启动智能解析</span>
            <span v-else class="animate-pulse">⏳ 安全通道传输中...</span>
          </button>
        </section>
      </aside>

      <main class="col-span-9 flex flex-col gap-4 overflow-hidden">
        <section class="bg-slate-800/50 backdrop-blur-md border border-slate-700/50 rounded-xl p-4 h-[42%] shrink-0 relative overflow-hidden shadow-inner">
          <h2 class="absolute top-4 left-4 text-xs font-bold text-slate-500 uppercase tracking-widest z-10">多智能体协同态势</h2>
          <div class="w-full h-full">
            <AgentTopology ref="topologyRef" />
          </div>
        </section>

        <section class="bg-[#0a0f18]/80 backdrop-blur-md border border-slate-700/50 rounded-xl p-4 flex-1 flex flex-col min-h-0 relative shadow-2xl">
          <h2 class="absolute top-4 left-4 text-xs font-bold text-slate-500 uppercase tracking-widest z-10">逻辑流监控终端</h2>
          <div class="mt-8 flex-1 overflow-hidden">
            <ThinkingConsole ref="consoleRef" :is-desensitized="formState.isDesensitized" />
          </div>
        </section>
      </main>

    </div>

  <el-dialog v-model="uiState.showApproval" title="🛡️ 人工校核与下发确认" width="70%" :close-on-click-modal="false" :show-close="false" align-center class="dark-dialog">
        <div class="text-sm text-slate-400 mb-4">智能体已完成初步解析，请核对任务责任人与截止日期。确认无误后系统将执行最终派发。</div>

        <div v-for="(draft, dIdx) in jobState.drafts" :key="dIdx" class="mb-4 border border-slate-700 rounded-lg overflow-hidden">
          <div class="bg-slate-800 px-4 py-2 font-bold text-slate-300 border-b border-slate-700">📄 {{ draft.title || draft.doc_id }}</div>
          <el-table :data="draft.tasks" style="width: 100%" stripe class="custom-dark-table">
            <el-table-column prop="task_id" label="任务ID" width="100" />
            <el-table-column prop="task_name" label="任务名称" />
            <el-table-column label="责任人 (可修改)" width="180">
              <template #default="scope">
                <el-input v-model="scope.row.owner" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="截止日期 (可修改)" width="200">
              <template #default="scope">
                <el-input v-model="scope.row.deadline_display" size="small" />
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="formState.mode === 'email'" class="mt-4 p-4 bg-slate-900 border border-slate-700 rounded-lg">
          <div class="font-bold text-slate-300 mb-2">下发目标邮箱</div>
          <div v-for="(email, idx) in jobState.recipientEmails" :key="idx" class="flex gap-2 mb-2">
            <el-input v-model="jobState.recipientEmails[idx]" placeholder="输入邮箱地址" size="small" class="flex-1" />
            <el-button v-if="idx === jobState.recipientEmails.length - 1" @click="jobState.recipientEmails.push('')" size="small" type="success" plain>+</el-button>
            <el-button v-if="jobState.recipientEmails.length > 1" @click="jobState.recipientEmails.splice(idx, 1)" size="small" type="danger" plain>-</el-button>
          </div>
        </div>

        <template #footer>
          <el-button @click="submitApproval" type="primary" :loading="uiState.isApproving" class="w-full">
            ✅ 确认无误，{{ formState.mode === 'email' ? '执行下发' : '完成解析' }}
          </el-button>
        </template>
  </el-dialog>  

  <el-dialog v-model="uiState.showResult" title="🎉 任务执行完毕" width="50%" align-center class="dark-dialog">
        <el-alert v-if="jobState.emailResult?.status === 'sent'" title="邮件已成功发送！" type="success" show-icon class="mb-4" />
        
        <div v-for="(report, rIdx) in jobState.reports" :key="rIdx" class="mb-4 p-4 border border-slate-700 rounded-lg bg-slate-800/50">
          <div class="font-bold text-slate-200 mb-3">{{ report.title || report.doc_id }}</div>
          <div class="flex gap-2 flex-wrap">
            <el-button v-if="report.html_url" @click="window.open(report.html_url)" type="primary" plain size="small">🌐 在线预览</el-button>
            <el-button v-if="report.md_url" @click="window.open(report.md_url)" type="info" plain size="small">📝 Markdown</el-button>
            <el-button v-if="report.docx_url" @click="window.open(report.docx_url)" type="info" plain size="small">📄 Word</el-button>
            <el-button v-if="report.ics_url" @click="window.open(report.ics_url)" type="warning" plain size="small">📅 ICS 日历</el-button>
          </div>
        </div>

        <template #footer>
          <el-button @click="uiState.showResult = false">关闭窗口</el-button>
        </template>
  </el-dialog>
  <el-drawer v-model="uiState.showPreview" direction="rtl" size="45%" class="dark-drawer">
        <template #header>
           <div class="flex items-center gap-2">
             <span class="text-blue-400 text-lg">🔍</span>
             <div class="flex flex-col">
               <span class="text-sm font-bold text-slate-200">{{ uiState.currentPreviewFile?.name }}</span>
               <span class="text-[10px] text-slate-500 uppercase font-mono">Document Intelligence Preview</span>
             </div>
           </div>
        </template>

        <el-tabs v-model="uiState.activePreviewTab" class="preview-tabs h-full flex flex-col">
          <el-tab-pane label="📄 源文件阅览" name="source" class="h-full">
            <div class="h-[calc(100vh-180px)] bg-slate-950 p-2 rounded-lg border border-slate-800 overflow-hidden flex flex-col relative">
              
              <div v-if="uiState.previewLoading" class="absolute inset-0 flex flex-col items-center justify-center bg-slate-950/80 z-10 text-slate-400">
                <div class="animate-spin mb-2 text-2xl">⏳</div>
                <div class="text-xs tracking-widest">读取本地缓冲区...</div>
              </div>

              <div v-if="uiState.previewType === 'text'" class="h-full w-full overflow-y-auto p-4 font-mono text-xs leading-relaxed text-slate-300 whitespace-pre-wrap custom-scrollbar">
                {{ uiState.realSourceText }}
              </div>

              <div v-else-if="uiState.previewType === 'image'" class="h-full w-full flex items-center justify-center overflow-auto p-2">
                <img :src="uiState.previewUrl" class="max-w-full max-h-full object-contain rounded drop-shadow-[0_0_15px_rgba(255,255,255,0.1)]" />
              </div>

              <div v-else-if="uiState.previewType === 'pdf'" class="h-full w-full rounded overflow-hidden bg-white">
                <iframe :src="uiState.previewUrl" class="w-full h-full border-none"></iframe>
              </div>

              <div v-else class="h-full w-full flex flex-col items-center justify-center text-center opacity-60 p-8">
                <span class="text-5xl mb-4">🗃️</span>
                <h3 class="text-sm font-bold text-slate-300 mb-2">二进制文档 (DOCX)</h3>
                <p class="text-[10px] text-slate-500 leading-relaxed">
                  当前格式不支持前端纯文本直读。<br>
                  系统已挂载 OCR 与 VLM 视觉模型解析器。<br>
                  请点击主控制台 <b>“启动智能解析”</b> 后，在右侧 <b>“AI 解析结果”</b> 栏查看结构化提取产物。
                </p>
              </div>

            </div>
          </el-tab-pane>

          <el-tab-pane label="🧠 AI 解析结果" name="analysis" class="h-full">
            <div class="h-[calc(100vh-180px)] overflow-y-auto space-y-4 pr-2 custom-scrollbar">
              <div v-if="getMatchedAnalysis()" class="space-y-4">
                <div v-for="(task, idx) in getMatchedAnalysis().tasks" :key="idx" class="bg-slate-900 border border-slate-800 rounded-lg p-4 shadow-lg border-l-4 border-l-blue-500">
                  <div class="flex justify-between items-start mb-3">
                    <span class="text-xs font-bold text-blue-400 uppercase tracking-tighter">TASK #{{ task.task_id }}</span>
                    <el-tag size="small" type="info" effect="dark">{{ task.deadline_display }}</el-tag>
                  </div>
                  <h4 class="text-sm font-bold text-slate-200 mb-2">{{ task.task_name }}</h4>
                  <p class="text-[11px] text-slate-400 leading-normal">{{ task.content || '未提取到详细描述' }}</p>
                  <div class="mt-3 pt-3 border-t border-slate-800 flex justify-between items-center text-[10px]">
                    <span class="text-slate-500">负责人: <span class="text-slate-300">{{ task.owner }}</span></span>
                    <span class="text-slate-500">状态: <span class="text-emerald-500">Ready</span></span>
                  </div>
                </div>
              </div>
              <div v-else class="flex flex-col items-center justify-center h-full opacity-30 text-center">
                <span class="text-4xl mb-4">🤖</span>
                <p class="text-xs">等待智能体完成推理后<br>此处将实时生成结构化要素</p>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
  </el-drawer>
  <footer class="absolute bottom-0 left-0 w-full h-8 bg-slate-950/80 backdrop-blur border-t border-slate-800/80 flex items-center justify-between px-4 z-50 font-mono text-[10px] text-slate-500">
      <div class="flex items-center gap-6">
        <span class="flex items-center gap-2 hover:text-slate-300 transition-colors cursor-default" title="证书有效期至: 2027-12-31">
          🔒 WSS Secure Connected (TLS 1.3)
        </span>
        <span class="flex items-center gap-2">
          <div class="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse shadow-[0_0_5px_#22c55e]"></div> 
          🛡️ JWT Token Active
        </span>
      </div>
      <div class="flex items-center gap-4">
        <span>Node: edge-bj-01</span>
        <span>|</span>
        <span class="text-blue-400/70">Engine: {{ formState.provider.toUpperCase() }}</span>
      </div>
    </footer>
  </div>

  <el-dialog v-model="uiState.showSettings" title="⚙️ 系统底层安全配置" width="380px" align-center class="dark-dialog">
        <div class="space-y-4">
          <div>
            <span class="text-[10px] text-slate-500 mb-1 block uppercase tracking-widest">Model Engine / 模型引擎</span>
            <el-select v-model="formState.provider" class="w-full" size="small">
              <el-option label="DeepSeek (V3)" value="deepseek" />
              <el-option label="阿里云通义 (Qwen-Max)" value="tongyi" />
              <el-option label="百度文心 (Ernie-4.0)" value="wenxin" />
              <el-option label="豆包AI (Pro-32k)" value="doubao" />
              <el-option label="Kimi (Moonshot-8k)" value="kimi" />
              <el-option label="智谱AI (GLM-4-Flash)" value="zhipu" />
            </el-select>
          </div>
          <div>
            <span class="text-[10px] text-slate-500 mb-1 block uppercase tracking-widest">Security Token / 安全令牌</span>
            <el-input v-model="formState.apiKey" type="password" show-password placeholder="输入调用秘钥" size="small" />
            <div class="text-[9px] text-slate-500 mt-1">系统会自动对密钥进行本地加密存储，不在网络留痕。</div>
          </div>
        </div>
        <template #footer>
          <el-button @click="uiState.showSettings = false" type="primary" class="w-full bg-blue-600 hover:bg-blue-500 border-none">
            保存安全配置
          </el-button>
        </template>
    </el-dialog>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentTopology from './components/AgentTopology.vue'
import ThinkingConsole from './components/ThinkingConsole.vue'

// --- 状态管理 ---
const formState = reactive({
  isDesensitized: false,
  provider: localStorage.getItem('docs_agent_ui_provider') || 'tongyi',
  apiKey: localStorage.getItem('docs_agent_ui_api_key') || '',
  mode: 'preview',
  emailTypes: ['md', 'docx', 'ics'],
  inputTab: 'upload',
  pastedText: '',
  crawlUrl: '',
  crawlKeyword: '',
  crawlCount: 5
})

// 1. 更新 uiState，增加用于图片和 PDF 的字段
const uiState = reactive({
  isSubmitting: false,
  isApproving: false,
  showApproval: false,
  showResult: false,
  showPreview: false,
  showSettings: false,
  currentPreviewFile: null,
  activePreviewTab: 'source', 
  realSourceText: '',          
  previewLoading: false,
  previewType: 'text', // 新增：区分预览类型 (text, image, pdf, unsupported)
  previewUrl: ''       // 新增：用于存放图片和 PDF 的本地临时链接
})

// 2. 彻底升级的 openPreview 方法
const openPreview = (file) => {
  uiState.currentPreviewFile = file
  uiState.showPreview = true
  uiState.realSourceText = ''
  uiState.previewUrl = ''
  uiState.previewLoading = false
  uiState.activePreviewTab = 'source'
  
  if (!file.raw) return

  const fileName = file.name.toLowerCase()
  const fileType = file.raw.type

  // 分支 1: 图片预览
  if (fileType.startsWith('image/')) {
    uiState.previewType = 'image'
    uiState.previewUrl = URL.createObjectURL(file.raw) // 创建浏览器本地的高速缓存链接
  } 
  // 分支 2: PDF 预览
  else if (fileType === 'application/pdf' || fileName.endsWith('.pdf')) {
    uiState.previewType = 'pdf'
    uiState.previewUrl = URL.createObjectURL(file.raw)
  } 
  // 分支 3: 纯文本预览
  else if (fileType.includes('text') || fileName.endsWith('.md') || fileName.endsWith('.txt')) {
    uiState.previewType = 'text'
    uiState.previewLoading = true
    const reader = new FileReader()
    reader.onload = (e) => {
      uiState.realSourceText = e.target.result
      uiState.previewLoading = false
    }
    reader.readAsText(file.raw)
  } 
  // 分支 4: 无法原生预览的文件 (如 .docx)
  else {
    uiState.previewType = 'unsupported'
  }
}

// 【新增】根据当前预览的文件名，在 jobState.drafts 中寻找对应的解析结果
const getMatchedAnalysis = () => {
  if (!uiState.currentPreviewFile) return null
  // 匹配逻辑：找 doc_id 包含文件名的草稿
  return jobState.drafts.find(d => 
    uiState.currentPreviewFile.name.includes(d.doc_id) || d.title === uiState.currentPreviewFile.name
  )
}

const jobState = reactive({
  currentJobId: '',
  statusEventSource: null,
  drafts: [],
  reports: [],
  recipientEmails: [''],
  emailResult: null
})

const fileList = ref([]) 
const topologyRef = ref(null)
const consoleRef = ref(null)

// 暴露 window 对象给 template 使用 (用于 window.open)
const window = globalThis.window

// --- 核心方法：构建请求数据 ---
const buildFormData = () => {
  const fd = new FormData()
  fd.append("llm_provider", formState.provider)
  fd.append("api_key", formState.apiKey)
  fd.append("mode", formState.mode)
  fd.append("input_tab", formState.inputTab)
  fd.append("email_file_types", formState.emailTypes.join(","))
  
  // 报告布局使用默认值
  fd.append("report_layout_md", "separate")
  fd.append("report_layout_html", "separate")
  fd.append("report_layout_docx", "bundle")

  if (formState.inputTab === "crawl") {
    fd.append("crawl_url", formState.crawlUrl)
    fd.append("crawl_count", String(formState.crawlCount))
    if (formState.crawlKeyword) fd.append("crawl_keyword", formState.crawlKeyword)
  } else if (formState.inputTab === "paste") {
    fd.append("pasted_text", formState.pastedText)
  } else {
    fileList.value.forEach(f => fd.append("files", f.raw))
  }
  return fd
}

// --- 核心方法：发起解析请求 ---
const handleStartJob = async () => {
  if (!formState.apiKey) return ElMessage.warning("请先填写 API Key")
  
  // 保存设置到本地
  localStorage.setItem('docs_agent_ui_provider', formState.provider)
  localStorage.setItem('docs_agent_ui_api_key', formState.apiKey)

  uiState.isSubmitting = true
  if (consoleRef.value) {
    consoleRef.value.clearLogs()
    consoleRef.value.setStatus(true, 'UPLOADING')
    consoleRef.value.appendLog('System', '开始上传并初始化任务...')
  }

  try {
    const response = await fetch("/api/jobs", { method: "POST", body: buildFormData() })
    const data = await response.json()

    if (!response.ok) throw new Error(data.error || "任务提交失败")
    
    jobState.currentJobId = data.job_id
    if (consoleRef.value) consoleRef.value.appendLog('System', `任务创建成功，JobID: ${data.job_id}，正在连接安全通道...`, 'success')
    
    // 启动 SSE 监听
    startStatusTracking(data.job_id)
    
    // 启动前台拓扑演示动画 (由于目前 Python 后端没有发送精确的 stage 变色事件，我们用演示动画配合真实日志)
    if (topologyRef.value) topologyRef.value.playDemo()

  } catch (error) {
    ElMessage.error(error.message)
    if (consoleRef.value) consoleRef.value.appendLog('System', `上传失败: ${error.message}`, 'error')
  } finally {
    uiState.isSubmitting = false
  }
}

// --- 核心方法：监听 SSE 状态流 ---
const startStatusTracking = (jobId) => {
  if (jobState.statusEventSource) jobState.statusEventSource.close()

  jobState.statusEventSource = new EventSource(`/api/jobs/${jobId}/events?from_seq=0`)

  jobState.statusEventSource.addEventListener("stream", (event) => {
    try {
      const streamData = JSON.parse(event.data)
      // 将后端的日志推送到我们的暗黑终端里
      if (consoleRef.value && streamData.event === 'token' && streamData.content) {
         consoleRef.value.appendLog(streamData.agent || 'System', streamData.content)
      } else if (consoleRef.value && streamData.event === 'error') {
         consoleRef.value.appendLog(streamData.agent || 'System', streamData.content, 'error')
      }
    } catch (e) {}
  })

  jobState.statusEventSource.addEventListener("job", (event) => {
    try {
      const jobData = JSON.parse(event.data)
      
      // 1. 等待审批状态 (核心：弹出审批框)
      if (jobData.status === 'pending_approval') {
        jobState.statusEventSource.close()
        if (consoleRef.value) {
          consoleRef.value.appendLog('System', '草稿生成完毕，等待人工校核...', 'success')
          consoleRef.value.setStatus(false, 'PENDING_APPROVAL')
        }
        jobState.drafts = JSON.parse(JSON.stringify(jobData.drafts || []))
        if (jobData.recipient_emails && jobData.recipient_emails.length > 0) {
          jobState.recipientEmails = jobData.recipient_emails
        }
        uiState.showApproval = true
      }
      
      // 2. 成功完成状态 (核心：展示结果)
      if (jobData.status === 'success') {
        jobState.statusEventSource.close()
        if (consoleRef.value) {
          consoleRef.value.appendLog('System', '任务全部执行完毕！', 'success')
          consoleRef.value.setStatus(false, 'SUCCESS')
        }
        jobState.reports = jobData.reports || []
        jobState.emailResult = jobData.email_result
        uiState.showResult = true
      }

      // 3. 失败状态
      if (jobData.status === 'failed') {
        jobState.statusEventSource.close()
        ElMessage.error(jobData.error || "执行异常")
        if (consoleRef.value) {
          consoleRef.value.appendLog('System', `异常终止: ${jobData.error}`, 'error')
          consoleRef.value.setStatus(false, 'FAILED')
        }
      }
    } catch (e) {}
  })
}

// --- 核心方法：提交审批结果 ---
const submitApproval = async () => {
  // 校验邮箱
  const validEmails = jobState.recipientEmails.map(e => e.trim()).filter(e => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e))
  if (formState.mode === 'email' && validEmails.length === 0) {
    return ElMessage.warning("请至少填写一个有效的下发邮箱")
  }

  uiState.isApproving = true
  try {
    const payload = {
      job_id: jobState.currentJobId,
      recipient_emails: validEmails,
      drafts: jobState.drafts.map(d => ({ draft_token: d.draft_token, draft_json: d.draft_json }))
    }

    const response = await fetch("/approve_task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })

    if (!response.ok) throw new Error("审批提交失败")
    
    uiState.showApproval = false
    ElMessage.success("已确认下发，系统继续处理中...")
    
    if (consoleRef.value) {
      consoleRef.value.setStatus(true, 'DISPATCHING')
      consoleRef.value.appendLog('System', '人工审批完成，正在生成最终产物与投递邮件...')
    }
    
    // 重新连接 SSE 监听后续阶段
    startStatusTracking(jobState.currentJobId)

  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    uiState.isApproving = false
  }
}
</script>

<style>
/* 抽屉暗黑模式适配 */
.dark-drawer { background-color: #0f172a !important; border-left: 1px solid #334155; }
.dark-drawer .el-drawer__header { color: #e2e8f0; border-bottom: 1px solid #334155; margin-bottom: 0; padding-bottom: 16px; }

/* 为了让 Element Plus 弹窗适配暗黑主题的补充样式 */
.dark-dialog .el-dialog {
  background-color: #0f172a;
  border: 1px solid #334155;
}
.dark-dialog .el-dialog__title {
  color: #e2e8f0;
  font-weight: bold;
}
.custom-dark-table {
  --el-table-border-color: #334155;
  --el-table-header-bg-color: #1e293b;
  --el-table-header-text-color: #94a3b8;
  --el-table-bg-color: #0f172a;
  --el-table-tr-bg-color: #0f172a;
  --el-table-row-hover-bg-color: #1e293b;
  --el-table-text-color: #cbd5e1;
}
.custom-dark-table .el-input__wrapper {
  background-color: #1e293b;
  box-shadow: 0 0 0 1px #334155 inset;
}
.custom-dark-table .el-input__inner {
  color: #e2e8f0;
}
</style>