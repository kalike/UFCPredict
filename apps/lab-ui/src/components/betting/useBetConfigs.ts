import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, BetConfig } from "../../api/client";

export const useBetConfigs = () =>
  useQuery({ queryKey: ["bet-configs"], queryFn: api.listBetConfigs });

export const useSaveBetConfig = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; params: BetConfig["params"]; is_default?: boolean }) =>
      api.saveBetConfig(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bet-configs"] }),
  });
};

export const useDeleteBetConfig = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteBetConfig(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bet-configs"] }),
  });
};

export const useCurrentCombo = () =>
  useQuery({ queryKey: ["current-combo"], queryFn: api.currentCombo });

export const useApplyCombo = () =>
  useMutation({ mutationFn: (combo: Record<string, number>) => api.applyCombo(combo) });
