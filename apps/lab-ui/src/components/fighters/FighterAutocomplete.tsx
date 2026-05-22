import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { api } from "../../api/client";

interface FighterAutocompleteProps {
  value: string;
  onChange: (name: string) => void;
  placeholder?: string;
  className?: string;
  label?: string;
}

export function FighterAutocomplete({
  value,
  onChange,
  placeholder = "Buscar luchador…",
  className = "",
  label,
}: FighterAutocompleteProps) {
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data: allNames = [] } = useQuery({
    queryKey: ["fighters", "names"],
    queryFn: api.fighterNames,
    staleTime: 10 * 60 * 1000,
  });

  // Sync external value changes
  useEffect(() => { setQuery(value); }, [value]);

  const filtered = query.length >= 2
    ? allNames.filter((n) => n.toLowerCase().includes(query.toLowerCase())).slice(0, 12)
    : [];

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleSelect(name: string) {
    setQuery(name);
    onChange(name);
    setOpen(false);
  }

  function handleClear() {
    setQuery("");
    onChange("");
    setOpen(false);
  }

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {label && (
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-1.5">
          {label}
        </p>
      )}
      <div className="flex items-center gap-2 bg-card border border-border rounded-lg px-3 py-2.5 focus-within:border-accent/50 transition-colors">
        <Search size={14} className="text-muted-foreground flex-shrink-0" />
        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => { if (query.length >= 2) setOpen(true); }}
          placeholder={placeholder}
          className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none min-w-0"
        />
        {query && (
          <button
            onClick={handleClear}
            className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {open && filtered.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-2xl overflow-hidden max-h-64 overflow-y-auto">
          {filtered.map((name) => (
            <button
              key={name}
              onMouseDown={() => handleSelect(name)}
              className={[
                "w-full text-left px-4 py-2.5 text-sm transition-colors",
                name === value
                  ? "bg-accent/10 text-accent"
                  : "text-foreground hover:bg-card-hover",
              ].join(" ")}
            >
              {name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
