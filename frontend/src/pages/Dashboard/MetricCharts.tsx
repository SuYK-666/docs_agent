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

export default function MetricCharts() {
  const { historyRecords } = useGlobalAppContext()
  const chartContainerRef = useRef<HTMLDivElement | null>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)
  const [kpi, setKpi] = useState<MetricState>(defaultMetricState)

  const hasHistory = historyRecords.length > 0
  const latestRecord = historyRecords[historyRecords.length - 1] || null

  const chartSeries = useMemo(
    () =>
      historyRecords.map((record, index) => ({
        label: `Task-${String(index + 1).padStart(2, '0')}`,
        throughputCount: record.throughputCount || record.fileCount || record.files.length || 0,
        averageConfidence: record.averageConfidence,
      })),
    [historyRecords],
  )

  useEffect(() => {
    let frameId = 0
    const targets = {
      throughput: latestRecord?.throughputCount || latestRecord?.fileCount || latestRecord?.files.length || 0,
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
  }, [kpi.confidence.current, kpi.hitRate.current, kpi.throughput.current, latestRecord])

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
          type: 'cross',
          crossStyle: { color: '#64748b' },
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
          startValue: Math.max(chartSeries.length - 8, 0),
          endValue: Math.max(chartSeries.length - 1, 0),
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
        },
      ],
      xAxis: [
        {
          type: 'category',
          data: chartSeries.map((item) => item.label),
          axisPointer: { type: 'shadow' },
          axisLine: { lineStyle: { color: '#475569' } },
          axisLabel: { color: '#94a3b8', fontSize: 10 },
        },
      ],
      yAxis: [
        {
          type: 'value',
          name: '文件数',
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
          name: '吞吐量',
          type: 'bar',
          barWidth: '10%',
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#3b82f6' },
              { offset: 1, color: '#1d4ed8' },
            ]),
            borderRadius: [4, 4, 0, 0],
          },
          data: chartSeries.map((item) => item.throughputCount),
        },
        {
          name: '平均置信度',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          itemStyle: { color: '#10b981' },
          lineStyle: {
            width: 2,
            shadowColor: 'rgba(16, 185, 129, 0.5)',
            shadowBlur: 10,
          },
          data: chartSeries.map((item) => item.averageConfidence),
        },
      ],
    })
  }, [chartSeries])

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
