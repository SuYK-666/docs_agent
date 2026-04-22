import type { JobStatusData, JobStreamMessage } from '@/hooks/useJobMonitor'
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'

export interface ThinkingConsoleHandle {
  clearLogs: () => void
}

interface ThinkingConsoleProps {
  logs: JobStreamMessage[]
  jobStatus: JobStatusData['jobStatus']
  currentJobId?: string
  error?: string | null
  isDesensitized?: boolean
  autoScroll?: boolean
}

type SystemLogType = 'info' | 'success' | 'warning' | 'error'
type StageKey = 'reader' | 'reviewer' | 'dispatcher'

type SystemLog = {
  id: string
  time: string
  agent: string
  content: string
  type: SystemLogType
}

type GroupedStageLogs = Record<StageKey, JobStreamMessage[]>

const stageOrder: StageKey[] = ['reader', 'reviewer', 'dispatcher']

const stageTitleMap: Record<StageKey, string> = {
  reader: 'STAGE 1: READER',
  reviewer: 'STAGE 2: REVIEWER & CRITIC',
  dispatcher: 'STAGE 3: DISPATCHER',
}

const statusMap: Record<
  JobStatusData['jobStatus'],
  { text: string; color: string; spinning: boolean }
> = {
  idle: { text: 'IDLE', color: 'text-slate-500', spinning: false },
  uploading: { text: 'UPLOADING', color: 'text-blue-400 drop-shadow-[0_0_5px_rgba(96,165,250,0.8)]', spinning: true },
  pending_approval: {
    text: 'PENDING_APPROVAL',
    color: 'text-amber-400 drop-shadow-[0_0_5px_rgba(251,191,36,0.8)] animate-pulse',
    spinning: false,
  },
  success: { text: 'SUCCESS', color: 'text-emerald-400 drop-shadow-[0_0_5px_rgba(74,222,128,0.8)]', spinning: false },
  failed: { text: 'FAILED', color: 'text-red-400 drop-shadow-[0_0_5px_rgba(248,113,113,0.8)]', spinning: false },
}

function mapAgentToStage(agent: string): StageKey {
  const normalized = String(agent).toLowerCase()
  if (normalized.includes('review') || normalized.includes('critic')) return 'reviewer'
  if (normalized.includes('dispatch') || normalized.includes('email')) return 'dispatcher'
  return 'reader'
}

function createEmptyStageLogs(): GroupedStageLogs {
  return {
    reader: [],
    reviewer: [],
    dispatcher: [],
  }
}

function nowTimeString() {
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
}

function formatText(text: string, isDesensitized: boolean) {
  if (!isDesensitized || !text) return text

  let safeText = String(text)
  safeText = safeText.replace(/(\d{3})\d{4}(\d{4})/g, '$1****$2')
  safeText = safeText.replace(/(\d{6})\d{8}(\d{4}|\d{3}[Xx])/g, '$1********$2')
  safeText = safeText.replace(
    /\b([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)(@[\w.-]+\.[A-Za-z]{2,})\b/g,
    (_, first, middle, domain) => first + '*'.repeat(String(middle).length) + domain,
  )
  return safeText
}

function getLogColor(type: string) {
  if (type === 'error') return 'text-red-400'
  if (type === 'success') return 'text-emerald-400'
  if (type === 'warning') return 'text-amber-400'
  return 'text-slate-300'
}

function getAgentBadgeMeta(agent: string) {
  const normalized = String(agent).toLowerCase()

  if (normalized === 'reader') return { label: '[REA]', badgeColor: 'text-blue-400', contentColor: 'text-blue-400' }
  if (normalized === 'reviewer') return { label: '[REV]', badgeColor: 'text-purple-400', contentColor: 'text-slate-300' }
  if (normalized === 'critic') return { label: '[CRI]', badgeColor: 'text-amber-400', contentColor: 'text-amber-400' }
  if (normalized === 'dispatcher') return { label: '[DIS]', badgeColor: 'text-emerald-400', contentColor: 'text-emerald-400' }
  if (normalized === 'system') return { label: '[SYSTEM]', badgeColor: 'text-slate-300', contentColor: 'text-slate-300' }
  if (normalized === 'email') return { label: '[MAIL]', badgeColor: 'text-emerald-400', contentColor: 'text-emerald-400' }

  return {
    label: `[${String(agent || 'LOG').slice(0, 6).toUpperCase()}]`,
    badgeColor: 'text-slate-400',
    contentColor: 'text-slate-300',
  }
}

function extractInlinePrefix(content: string) {
  const match = String(content).match(/^\s*(\[[A-Z_]{2,12}\])\s*(.*)$/s)
  if (!match) return null

  return {
    prefix: match[1],
    body: match[2] || '',
  }
}

function getPrefixColor(prefix: string) {
  if (prefix === '[SYSTEM]') return 'text-slate-300'
  if (prefix === '[REA]' || prefix === '[READER]') return 'text-blue-400'
  if (prefix === '[REV]' || prefix === '[REVIEWER]') return 'text-purple-400'
  if (prefix === '[CRI]' || prefix === '[CRITIC]') return 'text-amber-400'
  if (prefix === '[DIS]' || prefix === '[DISPATCHER]' || prefix === '[MAIL]') return 'text-emerald-400'
  if (prefix === '[ERR]' || prefix === '[ERROR]') return 'text-red-400'
  return 'text-slate-400'
}

function parseLogParts(time: string, agent: string, content: string) {
  const inlinePrefix = extractInlinePrefix(content)
  const resolvedLabel = inlinePrefix ? inlinePrefix.prefix : getAgentBadgeMeta(agent).label
  const badgeColor = inlinePrefix ? getPrefixColor(inlinePrefix.prefix) : getAgentBadgeMeta(agent).badgeColor
  const body = inlinePrefix ? inlinePrefix.body : content

  return {
    timeLabel: `[${time}]`,
    label: resolvedLabel,
    badgeColor,
    body,
  }
}

const ThinkingConsole = forwardRef<ThinkingConsoleHandle, ThinkingConsoleProps>(function ThinkingConsole(
  {
    logs,
    jobStatus,
    currentJobId,
    error,
    isDesensitized = false,
    autoScroll = true,
  },
  ref,
) {
  const [systemLogs, setSystemLogs] = useState<SystemLog[]>([])
  const [clearedAfterId, setClearedAfterId] = useState(-1)
  const systemScrollRef = useRef<HTMLDivElement | null>(null)
  const stageScrollRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const previousJobIdRef = useRef('')
  const previousJobStatusRef = useRef<JobStatusData['jobStatus']>('idle')
  const previousErrorRef = useRef<string | null>(null)

  useImperativeHandle(
    ref,
    () => ({
      clearLogs() {
        setSystemLogs([])
        setClearedAfterId(logs.length > 0 ? Math.max(...logs.map((log) => log.id)) : -1)
      },
    }),
    [logs],
  )

  const visibleLogs = useMemo(() => logs.filter((log) => log.id > clearedAfterId), [clearedAfterId, logs])

  const groupedFileLogs = useMemo(() => {
    return visibleLogs.reduce<Record<string, GroupedStageLogs>>((accumulator, log) => {
      if (!log.fileName || log.fileName === 'Global') return accumulator

      if (!accumulator[log.fileName]) {
        accumulator[log.fileName] = createEmptyStageLogs()
      }

      accumulator[log.fileName][mapAgentToStage(log.agent)].push(log)
      return accumulator
    }, {})
  }, [visibleLogs])

  const statusMeta = statusMap[jobStatus]

  const pushSystemLog = (agent: string, content: string, type: SystemLogType) => {
    setSystemLogs((current) => [
      ...current,
      {
        id: `${agent}-${type}-${current.length}-${Date.now()}`,
        time: nowTimeString(),
        agent,
        content,
        type,
      },
    ])
  }

  useEffect(() => {
    if (currentJobId && previousJobIdRef.current !== currentJobId) {
      pushSystemLog('System', `任务创建成功，JobID: ${currentJobId}`, 'success')
      previousJobIdRef.current = currentJobId
    }
  }, [currentJobId])

  useEffect(() => {
    if (previousJobStatusRef.current === jobStatus) return

    if (jobStatus === 'uploading') {
      pushSystemLog('System', '安全通道已建立，开始接收流式处理日志。', 'info')
    }

    if (jobStatus === 'pending_approval') {
      pushSystemLog('System', '系统进入待审批状态，请核验草稿后继续。', 'warning')
    }

    if (jobStatus === 'success') {
      pushSystemLog('System', '任务全部执行完毕，结果已写回工作台。', 'success')
    }

    if (jobStatus === 'failed') {
      pushSystemLog('System', '任务执行失败，请检查接口响应与任务参数。', 'error')
    }

    previousJobStatusRef.current = jobStatus
  }, [jobStatus])

  useEffect(() => {
    if (!error || previousErrorRef.current === error) return
    pushSystemLog('System', error, 'error')
    previousErrorRef.current = error
  }, [error])

  useEffect(() => {
    if (!autoScroll || !systemScrollRef.current) return
    systemScrollRef.current.scrollTop = systemScrollRef.current.scrollHeight
  }, [autoScroll, systemLogs])

  useEffect(() => {
    if (!autoScroll) return

    Object.values(stageScrollRefs.current).forEach((element) => {
      if (!element) return
      element.scrollTop = element.scrollHeight
    })
  }, [autoScroll, visibleLogs])

  const renderContent = (content: string, colorClass: string) => {
    const safeText = formatText(content, isDesensitized)
    return (
      <pre className={`min-w-0 flex-1 whitespace-pre-wrap break-all text-[15px] leading-7 ${colorClass}`}>
        {safeText}
      </pre>
    )
  }

  const renderLogLine = (
    time: string,
    agent: string,
    content: string,
    toneClass: string,
    key: string | number,
  ) => {
    const logParts = parseLogParts(time, agent, content)

    return (
      <div key={key} className="mb-3 flex flex-col rounded px-1 py-1 transition-colors hover:bg-slate-800/30">
        <span className="mb-1 block w-full text-[12px] tabular-nums text-slate-500">{logParts.timeLabel}</span>
        <div className="flex min-w-0 items-start gap-2">
          <span className={`shrink-0 font-bold text-[13px] ${logParts.badgeColor}`}>{logParts.label}</span>
          {renderContent(logParts.body, toneClass)}
        </div>
      </div>
    )
  }

  return (
    <div className="terminal-window flex h-full flex-col overflow-hidden rounded-lg border border-slate-700/50 bg-[#02060d] font-mono shadow-inner">
      <div className="z-20 flex shrink-0 items-center justify-between border-b border-slate-700/50 bg-slate-800/80 px-4 py-2 shadow-md">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-red-500/80" />
            <div className="h-2.5 w-2.5 rounded-full bg-yellow-500/80" />
            <div className="h-2.5 w-2.5 rounded-full bg-green-500/80" />
          </div>
          <span className="ml-3 text-[11px] font-bold tracking-wider text-slate-400">
            root@docs-agent-core:~/pipeline_monitor
          </span>
        </div>

        <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest">
          {statusMeta.spinning && <span className="animate-spin text-slate-300">↻</span>}
          <span className={`transition-colors duration-300 ${statusMeta.color}`}>{statusMeta.text}</span>
        </div>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto bg-[#050b14]/50 p-4">
        {systemLogs.length > 0 && (
          <div className="flex h-[150px] shrink-0 flex-col overflow-hidden rounded-lg border border-slate-700/50 bg-[#050b14] shadow-lg">
            <div className="flex items-center gap-2 border-b border-slate-700/50 bg-slate-800/80 px-3 py-2 text-[10px] font-bold text-slate-400">
              <span>System Kernel (全局调度)</span>
            </div>
            <div ref={systemScrollRef} className="flex-1 overflow-y-auto p-2 text-[15px] leading-relaxed">
              {systemLogs.map((log) => renderLogLine(log.time, log.agent, log.content, getLogColor(log.type), log.id))}
            </div>
          </div>
        )}

        {Object.entries(groupedFileLogs).map(([fileName, stages]) => {
          const isTyping = stageOrder.some((stage) => stages[stage].length > 0)

          return (
            <div key={fileName} className="flex h-[460px] max-h-[90%] shrink-0 flex-col overflow-hidden rounded-lg border border-slate-700/50 bg-[#050b14] shadow-lg">
              <div className="flex shrink-0 items-center justify-between border-b border-blue-900/40 bg-blue-900/20 px-4 py-2 text-[11px] font-bold text-blue-400">
                <div className="flex items-center gap-2">
                  <span>{fileName}</span>
                  {isTyping && <span className="h-1.5 w-1.5 animate-ping rounded-full bg-blue-400" />}
                </div>
                <span className="text-[9px] font-normal tracking-widest text-slate-500">PIPELINE VIEW</span>
              </div>

              <div className="custom-scrollbar-horizontal flex flex-1 overflow-x-auto bg-[#02060d]">
                {stageOrder.map((stage) => (
                  <div
                    key={`${fileName}-${stage}`}
                    className={`flex w-[525px] shrink-0 flex-col ${stage !== 'dispatcher' ? 'border-r border-slate-800/50' : ''} ${
                      stage === 'reviewer' ? 'bg-slate-900/10' : stage === 'dispatcher' ? 'bg-slate-900/20' : ''
                    }`}
                  >
                    <div className="sticky top-0 shrink-0 border-b border-slate-800 bg-slate-900/50 py-1 text-center text-[10px] font-bold tracking-widest text-slate-500">
                      {stageTitleMap[stage]}
                    </div>
                    <div
                      ref={(element) => {
                        stageScrollRefs.current[`${fileName}_${stage}`] = element
                      }}
                      className="flex-1 overflow-y-auto p-2 text-[15px]"
                    >
                      {stages[stage].map((log) => {
                        const agentMeta = getAgentBadgeMeta(log.agent)
                        const contentTone =
                          stage === 'reviewer'
                            ? getLogColor(log.event === 'token' ? 'info' : log.event)
                            : agentMeta.contentColor

                        return renderLogLine(log.time, log.agent, log.content, contentTone, log.id)
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}

        {systemLogs.length === 0 && Object.keys(groupedFileLogs).length === 0 && (
          <div className="flex h-full select-none items-center justify-center gap-2 italic text-slate-600/70">
            <span className="inline-block h-4 w-1.5 animate-pulse bg-slate-600" />
            Waiting for internal server streams to initialize...
          </div>
        )}
      </div>
    </div>
  )
})

export default ThinkingConsole
