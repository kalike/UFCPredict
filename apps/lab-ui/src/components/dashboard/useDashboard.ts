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
    // Poll while the (background) recalc is active. NOT tied to the POST's
    // in-flight state — that resolves in milliseconds while the recalc runs
    // for ~minutes, which made the progress indicator vanish instantly.
    refetchInterval: enabled ? 2000 : false,
    enabled,
  });
}

export function useInvalidateDashboard() {
  // Fires the recalc POST, which returns immediately while the recalc runs in
  // the background. We deliberately do NOT invalidate the summary here: doing
  // so on POST success refetches stale data before the recalc finishes. The
  // caller invalidates once the recalc actually completes (see Dashboard.tsx).
  return useMutation({
    mutationFn: (minFights: number) => api.dashboardInvalidate(minFights, true),
  });
}
