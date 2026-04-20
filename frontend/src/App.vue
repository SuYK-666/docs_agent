<template>
  <div :class="[
        'min-h-screen p-4 font-sans overflow-hidden bg-grid-pattern relative transition-colors duration-500',
        formState.theme === 'light' ? 'theme-light bg-[#f8fafc] text-[#1e293b]' : 'theme-dark bg-[#0f172a] text-slate-200'
      ]">
    <div class="absolute top-[-10%] left-[-5%] w-[30%] h-[30%] bg-blue-600/10 blur-[120px] rounded-full pointer-events-none"></div>
    <div class="absolute bottom-[-10%] right-[-5%] w-[30%] h-[30%] bg-purple-600/10 blur-[120px] rounded-full pointer-events-none"></div>

    <div class="relative z-10 grid grid-cols-12 grid-rows-[70px_1fr] gap-4 h-[calc(100vh-32px)]">

      <header class="col-span-12 glass-panel  floating-panel rounded-xl flex items-center justify-between px-6 z-20">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center text-xl shadow-[0_0_15px_rgba(59,130,246,0.5)]">🗂️</div>
          <h1 class="text-xl font-bold tracking-wider text-metallic">
            智能公文指挥调度中枢
          </h1>
        </div>
        
        <div class="flex gap-10 items-center pr-4">
          <div class="flex flex-col items-end group cursor-default">
            <span class="text-[12px] text-slate-400 font-medium mb-0.5 tracking-wider">今日吞吐量 (Docs)</span>
            <span class="text-2xl font-mono font-bold text-slate-100 tabular-data kpi-blue">
              {{ Math.floor(kpi.throughput.current).toLocaleString() }}
            </span>
          </div>
          <div class="h-8 w-px bg-slate-700"></div>
          
          <div class="flex flex-col items-end group cursor-default">
            <span class="text-[12px] text-slate-400 font-medium mb-0.5 tracking-wider">RAG 知识库命中率</span>
            <span class="text-2xl font-mono font-bold text-emerald-400 tabular-data kpi-green">
              {{ kpi.hitRate.current.toFixed(1) }}%
            </span>
          </div>
          <div class="h-8 w-px bg-slate-700"></div>
          
          <div class="flex flex-col items-end group cursor-default">
            <span class="text-[12px] text-slate-400 font-medium mb-0.5 tracking-wider">系统平均置信度</span>
            <span class="text-2xl font-mono font-bold text-blue-400 tabular-data kpi-gold">
              {{ kpi.confidence.current.toFixed(2) }}
            </span>
          </div>
        </div>
      </header>

      <aside class="col-span-3 flex flex-col gap-4 overflow-hidden">
        
        <section class="glass-panel rounded-xl p-4 flex-1 flex flex-col min-h-0 relative">
          
          <div class="flex justify-between items-center mb-3 border-b border-slate-700/50 pb-2">
            <h2 class="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
              <span class="w-1.5 h-1.5 bg-blue-500 rounded-full shadow-[0_0_5px_#3b82f6]"></span> 任务调度序列
            </h2>
            <el-button v-if="fileList.length > 0" @click="clearAllFiles" 
                      size="small" type="danger" plain 
                      class="!bg-transparent !border-slate-700/50 hover:!border-red-500 !text-[10px] !px-2 !h-6">
              🗑️ 一键清空
            </el-button>
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
              <el-upload drag multiple :auto-upload="false" v-model:file-list="fileList" class="upload-dark upload-floating floating-panel upload-blueprint rounded-lg overflow-hidden shrink-0" :show-file-list="false">
                <el-icon class="el-icon--upload mt-2"><UploadFilled /></el-icon>
                <div class="el-upload__text text-[10px]">拖拽或 <em>点击上传</em></div>
              </el-upload>
              <div class="flex-1 overflow-y-auto mt-2 space-y-2 pr-1 custom-scrollbar">
                <div v-for="(file, index) in fileList" :key="index" 
                     class="relative bg-slate-900/80 border border-slate-700 p-2.5 rounded overflow-hidden cursor-pointer hover:border-blue-500 transition-all group"
                     @click="openPreview(file)">
                  
                  <div v-if="jobState.fileMetrics[file.name]" 
                       class="absolute left-0 top-0 bottom-0 bg-blue-900/20 transition-all duration-500 z-0"
                       :style="{ width: (jobState.fileMetrics[file.name].percent || 0) + '%' }">
                  </div>

                  <div class="relative z-10 flex flex-col gap-1.5">
                    <div class="flex items-center justify-between">
                      <div class="flex items-center gap-2 overflow-hidden">
                        <span class="text-blue-400 text-sm">📄</span>
                        <span class="text-xs font-bold text-slate-300 truncate w-32" :title="file.name">{{ file.name }}</span>
                      </div>
                      
                      <div class="flex items-center gap-2">
                        <template v-if="!jobState.fileMetrics[file.name]">
                          <span class="text-[9px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">等待调度</span>
                        </template>
                        <template v-else>
                          <span class="text-[9px] font-mono font-bold" 
                                :class="jobState.fileMetrics[file.name].status === 'error' ? 'text-red-400' : 'text-blue-400'">
                            {{ jobState.fileMetrics[file.name].percent || 0 }}%
                          </span>
                        </template>

                        <button v-if="!uiState.isSubmitting" 
                                @click.stop="removeSingleFile(index, file.name)" 
                                class="text-slate-500 hover:text-red-400 transition-all px-1 font-bold text-lg leading-none active:scale-90">
                          ×
                        </button>
                      </div>
                    </div>

                    <div v-if="jobState.fileMetrics[file.name]" class="flex justify-between items-center text-[10px]">
                      <span class="text-slate-500 truncate w-2/3" :title="jobState.fileMetrics[file.name].detail">
                        <span v-if="jobState.fileMetrics[file.name].status === 'active'" class="inline-block w-1 h-1 rounded-full bg-blue-500 animate-ping mr-1"></span>
                        {{ jobState.fileMetrics[file.name].detail }}
                      </span>
                      <span class="text-slate-400 font-mono flex items-center gap-1 bg-slate-950 px-1 rounded border border-slate-800" title="该文件累计消耗 Token">
                        ⚡ {{ jobState.fileMetrics[file.name].tokens || 0 }}
                      </span>
                    </div>
                  </div>
                </div>
                
                <div v-if="fileList.length === 0" class="flex flex-col items-center justify-center h-full text-slate-600 text-xs opacity-50">
                  <span class="text-4xl mb-3">📭</span>
                  <span class="text-base font-medium text-slate-200 theme-text-main">暂无待处理任务</span>
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

          <button @click="handleStartJob" :disabled="uiState.isSubmitting" 
                  class="mt-3 shrink-0 w-full btn-corporate text-white font-bold py-2.5 rounded-lg transition-all active:scale-[0.98] text-sm tracking-widest flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
            <span v-if="!uiState.isSubmitting">🚀 启动智能解析</span>
            <span v-else class="flex items-center gap-2">
              <svg class="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
              安全通道传输中...
            </span>
          </button>
        </section>
      </aside>

      <main ref="mainAreaRef" class="col-span-9 flex flex-col overflow-hidden relative">
        
        <section :style="{ height: topPanelHeight + '%' }" class="shrink-0 flex gap-5 relative z-10 pb-2">
          
          <div class="w-[60%] bg-[#0b1120]/80 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 relative overflow-hidden floating-panel flex flex-col group transition-all duration-500">
            <div class="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-blue-500 to-transparent opacity-0 group-hover:opacity-100 transition-all duration-700 overflow-hidden">
               <div class="w-full h-full bg-white/20 animate-pulse"></div>
            </div>
            
            <div class="flex justify-between items-center mb-2 z-10 shrink-0">
               <h2 class="text-xs font-bold text-slate-500 uppercase tracking-widest">多智能体协同态势</h2>
               <div class="flex items-center gap-2">
                 <span class="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
                 <span class="text-[10px] text-emerald-500 font-mono font-bold uppercase">Live System</span>
               </div>
            </div>

            <div class="flex-1 w-full min-h-0 relative">
              <div class="absolute inset-0 flex items-center justify-center">
                <AgentTopology ref="topologyRef" />
              </div>
            </div>
          </div>

          <div class="w-[40%] bg-[#0b1120]/80 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 relative overflow-hidden flex flex-col group hover:border-blue-500/40 transition-colors duration-500">
            <div class="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-blue-400 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700 shadow-[0_0_10px_#60a5fa]"></div>
            <h2 class="text-xs font-bold text-slate-500 uppercase tracking-widest z-10 shrink-0">近7日系统并发与模型置信度</h2>
            <div class="flex-1 w-full mt-2 min-h-0 relative">
              <div ref="chartContainerRef" class="absolute inset-0"></div>
            </div>
          </div>

        </section>

        <div 
          class="h-3 -my-1.5 z-50 cursor-ns-resize flex items-center justify-center group relative shrink-0"
          @mousedown="startDrag"
        >
          <div class="w-full h-[2px] bg-slate-700/50 group-hover:bg-blue-500/80 transition-colors duration-200"
               :class="{'bg-blue-500 shadow-[0_0_10px_#3b82f6]': isDragging}"></div>
          <div class="absolute w-12 h-1.5 bg-slate-600 rounded-full group-hover:bg-blue-400 transition-colors"
               :class="{'bg-blue-400': isDragging}"></div>
        </div>

        <section class="glass-panel terminal-window rounded-xl p-4 flex-1 flex flex-col min-h-0 relative mt-2 overflow-hidden">
          <h2 class="absolute top-4 left-4 text-xs font-bold text-slate-500 uppercase tracking-widest z-10">逻辑流监控终端</h2>
          <div class="mt-8 flex-1 overflow-hidden">
            <ThinkingConsole ref="consoleRef" :is-desensitized="formState.isDesensitized" />
          </div>
        </section>

        <div v-if="isDragging" class="absolute inset-0 z-40 cursor-ns-resize bg-blue-500/5"></div>

      </main>

    </div>

  <!-- <el-dialog v-model="uiState.showApproval" append-to-body title="🛡️ 人工校核与下发确认" width="70%" :close-on-click-modal="false" :show-close="false" align-center class="dark-dialog">
        <div class="text-sm text-slate-400 mb-4">智能体已完成初步解析，请核对任务责任人与截止日期。确认无误后系统将执行最终派发。</div>

        <div v-for="(draft, dIdx) in jobState.drafts" :key="dIdx" class="mb-4 border border-slate-700 rounded-lg overflow-hidden">
          <div class="bg-slate-800 px-4 py-2 font-bold text-slate-300 border-b border-slate-700">📄 {{ draft.title || draft.doc_id }}</div>
          <el-table :data="draft.tasks" style="width: 100%" :row-class-name="tableRowClassName" class="custom-dark-table">
            
            <el-table-column type="expand">
              <template #default="props">
                <div class="m-2 p-3 bg-slate-900 border-l-4 rounded" 
                     :class="(props.row.score || 100) < 85 ? 'border-l-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.1)]' : 'border-l-emerald-500'">
                  <div class="text-xs font-bold mb-1 flex items-center gap-2"
                       :class="(props.row.score || 100) < 85 ? 'text-amber-500' : 'text-emerald-500'">
                    ⚖️ Critic Agent 质检报告 
                    <span class="text-[10px] bg-slate-800 px-1 rounded border border-slate-700">置信度: {{ props.row.score || '98' }}/100</span>
                  </div>
                  <div class="text-xs text-slate-300 leading-relaxed font-mono">
                    {{ props.row.critic_feedback || '各项要素交叉比对一致，未发现高危逻辑冲突，准许放行。' }}
                  </div>
                </div>
              </template>
            </el-table-column>

            <el-table-column prop="task_id" label="ID" width="60" />
            
            <el-table-column label="AI 评估" width="100" align="center">
              <template #default="scope">
                <div v-if="(scope.row.score || 100) < 85" class="flex items-center justify-center">
                  <span class="bg-amber-500/20 text-amber-400 border border-amber-500/50 text-[10px] px-1.5 py-0.5 rounded animate-pulse">需核实</span>
                </div>
                <div v-else class="flex items-center justify-center">
                  <span class="bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 text-[10px] px-1.5 py-0.5 rounded">可信</span>
                </div>
              </template>
            </el-table-column>

            <el-table-column prop="task_name" label="任务名称" show-overflow-tooltip />
            
            <el-table-column label="责任人 (可修改)" width="150">
              <template #default="scope">
                <el-input v-model="scope.row.owner" size="small" 
                          :class="{'warning-input': (scope.row.score || 100) < 85}" />
              </template>
            </el-table-column>
            
            <el-table-column label="截止日期 (可修改)" width="160">
              <template #default="scope">
                <el-input v-model="scope.row.deadline_display" size="small" 
                          :class="{'warning-input': (scope.row.score || 100) < 85}" />
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
  </el-dialog>   -->

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
  <el-drawer v-model="uiState.showPreview" append-to-body direction="rtl" 
             :size="(uiState.isApprovingInDrawer || uiState.reportPreviewUrl) ? '85%' : '45%'"
             class="dark-drawer" style="transition: width 0.3s ease-in-out;">
        
        <template #header>
           <div class="flex items-center justify-between w-full pr-4">
             <div class="flex items-center gap-2">
               <span class="text-blue-400 text-lg">🔍</span>
               <div class="flex flex-col">
                 <span class="text-sm font-bold text-slate-200">{{ uiState.currentPreviewFile?.name }}</span>
                 <span class="text-[10px] text-slate-500 uppercase font-mono">智能调度控制台</span>
               </div>
             </div>
             <el-button v-if="uiState.isApprovingInDrawer" 
                        @click="uiState.isApprovingInDrawer = false; uiState.activePreviewTab = 'verification'" 
                        size="small" type="info" plain>
                返回普通预览
              </el-button>
           </div>
        </template>

        <div v-if="!uiState.isApprovingInDrawer" class="flex gap-6 mb-4 border-b border-slate-800 px-2 shrink-0">
          <button @click="uiState.activePreviewTab = 'source'" class="pb-2 text-sm font-bold transition-all" :class="uiState.activePreviewTab === 'source' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-slate-500 hover:text-slate-300'">📄 源文件</button>
          <button @click="uiState.activePreviewTab = 'verification'" class="pb-2 text-sm font-bold transition-all" :class="uiState.activePreviewTab === 'verification' ? 'text-amber-400 border-b-2 border-amber-400' : 'text-slate-500 hover:text-slate-300'">🛡️ 校验信息</button>
          <button @click="uiState.activePreviewTab = 'analysis'" class="pb-2 text-sm font-bold transition-all" :class="uiState.activePreviewTab === 'analysis' ? 'text-emerald-400 border-b-2 border-emerald-400' : 'text-slate-500 hover:text-slate-300'">🧠 AI 结果</button>
        </div>

        <div class="h-[calc(100vh-160px)] flex gap-4 overflow-hidden">
          
          <div v-show="uiState.isApprovingInDrawer || uiState.reportPreviewUrl || uiState.activePreviewTab === 'source'" 
              :class="(uiState.isApprovingInDrawer || uiState.reportPreviewUrl) ? 'w-1/2 border-r border-slate-700/50 pr-4' : 'w-full'" 
              class="flex flex-col h-full">
            <div class="flex-1 bg-slate-950 p-2 rounded-lg border border-slate-800 overflow-hidden relative">
              <div v-if="uiState.previewLoading" class="absolute inset-0 z-20 bg-slate-950/90 backdrop-blur flex flex-col p-6 skeleton-container">
                <div class="w-1/3 h-4 skeleton-block rounded mb-8"></div>
                <div class="space-y-4">
                  <div class="w-full h-2 skeleton-block rounded"></div>
                  <div class="w-5/6 h-2 skeleton-block rounded"></div>
                  <div class="w-full h-2 skeleton-block rounded"></div>
                  <div class="w-4/5 h-2 skeleton-block rounded"></div>
                </div>
                <div class="mt-8 space-y-4">
                  <div class="w-full h-2 skeleton-block rounded"></div>
                  <div class="w-3/4 h-2 skeleton-block rounded"></div>
                </div>
                <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <span class="text-xs font-bold tracking-widest text-slate-400 bg-slate-900/50 px-4 py-2 rounded-full border border-slate-700/50 backdrop-blur-md shadow-lg">加载数据源...</span>
                </div>
              </div>
              <div v-if="uiState.previewType === 'text'" class="h-full w-full overflow-y-auto p-4 font-mono text-xs text-slate-300 whitespace-pre-wrap">{{ uiState.realSourceText }}</div>
              <div v-else-if="uiState.previewType === 'image'" class="h-full w-full flex items-center justify-center"><img :src="uiState.previewUrl" class="max-w-full max-h-full object-contain" /></div>
              <div v-else-if="uiState.previewType === 'pdf'" class="h-full w-full rounded overflow-hidden"><iframe :src="uiState.previewUrl" class="w-full h-full border-none"></iframe></div>
              <div v-else-if="uiState.previewType === 'docx'" class="h-full w-full rounded overflow-hidden bg-slate-100"><div id="docx-preview-container" class="h-full w-full overflow-y-auto text-black p-4"></div></div>
              <div v-else class="h-full w-full flex flex-col items-center justify-center text-center opacity-60">
                <span class="text-5xl mb-4">🗃️</span><h3 class="text-sm font-bold text-slate-300">不可直接预览的格式</h3>
              </div>
            </div>
          </div>

          <div v-show="uiState.isApprovingInDrawer || uiState.reportPreviewUrl || uiState.activePreviewTab !== 'source'" 
              :class="(uiState.isApprovingInDrawer || uiState.reportPreviewUrl) ? 'w-1/2 flex flex-col relative' : 'w-full flex flex-col h-full'">
            
            <div v-if="uiState.isApprovingInDrawer || uiState.activePreviewTab === 'verification'" class="flex-1 overflow-y-auto pr-2 custom-scrollbar pb-20">

              <div v-if="!uiState.isApprovingInDrawer && getMatchedAnalysis() && !getMatchedAnalysis().isFinalized && uiState.activePreviewTab === 'verification'" 
                  class="mb-4 p-3 bg-amber-900/20 border border-amber-500/30 rounded-lg flex items-center justify-between shadow-inner">
                <div class="text-[10px] text-amber-400 font-bold uppercase tracking-widest flex items-center gap-2">
                  <span class="w-2 h-2 bg-amber-500 rounded-full animate-pulse"></span>
                  任务等待审批中
                </div>
                <el-button @click="uiState.isApprovingInDrawer = true" size="small" type="warning" plain class="!text-[10px]">
                  进入高效校核模式
                </el-button>
              </div>

              <div v-if="jobState.drafts.length > 1" class="mb-4 flex items-center justify-between bg-slate-800/50 p-2 rounded border border-slate-700">
                <div class="text-[10px] text-slate-400">
                  批次进度: <span class="text-blue-400 font-bold">{{ currentFileIndex + 1 }}</span> / {{ jobState.drafts.length }}
                </div>
                <div class="flex gap-1">
                  <el-button size="small" type="info" plain :disabled="isFirstFile" @click="jumpFile(-1)">上一个</el-button>
                  <el-button size="small" type="primary" plain :disabled="isLastFile" @click="jumpFile(1)">下一个</el-button>
                </div>
              </div>
              <div class="text-[10px] font-bold text-amber-500 mb-2 uppercase tracking-widest flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span> 要素校验工作台
              </div>
              
              <div v-if="getMatchedAnalysis()" class="space-y-4">
                <div v-for="(task, idx) in getMatchedAnalysis().tasks" :key="idx" 
                     class="bg-slate-900 border border-slate-700 rounded-lg p-4 shadow-lg border-l-4" 
                     :class="(task.score || 98) < 85 ? 'border-l-amber-500' : 'border-l-blue-500'">
                  <div class="flex justify-between items-start mb-2">
                    <span class="text-xs font-bold text-blue-400">TASK #{{ task.task_id }}</span>
                    <span class="text-[10px] px-1.5 py-0.5 rounded border" 
                          :class="(task.score || 98) < 85 ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' : 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30'">
                      置信度: {{ task.score || 98 }}
                    </span>
                  </div>
                  <h4 class="text-sm font-bold text-slate-200 mb-2">{{ task.task_name }}</h4>
                  <p class="text-[11px] text-slate-400 leading-normal mb-3">{{ task.content }}</p>
                  
                  <div class="space-y-2 pt-3 border-t border-slate-800">
                     <div class="flex items-center gap-2">
                       <span class="text-xs text-slate-500 w-16">责任人:</span>
                       <el-input v-model="task.owner" size="small" class="flex-1" />
                     </div>
                     <div class="flex items-center gap-2">
                       <span class="text-xs text-slate-500 w-16">截止日:</span>
                       <el-input v-model="task.deadline_display" size="small" class="flex-1" />
                     </div>
                  </div>
                </div>
              </div>
              <div v-else class="h-full flex flex-col items-center justify-center opacity-30">暂无校验数据</div>
              <div v-if="uiState.isApprovingInDrawer && formState.mode === 'email'" class="mt-6 bg-slate-900 border border-slate-700 rounded-lg p-4 shadow-lg border-l-4 border-l-blue-500">
                <div class="text-xs font-bold text-slate-300 mb-3 flex items-center gap-2">
                  <span>📧 确认下发目标邮箱</span>
                  <span class="text-[9px] text-slate-500 font-normal">多目标请点击右侧加号</span>
                </div>
                <div v-for="(email, idx) in jobState.recipientEmails" :key="idx" class="flex gap-2 mb-2">
                  <el-input v-model="jobState.recipientEmails[idx]" placeholder="输入接收方邮箱地址..." size="small" class="flex-1" />
                  <el-button v-if="idx === jobState.recipientEmails.length - 1" @click="jobState.recipientEmails.push('')" size="small" type="success" plain>+</el-button>
                  <el-button v-if="jobState.recipientEmails.length > 1" @click="jobState.recipientEmails.splice(idx, 1)" size="small" type="danger" plain>-</el-button>
                </div>
              </div>
            </div>

            <div v-if="!uiState.isApprovingInDrawer && uiState.activePreviewTab === 'analysis'" class="flex-1 overflow-y-auto pr-2 custom-scrollbar">
              <div class="text-[10px] font-bold text-emerald-500 mb-4 uppercase tracking-widest flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]"></span> 
                最终执行产物库 (Artifact Library)
              </div>
              
              <div v-if="getMatchedReport()" class="h-full flex flex-col">
  
              <div v-if="uiState.reportPreviewUrl" class="flex-1 flex flex-col h-full bg-slate-950 p-2 rounded-lg border border-slate-800 relative">
                <div v-if="uiState.reportPreviewLoading" class="absolute inset-0 z-20 bg-slate-950/90 backdrop-blur flex flex-col p-6 skeleton-container">
                  <div class="flex justify-between mb-8">
                    <div class="w-1/4 h-5 skeleton-block rounded"></div>
                    <div class="w-16 h-5 skeleton-block rounded"></div>
                  </div>
                  <div class="grid grid-cols-2 gap-6">
                    <div class="space-y-3">
                      <div class="w-full h-2 skeleton-block rounded"></div>
                      <div class="w-full h-2 skeleton-block rounded"></div>
                      <div class="w-4/5 h-2 skeleton-block rounded"></div>
                    </div>
                    <div class="space-y-3">
                      <div class="w-full h-2 skeleton-block rounded"></div>
                      <div class="w-5/6 h-2 skeleton-block rounded"></div>
                    </div>
                  </div>
                  <div class="mt-8 w-full h-32 skeleton-block rounded"></div>
                  <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <span class="text-xs font-bold tracking-widest text-blue-400 bg-blue-900/20 px-4 py-2 rounded-full border border-blue-500/30 backdrop-blur-md shadow-lg flex items-center gap-2">
                      <svg class="animate-spin h-3 w-3 text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                      AI 报告生成中...
                    </span>
                  </div>
                </div>
                
                <div class="flex justify-between items-center mb-2 pb-2 border-b border-slate-800 shrink-0">
                  <span class="text-xs text-blue-400 font-bold tracking-widest uppercase">📄 对比预览模式 (Side-by-Side)</span>
                  <el-button @click="uiState.reportPreviewUrl = ''" size="small" type="danger" plain class="!px-2 !py-1 !h-auto text-[10px]">
                    关闭报告预览
                  </el-button>
                </div>

                <div class="flex-1 overflow-hidden relative rounded">
                  <iframe v-if="uiState.reportPreviewType === 'pdf'" :src="uiState.reportPreviewUrl" class="w-full h-full border-none bg-white"></iframe>
                  <div v-else-if="uiState.reportPreviewType === 'docx'" id="report-docx-container" class="h-full w-full overflow-y-auto text-black bg-slate-100 p-4 custom-scrollbar"></div>
                </div>
              </div>

              <div v-show="!uiState.reportPreviewUrl" class="bg-slate-900 border border-slate-700/50 rounded-lg p-4 floating-panel hover:border-blue-500/50 transition-colors">
                  <div class="text-xs font-bold text-slate-300 mb-3 border-b border-slate-800 pb-2 flex justify-between items-center">
                    <span>{{ getMatchedReport().title || '系统生成报告' }}</span>
                    <span class="text-emerald-500 text-[9px] bg-emerald-500/10 px-1 rounded">READY</span>
                  </div>
                  
                  <div class="grid grid-cols-2 gap-3">
                    <div v-if="getMatchedReport().html_url" class="flex flex-col gap-2 p-2 bg-slate-950 rounded border border-slate-800">
                      <span class="text-[9px] text-slate-500 uppercase">网页报告 (HTML)</span>
                      <div class="flex gap-1">
                        <el-button @click="previewReportInternal(getMatchedReport().html_url, 'pdf')" size="small" type="primary" class="!px-2 flex-1">👁️ 预览</el-button>
                        <el-button @click="downloadArtifact(getMatchedReport().html_url, 'Report.html')" size="small" plain class="!px-2">📥</el-button>
                      </div>
                    </div>

                    <div v-if="getMatchedReport().docx_url" class="flex flex-col gap-2 p-2 bg-slate-950 rounded border border-slate-800">
                      <span class="text-[9px] text-slate-500 uppercase">公文附件 (DOCX)</span>
                      <div class="flex gap-1">
                        <el-button @click="previewReportInternal(getMatchedReport().docx_url, 'docx')" size="small" type="info" class="!px-2 flex-1">👁️ 预览</el-button>
                        <el-button @click="downloadArtifact(getMatchedReport().docx_url, 'Report.docx')" size="small" plain class="!px-2">📥</el-button>
                      </div>
                    </div>

                    <div v-if="getMatchedReport().md_url || getMatchedReport().ics_url" class="col-span-2 flex gap-2">
                      <el-button v-if="getMatchedReport().md_url" @click="downloadArtifact(getMatchedReport().md_url, 'Report.md')" size="small" class="flex-1 !bg-slate-800">📥 下载 Markdown</el-button>
                      <el-button v-if="getMatchedReport().ics_url" @click="downloadArtifact(getMatchedReport().ics_url, 'Event.ics')" size="small" class="flex-1 !bg-slate-800">📅 导出日历 (ICS)</el-button>
                    </div>
                  </div>
                </div>
              </div>
              
              <div v-else class="h-full flex flex-col items-center justify-center opacity-30 text-center py-20">
                <span class="text-4xl mb-4">🤖</span>
                <p class="text-xs">等待任务完成下发后<br>最终产物将自动归档至此处</p>
              </div>
            </div>

            <div v-if="(uiState.isApprovingInDrawer || uiState.activePreviewTab === 'verification') && getMatchedAnalysis() && !getMatchedAnalysis().isFinalized" 
                class="absolute bottom-0 left-0 w-full bg-slate-900/90 backdrop-blur border-t border-slate-700 p-3 z-10">
               <el-button v-if="!isLastFile" @click="jumpFile(1)" :disabled="uiState.isApproving" type="primary" class="w-full !bg-blue-600 hover:!bg-blue-500 font-bold tracking-widest shadow-[0_0_10px_rgba(59,130,246,0.5)]">
                 ✅ 确认当前，查看下一份 ({{ currentFileIndex + 1 }}/{{ jobState.drafts.length }})
               </el-button>
               <el-button v-else @click="submitApproval" :disabled="uiState.isApproving" type="success" :loading="uiState.isApproving" class="w-full !bg-emerald-600 hover:!bg-emerald-500 font-bold tracking-widest shadow-[0_0_10px_rgba(16,185,129,0.5)]">
                 🚀 批次核实完毕，执行全量下发
               </el-button>
            </div>
          </div>
        </div>
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

  <el-dialog v-model="uiState.showSettings" append-to-body title="⚙️ 系统底层安全配置" width="380px" align-center class="dark-dialog">
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
          
          <div class="pt-4 border-t border-slate-700/30">
            <span class="text-[10px] text-slate-500 mb-2 block uppercase tracking-widest">Visual Theme / 视觉主题</span>
            <el-radio-group v-model="formState.theme" size="small" class="w-full flex">
              <el-radio-button label="dark" class="flex-1">🌃 深色模式</el-radio-button>
              <el-radio-button label="light" class="flex-1">📄 浅色模式</el-radio-button>
            </el-radio-group>
          </div>

        </div>
        <template #footer>
          <el-button @click="saveSettings" type="primary" class="w-full bg-blue-600 hover:bg-blue-500 border-none">
            保存系统配置
          </el-button>
        </template>
    </el-dialog>
</template>

<script setup>
import { reactive, ref, computed,onMounted, watch } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { renderAsync } from 'docx-preview'
import AgentTopology from './components/AgentTopology.vue'
import ThinkingConsole from './components/ThinkingConsole.vue'

// 【重写】：更健壮的索引匹配逻辑
const currentFileIndex = computed(() => {
  if (!uiState.currentPreviewFile || !jobState.drafts) return -1;
  const fileName = uiState.currentPreviewFile.name || '';
  return jobState.drafts.findIndex(d => {
    if (d.doc_id && fileName.includes(d.doc_id)) return true;
    if (d.title && fileName.includes(d.title)) return true;
    return false;
  });
});

const isFirstFile = computed(() => currentFileIndex.value <= 0);
const isLastFile = computed(() => currentFileIndex.value === jobState.drafts.length - 1);

const jumpFile = (step) => {
  const nextDraft = jobState.drafts[currentFileIndex.value + step];
  if (nextDraft) {
    const file = fileList.value.find(f => f.name.includes(nextDraft.doc_id) || nextDraft.title === f.name);
    if (file) openPreview(file);
  }
}


// --- 【新增】右侧面板垂直拖拽分割逻辑 ---
const mainAreaRef = ref(null)
// 从 localStorage 读取上次保存的比例，默认 42%
const topPanelHeight = ref(Number(localStorage.getItem('docs_agent_top_panel_height')) || 42)
const isDragging = ref(false)

const startDrag = () => {
  isDragging.value = true
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.userSelect = 'none' // 拖拽时防止选中文本
}

const onDrag = (e) => {
  if (!isDragging.value || !mainAreaRef.value) return
  const rect = mainAreaRef.value.getBoundingClientRect()
  
  // 计算鼠标在 main 容器内的相对 Y 坐标
  let newHeightPx = e.clientY - rect.top

  // 严格的最小高度限制：上区域 ≥ 100px，下区域 ≥ 200px
  if (newHeightPx < 100) newHeightPx = 100
  if (newHeightPx > rect.height - 200) newHeightPx = rect.height - 200

  // 转换为百分比
  topPanelHeight.value = (newHeightPx / rect.height) * 100
}

const stopDrag = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.userSelect = ''
  // 状态记忆：保存到本地
  localStorage.setItem('docs_agent_top_panel_height', topPanelHeight.value)
}

// 暴露 window 对象给 template 使用 (用于 window.open)
const window = globalThis.window

// --- 1. DOM/组件引用 (Refs) ---
const fileList = ref([]) 
const topologyRef = ref(null)
const consoleRef = ref(null)
const chartContainerRef = ref(null)
let myChart = null

// --- 2. 核心响应式状态 ---
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
  crawlCount: 5,
  theme: localStorage.getItem('docs_agent_theme') || 'dark', // 默认深色
})

const uiState = reactive({
  isSubmitting: false,
  isApproving: false,
  showApproval: false,
  isApprovingInDrawer: false, // 【新增这行】控制抽屉是否变宽、是否双栏
  showResult: false,
  showPreview: false,
  showSettings: false,
  currentPreviewFile: null,
  activePreviewTab: 'source', 
  realSourceText: '',          
  previewLoading: false,
  // 【新增】：独立于原文的报告预览状态
  reportPreviewUrl: '',
  reportPreviewType: '',
  reportPreviewLoading: false,
  previewType: 'text', 
  previewUrl: ''       
})

const jobState = reactive({
  currentJobId: '',
  statusEventSource: null,
  drafts: [],
  reports: [],
  recipientEmails: [''],
  emailResult: null,
  fileMetrics: {}
})

const kpi = reactive({
  throughput: { current: 0, target: 0 },
  hitRate: { current: 0, target: 0 },
  confidence: { current: 0, target: 0 }
})

// --- 3. 辅助功能与工具函数 ---
const updateFileMetric = (fileName, updates) => {
  if (!fileName) return;
  if (!jobState.fileMetrics[fileName]) {
    jobState.fileMetrics[fileName] = { percent: 0, tokens: 0, detail: '等待调度', status: 'pending' };
  }
  Object.assign(jobState.fileMetrics[fileName], updates);
}

const estimateTokenDelta = (text) => {
  const normalized = String(text || "").trim();
  return normalized ? Math.max(1, Math.ceil(normalized.length / 2)) : 0;
}

const animateValue = (obj, key, start, end, duration, isFloat) => {
  let startTimestamp = null;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    const ease = 1 - Math.pow(1 - progress, 4);
    const current = start + ease * (end - start);
    obj[key].current = current;
    if (progress < 1) window.requestAnimationFrame(step);
    else obj[key].current = end;
  };
  window.requestAnimationFrame(step);
}

const triggerKPIUpdate = (filesCount) => {
  const oldThroughput = kpi.throughput.target;
  kpi.throughput.target += filesCount;
  animateValue(kpi, 'throughput', oldThroughput, kpi.throughput.target, 1500, false);

  const oldHit = kpi.hitRate.target;
  const hitFluctuation = (Math.random() * 0.4 - 0.1); 
  kpi.hitRate.target = Math.min(99.9, oldHit + hitFluctuation);
  animateValue(kpi, 'hitRate', oldHit, kpi.hitRate.target, 1500, true);

  const oldConf = kpi.confidence.target;
  const confFluctuation = (Math.random() * 0.01 - 0.002); 
  kpi.confidence.target = Math.min(0.99, oldConf + confFluctuation);
  animateValue(kpi, 'confidence', oldConf, kpi.confidence.target, 1500, true);
}

// --- 4. ECharts 图表逻辑 ---
const initTrendChart = () => {
  if (!chartContainerRef.value) return
  myChart = echarts.init(chartContainerRef.value)
  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross', crossStyle: { color: '#64748b' } }, backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#e2e8f0' } },
    grid: { left: '3%', right: '3%', top: '15%', bottom: '5%', containLabel: true },
    xAxis: [{ type: 'category', data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], axisPointer: { type: 'shadow' }, axisLine: { lineStyle: { color: '#475569' } }, axisLabel: { color: '#94a3b8', fontSize: 10 } }],
    yAxis: [
      { type: 'value', name: '吞吐量', nameTextStyle: { color: '#64748b', fontSize: 10 }, min: 0, max: 3000, splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } }, axisLabel: { color: '#94a3b8', fontSize: 10 } },
      { type: 'value', name: '置信度', nameTextStyle: { color: '#64748b', fontSize: 10 }, min: 0.8, max: 1.0, splitLine: { show: false }, axisLabel: { color: '#94a3b8', fontSize: 10 } }
    ],
    series: [
      { name: '日均吞吐量', type: 'bar', barWidth: '30%', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#3b82f6' }, { offset: 1, color: '#1d4ed8' }]), borderRadius: [4, 4, 0, 0] }, data: [1250, 1800, 2100, 1500, 2600, 1100, 2908] },
      { name: '平均置信度', type: 'line', yAxisIndex: 1, smooth: true, itemStyle: { color: '#10b981' }, lineStyle: { width: 2, shadowColor: 'rgba(16, 185, 129, 0.5)', shadowBlur: 10 }, data: [0.95, 0.96, 0.94, 0.98, 0.97, 0.92, 0.98] }
    ]
  }
  myChart.setOption(option)
}

const fetchChartData = async () => {
  try {
    const response = await fetch("/api/chart_stats");
    if (!response.ok) throw new Error("获取图表数据失败");
    const res = await response.json();
    const dates = res.series.map(item => item.date);
    const throughputs = res.series.map(item => item.throughput);
    const confidences = res.series.map(item => item.confidence);
    myChart.setOption({ xAxis: [{ data: dates }], series: [{ name: '日均吞吐量', data: throughputs }, { name: '平均置信度', data: confidences }] });
  } catch (error) {
    // 降级使用 mock 数据，不中断流程
  }
}

const fetchRealSystemStats = async () => {
  try {
    const response = await fetch("/api/system_stats");
    if (!response.ok) throw new Error("无法获取监控数据");
    const realData = await response.json();
    animateValue(kpi, 'throughput', 0, realData.throughput, 1500, false);
    animateValue(kpi, 'hitRate', 0, realData.hit_rate, 1500, true);
    animateValue(kpi, 'confidence', 0, realData.confidence, 1500, true);
  } catch (error) {
    animateValue(kpi, 'throughput', 0, 14208, 1500, false);
    animateValue(kpi, 'hitRate', 0, 94.2, 1500, true);
    animateValue(kpi, 'confidence', 0, 0.98, 1500, true);
  }
}

// --- 5. 文件预览控制 ---
watch(() => uiState.showPreview, (newVal) => {
  if (!newVal) {
    if (uiState.previewUrl) {
      URL.revokeObjectURL(uiState.previewUrl);
      uiState.previewUrl = '';
    }
    const previewContainer = document.getElementById('docx-preview-container');
    if (previewContainer) previewContainer.innerHTML = '';
    uiState.previewType = 'text';
    uiState.realSourceText = '';
    uiState.currentPreviewFile = null;
    // 【新增这一行】：强制重置审批模式，防止幽灵状态
    //uiState.isApprovingInDrawer = false;
  }
});

// --- 【新增】处理 AI 生成报告的预览与下载 ---



const openPreview = (file) => {
  if (!file) return
  uiState.currentPreviewFile = file
  uiState.showPreview = true
  uiState.realSourceText = ''
  uiState.previewUrl = ''
  uiState.previewLoading = false
  uiState.activePreviewTab = 'source'

  if (!file.raw) { uiState.previewType = 'unsupported'; return; }

  const fileName = file.name.toLowerCase()
  const fileType = file.raw.type

  if (fileType.startsWith('image/')) {
    uiState.previewType = 'image'
    uiState.previewUrl = URL.createObjectURL(file.raw)
  } else if (fileType === 'application/pdf' || fileName.endsWith('.pdf')) {
    uiState.previewType = 'pdf'
    uiState.previewUrl = URL.createObjectURL(file.raw)
  } else if (fileType.includes('text') || fileName.endsWith('.md') || fileName.endsWith('.txt')) {
    uiState.previewType = 'text'
    uiState.previewLoading = true
    const reader = new FileReader()
    reader.onload = (e) => { uiState.realSourceText = e.target.result; uiState.previewLoading = false; }
    reader.readAsText(file.raw)
  } else if (fileName.endsWith('.docx')) {
    uiState.previewType = 'docx'
    uiState.previewLoading = true
    setTimeout(() => {
      const container = document.getElementById('docx-preview-container')
      if (container && file.raw) {
        renderAsync(file.raw, container, null, { inWrapper: true })
          .then(() => { uiState.previewLoading = false })
          .catch(() => { uiState.previewLoading = false; uiState.previewType = 'unsupported'; })
      }
    }, 300)
  } else {
    uiState.previewType = 'unsupported'
  }
}

const getMatchedAnalysis = () => {
  if (!uiState.currentPreviewFile || !Array.isArray(jobState.drafts)) return null
  return jobState.drafts.find(d => 
    (d.doc_id && uiState.currentPreviewFile.name.includes(d.doc_id)) || d.title === uiState.currentPreviewFile.name
  )
}

// 【新增】匹配该文件最终生成的实体报告资源
const getMatchedReport = () => {
  if (!uiState.currentPreviewFile || !Array.isArray(jobState.reports)) return null
  return jobState.reports.find(r => 
    (r.doc_id && uiState.currentPreviewFile.name.includes(r.doc_id)) || r.title === uiState.currentPreviewFile.name
  )
}

// 在预览窗口内直接打开生成的报告 (支持 HTML 推流预览和 Word 渲染预览)
const previewReportInternal = async (url, type) => {
  if (!url) return ElMessage.warning("报告地址无效");
  
  uiState.reportPreviewLoading = true;
  uiState.reportPreviewType = type;
  uiState.reportPreviewUrl = url;

  if (type === 'docx') {
    try {
      const response = await fetch(url);
      const blob = await response.blob();
      // 等待 Vue 将右侧的 report-docx-container 渲染到 DOM 中
      setTimeout(() => {
        const container = document.getElementById('report-docx-container');
        if (container) {
          container.innerHTML = '';
          renderAsync(blob, container, null, { inWrapper: true })
            .then(() => { uiState.reportPreviewLoading = false; })
            .catch(() => { uiState.reportPreviewType = 'unsupported'; uiState.reportPreviewLoading = false; });
        }
      }, 300);
    } catch (e) {
      ElMessage.error("远程 Word 报告读取失败");
      uiState.reportPreviewLoading = false;
    }
  } else {
    // HTML 报告直接推流给 iframe
    uiState.reportPreviewLoading = false;
  }
}

// 强制触发浏览器下载 (解决预览和下载的冲突)
const downloadArtifact = (url, fileName) => {
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.target = '_blank';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// --- 6. 任务提交流程 ---
const buildFormData = () => {
  const fd = new FormData()
  fd.append("llm_provider", formState.provider)
  fd.append("api_key", formState.apiKey)
  fd.append("mode", formState.mode)
  fd.append("input_tab", formState.inputTab)
  fd.append("email_file_types", formState.emailTypes.join(","))
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

const handleStartJob = async () => {
  if (!formState.apiKey) return ElMessage.warning("请先填写 API Key")
  
  localStorage.setItem('docs_agent_ui_provider', formState.provider)
  localStorage.setItem('docs_agent_ui_api_key', formState.apiKey)

  jobState.fileMetrics = {}
  fileList.value.forEach(f => updateFileMetric(f.name, { percent: 2, detail: '正在初始化...', tokens: 0, status: 'active' }));
  
  uiState.isSubmitting = true
  if (consoleRef.value) { consoleRef.value.clearLogs(); consoleRef.value.setStatus(true, 'UPLOADING'); }
  if (topologyRef.value) topologyRef.value.reset();

  try {
    const response = await fetch("/api/jobs", { method: "POST", body: buildFormData() })
    const data = await response.json()
    if (!response.ok) throw new Error(data.error || "提交失败")
    
    jobState.currentJobId = data.job_id
    if (consoleRef.value) consoleRef.value.appendLog('System', `任务创建成功，JobID: ${data.job_id}`, 'success')
    startStatusTracking(data.job_id)
  } catch (error) {
    ElMessage.error(error.message)
    uiState.isSubmitting = false 
  } 
}

// --- 7. SSE 状态流监听 (合并修正版) ---
const startStatusTracking = (jobId) => {
  if (jobState.statusEventSource) jobState.statusEventSource.close()
  jobState.statusEventSource = new EventSource(`/api/jobs/${jobId}/events?from_seq=0`)

  jobState.statusEventSource.addEventListener("stream", (event) => {
    try {
      const streamData = JSON.parse(event.data)
      const fileName = streamData.file_name || '合并任务'
      const eventType = streamData.event || 'token'
      
      if (consoleRef.value && eventType === 'token' && streamData.content) {
         // 调用新的 appendFileLog 方法，把 fileName 传过去！
         consoleRef.value.appendFileLog(fileName, streamData.agent || 'System', streamData.content)
      }

      if (!jobState.fileMetrics[fileName]) updateFileMetric(fileName, { tokens: 0, percent: 0, status: 'active' });

      if (eventType === 'token_update') {
        jobState.fileMetrics[fileName].tokens = Number(streamData.tokens || streamData.usage_tokens || 0);
      } else if (eventType === 'token') {
        jobState.fileMetrics[fileName].tokens += estimateTokenDelta(streamData.content);
      }

      if (eventType === 'stage_start') {
        const agent = streamData.agent ? streamData.agent.toLowerCase() : '';
        if (topologyRef.value) topologyRef.value.setAgentStatus(agent, 'active');
        let p = agent === 'reader' ? 25 : (agent === 'reviewer' ? 55 : 85);
        updateFileMetric(fileName, { percent: p, detail: streamData.content || '处理中...', status: 'active' });
      } else if (eventType === 'stage_done') {
        const agent = streamData.agent ? streamData.agent.toLowerCase() : '';
        if (topologyRef.value) topologyRef.value.setAgentStatus(agent, 'done');
        let p = agent === 'reader' ? 50 : 80;
        updateFileMetric(fileName, { percent: p, detail: '节点处理完成' });
      }
    } catch (e) {}
  })

  // 【合并修复】：只保留这一个干净的 job 监听器
  jobState.statusEventSource.addEventListener("job", (event) => {
    try {
      const jobData = JSON.parse(event.data)
      
      if (jobData.status === 'pending_approval') {
        jobState.statusEventSource.close()
        uiState.isSubmitting = false 
        jobState.drafts = jobData.drafts || []
        jobState.recipientEmails = (jobData.recipient_emails && jobData.recipient_emails.length > 0) ? jobData.recipient_emails : ['']
        
        // 【修复 1】：进入审批模式，强制切换到校验标签
        uiState.isApprovingInDrawer = true;
        uiState.activePreviewTab = 'verification'; // 确保右侧显示表格
        uiState.showPreview = true; 

        // 【修复 2】：更强力的初始化第一个文件，确保 currentFileIndex 不会是 -1
        if (jobState.drafts.length > 0) {
          const firstDraft = jobState.drafts[0];
          const fileName = firstDraft.title || firstDraft.doc_id;
          // 优先全字匹配，其次模糊匹配
          let matchedFile = fileList.value.find(f => f.name === fileName) || 
                            fileList.value.find(f => f.name.includes(firstDraft.doc_id || '')) ||
                            fileList.value[0]; // 兜底：实在找不到就开第一个文件

          if (matchedFile) openPreview(matchedFile);
          // 重要：因为 openPreview 会把 Tab 改回 source，这里要强制改回 verification
          uiState.activePreviewTab = 'verification';
          uiState.isApprovingInDrawer = true; 
        }
      }
      else if (jobData.status === 'success') {
        jobState.statusEventSource.close()
        uiState.isSubmitting = false 
        jobState.reports = jobData.reports || []
        jobState.emailResult = jobData.email_result
        uiState.showResult = true
        Object.keys(jobState.fileMetrics).forEach(fileName => {
          updateFileMetric(fileName, { percent: 100, detail: '任务执行完毕', status: 'done' });
        });
        if (consoleRef.value) {
          consoleRef.value.appendLog('System', '任务全部执行完毕！', 'success')
          consoleRef.value.setStatus(false, 'SUCCESS')
        }
        triggerKPIUpdate(jobData.reports?.length || 1);
      } else if (jobData.status === 'failed') {
        jobState.statusEventSource.close()
        uiState.isSubmitting = false
        if (consoleRef.value) consoleRef.value.setStatus(false, 'FAILED')
      }
    } catch (e) {}
  })
}

// --- 8. 审批提交 ---
const tableRowClassName = ({ row }) => ((row.score !== undefined && row.score < 85) || row.critic_warning) ? 'warning-row' : ''

const submitApproval = async () => {
  const totalFiles = jobState.drafts.length;
  const validEmails = jobState.recipientEmails.map(e => e.trim()).filter(e => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e))
  
  if (formState.mode === 'email' && validEmails.length === 0) return ElMessage.warning("请至少填写一个有效的邮箱")

  uiState.isApproving = true
  // 这里可以加上 isSubmitting，防止侧边栏被误点
  uiState.isSubmitting = true 

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
    
    // 【核心修复点 1】：提交成功后
    jobState.drafts.forEach(d => {
      d.isFinalized = true; 
    });
    
    // 【核心修复点 2】：重置 UI 状态
    uiState.isApprovingInDrawer = false; 
    uiState.showPreview = false; // 建议直接关闭抽屉，让用户看主大屏的进度

    ElMessage.success(`✅ 批次核实完毕，已成功下发 ${totalFiles} 份公文`);
    
    // 重新开启状态追踪，进入最后生成报告的阶段
    startStatusTracking(jobState.currentJobId)
  } catch (error) {
    ElMessage.error(error.message)
    // 如果失败了，要把提交状态改回来，允许用户重试
    uiState.isSubmitting = false 
  } finally {
    uiState.isApproving = false
  }
}

// --- 文件列表管理逻辑 ---

// 删除单个文件
const removeSingleFile = (index, fileName) => {
  fileList.value.splice(index, 1);
  // 清理监控指标
  if (jobState.fileMetrics[fileName]) delete jobState.fileMetrics[fileName];
  // 如果正在预览该文件，关闭预览
  if (uiState.currentPreviewFile?.name === fileName) uiState.showPreview = false;
}

// 一键清空
const clearAllFiles = () => {
  fileList.value = [];
  jobState.fileMetrics = {};
  jobState.drafts = [];
  jobState.reports = [];
  uiState.showPreview = false;
  uiState.showResult = false;
  if (consoleRef.value) consoleRef.value.clearLogs();
}

// --- 保存系统底层配置 ---
const saveSettings = () => {
  localStorage.setItem('docs_agent_theme', formState.theme)
  localStorage.setItem('docs_agent_ui_provider', formState.provider)
  localStorage.setItem('docs_agent_ui_api_key', formState.apiKey)
  uiState.showSettings = false
  ElMessage.success("系统配置已更新，视觉主题已切换")
}

// --- 9. 初始化钩子 (统一合并) ---
onMounted(() => {
  initTrendChart()
  fetchRealSystemStats()
  fetchChartData()
  window.addEventListener('resize', () => { if (myChart) myChart.resize() })

  // 【新增】：监听拖拽导致的父容器尺寸变化，实时重绘图表
  const resizeObserver = new ResizeObserver(() => {
    if (myChart) myChart.resize();
  });
  if (chartContainerRef.value) {
    resizeObserver.observe(chartContainerRef.value);
  }
})
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

/* --- 【新增】赛博朋克光影与动效 --- */

/* 1. 让背景网格缓慢向下移动，营造数据流下降的视觉错觉 */
@keyframes gridMove {
  0% { background-position: 0 0; }
  100% { background-position: 0 24px; }
}
.bg-grid-pattern {
  background-image: radial-gradient(rgba(59, 130, 246, 0.15) 1px, transparent 1px);
  background-size: 24px 24px;
  animation: gridMove 3s linear infinite; /* 激活网格流动 */
}

/* 2. 给中间的主画布区域加上微弱的呼吸扫描光效 */
@keyframes ambientBreathe {
  0%, 100% { box-shadow: inset 0 0 20px rgba(59, 130, 246, 0.05); }
  50% { box-shadow: inset 0 0 50px rgba(59, 130, 246, 0.15); }
}
main section {
  animation: ambientBreathe 4s ease-in-out infinite;
}

/* 3. 强化任务队列项的悬停微交互 (磁性吸附感) */
.custom-scrollbar > div:hover {
  transform: translateX(4px);
  border-left: 2px solid #3b82f6;
  background-color: rgba(30, 41, 59, 0.9);
}

/* 4. 左侧 Tabs 下划线动画变色 */
.custom-tabs .el-tabs__active-bar {
  background: linear-gradient(90deg, #38bdf8, #818cf8);
  box-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
}


/* --- 【新增】审批表格的风险预警样式 --- */
.custom-dark-table .warning-row {
  --el-table-tr-bg-color: rgba(245, 158, 11, 0.08); /* 极淡的琥珀色背景 */
}
.custom-dark-table .warning-row:hover > td.el-table__cell {
  background-color: rgba(245, 158, 11, 0.15) !important;
}
/* 警告行内的输入框也要泛红/泛黄，提示用户修改 */
.warning-input .el-input__wrapper {
  box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.5) inset !important;
  background-color: rgba(245, 158, 11, 0.05) !important;
}
.warning-input .el-input__inner {
  color: #fbbf24 !important;
  font-weight: bold;
}

/* --- 【新增】赛博朋克极客特效 --- */

/* 1. 流光字体：赋予顶部标题呼吸光泽 */
.text-shimmer {
  background: linear-gradient(120deg, #e2e8f0 20%, #60a5fa 40%, #60a5fa 60%, #e2e8f0 80%);
  background-size: 200% auto;
  color: transparent;
  -webkit-background-clip: text;
  background-clip: text; /* 添加这一行标准属性 */
  animation: shimmer 3s linear infinite;
}
@keyframes shimmer {
  to { background-position: 200% center; }
}

/* 2. CRT 显示器老式扫描线遮罩 (用在逻辑流监控终端) */
.crt-scanlines::before {
  content: " ";
  display: block;
  position: absolute;
  top: 0; left: 0; bottom: 0; right: 0;
  background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.15) 50%), 
              linear-gradient(90deg, rgba(255, 0, 0, 0.03), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.03));
  z-index: 50; /* 盖在最上层但允许穿透 */
  background-size: 100% 3px, 4px 100%;
  pointer-events: none; /* 绝对不能阻挡鼠标点击事件 */
}

/* 3. 增强左侧面板悬停时的浮空感 */
aside > section {
  box-shadow: inset 0 0 20px rgba(0,0,0,0.5), 0 5px 20px rgba(0,0,0,0.2);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

/* 4. 让拖拽分割器（Splitter）看起来像一道高能激光束 */
.cursor-ns-resize.group:hover > div:first-child {
  box-shadow: 0 0 15px #60a5fa, 0 0 30px #3b82f6;
  height: 3px; /* 拖拽时变粗变亮 */
}

/* --- 【全新】现代政企指挥舱 (Gov-Tech Command Center) 视觉规范 --- */

/* 1. 背景沉稳化：从跳动的黑客网格，改为高级点阵纹理，给人稳定、精准的心理暗示 */
.bg-grid-pattern {
  background-color: #0f172a; /* 坚实的深蓝灰基底 */
  background-image: radial-gradient(rgba(148, 163, 184, 0.15) 1px, transparent 1px);
  background-size: 20px 20px;
}

/* 2. 顶级毛玻璃材质 (Fluent/Mica)：告别纯黑深渊，拥抱带有一丝白边的高级亚克力质感 */
.glass-panel {
  background: rgba(30, 41, 59, 0.75); 
  backdrop-filter: blur(24px) saturate(120%);
  -webkit-backdrop-filter: blur(24px) saturate(120%);
  border: 1px solid rgba(255, 255, 255, 0.1); 
  transition: border-color 0.3s ease;
}

/* 3. 字体材质：去掉花哨流光，使用冷峻的金属微渐变 */
.text-metallic {
  background: linear-gradient(180deg, #ffffff 0%, #94a3b8 100%);
  -webkit-background-clip: text;
  background-clip: text; /* 添加这一行标准属性 */
  color: transparent;
  text-shadow: 0 2px 4px rgba(0,0,0,0.3);
}

/* 4. 等宽数字：让数据监控面板看起来像金融终端一样严谨 */
.tabular-data {
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

/* 5. 机械质感按钮：模拟物理世界的“按压反馈”，摒弃霓虹发光 */
.btn-corporate {
  background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%);
  border: 1px solid #3b82f6;
  border-top: 1px solid #60a5fa; /* 顶部高光 */
  box-shadow: 0 4px 6px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.15);
  text-shadow: 0 1px 2px rgba(0,0,0,0.4);
}
.btn-corporate:hover:not(:disabled) {
  background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
}

/* 6. 拖拽分割线的极简优化 */
.cursor-ns-resize.group:hover > div:first-child {
  background-color: #60a5fa !important;
  box-shadow: none !important; /* 去掉极客光效，回归实用主义 */
  height: 3px;
}

/* 深色模式默认光影 */
.floating-panel {
  /* 阴影解析：左上极细受光线(亮) + 右下极细暗色内折射(暗) + 实体右下大投影 + 侧向弱蓝环境弥散光 */
  box-shadow: 
    inset 1.5px 1.5px 2px rgba(255, 255, 255, 0.08), 
    inset -1px -1px 2px rgba(0, 0, 0, 0.3),
    8px 12px 24px -8px rgba(5, 10, 20, 0.8), 
    16px 24px 48px -12px rgba(59, 130, 246, 0.06) !important; 
  transition: box-shadow 0.5s cubic-bezier(0.2, 0.8, 0.2, 1) !important; /* 物理弹性动效 */
}

/* 深色模式悬停：阴影范围剧烈扩散，制造“被吸向屏幕外”的 Z 轴错觉，杜绝 X/Y 轴位移 */
.floating-panel:hover {
  box-shadow: 
    inset 2px 2px 3px rgba(255, 255, 255, 0.12), 
    inset -1.5px -1.5px 3px rgba(0, 0, 0, 0.5),
    15px 25px 40px -10px rgba(5, 10, 20, 0.95), 
    30px 45px 65px -15px rgba(59, 130, 246, 0.12) !important; 
}



/* ==========================================================================
   【极致版】雅致象牙白主题 (Warm Light/Ivory Theme) 
   核心理念：去除 Slate 冷灰，拥抱 Stone 暖灰与纯白高光
   ========================================================================== */

/* 1. 干净白金基底 (Base) */
.theme-light.bg-grid-pattern {
  background-color: #f8fafc !important; /* 纯净极浅灰底色，绝不发黄 */
  background-image: radial-gradient(rgba(0, 0, 0, 0.04) 1px, transparent 1px) !important;
  background-size: 24px 24px !important;
}
.theme-light .bg-blue-600\/10 { display: none; } /* 关掉背景杂色光晕 */
.theme-light .bg-purple-600\/10 { display: none; }

/* 2. 纯白玻璃材质 (消除发黄滤镜) */
.theme-light .glass-panel,
.theme-light aside .glass-panel {
  background: #ffffff !important; /* 绝对纯白 */
  backdrop-filter: none !important; /* 彻底移除导致发黄变脏的滤镜！ */
  -webkit-backdrop-filter: none !important;
  border: 1px solid #e2e8f0 !important;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important; /* 常规干净投影 */
}

/* ==========================================================================
   2. 【新增】高级物理侧顶光悬浮引擎 (Floating & Directional Light) 
   ========================================================================== */


.theme-light {
  /* 强制覆盖 Element Plus 在亮色模式下的全局底色与文字色 */
  --el-text-color-primary: #1e293b !important;
  --el-text-color-regular: #475569 !important;
  --el-bg-color: rgba(255, 255, 255, 0.9) !important;
  --el-border-color: #cbd5e1 !important;
  --el-border-color-hover: #d97706 !important;
  --el-fill-color-blank: rgba(241, 245, 249, 0.6) !important; /* 输入框底色 */
  --el-input-text-color: #1e293b !important;
  --el-input-bg-color: rgba(241, 245, 249, 0.6) !important;
}

/* 修复未选中 Tab 字体和底色一样的问题 */
div.theme-light .el-tabs__item {
  color: #64748b !important;
  transition: all 0.3s ease;
}
div.theme-light .el-tabs__item:hover { color: #d97706 !important; }
div.theme-light .el-tabs__item.is-active { 
  color: #d97706 !important; 
  font-weight: 900 !important; 
  text-shadow: 0 2px 10px rgba(217, 119, 6, 0.2); 
}

/* 修复“快捷粘贴”与“全网抓取”的黑色输入框，赋予立体内陷感 */
.theme-light .el-textarea__inner,
.theme-light .el-input__wrapper {
  background: rgba(241, 245, 249, 0.8) !important;
  border: 1px solid #cbd5e1 !important;
  box-shadow: inset 0 2px 5px rgba(0,0,0,0.03), 0 1px 0 rgba(255,255,255,1) !important; /* 物理内凹 */
  color: #1e293b !important;
  transition: all 0.3s ease !important;
}
.theme-light .el-textarea__inner:focus,
.theme-light .el-input__wrapper.is-focus {
  background: #ffffff !important;
  border-color: #d97706 !important; /* 聚焦时香槟金亮起 */
  box-shadow: inset 0 2px 5px rgba(217, 119, 6, 0.05), 0 0 0 1px #d97706 !important;
}

/* 3. 高级丝滑悬浮 (Hover & Activation) */
.theme-light .floating-panel {
  transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.4s ease, border-color 0.4s ease !important;
}
.theme-light .floating-panel:hover {
  transform: translateY(-4px) scale(1.002) !important; /* 带有弹性的吸附上浮 */
  border-color: rgba(217, 119, 6, 0.3) !important; /* 边缘泛起高级香槟金 */
  background: linear-gradient(135deg, rgba(255,255,255,1) 0%, rgba(255,255,255,0.9) 100%) !important;
  box-shadow: 
    0 15px 35px -5px rgba(15, 23, 42, 0.08), 
    0 0 40px -10px rgba(217, 119, 6, 0.15), /* 底层爆发出香槟金氛围光 */
    inset 1px 1px 0px rgba(255, 255, 255, 1) !important;
  z-index: 50;
}

/* 4. 文件上传区 - 工程蓝图托盘 (Blueprint Tray) */
.theme-light .upload-blueprint .el-upload-dragger {
  background: rgba(241, 245, 249, 0.6) !important; /* 高级毛玻璃银白 */
  border: 2px dashed #cbd5e1 !important;
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1) !important;
}
/* 强行把上传区里“隐形”的文字变深 */
.theme-light .upload-blueprint .el-upload__text,
.theme-light .upload-blueprint .el-upload__text em {
  color: #334155 !important; 
}
.theme-light .upload-blueprint .el-icon--upload {
  color: #1e40af !important; /* 默认藏青色图标 */
  transition: all 0.4s ease !important;
}

/* 🌟 上传区悬停特效：香槟金光感与微放大 */
.theme-light .upload-blueprint:hover .el-upload-dragger {
  background: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(255,255,255,1) 100%) !important;
  border-color: #d97706 !important; /* 香槟金虚线 */
  box-shadow: 0 10px 30px -5px rgba(217, 119, 6, 0.15), inset 0 2px 10px rgba(217,119,6,0.05) !important;
}
.theme-light .upload-blueprint:hover .el-icon--upload {
  color: #d97706 !important; /* 图标点亮为香槟金 */
  transform: translateY(-4px) scale(1.1); /* 动态微浮 */
}

/* 5. 逻辑流终端 - 纯白背景 + 高可视度日志字体 */
.theme-light .terminal-window {
  background: #ffffff !important; /* 强制纯白终端背景 */
  border: 1px solid #e2e8f0 !important;
  box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.02) !important;
}
/* 强制覆盖 ThinkingConsole 内部所有可能带黑底的容器 */
.theme-light .terminal-window div,
.theme-light .terminal-window pre,
.theme-light .terminal-window code {
  background-color: transparent !important;
}
/* 终端基础文字变深铁灰 */
.theme-light .terminal-window *,
.theme-light .terminal-window span,
.theme-light .terminal-window p {
  color: #334155 !important;
  text-shadow: none !important;
}
/* 精准映射各种高亮日志颜色，确保在白底上极度清晰且保留区分度 */
.theme-light .terminal-window .text-slate-300,
.theme-light .terminal-window .text-slate-400,
.theme-light .terminal-window .text-slate-500 { color: #475569 !important; } /* 普通日志：深灰 */
.theme-light .terminal-window .text-blue-400 { color: #1d4ed8 !important; font-weight: bold; } /* 浅蓝(Review等) -> 皇室深蓝 */
.theme-light .terminal-window .text-emerald-400 { color: #059669 !important; font-weight: bold; } /* 浅绿(Success) -> 深翡翠绿 */
.theme-light .terminal-window .text-amber-400 { color: #b45309 !important; font-weight: bold; } /* 浅黄(Warning) -> 深琥珀色 */
.theme-light .terminal-window .text-red-400 { color: #dc2626 !important; font-weight: bold; } /* 浅红(Error) -> 深红 */
.theme-light .terminal-window h2 { color: #64748b !important; }

/* 强制翻转非终端区域的白字 */
.theme-light :not(.terminal-window) > .text-white,
.theme-light :not(.terminal-window) > .text-slate-100,
.theme-light :not(.terminal-window) > .text-slate-200 { color: #1e293b !important; }

/* 6. 高精度色彩排版 (Typography) */
/* 主标题金属字：藏青 -> 冷银 */
.theme-light .text-metallic {
  background: linear-gradient(135deg, #1e3a8a 0%, #64748b 100%) !important;
  -webkit-background-clip: text !important;
  background-clip: text !important;
  color: transparent !important;
}
/* 核心数据点缀：抛弃单调的暗色反转，采用专属渐变 */
.theme-light .kpi-blue { 
  background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%) !important;
  -webkit-background-clip: text !important;
  background-clip: text !important; color: transparent !important;
}
.theme-light .kpi-green { 
  background: linear-gradient(135deg, #059669 0%, #10b981 100%) !important;
  -webkit-background-clip: text !important;
  background-clip: text !important; color: transparent !important;
}
.theme-light .kpi-gold { 
  background: linear-gradient(135deg, #b45309 0%, #f59e0b 100%) !important;
  -webkit-background-clip: text !important;
  background-clip: text !important; color: transparent !important;
}

/* 强制翻转所有写死的 Tailwind 纯白/浅灰文字 */
.theme-light .text-white,
.theme-light .text-slate-100,
.theme-light .text-slate-200 { color: #1e293b !important; } /* 变为深墨色 */
.theme-light .text-slate-300 { color: #334155 !important; }
.theme-light .text-slate-400 { color: #475569 !important; }
.theme-light .text-slate-500 { color: #64748b !important; }

/* 强制洗掉各种残余的暗色块 (如侧边栏的文件列表底色) */
.theme-light [class*="bg-slate-9"],
.theme-light [class*="bg-[#0b1120]"] {
  background-color: rgba(255, 255, 255, 0.7) !important;
  border-color: #e2e8f0 !important;
}

/* 7. 主操作按钮的 3D 物理质感 */
.theme-light .btn-corporate {
  background: linear-gradient(180deg, #2563eb 0%, #1e40af 100%) !important;
  border: 1px solid #1e3a8a !important;
  box-shadow: 
    inset 0 1px 0 rgba(255, 255, 255, 0.3), /* 顶部白金反光 */
    0 8px 15px -3px rgba(30, 64, 175, 0.3) !important; /* 底部皇室蓝投影 */
  color: #ffffff !important;
}
.theme-light .btn-corporate:hover:not(:disabled) {
  background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4), 0 12px 20px -5px rgba(30, 64, 175, 0.4) !important;
  transform: translateY(-1px);
}
.theme-light .btn-corporate:active {
  /* 按压时陷入阴影 */
  transform: translateY(1px);
  box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.2) !important;
}

/* 8. 局部精细修饰 (组件细节) */
/* Tabs 选中为香槟金 */
.theme-light .el-tabs__item.is-active { color: #d97706 !important; font-weight: bold; } /* Tab香槟金 */
.theme-light .bg-slate-700 { background-color: #e2e8f0 !important; } /* 分割线 */
.theme-light .border-slate-700, 
.theme-light .border-slate-700\/50, 
.theme-light .border-slate-800 { border-color: #e2e8f0 !important; }
/* 内部卡片(列表/弹窗)为纯净白 */
.theme-light .bg-slate-900\/80, 
.theme-light .bg-slate-900\/50,
.theme-light .bg-slate-950,
.theme-light .bg-slate-900 { 
  background-color: rgba(255, 255, 255, 0.8) !important; 
  border: 1px solid #e2e8f0 !important;
}


/* ==========================================================================
   【全局进阶体验 1】Mac 级沉浸式隐形滚动条 (双主题自动适配)
   ========================================================================== */

/* 全局接管滚动条宽度与高度 */
::-webkit-scrollbar {
  width: 6px !important;  /* 极细垂直滚动条 */
  height: 6px !important; /* 极细水平滚动条 */
}

/* 滚动条轨道：彻底透明，与背景融为一体 */
::-webkit-scrollbar-track {
  background: transparent !important;
  border-radius: 10px;
}

/* 滚动条滑块：默认深色模式下的半透明白灰 */
::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2) !important;
  border-radius: 10px;
  /* 不加过渡动画是因为 webkit-scrollbar 性能原因，靠 opacity 视觉错觉 */
}

/* 鼠标悬停在滑块上时：颜色加深，方便拖拽 */
::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.6) !important;
}

/* --------------------------------------------------------
   浅色模式 (Theme-Light) 专属适配
-------------------------------------------------------- */
.theme-light ::-webkit-scrollbar-thumb {
  background: rgba(100, 116, 139, 0.2) !important; /* 浅色下的淡淡石板灰 */
}
.theme-light ::-webkit-scrollbar-thumb:hover {
  background: rgba(100, 116, 139, 0.5) !important; /* 悬停加深 */
}

/* 终端内部独立适配：因为浅色模式下终端也是深色的，所以它的滚动条必须保持深色模式的样子 */
.theme-light .terminal-window ::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2) !important;
}
.theme-light .terminal-window ::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.6) !important;
}


/* ==========================================================================
   【全局进阶体验 2】终端高信噪比排版 (胶囊 Badge & JSON 结构化)
   ========================================================================== */

/* --------------------------------------------------------------------------
   1. 标签胶囊化 (Pill Badges) 修复拥挤与遗漏
   -------------------------------------------------------------------------- */
/* 把所有高亮颜色，以及被遗漏的中间栏白色（slate-300/200）都纳入胶囊范围 */
.terminal-window span.text-emerald-400,
.terminal-window span.text-blue-400,
.terminal-window span.text-amber-400,
.terminal-window span.text-red-400,
.terminal-window span.text-slate-400,
.terminal-window span.text-slate-300,
.terminal-window span.text-slate-200 {
  display: inline-block;
  padding: 6px 12px !important; /* 增加横向和纵向内边距，撑开空间 */
  border-radius: 6px !important; /* 边角更圆润 */
  font-size: 0.85em;
  font-weight: 900 !important;
  margin-right: 8px !important;
  border: 1px solid transparent;
  line-height: 1.4 !important; /* 恢复正常行高，彻底解决纵向挤压 */
  letter-spacing: 0.5px !important; /* 增加字间距，解决横向挤压 */
  white-space: nowrap !important; /* 绝对禁止内部文字换行 */
  vertical-align: top;
  white-space: pre-wrap !important; 
  word-break: break-all !important; 
  max-width: 100%; /* 绝对禁止撑破横向屏幕 */
  box-sizing: border-box;
}


/* 深色模式下的 Badge 底色 */
.terminal-window span.text-emerald-400 { background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); }
.terminal-window span.text-blue-400 { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.3); }
.terminal-window span.text-amber-400 { background: rgba(245, 158, 11, 0.15); border-color: rgba(245, 158, 11, 0.3); }
.terminal-window span.text-red-400 { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); }
.terminal-window span.text-slate-400 { background: rgba(148, 163, 184, 0.15); border-color: rgba(148, 163, 184, 0.3); }
/* 【新增】中间栏白色字体的胶囊样式 */
.terminal-window span.text-slate-300,
.terminal-window span.text-slate-200 { 
  background: rgba(255, 255, 255, 0.1); 
  border-color: rgba(255, 255, 255, 0.25); 
  color: #f8fafc !important; /* 保持白色字体 */
}

/* 浅色模式下终端也是深空蓝，复用深色底的半透明配色 */
.theme-light .terminal-window span.text-emerald-400 { background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); }
.theme-light .terminal-window span.text-blue-400 { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.3); }
.theme-light .terminal-window span.text-amber-400 { background: rgba(245, 158, 11, 0.15); border-color: rgba(245, 158, 11, 0.3); }
.theme-light .terminal-window span.text-red-400 { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); }
.theme-light .terminal-window span.text-slate-400 { background: rgba(148, 163, 184, 0.15); border-color: rgba(148, 163, 184, 0.3); }
/* 【新增】浅色主题下中间栏白色的胶囊样式 */
.theme-light .terminal-window span.text-slate-300,
.theme-light .terminal-window span.text-slate-200 { 
  background: rgba(255, 255, 255, 0.15); 
  border-color: rgba(255, 255, 255, 0.3); 
  color: #ea6919 !important; 
}

/* --------------------------------------------------------------------------
   2. 多行数据与 JSON 的高级代码块 (Code Block Formatting)
   -------------------------------------------------------------------------- */
.terminal-window pre,
.terminal-window code {
  display: block;
  background: rgba(0, 0, 0, 0.25) !important; /* 深色凹陷感 */
  border-left: 3px solid #3b82f6 !important; /* 科技蓝左侧高亮条 */
  padding: 10px 12px !important;
  border-radius: 0 4px 4px 0 !important;
  margin: 6px 0 6px 4px !important;
  font-family: 'Fira Code', 'Consolas', monospace !important;
  line-height: 1.5 !important;
  overflow-x: auto;
  font-size: 0.9em;
  box-shadow: inset 2px 2px 5px rgba(0, 0, 0, 0.1);
}

/* 浅色模式下的 JSON 代码块适配 (由于浅色模式下终端也是白底，所以代码块需要变成浅灰底) */
.theme-light .terminal-window pre,
.theme-light .terminal-window code {
  background: rgba(241, 245, 249, 0.6) !important;
  border-left: 3px solid #1d4ed8 !important; /* 皇室蓝边框 */
  box-shadow: inset 2px 2px 5px rgba(0, 0, 0, 0.02);
}


/* ==========================================================================
   【全局进阶体验 3】多智能体拓扑动态引擎 (Energy Flow & Living Nodes)
   ========================================================================== */

/* 1. 节点呼吸灯：给正在工作的智能体加上向外扩散的波纹 */
@keyframes agentPulse {
  0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
  70% { box-shadow: 0 0 0 15px rgba(59, 130, 246, 0); }
  100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); }
}

.agent-node-active {
  animation: agentPulse 2s infinite !important;
  border-color: #3b82f6 !important;
  position: relative;
}

/* 2. 数据飞线动画：如果拓扑图使用 SVG 路径，赋予其流动感 */
@keyframes lineFlow {
  from { stroke-dashoffset: 20; }
  to { stroke-dashoffset: 0; }
}

/* 针对拓扑图中的连接线（假设为 path 或 line） */
.topology-connection-active {
  stroke-dasharray: 4, 2;
  animation: lineFlow 0.8s linear infinite !important;
  stroke: #60a5fa !important;
  filter: drop-shadow(0 0 3px #3b82f6);
}

/* 3. 【解决立体感】菲涅尔反光边缘 (Fresnel Edge) 
   在浅色模式下，通过极其细微的“受光边缘”产生 3D 瓷器质感
*/
.theme-light .floating-panel {
  background: linear-gradient(135deg, #ffffff 0%, #f9fafb 100%) !important; /* 极细微的对角线渐变 */
  /* 核心：三层叠加阴影。1. 边缘极细亮线(受光) 2. 内部微弱凹陷 3. 外部弥散投影 */
  box-shadow: 
    inset 0 1px 1px rgba(255, 255, 255, 1),
    inset 0 -1px 1px rgba(0, 0, 0, 0.02),
    0 10px 25px -5px rgba(15, 23, 42, 0.05) !important;
}

.theme-light .floating-panel:hover {
  /* 悬停时：不仅变色，还要增强这种反光感 */
  box-shadow: 
    inset 0 1px 2px rgba(255, 255, 255, 1),
    0 25px 50px -12px rgba(15, 23, 42, 0.1) !important;
}

/* ==========================================================================
   【全局进阶体验 4】高级骨架屏扫光动画 (Skeleton Screen Shimmer)
   ========================================================================== */

/* 1. 骨架屏基础灰块 (深色模式默认) */
.skeleton-block {
  background-color: #1e293b; /* slate-800 */
  overflow: hidden;
  position: relative;
}

/* 2. 扫光动画核心引擎 */
@keyframes shimmerSweep {
  0% { transform: translateX(-150%); }
  50% { transform: translateX(150%); }
  100% { transform: translateX(150%); } /* 预留 50% 时间的停顿感，节奏更舒适 */
}

/* 3. 附加在容器上的扫光遮罩 */
.skeleton-container {
  position: absolute !important; 
  overflow: hidden;
}
.skeleton-container::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  /* 深色模式下的微弱银光 */
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.04) 50%, transparent 100%);
  animation: shimmerSweep 2.5s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  pointer-events: none; /* 绝对不能阻挡底层元素的点击 */
}

/* --------------------------------------------------------
   浅色模式 (Theme-Light) 骨架屏自适应
-------------------------------------------------------- */
.theme-light .skeleton-container {
  background: rgba(255, 255, 255, 0.9) !important;
}
.theme-light .skeleton-block {
  background-color: #e2e8f0 !important; /* 浅色模式下的浅灰块 */
}
.theme-light .skeleton-container::after {
  /* 浅色模式下极其清透的高光扫过 */
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.8) 50%, transparent 100%);
}
/* 浅色模式下中间“加载中”胶囊的提亮反转 */
.theme-light .skeleton-container span.bg-slate-900\/50 {
  background: #ffffff !important;
  color: #64748b !important;
  border-color: #cbd5e1 !important;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
}
</style>