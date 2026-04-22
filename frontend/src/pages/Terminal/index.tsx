import ThinkingConsole, { type ThinkingConsoleHandle } from '@/components/ThinkingConsole'
import { useGlobalAppContext } from '@/context/GlobalAppContext'
import type { JobStatusData } from '@/hooks/useJobMonitor'
import { ArrowLeft, Eye, MonitorCog, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'

interface TerminalPageProps {
  statusData: JobStatusData
}

export default function TerminalPage({ statusData }: TerminalPageProps) {
  const consoleRef = useRef<ThinkingConsoleHandle | null>(null)
  const { formState } = useGlobalAppContext()
  const [autoScroll, setAutoScroll] = useState(true)
  const receivedLogs = statusData.streamMessages.length
  const processingFiles = Object.values(statusData.fileMetrics).filter((metric) => metric.status === 'active').length

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#010409] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(14,116,144,0.28),transparent_24%),radial-gradient(circle_at_top_right,rgba(15,23,42,0.88),transparent_38%),radial-gradient(circle_at_bottom_left,rgba(30,64,175,0.2),transparent_28%),linear-gradient(180deg,#010409_0%,#03101f_44%,#010409_100%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(15,23,42,0.18)_1px,transparent_1px),linear-gradient(90deg,rgba(15,23,42,0.18)_1px,transparent_1px)] bg-[size:32px_32px] opacity-25" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(1,4,9,0.12)_46%,rgba(1,4,9,0.85)_100%)]" />

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-[1800px] flex-col px-4 py-4 sm:px-6 lg:px-8">
        <section className="grid flex-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="flex flex-col rounded-[1.8rem] border border-cyan-500/12 bg-black/30 p-4 shadow-[0_18px_60px_rgba(2,6,23,0.42)] backdrop-blur-xl">
            <Link
              to="/dashboard"
              className="inline-flex w-fit items-center gap-2 rounded-full border border-cyan-400/25 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/45 hover:bg-cyan-300/14"
            >
              <ArrowLeft className="h-4 w-4" />
              返回调度中心
            </Link>

            <div className="mt-5 rounded-[1.5rem] border border-white/8 bg-[#02060d]/90 p-4">
              <p className="text-[11px] uppercase tracking-[0.26em] text-cyan-100/65">终端控制台</p>
              <h1 className="mt-3 text-xl font-semibold text-white">实时监控终端</h1>
            </div>

            <div className="mt-4 space-y-3">
              <div className="rounded-[1.4rem] border border-white/8 bg-white/[0.03] p-4">
                <div className="flex items-center gap-2 text-cyan-100">
                  <MonitorCog className="h-4 w-4" />
                  <p className="text-sm font-semibold">状态卡片</p>
                </div>

                <div className="mt-4 grid gap-3">
                  <div className="rounded-[1rem] border border-white/8 bg-black/20 px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">已接收日志数</p>
                    <p className="mt-2 text-2xl font-semibold text-cyan-50">{receivedLogs}</p>
                  </div>

                  <div className="rounded-[1rem] border border-white/8 bg-black/20 px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">正在处理的文件数</p>
                    <p className="mt-2 text-2xl font-semibold text-cyan-50">{processingFiles}</p>
                  </div>
                </div>
              </div>

              <div className="rounded-[1.4rem] border border-white/8 bg-white/[0.03] p-4">
                <div className="flex items-center gap-2 text-cyan-100">
                  <Eye className="h-4 w-4" />
                  <p className="text-sm font-semibold">视图控制</p>
                </div>

                <div className="mt-4 space-y-3">
                  <button
                    type="button"
                    onClick={() => consoleRef.current?.clearLogs()}
                    className="flex w-full items-center justify-center gap-2 rounded-[1rem] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-100 transition hover:bg-red-500/18"
                  >
                    <Trash2 className="h-4 w-4" />
                    清空屏幕
                  </button>

                  <label className="flex items-center justify-between rounded-[1rem] border border-white/8 bg-black/20 px-4 py-3">
                    <div>
                      <p className="text-sm font-semibold text-white">自动滚屏</p>
                      <p className="mt-1 text-xs text-slate-400">关闭后保留当前位置，便于查看历史日志。</p>
                    </div>

                    <button
                      type="button"
                      onClick={() => setAutoScroll((current) => !current)}
                      className={`relative inline-flex h-7 w-12 items-center rounded-full transition ${
                        autoScroll ? 'bg-cyan-500/80' : 'bg-slate-700'
                      }`}
                      aria-pressed={autoScroll}
                    >
                      <span
                        className={`inline-block h-5 w-5 rounded-full bg-white transition ${
                          autoScroll ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </label>
                </div>
              </div>
            </div>
          </aside>

          <section className="min-h-0 rounded-[1.9rem] border border-cyan-400/12 bg-black/30 p-3 shadow-[0_22px_80px_rgba(2,6,23,0.5)] backdrop-blur-xl">
            <div className="h-[calc(100vh-9rem)] min-h-[760px]">
              <ThinkingConsole
                ref={consoleRef}
                logs={statusData.streamMessages}
                jobStatus={statusData.jobStatus}
                currentJobId={statusData.currentJobId}
                error={statusData.error}
                isDesensitized={formState.isDesensitized}
                autoScroll={autoScroll}
              />
            </div>
          </section>
        </section>
      </div>
    </main>
  )
}
