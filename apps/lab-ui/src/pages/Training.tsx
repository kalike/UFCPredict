import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type TrainJob } from "../api/client";
import { PageHeader } from "../components/ui";
import { RetrainForm } from "../features/training/RetrainForm";
import { TrainingMonitor } from "../features/training/TrainingMonitor";

export default function TrainingPage() {
  const qc = useQueryClient();
  const launch = useMutation({
    mutationFn: (jobs: TrainJob[]) => api.retrainBatch(jobs),
    onSuccess: () => {
      // Kick the monitor's polling immediately and refresh model lists.
      qc.invalidateQueries({ queryKey: ["train-status"] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });

  return (
    <div>
      <PageHeader title="Training" subtitle="Reentrenamiento por cola de jobs + monitor en vivo" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <RetrainForm disabled={launch.isPending} onLaunch={(jobs) => launch.mutate(jobs)} />
        <TrainingMonitor />
      </div>
      {launch.data && !launch.data.started && (
        <p className="mt-3 text-xs text-red-400">{launch.data.message}</p>
      )}
    </div>
  );
}
