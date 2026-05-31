import { useState } from "react";
import { PageHeader } from "../components/ui";
import { FightInputForm } from "../components/predictions/FightInputForm";
import { PredictionResults } from "../components/predictions/PredictionResults";
import { PastEventsTab } from "../components/predictions/PastEventsTab";
import { SessionsTab } from "../components/predictions/SessionsTab";
import { usePredictFights } from "../components/predictions/usePredictions";
import type { FightInput } from "../api/client";

type Tab = "new" | "past" | "sessions";

const TABS: { key: Tab; label: string }[] = [
  { key: "new", label: "Nueva predicción" },
  { key: "past", label: "Eventos pasados" },
  { key: "sessions", label: "Sesiones" },
];

export default function PredictionsPage() {
  const [tab, setTab] = useState<Tab>("new");
  const predict = usePredictFights();

  function onPredict(event: string, fights: FightInput[]) {
    predict.mutate({ event, fights });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Predicciones"
        subtitle="Inference con los modelos activos + TTA · matchups arbitrarios, eventos pasados y sesiones"
      />

      {/* Tabs */}
      <div className="flex gap-2 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key
                ? "border-accent text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "new" && (
        <div className="space-y-5">
          <FightInputForm onPredict={onPredict} isPending={predict.isPending} />
          {predict.isError && (
            <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
              {(predict.error as Error).message}
            </div>
          )}
          {predict.data && <PredictionResults data={predict.data} />}
        </div>
      )}

      {tab === "past" && <PastEventsTab />}
      {tab === "sessions" && <SessionsTab />}
    </div>
  );
}
