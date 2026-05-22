import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";

export function useFighterProfile(name: string | null) {
  return useQuery({
    queryKey: ["fighters", "detail", name],
    queryFn: () => api.fighterByName(name!),
    enabled: !!name,
    staleTime: 5 * 60 * 1000,
  });
}

export function useFightHistory(name: string | null) {
  return useQuery({
    queryKey: ["fighters", "history", name],
    queryFn: () => api.fightHistoryStats(name!),
    enabled: !!name,
    staleTime: 5 * 60 * 1000,
  });
}

export function useFightMatchup(name: string | null, fightIndex: number | null) {
  return useQuery({
    queryKey: ["fighters", "matchup", name, fightIndex],
    queryFn: () => api.fightMatchup(name!, fightIndex!),
    enabled: !!name && fightIndex != null,
    staleTime: 10 * 60 * 1000,
  });
}

export function useFighterRanking(limit = 20) {
  return useQuery({
    queryKey: ["fighters", "ranking", limit],
    queryFn: () => api.fighterRanking(limit),
    staleTime: 60 * 60 * 1000, // 1 hour — ranking solo cambia tras eventos
  });
}
