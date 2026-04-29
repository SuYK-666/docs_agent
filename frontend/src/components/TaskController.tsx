import { useGlobalAppContext } from '@/context/GlobalAppContext'
import { GlassEffect } from '@/components/ui/liquid-glass'
import type { JobInputTab, JobStatusData, StartJobOptions } from '@/hooks/useJobMonitor'
import { FileText, Globe, Link2, Mail, Play, Trash2, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface TaskControllerProps {
  startJob: (options: StartJobOptions) => Promise<void>
  statusData: JobStatusData
  className?: string
}

const inputTabs: Array<{ key: JobInputTab; label: string; icon: typeof Upload }> = [
  { key: 'upload', label: '文件上传', icon: Upload },
  { key: 'paste', label: '快捷粘贴', icon: FileText },
  { key: 'crawl', label: '全网抓取', icon: Globe },
]

const emailTypeOptions = [
  { value: 'md', label: 'MD' },
  { value: 'docx', label: 'Word' },
  { value: 'ics', label: 'ICS' },
]

const emptyStateText = '暂无待处理文件'

function formatMetricStatus(status: string) {
  if (status === 'error') return '异常'
  if (status === 'done') return '完成'
  if (status === 'active') return '处理中'
  return '等待调度'
}

function resolveFileMetric(fileName: string, metrics: JobStatusData['fileMetrics']) {
  if (metrics[fileName]) return metrics[fileName]

  const metricEntry = Object.entries(metrics).find(([metricFileName]) => {
    return metricFileName === fileName || metricFileName.includes(fileName) || fileName.includes(metricFileName)
  })

  return metricEntry?.[1]
}

export default function TaskController({ startJob, statusData, className = '' }: TaskControllerProps) {
  const navigate = useNavigate()
  const { fileList, formState, setFileList, setFormState, setCurrentSelectedFile } = useGlobalAppContext()
  const [isDragActive, setIsDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const appendFiles = (files: File[]) => {
    if (files.length === 0) return
    setFileList((current) => [...current, ...files])
  }

  const removeSingleFile = (index: number) => {
    setFileList((current) => current.filter((_, currentIndex) => currentIndex !== index))
  }

  const clearAllFiles = () => {
    setFileList([])
    setCurrentSelectedFile('')
  }

  const handleFileSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    appendFiles(Array.from(event.target.files || []))
    event.target.value = ''
  }

  const handleDragOver = (event: React.DragEvent<HTMLButtonElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (!isDragActive) setIsDragActive(true)
  }

  const handleDragLeave = (event: React.DragEvent<HTMLButtonElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragActive(false)
  }

  const handleDrop = (event: React.DragEvent<HTMLButtonElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragActive(false)
    appendFiles(Array.from(event.dataTransfer.files || []))
  }

  const handlePreviewFile = (fileName: string) => {
    setCurrentSelectedFile(fileName)
    navigate('/workspace')
  }

  const toggleEmailType = (value: string) => {
    setFormState((current) => ({
      ...current,
      emailTypes: current.emailTypes.includes(value)
        ? current.emailTypes.filter((item) => item !== value)
        : [...current.emailTypes, value],
    }))
  }

  const handleToggleDesensitized = () => {
    setFormState((current) => {
      if (statusData.isSubmitting && current.isDesensitized) {
        return current
      }

      return {
        ...current,
        isDesensitized: !current.isDesensitized,
      }
    })
  }

  const handleStartJob = async () => {
    const provider = formState.provider || window.localStorage.getItem('docs_agent_ui_provider') || 'tongyi'
    const apiKey = formState.apiKey || window.localStorage.getItem('docs_agent_ui_api_key') || ''
    const model = window.localStorage.getItem('docs_agent_ui_model') || ''

    if (fileList.length > 0 && (!formState.inputTab || formState.inputTab === 'upload')) {
      setCurrentSelectedFile(fileList[0]?.name || '')
    }

    await startJob({
      provider,
      apiKey,
      model,
      mode: formState.mode,
      inputTab: formState.inputTab,
      emailTypes: formState.emailTypes,
      pastedText: formState.pastedText,
      crawlUrl: formState.crawlUrl,
      crawlKeyword: formState.crawlKeyword,
      crawlCount: formState.crawlCount,
      files: fileList,
    })
  }

  return (
    <GlassEffect className={`rounded-[2rem] p-6 ${className}`} contentClassName="h-full w-full min-w-0">
      <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileSelection} />

      <div className="flex h-full min-h-[820px] min-w-0 flex-col">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-cyan-100/70">任务控制台</p>
            <h3 className="mt-2 text-2xl font-semibold text-white">任务输入与启动面板</h3>
          </div>
          <span className="rounded-full bg-white/10 px-3 py-1 text-sm text-white/75">
            {statusData.isSubmitting ? '任务提交中' : '待命'}
          </span>
        </div>

        <div className="grid min-w-0 flex-1 gap-4">
          <div className="flex items-center justify-between rounded-[1.35rem] border border-white/10 bg-black/18 p-3">
            <div className="min-w-0">
              <p
                className={`text-[11px] uppercase tracking-[0.18em] transition ${
                  formState.isDesensitized
                    ? 'text-emerald-400 font-bold drop-shadow-[0_0_5px_#10b981]'
                    : 'text-slate-500'
                }`}
              >
                {formState.isDesensitized ? '脱敏已开启' : '全局脱敏'}
              </p>
              <p className="mt-1 text-xs text-white/50">开启后日志即时脱敏；任务执行过程中如果已开启，则不可关闭。</p>
            </div>

            <button
              type="button"
              onClick={handleToggleDesensitized}
              disabled={statusData.isSubmitting && formState.isDesensitized}
              aria-pressed={formState.isDesensitized}
              className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition ${
                formState.isDesensitized ? 'bg-emerald-500/85' : 'bg-slate-700'
              } ${(statusData.isSubmitting && formState.isDesensitized) ? 'cursor-not-allowed opacity-70' : ''}`}
            >
              <span
                className={`inline-block h-5 w-5 rounded-full bg-white transition ${
                  formState.isDesensitized ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div className="flex min-h-0 min-w-0 flex-1 flex-col rounded-[1.5rem] border border-white/10 bg-black/18 p-3">
            <div className="grid grid-cols-3 gap-2">
              {inputTabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setFormState((current) => ({ ...current, inputTab: tab.key }))}
                  className={`flex items-center justify-center gap-2 rounded-[1.1rem] px-3 py-2.5 text-sm font-medium transition ${
                    formState.inputTab === tab.key ? 'bg-white/18 text-white' : 'text-white/70 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  <tab.icon className="h-4 w-4" />
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="mt-4 min-h-0 min-w-0 flex-1">
              {formState.inputTab === 'upload' && (
                <div className="flex h-full min-h-0 min-w-0 flex-col gap-3">
                  <div className="flex min-w-0 items-center justify-between gap-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-white/45">待处理文件</p>
                    <button
                      type="button"
                      onClick={clearAllFiles}
                      disabled={fileList.length === 0 || statusData.isSubmitting}
                      className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-white/75 transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      一键清空
                    </button>
                  </div>

                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    className={`rounded-[1.5rem] border border-dashed px-4 py-6 text-center transition ${
                      isDragActive
                        ? 'border-cyan-300/50 bg-cyan-300/10'
                        : 'border-white/15 bg-black/20 hover:bg-white/8'
                    }`}
                  >
                    <Upload className="mx-auto h-6 w-6 text-cyan-100" />
                    <p className="mt-3 text-sm font-semibold text-white">拖拽或点击上传</p>
                    <p className="mt-1 text-xs text-white/55">支持原生拖拽放置文件，文件队列会保留在全局状态中。</p>
                  </button>

                  <div className="min-h-[360px] flex-1 overflow-y-auto custom-scrollbar overflow-x-hidden p-1">
                    {fileList.map((file, index) => {
                      const metric = resolveFileMetric(file.name, statusData.fileMetrics)

                      return (
                        <button
                          key={`${file.name}-${index}`}
                          type="button"
                          onClick={() => handlePreviewFile(file.name)}
                          className="relative mb-2 block w-full min-w-0 box-border overflow-hidden rounded-[1.25rem] border border-white/10 bg-slate-900/80 p-3 text-left transition hover:border-cyan-300/35"
                        >
                          {metric && (
                            <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-[1rem]">
                              <div
                                className="absolute inset-y-0 left-0 max-w-full bg-blue-900/20 transition-all duration-500"
                                style={{ width: `${metric.percent || 0}%` }}
                              />
                            </div>
                          )}

                          <div className="relative z-10 flex w-full min-w-0 flex-col gap-2 overflow-hidden">
                            <div className="flex w-full min-w-0 items-center justify-between gap-3 overflow-hidden">
                              <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
                                <span className="flex-1 truncate text-sm font-semibold text-white">{file.name}</span>
                                <p className="truncate text-xs text-white/55">{metric ? formatMetricStatus(metric.status) : '等待调度'}</p>
                              </div>

                              <div className="flex shrink-0 items-center gap-2">
                                <span className={`text-[11px] font-mono font-bold ${metric?.status === 'error' ? 'text-red-400' : 'text-cyan-100'}`}>
                                  {metric ? `${metric.percent || 0}%` : '0%'}
                                </span>
                                {!statusData.isSubmitting && (
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      removeSingleFile(index)
                                    }}
                                    className="rounded-full p-1 text-slate-400 transition hover:bg-white/10 hover:text-red-400"
                                    aria-label={`remove-${file.name}`}
                                  >
                                    <X className="h-4 w-4" />
                                  </button>
                                )}
                              </div>
                            </div>

                            {metric && (
                              <div className="flex min-w-0 w-full items-center justify-between gap-3 overflow-hidden text-[11px]">
                                <span className="flex flex-1 min-w-0 items-center gap-1 overflow-hidden text-white/60" title={metric.detail}>
                                  {metric.status === 'active' && <span className="inline-block h-1.5 w-1.5 shrink-0 animate-ping rounded-full bg-blue-500" />}
                                  <span className="truncate">{metric.detail}</span>
                                </span>
                                <span
                                  className="flex shrink-0 items-center gap-1 rounded-full border border-cyan-300/15 bg-slate-950 px-2 py-1 font-mono text-cyan-100"
                                  title="该文件累计消耗 Token"
                                >
                                  <span className="text-[12px] leading-none">⚡</span>
                                  {metric.tokens || 0}
                                </span>
                              </div>
                            )}
                          </div>
                        </button>
                      )
                    })}

                    {fileList.length === 0 && (
                      <div className="flex h-full min-h-[280px] flex-col items-center justify-center rounded-[1.25rem] border border-dashed border-white/10 bg-black/12 text-center text-white/45">
                        <Upload className="h-8 w-8" />
                        <p className="mt-3 text-sm">{emptyStateText}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {formState.inputTab === 'paste' && (
                <div className="flex h-full flex-col rounded-[1.5rem] border border-white/10 bg-black/20 p-3">
                  <textarea
                    value={formState.pastedText}
                    onChange={(event) => setFormState((current) => ({ ...current, pastedText: event.target.value }))}
                    rows={12}
                    placeholder="直接粘贴微信、钉钉或文档正文内容..."
                    className="h-full w-full resize-none bg-transparent text-sm leading-7 text-white placeholder:text-white/35 outline-none"
                  />
                </div>
              )}

              {formState.inputTab === 'crawl' && (
                <div className="grid gap-3">
                  <div className="rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-3">
                    <input
                      value={formState.crawlUrl}
                      onChange={(event) => setFormState((current) => ({ ...current, crawlUrl: event.target.value }))}
                      placeholder="输入抓取 URL"
                      className="w-full bg-transparent text-sm text-white placeholder:text-white/35 outline-none"
                    />
                  </div>
                  <div className="rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-3">
                    <input
                      value={formState.crawlKeyword}
                      onChange={(event) => setFormState((current) => ({ ...current, crawlKeyword: event.target.value }))}
                      placeholder="过滤关键词"
                      className="w-full bg-transparent text-sm text-white placeholder:text-white/35 outline-none"
                    />
                  </div>
                  <div className="flex items-center justify-between rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-3">
                    <span className="text-sm text-white/65">抓取条数</span>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={formState.crawlCount}
                      onChange={(event) =>
                        setFormState((current) => ({
                          ...current,
                          crawlCount: Math.max(1, Math.min(20, Number(event.target.value) || 1)),
                        }))
                      }
                      className="w-20 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-right text-sm text-white outline-none"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-[1.5rem] border border-white/10 bg-black/18 p-3">
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'preview', label: '仅预览' },
                { value: 'email', label: '邮件下发' },
              ].map((mode) => (
                <button
                  key={mode.value}
                  onClick={() => setFormState((current) => ({ ...current, mode: mode.value as typeof formState.mode }))}
                  className={`rounded-[1.1rem] px-3 py-2.5 text-sm font-medium transition ${
                    formState.mode === mode.value ? 'bg-white/18 text-white' : 'text-white/70 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  {mode.label}
                </button>
              ))}
            </div>

            {formState.mode === 'email' && (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-[1.2rem] border border-white/10 bg-black/18 p-3">
                <span className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-white/55">
                  <Mail className="h-3.5 w-3.5" />
                  附件格式
                </span>
                <div className="flex flex-wrap gap-2">
                  {emailTypeOptions.map((option) => {
                    const active = formState.emailTypes.includes(option.value)
                    return (
                      <button
                        key={option.value}
                        onClick={() => toggleEmailType(option.value)}
                        className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                          active ? 'border-cyan-300/30 bg-cyan-300/10 text-cyan-100' : 'border-white/10 bg-white/5 text-white/65 hover:bg-white/10'
                        }`}
                      >
                        {option.label}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

          </div>

          {statusData.error && (
            <div className="rounded-[1.25rem] border border-rose-300/20 bg-rose-300/10 px-4 py-3 text-sm text-rose-100">
              {statusData.error}
            </div>
          )}

          <button
            onClick={() => void handleStartJob()}
            disabled={statusData.isSubmitting}
            className="mt-auto flex w-full items-center justify-center gap-2 rounded-[1.5rem] bg-gradient-to-b from-blue-500 to-blue-700 px-4 py-3 text-sm font-bold tracking-[0.2em] text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {statusData.isSubmitting ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/25 border-t-white" />
                安全通道传输中...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                启动智能解析
              </>
            )}
          </button>
        </div>
      </div>
    </GlassEffect>
  )
}
