import { useState } from "react";
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
  const [minFights, setMinFights] = useState(0);
  const { data, isLoading } = useDashboard(minFights);
  const invalidate = useInvalidateDashboard();
  const recalc = useRecalculationStatus(invalidate.isPending || false);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [specialTier, setSpecialTier] = useState<string | null>(null);

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

  const modelShorts = DASHBOARD_MODEL_ORDER.filter((s) => s in data.avg_by_model);
  const pastEvents = data.accuracy_by_event.filter((e) => e.is_past);

  return (
    <div className="space-y-5">
      <PageHeader title="Dashboard" subtitle="Accuracy de modelos y eventos" />
      <div className="flex items-center gap-3">
        <label className="text-xs text-muted-foreground">Min peleas</label>
        <Input type="number" value={minFights}
               onChange={(e) => setMinFights(Math.max(0, Number(e.target.value)))}
               className="w-20" />
        <Button variant="primary" disabled={invalidate.isPending}
                onClick={() => invalidate.mutate(minFights)}>
          Actualizar
        </Button>
        {invalidate.isPending && recalc.data?.is_running && (
          <span className="text-xs text-muted-foreground">{recalc.data.step}</span>
        )}
      </div>

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
