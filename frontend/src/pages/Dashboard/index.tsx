import AgentTopology, { type AgentTopologyStatusMap } from '@/components/AgentTopology'
import TaskController from '@/components/TaskController'
import { GlassEffect, GlassFilter } from '@/components/ui/liquid-glass'
import type { JobStatusData, StartJobOptions } from '@/hooks/useJobMonitor'
import MetricCharts from '@/pages/Dashboard/MetricCharts'
import { Activity, ArrowRight, Workflow } from 'lucide-react'
import { Link } from 'react-router-dom'

interface DashboardPageProps {
  startJob: (options: StartJobOptions) => Promise<void>
  statusData: JobStatusData
}

export default function DashboardPage({ startJob, statusData }: DashboardPageProps) {
  const topologyStatuses: AgentTopologyStatusMap = {
    reader: statusData.agentStatuses.reader ?? (statusData.jobStatus === 'failed' ? 'error' : 'waiting'),
    reviewer: statusData.agentStatuses.reviewer ?? (statusData.jobStatus === 'failed' ? 'error' : 'waiting'),
    dispatcher: statusData.agentStatuses.dispatcher ?? (statusData.jobStatus === 'failed' ? 'error' : 'waiting'),
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#07111f] text-white">
      <GlassFilter />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.24),transparent_32%),radial-gradient(circle_at_85%_15%,rgba(45,212,191,0.18),transparent_28%),radial-gradient(circle_at_50%_100%,rgba(249,115,22,0.16),transparent_24%),linear-gradient(145deg,#07111f_0%,#0d1728_45%,#081018_100%)]" />

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-[1680px] flex-col px-4 py-5 sm:px-6 lg:px-8">
        <GlassEffect
          className="rounded-[2rem] px-5 py-4"
          contentClassName="flex w-full flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"
        >
          <div className="flex items-center gap-4">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-300/20">
              <Workflow className="h-6 w-6 text-cyan-100" />
            </span>
            <div>
              <p className="text-sm uppercase tracking-[0.24em] text-cyan-100/75">调度中心</p>
              <h1 className="text-2xl font-semibold text-white sm:text-3xl">系统调度室</h1>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-sm text-cyan-100">
              宽屏调度布局
            </span>
            <Link
              to="/"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/16"
            >
              返回首页
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </GlassEffect>

        <section className="grid gap-6 py-6 xl:grid-cols-12">
          <div className="xl:col-span-4">
            <TaskController startJob={startJob} statusData={statusData} className="h-full" />
          </div>

          <div className="xl:col-span-8">
            <div className="flex h-full flex-col gap-6">
              <MetricCharts />

              <GlassEffect className="rounded-[2rem] p-5" contentClassName="w-full">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm uppercase tracking-[0.2em] text-cyan-100/70">Agent Flow Monitor</p>
                    <h3 className="mt-2 text-2xl font-semibold text-white">多智能体执行拓扑</h3>
                  </div>
                  <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-sm text-white/75">
                    <Activity className="h-4 w-4 text-emerald-200" />
                    {statusData.isSubmitting ? '实时执行中' : '等待下一批任务'}
                  </span>
                </div>

                <div className="rounded-[1.75rem] border border-white/10 bg-black/18 p-4">
                  <AgentTopology agentsStatus={topologyStatuses} />
                </div>
              </GlassEffect>
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}
