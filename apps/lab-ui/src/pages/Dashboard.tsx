import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader, Button, Input, Skeleton } from "../components/ui";
import {
  useDashboard, useInvalidateDashboard, useRecalculationStatus,
} from "../components/dashboard/useDashboard";
import { DASHBOARD_MODEL_ORDER } from "../lib/model-colors";
import StatGrid from "../components/dashboard/StatGrid";
import ConsensusTierGrid from "../components/dashboard/ConsensusTierGrid";
import ProbabilityTierGrid from "../components/dashboard/ProbabilityTierGrid";
import SpecialCasesTierGrid from "../components/dashboard/SpecialCasesTierGrid";
import SpecialCasesDialog from "../components/dashboard/SpecialCasesDialog";
import AccuracyChart from "../components/dashboard/AccuracyChart";
import LatestEventCard from "../components/dashboard/LatestEventCard";
import AccuracyHeatmap from "../components/dashboard/AccuracyHeatmap";
import ModelRanking from "../components/dashboard/ModelRanking";
import ModelAccuracyTable from "../components/dashboard/ModelAccuracyTable";
import EventsTable from "../components/dashboard/EventsTable";
import EventResultsPanel from "../components/dashboard/EventResultsPanel";

export default function Dashboard() {
  const qc = useQueryClient();
  const [minFights, setMinFights] = useState(0);
  const { data, isLoading, isError, error, refetch } = useDashboard(minFights);
  const invalidate = useInvalidateDashboard();
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [specialTier, setSpecialTier] = useState<string | null>(null);

  // The recalc runs in the background (~minutes) while the POST returns at once.
  // Track its lifecycle so the progress stays visible the whole time and the
  // dashboard refreshes only once it actually finishes.
  const [recalcPhase, setRecalcPhase] = useState<"idle" | "starting" | "running">("idle");
  const recalcActive = recalcPhase !== "idle";
  const recalc = useRecalculationStatus(recalcActive);

  useEffect(() => {
    if (!recalcActive) return;
    const st = recalc.data;
    if (!st) return;
    if (recalcPhase === "starting" && st.is_running) {
      setRecalcPhase("running");
    } else if (recalcPhase === "running" && !st.is_running) {
      // Recalc finished: now (and only now) refresh the dashboard data.
      setRecalcPhase("idle");
      qc.invalidateQueries({ queryKey: ["dashboard", "summary"] });
    }
  }, [recalc.data, recalcPhase, recalcActive, qc]);

  const startRecalc = () => {
    invalidate.mutate(minFights, { onSuccess: () => setRecalcPhase("starting") });
  };

  // Reusable controls bar (does not depend on `data`, so it stays accessible
  // during error states to let the user recover, e.g. lower "Min peleas").
  const controls = (
    <div className="flex items-center gap-3">
      <label className="text-xs text-muted-foreground">Min peleas</label>
      <Input type="number" value={minFights}
             onChange={(e) => setMinFights(Math.max(0, Number(e.target.value)))}
             className="w-20" />
      <Button variant="primary" disabled={recalcActive || invalidate.isPending}
              onClick={startRecalc}>
        {recalcActive ? "Recalculando…" : "Actualizar"}
      </Button>
      {recalcActive && (
        <span className="text-xs text-muted-foreground">
          {recalc.data?.is_running
            ? `${recalc.data.step ?? "recalculando"} · ${recalc.data.completed_events}/${recalc.data.total_events}`
            : "iniciando…"}
        </span>
      )}
    </div>
  );

  if (isError) {
    return (
      <div className="space-y-5">
        <PageHeader title="Dashboard" subtitle="Accuracy de modelos y eventos" />
        {controls}
        <div className="bg-card border border-destructive/40 rounded-xl p-6 space-y-3">
          <p className="text-destructive font-semibold">No se pudo cargar el dashboard</p>
          <p className="text-xs text-muted-foreground">
            {error instanceof Error ? error.message : "Error desconocido al consultar /api/dashboard."}
          </p>
          <Button variant="primary" onClick={() => refetch()}>Reintentar</Button>
        </div>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="space-y-5">
        <PageHeader title="Dashboard" subtitle="Accuracy de modelos y eventos" />
        <div className="grid grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
        </div>
        <Skeleton className="h-80 rounded-xl" />
      </div>
    );
  }

  const modelShorts = data.models?.length
    ? data.models
    : DASHBOARD_MODEL_ORDER.filter((s) => s in data.avg_by_model);
  const pastEvents = data.accuracy_by_event.filter((e) => e.is_past);

  return (
    <div className="space-y-5">
      <PageHeader title="Dashboard" subtitle="Accuracy de modelos y eventos" />
      {controls}

      <StatGrid data={data} />
      <ConsensusTierGrid tiers={data.consensus_tiers} />
      <ProbabilityTierGrid tiers={data.probability_tiers} />
      <SpecialCasesTierGrid tiers={data.special_case_tiers} onSelect={setSpecialTier} />

      <div className="grid grid-cols-[3fr_2fr] gap-4">
        <AccuracyChart events={pastEvents} modelShorts={modelShorts} />
        {data.latest_event && <LatestEventCard latest={data.latest_event} />}
      </div>

      {pastEvents.length > 0 && (
        <AccuracyHeatmap events={pastEvents} avgByModel={data.avg_by_model}
                         modelShorts={modelShorts} />
      )}

      <div className="grid grid-cols-[2fr_3fr] gap-4">
        <ModelRanking events={pastEvents} avgByModel={data.avg_by_model}
                      modelShorts={modelShorts} />
        <ModelAccuracyTable avgByModel={data.avg_by_model} modelShorts={modelShorts} />
      </div>

      <EventsTable events={data.accuracy_by_event} selectedEvent={selectedEvent}
                   onSelectEvent={(e) => setSelectedEvent(e === selectedEvent ? null : e)} />
      {selectedEvent && (
        <EventResultsPanel eventName={selectedEvent} onClose={() => setSelectedEvent(null)} />
      )}

      {specialTier && (
        <SpecialCasesDialog tier={specialTier} fights={data.special_case_fights}
                            onClose={() => setSpecialTier(null)} />
      )}
    </div>
  );
}
