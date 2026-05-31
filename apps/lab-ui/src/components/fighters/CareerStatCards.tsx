import { motion } from "framer-motion";
import { fmtPct } from "../../lib/formatters";

interface CareerStatCardsProps {
  careerStats: Record<string, number>;
}

interface StatCard {
  label: string;
  value: string;
}

function buildCards(cs: Record<string, number>): StatCard[] {
  const koRate = cs["ko_rate"] != null ? fmtPct(cs["ko_rate"]) : "—";
  const subRate = cs["sub_rate"] != null ? fmtPct(cs["sub_rate"]) : "—";
  const sigStrAcc = cs["sig_str_accuracy"] != null ? fmtPct(cs["sig_str_accuracy"]) : "—";
  const tdAcc = cs["td_accuracy"] != null ? fmtPct(cs["td_accuracy"]) : "—";

  const ctrlRaw = cs["ctrl_per_minute"] ?? cs["ctrl_minutes_per_fight"];
  const ctrl = ctrlRaw != null ? `${ctrlRaw.toFixed(2)} min` : "—";

  const kdRaw = cs["avg_kd"] ?? cs["kd_per_fight"];
  const avgKd = kdRaw != null ? kdRaw.toFixed(2) : "—";

  return [
    { label: "KO Rate", value: koRate },
    { label: "Sub Rate", value: subRate },
    { label: "Sig Str Acc", value: sigStrAcc },
    { label: "TD Accuracy", value: tdAcc },
    { label: "Ctrl Time/min", value: ctrl },
    { label: "Avg KD", value: avgKd },
  ];
}

export function CareerStatCards({ careerStats }: CareerStatCardsProps) {
  const cards = buildCards(careerStats);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      className="grid grid-cols-3 gap-3"
    >
      {cards.map(({ label, value }) => (
        <div
          key={label}
          className="bg-card border border-border rounded-xl p-4 card-hover-glow"
        >
          <p className="text-[10px] text-muted uppercase tracking-widest mb-2">{label}</p>
          <p
            className="text-2xl text-foreground"
            style={{ fontFamily: "'Oswald', sans-serif", fontWeight: 600 }}
          >
            {value}
          </p>
        </div>
      ))}
    </motion.div>
  );
}
