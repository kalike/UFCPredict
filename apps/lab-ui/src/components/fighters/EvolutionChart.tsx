import { useState } from "react";
import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { FightStatsRecord } from "../../api/client";

interface EvolutionChartProps {
  history: FightStatsRecord[];
}

type NumericFightKey = "sig_str_landed" | "td_landed" | "kd_landed" | "ctrl_seconds" | "sig_str_received";

interface MetricConfig {
  key: NumericFightKey;
  label: string;
}

const METRICS: MetricConfig[] = [
  { key: "sig_str_landed", label: "Sig Strikes" },
  { key: "td_landed", label: "Takedowns" },
  { key: "kd_landed", label: "Knockdowns" },
  { key: "ctrl_seconds", label: "Control (seg)" },
  { key: "sig_str_received", label: "Recibidas" },
];

interface ChartPoint {
  x: string;
  value: number;
  result: string;
}

interface CustomDotProps {
  cx?: number;
  cy?: number;
  payload?: { result: string };
}

function CustomDot({ cx, cy, payload }: CustomDotProps) {
  const color =
    payload?.result?.startsWith("W") || payload?.result === "win"
      ? "#22c55e"
      : payload?.result?.startsWith("L") || payload?.result === "loss"
        ? "#ef4444"
        : "#64748b";
  if (cx == null || cy == null) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill={color}
      stroke="var(--color-card)"
      strokeWidth={2}
    />
  );
}

function isWin(result: string | undefined): boolean {
  return !!result && (result.startsWith("W") || result === "win");
}

function isLoss(result: string | undefined): boolean {
  return !!result && (result.startsWith("L") || result === "loss");
}

interface TooltipPayloadItem {
  value: number;
  payload: ChartPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const item = payload[0];
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-foreground font-medium mb-0.5">{item.payload.x}</p>
      <p className="text-accent">{item.value}</p>
      <p
        className={
          isWin(item.payload.result)
            ? "text-success"
            : isLoss(item.payload.result)
              ? "text-destructive"
              : "text-muted"
        }
      >
        {item.payload.result}
      </p>
    </div>
  );
}

export function EvolutionChart({ history }: EvolutionChartProps) {
  const [activeMetric, setActiveMetric] = useState<NumericFightKey>("sig_str_landed");

  const sorted = [...history].sort((a, b) => a.fight_index - b.fight_index);

  const data: ChartPoint[] = sorted.map((fight) => ({
    x: fight.opponent,
    value: fight[activeMetric] ?? 0,
    result: fight.result,
  }));

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.2 }}
      className="bg-card border border-border rounded-xl p-5"
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h3
          className="text-foreground text-sm font-semibold"
          style={{ fontFamily: "'Oswald', sans-serif" }}
        >
          Evolución por Pelea
        </h3>
        <div className="flex flex-wrap gap-1">
          {METRICS.map((m) => (
            <button
              key={m.key}
              onClick={() => setActiveMetric(m.key)}
              className={`px-3 py-1 rounded-lg text-[11px] font-medium transition-colors ${
                activeMetric === m.key
                  ? "bg-accent/10 text-accent border border-accent/30"
                  : "text-muted-foreground hover:text-foreground border border-border hover:border-border-hover"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} margin={{ top: 8, right: 12, left: -10, bottom: 40 }}>
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke="var(--color-border)"
            strokeDasharray="3 3"
            vertical={false}
          />
          <XAxis
            dataKey="x"
            tick={{
              fill: "var(--color-muted-foreground)",
              fontSize: 10,
            }}
            angle={-35}
            textAnchor="end"
            interval={0}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--color-accent)"
            strokeWidth={2}
            fill="url(#areaGrad)"
            dot={<CustomDot />}
            activeDot={{ r: 7, fill: "var(--color-accent)", stroke: "var(--color-card)", strokeWidth: 2 }}
            animationDuration={800}
          />
        </AreaChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
