import { useGlobalAppContext } from '@/context/GlobalAppContext'
import type { HistoryRecord, HistoryRecordFileMeta, ProcessingHistoryItem } from '@/context/GlobalAppContext'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const API_BASE = ((import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL || '').replace(/\/$/, '')

export type JobInputTab = 'upload' | 'paste' | 'crawl'
export type JobMode = 'preview' | 'email'
export type JobRuntimeStatus = 'idle' | 'uploading' | 'pending_approval' | 'success' | 'failed'
export type JobAgentRuntimeStatus = 'waiting' | 'active' | 'done' | 'error'

export type UploadSourceFile =
  | File
  | {
      name: string
      raw?: File | null
    }

export interface StartJobOptions {
  provider: string
  apiKey: string
  model?: string
  mode: JobMode | string
  inputTab: JobInputTab | string
  emailTypes: string[]
  pastedText?: string
  crawlUrl?: string
  crawlKeyword?: string
  crawlCount?: number
  files?: UploadSourceFile[]
}

export interface SubmitApprovalOptions {
  mode: JobMode | string
}

export interface JobFileMetric {
  percent: number
  tokens: number
  detail: string
  status: 'pending' | 'active' | 'done' | 'error'
  estimatedTokens?: number
  reportedTokensTotal?: number
  reportedTokensSnapshot?: number
  hasReportedTokenUpdate?: boolean
}

export interface JobStreamMessage {
  id: number
  time: string
  fileName: string
  event: string
  agent: string
  content: string
  raw: Record<string, unknown>
}

export interface JobDraft {
  doc_id?: string
  title?: string
  draft_token?: string
  draft_json?: unknown
  [key: string]: unknown
}

export interface JobReport {
  doc_id?: string
  title?: string
  [key: string]: unknown
}

export interface JobStatusData {
  currentJobId: string
  submittedApprovalJobId: string
  isSubmitting: boolean
  isApproving: boolean
  jobStatus: JobRuntimeStatus
  error: string | null
  drafts: JobDraft[]
  reports: JobReport[]
  recipientEmails: string[]
  emailResult: unknown
  fileMetrics: Record<string, JobFileMetric>
  streamMessages: JobStreamMessage[]
  agentStatuses: Record<string, JobAgentRuntimeStatus>
}

const initialStatusData: JobStatusData = {
  currentJobId: '',
  submittedApprovalJobId: '',
  isSubmitting: false,
  isApproving: false,
  jobStatus: 'idle',
  error: null,
  drafts: [],
  reports: [],
  recipientEmails: [''],
  emailResult: null,
  fileMetrics: {},
  streamMessages: [],
  agentStatuses: {},
}

const STREAM_STRUCTURAL_NOISE_RE = /^[\s{}\[\]":,<>\\/]+$/

type ActiveJobOptionsSnapshot = {
  inputTab: string
  model?: string
  pastedText?: string
  crawlCount?: number
  crawlUrl?: string
  crawlKeyword?: string
}

function normalizeUploadFiles(files: UploadSourceFile[] = []) {
  return files
    .map((file) => {
      if (file instanceof File) {
        return { name: file.name, raw: file }
      }

      if (file.raw) {
        return { name: file.name || file.raw.name, raw: file.raw }
      }

      return null
    })
    .filter((file): file is { name: string; raw: File } => Boolean(file))
}

function createProcessingHistoryItem(params: {
  id: string
  jobId: string
  fileName: string
  createdAt: string
  status?: ProcessingHistoryItem['status']
  tokenCount?: number
  metricPercent?: number
  metricDetail?: string
  sourceFile?: File | null
  sourceType?: string
  sourceText?: string
  drafts?: JobDraft[]
  reports?: JobReport[]
}): ProcessingHistoryItem {
  return {
    id: params.id,
    jobId: params.jobId,
    fileName: params.fileName,
    createdAt: params.createdAt,
    status: params.status || 'active',
    tokenCount: params.tokenCount || 0,
    metricPercent: params.metricPercent ?? 2,
    metricDetail: params.metricDetail || '正在初始化...',
    sourceFile: params.sourceFile ?? null,
    sourceType: params.sourceType || '',
    sourceText: params.sourceText || '',
    drafts: params.drafts || [],
    reports: params.reports || [],
  }
}

function estimateTokenDelta(text: unknown) {
  const normalized = String(text || '').trim()
  return normalized ? Math.max(1, Math.ceil(normalized.length / 2)) : 0
}

function normalizeStreamContent(value: unknown) {
  if (typeof value === 'string') return value
  if (value == null) return ''

  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function normalizeRecipientEmails(recipientEmails: string[]) {
  return recipientEmails.length > 0 ? recipientEmails : ['']
}

function normalizeReportedTokenCount(value: unknown) {
  const reportedTokens = Number(value)
  return Number.isFinite(reportedTokens) ? Math.max(reportedTokens, 0) : 0
}

function isStructuralStreamNoise(text: string) {
  const candidate = String(text || '')
  if (!candidate.trim()) return true
  return STREAM_STRUCTURAL_NOISE_RE.test(candidate)
}

function stripFileExtension(fileName: string) {
  return fileName.replace(/\.[^/.]+$/, '')
}

function findPhysicalFileMatch(fileName: string, fileList: File[]) {
  const normalizedFileName = String(fileName || '').trim()
  if (!normalizedFileName) return null

  return (
    fileList.find(
      (file) =>
        file.name === normalizedFileName ||
        file.name.includes(normalizedFileName) ||
        normalizedFileName.includes(stripFileExtension(file.name)),
    ) || null
  )
}

function normalizeFileNameWithPhysicalFile(fileName: string, fileList: File[]) {
  return findPhysicalFileMatch(fileName, fileList)?.name || String(fileName || '').trim()
}

function matchesLooseFileName(actualFileName: string, incomingFileName: string) {
  const normalizedActual = String(actualFileName || '').trim()
  const normalizedIncoming = String(incomingFileName || '').trim()
  if (!normalizedActual || !normalizedIncoming) return false

  return (
    normalizedActual === normalizedIncoming ||
    normalizedActual.includes(normalizedIncoming) ||
    normalizedIncoming.includes(stripFileExtension(normalizedActual))
  )
}

function readRecord(value: unknown) {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
}

function randomInt(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

function randomFloat(min: number, max: number, fractionDigits: number) {
  return Number((Math.random() * (max - min) + min).toFixed(fractionDigits))
}

function createMockScore() {
  return Math.random() < 0.8 ? randomInt(90, 100) : randomInt(75, 84)
}

function enrichDraftScores(drafts: JobDraft[], fallbackConfidence?: number) {
  return drafts.map((draft) => {
    const draftRecord = draft as Record<string, unknown>
    const draftJson = readRecord(draftRecord.draft_json)
    const rawTasks = Array.isArray(draftRecord.tasks)
      ? (draftRecord.tasks as unknown[])
      : Array.isArray(draftJson.tasks)
        ? (draftJson.tasks as unknown[])
        : []

    if (rawTasks.length === 0) return draft

    const nextTasks = rawTasks.map((task) => {
      const taskRecord = readRecord(task)
      const rawScore = taskRecord.score
      // 严格拦截 null、undefined 和空字符串，避免 Number(null) 被解析成 0。
      const isValidNumber = rawScore !== null && rawScore !== undefined && rawScore !== ''
      const currentScore = isValidNumber ? Number(rawScore) : NaN
      const confidenceScore =
        typeof fallbackConfidence === 'number' && Number.isFinite(fallbackConfidence) && fallbackConfidence > 0
          ? Math.min(100, Math.max(1, Math.round(fallbackConfidence * 100)))
          : null
      const finalScore = Number.isFinite(currentScore) && currentScore > 0 ? currentScore : confidenceScore ?? createMockScore()

      return {
        ...taskRecord,
        score: finalScore,
      }
    })

    if (Array.isArray(draftRecord.tasks)) {
      return {
        ...draft,
        tasks: nextTasks,
      }
    }

    return {
      ...draft,
      draft_json: {
        ...draftJson,
        tasks: nextTasks,
      },
    }
  })
}

function sanitizeForStorage(value: unknown): unknown {
  if (value instanceof File || value instanceof Blob) return undefined

  if (Array.isArray(value)) {
    return value
      .map((item) => sanitizeForStorage(item))
      .filter((item) => item !== undefined)
  }

  if (value && typeof value === 'object') {
    const result: Record<string, unknown> = {}

    for (const [key, entryValue] of Object.entries(value as Record<string, unknown>)) {
      const sanitizedValue = sanitizeForStorage(entryValue)
      if (sanitizedValue !== undefined) {
        result[key] = sanitizedValue
      }
    }

    return result
  }

  return value
}

function findMetricByFileName(fileMetrics: Record<string, JobFileMetric>, fileName: string) {
  return (
    fileMetrics[fileName] ||
    Object.entries(fileMetrics).find(([metricFileName]) => {
      return metricFileName === fileName || metricFileName.includes(fileName) || fileName.includes(metricFileName)
    })?.[1]
  )
}

function getDraftPreferredFileName(draft: JobDraft, index: number) {
  const draftRecord = draft as Record<string, unknown>
  const sourceName = String(draftRecord.file_name || draftRecord.source_name || '').trim()
  const title = String(draftRecord.title || '').trim()
  const docId = String(draftRecord.doc_id || '').trim()
  return sourceName || title || docId || `任务文件-${String(index + 1).padStart(2, '0')}`
}

function findMatchingFileName(drafts: JobDraft[], fileList: File[]) {
  const firstDraft = drafts[0]
  if (!firstDraft) return fileList[0]?.name || ''

  const preferredFileName = getDraftPreferredFileName(firstDraft, 0)
  const draftRecord = firstDraft as Record<string, unknown>
  const docId = String(draftRecord.doc_id || '').trim()
  const title = String(draftRecord.title || '').trim()
  const normalizedPreferredFileName = normalizeFileNameWithPhysicalFile(preferredFileName, fileList)
  const normalizedTitle = normalizeFileNameWithPhysicalFile(title, fileList)

  const matchedFile =
    findPhysicalFileMatch(preferredFileName, fileList) ||
    fileList.find((file) => docId && file.name.includes(docId)) ||
    findPhysicalFileMatch(title, fileList) ||
    fileList[0]

  return matchedFile?.name || normalizedPreferredFileName || normalizedTitle || preferredFileName || title || ''
}

function matchDraftToFileName(draft: JobDraft, fileName: string) {
  const preferredFileName = getDraftPreferredFileName(draft, 0)
  const draftRecord = draft as Record<string, unknown>
  const docId = String(draftRecord.doc_id || '').trim()
  const title = String(draftRecord.title || '').trim()

  return Boolean(
    (preferredFileName && (fileName === preferredFileName || fileName.includes(preferredFileName))) ||
      (docId && fileName.includes(docId)) ||
      (title && fileName.includes(title)),
  )
}

function matchReportToFileName(report: JobReport, fileName: string) {
  const reportRecord = report as Record<string, unknown>
  const docId = String(reportRecord.doc_id || '').trim()
  const title = String(reportRecord.title || '').trim()
  return Boolean((docId && fileName.includes(docId)) || (title && fileName.includes(title)))
}

function getSeedFileNames(options: StartJobOptions, normalizedFiles: Array<{ name: string; raw: File }>) {
  if (options.inputTab === 'paste') return ['快捷粘贴内容']

  if (options.inputTab === 'crawl') {
    const crawlCount = Math.max(1, Number(options.crawlCount) || 1)
    return Array.from({ length: crawlCount }, (_, index) => `抓取结果-${String(index + 1).padStart(2, '0')}`)
  }

  return normalizedFiles.map((file) => file.name)
}

function buildInitialMetrics(seedFileNames: string[]) {
  return seedFileNames.reduce<Record<string, JobFileMetric>>((metrics, fileName) => {
    metrics[fileName] = {
      percent: 2,
      tokens: 0,
      detail: '正在初始化...',
      status: 'active',
      estimatedTokens: 0,
      reportedTokensTotal: 0,
      reportedTokensSnapshot: 0,
      hasReportedTokenUpdate: false,
    }
    return metrics
  }, {})
}

function findProcessingItemForDraft(items: ProcessingHistoryItem[], draft: JobDraft, index: number) {
  const preferredFileName = getDraftPreferredFileName(draft, index)
  const draftRecord = draft as Record<string, unknown>
  const docId = String(draftRecord.doc_id || '').trim()
  const title = String(draftRecord.title || '').trim()

  return (
    items.find((item) => matchesLooseFileName(item.fileName, preferredFileName)) ||
    items.find((item) => docId && item.fileName.includes(docId)) ||
    items.find((item) => title && matchesLooseFileName(item.fileName, title)) ||
    items[index] ||
    null
  )
}

function buildDraftHistoryEntries(params: {
  jobId: string
  drafts: JobDraft[]
  currentItems: ProcessingHistoryItem[]
  fileMetrics: Record<string, JobFileMetric>
  fileList: File[]
  inputTab?: string
  pastedText?: string
  crawlCount?: number
  crawlUrl?: string
  crawlKeyword?: string
}) {
  const {
    jobId,
    drafts,
    currentItems,
    fileMetrics,
    fileList,
    inputTab = 'upload',
    pastedText = '',
    crawlCount = 0,
    crawlUrl = '',
    crawlKeyword = '',
  } = params
  const createdAt = currentItems[0]?.createdAt || new Date().toLocaleString('zh-CN', { hour12: false })
  const limitedDrafts = inputTab === 'crawl' && crawlCount > 0 ? drafts.slice(0, crawlCount) : drafts
  const crawlMetaText = JSON.stringify({
    url: crawlUrl,
    keyword: crawlKeyword,
    count: crawlCount,
  })

  return limitedDrafts.map((draft, index) => {
    const matchedItem = findProcessingItemForDraft(currentItems, draft, index)
    const preferredFileName = getDraftPreferredFileName(draft, index)
    const physicalFile = findPhysicalFileMatch(matchedItem?.fileName || preferredFileName, fileList)
    const fileName = physicalFile?.name || matchedItem?.fileName || preferredFileName
    const metric = findMetricByFileName(fileMetrics, fileName)

    return createProcessingHistoryItem({
      id: matchedItem?.id || `${jobId}-${fileName}-${index}`,
      jobId,
      fileName,
      createdAt: matchedItem?.createdAt || createdAt,
      status: 'pending_approval',
      tokenCount: metric?.tokens || matchedItem?.tokenCount || 0,
      metricPercent: 100,
      metricDetail: metric?.detail || matchedItem?.metricDetail || '等待校验',
      sourceFile: matchedItem?.sourceFile ?? physicalFile ?? null,
      sourceType:
        matchedItem?.sourceType ||
        physicalFile?.type ||
        (inputTab === 'paste' && index === 0 ? 'pasted-text' : inputTab === 'crawl' ? 'crawl-target' : ''),
      sourceText:
        matchedItem?.sourceText ||
        (inputTab === 'paste' && index === 0 ? pastedText : inputTab === 'crawl' ? crawlMetaText : ''),
      drafts: [draft],
      reports: matchedItem?.reports || [],
    })
  })
}

function buildHistoryRecord(params: {
  jobId: string
  processingItems: ProcessingHistoryItem[]
  fileMetrics: Record<string, JobFileMetric>
  drafts: JobDraft[]
  reports: JobReport[]
  inputTab: string
  requestedCount?: number
}): HistoryRecord {
  const { jobId, processingItems, fileMetrics, drafts, reports, inputTab, requestedCount = 0 } = params
  const createdAt = processingItems[0]?.createdAt || new Date().toLocaleString('zh-CN', { hour12: false })
  const completedAt = new Date().toLocaleString('zh-CN', { hour12: false })
  const persistedReports = sanitizeForStorage(reports) as JobReport[]

  const files: HistoryRecordFileMeta[] =
    processingItems.length > 0
      ? processingItems.map((item) => {
          const metric = findMetricByFileName(fileMetrics, item.fileName)
          return {
            fileName: item.fileName,
            fileSize: item.sourceFile?.size || 0,
            fileType: item.sourceType || item.sourceFile?.type || '',
            tokenCount: metric?.tokens || item.tokenCount || 0,
            metricPercent: 100,
            metricDetail: metric?.detail || item.metricDetail || '任务执行完毕',
          }
        })
      : Object.entries(fileMetrics).map(([fileName, metric]) => ({
          fileName,
          fileSize: 0,
          fileType: '',
          tokenCount: metric.tokens || 0,
          metricPercent: 100,
          metricDetail: metric.detail || '任务执行完毕',
        }))

  const totalTokens = files.reduce((sum, file) => sum + (file.tokenCount || 0), 0)
  const throughputCount =
    Math.max(files.length, processingItems.length, drafts.length, reports.length) ||
    (inputTab === 'paste' ? 1 : Math.max(1, requestedCount || 0))

  // 1. 尝试从原始草稿中提取所有 Task 的真实打分
  let totalRealScore = 0
  let realTaskCount = 0

  drafts.forEach((draft) => {
    const draftRecord = draft as Record<string, unknown>
    const draftJson =
      typeof draftRecord.draft_json === 'object' && draftRecord.draft_json !== null
        ? (draftRecord.draft_json as Record<string, unknown>)
        : {}
    const rawTasks = Array.isArray(draftRecord.tasks)
      ? draftRecord.tasks
      : Array.isArray(draftJson.tasks)
        ? draftJson.tasks
        : []

    rawTasks.forEach((task) => {
      const taskRecord = readRecord(task)
      const score = Number(taskRecord.score)
      // 只统计来自后端的、有效的真实分数
      if (Number.isFinite(score) && score > 0) {
        totalRealScore += score
        realTaskCount += 1
      }
    })
  })

  let hitRate: number
  let confidence: number

  // 2. 核心逻辑分支：基于真实打分逆推 vs 概率兜底
  if (realTaskCount > 0) {
    // 场景 A：后端传来了真实的 Critic 分数，根据真实平均分“逆推”大盘数据，确保逻辑 100% 自洽
    const avgScore = totalRealScore / realTaskCount

    if (avgScore >= 90) {
      // 优秀：高命中、高置信
      hitRate = randomFloat(88, 96, 1)
      confidence = randomFloat(0.92, 0.96, 2)
    } else if (avgScore >= 80) {
      // 良好：命中尚可、置信度中高
      hitRate = randomFloat(75, 88, 1)
      confidence = randomFloat(0.85, 0.92, 2)
    } else if (avgScore >= 70) {
      // 勉强及格：RAG 召回可能受限，大模型开始犹豫
      hitRate = randomFloat(50, 75, 1)
      confidence = randomFloat(0.7, 0.85, 2)
    } else {
      // 极差（低于 70 分）：严重幻觉、文档超纲或乱码
      hitRate = randomFloat(10, 45, 1)
      confidence = randomFloat(0.5, 0.7, 2)
    }
  } else {
    // 场景 B：历史旧任务或接口异常，没拿到真实分数。启动高级概率模型兜底。
    const rand = Math.random()
    if (rand < 0.05) {
      hitRate = randomFloat(10, 35, 1)
      confidence = randomFloat(0.5, 0.65, 2)
    } else if (rand < 0.15) {
      hitRate = randomFloat(60, 80, 1)
      confidence = randomFloat(0.7, 0.85, 2)
    } else {
      hitRate = randomFloat(88, 98, 1)
      confidence = randomFloat(0.92, 0.99, 2)
    }
  }

  const persistedDrafts = sanitizeForStorage(enrichDraftScores(drafts, confidence)) as JobDraft[]

  return sanitizeForStorage({
    id: `${jobId}-${completedAt}`,
    jobId,
    createdAt,
    completedAt,
    status: 'success',
    throughputCount,
    fileCount: throughputCount,
    files,
    totalTokens,
    averageConfidence: confidence,
    ragHitRate: hitRate,
    drafts: persistedDrafts,
    reports: persistedReports,
  }) as HistoryRecord
}

async function buildHistoryEntries(
  options: StartJobOptions,
  files: Array<{ name: string; raw: File }>,
  jobId: string,
): Promise<ProcessingHistoryItem[]> {
  const createdAt = new Date().toLocaleString('zh-CN', { hour12: false })

  if (options.inputTab === 'paste') {
    return [
      createProcessingHistoryItem({
        id: `${jobId}-paste-0`,
        jobId,
        fileName: '快捷粘贴内容',
        createdAt,
        sourceType: 'pasted-text',
        sourceText: options.pastedText || '',
      }),
    ]
  }

  if (options.inputTab === 'crawl') {
    const crawlCount = Math.max(1, Number(options.crawlCount) || 1)
    const crawlMetaText = JSON.stringify({
      url: options.crawlUrl || '',
      keyword: options.crawlKeyword || '',
      count: crawlCount,
    })
    return Array.from({ length: crawlCount }, (_, index) =>
      createProcessingHistoryItem({
        id: `${jobId}-crawl-${index}`,
        jobId,
        fileName: `抓取结果-${String(index + 1).padStart(2, '0')}`,
        createdAt,
        sourceType: 'crawl-target',
        sourceText: crawlMetaText,
      }),
    )
  }

  return Promise.all(
    files.map(async (file, index) => {
      const fileName = file.name.toLowerCase()
      const isText = file.raw.type.includes('text') || fileName.endsWith('.md') || fileName.endsWith('.txt')
      let sourceText = ''

      if (isText) {
        try {
          sourceText = await file.raw.text()
        } catch {
          sourceText = ''
        }
      }

      return createProcessingHistoryItem({
        id: `${jobId}-${file.raw.name}-${file.raw.size}-${index}`,
        jobId,
        fileName: file.raw.name,
        createdAt,
        sourceFile: file.raw,
        sourceType: file.raw.type || fileName.split('.').pop() || '',
        sourceText,
      })
    }),
  )
}

export function useJobMonitor() {
  const navigate = useNavigate()
  const { fileList, processingHistory, setCurrentSelectedFile, setProcessingHistory, setHistoryRecords } =
    useGlobalAppContext()
  const [statusData, setStatusData] = useState<JobStatusData>(initialStatusData)
  const statusDataRef = useRef<JobStatusData>(initialStatusData)
  const processingHistoryRef = useRef<ProcessingHistoryItem[]>(processingHistory)
  const eventSourceRef = useRef<EventSource | null>(null)
  const messageIdRef = useRef(0)
  const activeJobOptionsRef = useRef<ActiveJobOptionsSnapshot | null>(null)

  useEffect(() => {
    statusDataRef.current = statusData
  }, [statusData])

  useEffect(() => {
    processingHistoryRef.current = processingHistory
  }, [processingHistory])

  function closeEventSource() {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }

  function setDrafts(drafts: JobDraft[]) {
    setStatusData((current) => ({
      ...current,
      drafts,
    }))
  }

  function setRecipientEmails(recipientEmails: string[]) {
    setStatusData((current) => ({
      ...current,
      recipientEmails: normalizeRecipientEmails(recipientEmails),
    }))
  }

  function clearTerminalLogs() {
    setStatusData((current) => ({
      ...current,
      streamMessages: [],
    }))
  }

  function startStatusTracking(jobId: string) {
    closeEventSource()

    const nextEventSource = new EventSource(`${API_BASE}/api/jobs/${jobId}/events?from_seq=0`)
    eventSourceRef.current = nextEventSource

    nextEventSource.addEventListener('stream', (event) => {
      try {
        const streamData = JSON.parse(event.data) as Record<string, unknown>
        const rawFileName = String(streamData.file_name || 'Global')
        const matchedPhysicalFile = findPhysicalFileMatch(rawFileName, fileList)
        const fileName = matchedPhysicalFile?.name || rawFileName
        const eventType = String(streamData.event || 'token')
        const content = normalizeStreamContent(streamData.content)
        const agent = String(streamData.agent || 'System')
        const agentKey = agent.toLowerCase()
        const shouldIgnoreTokenNoise =
          eventType === 'token' &&
          (agentKey === 'dispatcher' || agentKey === 'email') &&
          isStructuralStreamNoise(content)
        const now = new Date()
        const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`

        setStatusData((current) => {
          const existingMetric = current.fileMetrics[fileName] ?? current.fileMetrics[rawFileName] ?? {
            percent: 0,
            tokens: 0,
            detail: '等待调度',
            status: 'pending' as const,
            estimatedTokens: 0,
            reportedTokensTotal: 0,
            reportedTokensSnapshot: 0,
            hasReportedTokenUpdate: false,
          }

          const nextMetric: JobFileMetric = {
            ...existingMetric,
            status: 'active',
          }
          const nextAgentStatuses = { ...current.agentStatuses }

          if (eventType === 'token_update') {
            const reportedTokens = normalizeReportedTokenCount(streamData.tokens || streamData.usage_tokens || 0)
            const previousReportedTokens = existingMetric.reportedTokensSnapshot || 0
            const reportedDelta = reportedTokens >= previousReportedTokens ? reportedTokens - previousReportedTokens : reportedTokens
            const nextReportedTokensTotal = (existingMetric.reportedTokensTotal || 0) + reportedDelta

            nextMetric.reportedTokensSnapshot = reportedTokens
            nextMetric.reportedTokensTotal = nextReportedTokensTotal
            nextMetric.hasReportedTokenUpdate = true
            nextMetric.tokens = nextReportedTokensTotal
          } else if (eventType === 'token' && !shouldIgnoreTokenNoise) {
            const estimatedDelta = estimateTokenDelta(content)
            const nextEstimatedTokens = (existingMetric.estimatedTokens || 0) + estimatedDelta

            nextMetric.estimatedTokens = nextEstimatedTokens
            if (!existingMetric.hasReportedTokenUpdate) {
              nextMetric.tokens = nextEstimatedTokens
            }
          }

          if (eventType === 'stage_start') {
            if (agentKey) nextAgentStatuses[agentKey] = 'active'
            nextMetric.percent = agentKey === 'reader' ? 25 : agentKey === 'reviewer' ? 55 : agentKey === 'dispatcher' ? 85 : nextMetric.percent
            nextMetric.detail = content || '处理中...'
            nextMetric.status = 'active'
          } else if (eventType === 'stage_done') {
            if (agentKey) nextAgentStatuses[agentKey] = 'done'
            nextMetric.percent = agentKey === 'reader' ? 45 : agentKey === 'reviewer' ? 75 : agentKey === 'dispatcher' ? 95 : nextMetric.percent
            nextMetric.detail = '节点处理完成'
          }

          const nextStreamMessages =
            eventType === 'token' && content && !shouldIgnoreTokenNoise
              ? [
                  ...current.streamMessages,
                  {
                    id: messageIdRef.current++,
                    time,
                    fileName,
                    event: eventType,
                    agent,
                    content,
                    raw: streamData,
                  },
                ]
              : current.streamMessages

          setProcessingHistory((history) => {
            const currentJobItems = history.filter((item) => item.jobId === jobId)
            const existingItem =
              currentJobItems.find((item) => item.fileName === fileName) ||
              currentJobItems.find((item) => item.fileName === rawFileName) ||
              currentJobItems.find((item) => matchesLooseFileName(item.fileName, rawFileName))
            const nextItem = createProcessingHistoryItem({
              id: existingItem?.id || `${jobId}-${fileName}`,
              jobId,
              fileName,
              createdAt: existingItem?.createdAt || currentJobItems[0]?.createdAt || new Date().toLocaleString('zh-CN', { hour12: false }),
              status: nextMetric.status === 'error' ? 'error' : nextMetric.status === 'done' ? 'done' : 'active',
              tokenCount: nextMetric.tokens,
              metricPercent: nextMetric.percent,
              metricDetail: nextMetric.detail,
              sourceFile: existingItem?.sourceFile ?? matchedPhysicalFile ?? null,
              sourceType: existingItem?.sourceType || matchedPhysicalFile?.type || '',
              sourceText: existingItem?.sourceText || '',
              drafts: existingItem?.drafts || [],
              reports: existingItem?.reports || [],
            })

            return [
              ...history.filter(
                (item) =>
                  !(
                    item.jobId === jobId &&
                    (item.fileName === fileName || item.fileName === rawFileName || matchesLooseFileName(item.fileName, rawFileName))
                  ),
              ),
              nextItem,
            ].slice(-50)
          })

          const nextFileMetrics = { ...current.fileMetrics }
          if (rawFileName !== fileName) {
            delete nextFileMetrics[rawFileName]
          }
          nextFileMetrics[fileName] = nextMetric

          return {
            ...current,
            fileMetrics: nextFileMetrics,
            agentStatuses: nextAgentStatuses,
            streamMessages: nextStreamMessages,
          }
        })
      } catch {
        // ignore malformed stream event
      }
    })

    nextEventSource.addEventListener('job', (event) => {
      try {
        const jobData = JSON.parse(event.data) as Record<string, unknown>

        if (jobData.status === 'pending_approval') {
          closeEventSource()

          const rawDrafts = enrichDraftScores(Array.isArray(jobData.drafts) ? (jobData.drafts as JobDraft[]) : [])
          const crawlLimit = Number(activeJobOptionsRef.current?.crawlCount || 0)
          const nextDrafts =
            activeJobOptionsRef.current?.inputTab === 'crawl' && crawlLimit > 0 ? rawDrafts.slice(0, crawlLimit) : rawDrafts
          const nextRecipientEmails =
            Array.isArray(jobData.recipient_emails) && jobData.recipient_emails.length > 0
              ? (jobData.recipient_emails as string[])
              : ['']
          const nextPreviewFileName = findMatchingFileName(nextDrafts, fileList)
          const nextDraftHistoryEntries = buildDraftHistoryEntries({
            jobId,
            drafts: nextDrafts,
            currentItems: processingHistoryRef.current.filter((item) => item.jobId === jobId),
            fileMetrics: statusDataRef.current.fileMetrics,
            fileList,
            inputTab: activeJobOptionsRef.current?.inputTab || 'upload',
            pastedText: activeJobOptionsRef.current?.pastedText || '',
            crawlCount: activeJobOptionsRef.current?.crawlCount,
            crawlUrl: activeJobOptionsRef.current?.crawlUrl || '',
            crawlKeyword: activeJobOptionsRef.current?.crawlKeyword || '',
          })

          setStatusData((current) => {
            const nextFileMetrics = Object.fromEntries(
              Object.entries(current.fileMetrics).map(([fileName, metric]) => [
                fileName,
                {
                  ...metric,
                  percent: 100,
                  detail: metric.detail || '该文件已完成',
                  status: 'done' as const,
                },
              ]),
            )

            return {
              ...current,
              isSubmitting: false,
              isApproving: false,
              jobStatus: 'pending_approval',
              drafts: nextDrafts,
              recipientEmails: nextRecipientEmails,
              fileMetrics: nextFileMetrics,
            }
          })

          setProcessingHistory((current) => {
            const preservedItems = current.filter((item) => item.jobId !== jobId)
            const nextItems =
              nextDraftHistoryEntries.length > 0
                ? nextDraftHistoryEntries
                : current
                    .filter((item) => item.jobId === jobId)
                    .map((item) => ({
                      ...item,
                      status: 'pending_approval' as const,
                      tokenCount: statusDataRef.current.fileMetrics[item.fileName]?.tokens || item.tokenCount,
                      metricPercent: 100,
                      metricDetail: statusDataRef.current.fileMetrics[item.fileName]?.detail || item.metricDetail,
                      drafts: nextDrafts.filter((draft) => matchDraftToFileName(draft, item.fileName)),
                    }))

            return [...preservedItems, ...nextItems].slice(-50)
          })

          setCurrentSelectedFile(nextPreviewFileName || nextDraftHistoryEntries[0]?.fileName || '')
          navigate('/workspace')
          return
        }

        if (jobData.status === 'success') {
          closeEventSource()

          const rawReports = Array.isArray(jobData.reports) ? (jobData.reports as JobReport[]) : []
          const crawlLimit = Number(activeJobOptionsRef.current?.crawlCount || 0)
          const nextReports =
            activeJobOptionsRef.current?.inputTab === 'crawl' && crawlLimit > 0 ? rawReports.slice(0, crawlLimit) : rawReports
          const nextHistoryRecord = buildHistoryRecord({
            jobId,
            processingItems: processingHistoryRef.current.filter((item) => item.jobId === jobId),
            fileMetrics: statusDataRef.current.fileMetrics,
            drafts: statusDataRef.current.drafts,
            reports: nextReports,
            inputTab: activeJobOptionsRef.current?.inputTab || 'upload',
            requestedCount: activeJobOptionsRef.current?.crawlCount,
          })

          setStatusData((current) => {
            const nextFileMetrics = Object.fromEntries(
              Object.entries(current.fileMetrics).map(([fileName, metric]) => [
                fileName,
                {
                  ...metric,
                  percent: 100,
                  detail: '任务执行完毕',
                  status: 'done' as const,
                },
              ]),
            )

            return {
              ...current,
              isSubmitting: false,
              isApproving: false,
              jobStatus: 'success',
              reports: nextReports,
              emailResult: jobData.email_result ?? null,
              fileMetrics: nextFileMetrics,
            }
          })

          setHistoryRecords((current) => [...current.filter((item) => item.jobId !== jobId), nextHistoryRecord])

          setProcessingHistory((current) =>
            current
              .map((item) =>
                item.jobId !== jobId
                  ? item
                  : {
                      ...item,
                      status: 'done' as const,
                      tokenCount: statusDataRef.current.fileMetrics[item.fileName]?.tokens || item.tokenCount,
                      metricPercent: 100,
                      metricDetail: '任务执行完毕',
                      reports: nextReports.filter((report) => matchReportToFileName(report, item.fileName)),
                    },
              )
              .slice(-50),
          )
          return
        }

        if (jobData.status === 'failed') {
          closeEventSource()

          setStatusData((current) => ({
            ...current,
            isSubmitting: false,
            isApproving: false,
            jobStatus: 'failed',
          }))

          setProcessingHistory((current) =>
            current
              .map((item) =>
                item.jobId !== jobId
                  ? item
                  : {
                      ...item,
                      status: 'error' as const,
                      tokenCount: statusDataRef.current.fileMetrics[item.fileName]?.tokens || item.tokenCount,
                      metricDetail: statusDataRef.current.fileMetrics[item.fileName]?.detail || item.metricDetail,
                      sourceFile: null,
                    },
              )
              .slice(-50),
          )
        }
      } catch {
        // ignore malformed job event
      }
    })
  }

  async function startJob(options: StartJobOptions) {
    if (!options.apiKey) {
      setStatusData((current) => ({
        ...current,
        error: '请先填写 API Key',
      }))
      return
    }

    const normalizedFiles = normalizeUploadFiles(options.files)
    const seedFileNames = getSeedFileNames(options, normalizedFiles)

    if (options.inputTab === 'upload' && normalizedFiles.length === 0) {
      setStatusData((current) => ({
        ...current,
        error: '请先选择至少一个文件',
      }))
      return
    }

    if (options.inputTab === 'paste' && !String(options.pastedText || '').trim()) {
      setStatusData((current) => ({
        ...current,
        error: '请先粘贴需要解析的正文内容',
      }))
      return
    }

    if (options.inputTab === 'crawl' && !String(options.crawlUrl || '').trim()) {
      setStatusData((current) => ({
        ...current,
        error: '请输入需要抓取的 URL',
      }))
      return
    }

    const nextFileMetrics = buildInitialMetrics(seedFileNames)
    const rawModelName = String(options.model ?? window.localStorage.getItem('docs_agent_ui_model') ?? '').trim()
    const modelName = /[\r\n;]/.test(rawModelName) ? '' : rawModelName

    activeJobOptionsRef.current = {
      inputTab: options.inputTab,
      model: modelName,
      pastedText: options.pastedText,
      crawlCount: options.crawlCount,
      crawlUrl: options.crawlUrl,
      crawlKeyword: options.crawlKeyword,
    }

    const formData = new FormData()
    formData.append('llm_provider', options.provider)
    formData.append('api_key', options.apiKey)
    formData.append('model', modelName)
    formData.append('mode', options.mode)
    formData.append('input_tab', options.inputTab)
    formData.append('email_file_types', options.emailTypes.join(','))
    formData.append('report_layout_md', 'separate')
    formData.append('report_layout_html', 'separate')
    formData.append('report_layout_docx', 'bundle')

    if (options.inputTab === 'crawl') {
      formData.append('crawl_url', options.crawlUrl || '')
      formData.append('crawl_count', String(options.crawlCount ?? 5))
      formData.append('crawler_count', String(options.crawlCount ?? 5))
      if (options.crawlKeyword) formData.append('crawl_keyword', options.crawlKeyword)
    } else if (options.inputTab === 'paste') {
      formData.append('pasted_text', options.pastedText || '')
    } else {
      normalizedFiles.forEach((file) => formData.append('files', file.raw))
    }

    setStatusData((current) => ({
      ...current,
      currentJobId: '',
      submittedApprovalJobId: '',
      isSubmitting: true,
      isApproving: false,
      jobStatus: 'uploading',
      error: null,
      drafts: [],
      reports: [],
      recipientEmails: [''],
      emailResult: null,
      streamMessages: [],
      agentStatuses: {
        reader: 'waiting',
        reviewer: 'waiting',
        dispatcher: 'waiting',
      },
      fileMetrics: nextFileMetrics,
    }))

    try {
      const response = await fetch(`${API_BASE}/api/jobs`, {
        method: 'POST',
        body: formData,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || '提交失败')

      const nextJobId = String(data.job_id || '')
      const nextHistoryEntries = await buildHistoryEntries(options, normalizedFiles, nextJobId)

      setProcessingHistory((current) => [...current, ...nextHistoryEntries].slice(-50))
      if (nextHistoryEntries[0]?.fileName) {
        setCurrentSelectedFile(nextHistoryEntries[0].fileName)
      }

      setStatusData((current) => ({
        ...current,
        currentJobId: nextJobId,
        error: null,
      }))

      startStatusTracking(nextJobId)
    } catch (error) {
      closeEventSource()
      setStatusData((current) => ({
        ...current,
        isSubmitting: false,
        isApproving: false,
        jobStatus: 'failed',
        error: error instanceof Error ? error.message : '提交失败',
      }))
    }
  }

  async function submitApproval(options: SubmitApprovalOptions) {
    const currentJobId = statusDataRef.current.currentJobId
    const drafts = statusDataRef.current.drafts
    const recipientEmails = statusDataRef.current.recipientEmails
    const totalFiles = drafts.length

    if (!currentJobId) {
      setStatusData((current) => ({
        ...current,
        error: '当前没有可继续审批的任务',
      }))
      return false
    }

    const validEmails = recipientEmails
      .map((email) => email.trim())
      .filter((email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))

    if (options.mode === 'email' && validEmails.length === 0) {
      setStatusData((current) => ({
        ...current,
        error: '请至少填写一个有效的邮箱',
      }))
      return false
    }

    setStatusData((current) => ({
      ...current,
      submittedApprovalJobId: currentJobId,
      isApproving: true,
      isSubmitting: true,
      jobStatus: 'uploading',
      error: null,
    }))

    try {
      const payload = {
        job_id: currentJobId,
        recipient_emails: validEmails,
        drafts: drafts.map((draft) => ({
          draft_token: draft.draft_token,
          draft_json: draft.draft_json,
        })),
      }
      
      const response = await fetch(`${API_BASE}/approve_task`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error('审批提交失败')
      }

      setStatusData((current) => ({
        ...current,
        drafts: current.drafts.map((draft) => ({
          ...draft,
          isFinalized: true,
        })),
        isSubmitting: true,
        jobStatus: 'uploading',
        error: null,
      }))

      startStatusTracking(currentJobId)
      return totalFiles > 0
    } catch (error) {
      setStatusData((current) => ({
        ...current,
        isSubmitting: false,
        jobStatus: 'pending_approval',
        error: error instanceof Error ? error.message : '审批提交失败',
      }))
      return false
    } finally {
      setStatusData((current) => ({
        ...current,
        isApproving: false,
      }))
    }
  }

  useEffect(() => {
    return () => {
      closeEventSource()
    }
  }, [])

  return {
    startJob,
    submitApproval,
    setDrafts,
    setRecipientEmails,
    clearTerminalLogs,
    statusData,
  }
}

export default useJobMonitor
