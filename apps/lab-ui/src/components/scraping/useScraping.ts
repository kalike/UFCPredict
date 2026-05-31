import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ScrapingStatus } from "../../api/client";

export type DerivedStatus = "idle" | "running" | "completed" | "error";

/** Collapse the lab-api status shape into a single UI-friendly state. */
export function deriveStatus(s: ScrapingStatus | undefined): DerivedStatus {
  if (!s) return "idle";
  if (s.error) return "error";
  if (s.is_running) return "running";
  if (s.finished_at) return "completed";
  return "idle";
}

export function useScrapingStatus() {
  return useQuery({
    queryKey: ["scraping-status"],
    queryFn: api.scrapingStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? 1500 : false),
  });
}

export function usePhotosStatus() {
  return useQuery({
    queryKey: ["scraping-photos-status"],
    queryFn: api.photoScrapeStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? 1500 : false),
  });
}

export function useScrapingRuns(isBusy: boolean) {
  return useQuery({
    queryKey: ["scraping-runs"],
    queryFn: api.scrapingRuns,
    // Refresh the audit log periodically while any job is running so a freshly
    // finished scrape/photo run appears without a manual reload.
    refetchInterval: isBusy ? 4000 : false,
  });
}

export function useStartScraping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (letters?: string) => api.scrapingStart(letters),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scraping-status"] });
      qc.invalidateQueries({ queryKey: ["scraping-runs"] });
    },
  });
}

export function useStartPhotos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.photoScrapeStart(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scraping-photos-status"] });
      qc.invalidateQueries({ queryKey: ["scraping-runs"] });
    },
  });
}
