import { motion } from 'framer-motion'
import { TrendingDown, Minus, TrendingUp, ChevronsUp, Zap } from 'lucide-react'
import type { DashTier } from '../../api/client'
import { fmtPct } from '../../lib/formatters'

const TIER_CONFIG = [
  { key: 'low', label: 'Baja', icon: TrendingDown, delay: 0 },
  { key: 'medium', label: 'Media', icon: Minus, delay: 0.05 },
  { key: 'high', label: 'Alta', icon: TrendingUp, delay: 0.1 },
  { key: 'very_high', label: 'Muy Alta', icon: ChevronsUp, delay: 0.15 },
  { key: 'extreme', label: 'Extrema', icon: Zap, delay: 0.2 },
] as const

interface ProbabilityTierGridProps {
  tiers: Record<string, DashTier>
}

export default function ProbabilityTierGrid({ tiers }: ProbabilityTierGridProps) {
  if (!tiers) return null

  return (
    <div className="grid grid-cols-5 gap-4">
      {TIER_CONFIG.map(({ key, label, icon: Icon, delay }) => {
        const tier = tiers[key]
        const accuracy = tier?.accuracy
        const total = tier?.total ?? 0
        const tierLabel = tier?.label ?? ''

        const variant = accuracy == null
          ? 'default'
          : accuracy >= 0.65 ? 'success' : accuracy >= 0.5 ? 'warning' : 'destructive'

        const subtitleColor = {
          default: 'text-muted-foreground',
          warning: 'text-warning',
          success: 'text-success',
          destructive: 'text-destructive',
        }[variant]

        return (
          <motion.div
            key={key}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay, ease: 'easeOut' }}
            className="bg-card border border-border rounded-xl p-5 hover:border-accent/30 card-hover-glow transition-all duration-200"
          >
            <div className="flex items-start justify-between mb-3">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                {label} ({tierLabel})
              </span>
              <Icon size={16} className="text-border" />
            </div>
            <div
              className="text-foreground mb-1.5"
              style={{ fontFamily: "'Oswald', sans-serif", fontSize: '2.2rem', fontWeight: 700, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}
            >
              {fmtPct(accuracy)}
            </div>
            <div className={`text-xs ${subtitleColor}`}>
              {total} pelea{total !== 1 ? 's' : ''}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}
