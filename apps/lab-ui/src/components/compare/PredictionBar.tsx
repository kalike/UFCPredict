import { motion } from "framer-motion";

interface PredictionBarProps {
  fighter1: string;
  fighter2: string;
  /** Probabilidad de F1 ganar, entre 0 y 1 */
  probF1: number;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function PredictionBar({ fighter1, fighter2, probF1, size = "md", className = "" }: PredictionBarProps) {
  const pct1 = Math.round(probF1 * 100);
  const pct2 = 100 - pct1;

  const barHeight = { sm: "h-1.5", md: "h-2.5", lg: "h-4" }[size];
  const fontSize = { sm: "text-[10px]", md: "text-xs", lg: "text-sm" }[size];
  const numSize = { sm: "text-sm", md: "text-base", lg: "text-xl" }[size];

  return (
    <div className={`w-full ${className}`}>
      {/* Percentages */}
      <div className={`flex justify-between font-semibold mb-1.5 ${numSize}`}>
        <span className="text-accent" style={{ fontFamily: "'Oswald', sans-serif" }}>{pct1}%</span>
        <span className="text-info" style={{ fontFamily: "'Oswald', sans-serif" }}>{pct2}%</span>
      </div>

      {/* Bar */}
      <div className={`rounded-full overflow-hidden bg-border flex ${barHeight}`}>
        <motion.div
          className="h-full bg-accent"
          initial={{ width: 0 }}
          animate={{ width: `${pct1}%` }}
          transition={{ duration: 0.7, ease: "easeOut" }}
        />
        <motion.div
          className="h-full bg-info flex-1"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.7, delay: 0.1 }}
        />
      </div>

      {/* Fighter names */}
      <div className={`flex justify-between mt-1.5 text-muted-foreground ${fontSize}`}>
        <span className="truncate max-w-[45%]">{fighter1}</span>
        <span className="truncate max-w-[45%] text-right">{fighter2}</span>
      </div>
    </div>
  );
}
