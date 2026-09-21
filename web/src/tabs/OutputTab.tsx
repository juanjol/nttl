import { NumberInput, Row, Section, Select, TextInput } from "../components/controls";
import { list, num, str, type TabProps } from "./common";

const FORMATS = [
  { value: "fits", label: "FITS 16 bit (raw data)" },
  { value: "png", label: "PNG 16 bit" },
  { value: "tiff", label: "TIFF 16 bit" },
  { value: "jpeg", label: "JPEG 8 bit" },
];

export function OutputTab({ snapshot, expert, update }: TabProps) {
  const config = snapshot.config;
  const formats = list<string>(config, ["capture", "output", "formats"]);
  const mode = str(config, ["capture", "output", "stretch", "mode"], "auto");

  return (
    <div>
      <Section title="Files">
        <Row label="Output directory">
          <TextInput
            value={str(config, ["capture", "output", "directory"], "sessions")}
            onChange={(value) => update(["capture", "output", "directory"], value)}
          />
        </Row>
        <Row label="Formats" hint="FITS keeps the linear data for reprocessing">
          <div className="flex flex-col gap-1">
            {FORMATS.map((format) => (
              <label key={format.value} className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={formats.includes(format.value)}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...formats, format.value]
                      : formats.filter((item) => item !== format.value);
                    update(["capture", "output", "formats"], next);
                  }}
                />
                {format.label}
              </label>
            ))}
          </div>
        </Row>
        {expert && (
          <Row label="File name template" expert hint="Tokens: {session} and {seq}">
            <TextInput
              value={str(config, ["capture", "output", "filename_template"], "{session}_{seq:05d}")}
              onChange={(value) => update(["capture", "output", "filename_template"], value)}
            />
          </Row>
        )}
        <Row label="JPEG quality">
          <NumberInput
            value={num(config, ["capture", "output", "jpeg_quality"], 92)}
            min={1}
            max={100}
            onChange={(value) => update(["capture", "output", "jpeg_quality"], value)}
          />
        </Row>
      </Section>

      <Section title="Debayer">
        <Row label="Pattern" hint="Automatic uses the pattern reported by the sensor">
          <Select
            value={str(config, ["capture", "output", "debayer"], "auto")}
            options={[
              { value: "auto", label: "Automatic" },
              { value: "none", label: "Do not debayer" },
              { value: "RGGB", label: "RGGB" },
              { value: "BGGR", label: "BGGR" },
              { value: "GRBG", label: "GRBG" },
              { value: "GBRG", label: "GBRG" },
            ]}
            onChange={(value) => update(["capture", "output", "debayer"], value)}
          />
        </Row>
      </Section>

      <Section title="Rendering">
        <Row label="Stretch">
          <Select
            value={mode}
            options={[
              { value: "auto", label: "Automatic (screen transfer)" },
              { value: "linear", label: "Linear percentile" },
              { value: "none", label: "None" },
            ]}
            onChange={(value) => update(["capture", "output", "stretch", "mode"], value)}
          />
        </Row>
        {mode === "auto" && (
          <Row label="Target background" hint="Higher lifts the sky, lower keeps it dark">
            <NumberInput
              value={num(config, ["capture", "output", "stretch", "target_background"], 0.25)}
              min={0.01}
              max={0.9}
              step={0.01}
              onChange={(value) =>
                update(["capture", "output", "stretch", "target_background"], value)
              }
            />
          </Row>
        )}
        {expert && mode === "auto" && (
          <Row label="Shadow clipping" expert hint="In noise sigmas below the median">
            <NumberInput
              value={num(config, ["capture", "output", "stretch", "shadow_clip"], -2.8)}
              max={0}
              step={0.1}
              onChange={(value) => update(["capture", "output", "stretch", "shadow_clip"], value)}
            />
          </Row>
        )}
        {expert && mode === "linear" && (
          <Row label="Percentiles" expert>
            <div className="flex gap-2">
              <NumberInput
                value={num(config, ["capture", "output", "stretch", "low_percentile"], 0.5)}
                min={0}
                max={49}
                step={0.1}
                onChange={(value) =>
                  update(["capture", "output", "stretch", "low_percentile"], value)
                }
              />
              <NumberInput
                value={num(config, ["capture", "output", "stretch", "high_percentile"], 99.8)}
                min={51}
                max={100}
                step={0.1}
                onChange={(value) =>
                  update(["capture", "output", "stretch", "high_percentile"], value)
                }
              />
            </div>
          </Row>
        )}
        <Row label="Gamma">
          <NumberInput
            value={num(config, ["capture", "output", "stretch", "gamma"], 1)}
            min={0.1}
            max={5}
            step={0.05}
            onChange={(value) => update(["capture", "output", "stretch", "gamma"], value)}
          />
        </Row>
      </Section>
    </div>
  );
}
