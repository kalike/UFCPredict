import { useState } from "react";
import { Settings } from "lucide-react";
import { Button, Card } from "../ui";
import type { BettingConfig, StrategyResult } from "../../api/client";
import { useBacktest, useBettingDefaults } from "./useBetting";
import { ConfigPanel } from "./ConfigPanel";
import { BettingKPIs } from "./BettingKPIs";
import { EquityCurve } from "./EquityCurve";
import { PnLChart } from "./PnLChart";
import { StrategyTable } from "./StrategyTable";
import { StrategyHeatmap } from "./StrategyHeatmap";
import { TopPicks } from "./TopPicks";
import { EventDetail } from "./EventDetail";

type Props = { config: BettingConfig; onChange: (c: BettingConfig) => void };

const KEYS = ["total", "singles", "doubles", "triples", "baseline"] as const;

export function BacktestView({ config, onChange }: Props) {
  const backtest = useBacktest();
  const { data: defaults } = useBettingDefaults();
  const [strategy, setStrategy] =
    useState<(typeof KEYS)[number]>("total");
  const [configOpen, setConfigOpen] = useState(false);
  const result = backtest.data;

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Button variant="secondary" onClick={() => setConfigOpen(true)}>
          <span className="flex items-center gap-1.5">
            <Settings size={14} /> Configuración
          </span>
        </Button>
        <Button onClick={() => backtest.mutate(config)} disabled={backtest.isPending}>
          {backtest.isPending ? "Calculando…" : "Ejecutar backtest"}
        </Button>
      </div>

      <ConfigPanel
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        config={config}
        onChange={onChange}
        onRunBacktest={() => {
          backtest.mutate(config);
          setConfigOpen(false);
        }}
        onResetDefaults={() => defaults && onChange(defaults)}
      />

      {result && (
        <>
          {/* Strategy selector */}
          <div className="flex gap-2 flex-wrap">
            {KEYS.map((k) => (
              <Button
                key={k}
                variant={strategy === k ? "primary" : "secondary"}
                onClick={() => setStrategy(k)}
              >
                {k}
                {result.best_strategy === k ? " ★" : ""}
              </Button>
            ))}
          </div>

          {/* KPI panel for the selected strategy (full legacy backend panel on "total") */}
          <BettingKPIs
            strategies={result.strategies}
            total={result.total}
            totalEvents={result.total_events}
            strategy={strategy}
          />

          {/* Cross-strategy charts */}
          <EquityCurve strategies={result.strategies} />
          <PnLChart strategies={result.strategies} />

          {/* Strategy comparison table */}
          <StrategyTable
            strategies={result.strategies}
            bestStrategy={result.best_strategy}
          />

          {/* ROI heatmap per event × strategy */}
          <StrategyHeatmap strategies={result.strategies} />

          {/* Top picks by hit rate */}
          <TopPicks strategies={result.strategies} />

          {/* Expandable per-event detail */}
          <EventDetail strategies={result.strategies} />
        </>
      )}

      {backtest.isError && (
        <Card>Error: {(backtest.error as Error).message}</Card>
      )}
    </div>
  );
}
