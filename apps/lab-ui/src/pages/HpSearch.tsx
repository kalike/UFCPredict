import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader } from "../components/ui";
import { HpSearchForm, type HpJob } from "../components/hp/HpSearchForm";
import { HpSearchMonitor } from "../components/hp/HpSearchMonitor";
import { HpStudyResults } from "../components/hp/HpStudyResults";
import { TrainingMonitor } from "../components/hp/TrainingMonitor";
import { useHpStatus, useHpStudies } from "../components/hp/useHpSearch";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function HpSearchPage() {
  const qc = useQueryClient();
  const trainable = useQuery({ queryKey: ["trainable"], queryFn: api.trainable });
  const studies = useHpStudies();

  const [queueActive, setQueueActive] = useState(false);
  const [queueIndex, setQueueIndex] = useState(0);
  const [queueTotal, setQueueTotal] = useState(0);
  const [currentNTrials, setCurrentNTrials] = useState(0);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [adopting, setAdopting] = useState(false);
  const [showTraining, setShowTraining] = useState(false);
  const runningRef = useRef(false);

  const status = useHpStatus();

  const trainStatus = useQuery({
    queryKey: ["train-status"],
    queryFn: api.trainStatus,
    refetchInterval: (q) => (adopting || q.state.data?.is_running ? 1500 : false),
  });

  // Adoption finished once training is no longer running.
  useEffect(() => {
    if (adopting && trainStatus.data && !trainStatus.data.is_running) {
      setAdopting(false);
      qc.invalidateQueries({ queryKey: ["hp-studies"] });
    }
  }, [adopting, trainStatus.data, qc]);

  const trainRunning = !!trainStatus.data?.is_running;
  const busy = queueActive || !!status.data?.is_running || adopting || trainRunning;

  async function onDeleteStudy(studyId: number) {
    setLaunchError(null);
    try {
      await api.hpDeleteStudy(studyId);
      qc.invalidateQueries({ queryKey: ["hp-studies"] });
    } catch (e) {
      setLaunchError(e instanceof Error ? e.message : "No se pudo eliminar el job");
    }
  }

  async function onDeleteManyStudies(studyIds: number[]) {
    setLaunchError(null);
    try {
      await api.hpDeleteStudiesBatch(studyIds);
      qc.invalidateQueries({ queryKey: ["hp-studies"] });
    } catch (e) {
      setLaunchError(e instanceof Error ? e.message : "No se pudieron eliminar los jobs");
    }
  }

  async function onAdopt(studyId: number, trialIdxs: number[]) {
    setLaunchError(null);
    setAdopting(true);
    setShowTraining(true);
    try {
      const res = await api.hpAdopt(trialIdxs.map((i) => ({ study_id: studyId, trial_idx: i })));
      if (!res.started) {
        setAdopting(false);
        setLaunchError(res.message ?? "No se pudo lanzar el entrenamiento");
      } else {
        qc.invalidateQueries({ queryKey: ["train-status"] });
      }
    } catch (e) {
      setAdopting(false);
      setLaunchError(e instanceof Error ? e.message : "Error al adoptar trials");
    }
  }

  // Wait until the given study has started and then finished.
  async function waitUntilDone(studyId: number | null) {
    for (let tries = 0; tries < 4000; tries++) {
      await sleep(1000);
      const s = await api.hpStatus();
      qc.setQueryData(["hp-status"], s);
      if (studyId != null && s.study_id === studyId && !s.is_running) return;
      // Defensive: a different study finished or nothing is running after a grace period.
      if (!s.is_running && tries > 3) return;
    }
  }

  async function runQueue(jobs: HpJob[]) {
    if (runningRef.current) return;
    runningRef.current = true;
    setQueueActive(true);
    setQueueTotal(jobs.length);
    setLaunchError(null);
    try {
      for (let i = 0; i < jobs.length; i++) {
        const job = jobs[i];
        setQueueIndex(i);
        setCurrentNTrials(job.n_trials);
        const res = await api.hpStart({
          model_short: job.model,
          feature_set: job.feature_set,
          feat_type: job.feat_type,
          dataset: job.dataset,
          min_fights: job.min_fights,
          n_trials: job.n_trials,
          objectives: job.objectives,
          overfit_penalty: job.overfit_penalty,
        });
        if (!res.started) {
          setLaunchError(res.message ?? `No se pudo iniciar ${job.model}`);
          continue;
        }
        await waitUntilDone(res.study_id);
        qc.invalidateQueries({ queryKey: ["hp-studies"] });
      }
    } catch (e) {
      setLaunchError(e instanceof Error ? e.message : "Error lanzando la cola");
    } finally {
      runningRef.current = false;
      setQueueActive(false);
      qc.invalidateQueries({ queryKey: ["hp-studies"] });
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Optimización de Modelos"
        subtitle="Búsqueda de hiperparámetros con Optuna · XGB / RF / CB / Deep"
      />

      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-5">
        {/* Left: form */}
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-muted-foreground mb-4">
            Nueva búsqueda
          </h3>
          <HpSearchForm
            models={trainable.data ?? []}
            busy={busy}
            onLaunch={runQueue}
          />
          {launchError && (
            <p className="mt-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
              {launchError}
            </p>
          )}
        </Card>

        {/* Right: live monitor */}
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-muted-foreground mb-4">
            Monitor
          </h3>
          <HpSearchMonitor
            status={status.data}
            nTrials={currentNTrials || (status.data?.completed_trials ?? 0)}
            queueIndex={queueIndex}
            queueTotal={queueTotal}
            live={queueActive || !!status.data?.is_running}
          />
          {showTraining && (
            <div className="mt-4">
              <TrainingMonitor
                status={trainStatus.data}
                onDismiss={() => setShowTraining(false)}
              />
            </div>
          )}
        </Card>
      </div>

      {/* Job results — expand any job to inspect its trials and adopt */}
      <Card>
        <h3 className="font-display text-sm uppercase tracking-widest text-muted-foreground mb-3">
          Resultados de jobs
        </h3>
        <HpStudyResults
          studies={studies.data ?? []}
          adopting={adopting}
          liveStudyId={status.data?.is_running ? status.data.study_id : null}
          onAdopt={onAdopt}
          onDelete={onDeleteStudy}
          onDeleteMany={onDeleteManyStudies}
        />
      </Card>
    </div>
  );
}
