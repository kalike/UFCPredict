import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { FightInput, SaveSessionRequest } from "../../api/client";

// ─── Queries ──────────────────────────────────────────

export function usePastEvents() {
  return useQuery({
    queryKey: ["predictions", "past-events"],
    queryFn: api.pastEvents,
    staleTime: 2 * 60 * 1000,
  });
}

export function usePastEventPredictions(name: string | null) {
  return useQuery({
    queryKey: ["predictions", "past-event", name],
    queryFn: () => api.pastEventPredictions(name!),
    enabled: !!name,
    staleTime: 2 * 60 * 1000,
  });
}

export function useSessions() {
  return useQuery({
    queryKey: ["predictions", "sessions"],
    queryFn: api.listSessions,
    staleTime: 30 * 1000,
  });
}

export function useSession(id: number | null) {
  return useQuery({
    queryKey: ["predictions", "session", id],
    queryFn: () => api.getSession(id!),
    enabled: id != null,
    staleTime: 30 * 1000,
  });
}

// ─── Mutations ────────────────────────────────────────

export function usePredictFights() {
  return useMutation({
    mutationFn: ({ event, fights }: { event: string; fights: FightInput[] }) =>
      api.predictFights(event, fights),
  });
}

export function useTapologyScrape() {
  return useMutation({ mutationFn: (url: string) => api.tapologyScrape(url) });
}

export function useSaveSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SaveSessionRequest) => api.saveSession(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["predictions", "sessions"] }),
  });
}

export function useMarkResult(sessionId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ index, winner }: { index: number; winner: string | null }) =>
      api.markResult(sessionId, index, winner),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["predictions", "session", sessionId] });
      qc.invalidateQueries({ queryKey: ["predictions", "sessions"] });
    },
  });
}

export function usePromoteSession(sessionId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { event_date?: string | null; event_location?: string | null }) =>
      api.promoteSession(sessionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["predictions", "session", sessionId] });
      qc.invalidateQueries({ queryKey: ["predictions", "sessions"] });
    },
  });
}

export function useImportOdds(sessionId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (url: string) => api.importOdds(sessionId, url),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["predictions", "session", sessionId] }),
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteSession(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["predictions", "sessions"] }),
  });
}

export function useDeleteAllSessions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.deleteAllSessions(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["predictions", "sessions"] }),
  });
}
