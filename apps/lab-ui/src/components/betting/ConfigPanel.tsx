import { useState } from "react";
import { X, ChevronDown, Save, Trash2, Cpu } from "lucide-react";
import type { BettingConfig } from "../../api/client";
import {
  useBetConfigs,
  useSaveBetConfig,
  useDeleteBetConfig,
  useCurrentCombo,
  useApplyCombo,
} from "./useBetConfigs";

type Props = {
  open: boolean;
  onClose: () => void;
  config: BettingConfig;
  onChange: (config: BettingConfig) => void;
  onRunBacktest: () => void;
  onResetDefaults: () => void;
};

function Slider({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="text-foreground font-semibold tabular-nums">
          {format ? format(value) : value}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer accent-[var(--color-accent)]"
      />
    </div>
  );
}

function Collapsible({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border-t border-border pt-4">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="uppercase tracking-wider">{title}</span>
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="pt-4">{children}</div>}
    </div>
  );
}

const moneyCls =
  "flex-1 bg-white/5 border border-border rounded px-3 py-1.5 text-xs text-foreground tabular-nums focus:border-[var(--color-accent)] focus:outline-none";

export function ConfigPanel({ open, onClose, config, onChange, onRunBacktest, onResetDefaults }: Props) {
  const [typeFiltersOpen, setTypeFiltersOpen] = useState(false);
  const [exposureOpen, setExposureOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [expandedEntry, setExpandedEntry] = useState<number | null>(null);

  const { data: presets = [] } = useBetConfigs();
  const save = useSaveBetConfig();
  const del = useDeleteBetConfig();
  const { data: currentCombo } = useCurrentCombo();
  const applyCombo = useApplyCombo();

  const update = (key: keyof BettingConfig, value: number | boolean) =>
    onChange({ ...config, [key]: value } as BettingConfig);

  const saveCurrent = () => {
    const name = newName.trim();
    if (!name) return;
    save.mutate({ name, params: { config, combo: currentCombo ?? null } });
    setNewName("");
  };

  const expTotal =
    (config.exposure_pct_singles ?? 0) +
    (config.exposure_pct_doubles ?? 0) +
    (config.exposure_pct_triples ?? 0);

  return (
    <>
      {/* Overlay */}
      <div
        className={`fixed inset-0 z-40 bg-black transition-opacity duration-200 ${
          open ? "opacity-40" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
      />
      {/* Drawer */}
      <div
        className={`fixed right-0 top-0 h-full w-[340px] bg-card border-l border-border z-50 flex flex-col transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h3 className="text-sm font-semibold text-foreground uppercase tracking-widest">
            Configuración
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">
          {/* Presets (BBDD) */}
          <div className="space-y-2 pb-4 border-b border-border">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
              Configuraciones guardadas
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Nombre de la config"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveCurrent();
                }}
                className="flex-1 bg-white/5 border border-border rounded px-2 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-[var(--color-accent)] focus:outline-none"
              />
              <button
                onClick={saveCurrent}
                disabled={!newName.trim()}
                title="Guardar config actual"
                className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-semibold bg-accent text-accent-foreground hover:bg-accent-hi transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Save size={12} />
                Guardar
              </button>
            </div>
            {presets.length > 0 && (
              <div className="space-y-1 max-h-60 overflow-y-auto">
                {presets.map((p) => {
                  const comboEntries = p.params.combo ? Object.entries(p.params.combo) : [];
                  const isExpanded = expandedEntry === p.id;
                  return (
                    <div key={p.id} className="rounded bg-white/5 hover:bg-white/10 transition-colors">
                      <div className="flex items-center gap-2 px-2 py-1">
                        <button
                          onClick={() =>
                            onChange({
                              ...config,
                              ...(p.params.config as Partial<BettingConfig>),
                            } as BettingConfig)
                          }
                          className="flex-1 text-left text-xs text-foreground truncate"
                          title="Cargar"
                        >
                          {p.name}
                        </button>
                        {comboEntries.length > 0 && (
                          <button
                            onClick={() => setExpandedEntry(isExpanded ? null : p.id)}
                            className="text-[10px] text-accent hover:opacity-80 transition-colors flex items-center gap-1"
                            title={`Combo de ${comboEntries.length} modelos`}
                          >
                            <Cpu size={11} />
                            {comboEntries.length}
                          </button>
                        )}
                        <button
                          onClick={() => del.mutate(p.id)}
                          className="text-muted-foreground hover:text-red-400 transition-colors"
                          title="Eliminar"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                      {isExpanded && comboEntries.length > 0 && (
                        <div className="px-2 pb-2 space-y-2">
                          <div className="flex flex-wrap gap-1">
                            {comboEntries.map(([short, v]) => (
                              <span
                                key={short}
                                className="text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-accent border border-accent/30"
                              >
                                {short} v{v}
                              </span>
                            ))}
                          </div>
                          <button
                            onClick={() => p.params.combo && applyCombo.mutate(p.params.combo)}
                            disabled={applyCombo.isPending}
                            className="w-full text-[10px] py-1 rounded bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50 transition-colors"
                          >
                            {applyCombo.isPending ? "Aplicando…" : "Aplicar combo de modelos"}
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Main sliders */}
          <Slider
            label="Consenso mínimo"
            value={config.min_consensus_pct}
            min={50}
            max={100}
            step={5}
            format={(v) => `${v}%`}
            onChange={(v) => update("min_consensus_pct", v)}
          />
          <Slider
            label="Prob mínima singles"
            value={config.min_model_prob}
            min={0.5}
            max={0.8}
            step={0.01}
            format={(v) => v.toFixed(2)}
            onChange={(v) => update("min_model_prob", v)}
          />
          <Slider
            label="Min peleas PIT por luchador"
            value={config.min_pit_fights ?? 0}
            min={0}
            max={20}
            step={1}
            format={(v) => (v === 0 ? "sin filtro" : `${v}`)}
            onChange={(v) => update("min_pit_fights", v)}
          />
          <Slider
            label="Kelly fraction"
            value={config.kelly_fraction}
            min={0.1}
            max={0.5}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(v) => update("kelly_fraction", v)}
          />
          <Slider
            label="Max exposure por evento"
            value={config.max_event_exposure_pct}
            min={0.05}
            max={0.3}
            step={0.01}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            onChange={(v) => update("max_event_exposure_pct", v)}
          />
          <Slider
            label="Max picks por evento"
            value={config.max_picks_per_event}
            min={3}
            max={12}
            step={1}
            onChange={(v) => update("max_picks_per_event", v)}
          />

          <div className="space-y-1.5">
            <span className="text-xs text-muted-foreground">Max legs por parlay</span>
            <div className="flex gap-2">
              {[2, 3].map((n) => (
                <button
                  key={n}
                  onClick={() => update("max_parlay_legs", n)}
                  className={`flex-1 py-1.5 rounded text-xs font-semibold transition-colors ${
                    config.max_parlay_legs === n
                      ? "bg-accent text-accent-foreground"
                      : "bg-white/5 text-muted-foreground hover:bg-white/10"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <span className="text-xs text-muted-foreground">Bankroll</span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">$</span>
              <input
                type="number"
                min={100}
                max={1000000}
                value={config.bankroll}
                onChange={(e) =>
                  update("bankroll", Math.max(100, Math.min(1_000_000, Number(e.target.value) || 100)))
                }
                className={moneyCls}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <span className="text-xs text-muted-foreground">Stake por combo</span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">$</span>
              <input
                type="number"
                min={1}
                max={10000}
                value={config.stake_per_combo}
                onChange={(e) =>
                  update("stake_per_combo", Math.max(1, Math.min(10_000, Number(e.target.value) || 1)))
                }
                className={moneyCls}
              />
            </div>
          </div>

          {/* Per-type filters (collapsible) */}
          <Collapsible
            title="Filtros por tipo de apuesta"
            open={typeFiltersOpen}
            onToggle={() => setTypeFiltersOpen(!typeFiltersOpen)}
          >
            <div className="space-y-5">
              <div className="space-y-3">
                <div className="text-[10px] uppercase tracking-wider text-accent font-semibold">Doubles</div>
                <Slider
                  label="Prob mínima por leg"
                  value={config.min_prob_leg_double ?? 0}
                  min={0}
                  max={0.8}
                  step={0.01}
                  format={(v) => (v === 0 ? "usa singles" : v.toFixed(2))}
                  onChange={(v) => update("min_prob_leg_double", v)}
                />
                <Slider
                  label="Prob combinada mínima"
                  value={config.min_combined_prob_double ?? 0}
                  min={0}
                  max={0.6}
                  step={0.01}
                  format={(v) => (v === 0 ? "sin filtro" : v.toFixed(2))}
                  onChange={(v) => update("min_combined_prob_double", v)}
                />
              </div>
              <div className="space-y-3">
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-gold)] font-semibold">
                  Triples
                </div>
                <Slider
                  label="Prob mínima por leg"
                  value={config.min_prob_leg_triple ?? 0}
                  min={0}
                  max={0.8}
                  step={0.01}
                  format={(v) => (v === 0 ? "usa singles" : v.toFixed(2))}
                  onChange={(v) => update("min_prob_leg_triple", v)}
                />
                <Slider
                  label="Prob combinada mínima"
                  value={config.min_combined_prob_triple ?? 0}
                  min={0}
                  max={0.4}
                  step={0.01}
                  format={(v) => (v === 0 ? "sin filtro" : v.toFixed(2))}
                  onChange={(v) => update("min_combined_prob_triple", v)}
                />
              </div>
              <div className="space-y-3">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                  Compartido (doubles + triples)
                </div>
                <Slider
                  label="EV mínimo del combo"
                  value={config.min_combo_ev ?? 0}
                  min={0}
                  max={0.5}
                  step={0.01}
                  format={(v) => (v === 0 ? "sin filtro" : v.toFixed(2))}
                  onChange={(v) => update("min_combo_ev", v)}
                />
              </div>
            </div>
          </Collapsible>

          {/* Per-type exposure (collapsible) */}
          <Collapsible
            title="Exposición por tipo"
            open={exposureOpen}
            onToggle={() => setExposureOpen(!exposureOpen)}
          >
            <div className="space-y-4">
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                Cap por tipo como % del bankroll. 0 = sin cap por tipo (solo aplica el cap global).
                Evita que una estrategia canibalice a las otras bajo el cap compartido.
              </p>
              <Slider
                label="Peso singles"
                value={config.exposure_pct_singles ?? 0}
                min={0}
                max={0.3}
                step={0.01}
                format={(v) => (v === 0 ? "auto" : `${(v * 100).toFixed(0)}%`)}
                onChange={(v) => update("exposure_pct_singles", v)}
              />
              <Slider
                label="Peso doubles"
                value={config.exposure_pct_doubles ?? 0}
                min={0}
                max={0.3}
                step={0.01}
                format={(v) => (v === 0 ? "auto" : `${(v * 100).toFixed(0)}%`)}
                onChange={(v) => update("exposure_pct_doubles", v)}
              />
              <Slider
                label="Peso triples"
                value={config.exposure_pct_triples ?? 0}
                min={0}
                max={0.3}
                step={0.01}
                format={(v) => (v === 0 ? "auto" : `${(v * 100).toFixed(0)}%`)}
                onChange={(v) => update("exposure_pct_triples", v)}
              />
              {expTotal > 0 && (
                <div className="flex justify-between text-[11px] pt-2 border-t border-border/40">
                  <span className="text-muted-foreground">Suma pesos</span>
                  <span
                    className={`tabular-nums font-semibold ${
                      expTotal > config.max_event_exposure_pct ? "text-amber-400" : "text-foreground"
                    }`}
                  >
                    {(expTotal * 100).toFixed(0)}% / {(config.max_event_exposure_pct * 100).toFixed(0)}%
                  </span>
                </div>
              )}
            </div>
          </Collapsible>

          {/* Compound */}
          <div className="border-t border-border pt-4 space-y-3">
            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-xs text-muted-foreground">Interés compuesto</span>
              <input
                type="checkbox"
                checked={config.compound_mode ?? false}
                onChange={(e) => update("compound_mode", e.target.checked)}
                className="w-4 h-4 accent-[var(--color-accent)]"
              />
            </label>
            {config.compound_mode && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <span className="text-xs text-muted-foreground">Bankroll mínimo (floor)</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">$</span>
                    <input
                      type="number"
                      min={0}
                      max={100000}
                      value={config.bankroll_floor ?? 500}
                      onChange={(e) => update("bankroll_floor", Number(e.target.value) || 0)}
                      className={moneyCls}
                    />
                  </div>
                </div>
                <Slider
                  label="Stake parlay (%)"
                  value={config.parlay_stake_pct ?? 0.01}
                  min={0.001}
                  max={0.05}
                  step={0.001}
                  format={(v) => `${(v * 100).toFixed(1)}%`}
                  onChange={(v) => update("parlay_stake_pct", v)}
                />
              </div>
            )}
          </div>
        </div>

        <div className="px-5 py-4 border-t border-border space-y-2">
          <button
            onClick={onRunBacktest}
            className="w-full py-2 rounded bg-accent text-accent-foreground text-xs font-semibold hover:bg-accent-hi transition-colors"
          >
            Ejecutar Backtest
          </button>
          <button
            onClick={onResetDefaults}
            className="w-full py-2 rounded bg-white/5 text-muted-foreground text-xs font-semibold hover:bg-white/10 transition-colors"
          >
            Restaurar Defaults
          </button>
        </div>
      </div>
    </>
  );
}
