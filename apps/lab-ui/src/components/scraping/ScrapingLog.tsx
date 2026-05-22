import { useEffect, useRef } from "react";

interface ScrapingLogProps {
  lines: string[];
}

function lineClass(line: string): string {
  if (line.startsWith("[ERROR]")) return "text-destructive";
  if (line.startsWith("[OK]") || line.startsWith("[SUCCESS]")) return "text-success";
  if (line.startsWith("[WARN]")) return "text-warning";
  return "text-muted-foreground";
}

export function ScrapingLog({ lines }: ScrapingLogProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div className="rounded-lg border border-border overflow-hidden flex flex-col flex-1 min-h-0">
      <div className="px-4 py-2.5 border-b border-border bg-card flex items-center gap-2">
        <div className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-destructive/60" />
          <span className="w-2.5 h-2.5 rounded-full bg-warning/60" />
          <span className="w-2.5 h-2.5 rounded-full bg-success/60" />
        </div>
        <span className="text-muted-foreground text-xs font-mono ml-1">log output</span>
      </div>
      <div
        ref={containerRef}
        className="flex-1 min-h-64 max-h-[70vh] overflow-y-auto bg-[#020208] p-4 space-y-0.5 font-mono text-xs"
      >
        {lines.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <span className="text-muted-foreground">Sin logs disponibles</span>
          </div>
        ) : (
          lines.map((line, idx) => (
            <div key={idx} className={`whitespace-pre-wrap break-words ${lineClass(line)}`}>
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
