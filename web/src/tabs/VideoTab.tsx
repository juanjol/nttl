import { NumberInput, Row, Section, Select } from "../components/controls";
import { num, str, type TabProps } from "./common";

export function VideoTab({ snapshot, expert, update }: TabProps) {
  const config = snapshot.config;

  return (
    <div>
      <Section title="Video profile">
        <Row label="Codec">
          <Select
            value={str(config, ["video", "codec"], "h264")}
            options={[
              { value: "h264", label: "H.264" },
              { value: "h265", label: "H.265" },
              { value: "vp9", label: "VP9" },
              { value: "prores", label: "ProRes (editing)" },
            ]}
            onChange={(value) => update(["video", "codec"], value)}
          />
        </Row>
        <Row label="Frames per second">
          <NumberInput
            value={num(config, ["video", "fps"], 24)}
            min={1}
            max={240}
            onChange={(value) => update(["video", "fps"], Math.round(value))}
          />
        </Row>
        <Row label="Quality (CRF)" hint="Lower is better quality and larger files">
          <NumberInput
            value={num(config, ["video", "crf"], 18)}
            min={0}
            max={63}
            onChange={(value) => update(["video", "crf"], Math.round(value))}
          />
        </Row>
        {expert && (
          <>
            <Row label="Encoder preset" expert>
              <Select
                value={str(config, ["video", "preset"], "medium")}
                options={["ultrafast", "fast", "medium", "slow", "veryslow"].map((value) => ({
                  value,
                  label: value,
                }))}
                onChange={(value) => update(["video", "preset"], value)}
              />
            </Row>
            <Row label="Maximum width" expert hint="0 keeps the native size">
              <NumberInput
                value={num(config, ["video", "max_width"], 0)}
                min={0}
                onChange={(value) =>
                  update(["video", "max_width"], value >= 16 ? Math.round(value) : null)
                }
              />
            </Row>
            <Row label="Source frames" expert>
              <Select
                value={str(config, ["video", "prefer_format"], "jpeg")}
                options={[
                  { value: "jpeg", label: "JPEG" },
                  { value: "png", label: "PNG" },
                  { value: "tiff", label: "TIFF" },
                ]}
                onChange={(value) => update(["video", "prefer_format"], value)}
              />
            </Row>
          </>
        )}
        {!snapshot.ffmpeg.available && (
          <p className="text-xs text-amber-300">
            ffmpeg was not found. Install it and make sure it is on PATH to compile videos.
          </p>
        )}
      </Section>

      <Section title="Jobs">
        {snapshot.jobs.length === 0 && <p className="text-sm text-slate-500">No jobs yet.</p>}
        <ul className="flex flex-col gap-1 text-xs">
          {snapshot.jobs.map((job) => (
            <li key={job.id} className="flex items-center justify-between gap-2">
              <span className="text-slate-300">{job.name}</span>
              <span className="text-slate-500">
                {job.state}
                {job.frames_total > 0 && ` ${Math.round(job.progress * 100)}%`}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
