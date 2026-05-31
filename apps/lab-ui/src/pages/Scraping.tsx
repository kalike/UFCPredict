import { PageHeader } from "../components/ui";
import { ScrapingControl } from "../components/scraping/ScrapingControl";
import { PhotosControl } from "../components/scraping/PhotosControl";
import { PipelineProgress } from "../components/scraping/PipelineProgress";
import { ScrapingLog } from "../components/scraping/ScrapingLog";
import { ScrapingRuns } from "../components/scraping/ScrapingRuns";
import {
  useScrapingStatus,
  usePhotosStatus,
  useScrapingRuns,
} from "../components/scraping/useScraping";

export default function ScrapingPage() {
  const { data: scraping } = useScrapingStatus();
  const { data: photos } = usePhotosStatus();

  const isBusy = !!scraping?.is_running || !!photos?.is_running;
  const { data: runs, isLoading: runsLoading } = useScrapingRuns(isBusy);

  // One console for both jobs: show whichever is active, else the last tails.
  const logLines = scraping?.is_running
    ? scraping.log_lines ?? []
    : photos?.is_running
      ? photos.log_lines ?? []
      : [...(scraping?.log_lines ?? []), ...(photos?.log_lines ?? [])];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Scraping"
        subtitle="Actualización de datos UFCStats, descarga de fotos y log de auditoría"
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Left: controls + pipeline */}
        <div className="space-y-5">
          <ScrapingControl />
          <PhotosControl />
          <PipelineProgress status={scraping} />
        </div>

        {/* Right: live log */}
        <div className="flex flex-col min-h-[28rem]">
          <ScrapingLog lines={logLines} />
        </div>
      </div>

      {/* Full-width audit log */}
      <ScrapingRuns runs={runs ?? []} isLoading={runsLoading} />
    </div>
  );
}
