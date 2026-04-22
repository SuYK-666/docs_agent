import { useGlobalAppContext } from '@/context/GlobalAppContext'
import type { HistoryRecord } from '@/context/GlobalAppContext'
import type { ProcessingHistoryItem } from '@/context/GlobalAppContext'
import { GlassEffect, GlassFilter } from '@/components/ui/liquid-glass'
import type { JobDraft, JobReport, JobStatusData, SubmitApprovalOptions } from '@/hooks/useJobMonitor'
import { ChevronLeft, ChevronRight, Download, FileSearch, FolderOpen, PanelsTopLeft } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

interface WorkspacePageProps {
  statusData: JobStatusData
  submitApproval: (options: SubmitApprovalOptions) => Promise<boolean>
  setDrafts: (drafts: JobDraft[]) => void
  setRecipientEmails: (recipientEmails: string[]) => void
}

type PreviewTab = 'source' | 'verification' | 'analysis'
type SourcePreviewType = 'image' | 'pdf' | 'text' | 'docx' | 'crawl' | 'unsupported'
type ReportPreviewType = 'html' | 'pdf' | 'docx' | 'unsupported' | ''

type WorkspaceTask = {
  key: string
  taskId: string
  taskName: string
  content: string
  owner: string
  deadline: string
  score: number
  criticFeedback: string
  raw: Record<string, unknown>
}

type WorkspaceDraft = {
  key: string
  title: string
  docId: string
  sourceName: string
  tasks: WorkspaceTask[]
  raw: JobDraft
}

type WorkspaceHistoryListItem = {
  key: string
  fileName: string
  jobId: string
  createdAt: string
  status: 'active' | 'pending_approval' | 'done' | 'error'
  tokenCount: number
  metricPercent: number
  metricDetail: string
  isArchived: boolean
}

function readRecord(value: unknown) {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
}

function readString(record: Record<string, unknown>, keys: string[], fallback = '') {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return fallback
}

function readNumber(record: Record<string, unknown>, keys: string[], fallback = 98) {
  for (const key of keys) {
    const value = Number(record[key])
    if (!Number.isNaN(value) && Number.isFinite(value)) return value
  }
  return fallback
}

function getDraftTasks(draft: JobDraft) {
  const draftRecord = draft as Record<string, unknown>
  if (Array.isArray(draftRecord.tasks)) return draftRecord.tasks as unknown[]

  const draftJson = readRecord(draftRecord.draft_json)
  if (Array.isArray(draftJson.tasks)) return draftJson.tasks as unknown[]

  return []
}

function getDraftKey(draft: JobDraft, index: number) {
  const draftRecord = draft as Record<string, unknown>
  return readString(draftRecord, ['doc_id', 'title', 'name'], `draft-${index + 1}`)
}

function buildWorkspaceDrafts(drafts: JobDraft[]): WorkspaceDraft[] {
  return drafts.map((draft, draftIndex) => {
    const draftRecord = draft as Record<string, unknown>
    const docId = readString(draftRecord, ['doc_id', 'docId'], `draft-${draftIndex + 1}`)
    const title = readString(draftRecord, ['title', 'name'], `待审批草稿 ${draftIndex + 1}`)
    const sourceName = readString(draftRecord, ['file_name', 'source_name', 'title'], title)

    const tasks = getDraftTasks(draft).map((task, taskIndex) => {
      const taskRecord = readRecord(task)
      return {
        key: `${docId || title}-${taskIndex}`,
        taskId: readString(taskRecord, ['task_id', 'taskId'], String(taskIndex + 1)),
        taskName: readString(taskRecord, ['task_name', 'taskName', 'name'], `待校验要素 ${taskIndex + 1}`),
        content: readString(taskRecord, ['content', 'summary', 'description'], '等待进一步补充任务描述。'),
        owner: readString(taskRecord, ['owner', 'assignee'], ''),
        deadline: readString(taskRecord, ['deadline_display', 'deadline', 'due_date'], ''),
        score: readNumber(taskRecord, ['score', 'confidence'], 0),
        criticFeedback: readString(
          taskRecord,
          ['critic_feedback', 'criticFeedback'],
          '关键字段已完成交叉核验，当前未发现高风险冲突，可继续复核后下发。',
        ),
        raw: taskRecord,
      }
    })

    return {
      key: getDraftKey(draft, draftIndex),
      title,
      docId,
      sourceName,
      tasks,
      raw: draft,
    }
  })
}

function buildUpdatedDrafts(
  drafts: JobDraft[],
  draftKey: string,
  taskKey: string,
  field: 'owner' | 'deadline',
  value: string,
) {
  return drafts.map((draft, draftIndex) => {
    const workspaceDraft = buildWorkspaceDrafts([draft])[0]
    if (!workspaceDraft || getDraftKey(draft, draftIndex) !== draftKey) return draft

    const nextTasks = workspaceDraft.tasks.map((task) => {
      const nextOwner = task.key === taskKey && field === 'owner' ? value : task.owner
      const nextDeadline = task.key === taskKey && field === 'deadline' ? value : task.deadline

      return {
        ...task.raw,
        task_id: task.taskId,
        task_name: task.taskName,
        content: task.content,
        owner: nextOwner,
        assignee: nextOwner,
        deadline_display: nextDeadline,
        deadline: nextDeadline,
        score: task.score,
        critic_feedback: task.criticFeedback,
      }
    })

    const draftRecord = draft as Record<string, unknown>
    const draftJson = readRecord(draftRecord.draft_json)

    if (Object.keys(draftJson).length > 0) {
      return {
        ...draft,
        draft_json: {
          ...draftJson,
          tasks: nextTasks,
        },
      }
    }

    return {
      ...draft,
      tasks: nextTasks,
    }
  })
}

function matchReportToFileName(report: JobReport, fileName: string) {
  const reportRecord = report as Record<string, unknown>
  const docId = String(reportRecord.doc_id || '')
  const title = String(reportRecord.title || '')
  if (docId && fileName.includes(docId)) return true
  if (title && fileName.includes(title)) return true
  return false
}

function getFileStatusText(status?: string) {
  if (status === 'active') return '处理中'
  if (status === 'done') return '已完成'
  if (status === 'error') return '异常'
  if (status === 'pending_approval') return '待校验'
  return '待处理'
}

function getReportLabel(reportType: ReportPreviewType) {
  if (reportType === 'html') return 'HTML'
  if (reportType === 'pdf') return 'PDF'
  if (reportType === 'docx') return 'DOCX'
  return 'Artifact'
}

function findSelectedHistoryRecord(history: ProcessingHistoryItem[], currentSelectedFile: string) {
  if (!currentSelectedFile) return null
  return history.find((item) => item.fileName === currentSelectedFile) || null
}

function resolveDraftFileName(
  draft: WorkspaceDraft | null,
  history: ProcessingHistoryItem[],
  fileList: File[],
) {
  if (!draft) return ''

  const candidates = [draft.sourceName, draft.docId, draft.title].filter(Boolean)

  for (const candidate of candidates) {
    const historyMatch =
      history.find((item) => item.fileName === candidate) ||
      history.find((item) => candidate && item.fileName.includes(candidate)) ||
      history.find((item) => candidate && candidate.includes(item.fileName))

    if (historyMatch) return historyMatch.fileName

    const fileMatch =
      fileList.find((file) => file.name === candidate) ||
      fileList.find((file) => candidate && file.name.includes(candidate)) ||
      fileList.find((file) => candidate && candidate.includes(file.name))

    if (fileMatch) return fileMatch.name
  }

  return draft.sourceName || draft.title || draft.docId || ''
}

function getSourceFileDisplayName(selectedHistoryItem: ProcessingHistoryItem | null, liveSelectedFile: File | null) {
  return selectedHistoryItem?.fileName || liveSelectedFile?.name || '未选择文件'
}

function parseCrawlerMeta(sourceText: string) {
  try {
    const parsed = JSON.parse(sourceText) as Record<string, unknown>
    return {
      url: typeof parsed.url === 'string' ? parsed.url : '',
      keyword: typeof parsed.keyword === 'string' ? parsed.keyword : '',
      count: Number(parsed.count) || 0,
    }
  } catch {
    return {
      url: '',
      keyword: '',
      count: 0,
    }
  }
}

function findSelectedArchiveRecord(historyRecords: HistoryRecord[], currentSelectedFile: string) {
  if (!currentSelectedFile) return null

  return (
    historyRecords.find((record) => record.jobId === currentSelectedFile) ||
    historyRecords.find((record) => record.files.some((file) => file.fileName === currentSelectedFile)) ||
    null
  )
}

function buildWorkspaceHistoryItems(
  processingHistory: ProcessingHistoryItem[],
  historyRecords: HistoryRecord[],
): WorkspaceHistoryListItem[] {
  const liveItems = [...processingHistory]
    .reverse()
    .map<WorkspaceHistoryListItem>((item) => ({
      key: item.id,
      fileName: item.fileName,
      jobId: item.jobId,
      createdAt: item.createdAt,
      status: item.status,
      tokenCount: item.tokenCount,
      metricPercent: item.metricPercent,
      metricDetail: item.metricDetail,
      isArchived: false,
    }))

  const liveJobIds = new Set(processingHistory.map((item) => item.jobId))
  const archivedItems = [...historyRecords]
    .reverse()
    .filter((record) => !liveJobIds.has(record.jobId))
    .map<WorkspaceHistoryListItem>((record) => ({
      key: `archive-${record.jobId}`,
      fileName: record.files[0]?.fileName || record.jobId,
      jobId: record.jobId,
      createdAt: record.completedAt || record.createdAt,
      status: record.status === 'success' ? 'done' : 'error',
      tokenCount: record.totalTokens,
      metricPercent: 100,
      metricDetail: `已归档 · ${record.fileCount} 份文件`,
      isArchived: true,
    }))

  return [...liveItems, ...archivedItems]
}

export default function WorkspacePage({
  statusData,
  submitApproval,
  setDrafts,
  setRecipientEmails,
}: WorkspacePageProps) {
  const { fileList, formState, processingHistory, historyRecords, currentSelectedFile, setCurrentSelectedFile } =
    useGlobalAppContext()
  const [activePreviewTab, setActivePreviewTab] = useState<PreviewTab>('source')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewType, setPreviewType] = useState<SourcePreviewType>('unsupported')
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewText, setPreviewText] = useState('')
  const [reportPreviewLoading, setReportPreviewLoading] = useState(false)
  const [reportPreviewType, setReportPreviewType] = useState<ReportPreviewType>('')
  const [reportPreviewUrl, setReportPreviewUrl] = useState('')
  const [approvalSubmitted, setApprovalSubmitted] = useState(false)
  const sourceObjectUrlRef = useRef('')
  const sourceDocxTimerRef = useRef<number | null>(null)

  const isApprovalStage = statusData.jobStatus === 'pending_approval'
  const hasSelectedFile = Boolean(currentSelectedFile)
  const historyItems = useMemo(
    () => buildWorkspaceHistoryItems(processingHistory, historyRecords),
    [historyRecords, processingHistory],
  )
  const selectedHistoryItem = useMemo(
    () => findSelectedHistoryRecord(processingHistory, currentSelectedFile),
    [currentSelectedFile, processingHistory],
  )
  const selectedArchiveRecord = useMemo(
    () => findSelectedArchiveRecord(historyRecords, currentSelectedFile),
    [currentSelectedFile, historyRecords],
  )
  const isCurrentLiveJob = Boolean(
    selectedHistoryItem && statusData.currentJobId && selectedHistoryItem.jobId === statusData.currentJobId,
  )
  const isArchivedSelection = Boolean(selectedArchiveRecord) && !isCurrentLiveJob

  const activeDrafts = useMemo(() => {
    if (isApprovalStage && isCurrentLiveJob) {
      return statusData.drafts
    }

    if (selectedHistoryItem?.drafts.length) return selectedHistoryItem.drafts
    if (isCurrentLiveJob) return statusData.drafts
    if (selectedArchiveRecord?.drafts.length) return selectedArchiveRecord.drafts
    return []
  }, [isApprovalStage, isCurrentLiveJob, selectedArchiveRecord, selectedHistoryItem, statusData.drafts])

  const activeReports = useMemo(() => {
    if (selectedHistoryItem?.reports.length) return selectedHistoryItem.reports
    if (isCurrentLiveJob) return statusData.reports
    if (selectedArchiveRecord?.reports.length) return selectedArchiveRecord.reports
    return []
  }, [isCurrentLiveJob, selectedArchiveRecord, selectedHistoryItem, statusData.reports])

  const workspaceDrafts = useMemo(() => buildWorkspaceDrafts(activeDrafts), [activeDrafts])

  const selectedDraft = useMemo(() => {
    if (workspaceDrafts.length === 0) return null

    const matched = workspaceDrafts.find((draft) => {
      if (!currentSelectedFile) return false
      return (
        draft.sourceName === currentSelectedFile ||
        (draft.docId && currentSelectedFile.includes(draft.docId)) ||
        (draft.title && currentSelectedFile.includes(draft.title))
      )
    })

    return matched || workspaceDrafts[0]
  }, [currentSelectedFile, workspaceDrafts])

  const selectedDraftIndex = useMemo(() => {
    if (!selectedDraft) return -1
    return workspaceDrafts.findIndex((draft) => draft.key === selectedDraft.key)
  }, [selectedDraft, workspaceDrafts])

  const matchedReport = useMemo(() => {
    if (!currentSelectedFile) return null
    return activeReports.find((report) => matchReportToFileName(report, currentSelectedFile)) || null
  }, [activeReports, currentSelectedFile])

  const liveSelectedFile = useMemo(
    () => fileList.find((file) => currentSelectedFile && file.name === currentSelectedFile) || null,
    [currentSelectedFile, fileList],
  )
  const selectedSourceFile = isArchivedSelection ? null : selectedHistoryItem?.sourceFile ?? liveSelectedFile
  const selectedSourceType = isArchivedSelection ? '' : selectedHistoryItem?.sourceType || selectedSourceFile?.type || ''
  const selectedSourceName = (isArchivedSelection ? '' : selectedHistoryItem?.fileName || selectedSourceFile?.name || '').toLowerCase()
  const crawlerMeta = useMemo(() => parseCrawlerMeta(selectedHistoryItem?.sourceText || ''), [selectedHistoryItem?.sourceText])
  const releasedHistorySource = Boolean(
    selectedHistoryItem &&
      !selectedHistoryItem.sourceFile &&
      !liveSelectedFile &&
      !selectedHistoryItem.sourceText &&
      selectedSourceType !== 'pasted-text' &&
      selectedSourceType !== 'crawl-target',
  )
  const isSourceDocx = Boolean(selectedSourceFile && selectedSourceName.endsWith('.docx'))

  const shouldExpandPreview = !isArchivedSelection && isApprovalStage && activePreviewTab !== 'source'
  const shouldSplitPreview = !isArchivedSelection && isApprovalStage && activePreviewTab !== 'source'
  const sourcePaneVisible = !isArchivedSelection && (activePreviewTab === 'source' || shouldSplitPreview)
  const isVerificationSplit = !isArchivedSelection && isApprovalStage && activePreviewTab === 'verification'
  const isAnalysisSplit = !isArchivedSelection && isApprovalStage && activePreviewTab === 'analysis'

  useEffect(() => {
    if (isArchivedSelection && activePreviewTab === 'source') {
      setActivePreviewTab('verification')
      return
    }

    if (isApprovalStage && !isArchivedSelection) {
      setActivePreviewTab('verification')
    }
  }, [activePreviewTab, isApprovalStage, isArchivedSelection])

  useEffect(() => {
    return () => {
      if (sourceDocxTimerRef.current) {
        window.clearTimeout(sourceDocxTimerRef.current)
      }
      if (sourceObjectUrlRef.current) {
        URL.revokeObjectURL(sourceObjectUrlRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (sourceObjectUrlRef.current) {
      URL.revokeObjectURL(sourceObjectUrlRef.current)
      sourceObjectUrlRef.current = ''
    }

    setPreviewUrl('')
    setPreviewText('')
    setPreviewLoading(false)

    const sourceFile = selectedSourceFile
    const sourceText = selectedHistoryItem?.sourceText || ''
    const sourceType = selectedSourceType
    const sourceName = selectedSourceName

    if (isArchivedSelection) {
      setPreviewType('unsupported')
      const container = document.getElementById('docx-preview-container')
      if (container) container.innerHTML = ''
      return
    }

    if (!selectedHistoryItem && !liveSelectedFile) {
      setPreviewType('unsupported')
      const container = document.getElementById('docx-preview-container')
      if (container) container.innerHTML = ''
      return
    }

    if (releasedHistorySource) {
      setPreviewType('unsupported')
      const container = document.getElementById('docx-preview-container')
      if (container) container.innerHTML = ''
      return
    }

    if (sourceFile) {
      if (sourceFile.type.startsWith('image/')) {
        const objectUrl = URL.createObjectURL(sourceFile)
        sourceObjectUrlRef.current = objectUrl
        setPreviewType('image')
        setPreviewUrl(objectUrl)
        return
      }

      if (sourceFile.type === 'application/pdf' || sourceName.endsWith('.pdf')) {
        const objectUrl = URL.createObjectURL(sourceFile)
        sourceObjectUrlRef.current = objectUrl
        setPreviewType('pdf')
        setPreviewUrl(objectUrl)
        return
      }

      if (sourceFile.type.includes('text') || sourceName.endsWith('.md') || sourceName.endsWith('.txt')) {
        setPreviewType('text')
        setPreviewText(sourceText)
        return
      }

      if (sourceName.endsWith('.docx')) {
        setPreviewType('docx')

        if (!sourcePaneVisible) return

        const container = document.getElementById('docx-preview-container')
        if (!container) return

        container.innerHTML = ''
        setPreviewLoading(true)

        void import('docx-preview')
          .then(({ renderAsync }) => renderAsync(sourceFile, container, undefined, { inWrapper: true }))
          .then(() => setPreviewLoading(false))
          .catch(() => {
            setPreviewType('unsupported')
            setPreviewLoading(false)
          })
        return
      }
    }

    if (sourceType === 'crawl-target') {
      setPreviewType('crawl')
      return
    }

    if (sourceType === 'pasted-text' || sourceText) {
      setPreviewType('text')
      setPreviewText(sourceText)
      return
    }

    if (sourceType.includes('text')) {
      setPreviewType('text')
      setPreviewText('原始文件已归档以节省内存，当前仅保留文本快照。')
      return
    }

    setPreviewType('unsupported')
    const container = document.getElementById('docx-preview-container')
    if (container) container.innerHTML = ''
  }, [
    currentSelectedFile,
    liveSelectedFile,
    releasedHistorySource,
    selectedHistoryItem,
    selectedSourceFile,
    selectedSourceName,
    selectedSourceType,
    sourcePaneVisible,
    isArchivedSelection,
  ])

  useEffect(() => {
    if (!sourcePaneVisible || previewType !== 'docx' || !isSourceDocx || !selectedSourceFile) return

    if (sourceDocxTimerRef.current) {
      window.clearTimeout(sourceDocxTimerRef.current)
    }

    sourceDocxTimerRef.current = window.setTimeout(() => {
      requestAnimationFrame(() => {
        const container = document.getElementById('docx-preview-container')
        if (!container) return

        container.innerHTML = ''
        setPreviewLoading(true)

        void import('docx-preview')
          .then(({ renderAsync }) => renderAsync(selectedSourceFile, container, undefined, { inWrapper: true }))
          .then(() => setPreviewLoading(false))
          .catch(() => {
            setPreviewType('unsupported')
            setPreviewLoading(false)
          })
      })
    }, 100)

    return () => {
      if (sourceDocxTimerRef.current) {
        window.clearTimeout(sourceDocxTimerRef.current)
        sourceDocxTimerRef.current = null
      }
    }
  }, [activePreviewTab, currentSelectedFile, isSourceDocx, previewType, selectedSourceFile, sourcePaneVisible])

  useEffect(() => {
    const container = document.getElementById('report-docx-container')
    if (!container) return

    if (reportPreviewType !== 'docx' || !reportPreviewUrl || activePreviewTab !== 'analysis') {
      container.innerHTML = ''
      return
    }

    setReportPreviewLoading(true)

    void fetch(reportPreviewUrl)
      .then((response) => response.blob())
      .then(async (blob) => {
        container.innerHTML = ''
        const { renderAsync } = await import('docx-preview')
        await renderAsync(blob, container, undefined, { inWrapper: true })
        setReportPreviewLoading(false)
      })
      .catch(() => {
        setReportPreviewType('unsupported')
        setReportPreviewLoading(false)
      })
  }, [activePreviewTab, reportPreviewType, reportPreviewUrl])

  const selectFile = (fileName: string) => {
    setCurrentSelectedFile(fileName)
    setReportPreviewLoading(false)
    setReportPreviewType('')
    setReportPreviewUrl('')
  }

  const updateTaskField = (draftKey: string, taskKey: string, field: 'owner' | 'deadline', value: string) => {
    setDrafts(buildUpdatedDrafts(activeDrafts, draftKey, taskKey, field, value))
  }

  const jumpDraft = (offset: number) => {
    if (selectedDraftIndex < 0) return
    const nextDraft = workspaceDrafts[selectedDraftIndex + offset]
    if (!nextDraft) return
    const nextFileName = resolveDraftFileName(nextDraft, processingHistory, fileList)
    if (!nextFileName) return
    selectFile(nextFileName)
  }

  const updateEmail = (index: number, value: string) => {
    setRecipientEmails(statusData.recipientEmails.map((email, currentIndex) => (currentIndex === index ? value : email)))
  }

  const addEmail = () => {
    setRecipientEmails([...statusData.recipientEmails, ''])
  }

  const removeEmail = (index: number) => {
    const nextEmails = statusData.recipientEmails.filter((_, currentIndex) => currentIndex !== index)
    setRecipientEmails(nextEmails.length > 0 ? nextEmails : [''])
  }

  const previewReport = (url: string, type: ReportPreviewType) => {
    if (!url) return
    setReportPreviewType(type)
    setReportPreviewUrl(url)
    setReportPreviewLoading(type === 'docx')
  }

  const downloadArtifact = (url: string, fileName: string) => {
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const handleSubmitApproval = async () => {
    if (workspaceDrafts.length === 0 || approvalSubmitted) return
    setApprovalSubmitted(false)
    const success = await submitApproval({ mode: formState.mode })
    if (success) {
      setApprovalSubmitted(true)
      setActivePreviewTab('source')
    }
  }

  useEffect(() => {
    if (statusData.jobStatus === 'pending_approval') {
      setApprovalSubmitted(false)
    }
  }, [statusData.currentJobId, statusData.jobStatus])

  const renderSourcePane = (label?: string) => (
    <div className="relative flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-[1.5rem] border border-white/10 bg-black/20">
      {previewLoading && (
        <div className="skeleton-container absolute inset-0 z-20 rounded-[1.5rem] bg-slate-950/92 p-6 backdrop-blur">
          <div className="mb-8 h-5 w-1/4 rounded skeleton-block" />
          <div className="space-y-4">
            <div className="h-2 w-full rounded skeleton-block" />
            <div className="h-2 w-5/6 rounded skeleton-block" />
            <div className="h-2 w-full rounded skeleton-block" />
            <div className="h-2 w-4/5 rounded skeleton-block" />
          </div>
          <div className="mt-8 h-32 w-full rounded skeleton-block" />
        </div>
      )}

      <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-white/8 px-4 py-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-200/70">{label || '原文预览'}</p>
            <p className="truncate text-sm text-white/80">{getSourceFileDisplayName(selectedHistoryItem, liveSelectedFile)}</p>
          </div>
          <span className="shrink-0 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-100">
            Source
          </span>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar p-4">
          {previewType === 'image' && previewUrl && (
            <img src={previewUrl} alt={currentSelectedFile} className="h-full min-h-0 w-full rounded-[1rem] object-contain" />
          )}
          {previewType === 'pdf' && previewUrl && (
            <iframe src={previewUrl} className="h-full min-h-0 w-full rounded-[1rem] border-none bg-white" title="source-pdf-preview" />
          )}
          {previewType === 'text' && (
            <div className="min-h-full rounded-[1rem] bg-slate-950/85 p-5">
              <pre className="whitespace-pre-wrap break-all text-sm leading-7 text-slate-200">
                {previewText || '文本文件内容为空。'}
              </pre>
            </div>
          )}
          {previewType === 'crawl' && (
            <div className="flex min-h-full items-center justify-center">
              <div className="w-full max-w-2xl rounded-[1.5rem] border border-cyan-400/15 bg-slate-950/85 p-6 shadow-[0_18px_50px_rgba(8,15,31,0.35)]">
                <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-cyan-200/70">Crawler Target</p>
                <h3 className="mt-3 text-xl font-semibold text-white">网页抓取目标</h3>

                <div className="mt-5 rounded-[1rem] border border-white/10 bg-black/20 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-white/40">目标 URL</p>
                  {crawlerMeta.url ? (
                    <a
                      href={crawlerMeta.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 block break-all text-sm leading-7 text-cyan-200 underline decoration-cyan-300/40 underline-offset-4 transition hover:text-cyan-100"
                    >
                      {crawlerMeta.url}
                    </a>
                  ) : (
                    <p className="mt-2 text-sm text-white/60">当前未记录抓取目标地址</p>
                  )}
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded-[1rem] border border-white/10 bg-black/20 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-white/40">抓取关键字</p>
                    <p className="mt-2 text-sm text-white/80">{crawlerMeta.keyword || '未设置'}</p>
                  </div>
                  <div className="rounded-[1rem] border border-white/10 bg-black/20 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-white/40">抓取条目数</p>
                    <p className="mt-2 text-sm text-white/80">{crawlerMeta.count || 0} 条</p>
                  </div>
                </div>

                <div className="mt-4 rounded-[1rem] border border-emerald-400/15 bg-emerald-400/8 p-4 text-sm leading-7 text-emerald-100">
                  {selectedHistoryItem?.status === 'done' ? '网页快照已归档，当前展示的是抓取目标与参数摘要。' : '智能体正在提取目标网页正文，请在校验或结果页查看结构化输出。'}
                </div>
              </div>
            </div>
          )}
          <div
            id="docx-preview-container"
            className={`h-full min-h-0 w-full overflow-y-auto custom-scrollbar rounded-[1rem] bg-slate-100 p-4 text-black ${
              previewType === 'docx' ? 'block' : 'hidden'
            }`}
          />
          {previewType === 'unsupported' && !previewLoading && (
            <div className="flex h-full min-h-0 items-center justify-center rounded-[1rem] border border-dashed border-white/10 px-6 text-center text-white/45">
              {releasedHistorySource
                ? '源文件已从内存释放，请查看 AI 校验记录或结果报告。'
                : '原始文件已归档或当前类型暂不支持预览，系统仅保留文本快照、校验结果和报告资源。'}
            </div>
          )}
        </div>
      </div>
    </div>
  )

  const renderVerificationPane = () => {
    if (!selectedDraft) {
      return <div className="flex h-full items-center justify-center text-white/45">暂无校验数据</div>
    }

    const isLastDraft = selectedDraftIndex === workspaceDrafts.length - 1

    return (
      <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[1.5rem] border border-white/10 bg-black/20">
        <div className="border-b border-white/8 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-200/70">校验工作台</p>
              <p className="truncate text-sm text-white/80">{selectedDraft.title}</p>
            </div>
            <span className="shrink-0 rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-amber-100">
              Review
            </span>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar pr-2 p-4">
          <div className="space-y-4">
            {selectedDraft.tasks.map((task) => {
              const isLowScore = task.score < 85

              return (
                <div
                  key={task.key}
                  className={`rounded-[1.25rem] border p-4 transition ${
                    isLowScore ? 'border-amber-500/35 bg-amber-500/10' : 'border-white/8 bg-white/4'
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-white/45">任务 ID #{task.taskId}</p>
                      <h3 className="truncate text-base font-semibold text-white">{task.taskName}</h3>
                    </div>
                    <span
                      className={`shrink-0 rounded-full border px-3 py-1 text-xs font-bold ${
                        isLowScore
                          ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                          : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                      }`}
                    >
                      AI 评估 {task.score}
                    </span>
                  </div>

                  <p className="mt-3 text-sm leading-7 text-white/68">{task.content}</p>

                  <div
                    className={`mt-4 rounded-[1rem] border px-3 py-3 text-sm ${
                      isLowScore ? 'border-amber-500/25 bg-amber-500/8 text-amber-100' : 'border-white/8 bg-white/4 text-white/70'
                    }`}
                  >
                    <p className="text-xs font-bold uppercase tracking-[0.18em]">Critic Agent 质检报告</p>
                    <p className="mt-2 leading-6">{task.criticFeedback}</p>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <label className="grid gap-2">
                      <span className="text-xs uppercase tracking-[0.16em] text-white/45">责任人</span>
                      <input
                        value={task.owner}
                        onChange={(event) => updateTaskField(selectedDraft.key, task.key, 'owner', event.target.value)}
                        className="rounded-[1rem] border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-300/35"
                        placeholder="输入责任人"
                      />
                    </label>

                    <label className="grid gap-2">
                      <span className="text-xs uppercase tracking-[0.16em] text-white/45">截止日期</span>
                      <input
                        value={task.deadline}
                        onChange={(event) => updateTaskField(selectedDraft.key, task.key, 'deadline', event.target.value)}
                        className="rounded-[1rem] border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-300/35"
                        placeholder="输入截止日期"
                      />
                    </label>
                  </div>
                </div>
              )
            })}

            {formState.mode === 'email' && (
              <div className="rounded-[1.25rem] border border-blue-500/20 bg-blue-500/8 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">下发目标邮箱</div>
                <div className="space-y-2">
                  {statusData.recipientEmails.map((email, index) => (
                    <div key={index} className="flex gap-2">
                      <input
                        value={email}
                        onChange={(event) => updateEmail(index, event.target.value)}
                        placeholder="输入接收方邮箱地址..."
                        className="flex-1 rounded-[1rem] border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-300/35"
                      />
                      {index === statusData.recipientEmails.length - 1 && (
                        <button
                          type="button"
                          onClick={addEmail}
                          className="rounded-[1rem] border border-emerald-500/30 bg-emerald-500/10 px-3 text-emerald-200 transition hover:bg-emerald-500/18"
                        >
                          +
                        </button>
                      )}
                      {statusData.recipientEmails.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeEmail(index)}
                          className="rounded-[1rem] border border-red-500/30 bg-red-500/10 px-3 text-red-200 transition hover:bg-red-500/18"
                        >
                          -
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="border-t border-white/8 p-4">
          {!isLastDraft ? (
            <button
              type="button"
              onClick={() => jumpDraft(1)}
              className="w-full rounded-[1.2rem] bg-blue-600 px-4 py-3 text-sm font-bold tracking-[0.14em] text-white transition hover:bg-blue-500"
            >
              ✅ 确认当前，查看下一份 ({selectedDraftIndex + 1}/{workspaceDrafts.length})
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void handleSubmitApproval()}
              disabled={statusData.isApproving || approvalSubmitted}
              className={`w-full rounded-[1.2rem] px-4 py-3 text-sm font-bold tracking-[0.14em] text-white transition ${
                approvalSubmitted
                  ? 'cursor-not-allowed bg-slate-600 opacity-70'
                  : 'bg-emerald-600 hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-70'
              }`}
            >
              {approvalSubmitted
                ? '✅ 全量下发已提交'
                : statusData.isApproving
                  ? '⏳ 正在执行安全下发...'
                  : '🚀 批次核实完毕，执行全量下发'}
            </button>
          )}
        </div>
      </div>
    )
  }

  const renderArchiveSummaryBoard = () => {
    if (!selectedArchiveRecord) {
      return <div className="flex h-full items-center justify-center text-white/45">暂无归档摘要</div>
    }

    return (
      <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[1.5rem] border border-white/10 bg-black/20">
        <div className="border-b border-white/8 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-2xl bg-cyan-300/10 text-cyan-100">
              <FolderOpen className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-200/70">归档摘要</p>
              <p className="mt-1 text-sm text-white/78">📦 历史文件原件已从内存释放，当前仅保留运行指标摘要</p>
            </div>
          </div>
        </div>

        <div className="grid gap-3 border-b border-white/8 p-4 md:grid-cols-3">
          <div className="rounded-[1.1rem] border border-white/10 bg-white/5 p-4">
            <p className="text-[11px] uppercase tracking-[0.16em] text-white/45">总 Token</p>
            <p className="mt-2 text-2xl font-semibold text-white">{selectedArchiveRecord.totalTokens}</p>
          </div>
          <div className="rounded-[1.1rem] border border-white/10 bg-white/5 p-4">
            <p className="text-[11px] uppercase tracking-[0.16em] text-white/45">平均置信度</p>
            <p className="mt-2 text-2xl font-semibold text-white">{selectedArchiveRecord.averageConfidence.toFixed(2)}</p>
          </div>
          <div className="rounded-[1.1rem] border border-white/10 bg-white/5 p-4">
            <p className="text-[11px] uppercase tracking-[0.16em] text-white/45">RAG 命中率</p>
            <p className="mt-2 text-2xl font-semibold text-white">{selectedArchiveRecord.ragHitRate.toFixed(1)}%</p>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar p-4">
          {workspaceDrafts.length > 0 ? (
            <div className="space-y-4">
              {workspaceDrafts.map((draft) => (
                <div key={draft.key} className="rounded-[1.25rem] border border-white/10 bg-white/5 p-4">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-white">{draft.title}</p>
                      <p className="truncate text-xs text-white/45">{draft.sourceName || draft.docId}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-white/10 bg-white/6 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-white/70">
                      静态校验结果
                    </span>
                  </div>

                  <div className="space-y-3">
                    {draft.tasks.map((task) => {
                      const isLowScore = task.score < 85

                      return (
                        <div
                          key={task.key}
                          className={`rounded-[1rem] border p-4 ${
                            isLowScore ? 'border-amber-500/35 bg-amber-500/10' : 'border-white/8 bg-black/15'
                          }`}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-[11px] uppercase tracking-[0.16em] text-white/45">任务 ID #{task.taskId}</p>
                              <p className="truncate text-sm font-semibold text-white">{task.taskName}</p>
                            </div>
                            <span
                              className={`shrink-0 rounded-full border px-3 py-1 text-xs font-bold ${
                                isLowScore
                                  ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                                  : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                              }`}
                            >
                              评分 {task.score}
                            </span>
                          </div>

                          <p className="mt-3 text-sm leading-7 text-white/68">{task.content}</p>

                          <div className="mt-4 grid gap-3 md:grid-cols-2">
                            <div className="rounded-[0.9rem] border border-white/8 bg-white/5 px-3 py-2.5">
                              <p className="text-[11px] uppercase tracking-[0.16em] text-white/45">责任人</p>
                              <p className="mt-1 text-sm text-white">{task.owner || '未填写'}</p>
                            </div>
                            <div className="rounded-[0.9rem] border border-white/8 bg-white/5 px-3 py-2.5">
                              <p className="text-[11px] uppercase tracking-[0.16em] text-white/45">截止日期</p>
                              <p className="mt-1 text-sm text-white">{task.deadline || '未填写'}</p>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-white/45">该批次没有可展示的校验任务快照</div>
          )}
        </div>
      </div>
    )
  }

  const renderAnalysisPane = () => (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[1.5rem] border border-white/10 bg-black/20">
      <div className="border-b border-white/8 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-200/70">AI 结果</p>
            <p className="truncate text-sm text-white/80">
              {String((matchedReport as Record<string, unknown> | null)?.title || '系统生成报告')}
            </p>
          </div>
          <span className="shrink-0 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-100">
            已生成
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar p-4">
        {matchedReport ? (
          <div className="space-y-4">
            {reportPreviewUrl ? (
              <div className="relative flex h-[108vh] min-h-[108vh] flex-col rounded-[1.2rem] border border-white/10 bg-slate-950 p-3">
                {reportPreviewLoading && (
                  <div className="skeleton-container absolute inset-0 z-20 rounded-[1.2rem] bg-slate-950/92 p-6 backdrop-blur">
                    <div className="mb-8 flex justify-between">
                      <div className="h-5 w-1/4 rounded skeleton-block" />
                      <div className="h-5 w-16 rounded skeleton-block" />
                    </div>
                    <div className="grid grid-cols-2 gap-6">
                      <div className="space-y-3">
                        <div className="h-2 w-full rounded skeleton-block" />
                        <div className="h-2 w-full rounded skeleton-block" />
                        <div className="h-2 w-4/5 rounded skeleton-block" />
                      </div>
                      <div className="space-y-3">
                        <div className="h-2 w-full rounded skeleton-block" />
                        <div className="h-2 w-5/6 rounded skeleton-block" />
                      </div>
                    </div>
                    <div className="mt-8 h-32 w-full rounded skeleton-block" />
                  </div>
                )}

                <div className="mb-3 flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-xs font-bold uppercase tracking-widest text-blue-400">
                    报告预览模式 ({getReportLabel(reportPreviewType)})
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setReportPreviewUrl('')
                      setReportPreviewType('')
                      setReportPreviewLoading(false)
                    }}
                    className="rounded-full border border-red-500/20 bg-red-500/10 px-3 py-1 text-xs text-red-100 transition hover:bg-red-500/18"
                  >
                    关闭报告预览
                  </button>
                </div>

                <div className="min-h-0 flex-1 overflow-hidden rounded">
                  {(reportPreviewType === 'html' || reportPreviewType === 'pdf') && (
                    <iframe src={reportPreviewUrl} className="h-full min-h-0 w-full border-none bg-white" title="report-preview" />
                  )}
                  {reportPreviewType === 'docx' && (
                    <div
                      id="report-docx-container"
                      className="h-full min-h-0 w-full overflow-y-auto custom-scrollbar rounded bg-slate-100 p-4 text-black"
                    />
                  )}
                  {reportPreviewType === 'unsupported' && (
                    <div className="flex h-full min-h-0 items-center justify-center text-white/45">该报告类型暂不支持预览。</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="rounded-[1.2rem] border border-white/10 bg-black/20 p-4">
                <div className="mb-3 flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="truncate text-sm font-semibold text-white">
                    {String((matchedReport as Record<string, unknown>).title || '系统生成报告')}
                  </span>
                  <span className="shrink-0 rounded-full bg-emerald-500/10 px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-emerald-300">
                    就绪
                  </span>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  {String((matchedReport as Record<string, unknown>).html_url || '') && (
                    <div className="rounded-[1rem] border border-white/10 bg-slate-950 p-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-white/45">HTML 报告</p>
                      <div className="mt-3 flex gap-2">
                        <button
                          type="button"
                          onClick={() => previewReport(String((matchedReport as Record<string, unknown>).html_url), 'html')}
                          className="flex-1 rounded-[0.9rem] bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500"
                        >
                          预览
                        </button>
                        <button
                          type="button"
                          onClick={() => downloadArtifact(String((matchedReport as Record<string, unknown>).html_url), 'Report.html')}
                          className="rounded-[0.9rem] border border-white/10 px-3 py-2 text-white/75 transition hover:bg-white/10"
                        >
                          <Download className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  )}

                  {String((matchedReport as Record<string, unknown>).docx_url || '') && (
                    <div className="rounded-[1rem] border border-white/10 bg-slate-950 p-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-white/45">Word 报告</p>
                      <div className="mt-3 flex gap-2">
                        <button
                          type="button"
                          onClick={() => previewReport(String((matchedReport as Record<string, unknown>).docx_url), 'docx')}
                          className="flex-1 rounded-[0.9rem] bg-slate-700 px-3 py-2 text-sm font-semibold text-white transition hover:bg-slate-600"
                        >
                          预览
                        </button>
                        <button
                          type="button"
                          onClick={() => downloadArtifact(String((matchedReport as Record<string, unknown>).docx_url), 'Report.docx')}
                          className="rounded-[0.9rem] border border-white/10 px-3 py-2 text-white/75 transition hover:bg-white/10"
                        >
                          <Download className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  )}

                  {(String((matchedReport as Record<string, unknown>).md_url || '') ||
                    String((matchedReport as Record<string, unknown>).ics_url || '')) && (
                    <div className="grid gap-2 md:col-span-2 md:grid-cols-3">
                      {String((matchedReport as Record<string, unknown>).md_url || '') && (
                        <button
                          type="button"
                          onClick={() => downloadArtifact(String((matchedReport as Record<string, unknown>).md_url), 'Report.md')}
                          className="rounded-[1rem] border border-white/10 bg-slate-800 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-700"
                        >
                          下载 Markdown
                        </button>
                      )}

                      {String((matchedReport as Record<string, unknown>).docx_url || '') && (
                        <button
                          type="button"
                          onClick={() => downloadArtifact(String((matchedReport as Record<string, unknown>).docx_url), 'Report.docx')}
                          className="rounded-[1rem] border border-white/10 bg-slate-800 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-700"
                        >
                          下载 Word
                        </button>
                      )}

                      {String((matchedReport as Record<string, unknown>).ics_url || '') && (
                        <button
                          type="button"
                          onClick={() => downloadArtifact(String((matchedReport as Record<string, unknown>).ics_url), 'Event.ics')}
                          className="rounded-[1rem] border border-white/10 bg-slate-800 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-700"
                        >
                          下载 ICS
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col items-center justify-center text-center text-white/40">
            <p className="text-base font-medium">等待任务完成后生成最终产物</p>
            <p className="mt-2 text-sm">报告资源会在这里自动归档。</p>
          </div>
        )}
      </div>
    </div>
  )

  return (
    <main className="relative min-h-screen bg-[#07111f] text-white">
      <GlassFilter />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(244,114,182,0.16),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(56,189,248,0.18),transparent_28%),linear-gradient(180deg,#06101d_0%,#0b1527_100%)]" />

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-[1800px] flex-col px-4 py-5 sm:px-6 lg:px-8">
        <GlassEffect
          className="rounded-[2rem] px-5 py-4"
          contentClassName="flex w-full flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"
        >
          <div className="flex items-center gap-4">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-300/20">
              <PanelsTopLeft className="h-6 w-6 text-cyan-100" />
            </span>
            <div>
              <p className="text-sm uppercase tracking-[0.24em] text-cyan-100/75">审批工作台</p>
              <h1 className="text-2xl font-semibold text-white sm:text-3xl">预览与审批工作台</h1>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm text-white/72">
            <span className="rounded-full border border-white/10 bg-white/6 px-4 py-2">
              历史记录 {historyItems.length} 条
            </span>
            <span className="rounded-full border border-white/10 bg-white/6 px-4 py-2">
              草稿 {workspaceDrafts.length} 份
            </span>
            {isApprovalStage && activePreviewTab === 'source' && (
              <button
                type="button"
                onClick={() => setActivePreviewTab('verification')}
                className="rounded-full border border-amber-400/20 bg-amber-400/10 px-4 py-2 text-amber-100 transition hover:bg-amber-400/18"
              >
                进入校验
              </button>
            )}
          </div>
        </GlassEffect>

        <section className="flex flex-1 flex-col gap-6 py-6 lg:flex-row lg:items-stretch">
          <div
            className={`w-full min-w-0 transition-all duration-500 ${
              shouldExpandPreview ? 'lg:w-[15%] lg:opacity-65' : 'lg:w-[30%] lg:opacity-100'
            }`}
          >
            <GlassEffect
              className="rounded-[2rem] p-5"
              contentClassName="flex h-[820px] w-full flex-col overflow-hidden lg:h-[920px]"
            >
              <div className="mb-4 flex items-center gap-3">
                <FileSearch className="h-5 w-5 text-cyan-100" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white">处理记录</p>
                  <p className="truncate text-xs text-white/45">点击任一文件即可切换预览上下文</p>
                </div>
              </div>

              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto custom-scrollbar pr-1">
                {historyItems.length > 0 ? (
                  historyItems.map((item) => {
                    const isCurrent = !item.isArchived && item.jobId === statusData.currentJobId
                    const isSelected = currentSelectedFile === item.fileName
                    const textTone = isCurrent ? 'text-slate-200' : 'text-slate-400'

                    return (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => selectFile(item.fileName)}
                        className={`w-full min-w-0 overflow-hidden rounded-[1.25rem] border p-4 text-left transition ${
                          isCurrent
                            ? 'border-blue-500 bg-slate-800 opacity-100 shadow-md'
                            : item.isArchived
                              ? 'border-slate-800 bg-slate-900/50 opacity-80'
                              : 'border-slate-800 bg-slate-900/50 opacity-60 grayscale-[50%]'
                        } ${isSelected ? 'border-l-4 border-blue-500 bg-blue-900/20 ring-1 ring-cyan-300/35' : ''}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1 overflow-hidden">
                            <p className={`truncate text-sm font-semibold ${textTone}`}>{item.fileName}</p>
                            <p className={`truncate text-xs ${isCurrent ? 'text-slate-300/70' : 'text-slate-500'}`}>{item.createdAt}</p>
                          </div>
                          <span className="shrink-0 rounded-full border border-white/10 bg-white/6 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-white/70">
                            {getFileStatusText(item.status)}
                          </span>
                        </div>

                        <div className="mt-3 flex min-w-0 items-center justify-between gap-3 text-[11px]">
                          <span
                            className={`min-w-0 flex-1 truncate ${isCurrent ? 'text-slate-300/75' : 'text-slate-500'}`}
                            title={item.metricDetail}
                          >
                            {item.metricDetail}
                          </span>
                          <div className="flex shrink-0 items-center gap-2">
                            <span className={`font-mono font-bold ${isCurrent ? 'text-cyan-100' : 'text-slate-400'}`}>
                              {item.metricPercent}%
                            </span>
                            <span
                              className={`flex items-center gap-1 rounded-full border px-2 py-1 font-mono ${
                                isCurrent
                                  ? 'border-cyan-300/20 bg-cyan-300/10 text-cyan-100'
                                  : 'border-white/10 bg-white/6 text-slate-300'
                              }`}
                              title="该文件累计消耗 Token"
                            >
                              ⚡ {item.tokenCount}
                            </span>
                          </div>
                        </div>
                      </button>
                    )
                  })
                ) : (
                  <div className="flex h-full items-center justify-center rounded-[1.4rem] border border-dashed border-white/10 px-4 text-center text-sm text-white/45">
                    暂无处理记录，先回到调度中心上传文件并启动任务。
                  </div>
                )}
              </div>
            </GlassEffect>
          </div>

          <div
            className={`w-full min-w-0 transition-all duration-500 ${
              shouldExpandPreview ? 'lg:w-[85%]' : 'lg:w-[70%]'
            }`}
          >
            <GlassEffect
              className="rounded-[2rem] p-5"
              contentClassName="flex h-[820px] w-full flex-col overflow-hidden lg:h-[920px]"
            >
              <div className="mb-4 flex flex-col gap-3 border-b border-white/8 pb-4 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white">预览区</p>
                  <p className="truncate text-xs text-white/45">
                    {currentSelectedFile || '请选择左侧记录以打开原文、校验信息或 AI 结果'}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {!isArchivedSelection && (
                    <button
                      type="button"
                      onClick={() => setActivePreviewTab('source')}
                      className={`rounded-full px-4 py-2 text-sm transition ${
                        activePreviewTab === 'source'
                          ? 'bg-white text-slate-900'
                          : 'border border-white/10 bg-white/6 text-white/72 hover:bg-white/10'
                      }`}
                    >
                      📄 原文预览
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setActivePreviewTab('verification')}
                    className={`rounded-full px-4 py-2 text-sm transition ${
                      activePreviewTab === 'verification'
                        ? 'bg-amber-300 text-slate-950'
                        : 'border border-white/10 bg-white/6 text-white/72 hover:bg-white/10'
                    }`}
                  >
                    🛡️ 校验信息
                  </button>
                  <button
                    type="button"
                    onClick={() => setActivePreviewTab('analysis')}
                    className={`rounded-full px-4 py-2 text-sm transition ${
                      activePreviewTab === 'analysis'
                        ? 'bg-emerald-300 text-slate-950'
                        : 'border border-white/10 bg-white/6 text-white/72 hover:bg-white/10'
                    }`}
                  >
                    🧠 AI 结果
                  </button>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-hidden">
                {!hasSelectedFile ? (
                  <div className="flex h-full min-h-0 items-center justify-center rounded-[1.5rem] border border-dashed border-white/10 bg-black/15 px-6 text-center">
                    <div className="flex max-w-md flex-col items-center gap-3 text-slate-500">
                      <FolderOpen className="h-10 w-10 text-slate-500" />
                      <p className="text-base font-medium">🗂️ 请在左侧选择一份处理记录以查看原文或审批报告</p>
                    </div>
                  </div>
                ) : isArchivedSelection ? (
                  renderArchiveSummaryBoard()
                ) : shouldSplitPreview ? (
                  <div className="grid h-full min-h-0 flex-1 grid-cols-2 gap-4 overflow-hidden">
                    <div className="h-full min-h-0 overflow-hidden">{renderSourcePane('原文')}</div>
                    <div className="h-full min-h-0 overflow-y-auto custom-scrollbar overflow-x-hidden pr-2">
                      {isVerificationSplit ? renderVerificationPane() : null}
                      {isAnalysisSplit ? renderAnalysisPane() : null}
                    </div>
                  </div>
                ) : (
                  <div className="h-full min-h-0 overflow-y-auto custom-scrollbar overflow-x-hidden pr-2">
                    {activePreviewTab === 'source' && renderSourcePane()}
                    {activePreviewTab === 'verification' && renderVerificationPane()}
                    {activePreviewTab === 'analysis' && renderAnalysisPane()}
                  </div>
                )}
              </div>

              {!isArchivedSelection && selectedDraft && workspaceDrafts.length > 1 && (
                <div className="mt-4 flex items-center justify-between border-t border-white/8 pt-4">
                  <button
                    type="button"
                    onClick={() => jumpDraft(-1)}
                    disabled={selectedDraftIndex <= 0}
                    className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white/72 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronLeft className="h-4 w-4" />
                    上一份
                  </button>

                  <span className="text-xs uppercase tracking-[0.18em] text-white/45">
                    {selectedDraftIndex + 1}/{workspaceDrafts.length}
                  </span>

                  <button
                    type="button"
                    onClick={() => jumpDraft(1)}
                    disabled={selectedDraftIndex >= workspaceDrafts.length - 1}
                    className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white/72 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    下一份
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              )}
            </GlassEffect>
          </div>
        </section>
      </div>
    </main>
  )
}
