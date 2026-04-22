import { BadgeCheck, BookOpenText, CircleAlert, Clock3, Send, ShieldCheck } from 'lucide-react'

export type AgentRuntimeStatus = 'waiting' | 'active' | 'done' | 'error'

export interface AgentTopologyStatusMap {
  reader: AgentRuntimeStatus
  reviewer: AgentRuntimeStatus
  dispatcher: AgentRuntimeStatus
}

interface AgentTopologyProps {
  agentsStatus: AgentTopologyStatusMap
}

type AgentKey = keyof AgentTopologyStatusMap

const agentMeta: Record<
  AgentKey,
  {
    title: string
    icon: typeof BookOpenText
    activeGlow: string
    iconTone: string
    subtitle: string
  }
> = {
  reader: {
    title: 'Reader',
    icon: BookOpenText,
    activeGlow: 'bg-blue-500/20',
    iconTone: 'text-blue-100',
    subtitle: 'Document ingestion',
  },
  reviewer: {
    title: 'Reviewer',
    icon: ShieldCheck,
    activeGlow: 'bg-blue-500/20',
    iconTone: 'text-slate-100',
    subtitle: 'Review and critic',
  },
  dispatcher: {
    title: 'Dispatcher',
    icon: Send,
    activeGlow: 'bg-emerald-500/20',
    iconTone: 'text-emerald-100',
    subtitle: 'Dispatch output',
  },
}

function getNodeClass(status: AgentRuntimeStatus) {
  if (status === 'active') {
    return 'agent-node-active border-blue-500 bg-slate-800/85'
  }

  if (status === 'done') {
    return 'border-emerald-500/45 bg-slate-900/70'
  }

  if (status === 'error') {
    return 'border-red-500/45 bg-red-950/25'
  }

  return 'border-slate-700 bg-slate-900/45 opacity-75'
}

function getStatusText(status: AgentRuntimeStatus) {
  if (status === 'active') return 'Processing...'
  if (status === 'done') return 'Completed'
  if (status === 'error') return 'Failed'
  return 'Pending'
}

function getStatusTextClass(status: AgentRuntimeStatus) {
  if (status === 'active') return 'text-blue-400 font-bold animate-pulse'
  if (status === 'done') return 'text-emerald-400'
  if (status === 'error') return 'text-red-400'
  return 'text-slate-500'
}

function getNodeBadge(status: AgentRuntimeStatus) {
  if (status === 'active') return <Clock3 className="h-3.5 w-3.5" />
  if (status === 'done') return <BadgeCheck className="h-3.5 w-3.5" />
  if (status === 'error') return <CircleAlert className="h-3.5 w-3.5" />
  return <Clock3 className="h-3.5 w-3.5" />
}

export default function AgentTopology({ agentsStatus }: AgentTopologyProps) {
  const lineStatus = {
    readerToReviewer: agentsStatus.reader === 'done' && agentsStatus.reviewer === 'waiting',
    reviewerToDispatcher: agentsStatus.reviewer === 'done' && agentsStatus.dispatcher === 'waiting',
  }

  return (
    <div className="relative flex h-full min-h-[230px] w-full select-none items-center justify-center overflow-hidden rounded-[1.6rem] border border-white/8 bg-[linear-gradient(180deg,rgba(2,6,23,0.68),rgba(15,23,42,0.46))] p-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.14),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(16,185,129,0.12),transparent_24%)]" />

      <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
        <path d="M 25% 50% L 50% 50%" stroke="#334155" strokeWidth="2" fill="none" strokeDasharray="6 6" />
        {lineStatus.readerToReviewer && (
          <path
            d="M 25% 50% L 50% 50%"
            stroke="#3b82f6"
            strokeWidth="2"
            fill="none"
            strokeDasharray="6 6"
            className="animate-dash"
          />
        )}

        <path d="M 50% 50% L 75% 50%" stroke="#334155" strokeWidth="2" fill="none" strokeDasharray="6 6" />
        {lineStatus.reviewerToDispatcher && (
          <path
            d="M 50% 50% L 75% 50%"
            stroke="#3b82f6"
            strokeWidth="2"
            fill="none"
            strokeDasharray="6 6"
            className="animate-dash"
          />
        )}
      </svg>

      <div className="relative z-10 flex w-full flex-col gap-4 px-2 md:flex-row md:justify-around md:gap-6">
        {(Object.keys(agentMeta) as AgentKey[]).map((agentKey) => {
          const meta = agentMeta[agentKey]
          const status = agentsStatus[agentKey]
          const Icon = meta.icon

          return (
            <div
              key={agentKey}
              className={`agent-topology-node relative flex min-w-0 flex-1 items-center gap-4 rounded-xl border px-5 py-4 transition-all duration-500 ${getNodeClass(status)}`}
            >
              <div className="agent-topology-icon-box flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 shadow-inner">
                <Icon className={`h-5 w-5 ${meta.iconTone}`} />
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold tracking-wider text-slate-100">{meta.title}</span>
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] ${getStatusTextClass(status)}`}>
                    {getNodeBadge(status)}
                    {getStatusText(status)}
                  </span>
                </div>
                <p className="mt-2 text-xs uppercase tracking-[0.22em] text-white/35">{meta.subtitle}</p>
              </div>

              {status === 'active' && <div className={`absolute -inset-1 -z-10 rounded-xl blur-md ${meta.activeGlow}`} />}
            </div>
          )
        })}
      </div>
    </div>
  )
}
