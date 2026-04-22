import SystemSettingsModal from '@/components/SystemSettingsModal'
import { GlassEffect } from '@/components/ui/liquid-glass'
import { Settings2, TerminalSquare, Workflow, PanelsTopLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

const navigationItems = [
  { label: '调度中心', to: '/dashboard', icon: Workflow },
  { label: '监控终端', to: '/terminal', icon: TerminalSquare },
  { label: '审批工作台', to: '/workspace', icon: PanelsTopLeft },
]

export default function GlobalHeader() {
  const location = useLocation()
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  if (location.pathname === '/') return null

  return (
    <>
      <header className="relative z-20 px-4 py-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1600px]">
          <GlassEffect
            className="rounded-[1.6rem] border border-white/10 px-4 py-3 shadow-[0_18px_60px_rgba(2,6,23,0.35)]"
            contentClassName="flex w-full items-center justify-between gap-4"
          >
            <div className="flex min-w-0 items-center gap-4">
              <Link to="/dashboard" className="flex items-center gap-3 text-white">
                <span className="grid h-10 w-10 place-items-center rounded-2xl bg-cyan-300/15">
                  <Workflow className="h-5 w-5 text-cyan-100" />
                </span>
                <div>
                  <p className="text-sm font-semibold leading-tight">Docs Agent</p>
                  <p className="text-xs text-white/55">系统导航</p>
                </div>
              </Link>

              <nav className="hidden items-center gap-2 md:flex">
                {navigationItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition ${
                        isActive ? 'bg-white/18 text-white' : 'text-white/70 hover:bg-white/10 hover:text-white'
                      }`
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </NavLink>
                ))}
              </nav>
            </div>

            <button type="button" onClick={() => setIsSettingsOpen(true)} className="shrink-0" aria-label="打开系统设置">
              <GlassEffect className="rounded-full px-4 py-2.5 hover:scale-[1.02]">
                <span className="inline-flex items-center gap-2 text-sm font-medium text-white">
                  <Settings2 className="h-4 w-4" />
                  ⚙️ 系统设置
                </span>
              </GlassEffect>
            </button>
          </GlassEffect>
        </div>
      </header>

      <SystemSettingsModal open={isSettingsOpen} onOpenChange={setIsSettingsOpen} />
    </>
  )
}
