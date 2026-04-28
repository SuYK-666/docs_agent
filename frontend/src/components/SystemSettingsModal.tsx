import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useGlobalAppContext } from '@/context/GlobalAppContext'
import { Eye, EyeOff, KeyRound, ServerCog } from 'lucide-react'
import { useEffect, useState } from 'react'

export const SETTINGS_UPDATED_EVENT = 'docs-agent-settings-updated'

interface SystemSettingsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const providerOptions = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'tongyi', label: '通义' },
  { value: 'wenxin', label: '文心' },
  { value: 'doubao', label: '豆包' },
  { value: 'kimi', label: 'Kimi' },
  { value: 'zhipu', label: '智谱' },
]

export default function SystemSettingsModal({ open, onOpenChange }: SystemSettingsModalProps) {
  const { formState, setFormState } = useGlobalAppContext()
  const [provider, setProvider] = useState('tongyi')
  const [modelName, setModelName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false)

  useEffect(() => {
    if (!open) return

    setProvider(formState.provider || window.localStorage.getItem('docs_agent_ui_provider') || 'tongyi')
    setModelName(window.localStorage.getItem('docs_agent_ui_model') || '')
    setApiKey(formState.apiKey || window.localStorage.getItem('docs_agent_ui_api_key') || '')
    setIsApiKeyVisible(false)
  }, [formState.apiKey, formState.provider, open])

  const handleSave = () => {
    const normalizedModelName = modelName.trim()

    window.localStorage.setItem('docs_agent_ui_provider', provider)
    window.localStorage.setItem('docs_agent_ui_model', normalizedModelName)
    window.localStorage.setItem('docs_agent_ui_api_key', apiKey)
    setFormState((current) => ({
      ...current,
      provider,
      apiKey,
    }))
    window.dispatchEvent(new Event(SETTINGS_UPDATED_EVENT))
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
            <div className="grid gap-4">
              <label className="grid gap-2">
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">模型型号</span>
                <input
                  value={modelName}
                  onChange={(event) => setModelName(event.target.value)}
                  placeholder="例如：qwen-max (留空则自动使用系统预设最优模型)"
                  className="rounded-[1.2rem] border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-white/35 outline-none transition focus:border-cyan-300/35"
                />
                {!modelName.trim() && (
                  <span className="text-xs text-white/40">当前将使用 {provider} 的默认预设型号</span>
                )}
              </label>

              <div className="grid gap-2">
                <label className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55" htmlFor="system-api-key">
                  安全密钥
                </label>
                <div className="flex items-center gap-3 rounded-[1.2rem] border border-white/10 bg-black/20 px-4 py-3">
                  <KeyRound className="h-4 w-4 text-cyan-100" />
                  <input
                    id="system-api-key"
                    type={isApiKeyVisible ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder="输入调用密钥"
                    className="min-w-0 flex-1 bg-transparent text-sm text-white placeholder:text-white/35 outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setIsApiKeyVisible((current) => !current)}
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-white/60 transition hover:bg-white/10 hover:text-white"
                    aria-label={isApiKeyVisible ? '隐藏 API Key' : '显示 API Key'}
                    aria-pressed={isApiKeyVisible}
                  >
                    {isApiKeyVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
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
