import { useRef, useState } from "react";
import { Plus, Trash2, Download, FileUp, Loader2 } from "lucide-react";
import type { CommunityPicks, FightInput } from "../../api/client";
import { FighterAutocomplete } from "../fighters/FighterAutocomplete";
import { Button, Input } from "../ui";
import { useTapologyScrape } from "./usePredictions";

interface Row {
  fighter_1: string;
  fighter_2: string;
  odds1: string;
  odds2: string;
  community?: CommunityPicks | null;
}

const EMPTY: Row = { fighter_1: "", fighter_2: "", odds1: "", odds2: "" };
const MAX_FIGHTS = 20;

function parseTxt(text: string): { event: string; rows: Row[] } {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return { event: "", rows: [] };
  const event = lines[0];
  const rows: Row[] = [];
  const re = /^(.+?)\s+\(([+-]?\d+)\)\s+vs\s+(.+?)\s+\(([+-]?\d+)\)\s*$/i;
  const simple = /^(.+?)\s+vs\s+(.+?)\s*$/i;
  for (const line of lines.slice(1)) {
    const m = line.match(re);
    if (m) {
      rows.push({ fighter_1: m[1].trim(), fighter_2: m[3].trim(), odds1: m[2], odds2: m[4] });
    } else {
      const s = line.match(simple);
      if (s) rows.push({ ...EMPTY, fighter_1: s[1].trim(), fighter_2: s[2].trim() });
    }
  }
  return { event, rows };
}

interface FightInputFormProps {
  onPredict: (event: string, fights: FightInput[]) => void;
  isPending: boolean;
}

export function FightInputForm({ onPredict, isPending }: FightInputFormProps) {
  const [event, setEvent] = useState("");
  const [rows, setRows] = useState<Row[]>([{ ...EMPTY }]);
  const [showOdds, setShowOdds] = useState(false);
  const [tapUrl, setTapUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const tapology = useTapologyScrape();

  function setRow(i: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((rs) => (rs.length < MAX_FIGHTS ? [...rs, { ...EMPTY }] : rs));
  }
  function removeRow(i: number) {
    setRows((rs) => (rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs));
  }

  function validate(): FightInput[] | null {
    if (!event.trim()) { setError("Indica el nombre del evento"); return null; }
    const fights: FightInput[] = [];
    for (const r of rows) {
      if (!r.fighter_1.trim() && !r.fighter_2.trim()) continue;
      if (!r.fighter_1.trim() || !r.fighter_2.trim()) {
        setError("Cada pelea necesita ambos luchadores"); return null;
      }
      if (r.fighter_1.trim() === r.fighter_2.trim()) {
        setError("Los luchadores de una pelea deben ser distintos"); return null;
      }
      fights.push({
        fighter_1: r.fighter_1.trim(),
        fighter_2: r.fighter_2.trim(),
        odds_f1_american: r.odds1 ? Number(r.odds1) : null,
        odds_f2_american: r.odds2 ? Number(r.odds2) : null,
        community_picks: r.community ?? null,
      });
    }
    if (fights.length === 0) { setError("Añade al menos una pelea"); return null; }
    setError(null);
    return fights;
  }

  function submit() {
    const fights = validate();
    if (fights) onPredict(event.trim(), fights);
  }

  async function loadTapology() {
    setError(null);
    try {
      const res = await tapology.mutateAsync(tapUrl);
      if (res.event_name) setEvent(res.event_name);
      const next: Row[] = res.fights.map((f) => ({
        fighter_1: f.fighter_1,
        fighter_2: f.fighter_2,
        odds1: f.odds_f1_american != null ? String(f.odds_f1_american) : "",
        odds2: f.odds_f2_american != null ? String(f.odds_f2_american) : "",
        community: f.community_picks,
      }));
      setRows(next.length ? next : [{ ...EMPTY }]);
      if (res.fights.some((f) => f.odds_f1_american != null)) setShowOdds(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const { event: ev, rows: parsed } = parseTxt(String(reader.result));
      if (ev) setEvent(ev);
      if (parsed.length) setRows(parsed);
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  const nFights = rows.filter((r) => r.fighter_1.trim() && r.fighter_2.trim()).length;

  return (
    <div className="space-y-4">
      {/* Loaders: Tapology + TXT */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Cargar evento</p>
        <div className="flex gap-2">
          <Input
            placeholder="https://www.tapology.com/fightcenter/events/…"
            value={tapUrl}
            onChange={(e) => setTapUrl(e.target.value)}
          />
          <Button variant="secondary" onClick={loadTapology} disabled={!tapUrl || tapology.isPending}>
            {tapology.isPending ? <Loader2 className="animate-spin" size={15} /> : <Download size={15} />}
            <span className="ml-1.5">Tapology</span>
          </Button>
          <Button variant="secondary" onClick={() => fileRef.current?.click()}>
            <FileUp size={15} /><span className="ml-1.5">TXT</span>
          </Button>
          <input ref={fileRef} type="file" accept=".txt" hidden onChange={onFile} />
        </div>
      </div>

      {/* Manual entry */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Evento</p>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
            <input type="checkbox" checked={showOdds} onChange={(e) => setShowOdds(e.target.checked)} />
            Cuotas
          </label>
        </div>
        <Input placeholder="Nombre del evento (p.ej. UFC 300)" value={event} onChange={(e) => setEvent(e.target.value)} />

        <div className="space-y-2">
          {rows.map((r, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="flex-1 grid grid-cols-2 gap-2">
                <FighterAutocomplete value={r.fighter_1} onChange={(v) => setRow(i, { fighter_1: v })} placeholder="Luchador 1…" />
                <FighterAutocomplete value={r.fighter_2} onChange={(v) => setRow(i, { fighter_2: v })} placeholder="Luchador 2…" />
                {showOdds && (
                  <>
                    <Input placeholder="Cuota US (+150)" value={r.odds1} onChange={(e) => setRow(i, { odds1: e.target.value })} />
                    <Input placeholder="Cuota US (-180)" value={r.odds2} onChange={(e) => setRow(i, { odds2: e.target.value })} />
                  </>
                )}
              </div>
              <button
                onClick={() => removeRow(i)}
                className="mt-2 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-30"
                disabled={rows.length === 1}
                title="Eliminar pelea"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>

        {rows.length < MAX_FIGHTS && (
          <button onClick={addRow} className="flex items-center gap-1.5 text-xs text-accent hover:text-accent-hi transition-colors">
            <Plus size={14} /> Añadir pelea
          </button>
        )}
      </div>

      {error && (
        <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">{error}</div>
      )}

      <Button onClick={submit} disabled={isPending || nFights === 0}>
        {isPending ? <Loader2 className="animate-spin inline" size={15} /> : null}
        <span className={isPending ? "ml-1.5" : ""}>Predecir {nFights} pelea{nFights === 1 ? "" : "s"}</span>
      </Button>
    </div>
  );
}
