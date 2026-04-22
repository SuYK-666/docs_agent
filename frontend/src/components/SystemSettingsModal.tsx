import { useTheme } from '@/components/next/next-themes'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useGlobalAppContext } from '@/context/GlobalAppContext'
import { KeyRound, Moon, ServerCog, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

export const SETTINGS_UPDATED_EVENT = 'docs-agent-settings-updated'

interface SystemSettingsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const providerOptions = [
  { value: 'deepseek', label: 'DeepSeek (V3)' },
  { value: 'tongyi', label: '通义 (Qwen-Max)' },
  { value: 'wenxin', label: '文心 (Ernie-4.0)' },
  { value: 'doubao', label: '豆包 AI (Pro-32k)' },
  { value: 'kimi', label: 'Kimi (Moonshot-8k)' },
  { value: 'zhipu', label: '智谱 AI (GLM-4-Flash)' },
]

export default function SystemSettingsModal({ open, onOpenChange }: SystemSettingsModalProps) {
  const { formState, setFormState } = useGlobalAppContext()
  const { resolvedTheme, setTheme, theme } = useTheme()
  const [provider, setProvider] = useState('tongyi')
  const [apiKey, setApiKey] = useState('')
  const [selectedTheme, setSelectedTheme] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    if (!open) return

    const savedTheme = window.localStorage.getItem('docs_agent_theme')
    const currentTheme = savedTheme || resolvedTheme || theme || 'dark'

    setProvider(formState.provider || window.localStorage.getItem('docs_agent_ui_provider') || 'tongyi')
    setApiKey(formState.apiKey || window.localStorage.getItem('docs_agent_ui_api_key') || '')
    setSelectedTheme(currentTheme === 'light' ? 'light' : 'dark')
  }, [formState.apiKey, formState.provider, open, resolvedTheme, theme])

  const handleSave = () => {
    window.localStorage.setItem('docs_agent_theme', selectedTheme)
    window.localStorage.setItem('docs_agent_ui_provider', provider)
    window.localStorage.setItem('docs_agent_ui_api_key', apiKey)
    setFormState((current) => ({
      ...current,
      provider,
      apiKey,
    }))
    window.dispatchEvent(new Event(SETTINGS_UPDATED_EVENT))
    setTheme(selectedTheme)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl border-white/10 bg-[linear-gradient(180deg,rgba(11,18,32,0.98),rgba(9,15,28,0.96))]">
        <DialogHeader className="pr-10">
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-cyan-300/15 bg-cyan-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-cyan-100">
            <ServerCog className="h-3.5 w-3.5" />
            系统设置
          </div>
          <DialogTitle className="mt-3">系统底层安全配置</DialogTitle>
        </DialogHeader>

        <div className="mt-6 grid gap-5">
          <section className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-4">
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">模型引擎</span>
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
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">安全密钥</span>
              <div className="flex items-center gap-3 rounded-[1.2rem] border border-white/10 bg-black/20 px-4 py-3">
                <KeyRound className="h-4 w-4 text-cyan-100" />
                <input
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="输入调用密钥"
                  className="w-full bg-transparent text-sm text-white placeholder:text-white/35 outline-none"
                />
              </div>
            </label>
          </section>

          <section className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">界面主题</p>
              </div>

              <div className="grid grid-cols-2 gap-2 rounded-[1.2rem] border border-white/10 bg-black/20 p-1.5">
                <button
                  type="button"
                  onClick={() => setSelectedTheme('dark')}
                  className={`inline-flex items-center justify-center gap-2 rounded-[0.95rem] px-4 py-2.5 text-sm font-medium transition ${
                    selectedTheme === 'dark' ? 'bg-white/15 text-white' : 'text-white/65 hover:bg-white/8 hover:text-white'
                  }`}
                >
                  <Moon className="h-4 w-4" />
                  深色
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedTheme('light')}
                  className={`inline-flex items-center justify-center gap-2 rounded-[0.95rem] px-4 py-2.5 text-sm font-medium transition ${
                    selectedTheme === 'light' ? 'bg-white/15 text-white' : 'text-white/65 hover:bg-white/8 hover:text-white'
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
            保存系统配置
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
