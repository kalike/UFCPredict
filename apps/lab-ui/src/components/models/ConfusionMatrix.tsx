// Confusion matrix as stored by the lab: sklearn order with labels=[1, 0],
// i.e. rows = real F1/F2, cols = pred F1/F2:
//   [[TP, FN],
//    [FP, TN]]
// Diagonal (TP, TN) = correct (green); off-diagonal (FN, FP) = wrong (red).

const OSWALD = { fontFamily: "'Oswald', sans-serif" } as const;

function Cell({ value, label, ok }: { value: number; label: string; ok: boolean }) {
  return (
    <div
      className={[
        "rounded-lg p-3 text-center border",
        ok ? "bg-success/10 border-success/20" : "bg-destructive/5 border-destructive/20",
      ].join(" ")}
    >
      <div
        className={["text-xl font-bold leading-none", ok ? "text-success" : "text-destructive"].join(" ")}
        style={OSWALD}
      >
        {value}
      </div>
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">{label}</div>
    </div>
  );
}

export function ConfusionMatrix({ matrix }: { matrix: number[][] }) {
  const tp = matrix[0]?.[0] ?? 0;
  const fn = matrix[0]?.[1] ?? 0;
  const fp = matrix[1]?.[0] ?? 0;
  const tn = matrix[1]?.[1] ?? 0;

  return (
    <div>
      {/* Column headers */}
      <div className="flex mb-1 pl-10">
        <div className="flex-1 text-center text-[10px] text-muted-foreground uppercase tracking-wider">Pred. F1</div>
        <div className="flex-1 text-center text-[10px] text-muted-foreground uppercase tracking-wider">Pred. F2</div>
      </div>

      <div className="flex gap-1">
        {/* Row labels */}
        <div className="flex flex-col justify-around w-9 shrink-0">
          {["Real F1", "Real F2"].map((l) => (
            <div
              key={l}
              className="text-[10px] text-muted-foreground uppercase tracking-wider text-center"
              style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", height: "48px" }}
            >
              {l}
            </div>
          ))}
        </div>

        {/* 2x2 grid */}
        <div className="grid grid-cols-2 gap-2 flex-1 max-w-[200px]">
          <Cell value={tp} label="TP" ok />
          <Cell value={fn} label="FN" ok={false} />
          <Cell value={fp} label="FP" ok={false} />
          <Cell value={tn} label="TN" ok />
        </div>
      </div>
    </div>
  );
}
