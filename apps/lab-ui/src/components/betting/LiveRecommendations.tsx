import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { BettingConfig, BetCombo, RecommendResponse } from "../../api/client";
import { api } from "../../api/client";
import { Card, Button, Badge } from "../ui";
import { useRecommend } from "./useBetting";
import { SessionPicker } from "./SessionPicker";
import { PickSelector, loadExclusions, saveExclusions } from "./PickSelector";

// localStorage key identical to the legacy backend: betting_placed_{eventName}.
const PLACED_PREFIX = "betting_placed_";

function loadPlaced(eventName: string): Set<string> {
  try {
    const raw = localStorage.getItem(PLACED_PREFIX + eventName);
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
  } catch {
    return new Set();
  }
}

function savePlaced(eventName: string, placed: Set<string>) {
  localStorage.setItem(PLACED_PREFIX + eventName, JSON.stringify([...placed]));
}

function comboKey(combo: BetCombo): string {
  return combo.type + ":" + combo.picks.map((p) => p.pick).join("+");
}

const TYPE_TONE: Record<string, "accent" | "gold" | "muted"> = {
  single: "accent",
  double: "gold",
  triple: "muted",
};

function ComboCard({
  combo,
  placed,
  onToggle,
}: {
  combo: BetCombo;
  placed: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      onClick={onToggle}
      className={`border rounded-lg p-4 text-xs space-y-2 cursor-pointer transition-colors ${
        placed
          ? "border-emerald-500/60 bg-emerald-500/10"
          : "border-border bg-card hover:border-white/20"
      }`}
    >
      <div className="flex items-center gap-2">
        <Badge tone={TYPE_TONE[combo.type] ?? "muted"}>{combo.type}</Badge>
        {placed && (
          <span className="text-[10px] text-emerald-400 font-semibold uppercase tracking-widest">
            Realizada
          </span>
        )}
      </div>
      <div className="space-y-1 pt-1">
        {combo.picks.map((p, i) => (
          <div key={i} className="flex justify-between">
            <span className="text-foreground font-medium">{p.pick}</span>
            <span className="text-muted-foreground tabular-nums">
              ({p.pick_odds_american > 0 ? "+" : ""}
              {p.pick_odds_american}) {(p.model_prob * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
      <div className="border-t border-border pt-2 space-y-0.5 text-muted-foreground">
        <Row label="Odds combinadas" value={combo.combined_odds.toFixed(2)} />
        <Row label="Prob combinada" value={`${(combo.combined_prob * 100).toFixed(0)}%`} />
        <div className="flex justify-between">
          <span>EV</span>
          <span
            className={`tabular-nums font-semibold ${
              combo.ev >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {combo.ev >= 0 ? "+" : ""}
            {combo.ev.toFixed(3)}
          </span>
        </div>
        <Row label="Stake" value={`$${combo.stake.toFixed(0)}`} strong />
        <div className="flex justify-between">
          <span>Return potencial</span>
          <span className="text-emerald-400 tabular-nums font-semibold">
            ${combo.potential_return.toFixed(0)}
          </span>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex justify-between">
      <span>{label}</span>
      <span className={`text-foreground tabular-nums ${strong ? "font-semibold" : ""}`}>{value}</span>
    </div>
  );
}

function ComboGroup({
  title,
  combos,
  placedSet,
  onToggle,
}: {
  title: string;
  combos: BetCombo[];
  placedSet: Set<string>;
  onToggle: (c: BetCombo) => void;
}) {
  if (combos.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-muted-foreground mb-2">
        {title} ({combos.length})
      </h4>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {combos.map((c, i) => (
          <ComboCard key={i} combo={c} placed={placedSet.has(comboKey(c))} onToggle={() => onToggle(c)} />
        ))}
      </div>
    </div>
  );
}

export function LiveRecommendations({ config }: { config: BettingConfig }) {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [eventName, setEventName] = useState<string>("");
  const [exclusions, setExclusions] = useState<string[]>([]);
  const [placedSet, setPlacedSet] = useState<Set<string>>(new Set());
  const [imported, setImported] = useState(false);
  const qc = useQueryClient();
  const recommend = useRecommend();
  const data = recommend.data as RecommendResponse | undefined;

  const generate = useCallback(
    (id: number, excl: string[]) => {
      recommend.mutate({ sessionId: id, config: { ...config, excluded_picks: excl } });
    },
    [config, recommend],
  );

  const onSelectSession = useCallback(
    (id: number, name: string) => {
      setSessionId(id);
      setEventName(name);
      const excl = loadExclusions(id);
      setExclusions(excl);
      setPlacedSet(loadPlaced(name));
      generate(id, excl);
    },
    [generate],
  );

  const toggleExclusion = useCallback(
    (key: string) => {
      if (sessionId == null) return;
      const next = exclusions.includes(key)
        ? exclusions.filter((k) => k !== key)
        : [...exclusions, key];
      setExclusions(next);
      saveExclusions(sessionId, next);
      generate(sessionId, next);
    },
    [exclusions, sessionId, generate],
  );

  const togglePlaced = useCallback(
    (combo: BetCombo) => {
      setPlacedSet((prev) => {
        const next = new Set(prev);
        const k = comboKey(combo);
        if (next.has(k)) next.delete(k);
        else next.add(k);
        savePlaced(eventName, next);
        return next;
      });
    },
    [eventName],
  );

  const importToRegistry = useCallback(() => {
    if (!data) return;
    const combos = [...data.singles, ...data.doubles, ...data.triples].filter((c) =>
      placedSet.has(comboKey(c)),
    );
    if (combos.length === 0) return;
    api
      .importUserBets({ event_name: data.event_name, combos, session_id: sessionId ?? undefined })
      .then(() => {
        qc.invalidateQueries({ queryKey: ["user-bets"] });
        qc.invalidateQueries({ queryKey: ["user-bets-stats"] });
        setImported(true);
        setTimeout(() => setImported(false), 2000);
      })
      .catch(() => undefined);
  }, [data, placedSet, sessionId, qc]);

  const nPlaced = placedSet.size;

  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">
          Recomendaciones live
        </h3>
        <div className="max-w-md">
          <SessionPicker value={sessionId} onChange={onSelectSession} />
        </div>
        {recommend.isPending && <p className="text-xs text-muted-foreground">Generando…</p>}
        {recommend.isError && (
          <p className="text-xs text-red-400">Error: {(recommend.error as Error).message}</p>
        )}
      </Card>

      {data && (
        <>
          <PickSelector
            picks={data.all_qualified_picks}
            excludedPicks={exclusions}
            onToggle={toggleExclusion}
          />

          <Card className="space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">
                  Combos · {data.event_name}
                </h3>
                <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                  <span>Stake total: <span className="text-foreground font-semibold">${data.summary.total_stake.toFixed(0)}</span></span>
                  <span>Return esperado: <span className="text-emerald-400 font-semibold">${data.summary.expected_return.toFixed(0)}</span></span>
                  <span>Exposure: <span className="text-foreground font-semibold">{(data.summary.exposure_pct * 100).toFixed(1)}%</span></span>
                </div>
              </div>
              <Button
                variant="secondary"
                disabled={nPlaced === 0 || imported}
                onClick={importToRegistry}
              >
                {imported ? "Guardado ✓" : `Importar a Mi Registro${nPlaced > 0 ? ` (${nPlaced})` : ""}`}
              </Button>
            </div>
            <ComboGroup title="Singles" combos={data.singles} placedSet={placedSet} onToggle={togglePlaced} />
            <ComboGroup title="Doubles" combos={data.doubles} placedSet={placedSet} onToggle={togglePlaced} />
            <ComboGroup title="Triples" combos={data.triples} placedSet={placedSet} onToggle={togglePlaced} />
            {data.singles.length === 0 && data.doubles.length === 0 && data.triples.length === 0 && (
              <p className="text-xs text-muted-foreground">No hay combos para esta config.</p>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
