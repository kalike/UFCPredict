import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import type { CompareByNameResponse } from "../../api/client";
import { PredictionBar } from "./PredictionBar";

interface CompareHeaderProps {
  data: CompareByNameResponse;
}

function eloColor(elo: number): string {
  if (elo > 1600) return "text-success";
  if (elo < 1400) return "text-destructive";
  return "text-muted-foreground";
}

function FighterAvatar({
  name,
  photoUrl,
  side,
  onClick,
}: {
  name: string;
  photoUrl: string;
  side: "left" | "right";
  onClick: () => void;
}) {
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const accentLine = side === "left" ? "border-b-accent" : "border-b-info";

  return (
    <button
      onClick={onClick}
      className="flex-shrink-0 focus:outline-none transition-opacity hover:opacity-80"
      style={{ width: 160, height: 200 }}
      title={`Ver perfil de ${name}`}
    >
      {photoUrl ? (
        <img
          src={photoUrl}
          alt={name}
          className={`w-full h-full object-contain object-bottom border-b-2 ${accentLine}`}
          onError={(e) => {
            const target = e.currentTarget;
            target.style.display = "none";
            const sibling = target.nextElementSibling as HTMLElement | null;
            if (sibling) sibling.style.display = "flex";
          }}
        />
      ) : null}
      {/* Fallback initials */}
      <div
        className={`w-full h-full border-b-2 ${accentLine} bg-card items-center justify-center`}
        style={{ display: photoUrl ? "none" : "flex" }}
      >
        <span
          className="text-3xl font-bold text-muted-foreground"
          style={{ fontFamily: "'Oswald', sans-serif" }}
        >
          {initials}
        </span>
      </div>
    </button>
  );
}

export function CompareHeader({ data }: CompareHeaderProps) {
  const navigate = useNavigate();
  const { fighter_1, fighter_2, prediction } = data;

  const canPredict =
    prediction !== null &&
    prediction.fighter_1_has_history &&
    prediction.fighter_2_has_history;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="bg-card border border-border rounded-xl p-6"
    >
      <div className="flex items-center justify-between gap-4">
        {/* Fighter 1 */}
        <div className="flex flex-col items-center gap-3 flex-1">
          <FighterAvatar
            name={fighter_1.name}
            photoUrl={fighter_1.photo_url}
            side="left"
            onClick={() => navigate(`/fighters?name=${encodeURIComponent(fighter_1.name)}`)}
          />
          <div className="text-center">
            <h2
              className="text-foreground leading-tight"
              style={{ fontFamily: "'Oswald', sans-serif", fontSize: "1.8rem", fontWeight: 600 }}
            >
              {fighter_1.name}
            </h2>
            <span className={`text-sm font-semibold ${eloColor(fighter_1.elo)}`}>
              ELO {Math.round(fighter_1.elo)}
            </span>
          </div>
        </div>

        {/* Center: VS + bar */}
        <div className="flex flex-col items-center gap-4 min-w-[260px] max-w-[360px] w-full">
          <span
            className="text-muted-foreground leading-none select-none"
            style={{ fontFamily: "'Oswald', sans-serif", fontSize: "3rem", fontWeight: 700, letterSpacing: "0.1em" }}
          >
            VS
          </span>

          {canPredict && prediction ? (
            <div className="w-full space-y-3">
              <PredictionBar
                fighter1={fighter_1.name}
                fighter2={fighter_2.name}
                probF1={prediction.prob_f1}
                size="lg"
              />
              <p className="text-center text-[10px] uppercase tracking-widest text-muted-foreground">
                Ensemble TTA · {prediction.contributing_models.length} modelo
                {prediction.contributing_models.length === 1 ? "" : "s"} activo
                {prediction.contributing_models.length === 1 ? "" : "s"} (
                {prediction.contributing_models.join(", ")})
              </p>
            </div>
          ) : (
            <p className="text-muted-foreground text-sm text-center italic">
              Sin datos suficientes para predicción
            </p>
          )}
        </div>

        {/* Fighter 2 */}
        <div className="flex flex-col items-center gap-3 flex-1">
          <FighterAvatar
            name={fighter_2.name}
            photoUrl={fighter_2.photo_url}
            side="right"
            onClick={() => navigate(`/fighters?name=${encodeURIComponent(fighter_2.name)}`)}
          />
          <div className="text-center">
            <h2
              className="text-foreground leading-tight"
              style={{ fontFamily: "'Oswald', sans-serif", fontSize: "1.8rem", fontWeight: 600 }}
            >
              {fighter_2.name}
            </h2>
            <span className={`text-sm font-semibold ${eloColor(fighter_2.elo)}`}>
              ELO {Math.round(fighter_2.elo)}
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
