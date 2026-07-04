import { useMutation, useQuery } from "@tanstack/react-query";
import { api, BettingConfig } from "../../api/client";

export const useBettingDefaults = () =>
  useQuery({ queryKey: ["betting-defaults"], queryFn: api.bettingDefaults, staleTime: Infinity });

export const useBacktest = () =>
  useMutation({ mutationFn: (cfg: BettingConfig) => api.runBacktest(cfg) });

export const useRecommend = () =>
  useMutation({ mutationFn: (v: { sessionId: number; config: BettingConfig }) =>
    api.recommend(v.sessionId, v.config) });
