import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { DashEventAccuracy, DashModelAvg } from '../../api/client'
import { modelColor, DASHBOARD_MODEL_ORDER } from '../../lib/model-colors'

interface ModelRankingProps {
  events: DashEventAccuracy[]
  avgByModel: Record<string, DashModelAvg>
  modelShorts: string[]
}

function getRankLabel(i: number): string {
  if (i === 0) return '1'
  if (i === 1) return '2'
  if (i === 2) return '3'
  return `${i + 1}`
}

export default function ModelRanking({ events, avgByModel, modelShorts }: ModelRankingProps) {
  const [scope, setScope] = useState<string>('global')

  const scopeOptions = [
    { value: 'global', label: 'Global (media)' },
    ...events.map(ev => ({ value: ev.event, label: ev.event })),
  ]

  const accuracies: Record<string, number | null> = {}
  if (scope === 'global') {
    for (const s of modelShorts) {
      accuracies[s] = avgByModel[s]?.avg_accuracy ?? null
    }
  } else {
    const ev = events.find(e => e.event === scope)
    for (const s of modelShorts) {
      accuracies[s] = ev?.accuracy_by_model[s]?.accuracy ?? null
    }
  }

  const globalAvgs: Record<string, number | null> = {}
  for (const s of modelShorts) {
    globalAvgs[s] = avgByModel[s]?.avg_accuracy ?? null
  }

  const sorted = DASHBOARD_MODEL_ORDER
    .filter(s => modelShorts.includes(s))
    .slice()
    .sort((a, b) => {
      const va = accuracies[a] ?? -1
      const vb = accuracies[b] ?? -1
      return vb - va
    })

  const globalMean =
    Object.values(globalAvgs).filter((v): v is number => v != null).reduce((a, b) => a + b, 0) /
    (modelShorts.length || 1)

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest">
          Ranking
        </h3>
        <select
          value={scope}
          onChange={e => setScope(e.target.value)}
          className="text-xs bg-white/5 border border-border text-muted-foreground rounded-lg px-2 py-1 outline-none cursor-pointer max-w-[140px] truncate"
        >
          {scopeOptions.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {sorted.map((short, i) => {
            const acc = accuracies[short]
            const pct = acc != null ? acc * 100 : null
            const delta = acc != null ? (acc - globalMean) * 100 : null
            const color = modelColor(short)

            return (
              <motion.div
                key={short}
                layout
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-2"
              >
                <span className="text-sm w-6 text-center flex-shrink-0 tabular-nums text-muted-foreground">
                  {getRankLabel(i)}
                </span>
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
                <span className="text-muted-foreground text-xs w-9 flex-shrink-0">{short}</span>
                <div className="flex-1 bg-border rounded-full h-2 overflow-hidden">
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: color }}
                    initial={{ width: 0 }}
                    animate={{ width: pct != null ? `${pct}%` : '0%' }}
                    transition={{ duration: 0.5, ease: 'easeOut' }}
                  />
                </div>
                <span className="text-foreground text-xs font-semibold w-11 text-right tabular-nums">
                  {pct != null ? `${pct.toFixed(1)}%` : '—'}
                </span>
                {delta != null && (
                  <span
                    className={`text-[10px] w-12 text-right tabular-nums ${
                      delta > 0 ? 'text-success' : delta < 0 ? 'text-destructive' : 'text-muted-foreground'
                    }`}
                  >
                    {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
                  </span>
                )}
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
