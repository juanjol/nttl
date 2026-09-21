import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, NumberInput, Row, Section, Select, TextInput, Toggle } from "../components/controls";
import type { OverlayPreset } from "../types";
import { bool, list, num, str, type TabProps } from "./common";

function templateOf(item: { template?: unknown }): string {
  return String(item.template ?? "");
}

interface OverlayItem {
  template: string;
  position: string;
  font_size: number;
  color: string;
  opacity: number;
  background: string | null;
}

const POSITIONS = [
  { value: "top_left", label: "Top left" },
  { value: "top_right", label: "Top right" },
  { value: "bottom_left", label: "Bottom left" },
  { value: "bottom_right", label: "Bottom right" },
];

const TOKENS = [
  "{date}",
  "{time}",
  "{datetime}",
  "{date_utc}",
  "{time_utc}",
  "{exp}",
  "{gain}",
  "{offset}",
  "{sensor_temp}",
  "{seq}",
  "{camera}",
  "{bin}",
  "{bayer}",
];

const DEFAULT_ITEM: OverlayItem = {
  template: "{datetime}",
  position: "bottom_left",
  font_size: 18,
  color: "#ffffff",
  opacity: 1,
  background: null,
};

const PRESET_LABELS: Record<string, string> = {
  none: "No text",
  timestamp: "Date and time",
  standard: "Date, exposure and gain",
  detailed: "Everything (camera, frame, exposure)",
};

export function OverlayTab({ snapshot, expert, update }: TabProps) {
  const config = snapshot.config;
  const path = ["capture", "output", "overlay"];
  const items = list<OverlayItem>(config, [...path, "items"]);
  const [presets, setPresets] = useState<OverlayPreset[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .overlayPresets()
      .then((body) => !cancelled && setPresets(body.presets))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const matching = presets.find(
    (preset) => JSON.stringify(preset.items.map(templateOf)) === JSON.stringify(items.map(templateOf)),
  );

  const setItems = (next: OverlayItem[]) => update([...path, "items"], next);
  const patchItem = (index: number, patch: Partial<OverlayItem>) =>
    setItems(items.map((item, position) => (position === index ? { ...item, ...patch } : item)));

  return (
    <div>
      <Section title="Overlay">
        <Row label="Draw information on the frames">
          <Toggle
            label="Overlay enabled"
            checked={bool(config, [...path, "enabled"], true)}
            onChange={(value) => update([...path, "enabled"], value)}
          />
        </Row>
        {expert && (
          <Row label="Margin and line spacing" expert>
            <div className="flex gap-2">
              <NumberInput
                value={num(config, [...path, "margin"], 8)}
                min={0}
                onChange={(value) => update([...path, "margin"], value)}
              />
              <NumberInput
                value={num(config, [...path, "line_spacing"], 4)}
                min={0}
                onChange={(value) => update([...path, "line_spacing"], value)}
              />
            </div>
          </Row>
        )}
        {expert && (
          <Row label="Font file" expert hint="Leave empty to use the bundled sans serif">
            <TextInput
              value={str(config, [...path, "font_path"])}
              onChange={(value) => update([...path, "font_path"], value.length ? value : null)}
            />
          </Row>
        )}
      </Section>

      <Section title="Template">
        <Row label="Predefined layout" hint="Pick one and tune the texts below if you want">
          <Select
            value={matching?.name ?? "custom"}
            options={[
              ...presets.map((preset) => ({
                value: preset.name,
                label: PRESET_LABELS[preset.name] ?? preset.name,
              })),
              { value: "custom", label: "Custom" },
            ]}
            onChange={(value) => {
              const preset = presets.find((entry) => entry.name === value);
              if (preset) setItems(preset.items as unknown as OverlayItem[]);
            }}
          />
        </Row>
      </Section>

      <Section title="Items">
        {items.map((item, index) => (
          <div key={index} className="mb-3 rounded-md border border-edge bg-panel-soft/60 p-2">
            <Row label={`Text ${index + 1}`}>
              <TextInput
                value={item.template}
                onChange={(value) => patchItem(index, { template: value })}
              />
            </Row>
            <div className="grid grid-cols-2 gap-2">
              <Row label="Position">
                <Select
                  value={item.position}
                  options={POSITIONS}
                  onChange={(value) => patchItem(index, { position: value })}
                />
              </Row>
              <Row label="Font size">
                <NumberInput
                  value={item.font_size}
                  min={6}
                  max={200}
                  onChange={(value) => patchItem(index, { font_size: Math.round(value) })}
                />
              </Row>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Row label="Colour">
                <input
                  type="color"
                  className="h-9 w-full rounded-md border border-edge bg-panel-soft"
                  value={item.color}
                  onChange={(event) => patchItem(index, { color: event.target.value })}
                />
              </Row>
              <Row label="Background">
                <div className="flex items-center gap-2">
                  <Toggle
                    label="Background"
                    checked={Boolean(item.background)}
                    onChange={(value) => patchItem(index, { background: value ? "#000000" : null })}
                  />
                  {item.background && (
                    <input
                      type="color"
                      className="h-9 w-16 rounded-md border border-edge bg-panel-soft"
                      value={item.background}
                      onChange={(event) => patchItem(index, { background: event.target.value })}
                    />
                  )}
                </div>
              </Row>
            </div>
            <div className="flex justify-end">
              <Button
                variant="danger"
                onClick={() => setItems(items.filter((_, position) => position !== index))}
              >
                Remove
              </Button>
            </div>
          </div>
        ))}
        <Button onClick={() => setItems([...items, { ...DEFAULT_ITEM }])}>Add text</Button>
      </Section>

      <Section title="Available tokens">
        <div className="flex flex-wrap gap-1 text-xs text-slate-400">
          {TOKENS.map((token) => (
            <code key={token} className="rounded bg-panel-soft px-1.5 py-0.5">
              {token}
            </code>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Numbers accept format specifiers, for example {"{sensor_temp:+.2f}"}.
        </p>
      </Section>
    </div>
  );
}
