import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";

export function useHpStatus(activeMs = 1000, idleMs = 5000) {
  return useQuery({
    queryKey: ["hp-status"],
    queryFn: api.hpStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? activeMs : idleMs),
  });
}

export function useHpStudies() {
  return useQuery({ queryKey: ["hp-studies"], queryFn: api.hpStudies });
}

export function useHpTrials(studyId: number | null, live: boolean) {
  return useQuery({
    queryKey: ["hp-trials", studyId],
    queryFn: () => api.hpTrials(studyId!),
    enabled: studyId != null,
    refetchInterval: live ? 1500 : false,
  });
}
