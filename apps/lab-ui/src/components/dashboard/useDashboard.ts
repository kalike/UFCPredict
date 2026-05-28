import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";

export function useDashboard(minFights = 0) {
  return useQuery({
    queryKey: ["dashboard", "summary", minFights],
    queryFn: () => api.dashboardSummary(minFights),
    staleTime: 5 * 60 * 1000,
  });
}

export function useEventFights(eventName: string | null) {
  return useQuery({
    queryKey: ["dashboard", "event-fights", eventName],
    queryFn: () => api.dashboardEventFights(eventName as string),
    enabled: !!eventName,
    staleTime: 10 * 60 * 1000,
  });
}

export function useRecalculationStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["dashboard", "recalc-status"],
    queryFn: () => api.dashboardRecalcStatus(),
    refetchInterval: enabled ? 2000 : false,
  });
}

export function useInvalidateDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (minFights: number) => api.dashboardInvalidate(minFights, true),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}
