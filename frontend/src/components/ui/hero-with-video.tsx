import React, { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  ArrowRight,
  BarChart3,
  Boxes,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  Clock3,
  Code2,
  Database,
  GitBranch,
  Layers3,
  LineChart,
  ListChecks,
  Menu,
  Moon,
  Network,
  Play,
  RadioTower,
  Route,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  TableProperties,
  Workflow,
  X,
  Zap,
} from 'lucide-react'
import { useTheme } from '../next/next-themes'
import { GlassEffect, GlassFilter } from './liquid-glass'

interface NavbarHeroProps {
  brandName?: string
  heroTitle?: string
  heroSubtitle?: string
  heroDescription?: string
  backgroundImage?: string
  videoUrl?: string
  emailPlaceholder?: string
}

type ViewKey = 'home' | 'about' | 'blog' | 'plans-prices'

const routes: Record<ViewKey, string> = {
  home: '/',
  about: '/about',
  blog: '/blog',
  'plans-prices': '/plans-prices',
}

const navigation = [
  { label: 'About', view: 'about' as const },
  { label: 'Resources', view: 'home' as const },
  { label: 'Blog', view: 'blog' as const },
  { label: 'Plans & Prices', view: 'plans-prices' as const },
]

const routeToView = (pathname: string): ViewKey => {
  if (pathname === '/about') return 'about'
  if (pathname === '/blog') return 'blog'
  if (pathname === '/plans-prices' || pathname === '/plans' || pathname === '/pricing') return 'plans-prices'
  return 'home'
}

const statFormatter = new Intl.NumberFormat('zh-CN')

const NavbarHero: React.FC<NavbarHeroProps> = ({
  brandName = 'NexusOps',
  heroTitle = '文档智能体运行中枢',
  heroSubtitle = '实时编排 / 协同执行 / 数据闭环',
  heroDescription = '把任务调度、智能体态势、逻辑流控制和数据资产集中到一个可操作的前端控制台。',
  backgroundImage = 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?ixlib=rb-4.0.3&auto=format&fit=crop&w=2072&q=80',
}) => {
  const [view, setView] = useState<ViewKey>(() => routeToView(window.location.pathname))
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)
  const [mounted, setMounted] = useState(false)
  const { theme, setTheme } = useTheme()

  useEffect(() => {
    setMounted(true)

    const syncView = () => setView(routeToView(window.location.pathname))
    window.addEventListener('popstate', syncView)
    return () => window.removeEventListener('popstate', syncView)
  }, [])

  const pageTitle = useMemo(() => {
    if (view === 'about') return '任务调度序列'
    if (view === 'blog') return '多智能体协同态势与逻辑流控制终端'
    if (view === 'plans-prices') return '数据资产界面'
    return heroTitle
  }, [heroTitle, view])

  const navigateTo = (nextView: ViewKey) => {
    setView(nextView)
    setOpenDropdown(null)
    setIsMobileMenuOpen(false)
    window.history.pushState({}, '', routes[nextView])
  }

  const ThemeToggleButton = () => {
    if (!mounted) return <div className="h-11 w-11" />

    return (
      <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme">
        <GlassEffect className="h-11 w-11 items-center justify-center rounded-full hover:scale-105">
          {theme === 'light' ? <Moon className="h-5 w-5 text-white" /> : <Sun className="h-5 w-5 text-white" />}
        </GlassEffect>
      </button>
    )
  }

  return (
    <main
      className="absolute inset-0 overflow-y-auto text-white"
      style={{
        backgroundImage: `url("${backgroundImage}")`,
        backgroundPosition: 'center center',
        backgroundSize: 'cover',
      }}
    >
      <GlassFilter />
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(45,212,191,0.34),transparent_28%),radial-gradient(circle_at_80%_0%,rgba(244,114,182,0.25),transparent_26%),linear-gradient(135deg,rgba(7,12,20,0.94),rgba(21,28,42,0.84)_48%,rgba(18,12,32,0.9))]" />

      <div className="relative z-10 mx-auto flex min-h-full w-full max-w-7xl flex-col px-4 py-4 sm:px-6 lg:px-8">
        <GlassEffect className="z-30 items-center justify-between rounded-3xl px-4 py-3 sm:px-6" contentClassName="flex w-full items-center justify-between gap-4">
          <button onClick={() => navigateTo('home')} className="flex flex-shrink-0 items-center gap-3 text-left">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-white/20">
              <Workflow className="h-5 w-5 text-cyan-100" />
            </span>
            <span>
              <span className="block text-xl font-bold leading-tight text-white">{brandName}</span>
              <span className="block text-xs font-medium text-white/60">{pageTitle}</span>
            </span>
          </button>

          <nav className="hidden font-medium text-white/80 lg:flex">
            <ul className="flex items-center gap-1">
              {navigation.map((item) => {
                const isActive = view === item.view

                if (item.label === 'Resources') {
                  return (
                    <li className="relative" key={item.label}>
                      <button
                        onClick={() => setOpenDropdown(openDropdown === 'desktop-resources' ? null : 'desktop-resources')}
                        className="flex items-center rounded-xl px-3 py-2 text-sm transition-colors hover:bg-white/15 hover:text-white"
                      >
                        Resources
                        <ChevronDown className={`ml-1 h-4 w-4 transition-transform ${openDropdown === 'desktop-resources' ? 'rotate-180' : ''}`} />
                      </button>
                      {openDropdown === 'desktop-resources' && (
                        <div className="absolute left-0 top-full z-30 mt-2 w-56">
                          <GlassEffect className="rounded-3xl p-2" contentClassName="w-full">
                            <button onClick={() => navigateTo('about')} className="flex w-full items-center gap-2 rounded-2xl px-3 py-2 text-left text-sm text-white/85 hover:bg-white/15">
                              <CalendarClock className="h-4 w-4" />
                              任务调度序列
                            </button>
                            <button onClick={() => navigateTo('blog')} className="flex w-full items-center gap-2 rounded-2xl px-3 py-2 text-left text-sm text-white/85 hover:bg-white/15">
                              <BrainCircuit className="h-4 w-4" />
                              协同控制终端
                            </button>
                          </GlassEffect>
                        </div>
                      )}
                    </li>
                  )
                }

                return (
                  <li key={item.label}>
                    <button
                      onClick={() => navigateTo(item.view)}
                      className={`rounded-xl px-3 py-2 text-sm transition-colors ${
                        isActive ? 'bg-white/20 text-white' : 'text-white/85 hover:bg-white/15 hover:text-white'
                      }`}
                    >
                      {item.label}
                    </button>
                  </li>
                )
              })}
            </ul>
          </nav>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-3 lg:flex">
              <button onClick={() => navigateTo('blog')} className="rounded-2xl px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/15">
                打开终端
              </button>
              <button onClick={() => navigateTo('about')}>
                <GlassEffect className="rounded-3xl px-5 py-2.5 hover:scale-105">
                  <span className="flex items-center gap-2 text-sm font-medium text-white">
                    调度任务
                    <ArrowRight className="h-4 w-4" />
                  </span>
                </GlassEffect>
              </button>
            </div>

            <ThemeToggleButton />

            <button onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)} className="lg:hidden" aria-label="Open menu">
              <GlassEffect className="h-11 w-11 items-center justify-center rounded-full">
                {isMobileMenuOpen ? <X className="h-6 w-6 text-white" /> : <Menu className="h-6 w-6 text-white" />}
              </GlassEffect>
            </button>
          </div>
        </GlassEffect>

        {isMobileMenuOpen && (
          <GlassEffect className="z-20 mt-3 rounded-3xl p-3 lg:hidden" contentClassName="w-full">
            <div className="grid gap-1">
              {navigation
                .filter((item) => item.label !== 'Resources')
                .map((item) => (
                  <button
                    key={item.label}
                    onClick={() => navigateTo(item.view)}
                    className={`rounded-2xl px-3 py-2 text-left text-sm text-white hover:bg-white/15 ${view === item.view ? 'bg-white/20' : ''}`}
                  >
                    {item.label}
                  </button>
                ))}
            </div>
          </GlassEffect>
        )}

        <div className="flex-1 py-6 sm:py-8">{view === 'home' && <HomeView title={heroTitle} subtitle={heroSubtitle} description={heroDescription} navigateTo={navigateTo} />}</div>
        {view === 'about' && <SchedulerView />}
        {view === 'blog' && <AgentOpsView />}
        {view === 'plans-prices' && <DataView />}
      </div>
    </main>
  )
}

const HomeView = ({
  title,
  subtitle,
  description,
  navigateTo,
}: {
  title: string
  subtitle: string
  description: string
  navigateTo: (view: ViewKey) => void
}) => (
  <section className="grid min-h-[calc(100vh-140px)] items-center gap-8 lg:grid-cols-[1.1fr_0.9fr]">
    <div className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-100/80">{subtitle}</p>
      <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight text-white sm:text-6xl">{title}</h1>
      <p className="mt-6 max-w-2xl text-lg leading-8 text-white/75">{description}</p>
      <div className="mt-8 flex flex-wrap gap-3">
        <button onClick={() => navigateTo('about')}>
          <GlassEffect className="rounded-3xl px-5 py-3 hover:scale-105">
            <span className="flex items-center gap-2 text-sm font-semibold text-white">
              查看任务调度
              <CalendarClock className="h-4 w-4" />
            </span>
          </GlassEffect>
        </button>
        <button onClick={() => navigateTo('blog')} className="rounded-3xl border border-white/25 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10">
          协同态势终端
        </button>
      </div>
    </div>

    <div className="grid gap-4">
      {[
        ['任务队列', '128', '优先级、依赖、窗口期统一编排'],
        ['活跃智能体', '24', 'Reader / Reviewer / Critic / Dispatcher 协同'],
        ['数据表状态', '99.2%', '采集、索引、审计与导出状态闭环'],
      ].map(([label, value, note]) => (
        <GlassEffect key={label} className="rounded-3xl p-5" contentClassName="w-full">
          <div className="flex items-center justify-between gap-5">
            <div>
              <p className="text-sm text-white/60">{label}</p>
              <p className="mt-2 text-3xl font-bold text-white">{value}</p>
            </div>
            <p className="max-w-48 text-right text-sm leading-6 text-white/70">{note}</p>
          </div>
        </GlassEffect>
      ))}
    </div>
  </section>
)

const SchedulerView = () => {
  const jobs = [
    { name: '文档摄取批处理', time: '09:00', state: '运行中', load: 72, owner: 'Reader-03', color: 'bg-emerald-300' },
    { name: 'OCR 版面解析', time: '09:18', state: '排队', load: 46, owner: 'Vision-02', color: 'bg-cyan-300' },
    { name: 'RAG 索引刷新', time: '09:45', state: '等待依赖', load: 31, owner: 'Retriever-01', color: 'bg-amber-300' },
    { name: '安全审查与脱敏', time: '10:10', state: '预留窗口', load: 18, owner: 'Guard-01', color: 'bg-pink-300' },
  ]

  return (
    <section className="grid gap-6 pb-8 lg:grid-cols-[0.72fr_1.28fr]">
      <div className="space-y-5">
        <PanelTitle icon={CalendarClock} eyebrow="ABOUT ROUTE" title="任务调度序列" description="从 http://127.0.0.1:5173/about 进入，集中查看任务排程、依赖链、优先级和执行窗口。" />
        <GlassEffect className="rounded-3xl p-5" contentClassName="w-full">
          <div className="grid grid-cols-2 gap-3">
            <Metric icon={ListChecks} label="今日任务" value="36" tone="text-cyan-100" />
            <Metric icon={Zap} label="高优先级" value="8" tone="text-amber-100" />
            <Metric icon={Clock3} label="平均等待" value="4.6m" tone="text-emerald-100" />
            <Metric icon={ShieldCheck} label="准点率" value="97%" tone="text-pink-100" />
          </div>
        </GlassEffect>
        <ControlStrip />
      </div>

      <div className="space-y-5">
        <GlassEffect className="rounded-3xl p-5" contentClassName="w-full">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-white/55">调度队列</p>
              <h2 className="text-2xl font-bold text-white">执行时间轴</h2>
            </div>
            <button className="flex items-center gap-2 rounded-2xl bg-white/15 px-4 py-2 text-sm font-semibold text-white hover:bg-white/25">
              <Play className="h-4 w-4" />
              启动下一批
            </button>
          </div>

          <div className="space-y-4">
            {jobs.map((job, index) => (
              <div key={job.name} className="grid gap-3 rounded-2xl border border-white/10 bg-black/18 p-4 sm:grid-cols-[82px_1fr_120px] sm:items-center">
                <div>
                  <p className="text-xs text-white/50">T+{index}</p>
                  <p className="text-xl font-bold text-white">{job.time}</p>
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${job.color}`} />
                    <h3 className="font-semibold text-white">{job.name}</h3>
                    <span className="rounded-full bg-white/10 px-2 py-1 text-xs text-white/70">{job.state}</span>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                    <div className="h-full rounded-full bg-gradient-to-r from-cyan-300 via-emerald-300 to-pink-300" style={{ width: `${job.load}%` }} />
                  </div>
                </div>
                <div className="text-left sm:text-right">
                  <p className="text-xs text-white/50">Owner</p>
                  <p className="text-sm font-semibold text-white">{job.owner}</p>
                </div>
              </div>
            ))}
          </div>
        </GlassEffect>

        <div className="grid gap-5 md:grid-cols-3">
          {['依赖校验', '资源水位', '失败重试'].map((item, index) => (
            <GlassEffect key={item} className="rounded-3xl p-4" contentClassName="w-full">
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-2xl bg-white/15">
                  {[GitBranch, ServerCog, Route][index] && React.createElement([GitBranch, ServerCog, Route][index], { className: 'h-5 w-5 text-cyan-100' })}
                </span>
                <div>
                  <p className="font-semibold text-white">{item}</p>
                  <p className="text-xs text-white/55">状态正常</p>
                </div>
              </div>
            </GlassEffect>
          ))}
        </div>
      </div>
    </section>
  )
}

const AgentOpsView = () => {
  const agents = [
    ['Reader', '文档读取', 92, '在线'],
    ['Reviewer', '结论复核', 81, '在线'],
    ['Critic', '风险质询', 64, '观察'],
    ['Dispatcher', '任务分派', 88, '在线'],
    ['Retriever', '知识检索', 73, '同步'],
  ]

  const flow = ['事件接入', '策略选择', '智能体分工', '工具执行', '审查合并', '结果发布']

  return (
    <section className="space-y-6 pb-8">
      <PanelTitle icon={BrainCircuit} eyebrow="BLOG ROUTE" title="多智能体协同态势与逻辑流控制终端" description="从 http://127.0.0.1:5173/blog 进入，把协作状态、执行链路、控制开关放在同一张操作台。" />

      <div className="grid gap-6 xl:grid-cols-[1fr_1.15fr]">
        <GlassEffect className="rounded-3xl p-5" contentClassName="w-full">
          <div className="mb-5 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm text-white/55">协同态势</p>
              <h2 className="text-2xl font-bold text-white">智能体集群</h2>
            </div>
            <span className="flex items-center gap-2 rounded-full bg-emerald-300/15 px-3 py-1.5 text-sm text-emerald-100">
              <RadioTower className="h-4 w-4" />
              Live
            </span>
          </div>

          <div className="grid gap-3">
            {agents.map(([name, role, load, state]) => (
              <div key={name} className="rounded-2xl border border-white/10 bg-black/18 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <span className="grid h-11 w-11 place-items-center rounded-2xl bg-white/15">
                      <BrainCircuit className="h-5 w-5 text-cyan-100" />
                    </span>
                    <div>
                      <p className="font-semibold text-white">{name}</p>
                      <p className="text-sm text-white/55">{role}</p>
                    </div>
                  </div>
                  <span className="rounded-full bg-white/10 px-2.5 py-1 text-xs text-white/70">{state}</span>
                </div>
                <div className="mt-4 grid grid-cols-[1fr_44px] items-center gap-3">
                  <div className="h-2 rounded-full bg-white/10">
                    <div className="h-full rounded-full bg-gradient-to-r from-emerald-300 to-cyan-300" style={{ width: `${load}%` }} />
                  </div>
                  <span className="text-right text-sm font-semibold text-white">{load}%</span>
                </div>
              </div>
            ))}
          </div>
        </GlassEffect>

        <GlassEffect className="rounded-3xl p-5" contentClassName="w-full">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-white/55">逻辑流控制</p>
              <h2 className="text-2xl font-bold text-white">终端链路</h2>
            </div>
            <div className="flex gap-2">
              {['暂停', '重排', '旁路'].map((label) => (
                <button key={label} className="rounded-2xl bg-white/12 px-3 py-2 text-sm font-semibold text-white hover:bg-white/22">
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4">
            {flow.map((step, index) => (
              <div key={step} className="grid gap-3 rounded-2xl border border-white/10 bg-black/18 p-4 sm:grid-cols-[46px_1fr_auto] sm:items-center">
                <span className="grid h-11 w-11 place-items-center rounded-2xl bg-white/15 text-sm font-bold text-white">{index + 1}</span>
                <div>
                  <p className="font-semibold text-white">{step}</p>
                  <p className="text-sm text-white/55">{index < 4 ? '自动推进中，允许人工插队' : '需要合并检查后发布'}</p>
                </div>
                <span className="flex items-center gap-2 text-sm text-white/70">
                  <CircleDot className="h-4 w-4 text-cyan-200" />
                  {index === 5 ? '待审' : '通过'}
                </span>
              </div>
            ))}
          </div>
        </GlassEffect>
      </div>
    </section>
  )
}

const DataView = () => {
  const rows = [
    ['ingestion_jobs', 18342, '16.8 GB', '5分钟前', 'Healthy'],
    ['rag_chunks', 429118, '41.2 GB', '12分钟前', 'Indexing'],
    ['review_findings', 7824, '2.1 GB', '刚刚', 'Healthy'],
    ['delivery_events', 53891, '8.4 GB', '1小时前', 'Healthy'],
  ]

  return (
    <section className="space-y-6 pb-8">
      <PanelTitle icon={Database} eyebrow="PLANS & PRICES ROUTE" title="数据资产界面" description="从 http://127.0.0.1:5173/plans-prices 进入，查看数据表、同步状态、容量、质量和导出通道。" />

      <div className="grid gap-5 md:grid-cols-4">
        <Metric icon={TableProperties} label="数据表" value="42" tone="text-cyan-100" />
        <Metric icon={Layers3} label="总记录" value={statFormatter.format(508812)} tone="text-emerald-100" />
        <Metric icon={LineChart} label="质量评分" value="98.4" tone="text-amber-100" />
        <Metric icon={Boxes} label="存储" value="68.5G" tone="text-pink-100" />
      </div>

      <GlassEffect className="rounded-3xl p-5" contentClassName="w-full">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-white/55">数据目录</p>
            <h2 className="text-2xl font-bold text-white">资产清单</h2>
          </div>
          <button className="flex items-center gap-2 rounded-2xl bg-white/15 px-4 py-2 text-sm font-semibold text-white hover:bg-white/25">
            <SlidersHorizontal className="h-4 w-4" />
            筛选
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-separate border-spacing-y-3 text-left">
            <thead>
              <tr className="text-sm text-white/55">
                <th className="px-4 font-medium">表名</th>
                <th className="px-4 font-medium">记录数</th>
                <th className="px-4 font-medium">容量</th>
                <th className="px-4 font-medium">同步</th>
                <th className="px-4 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, count, size, sync, status]) => (
                <tr key={name} className="bg-black/18 text-white">
                  <td className="rounded-l-2xl px-4 py-4 font-semibold">{name}</td>
                  <td className="px-4 py-4 text-white/75">{typeof count === 'number' ? statFormatter.format(count) : count}</td>
                  <td className="px-4 py-4 text-white/75">{size}</td>
                  <td className="px-4 py-4 text-white/75">{sync}</td>
                  <td className="rounded-r-2xl px-4 py-4">
                    <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-sm text-white/80">
                      <CheckCircle2 className="h-4 w-4 text-emerald-200" />
                      {status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassEffect>
    </section>
  )
}

const PanelTitle = ({
  icon: Icon,
  eyebrow,
  title,
  description,
}: {
  icon: React.ElementType
  eyebrow: string
  title: string
  description: string
}) => (
  <div className="flex flex-col gap-4 rounded-[1.75rem] border border-white/10 bg-black/22 p-5 sm:flex-row sm:items-center sm:justify-between">
    <div>
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-100/75">{eyebrow}</p>
      <h1 className="mt-3 text-3xl font-bold leading-tight text-white sm:text-4xl">{title}</h1>
      <p className="mt-3 max-w-3xl text-base leading-7 text-white/70">{description}</p>
    </div>
    <span className="grid h-14 w-14 flex-none place-items-center rounded-2xl bg-white/15">
      <Icon className="h-7 w-7 text-cyan-100" />
    </span>
  </div>
)

const Metric = ({ icon: Icon, label, value, tone }: { icon: React.ElementType; label: string; value: string; tone: string }) => (
  <GlassEffect className="rounded-3xl p-4" contentClassName="w-full">
    <div className="flex min-h-24 flex-col justify-between">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-white/58">{label}</p>
        <Icon className={`h-5 w-5 ${tone}`} />
      </div>
      <p className="mt-4 text-3xl font-bold text-white">{value}</p>
    </div>
  </GlassEffect>
)

const ControlStrip = () => (
  <GlassEffect className="rounded-3xl p-5" contentClassName="w-full">
    <div className="space-y-4">
      {[
        ['自动重试', '开启'],
        ['资源均衡', '智能'],
        ['冲突处理', '人工确认'],
      ].map(([name, state]) => (
        <div key={name} className="flex items-center justify-between gap-4 rounded-2xl bg-black/16 px-4 py-3">
          <span className="flex items-center gap-3 text-sm font-semibold text-white">
            <Activity className="h-4 w-4 text-cyan-100" />
            {name}
          </span>
          <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/70">{state}</span>
        </div>
      ))}
    </div>
  </GlassEffect>
)

export { NavbarHero }
