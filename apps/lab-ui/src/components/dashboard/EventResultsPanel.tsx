import { motion } from 'framer-motion'
import { CheckCircle2, XCircle, X } from 'lucide-react'
import { useEventFights } from './useDashboard'
import { Skeleton } from '../ui'

interface EventResultsPanelProps {
  eventName: string
  onClose: () => void
}

function fmtPctRaw(pct: number): string {
  return `${pct.toFixed(1)}%`
}

export default function EventResultsPanel({ eventName, onClose }: EventResultsPanelProps) {
  const { data, isLoading, error } = useEventFights(eventName)

  const correct = data?.fights?.filter(f => f.correct) ?? []
  const wrong = data?.fights?.filter(f => !f.correct) ?? []

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.25 }}
      className="bg-card border border-border rounded-xl p-5"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-foreground font-semibold">{eventName}</h3>
          {data?.fights && data.fights.length > 0 && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {data.fights.length} peleas · {fmtPctRaw((correct.length / data.fights.length) * 100)} consenso
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors p-1"
          aria-label="Cerrar"
        >
          <X size={16} />
        </button>
      </div>

      {error ? (
        <p className="text-xs text-muted-foreground text-center py-4">
          No se pudieron cargar las peleas de este evento
        </p>
      ) : isLoading ? (
        <div className="grid grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {/* Correctas */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle2 size={14} className="text-success" />
              <span className="text-sm font-semibold text-success">Acertadas ({correct.length})</span>
            </div>
            <div className="space-y-2">
              {correct.map((fight, i) => (
                <div
                  key={i}
                  className="bg-success/5 border border-success/20 rounded-lg px-3 py-2"
                >
                  <div className="text-xs text-foreground font-medium truncate">
                    {fight.predicted_winner}{' '}
                    <span className="text-muted-foreground">vs</span>{' '}
                    {fight.predicted_winner === fight.fighter_1 ? fight.fighter_2 : fight.fighter_1}
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">
                    {fmtPctRaw(fight.consensus_pct)} consenso
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Falladas */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <XCircle size={14} className="text-destructive" />
              <span className="text-sm font-semibold text-destructive">Falladas ({wrong.length})</span>
            </div>
            <div className="space-y-2">
              {wrong.map((fight, i) => (
                <div
                  key={i}
                  className="bg-destructive/5 border border-destructive/20 rounded-lg px-3 py-2"
                >
                  <div className="text-xs">
                    <span className="text-destructive font-medium">Pred:</span>{' '}
                    <span className="text-foreground">{fight.predicted_winner}</span>
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">
                    <span className="text-success">Real:</span>{' '}
                    {fight.real_winner}
                    {' · '}{fmtPctRaw(fight.consensus_pct)} consenso
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </motion.div>
  )
}
