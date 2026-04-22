import { useTheme } from '@/components/next/next-themes'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { KeyRound, Moon, ServerCog, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

interface SystemSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const SETTINGS_UPDATED_EVENT = 'docs-agent-settings-updated'

const providerOptions = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'tongyi', label: '通义' },
  { value: 'openai', label: 'OpenAI' },
]

export default function SystemSettingsDialog({ open, onOpenChange }: SystemSettingsDialogProps) {
  const { theme, setTheme } = useTheme()
  const [provider, setProvider] = useState('tongyi')
  const [apiKey, setApiKey] = useState('')

  useEffect(() => {
    if (!open) return

    setProvider(window.localStorage.getItem('docs_agent_ui_provider') || 'tongyi')
    setApiKey(window.localStorage.getItem('docs_agent_ui_api_key') || '')
  }, [open])

  const handleSave = () => {
    window.localStorage.setItem('docs_agent_ui_provider', provider)
    window.localStorage.setItem('docs_agent_ui_api_key', apiKey)
    window.dispatchEvent(new Event(SETTINGS_UPDATED_EVENT))
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl border-cyan-300/12 bg-[linear-gradient(180deg,rgba(8,15,28,0.98),rgba(7,16,31,0.95))]">
        <DialogHeader className="pr-10">
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-cyan-300/15 bg-cyan-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-cyan-100">
            <ServerCog className="h-3.5 w-3.5" />
            系统设置
          </div>
          <DialogTitle className="mt-3">系统配置中心</DialogTitle>
          <DialogDescription>统一管理模型引擎、调用密钥和主题模式。</DialogDescription>
        </DialogHeader>

        <div className="mt-6 grid gap-5">
          <section className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-4">
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">模型服务商</span>
              <div className="rounded-[1.2rem] border border-white/10 bg-black/20 px-4 py-3">
                <select
                  value={provider}
                  onChange={(event) => setProvider(event.target.value)}
                  className="w-full bg-transparent text-sm text-white outline-none"
                >
                  {providerOptions.map((option) => (
                    <option key={option.value} value={option.value} className="bg-slate-950">
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </label>
          </section>

          <section className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-4">
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">API Key</span>
              <div className="flex items-center gap-3 rounded-[1.2rem] border border-white/10 bg-black/20 px-4 py-3">
                <KeyRound className="h-4 w-4 text-cyan-100" />
                <input
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="输入当前服务商的 API Key"
                  className="w-full bg-transparent text-sm text-white placeholder:text-white/35 outline-none"
                />
              </div>
            </label>
          </section>

          <section className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">主题模式</p>
              </div>

              <div className="grid grid-cols-2 gap-2 rounded-[1.2rem] border border-white/10 bg-black/20 p-1.5">
                <button
                  type="button"
                  onClick={() => setTheme('dark')}
                  className={`inline-flex items-center justify-center gap-2 rounded-[0.95rem] px-4 py-2.5 text-sm font-medium transition ${
                    theme === 'dark' ? 'bg-white/15 text-white' : 'text-white/65 hover:bg-white/8 hover:text-white'
                  }`}
                >
                  <Moon className="h-4 w-4" />
                  深色
                </button>
                <button
                  type="button"
                  onClick={() => setTheme('light')}
                  className={`inline-flex items-center justify-center gap-2 rounded-[0.95rem] px-4 py-2.5 text-sm font-medium transition ${
                    theme === 'light' ? 'bg-white/15 text-white' : 'text-white/65 hover:bg-white/8 hover:text-white'
                  }`}
                >
                  <Sun className="h-4 w-4" />
                  浅色
                </button>
              </div>
            </div>
          </section>
        </div>

        <DialogFooter>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-full border border-white/10 bg-white/5 px-5 py-2.5 text-sm font-medium text-white/75 transition hover:bg-white/10 hover:text-white"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-full border border-cyan-300/20 bg-cyan-300/12 px-5 py-2.5 text-sm font-semibold text-cyan-50 transition hover:bg-cyan-300/18"
          >
            保存设置
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export { SETTINGS_UPDATED_EVENT }
