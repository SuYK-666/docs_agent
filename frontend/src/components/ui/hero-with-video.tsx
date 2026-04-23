import SystemSettingsModal from '@/components/SystemSettingsModal'
import { ArrowRight, Menu, Settings2, Workflow, X } from 'lucide-react'
import React, { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
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

const primaryNavigation = [
  { label: '调度中心', to: '/dashboard' },
  { label: '监控终端', to: '/terminal' },
  { label: '审批工作台', to: '/workspace' },
]

const statusCards = [
  ['首页入口', '系统引导'],
  ['调度中心', '任务编排'],
  ['工作台 / 终端', '审批与监控'],
]

const NavbarHero: React.FC<NavbarHeroProps> = ({
  brandName = 'Docs Agent',
  heroTitle = '文档智能体协同中枢',
  heroSubtitle = '实时编排 / 协同执行 / 数据闭环',
  heroDescription = '从这里进入任务调度、审批校验与全屏监控。',
  backgroundImage = 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?ixlib=rb-4.0.3&auto=format&fit=crop&w=2072&q=80',
}) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const location = useLocation()

  const isCurrent = (path: string) => location.pathname === path

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
        <GlassEffect
          className="z-30 items-center justify-between rounded-3xl px-4 py-3 sm:px-6"
          contentClassName="flex w-full items-center justify-between gap-4"
        >
          <Link to="/" className="flex flex-shrink-0 items-center gap-3 text-left">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-white/20">
              <Workflow className="h-5 w-5 text-cyan-100" />
            </span>
            <span>
              <span className="block text-xl font-bold leading-tight text-white">{brandName}</span>
              <span className="block text-xs font-medium text-white/60">系统首页</span>
            </span>
          </Link>

          <nav className="hidden font-medium text-white/80 lg:flex">
            <ul className="flex items-center gap-1">
              {primaryNavigation.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className={`rounded-xl px-3 py-2 text-sm transition-colors ${
                      isCurrent(item.to) ? 'bg-white/20 text-white' : 'text-white/85 hover:bg-white/15 hover:text-white'
                    }`}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}

            </ul>
          </nav>

          <div className="flex items-center gap-3">
            <button onClick={() => setIsSettingsOpen(true)} aria-label="打开系统设置">
              <GlassEffect className="h-11 w-11 items-center justify-center rounded-full hover:scale-105">
                <Settings2 className="h-5 w-5 text-white" />
              </GlassEffect>
            </button>

            <button onClick={() => setIsMobileMenuOpen((current) => !current)} className="lg:hidden" aria-label="打开菜单">
              <GlassEffect className="h-11 w-11 items-center justify-center rounded-full">
                {isMobileMenuOpen ? <X className="h-6 w-6 text-white" /> : <Menu className="h-6 w-6 text-white" />}
              </GlassEffect>
            </button>
          </div>
        </GlassEffect>

        {isMobileMenuOpen && (
          <GlassEffect className="z-20 mt-3 rounded-3xl p-3 lg:hidden" contentClassName="w-full">
            <div className="grid gap-1">
              {[...primaryNavigation, { label: '首页', to: '/' }].map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`rounded-2xl px-3 py-2 text-left text-sm text-white hover:bg-white/15 ${isCurrent(item.to) ? 'bg-white/20' : ''}`}
                >
                  {item.label}
                </Link>
              ))}
              <button
                type="button"
                onClick={() => setIsSettingsOpen(true)}
                className="rounded-2xl px-3 py-2 text-left text-sm text-white hover:bg-white/15"
              >
                系统设置
              </button>
            </div>
          </GlassEffect>
        )}

        <section className="grid min-h-[calc(100vh-140px)] flex-1 items-center gap-8 py-6 sm:py-8 lg:grid-cols-[1.08fr_0.92fr]">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-100/80">{heroSubtitle}</p>
            <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight text-white sm:text-6xl">{heroTitle}</h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-white/75">{heroDescription}</p>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/dashboard">
                <GlassEffect className="rounded-3xl px-5 py-3 hover:scale-105">
                  <span className="flex items-center gap-2 text-sm font-semibold text-white">
                    进入调度中心
                    <ArrowRight className="h-4 w-4" />
                  </span>
                </GlassEffect>
              </Link>
              <Link to="/workspace" className="rounded-3xl border border-white/25 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10">
                打开审批工作台
              </Link>
            </div>
          </div>

          <div className="grid gap-4">
            {statusCards.map(([label, value]) => (
              <GlassEffect key={label} className="rounded-3xl p-5" contentClassName="w-full">
                <div className="flex items-center justify-between gap-5">
                  <p className="text-sm text-white/60">{label}</p>
                  <p className="text-3xl font-bold text-white">{value}</p>
                </div>
              </GlassEffect>
            ))}
          </div>
        </section>
      </div>

      <SystemSettingsModal open={isSettingsOpen} onOpenChange={setIsSettingsOpen} />
    </main>
  )
}

export { NavbarHero }
