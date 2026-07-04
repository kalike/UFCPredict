import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, UserBet } from "../../api/client";

export const useMyBets = (
  filters: { event_id?: number; status?: string; bet_type?: string } = {},
) =>
  useQuery({ queryKey: ["user-bets", filters], queryFn: () => api.listUserBets(filters) });

export const useMyBetsStats = (eventId?: number) =>
  useQuery({ queryKey: ["user-bets-stats", eventId], queryFn: () => api.userBetsStats(eventId) });

export const useUpdateBet = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; patch: Partial<UserBet> }) => api.updateUserBet(v.id, v.patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-bets"] });
      qc.invalidateQueries({ queryKey: ["user-bets-stats"] });
    },
  });
};

export const useDeleteBet = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteUserBet(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-bets"] });
      qc.invalidateQueries({ queryKey: ["user-bets-stats"] });
    },
  });
};
