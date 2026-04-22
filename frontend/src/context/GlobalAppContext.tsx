import type { JobDraft, JobInputTab, JobReport } from '@/hooks/useJobMonitor'
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'

export const HISTORY_STORAGE_KEY = 'nexusops_history'

export type GlobalFormState = {
  isDesensitized: boolean
  provider: string
  apiKey: string
  mode: 'preview' | 'email'
  emailTypes: string[]
  inputTab: JobInputTab
  pastedText: string
  crawlUrl: string
  crawlKeyword: string
  crawlCount: number
}

export type ProcessingHistoryItem = {
  id: string
  jobId: string
  fileName: string
  createdAt: string
  status: 'active' | 'pending_approval' | 'done' | 'error'
  tokenCount: number
  metricPercent: number
  metricDetail: string
  sourceFile: File | null
  sourceType: string
  sourceText: string
  drafts: JobDraft[]
  reports: JobReport[]
}

export type HistoryRecordFileMeta = {
  fileName: string
  fileSize: number
  fileType: string
  tokenCount: number
  metricPercent: number
  metricDetail: string
}

export type HistoryRecord = {
  id: string
  jobId: string
  createdAt: string
  completedAt: string
  status: 'success' | 'failed'
  throughputCount: number
  fileCount: number
  files: HistoryRecordFileMeta[]
  totalTokens: number
  averageConfidence: number
  ragHitRate: number
  drafts: JobDraft[]
  reports: JobReport[]
}

type GlobalAppContextValue = {
  fileList: File[]
  setFileList: React.Dispatch<React.SetStateAction<File[]>>
  formState: GlobalFormState
  setFormState: React.Dispatch<React.SetStateAction<GlobalFormState>>
  processingHistory: ProcessingHistoryItem[]
  setProcessingHistory: React.Dispatch<React.SetStateAction<ProcessingHistoryItem[]>>
  historyRecords: HistoryRecord[]
  setHistoryRecords: React.Dispatch<React.SetStateAction<HistoryRecord[]>>
  currentSelectedFile: string
  setCurrentSelectedFile: React.Dispatch<React.SetStateAction<string>>
}

const GlobalAppContext = createContext<GlobalAppContextValue | null>(null)

const initialFormState: GlobalFormState = {
  isDesensitized: false,
  provider: window.localStorage.getItem('docs_agent_ui_provider') || 'tongyi',
  apiKey: window.localStorage.getItem('docs_agent_ui_api_key') || '',
  mode: 'preview',
  emailTypes: ['md', 'docx', 'ics'],
  inputTab: 'upload',
  pastedText: '',
  crawlUrl: '',
  crawlKeyword: '',
  crawlCount: 5,
}

function readHistoryRecordsFromStorage() {
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY)
    if (!raw) return []

    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []

    return parsed.filter((item): item is HistoryRecord => Boolean(item && typeof item === 'object'))
  } catch {
    return []
  }
}

interface GlobalAppProviderProps {
  children: React.ReactNode
}

export function GlobalAppProvider({ children }: GlobalAppProviderProps) {
  const [fileList, setFileList] = useState<File[]>([])
  const [formState, setFormState] = useState<GlobalFormState>(initialFormState)
  const [processingHistory, setProcessingHistory] = useState<ProcessingHistoryItem[]>([])
  const [historyRecords, setHistoryRecords] = useState<HistoryRecord[]>(() => readHistoryRecordsFromStorage())
  const [currentSelectedFile, setCurrentSelectedFile] = useState('')

  useEffect(() => {
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(historyRecords))
  }, [historyRecords])

  const value = useMemo(
    () => ({
      fileList,
      setFileList,
      formState,
      setFormState,
      processingHistory,
      setProcessingHistory,
      historyRecords,
      setHistoryRecords,
      currentSelectedFile,
      setCurrentSelectedFile,
    }),
    [currentSelectedFile, fileList, formState, historyRecords, processingHistory],
  )

  return <GlobalAppContext.Provider value={value}>{children}</GlobalAppContext.Provider>
}

export function useGlobalAppContext() {
  const context = useContext(GlobalAppContext)
  if (!context) {
    throw new Error('useGlobalAppContext must be used inside <GlobalAppProvider>.')
  }

  return context
}
