import { useState } from "react";
import { motion } from "framer-motion";
import type { FighterProfile } from "../../api/client";

interface FighterProfileHeaderProps {
  fighter: FighterProfile;
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((word) => word[0])
    .join("")
    .toUpperCase()
    .slice(0, 3);
}

function eloColor(elo: number): string {
  if (elo > 1600) return "text-success";
  if (elo < 1400) return "text-destructive";
  return "text-muted";
}

const PHYSICAL_KEYS: { label: string; keys: string[] }[] = [
  { label: "Altura", keys: ["Height", "height"] },
  { label: "Peso", keys: ["Weight", "weight"] },
  { label: "Alcance", keys: ["Reach", "reach"] },
  { label: "Postura", keys: ["Stance", "STANCE", "stance"] },
  { label: "Fecha Nac.", keys: ["DOB", "dob", "Date of Birth"] },
  { label: "División", keys: ["Weight class", "weight_class", "WeightClass"] },
];

function getStat(stats: Record<string, string | number>, keys: string[]): string {
  for (const k of keys) {
    if (stats[k]) return String(stats[k]);
  }
  return "—";
}

export function FighterProfileHeader({ fighter }: FighterProfileHeaderProps) {
  const [photoError, setPhotoError] = useState(false);
  const hasPhoto = !!fighter.photo_url && !photoError;

  const record = getStat(fighter.stats, ["Record", "record"]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="bg-card border border-border rounded-xl p-6"
    >
      <div className="flex flex-col sm:flex-row gap-6">
        {/* Photo */}
        <div className="flex-shrink-0">
          {hasPhoto ? (
            <img
              src={fighter.photo_url}
              alt={fighter.name}
              onError={() => setPhotoError(true)}
              className="w-[200px] h-[240px] object-contain object-bottom border-b-2 border-b-accent"
            />
          ) : (
            <div className="w-[200px] h-[240px] bg-card border-b-2 border-b-accent flex items-center justify-center text-3xl font-bold text-muted">
              {getInitials(fighter.name)}
            </div>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          {/* Name */}
          <h2
            className="text-foreground leading-tight mb-1"
            style={{ fontFamily: "'Oswald', sans-serif", fontSize: "2.5rem", fontWeight: 700 }}
          >
            {fighter.name}
          </h2>

          {/* Record + ELO row */}
          <div className="flex flex-wrap items-end gap-6 mb-5">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-0.5">
                Récord
              </p>
              <span
                className="text-foreground leading-none"
                style={{ fontFamily: "'Oswald', sans-serif", fontSize: "1.75rem", fontWeight: 600 }}
              >
                {record}
              </span>
            </div>

            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-0.5">
                ELO Rating
              </p>
              <span
                className={`leading-none ${eloColor(fighter.elo)}`}
                style={{ fontFamily: "'Oswald', sans-serif", fontSize: "1.75rem", fontWeight: 600 }}
              >
                {Math.round(fighter.elo)}
              </span>
            </div>

            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-0.5">
                Peleas
              </p>
              <span
                className="text-foreground leading-none"
                style={{ fontFamily: "'Oswald', sans-serif", fontSize: "1.75rem", fontWeight: 600 }}
              >
                {fighter.n_fights}
              </span>
            </div>
          </div>

          {/* Physical stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2">
            {PHYSICAL_KEYS.map(({ label, keys }) => {
              const val = getStat(fighter.stats, keys);
              if (val === "—") return null;
              return (
                <div key={label} className="flex gap-2 items-baseline">
                  <span className="text-[11px] text-muted-foreground flex-shrink-0 min-w-[56px]">
                    {label}
                  </span>
                  <span className="text-sm text-foreground font-medium truncate">{val}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
