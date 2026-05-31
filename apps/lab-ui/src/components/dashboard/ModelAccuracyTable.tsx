import type { DashModelAvg } from '../../api/client'
import { modelColor, DASHBOARD_MODEL_ORDER } from '../../lib/model-colors'

interface ModelAccuracyTableProps {
  avgByModel: Record<string, DashModelAvg>
  modelShorts: string[]
}

export default function ModelAccuracyTable({ avgByModel, modelShorts }: ModelAccuracyTableProps) {
  const sorted = DASHBOARD_MODEL_ORDER
    .filter(s => modelShorts.includes(s))
    .slice()
    .sort((a, b) => {
      const va = avgByModel[a]?.avg_accuracy ?? -1
      const vb = avgByModel[b]?.avg_accuracy ?? -1
      return vb - va
    })

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        Accuracy Media Histórica
      </h3>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left text-muted-foreground font-medium pb-2">Modelo</th>
            <th className="text-right text-muted-foreground font-medium pb-2">Accuracy</th>
            <th className="text-right text-muted-foreground font-medium pb-2">Aciertos</th>
            <th className="text-right text-muted-foreground font-medium pb-2">Eventos</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((short, i) => {
            const m = avgByModel[short]
            if (!m) return null
            const acc = m.avg_accuracy != null ? `${(m.avg_accuracy * 100).toFixed(1)}%` : '—'
            const hits = m.total_correct != null ? `${m.total_correct} / ${m.total_fights}` : '—'
            return (
              <tr
                key={short}
                className={`border-b border-border/50 hover:bg-white/5 transition-colors${i === 0 ? ' text-foreground' : ''}`}
              >
                <td className="py-2">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: modelColor(short) }}
                    />
                    <span className={i < 3 ? 'font-semibold text-foreground' : 'text-muted-foreground'}>
                      {short}
                    </span>
                  </div>
                </td>
                <td className="text-right tabular-nums font-semibold text-foreground py-2">{acc}</td>
                <td className="text-right tabular-nums text-muted-foreground py-2">{hits}</td>
                <td className="text-right tabular-nums text-muted-foreground py-2">{m.n_events}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
