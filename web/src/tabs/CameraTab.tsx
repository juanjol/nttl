import { api } from "../api";
import { NumberInput, Row, Section, Select, Slider, TextInput, Toggle } from "../components/controls";
import { bool, num, str, type TabProps } from "./common";

const HIDDEN_CONTROLS = new Set(["exposure", "cooler_on", "target_temp"]);

export function CameraTab({ snapshot, expert, update }: TabProps) {
  const config = snapshot.config;
  const camera = snapshot.camera;
  const info = camera.info;
  const controls = camera.controls ?? {};
  const values = camera.values ?? {};

  return (
    <div>
      <Section title="Connection">
        <Row label="Backend">
          <Select
            value={str(config, ["capture", "camera", "backend"], "simulated")}
            options={[
              { value: "asi", label: "ZWO ASI" },
              { value: "simulated", label: "Simulated" },
            ]}
            onChange={(value) => update(["capture", "camera", "backend"], value)}
          />
        </Row>
        <Row label="Camera id" hint="Leave empty to use the first camera found">
          <TextInput
            value={str(config, ["capture", "camera", "camera_id"])}
            onChange={(value) =>
              update(["capture", "camera", "camera_id"], value.length ? value : null)
            }
          />
        </Row>
        {info && (
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-400">
            <dt>Sensor</dt>
            <dd className="text-slate-200">
              {info.max_width} x {info.max_height} at {info.pixel_size_um} um
            </dd>
            <dt>Depth</dt>
            <dd className="text-slate-200">{info.bit_depth} bit</dd>
            <dt>Colour</dt>
            <dd className="text-slate-200">{info.is_color ? info.bayer_pattern : "mono"}</dd>
            <dt>Cooler</dt>
            <dd className="text-slate-200">{info.has_cooler ? "yes" : "no"}</dd>
          </dl>
        )}
      </Section>

      <Section title="Frame">
        <Row label="Binning">
          <Select
            value={String(num(config, ["capture", "camera", "bin"], 1))}
            options={(info?.supported_bins ?? [1, 2, 4]).map((value) => ({
              value: String(value),
              label: `${value} x ${value}`,
            }))}
            onChange={(value) => update(["capture", "camera", "bin"], Number(value))}
          />
        </Row>
        <Row label="Offset">
          <NumberInput
            value={num(config, ["capture", "camera", "offset"], 50)}
            min={0}
            onChange={(value) => update(["capture", "camera", "offset"], value)}
          />
        </Row>
        {expert && (
          <Row label="Region of interest" expert hint="x, y, width, height in sensor pixels">
            <div className="grid grid-cols-4 gap-2">
              {["x", "y", "width", "height"].map((label, index) => (
                <NumberInput
                  key={label}
                  value={
                    (snapshot.config.capture as never as { camera: { roi: number[] | null } })
                      ?.camera?.roi?.[index] ?? 0
                  }
                  min={0}
                  onChange={(value) => {
                    const current =
                      (snapshot.config.capture as never as { camera: { roi: number[] | null } })
                        ?.camera?.roi ?? [0, 0, info?.max_width ?? 0, info?.max_height ?? 0];
                    const next = [...current];
                    next[index] = Math.round(value);
                    update(["capture", "camera", "roi"], next);
                  }}
                />
              ))}
            </div>
          </Row>
        )}
      </Section>

      {info?.has_cooler && (
        <Section title="Cooling">
          <Row label="Cooler">
            <Toggle
              label="Cooler"
              checked={bool(config, ["capture", "camera", "cooler_enabled"])}
              onChange={(value) => {
                update(["capture", "camera", "cooler_enabled"], value);
                void api.setCooler(value, num(config, ["capture", "camera", "target_temp_c"], 0));
              }}
            />
          </Row>
          <Row label="Target temperature (C)">
            <NumberInput
              value={num(config, ["capture", "camera", "target_temp_c"], 0)}
              min={-50}
              max={40}
              onChange={(value) => {
                update(["capture", "camera", "target_temp_c"], value);
                void api.setCooler(
                  bool(config, ["capture", "camera", "cooler_enabled"]),
                  value,
                );
              }}
            />
          </Row>
        </Section>
      )}

      <Section title="Live camera controls">
        {Object.entries(controls)
          .filter(([name, control]) => control.writable && !HIDDEN_CONTROLS.has(name))
          .map(([name, control]) => (
            <Row key={name} label={`${name}${control.unit ? ` (${control.unit})` : ""}`}>
              <Slider
                value={values[name] ?? control.default}
                min={control.min}
                max={control.max}
                onChange={(value) => void api.setControl(name, value)}
              />
            </Row>
          ))}
        {!camera.connected && (
          <p className="text-sm text-rose-300">{camera.error ?? "camera not connected"}</p>
        )}
      </Section>
    </div>
  );
}
