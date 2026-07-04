import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { StrategyResult } from "../../api/client";

const STRATEGY_COLORS: Record<string, string> = {
  singles: "var(--color-success)",
  doubles: "var(--color-info)",
  triples: "var(--color-accent-2)",
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
          <span className="text-muted capitalize">{entry.dataKey}</span>
          <span
            className={`font-semibold tabular-nums ${
              entry.value >= 0 ? "text-success" : "text-destructive"
            }`}
          >
            ${entry.value?.toFixed(0)}
          </span>
        </div>
      ))}
    </div>
  );
}

interface PnLChartProps {
  strategies: Record<string, StrategyResult>;
}

export function PnLChart({ strategies }: PnLChartProps) {
  const events = strategies.singles?.events || [];
  const chartData = events.map((ev, i) => {
    const row: Record<string, string | number> = {
      event: ev.event_name?.replace(/UFC\s*/i, "") || `E${i + 1}`,
    };
    for (const key of ["singles", "doubles", "triples"]) {
      const strat = strategies[key];
      if (strat?.events[i]) {
        row[key] = strat.events[i].profit;
      }
    }
    return row;
  });

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        P&L por Evento
      </h3>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart
          data={chartData}
          margin={{ top: 5, right: 10, bottom: 30, left: 0 }}
        >
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
            tickFormatter={(v: number) => `$${v}`}
            tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          {Object.entries(STRATEGY_COLORS).map(([key, color]) =>
            strategies[key] ? (
              <Bar
                key={key}
                dataKey={key}
                name={key.charAt(0).toUpperCase() + key.slice(1)}
                maxBarSize={20}
              >
                {chartData.map((d, idx) => (
                  <Cell
                    key={idx}
                    fill={
                      (d[key] as number) >= 0
                        ? color
                        : "var(--color-destructive)"
                    }
                  />
                ))}
              </Bar>
            ) : null
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
