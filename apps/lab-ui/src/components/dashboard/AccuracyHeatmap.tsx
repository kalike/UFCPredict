import type { DashEventAccuracy, DashModelAvg } from '../../api/client'
import { modelColor, DASHBOARD_MODEL_ORDER } from '../../lib/model-colors'

function heatBg(accuracy: number | null): string {
  if (accuracy == null) return 'transparent'
  const norm = Math.max(0, Math.min(1, (accuracy * 100 - 40) / 60))

  // Interpolacion HSL en 3 stops: rojo vivo -> naranja saturado -> verde
  // Evita la ruta olivo/marron que produce la interpolacion RGB lineal con B fijo.
  const stops: Array<[number, number, number]> = [
    [0, 78, 50],   // 40% - rojo
    [28, 85, 54],  // 70% - naranja vivo
    [135, 62, 42], // 100% - verde
  ]
  const [a, b] = norm < 0.5 ? [stops[0], stops[1]] : [stops[1], stops[2]]
  const t = norm < 0.5 ? norm / 0.5 : (norm - 0.5) / 0.5
  const h = a[0] + (b[0] - a[0]) * t
  const s = a[1] + (b[1] - a[1]) * t
  const l = a[2] + (b[2] - a[2]) * t
  return `hsla(${h.toFixed(1)}, ${s.toFixed(1)}%, ${l.toFixed(1)}%, 0.7)`
}

interface AccuracyHeatmapProps {
  events: DashEventAccuracy[]
  avgByModel: Record<string, DashModelAvg>
  modelShorts: string[]
}

export default function AccuracyHeatmap({ events, avgByModel, modelShorts }: AccuracyHeatmapProps) {
  const orderedShorts = DASHBOARD_MODEL_ORDER.filter(s => modelShorts.includes(s))

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        Accuracy por Modelo × Evento
      </h3>
      <div className="overflow-x-auto">
        <table className="text-xs border-collapse w-full">
          <thead>
            <tr>
              <th className="text-left text-muted-foreground font-medium py-2 pr-3 pl-1 sticky left-0 bg-card z-10 min-w-[80px]">
                Modelo
              </th>
              {events.map((ev) => (
                <th
                  key={ev.event}
                  className="text-center text-muted-foreground font-medium px-1.5 py-2 whitespace-nowrap max-w-[80px]"
                  title={ev.event}
                >
                  <span className="block truncate max-w-[72px]">
                    {ev.event.replace(/UFC\s+/i, '').slice(0, 12)}
                  </span>
                </th>
              ))}
              <th className="text-center text-muted-foreground font-semibold px-2 py-2 sticky right-0 bg-card z-10 min-w-[52px]">
                Media
              </th>
            </tr>
          </thead>
          <tbody>
            {orderedShorts.map((short) => {
              const avg = avgByModel[short]?.avg_accuracy
              return (
                <tr key={short} className="hover:bg-white/5 transition-colors">
                  <td className="sticky left-0 bg-card z-10 py-1.5 pr-3 pl-1">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ background: modelColor(short) }}
                      />
                      <span className="text-muted-foreground font-medium">{short}</span>
                    </div>
                  </td>
                  {events.map((ev) => {
                    const acc = ev.accuracy_by_model[short]?.accuracy
                    return (
                      <td
                        key={ev.event}
                        className="text-center px-1.5 py-1.5 rounded"
                        style={{ background: heatBg(acc ?? null) }}
                        title={acc != null ? `${(acc * 100).toFixed(1)}%` : '—'}
                      >
                        <span className="tabular-nums text-foreground font-medium">
                          {acc != null ? `${(acc * 100).toFixed(0)}%` : '—'}
                        </span>
                      </td>
                    )
                  })}
                  <td
                    className="text-center px-2 py-1.5 sticky right-0 bg-card z-10"
                    style={{ background: heatBg(avg ?? null) }}
                  >
                    <span className="tabular-nums text-foreground font-semibold">
                      {avg != null ? `${(avg * 100).toFixed(1)}%` : '—'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
