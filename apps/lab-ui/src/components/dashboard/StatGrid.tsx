import { motion } from 'framer-motion'
import { Brain, Target, Users, Calendar, AlertTriangle } from 'lucide-react'
import type { DashboardSummary } from '../../api/client'
import { fmtPct, fmtNumber } from '../../lib/formatters'

interface StatCardProps {
  label: string
  value: string
  subtitle?: string
  subtitleVariant?: 'default' | 'warning' | 'success'
  icon: React.ElementType
  delay?: number
}

function StatCard({ label, value, subtitle, subtitleVariant = 'default', icon: Icon, delay = 0 }: StatCardProps) {
  const subtitleColor = {
    default: 'text-muted-foreground',
    warning: 'text-warning',
    success: 'text-success',
  }[subtitleVariant]

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay, ease: 'easeOut' }}
      className="bg-card border border-border rounded-xl p-5 hover:border-accent/30 card-hover-glow transition-all duration-200"
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{label}</span>
        <Icon size={16} className="text-border" />
      </div>
      <div
        className="text-foreground mb-1.5"
        style={{ fontFamily: "'Oswald', sans-serif", fontSize: '2.2rem', fontWeight: 700, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </div>
      {subtitle && (
        <div className={`text-xs flex items-center gap-1 ${subtitleColor}`}>
          {subtitleVariant === 'warning' && <AlertTriangle size={11} />}
          {subtitle}
        </div>
      )}
    </motion.div>
  )
}

interface StatGridProps {
  data: DashboardSummary
}

export default function StatGrid({ data }: StatGridProps) {
  const activeModels = data.n_models - data.disabled_models.length
  const disabledCount = data.disabled_models.length

  return (
    <div className="grid grid-cols-4 gap-4">
      <StatCard
        label="Modelos Activos"
        value={`${activeModels} / ${data.n_models}`}
        subtitle={disabledCount > 0 ? `${disabledCount} deshabilitado${disabledCount > 1 ? 's' : ''}` : 'Todos activos'}
        subtitleVariant={disabledCount > 0 ? 'warning' : 'success'}
        icon={Brain}
        delay={0}
      />
      <StatCard
        label="Accuracy Media"
        value={fmtPct(data.avg_consensus_accuracy)}
        subtitle="consenso global"
        icon={Target}
        delay={0.05}
      />
      <StatCard
        label="Peleadores"
        value={fmtNumber(data.n_fighters)}
        subtitle="en base de datos"
        icon={Users}
        delay={0.1}
      />
      <StatCard
        label="Eventos Predichos"
        value={String(data.n_predicted_events)}
        subtitle={`${data.n_past_events} verificados`}
        subtitleVariant={data.n_past_events > 0 ? 'success' : 'default'}
        icon={Calendar}
        delay={0.15}
      />
    </div>
  )
}
