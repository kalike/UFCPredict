import { Check, X } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import type { DashSpecialFight } from '../../api/client'

export type SpecialTierKey = 'dwcs_debut' | 'no_history' | 'combined'

interface SpecialCasesDialogProps {
  tier: string | null
  fights: DashSpecialFight[]
  onClose: () => void
}

const TIER_TITLE: Record<SpecialTierKey, string> = {
  dwcs_debut: 'Combates con debutante de DWCS',
  no_history: 'Combates con peleador sin historial',
  combined: 'Combates con datos escasos (DWCS + sin historial)',
}

const TIER_DESCRIPTION: Record<SpecialTierKey, string> = {
  dwcs_debut:
    'Peleas donde al menos uno de los luchadores solo tenía una pelea previa y era de DWCS (Contender Series).',
  no_history:
    'Peleas donde al menos uno de los luchadores no tenía historial registrado.',
  combined: 'Unión de ambos casos (debut DWCS o sin historial registrado).',
}

function isSpecialTierKey(tier: string | null): tier is SpecialTierKey {
  return tier === 'dwcs_debut' || tier === 'no_history' || tier === 'combined'
}

function filterFights(tier: SpecialTierKey, fights: DashSpecialFight[]): DashSpecialFight[] {
  switch (tier) {
    case 'dwcs_debut':
      return fights.filter(f => f.fighter_1_dwcs_only || f.fighter_2_dwcs_only)
    case 'no_history':
      return fights.filter(f => !f.fighter_1_has_history || !f.fighter_2_has_history)
    case 'combined':
      return fights
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

function fighterBadge(isDwcs: boolean, noHistory: boolean): string | null {
  if (isDwcs) return 'DWCS único'
  if (noHistory) return 'Sin historial'
  return null
}

interface FighterCellProps {
  name: string
  badge: string | null
  isWinner: boolean
  isPredicted: boolean
  align: 'left' | 'right'
}

function FighterCell({ name, badge, isWinner, isPredicted, align }: FighterCellProps) {
  const alignClass = align === 'right' ? 'text-right items-end' : 'text-left items-start'
  return (
    <div className={`flex flex-col ${alignClass} min-w-0`}>
      <span
        className={`truncate ${isWinner ? 'text-success font-medium' : 'text-foreground'}`}
        title={name}
      >
        {name}
      </span>
      <div className="flex gap-1 mt-0.5 flex-wrap">
        {badge && (
          <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/30">
            {badge}
          </span>
        )}
        {isPredicted && (
          <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-white/5 text-muted-foreground">
            Predicho
          </span>
        )}
      </div>
    </div>
  )
}

export default function SpecialCasesDialog({ tier, fights, onClose }: SpecialCasesDialogProps) {
  const open = tier !== null
  const validTier = isSpecialTierKey(tier) ? tier : null
  const filtered = validTier ? filterFights(validTier, fights) : []
  const correctCount = filtered.filter(f => f.correct).length
  const total = filtered.length
  const accuracy = total > 0 ? (correctCount / total) * 100 : null

  return (
    <Dialog.Root open={open} onOpenChange={v => { if (!v) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-3xl max-h-[85vh] -translate-x-1/2 -translate-y-1/2 bg-card border border-border rounded-xl p-6 shadow-2xl focus:outline-none flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-start justify-between gap-4 mb-2">
            <div>
              <Dialog.Title
                className="text-foreground font-semibold text-lg"
                style={{ fontFamily: "'Oswald', sans-serif" }}
              >
                {validTier ? TIER_TITLE[validTier] : ''}
              </Dialog.Title>
              <Dialog.Description className="text-xs text-muted-foreground mt-1">
                {validTier ? TIER_DESCRIPTION[validTier] : ''}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0 mt-0.5"
                aria-label="Cerrar"
              >
                <X size={16} />
              </button>
            </Dialog.Close>
          </div>

          {/* Stats summary */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground border-b border-border pb-3 mb-1">
            <span>
              <span className="text-foreground font-medium">{correctCount}/{total}</span> acertadas
            </span>
            {accuracy != null && (
              <span>
                Accuracy:{' '}
                <span className="text-foreground font-medium">{accuracy.toFixed(1)}%</span>
              </span>
            )}
          </div>

          {/* Fights list */}
          <div className="overflow-y-auto flex-1 -mx-6 px-6">
            {filtered.length === 0 ? (
              <p className="text-sm text-muted-foreground py-6 text-center">
                No hay combates en esta categoría aún.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {filtered.map((f, i) => {
                  const f1Badge = fighterBadge(f.fighter_1_dwcs_only, !f.fighter_1_has_history)
                  const f2Badge = fighterBadge(f.fighter_2_dwcs_only, !f.fighter_2_has_history)
                  return (
                    <li key={`${f.event}-${i}`} className="py-3 flex items-start gap-3">
                      <div className="flex-shrink-0 mt-0.5">
                        {f.correct ? (
                          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-success/15 text-success">
                            <Check size={14} />
                          </span>
                        ) : (
                          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-destructive/15 text-destructive">
                            <X size={14} />
                          </span>
                        )}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs text-muted-foreground truncate">{f.event}</span>
                          <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                            {formatDate(f.date)}
                          </span>
                        </div>

                        <div className="mt-1 grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-sm">
                          <FighterCell
                            name={f.fighter_1}
                            badge={f1Badge}
                            isWinner={f.real_winner === f.fighter_1}
                            isPredicted={f.predicted_winner === f.fighter_1}
                            align="right"
                          />
                          <span className="text-[10px] text-muted-foreground px-1">vs</span>
                          <FighterCell
                            name={f.fighter_2}
                            badge={f2Badge}
                            isWinner={f.real_winner === f.fighter_2}
                            isPredicted={f.predicted_winner === f.fighter_2}
                            align="left"
                          />
                        </div>

                        <div className="mt-1 text-[10px] text-muted-foreground">
                          Predicción:{' '}
                          <span className="text-foreground">{f.predicted_winner}</span>
                          {' · '}
                          Resultado:{' '}
                          <span className="text-foreground">{f.real_winner}</span>
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
