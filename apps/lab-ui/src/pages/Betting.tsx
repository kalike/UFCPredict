import { useState } from "react";
import { PageHeader } from "../components/ui";
import type { BettingConfig } from "../api/client";
import { useBettingDefaults } from "../components/betting/useBetting";
import { BacktestView } from "../components/betting/BacktestView";
import { LiveRecommendations } from "../components/betting/LiveRecommendations";
import { MyBetsView } from "../components/betting/MyBetsView";

type Tab = "engine" | "registro";

export default function Betting() {
  const [tab, setTab] = useState<Tab>("engine");
  const { data: defaults } = useBettingDefaults();
  const [config, setConfig] = useState<BettingConfig | null>(null);
  const cfg = config ?? defaults ?? null;

  return (
    <div>
      <PageHeader
        title="Apuestas"
        subtitle="Backtest, recomendaciones y registro de apuestas"
      />
      <div className="flex gap-2 mb-6 border-b border-border">
        {(
          [
            ["engine", "Engine"],
            ["registro", "Mi Registro"],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === k
                ? "border-accent text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "engine" && (
        <div data-testid="engine-tab" className="space-y-8">
          {cfg && <BacktestView config={cfg} onChange={setConfig} />}
          {cfg && <LiveRecommendations config={cfg} />}
        </div>
      )}
      {tab === "registro" && (
        <div data-testid="registro-tab">
          <MyBetsView />
        </div>
      )}
    </div>
  );
}
