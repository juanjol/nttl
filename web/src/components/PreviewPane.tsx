import { useEffect, useState } from "react";
import type { Snapshot } from "../types";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
      <span className="text-sm tabular-nums text-slate-100">{value}</span>
    </div>
  );
}

export function PreviewPane({ snapshot }: { snapshot: Snapshot }) {
  const [cacheBuster, setCacheBuster] = useState(0);
  const session = snapshot.session;
  const stats = snapshot.stats;
  const running = session.state === "running";
  const idle = !snapshot.live_view && !running;

  useEffect(() => {
    if (idle) return;
    const timer = window.setInterval(() => setCacheBuster((value) => value + 1), 2000);
    return () => window.clearInterval(timer);
  }, [idle]);

  const level = stats?.level ?? session.level ?? 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-lg border border-edge bg-black">
        <img
          alt="Live camera preview"
          className="max-h-full max-w-full object-contain"
          src={`/api/preview.jpg?t=${cacheBuster}`}
          onError={(event) => {
            (event.target as HTMLImageElement).style.opacity = "0.15";
          }}
        />
        {idle && (
          <p className="absolute inset-x-0 bottom-6 text-center text-sm text-slate-400">
            The camera is off. Press "Live preview" to see what it sees, or "Start recording" to
            capture a timelapse.
          </p>
        )}
        {snapshot.live_view && !running && (
          <span className="absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/60 px-2.5 py-1 text-xs text-sky-300">
            <span className="h-2 w-2 rounded-full bg-sky-400" />
            live preview
          </span>
        )}
        {running && (
          <span className="absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/60 px-2.5 py-1 text-xs text-emerald-300">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
            recording
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-4 rounded-lg border border-edge bg-panel px-4 py-3 sm:grid-cols-6">
        <Stat label="Frames" value={String(session.frames_captured)} />
        <Stat label="Exposure" value={`${session.exposure_s.toFixed(3)} s`} />
        <Stat label="Gain" value={session.gain.toFixed(0)} />
        <Stat
          label="Sensor"
          value={session.sensor_temp_c === null ? "-" : `${session.sensor_temp_c.toFixed(1)} C`}
        />
        <Stat label="Level" value={level.toFixed(3)} />
        <Stat
          label="Clipped"
          value={stats ? `${(stats.saturated_fraction * 100).toFixed(2)} %` : "-"}
        />
      </div>
      {session.last_error && (
        <p className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {session.last_error}
        </p>
      )}
    </div>
  );
}
