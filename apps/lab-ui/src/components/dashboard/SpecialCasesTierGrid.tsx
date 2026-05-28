import { motion } from 'framer-motion'
import { Sparkles, CircleHelp, Layers } from 'lucide-react'
import type { DashTier } from '../../api/client'
import { fmtPct } from '../../lib/formatters'

const TIER_CONFIG = [
  { key: 'dwcs_debut', label: 'Debut DWCS', icon: Sparkles, delay: 0 },
  { key: 'no_history', label: 'Sin historial', icon: CircleHelp, delay: 0.05 },
  { key: 'combined', label: 'Ambos casos', icon: Layers, delay: 0.1 },
] as const

interface SpecialCasesTierGridProps {
  tiers: Record<'dwcs_debut' | 'no_history' | 'combined', DashTier>
  onSelect: (tier: string) => void
}

export default function SpecialCasesTierGrid({ tiers, onSelect }: SpecialCasesTierGridProps) {
  return (
    <div className="grid grid-cols-3 gap-4">
      {TIER_CONFIG.map(({ key, label, icon: Icon, delay }) => {
        const tier = tiers[key]
        const accuracy = tier?.accuracy
        const total = tier?.total ?? 0
        const clickable = total > 0

        const variant =
          accuracy == null
            ? 'default'
            : accuracy >= 0.65
            ? 'success'
            : accuracy >= 0.5
            ? 'warning'
            : 'destructive'

        const subtitleColor = {
          default: 'text-muted-foreground',
          warning: 'text-yellow-400',
          success: 'text-success',
          destructive: 'text-destructive',
        }[variant]

        const handleClick = () => {
          if (clickable) onSelect(key)
        }

        const handleKeyDown = (e: React.KeyboardEvent) => {
          if (!clickable) return
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onSelect(key)
          }
        }

        return (
          <motion.div
            key={key}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay, ease: 'easeOut' }}
            onClick={handleClick}
            onKeyDown={handleKeyDown}
            role={clickable ? 'button' : undefined}
            tabIndex={clickable ? 0 : undefined}
            className={`bg-card border border-border rounded-xl p-5 transition-all duration-200 ${
              clickable
                ? 'cursor-pointer hover:border-accent/50 hover:bg-white/5 focus:outline-none focus:border-accent'
                : 'hover:border-accent/30'
            }`}
          >
            <div className="flex items-start justify-between mb-3">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                {label}
              </span>
              <Icon size={16} className="text-border" />
            </div>
            <div
              className="text-foreground mb-1.5"
              style={{
                fontFamily: "'Oswald', sans-serif",
                fontSize: '2.2rem',
                fontWeight: 700,
                lineHeight: 1,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {fmtPct(accuracy)}
            </div>
            <div className={`text-xs ${subtitleColor}`}>
              {total} pelea{total !== 1 ? 's' : ''}
              {clickable && (
                <span className="ml-1.5 text-[10px] text-muted-foreground/80">· ver detalle</span>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}
