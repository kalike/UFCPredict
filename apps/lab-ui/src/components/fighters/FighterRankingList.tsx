import { useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle } from "lucide-react";
import type { FighterRankingEntry } from "../../api/client";
import { Skeleton } from "../ui";
import { useFighterRanking } from "./useFighters";

interface FighterRankingListProps {
  onSelect: (name: string) => void;
  limit?: number;
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 3);
}

function rankBadgeClass(rank: number): string {
  if (rank <= 3) {
    return "bg-accent text-accent-foreground";
  }
  return "bg-destructive/10 text-destructive";
}

function FighterRow({
  entry,
  onSelect,
}: {
  entry: FighterRankingEntry;
  onSelect: (name: string) => void;
}) {
  const [photoError, setPhotoError] = useState(false);
  const hasPhoto = entry.has_photo && !!entry.photo_url && !photoError;

  return (
    <motion.button
      type="button"
      onClick={() => onSelect(entry.name)}
      whileHover={{ x: 2 }}
      whileTap={{ scale: 0.99 }}
      className="w-full flex items-center gap-4 bg-card border border-border rounded-lg px-4 py-2.5 text-left hover:border-accent transition-colors"
      aria-label={`Ver perfil de ${entry.name}`}
    >
      {/* Rank */}
      <div
        className={`flex-shrink-0 w-10 text-center px-1.5 py-0.5 rounded text-xs font-semibold ${rankBadgeClass(entry.rank)}`}
        style={{ fontFamily: "'Oswald', sans-serif" }}
      >
        #{entry.rank}
      </div>

      {/* Photo */}
      <div className="flex-shrink-0 w-12 h-12 rounded-full bg-muted/20 overflow-hidden flex items-center justify-center">
        {hasPhoto ? (
          <img
            src={entry.photo_url}
            alt={entry.name}
            className="w-full h-full object-cover object-top"
            onError={() => setPhotoError(true)}
          />
        ) : (
          <span
            className="text-xs text-muted-foreground"
            style={{ fontFamily: "'Oswald', sans-serif" }}
          >
            {getInitials(entry.name)}
          </span>
        )}
      </div>

      {/* Name */}
      <div
        className="flex-1 min-w-0 text-foreground uppercase truncate text-sm"
        style={{ fontFamily: "'Oswald', sans-serif" }}
        title={entry.name}
      >
        {entry.name}
      </div>

      {/* ELO */}
      <div
        className="flex-shrink-0 text-muted-foreground text-sm"
        style={{ fontFamily: "'JetBrains Mono', monospace" }}
      >
        ELO {Math.round(entry.elo)}
      </div>
    </motion.button>
  );
}

function RankingSkeleton({ count = 20 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 bg-card border border-border rounded-lg px-4 py-2.5"
        >
          <Skeleton className="w-10 h-5" />
          <Skeleton className="w-12 h-12 rounded-full" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
    </div>
  );
}

export function FighterRankingList({
  onSelect,
  limit = 20,
}: FighterRankingListProps) {
  const { data, isLoading, isError } = useFighterRanking(limit);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h2
          className="text-foreground text-xl"
          style={{ fontFamily: "'Oswald', sans-serif" }}
        >
          Top {limit} por ELO
        </h2>
        <RankingSkeleton count={limit} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 text-destructive py-8">
        <AlertCircle size={18} />
        <span className="text-sm">No se pudo cargar el ranking</span>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="text-muted-foreground text-sm py-8 text-center">
        No hay luchadores activos en el ranking.
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <h2
        className="text-foreground text-xl"
        style={{ fontFamily: "'Oswald', sans-serif" }}
      >
        Top {data.length} por ELO
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {data.map((entry) => (
          <FighterRow key={entry.name} entry={entry} onSelect={onSelect} />
        ))}
      </div>
    </motion.div>
  );
}
