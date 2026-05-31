import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { PageHeader, Skeleton } from "../components/ui";
import { FighterAutocomplete } from "../components/fighters/FighterAutocomplete";
import { useCompare } from "../components/compare/useCompare";
import { CompareHeader } from "../components/compare/CompareHeader";
import { CompareRadar } from "../components/compare/CompareRadar";
import { CompareStatCards } from "../components/compare/CompareStatCards";
import { FeatureDeltaTable } from "../components/compare/FeatureDeltaTable";
import { FighterRecentFights } from "../components/compare/FighterRecentFights";

function CompareSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-56 rounded-xl" />
      <div className="grid grid-cols-2 gap-5">
        <Skeleton className="h-80 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
      <Skeleton className="h-64 rounded-xl" />
      <Skeleton className="h-48 rounded-xl" />
    </div>
  );
}

export default function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const f1 = searchParams.get("f1") || "";
  const f2 = searchParams.get("f2") || "";

  const setFighter = useCallback(
    (key: "f1" | "f2", value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value) {
          next.set(key, value);
        } else {
          next.delete(key);
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const { data, isLoading, isError } = useCompare(f1 || null, f2 || null);

  const ready = !!f1 && !!f2;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Comparador"
        subtitle="Compara dos luchadores cabeza a cabeza con estadísticas y predicción"
      />

      {/* Fighter selectors */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="grid grid-cols-2 gap-4"
      >
        <FighterAutocomplete
          value={f1}
          onChange={(name) => setFighter("f1", name)}
          placeholder="Luchador 1…"
          label="Esquina roja"
        />
        <FighterAutocomplete
          value={f2}
          onChange={(name) => setFighter("f2", name)}
          placeholder="Luchador 2…"
          label="Esquina azul"
        />
      </motion.div>

      {/* Empty state */}
      {!ready && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center justify-center py-20 gap-4"
        >
          <span
            className="text-muted-foreground"
            style={{ fontFamily: "'Oswald', sans-serif", fontSize: "5rem", opacity: 0.12, lineHeight: 1 }}
          >
            VS
          </span>
          <p className="text-muted-foreground text-sm">
            Selecciona dos luchadores para comenzar la comparación
          </p>
        </motion.div>
      )}

      {ready && isLoading && <CompareSkeleton />}

      {ready && isError && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="bg-destructive/10 border border-destructive/30 rounded-xl p-6 text-center"
        >
          <p className="text-destructive font-semibold">Error cargando comparación</p>
          <p className="text-muted-foreground text-sm mt-1">
            Verifica que ambos luchadores existen en la base de datos
          </p>
        </motion.div>
      )}

      {ready && !isLoading && !isError && data && (
        <div className="space-y-5">
          {/* Hero */}
          <CompareHeader data={data} />

          {/* Radar + Stat cards side by side */}
          <div className="grid grid-cols-2 gap-5">
            <CompareRadar
              f1={data.fighter_1}
              f2={data.fighter_2}
              f1Name={data.fighter_1.name}
              f2Name={data.fighter_2.name}
            />
            <CompareStatCards data={data} />
          </div>

          {/* Feature deltas */}
          <FeatureDeltaTable
            deltas={data.feature_deltas}
            f1Name={data.fighter_1.name}
            f2Name={data.fighter_2.name}
          />

          {/* Recent fights */}
          <FighterRecentFights
            f1Name={data.fighter_1.name}
            f2Name={data.fighter_2.name}
            fights1={data.recent_fights_f1}
            fights2={data.recent_fights_f2}
          />
        </div>
      )}
    </div>
  );
}
