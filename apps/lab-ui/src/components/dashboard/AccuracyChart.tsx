import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { DashEventAccuracy } from '../../api/client'
import { modelColor, DASHBOARD_MODEL_ORDER } from '../../lib/model-colors'

interface AccuracyChartProps {
  events: DashEventAccuracy[]
  modelShorts: string[]
}

interface TooltipPayload {
  dataKey: string
  value: number
  color: string
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipPayload[]; label?: string }) {
  if (!active || !payload?.length) return null
  const sorted = [...payload].sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
  return (
    <div className="bg-card border border-border rounded-lg p-3 text-xs shadow-xl min-w-[160px]">
      <div className="font-semibold text-muted-foreground mb-2 truncate">{label}</div>
      {sorted.map((entry) => (
        <div key={entry.dataKey} className="flex justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: entry.color }} />
            <span className="text-muted-foreground">{entry.dataKey}</span>
          </span>
          <span className="text-foreground font-semibold tabular-nums">
            {entry.value != null ? `${entry.value.toFixed(1)}%` : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function AccuracyChart({ events, modelShorts }: AccuracyChartProps) {
  const [highlighted, setHighlighted] = useState<string | null>(null)

  const chartData = events.map((ev) => {
    const row: Record<string, string | number | null> = { event: ev.event }
    for (const short of modelShorts) {
      const acc = ev.accuracy_by_model[short]?.accuracy
      row[short] = acc != null ? Math.round(acc * 1000) / 10 : null
    }
    return row
  })

  const orderedShorts = DASHBOARD_MODEL_ORDER.filter(s => modelShorts.includes(s))

  const handleLegendClick = (e: { dataKey?: string | number | ((obj: unknown) => unknown) }) => {
    const key = typeof e.dataKey === 'string' ? e.dataKey : null
    if (!key) return
    setHighlighted(prev => prev === key ? null : key)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      className="bg-card border border-border rounded-xl p-5"
    >
      <h3
        className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4"
        style={{ fontFamily: "'Oswald', sans-serif" }}
      >
        Accuracy por Evento
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 30, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
          <XAxis
            dataKey="event"
            tick={{ fill: 'var(--color-muted-foreground)', fontSize: 10 }}
            angle={-35}
            textAnchor="end"
            interval={0}
            height={60}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={[30, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11 }}
            width={40}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            onClick={handleLegendClick}
            wrapperStyle={{ paddingTop: '0.5rem', fontSize: '11px', cursor: 'pointer' }}
          />
          {orderedShorts.map((short) => (
            <Line
              key={short}
              dataKey={short}
              stroke={modelColor(short)}
              strokeWidth={1.5}
              dot={false}
              opacity={highlighted && highlighted !== short ? 0.1 : 1}
              animationDuration={800}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </motion.div>
  )
}
