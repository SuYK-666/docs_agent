import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useGlobalAppContext } from '@/context/GlobalAppContext'
import { Eye, EyeOff, KeyRound, ServerCog } from 'lucide-react'
import { useEffect, useState } from 'react'

export const SETTINGS_UPDATED_EVENT = 'docs-agent-settings-updated'
const API_BASE = ((import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL || '').replace(/\/$/, '')

interface SystemSettingsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type LlmModelOption = {
  value: string
  label: string
  recommended?: boolean
}

type LlmProviderOption = {
  value: string
  label: string
  defaultModel: string
  models: LlmModelOption[]
  supportsCustomModel?: boolean
}

type TestState =
  | { status: 'idle'; message: string }
  | { status: 'testing'; message: string }
  | { status: 'success'; message: string }
  | { status: 'error'; message: string }

const fallbackProviderOptions: LlmProviderOption[] = [
  {
    value: 'deepseek',
    label: 'DeepSeek',
    defaultModel: 'deepseek-chat',
    models: [
      { value: 'deepseek-chat', label: 'deepseek-chat（兼容默认）', recommended: true },
      { value: 'deepseek-reasoner', label: 'deepseek-reasoner（推理模型）' },
      { value: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
      { value: 'deepseek-v4-pro', label: 'DeepSeek V4 Pro' },
    ],
  },
  {
    value: 'tongyi',
    label: '通义',
    defaultModel: 'qwen-max',
    models: [
      { value: 'qwen-max', label: 'Qwen Max', recommended: true },
      { value: 'qwen-plus', label: 'Qwen Plus' },
      { value: 'qwen3-max', label: 'Qwen3 Max' },
      { value: 'qwen3.6-plus', label: 'Qwen3.6 Plus' },
    ],
  },
  {
    value: 'wenxin',
    label: '文心',
    defaultModel: 'ernie-4.0-turbo-8k',
    models: [
      { value: 'ernie-4.5-turbo-128k', label: 'ERNIE 4.5 Turbo 128K' },
      { value: 'ernie-4.5-turbo-32k', label: 'ERNIE 4.5 Turbo 32K' },
      { value: 'ernie-4.0-turbo-8k', label: 'ERNIE 4.0 Turbo 8K（兼容旧配置）', recommended: true },
    ],
  },
  {
    value: 'doubao',
    label: '豆包',
    defaultModel: 'doubao-pro-32k',
    models: [
      { value: 'doubao-pro-32k', label: 'Doubao Pro 32K（公共接入点/兼容旧配置）', recommended: true },
      { value: 'doubao-lite-32k', label: 'Doubao Lite 32K（公共接入点）' },
      { value: 'doubao-seed-1-6-251015', label: 'Doubao Seed 1.6 251015' },
      { value: 'doubao-seed-1-6-flash-250828', label: 'Doubao Seed 1.6 Flash 250828' },
    ],
  },
  {
    value: 'kimi',
    label: 'Kimi',
    defaultModel: 'moonshot-v1-8k',
    models: [
      { value: 'kimi-k2.6', label: 'Kimi K2.6' },
      { value: 'kimi-k2.5', label: 'Kimi K2.5' },
      { value: 'moonshot-v1-32k', label: 'Moonshot V1 32K' },
      { value: 'moonshot-v1-8k', label: 'Moonshot V1 8K', recommended: true },
    ],
  },
  {
    value: 'zhipu',
    label: '智谱',
    defaultModel: 'GLM-4-Flash-250414',
    models: [
      { value: 'GLM-4-Flash-250414', label: 'GLM-4-Flash-250414', recommended: true },
      { value: 'GLM-4-FlashX-250414', label: 'GLM-4-FlashX-250414' },
      { value: 'GLM-4-Air-250414', label: 'GLM-4-Air-250414' },
      { value: 'GLM-4-Plus', label: 'GLM-4-Plus' },
    ],
  },
]

function getProviderOption(options: LlmProviderOption[], provider: string) {
  return options.find((option) => option.value === provider) || options[0]
}

function getDefaultModel(option: LlmProviderOption | undefined) {
  if (!option) return ''
  return option.defaultModel || option.models.find((model) => model.recommended)?.value || option.models[0]?.value || ''
}

function resolveModelSelection(option: LlmProviderOption | undefined, savedModel: string) {
  const normalized = savedModel.trim()
  if (!option) return { selectedModel: '', customModel: normalized }
  if (normalized && option.models.some((model) => model.value === normalized)) {
    return { selectedModel: normalized, customModel: '' }
  }
  return { selectedModel: getDefaultModel(option), customModel: normalized }
}

export default function SystemSettingsModal({ open, onOpenChange }: SystemSettingsModalProps) {
  const { formState, setFormState } = useGlobalAppContext()
  const [providerOptions, setProviderOptions] = useState<LlmProviderOption[]>(fallbackProviderOptions)
  const [provider, setProvider] = useState('tongyi')
  const [selectedModel, setSelectedModel] = useState('')
  const [customModel, setCustomModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false)
  const [testState, setTestState] = useState<TestState>({ status: 'idle', message: '' })

  useEffect(() => {
    if (!open) return

    const savedProvider = formState.provider || window.localStorage.getItem('docs_agent_ui_provider') || 'tongyi'
    const savedModel = window.localStorage.getItem('docs_agent_ui_model') || ''
    const initialOption = getProviderOption(providerOptions, savedProvider)
    const initialModel = resolveModelSelection(initialOption, savedModel)
    setProvider(savedProvider)
    setSelectedModel(initialModel.selectedModel)
    setCustomModel(initialModel.customModel)
    setApiKey(formState.apiKey || window.localStorage.getItem('docs_agent_ui_api_key') || '')
    setIsApiKeyVisible(false)
    setTestState({ status: 'idle', message: '' })

    let cancelled = false
    void fetch(`${API_BASE}/api/llm/models`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (cancelled || !data || !Array.isArray(data.providers)) return
        const nextOptions = data.providers as LlmProviderOption[]
        setProviderOptions(nextOptions)
        const nextOption = getProviderOption(nextOptions, savedProvider)
        const nextModel = resolveModelSelection(nextOption, savedModel)
        setSelectedModel(nextModel.selectedModel)
        setCustomModel(nextModel.customModel)
      })
      .catch(() => {
        // Keep local fallback presets when the backend list is unavailable.
      })

    return () => {
      cancelled = true
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formState.apiKey, formState.provider, open])

  const providerOption = getProviderOption(providerOptions, provider)
  const effectiveModel = (customModel.trim() || selectedModel || getDefaultModel(providerOption)).trim()

  const handleProviderChange = (nextProvider: string) => {
    const nextOption = getProviderOption(providerOptions, nextProvider)
    setProvider(nextProvider)
    setSelectedModel(getDefaultModel(nextOption))
    setCustomModel('')
    setTestState({ status: 'idle', message: '' })
  }

  const handleSave = () => {
    const normalizedModelName = effectiveModel

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

  const handleTestConnection = async () => {
    if (!apiKey.trim()) {
      setTestState({ status: 'error', message: '请先填写 API Key。' })
      return
    }

    setTestState({ status: 'testing', message: '正在测试模型连接...' })
    try {
      const response = await fetch(`${API_BASE}/api/llm/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          model: effectiveModel,
          api_key: apiKey,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || !data.ok) {
        setTestState({
          status: 'error',
          message: String(data.error || '模型连接测试失败。'),
        })
        return
      }

      setTestState({
        status: 'success',
        message: `测试通过：${data.provider || provider} / ${data.model || effectiveModel}`,
      })
    } catch (error) {
      setTestState({
        status: 'error',
        message: error instanceof Error ? error.message : '模型连接测试失败。',
      })
    }
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
                  onChange={(event) => handleProviderChange(event.target.value)}
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
                <div className="rounded-[1.2rem] border border-white/10 bg-black/20 px-4 py-3">
                  <select
                    value={selectedModel}
                    onChange={(event) => {
                      setSelectedModel(event.target.value)
                      setCustomModel('')
                      setTestState({ status: 'idle', message: '' })
                    }}
                    className="w-full bg-transparent text-sm text-white outline-none"
                  >
                    {providerOption?.models.map((model) => (
                      <option key={model.value} value={model.value} className="bg-slate-950">
                        {model.label}{model.recommended ? ' · 推荐' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <input
                  value={customModel}
                  onChange={(event) => {
                    setCustomModel(event.target.value)
                    setTestState({ status: 'idle', message: '' })
                  }}
                  placeholder="自定义模型或专属接入点，例如 ep-xxxx"
                  className="rounded-[1.2rem] border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-white/35 outline-none transition focus:border-cyan-300/35"
                />
                <span className="text-xs text-white/40">实际使用：{effectiveModel || '系统默认型号'}</span>
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

              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={testState.status === 'testing'}
                  className="rounded-full border border-cyan-300/20 bg-cyan-300/12 px-4 py-2 text-xs font-semibold text-cyan-50 transition hover:bg-cyan-300/18 disabled:cursor-wait disabled:opacity-60"
                >
                  测试连接
                </button>
                {testState.message && (
                  <span
                    className={
                      testState.status === 'success'
                        ? 'text-xs text-emerald-200'
                        : testState.status === 'error'
                          ? 'text-xs text-rose-200'
                          : 'text-xs text-white/45'
                    }
                  >
                    {testState.message}
                  </span>
                )}
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
