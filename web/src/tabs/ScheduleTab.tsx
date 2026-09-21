import { api } from "../api";
import { Button, NumberInput, Row, Section, Select, TextInput, Toggle } from "../components/controls";
import { bool, num, str, type TabProps } from "./common";

export function ScheduleTab({ snapshot, expert }: TabProps) {
  const config = snapshot.config;
  const path = ["schedule"];
  const schedule = (config.schedule ?? {}) as Record<string, unknown>;
  const mode = str(config, [...path, "mode"], "solar");
  const status = snapshot.scheduler;

  const push = (patch: Record<string, unknown>) => {
    void api.updateSchedule({ ...schedule, ...patch });
  };

  return (
    <div>
      <Section title="Unattended operation">
        <Row label="Run every night automatically">
          <Toggle
            label="Scheduler enabled"
            checked={bool(config, [...path, "enabled"])}
            onChange={(value) => push({ enabled: value })}
          />
        </Row>
        <Row label="Window">
          <Select
            value={mode}
            options={[
              { value: "solar", label: "Sun based (twilight)" },
              { value: "fixed", label: "Fixed clock times" },
            ]}
            onChange={(value) => push({ mode: value })}
          />
        </Row>
        {mode === "solar" ? (
          <>
            <Row label="Latitude and longitude">
              <div className="flex gap-2">
                <NumberInput
                  value={num(config, [...path, "latitude"])}
                  min={-90}
                  max={90}
                  step={0.0001}
                  onChange={(value) => push({ latitude: value })}
                />
                <NumberInput
                  value={num(config, [...path, "longitude"])}
                  min={-180}
                  max={180}
                  step={0.0001}
                  onChange={(value) => push({ longitude: value })}
                />
              </div>
            </Row>
            <Row label="Twilight" hint="Degrees below the horizon when capture starts">
              <Select
                value={String(num(config, [...path, "sun_depression_deg"], 12))}
                options={[
                  { value: "6", label: "Civil (6 degrees)" },
                  { value: "12", label: "Nautical (12 degrees)" },
                  { value: "18", label: "Astronomical (18 degrees)" },
                ]}
                onChange={(value) => push({ sun_depression_deg: Number(value) })}
              />
            </Row>
            {expert && (
              <Row label="Start and end offsets (minutes)" expert>
                <div className="flex gap-2">
                  <NumberInput
                    value={num(config, [...path, "start_offset_min"])}
                    onChange={(value) => push({ start_offset_min: Math.round(value) })}
                  />
                  <NumberInput
                    value={num(config, [...path, "end_offset_min"])}
                    onChange={(value) => push({ end_offset_min: Math.round(value) })}
                  />
                </div>
              </Row>
            )}
          </>
        ) : (
          <Row label="Start and end times">
            <div className="flex gap-2">
              <TextInput
                value={str(config, [...path, "fixed_start"], "21:00")}
                onChange={(value) => push({ fixed_start: value })}
              />
              <TextInput
                value={str(config, [...path, "fixed_end"], "05:00")}
                onChange={(value) => push({ fixed_end: value })}
              />
            </div>
          </Row>
        )}
        <Row label="Time zone" hint="Leave empty to use the system time zone">
          <TextInput
            value={str(config, [...path, "timezone"])}
            onChange={(value) => push({ timezone: value.length ? value : null })}
          />
        </Row>
        <Row label="Compile the video at dawn">
          <Toggle
            label="Compile at end"
            checked={bool(config, [...path, "compile_at_end"], true)}
            onChange={(value) => push({ compile_at_end: value })}
          />
        </Row>
        {expert && (
          <Row label="Session name template" expert hint="Token: {night}">
            <TextInput
              value={str(config, [...path, "session_name_template"], "night_{night}")}
              onChange={(value) => push({ session_name_template: value })}
            />
          </Row>
        )}
      </Section>

      <Section title="Status">
        {status.error && <p className="text-xs text-rose-300">{status.error}</p>}
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-400">
          <dt>Scheduler</dt>
          <dd className="text-slate-200">{status.enabled ? "enabled" : "disabled"}</dd>
          <dt>In window</dt>
          <dd className="text-slate-200">{status.in_window ? "yes" : "no"}</dd>
          <dt>Night</dt>
          <dd className="text-slate-200">{status.night ?? "-"}</dd>
          <dt>Next start</dt>
          <dd className="text-slate-200">
            {status.next_start ? new Date(status.next_start).toLocaleString() : "-"}
          </dd>
          <dt>Window end</dt>
          <dd className="text-slate-200">
            {status.next_end ? new Date(status.next_end).toLocaleString() : "-"}
          </dd>
        </dl>
        <div className="mt-2">
          <Button onClick={() => push({})}>Refresh</Button>
        </div>
      </Section>
    </div>
  );
}
