import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Button, Section, Select } from "../components/controls";
import type { LogEntry } from "../types";

const LEVELS = [
  { value: "DEBUG", label: "Everything" },
  { value: "INFO", label: "Information" },
  { value: "WARNING", label: "Warnings" },
  { value: "ERROR", label: "Errors only" },
];

const ORDER: Record<string, number> = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 };

const COLOURS: Record<string, string> = {
  DEBUG: "text-slate-500",
  INFO: "text-slate-300",
  WARNING: "text-amber-300",
  ERROR: "text-rose-300",
  CRITICAL: "text-rose-300",
};

export function LogsTab() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [level, setLevel] = useState("INFO");
  const [follow, setFollow] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);
  const lastId = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      api
        .logs(lastId.current)
        .then((body) => {
          if (cancelled || body.entries.length === 0) return;
          lastId.current = body.entries[body.entries.length - 1].id;
          setEntries((current) => [...current, ...body.entries].slice(-800));
          setError(null);
        })
        .catch((exc: Error) => !cancelled && setError(exc.message));
    };
    poll();
    const timer = window.setInterval(poll, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (follow) bottom.current?.scrollIntoView({ block: "end" });
  }, [entries, follow]);

  const visible = entries.filter(
    (entry) => (ORDER[entry.level] ?? 20) >= (ORDER[level] ?? 20),
  );

  return (
    <div>
      <Section title="Live log">
        <div className="flex items-end gap-2 pb-2">
          <div className="flex-1">
            <Select value={level} options={LEVELS} onChange={setLevel} />
          </div>
          <Button variant={follow ? "primary" : "default"} onClick={() => setFollow(!follow)}>
            {follow ? "Following" : "Paused"}
          </Button>
          <Button
            onClick={() =>
              void api
                .clearLogs()
                .then(() => setEntries([]))
                .catch((exc: Error) => setError(exc.message))
            }
          >
            Clear
          </Button>
        </div>
        {error && <p className="pb-2 text-xs text-rose-300">{error}</p>}
        <div className="h-[420px] overflow-y-auto rounded-md border border-edge bg-black/40 p-2 font-mono text-[11px] leading-relaxed">
          {visible.length === 0 && <p className="text-slate-500">Nothing logged yet.</p>}
          {visible.map((entry) => (
            <div key={entry.id} className="flex gap-2 whitespace-pre-wrap break-words">
              <span className="shrink-0 text-slate-600">{entry.time.slice(11, 19)}</span>
              <span className={`shrink-0 ${COLOURS[entry.level] ?? "text-slate-400"}`}>
                {entry.level}
              </span>
              <span className="text-slate-300">{entry.message}</span>
            </div>
          ))}
          <div ref={bottom} />
        </div>
      </Section>
    </div>
  );
}
