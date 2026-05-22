import { useMemo } from "react";
import { motion } from "framer-motion";
import type { CompareFighterStats } from "../../api/client";

interface CompareRadarProps {
  f1: CompareFighterStats;
  f2: CompareFighterStats;
  f1Name: string;
  f2Name: string;
}

const AXES = [
  { key: "win_rate",         label: "Win Rate" },
  { key: "ko_rate",          label: "KO Rate" },
  { key: "sub_rate",         label: "Sub Rate" },
  { key: "sig_str_accuracy", label: "Sig Str %" },
  { key: "td_accuracy",      label: "TD %" },
  { key: "td_defense",       label: "TD Def" },
  { key: "sig_str_defense",  label: "Str Def" },
  { key: "recent_win_rate",  label: "Recent W" },
];

const CX = 200;
const CY = 200;
const MAX_R = 140;
const N = AXES.length;

function polarToCartesian(cx: number, cy: number, r: number, angleRad: number) {
  return { x: cx + r * Math.cos(angleRad), y: cy + r * Math.sin(angleRad) };
}

function getAngle(i: number): number {
  return -Math.PI / 2 + (2 * Math.PI * i) / N;
}

function pointsToString(pts: { x: number; y: number }[]): string {
  return pts.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
}

function buildPolygon(values: number[]): { x: number; y: number }[] {
  return values.map((v, i) => {
    const angle = getAngle(i);
    const r = v * MAX_R;
    return polarToCartesian(CX, CY, r, angle);
  });
}

function buildGrid(fraction: number): { x: number; y: number }[] {
  return Array.from({ length: N }, (_, i) => {
    const angle = getAngle(i);
    return polarToCartesian(CX, CY, MAX_R * fraction, angle);
  });
}

export function CompareRadar({ f1, f2, f1Name, f2Name }: CompareRadarProps) {
  const { f1Normalized, f2Normalized } = useMemo(() => {
    const f1Vals = AXES.map((a) => f1.career[a.key] ?? 0);
    const f2Vals = AXES.map((a) => f2.career[a.key] ?? 0);

    const normalized1 = f1Vals.map((v, i) => {
      const maxVal = Math.max(f1Vals[i], f2Vals[i]);
      return maxVal === 0 ? 0 : v / maxVal;
    });
    const normalized2 = f2Vals.map((v, i) => {
      const maxVal = Math.max(f1Vals[i], f2Vals[i]);
      return maxVal === 0 ? 0 : v / maxVal;
    });

    return { f1Normalized: normalized1, f2Normalized: normalized2 };
  }, [f1, f2]);

  const f1Points = buildPolygon(f1Normalized);
  const f2Points = buildPolygon(f2Normalized);
  const grid33 = buildGrid(0.33);
  const grid66 = buildGrid(0.66);
  const grid100 = buildGrid(1);

  const axisEndpoints = Array.from({ length: N }, (_, i) =>
    polarToCartesian(CX, CY, MAX_R, getAngle(i)),
  );

  const labelPoints = Array.from({ length: N }, (_, i) =>
    polarToCartesian(CX, CY, MAX_R + 22, getAngle(i)),
  );

  return (
    <div className="bg-card border border-border rounded-xl p-5 flex flex-col items-center gap-4">
      <h3 className="text-muted-foreground text-xs uppercase tracking-widest font-semibold self-start">
        Perfil de atributos
      </h3>

      <svg
        viewBox="0 0 400 400"
        width="100%"
        style={{ maxWidth: 400 }}
        className="overflow-visible"
        aria-label="Radar chart de atributos"
      >
        {/* Grid polygons */}
        {[grid33, grid66, grid100].map((grid, gi) => (
          <polygon
            key={gi}
            points={pointsToString(grid)}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth={gi === 2 ? 1.5 : 1}
            strokeOpacity={gi === 2 ? 0.6 : 0.35}
          />
        ))}

        {/* Axis lines */}
        {axisEndpoints.map((end, i) => (
          <line
            key={i}
            x1={CX}
            y1={CY}
            x2={end.x}
            y2={end.y}
            stroke="var(--color-border)"
            strokeWidth={1}
            strokeOpacity={0.4}
          />
        ))}

        {/* F1 polygon */}
        <motion.polygon
          points={pointsToString(f1Points)}
          style={{
            fill: "color-mix(in oklch, var(--color-accent) 20%, transparent)",
            stroke: "var(--color-accent)",
          }}
          strokeWidth={2}
          strokeLinejoin="round"
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          // @ts-expect-error framer-motion SVG transform origin
          transformOrigin={`${CX}px ${CY}px`}
        />

        {/* F2 polygon */}
        <motion.polygon
          points={pointsToString(f2Points)}
          style={{
            fill: "color-mix(in oklch, var(--color-info) 20%, transparent)",
            stroke: "var(--color-info)",
          }}
          strokeWidth={2}
          strokeLinejoin="round"
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.55, ease: "easeOut", delay: 0.1 }}
          // @ts-expect-error framer-motion SVG transform origin
          transformOrigin={`${CX}px ${CY}px`}
        />

        {/* F1 dots */}
        {f1Points.map((pt, i) => (
          <motion.circle
            key={`f1-dot-${i}`}
            cx={pt.x}
            cy={pt.y}
            r={4}
            style={{ fill: "var(--color-accent)" }}
            stroke="var(--color-background)"
            strokeWidth={1.5}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, delay: 0.5 + i * 0.03 }}
          />
        ))}

        {/* F2 dots */}
        {f2Points.map((pt, i) => (
          <motion.circle
            key={`f2-dot-${i}`}
            cx={pt.x}
            cy={pt.y}
            r={4}
            style={{ fill: "var(--color-info)" }}
            stroke="var(--color-background)"
            strokeWidth={1.5}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, delay: 0.6 + i * 0.03 }}
          />
        ))}

        {/* Axis labels */}
        {labelPoints.map((pt, i) => {
          const angle = getAngle(i);
          let anchor: "start" | "middle" | "end" = "middle";
          if (Math.cos(angle) > 0.3) anchor = "start";
          else if (Math.cos(angle) < -0.3) anchor = "end";

          return (
            <text
              key={`label-${i}`}
              x={pt.x}
              y={pt.y}
              textAnchor={anchor}
              dominantBaseline="middle"
              fontSize={10}
              fontWeight={500}
              fill="var(--color-muted)"
              style={{ fontFamily: "'Oswald', sans-serif", letterSpacing: "0.04em" }}
            >
              {AXES[i].label}
            </text>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-6 text-xs">
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block w-3 h-3 rounded-full"
            style={{ backgroundColor: "var(--color-accent)" }}
          />
          <span className="text-muted-foreground truncate max-w-[120px]">{f1Name}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block w-3 h-3 rounded-full"
            style={{ backgroundColor: "var(--color-info)" }}
          />
          <span className="text-muted-foreground truncate max-w-[120px]">{f2Name}</span>
        </div>
      </div>
    </div>
  );
}
