import { useGlobalAppContext } from '@/context/GlobalAppContext'
import { GlassEffect } from '@/components/ui/liquid-glass'
import * as echarts from 'echarts'
import { Activity, BarChart3, BrainCircuit } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

type MetricKey = 'throughput' | 'hitRate' | 'confidence'

type MetricState = Record<
  MetricKey,
  {
    current: number
    target: number
  }
>

type ChartPoint = {
  label: string
  totalTokens: number
  averageConfidence: number
}

type DenseAxisPayload = {
  categories: string[]
  labelMap: Record<string, string>
  lineData: Array<[string, number]>
}

const defaultMetricState: MetricState = {
  throughput: { current: 0, target: 0 },
  hitRate: { current: 0, target: 0 },
  confidence: { current: 0, target: 0 },
}

const metricCards = [
  {
    key: 'throughput' as const,
    label: '吞吐量',
    icon: Activity,
    accent: 'text-cyan-100',
    renderValue: (value: number, hasData: boolean) => (hasData ? new Intl.NumberFormat('zh-CN').format(Math.floor(value)) : '--'),
  },
  {
    key: 'hitRate' as const,
    label: 'RAG 命中率',
    icon: BarChart3,
    accent: 'text-emerald-100',
    renderValue: (value: number, hasData: boolean) => (hasData ? `${value.toFixed(1)}%` : '--'),
  },
  {
    key: 'confidence' as const,
    label: '平均置信度',
    icon: BrainCircuit,
    accent: 'text-amber-100',
    renderValue: (value: number, hasData: boolean) => (hasData ? value.toFixed(2) : '--'),
  },
]

function buildDenseAxis(points: ChartPoint[]): DenseAxisPayload {
  if (points.length === 0) {
    return {
      categories: [],
      labelMap: {},
      lineData: [],
    }
  }

  const sidePadding = Math.max(3, Math.ceil(points.length / 2) + 1)
  const categories: string[] = []
  const labelMap: Record<string, string> = {}
  const lineData: Array<[string, number]> = []

  for (let i = 0; i < sidePadding; i += 1) {
    categories.push(`pad-start-${i}`)
  }

  points.forEach((point, index) => {
    const slotKey = `task-slot-${index}`
    categories.push(slotKey)
    labelMap[slotKey] = point.label
    lineData.push([slotKey, point.averageConfidence])

    if (index < points.length - 1) {
      categories.push(`task-gap-${index}`)
    }
  })

  for (let i = 0; i < sidePadding; i += 1) {
    categories.push(`pad-end-${i}`)
  }

  return {
    categories,
    labelMap,
    lineData,
  }
}

export default function MetricCharts() {
  const { historyRecords } = useGlobalAppContext()
  const chartContainerRef = useRef<HTMLDivElement | null>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)
  const [kpi, setKpi] = useState<MetricState>(defaultMetricState)

  const hasHistory = historyRecords.length > 0
  const latestRecord = useMemo(() => {
    const record = historyRecords[historyRecords.length - 1] || null
    if (!record) return null

    return {
      ...record,
      totalFilesProcessed: historyRecords.reduce((sum, item) => sum + (item.files?.length || 0), 0),
    }
  }, [historyRecords])

  const chartSeries = useMemo<ChartPoint[]>(
    () =>
      historyRecords.map((record, index) => ({
        label: `Task-${String(index + 1).padStart(2, '0')}`,
        totalTokens: record.totalTokens || 0,
        averageConfidence: record.averageConfidence,
      })),
    [historyRecords],
  )

  const denseAxis = useMemo(() => buildDenseAxis(chartSeries), [chartSeries])

  useEffect(() => {
    let frameId = 0
    const targets = {
      throughput: latestRecord?.totalFilesProcessed || 0,
      hitRate: latestRecord?.ragHitRate || 0,
      confidence: latestRecord?.averageConfidence || 0,
    }

    const starts = {
      throughput: kpi.throughput.current,
      hitRate: kpi.hitRate.current,
      confidence: kpi.confidence.current,
    }

    const start = performance.now()
    const duration = 700

    const tick = (timestamp: number) => {
      const progress = Math.min((timestamp - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 4)

      setKpi({
        throughput: {
          current: starts.throughput + (targets.throughput - starts.throughput) * eased,
          target: targets.throughput,
        },
        hitRate: {
          current: starts.hitRate + (targets.hitRate - starts.hitRate) * eased,
          target: targets.hitRate,
        },
        confidence: {
          current: starts.confidence + (targets.confidence - starts.confidence) * eased,
          target: targets.confidence,
        },
      })

      if (progress < 1) {
        frameId = window.requestAnimationFrame(tick)
      }
    }

    frameId = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frameId)
  }, [latestRecord])

  useEffect(() => {
    if (!chartContainerRef.current) return

    chartInstanceRef.current = echarts.init(chartContainerRef.current)

    const resizeChart = () => {
      chartInstanceRef.current?.resize()
    }

    window.addEventListener('resize', resizeChart)
    return () => {
      window.removeEventListener('resize', resizeChart)
      chartInstanceRef.current?.dispose()
      chartInstanceRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!chartInstanceRef.current) return

    chartInstanceRef.current.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow',
        },
        backgroundColor: 'rgba(15, 23, 42, 0.9)',
        borderColor: '#334155',
        textStyle: { color: '#e2e8f0' },
      },
      grid: {
        left: '4%',
        right: '4%',
        top: '12%',
        bottom: '16%',
        containLabel: true,
      },
      dataZoom: [
        {
          type: 'inside',
          startValue: Math.max(denseAxis.categories.length - 15, 0),
          endValue: Math.max(denseAxis.categories.length - 1, 0),
        },
        {
          type: 'slider',
          height: 18,
          bottom: 18,
          borderColor: '#1e293b',
          fillerColor: 'rgba(59, 130, 246, 0.18)',
          backgroundColor: 'rgba(15, 23, 42, 0.55)',
          handleStyle: {
            color: '#93c5fd',
          },
          startValue: Math.max(denseAxis.categories.length - 15, 0),
          endValue: Math.max(denseAxis.categories.length - 1, 0),
        },
      ],
      xAxis: [
        {
          type: 'category',
          data: denseAxis.categories,
          boundaryGap: true,
          axisPointer: { type: 'shadow' },
          axisLine: { lineStyle: { color: '#475569' } },
          axisTick: { show: false },
          axisLabel: {
            color: '#94a3b8',
            fontSize: 10,
            interval: 0,
            formatter: (value: string) => denseAxis.labelMap[value] || '',
          },
        },
      ],
      yAxis: [
        {
          type: 'value',
          name: 'Token 消耗',
          nameTextStyle: { color: '#64748b', fontSize: 10 },
          min: 0,
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#94a3b8', fontSize: 10 },
        },
        {
          type: 'value',
          name: '置信度',
          nameTextStyle: { color: '#64748b', fontSize: 10 },
          min: 0.8,
          max: 1.0,
          splitLine: { show: false },
          axisLabel: { color: '#94a3b8', fontSize: 10 },
        },
      ],
      series: [
        {
          name: '总 Token',
          type: 'line',
          smooth: true,
          symbol: 'none',
          lineStyle: {
            width: 2,
            color: '#3b82f6',
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(59, 130, 246, 0.4)' },
              { offset: 1, color: 'rgba(59, 130, 246, 0.02)' },
            ]),
          },
          data: chartSeries.map((item, index) => [`task-slot-${index}`, item.totalTokens]),
        },
        {
          name: '平均置信度',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          itemStyle: { color: '#a855f7' },
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: '#a855f7',
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(168, 85, 247, 0.32)' },
              { offset: 1, color: 'rgba(168, 85, 247, 0.02)' },
            ]),
          },
          data: denseAxis.lineData,
        },
      ],
    })
  }, [denseAxis])

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_290px] xl:items-stretch">
      <GlassEffect className="rounded-[2rem] p-6" contentClassName="flex h-full w-full flex-col">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-cyan-100/70">指标趋势</p>
            <h3 className="mt-2 text-2xl font-semibold text-white">系统调度历史看板</h3>
          </div>
          <span className="rounded-full border border-white/15 bg-white/8 px-4 py-2 text-sm font-medium text-white/72">
            历史批次 {historyRecords.length} 条
          </span>
        </div>

        <div className="relative flex min-w-0 flex-1">
          <div className="w-full rounded-[1.75rem] border border-white/10 bg-black/18 p-4">
            <div ref={chartContainerRef} className="h-[420px] w-full" />
          </div>

          {!hasHistory && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center">
              <div className="rounded-[1.4rem] border border-white/10 bg-slate-950/82 px-6 py-4 text-center shadow-[0_12px_40px_rgba(2,6,23,0.35)] backdrop-blur">
                <p className="text-base font-semibold text-white">📊 暂无系统调度历史，请先在左侧启动智能解析任务</p>
              </div>
            </div>
          )}
        </div>
      </GlassEffect>

      <div className="grid gap-4">
        {metricCards.map((metric) => (
          <GlassEffect key={metric.label} className="h-full rounded-[1.75rem] p-5" contentClassName="w-full">
            <div className="flex h-full min-h-[145px] flex-col justify-between gap-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm uppercase tracking-[0.16em] text-white/60">{metric.label}</p>
                <span className="grid h-11 w-11 place-items-center rounded-2xl bg-white/12">
                  <metric.icon className={`h-5 w-5 ${metric.accent}`} />
                </span>
              </div>
              <div>
                <p className="text-4xl font-semibold text-white">{metric.renderValue(kpi[metric.key].current, hasHistory)}</p>
              </div>
            </div>
          </GlassEffect>
        ))}
      </div>
    </div>
  )
}
