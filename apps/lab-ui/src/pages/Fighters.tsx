import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { AlertCircle } from "lucide-react";
import { PageHeader, Skeleton } from "../components/ui";
import { FighterAutocomplete } from "../components/fighters/FighterAutocomplete";
import { FighterProfileHeader } from "../components/fighters/FighterProfileHeader";
import { CareerStatCards } from "../components/fighters/CareerStatCards";
import { EvolutionChart } from "../components/fighters/EvolutionChart";
import { FightHistoryTable } from "../components/fighters/FightHistoryTable";
import { FightMatchupModal } from "../components/fighters/FightMatchupModal";
import { FighterRankingList } from "../components/fighters/FighterRankingList";
import { useFighterProfile, useFightHistory } from "../components/fighters/useFighters";

function FighterLoadingSkeleton() {
  return (
    <div className="space-y-4">
      {/* Profile header skeleton */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex gap-6">
          <Skeleton className="w-[200px] h-[200px] rounded-xl flex-shrink-0" />
          <div className="flex-1 space-y-3">
            <Skeleton className="h-10 w-64 rounded-xl" />
            <Skeleton className="h-6 w-40 rounded-xl" />
            <div className="grid grid-cols-3 gap-3 mt-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-4 rounded-xl" />
              ))}
            </div>
          </div>
        </div>
      </div>
      {/* Career stat cards skeleton */}
      <div className="grid grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
      {/* Chart skeleton */}
      <Skeleton className="h-72 rounded-xl" />
      {/* Table skeleton */}
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

export default function FightersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedFightIndex, setSelectedFightIndex] = useState<number | null>(null);

  const nameFromUrl = searchParams.get("name") ?? "";

  function handleSelectFighter(name: string) {
    if (name) {
      setSearchParams({ name });
    } else {
      setSearchParams({});
    }
    setSelectedFightIndex(null);
  }

  const {
    data: fighter,
    isLoading: fighterLoading,
    isError: fighterError,
  } = useFighterProfile(nameFromUrl || null);

  const {
    data: history,
    isError: historyError,
  } = useFightHistory(nameFromUrl || null);

  const hasHistory = !historyError && !!history && history.length > 0;

  return (
    <div className="space-y-4">
      <PageHeader title="Peleadores" subtitle="Búsqueda, perfil y ranking ELO" />

      {/* Search */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <FighterAutocomplete
          value={nameFromUrl}
          onChange={handleSelectFighter}
          placeholder="Buscar luchador…"
          className="w-full"
        />
      </motion.div>

      {/* Content */}
      {nameFromUrl && (
        <>
          {fighterLoading && <FighterLoadingSkeleton />}

          {fighterError && !fighterLoading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2 text-destructive py-8"
            >
              <AlertCircle size={18} />
              <span className="text-sm">No se encontró al luchador</span>
            </motion.div>
          )}

          {fighter && !fighterLoading && (
            <div className="space-y-4">
              <FighterProfileHeader fighter={fighter} />

              <CareerStatCards careerStats={fighter.career_stats} />

              {hasHistory && history && (
                <>
                  <EvolutionChart history={history} />
                  <FightHistoryTable
                    history={history}
                    fighterName={fighter.name}
                    onSelectFight={setSelectedFightIndex}
                  />
                </>
              )}
            </div>
          )}
        </>
      )}

      {!nameFromUrl && (
        <FighterRankingList onSelect={handleSelectFighter} />
      )}

      {/* Matchup modal */}
      {fighter && selectedFightIndex !== null && (
        <FightMatchupModal
          fighterName={fighter.name}
          fightIndex={selectedFightIndex}
          onClose={() => setSelectedFightIndex(null)}
        />
      )}
    </div>
  );
}
