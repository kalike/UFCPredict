import { useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { StrategyResult } from "../../api/client";

const STRATEGY_COLORS: Record<string, string> = {
  singles: "var(--color-success)",
  doubles: "var(--color-info)",
  triples: "var(--color-accent-2)",
  baseline: "var(--color-muted-foreground)",
  bankroll: "var(--color-warning, #f59e0b)",
};

const STRATEGY_LABELS: Record<string, string> = {
  singles: "Singles",
  doubles: "Doubles",
  triples: "Triples",
  baseline: "Baseline",
  bankroll: "Bankroll",
};

interface TooltipPayload {
  dataKey: string;
  value: number;
  color: string;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border rounded-lg p-3 text-xs shadow-xl min-w-[140px]">
      <div className="font-semibold text-muted mb-2">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ background: entry.color }}
            />
            <span className="text-muted">
              {STRATEGY_LABELS[entry.dataKey] || entry.dataKey}
            </span>
          </span>
          <span className="text-foreground font-semibold tabular-nums">
            ${entry.value?.toFixed(0)}
          </span>
        </div>
      ))}
    </div>
  );
}

interface EquityCurveProps {
  strategies: Record<string, StrategyResult>;
}

export function EquityCurve({ strategies }: EquityCurveProps) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  const bankrollHistory = Object.values(strategies).find(
    (s) => s.bankroll_history && s.bankroll_history.length > 1
  )?.bankroll_history;
  const hasBankrollHistory = !!bankrollHistory && bankrollHistory.length > 1;

  const maxLen = Math.max(
    0,
    ...Object.values(strategies).map((s) => s.cumulative_pnl.length)
  );

  if (maxLen === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
          Equity Curve
        </h3>
        <div className="flex items-center justify-center h-32 text-xs text-muted-foreground">
          Sin datos de equity
        </div>
      </div>
    );
  }

  const singleEvents = strategies.singles?.events || [];

  const chartData = Array.from({ length: maxLen }, (_, i) => {
    const row: Record<string, string | number> = {
      event:
        i === 0
          ? "Inicio"
          : singleEvents[i - 1]?.event_name?.replace(/UFC\s*/i, "") ||
            `E${i}`,
    };
    for (const key of Object.keys(strategies)) {
      row[key] =
        strategies[key].cumulative_pnl[i] ??
        strategies[key].cumulative_pnl.at(-1) ??
        0;
    }
    if (hasBankrollHistory) {
      row.bankroll = bankrollHistory[i] ?? bankrollHistory.at(-1) ?? 0;
    }
    return row;
  });

  const toggleSeries = (e: {
    dataKey?: string | number | ((obj: unknown) => unknown);
  }) => {
    const key = typeof e.dataKey === "string" ? e.dataKey : null;
    if (!key) return;
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        Equity Curve
      </h3>
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={chartData} margin={{ top: 5, right: 10, bottom: 30, left: 0 }}>
          <defs>
            {Object.entries(STRATEGY_COLORS).map(([key, color]) => (
              <linearGradient key={key} id={`grad-${key}`} x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0%"
                  stopColor={color}
                  stopOpacity={key === "bankroll" ? 0.08 : 0.15}
                />
                <stop offset="100%" stopColor={color} stopOpacity={0.05} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="event"
            tick={{ fill: "var(--color-muted-foreground)", fontSize: 10 }}
            angle={-35}
            textAnchor="end"
            interval={0}
            height={60}
          />
          <YAxis
            yAxisId="left"
            tickFormatter={(v: number) => `$${v}`}
            tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
            width={60}
          />
          {hasBankrollHistory && (
            <YAxis
              yAxisId="right"
              orientation="right"
              tickFormatter={(v: number) => `$${v}`}
              tick={{ fill: "var(--color-warning, #f59e0b)", fontSize: 11 }}
              width={65}
            />
          )}
          <ReferenceLine
            yAxisId="left"
            y={0}
            stroke="var(--color-muted-foreground)"
            strokeDasharray="3 3"
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend onClick={toggleSeries} wrapperStyle={{ cursor: "pointer" }} />
          {Object.keys(strategies).map((key) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              stroke={STRATEGY_COLORS[key] || "var(--color-foreground)"}
              fill={`url(#grad-${key})`}
              strokeWidth={key === "baseline" ? 1 : 2}
              strokeDasharray={key === "baseline" ? "5 3" : undefined}
              dot={false}
              hide={hidden.has(key)}
              name={STRATEGY_LABELS[key] || key}
              yAxisId="left"
            />
          ))}
          {hasBankrollHistory && (
            <Area
              type="monotone"
              dataKey="bankroll"
              stroke={STRATEGY_COLORS.bankroll}
              fill={`url(#grad-bankroll)`}
              strokeWidth={2}
              strokeDasharray="4 2"
              dot={false}
              hide={hidden.has("bankroll")}
              name={STRATEGY_LABELS.bankroll}
              yAxisId="right"
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
