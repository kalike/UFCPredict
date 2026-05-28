import { CheckCircle2, Clock } from 'lucide-react'
import { motion } from 'framer-motion'
import type { DashEventAccuracy } from '../../api/client'
import { fmtDate, fmtPct } from '../../lib/formatters'

interface EventsTableProps {
  events: DashEventAccuracy[]
  selectedEvent: string | null
  onSelectEvent: (event: string) => void
}

function cn(...classes: (string | false | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ')
}

export default function EventsTable({ events, selectedEvent, onSelectEvent }: EventsTableProps) {
  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        Todos los Eventos
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-[10px] uppercase tracking-widest text-muted-foreground">
              <th className="text-left font-medium pb-2 pr-4">Evento</th>
              <th className="text-left font-medium pb-2 pr-4">Fecha</th>
              <th className="text-right font-medium pb-2 pr-4">Aciertos</th>
              <th className="text-right font-medium pb-2 pr-4">Accuracy</th>
              <th className="text-left font-medium pb-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev, idx) => {
              const isSelected = selectedEvent === ev.event
              const isPast = ev.is_past
              return (
                <motion.tr
                  key={ev.event}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2, delay: idx * 0.02 }}
                  onClick={() => isPast && onSelectEvent(ev.event)}
                  className={cn(
                    'border-b border-border/40 transition-all duration-150',
                    isPast
                      ? 'cursor-pointer hover:bg-white/5'
                      : 'opacity-50 cursor-default',
                    isSelected && 'bg-accent/5 border-l-2 border-accent',
                  )}
                >
                  <td className={cn('py-2.5 pr-4', isSelected ? 'pl-3' : 'pl-1')}>
                    <span className={cn('font-medium', isPast ? 'text-foreground' : 'text-muted-foreground')}>
                      {ev.event}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 text-muted-foreground text-xs tabular-nums">
                    {fmtDate(ev.date)}
                  </td>
                  <td className="py-2.5 pr-4 text-right tabular-nums text-xs">
                    {isPast ? (
                      <span>
                        <span className="text-success font-semibold">{ev.n_correct}</span>
                        <span className="text-muted-foreground">/{ev.n_fights_valid}</span>
                      </span>
                    ) : (
                      <span className="text-muted-foreground">{ev.n_fights}</span>
                    )}
                  </td>
                  <td className="py-2.5 pr-4 text-right">
                    {ev.overall_accuracy != null ? (
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 bg-border rounded-full h-1.5 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-accent"
                            style={{ width: `${ev.overall_accuracy * 100}%` }}
                          />
                        </div>
                        <span className="tabular-nums text-xs text-foreground font-semibold w-10 text-right">
                          {fmtPct(ev.overall_accuracy)}
                        </span>
                      </div>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </td>
                  <td className="py-2.5">
                    {isPast ? (
                      <span className="flex items-center gap-1 text-success text-xs">
                        <CheckCircle2 size={12} />
                        Verificado
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-accent text-xs">
                        <Clock size={12} />
                        Pendiente
                      </span>
                    )}
                  </td>
                </motion.tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
