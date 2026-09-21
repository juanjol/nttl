import { useCallback, useMemo, useState } from "react";
import type { ReactElement } from "react";
import { api, patchFor } from "./api";
import { PreviewPane } from "./components/PreviewPane";
import { Toggle } from "./components/controls";
import { useSnapshot } from "./hooks/useSnapshot";
import { CameraTab } from "./tabs/CameraTab";
import { CaptureTab } from "./tabs/CaptureTab";
import { DarksTab } from "./tabs/DarksTab";
import { OutputTab } from "./tabs/OutputTab";
import { OverlayTab } from "./tabs/OverlayTab";
import { ScheduleTab } from "./tabs/ScheduleTab";
import { VideoTab } from "./tabs/VideoTab";
import type { TabProps } from "./tabs/common";

const TABS: { id: string; label: string; render: (props: TabProps) => ReactElement }[] = [
  { id: "capture", label: "Capture", render: (props) => <CaptureTab {...props} /> },
  { id: "camera", label: "Camera", render: (props) => <CameraTab {...props} /> },
  { id: "output", label: "Output", render: (props) => <OutputTab {...props} /> },
  { id: "overlay", label: "Overlay", render: (props) => <OverlayTab {...props} /> },
  { id: "darks", label: "Darks", render: (props) => <DarksTab {...props} /> },
  { id: "video", label: "Video", render: (props) => <VideoTab {...props} /> },
  { id: "schedule", label: "Schedule", render: (props) => <ScheduleTab {...props} /> },
];

export default function App() {
  const { snapshot, error } = useSnapshot();
  const [tab, setTab] = useState("capture");
  const [expert, setExpert] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const update = useCallback((path: string[], value: unknown) => {
    setBusy(true);
    api
      .patchConfig(patchFor(path, value))
      .then(() => setMessage(null))
      .catch((exc: Error) => setMessage(exc.message))
      .finally(() => setBusy(false));
  }, []);

  const active = useMemo(() => TABS.find((entry) => entry.id === tab) ?? TABS[0], [tab]);

  if (!snapshot) {
    return (
      <main className="flex h-full items-center justify-center text-slate-400">
        {error ? `Cannot reach the server: ${error}` : "Connecting to the camera server..."}
      </main>
    );
  }

  const session = snapshot.session;
  const running = session.state === "running";

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-edge bg-panel px-4 py-3">
        <h1 className="text-lg font-semibold tracking-tight">NTTL</h1>
        <span className="text-sm text-slate-400">
          {snapshot.camera.info?.name ?? "no camera"}
        </span>
        <span
          className={`h-2 w-2 rounded-full ${
            snapshot.camera.connected ? "bg-emerald-400" : "bg-rose-500"
          }`}
        />
        <span className="rounded-full border border-edge px-2 py-0.5 text-xs text-slate-300">
          {session.session_name}: {session.state}
        </span>
        {snapshot.scheduler.enabled && (
          <span className="rounded-full border border-edge px-2 py-0.5 text-xs text-sky-300">
            scheduler {snapshot.scheduler.in_window ? "in window" : "waiting"}
          </span>
        )}
        <div className="ml-auto flex items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-slate-400">
            Expert mode
            <Toggle label="Expert mode" checked={expert} onChange={setExpert} />
          </label>
          <button
            type="button"
            onClick={() => void (running ? api.stopSession() : api.startSession())}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              running ? "bg-rose-500/80 text-white" : "bg-accent text-slate-900"
            }`}
          >
            {running ? "Stop capture" : "Start capture"}
          </button>
        </div>
      </header>

      {message && (
        <p className="border-b border-rose-500/40 bg-rose-500/10 px-4 py-2 text-xs text-rose-200">
          {message}
        </p>
      )}

      <main className="flex min-h-0 flex-1 flex-col gap-4 p-4 lg:flex-row">
        <PreviewPane snapshot={snapshot} />
        <aside className="flex w-full min-h-0 flex-col rounded-lg border border-edge bg-panel lg:w-[420px]">
          <nav className="flex flex-wrap gap-1 border-b border-edge p-2">
            {TABS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                onClick={() => setTab(entry.id)}
                className={`rounded-md px-2.5 py-1.5 text-xs transition ${
                  entry.id === active.id
                    ? "bg-accent/20 text-accent"
                    : "text-slate-400 hover:text-slate-100"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </nav>
          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-1">
            {active.render({ snapshot, expert, update, busy })}
          </div>
        </aside>
      </main>
    </div>
  );
}
