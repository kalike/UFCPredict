import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";

export function useCompare(f1: string | null, f2: string | null) {
  return useQuery({
    queryKey: ["compare", "by-name", f1, f2],
    queryFn: () => api.compareByName(f1!, f2!),
    enabled: !!f1 && !!f2,
    staleTime: 5 * 60 * 1000,
  });
}
