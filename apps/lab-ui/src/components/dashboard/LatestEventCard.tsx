import { motion } from 'framer-motion'
import { MapPin, Calendar } from 'lucide-react'
import type { DashEventAccuracy } from '../../api/client'
import { modelColor, DASHBOARD_MODEL_ORDER } from '../../lib/model-colors'
import { fmtDate, fmtPct } from '../../lib/formatters'

interface LatestEventCardProps {
  latest: DashEventAccuracy
}

export default function LatestEventCard({ latest }: LatestEventCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.15 }}
      className="bg-card border border-border rounded-xl p-5 flex flex-col gap-4"
    >
      <h3
        className="text-sm font-semibold text-muted-foreground uppercase tracking-widest"
        style={{ fontFamily: "'Oswald', sans-serif" }}
      >
        Último Evento
      </h3>

      {/* Event name + meta */}
      <div>
        <div className="text-foreground font-semibold text-base leading-tight">{latest.event}</div>
        <div className="flex items-center gap-3 mt-1.5">
          {latest.date && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Calendar size={11} />
              {fmtDate(latest.date)}
            </span>
          )}
          {latest.location && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <MapPin size={11} />
              {latest.location}
            </span>
          )}
        </div>
      </div>

      {/* Consensus accuracy — big display number */}
      <div className="text-center py-2">
        <div
          className="text-accent"
          style={{
            fontFamily: "'Oswald', sans-serif",
            fontSize: '3rem',
            fontWeight: 700,
            lineHeight: 1,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {fmtPct(latest.overall_accuracy)}
        </div>
        <div className="text-xs text-muted-foreground mt-1">{latest.n_fights} peleas · consenso</div>
      </div>

      {/* Mini bars per model in DASHBOARD_MODEL_ORDER */}
      <div className="border-t border-border pt-3 space-y-1.5">
        {DASHBOARD_MODEL_ORDER.map((short) => {
          const acc = latest.accuracy_by_model[short]?.accuracy
          const pct = acc != null ? acc * 100 : null
          return (
            <div key={short} className="flex items-center gap-2">
              <span className="text-[10px] text-muted-foreground w-9 flex-shrink-0 tabular-nums">{short}</span>
              <div className="flex-1 bg-border rounded-full h-1.5 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: pct != null ? `${pct}%` : '0%', background: modelColor(short) }}
                />
              </div>
              <span className="text-[10px] text-muted-foreground w-10 text-right tabular-nums">
                {pct != null ? `${pct.toFixed(1)}%` : '—'}
              </span>
            </div>
          )
        })}
      </div>
    </motion.div>
  )
}
