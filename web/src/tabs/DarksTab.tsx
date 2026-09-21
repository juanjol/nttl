import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, NumberInput, Row, Section } from "../components/controls";
import type { DarkEntryView } from "../types";
import { num, type TabProps } from "./common";

export function DarksTab({ snapshot, expert, update }: TabProps) {
  const config = snapshot.config;
  const [darks, setDarks] = useState<DarkEntryView[]>([]);
  const [frames, setFrames] = useState(16);
  const [error, setError] = useState<string | null>(null);
  const jobs = snapshot.jobs.filter((job) => job.name.startsWith("darks:"));

  const reload = () => {
    api
      .darks()
      .then((body) => setDarks(body.darks))
      .catch((exc: Error) => setError(exc.message));
  };

  useEffect(reload, [snapshot.jobs.length, jobs[0]?.state]);

  return (
    <div>
      <Section title="Build a master dark">
        <p className="mb-2 text-xs text-slate-500">
          Cover the telescope or sensor. The camera takes the frames with the current exposure and
          gain and stores the median as a master dark.
        </p>
        <Row label="Frames to stack">
          <NumberInput value={frames} min={1} max={200} onChange={(value) => setFrames(value)} />
        </Row>
        <Button
          variant="primary"
          onClick={() =>
            void api
              .buildDarks(
                num(config, ["capture", "camera", "exposure_s"], 1),
                num(config, ["capture", "camera", "gain"], 120),
                Math.round(frames),
              )
              .then(reload)
              .catch((exc: Error) => setError(exc.message))
          }
        >
          Capture darks
        </Button>
        {jobs.slice(0, 1).map((job) => (
          <p key={job.id} className="mt-2 text-xs text-slate-400">
            {job.name}: {job.state} {job.frames_total ? `${job.frames_done}/${job.frames_total}` : ""}
          </p>
        ))}
        {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
      </Section>

      {expert && (
        <Section title="Matching tolerances">
          <Row label="Exposure tolerance" expert hint="Relative, 0.05 means 5 percent">
            <NumberInput
              value={num(config, ["darks", "exposure_rel_tol"], 0.05)}
              min={0}
              max={1}
              step={0.01}
              onChange={(value) => update(["darks", "exposure_rel_tol"], value)}
            />
          </Row>
          <Row label="Gain tolerance" expert>
            <NumberInput
              value={num(config, ["darks", "gain_tol"], 1)}
              min={0}
              onChange={(value) => update(["darks", "gain_tol"], value)}
            />
          </Row>
          <Row label="Temperature tolerance (C)" expert>
            <NumberInput
              value={num(config, ["darks", "temp_tol_c"], 3)}
              min={0}
              step={0.5}
              onChange={(value) => update(["darks", "temp_tol_c"], value)}
            />
          </Row>
        </Section>
      )}

      <Section title="Library">
        {darks.length === 0 && <p className="text-sm text-slate-500">No master darks yet.</p>}
        <ul className="flex flex-col gap-2">
          {darks.map((dark) => (
            <li
              key={dark.name}
              className="flex items-center justify-between rounded-md border border-edge bg-panel-soft/60 px-2 py-1.5 text-xs"
            >
              <div>
                <div className="text-slate-200">
                  {dark.exposure_s}s gain {dark.gain} bin {dark.bin}
                </div>
                <div className="text-slate-500">
                  {dark.sensor_temp_c.toFixed(1)}C, {dark.frames} frames, {dark.width}x{dark.height}
                </div>
              </div>
              <Button
                variant="danger"
                onClick={() => void api.deleteDark(dark.name).then(reload)}
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
