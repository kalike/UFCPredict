import { motion } from "framer-motion";
import type { FeatureImportance } from "../../api/client";

export function FeatureImportanceChart({
  importance, top = 15,
}: { importance: FeatureImportance[]; top?: number }) {
  const sorted = [...importance].sort((a, b) => b.importance - a.importance).slice(0, top);
  const max = sorted[0]?.importance ?? 1;

  return (
    <div className="space-y-1.5">
      {sorted.map((item, i) => (
        <div key={item.feature} className="flex items-center gap-2">
          <div className="w-32 text-right text-xs text-muted pr-2 truncate shrink-0" title={item.feature}>
            {item.feature}
          </div>
          <div className="flex-1 bg-border/30 rounded-r h-4 overflow-hidden">
            <motion.div
              className="bg-accent h-full rounded-r"
              initial={{ width: 0 }}
              animate={{ width: `${max > 0 ? ((item.importance / max) * 100).toFixed(0) : 0}%` }}
              transition={{ duration: 0.5, delay: i * 0.03, ease: "easeOut" }}
            />
          </div>
          <div className="w-12 text-right text-xs text-foreground shrink-0">
            {item.importance.toFixed(3)}
          </div>
        </div>
      ))}
    </div>
  );
}
