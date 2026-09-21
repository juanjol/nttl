import { Button, NumberInput, Row, Section, Select, TextInput, Toggle } from "../components/controls";
import { api } from "../api";
import { bool, num, str, type TabProps } from "./common";

export function CaptureTab({ snapshot, expert, update, busy }: TabProps) {
  const config = snapshot.config;
  const auto = bool(config, ["capture", "auto_exposure", "enabled"]);
  const running = snapshot.session.state === "running";

  return (
    <div>
      <Section title="Session">
        <Row label="Name">
          <TextInput
            value={str(config, ["capture", "session_name"], "session")}
            onChange={(value) => update(["capture", "session_name"], value)}
          />
        </Row>
        <Row label="Interval between frames (s)" hint="0 captures as fast as the camera allows">
          <NumberInput
            value={num(config, ["capture", "interval_s"])}
            min={0}
            step={0.5}
            onChange={(value) => update(["capture", "interval_s"], value)}
          />
        </Row>
        <Row label="Frame count" hint="Leave empty for unlimited">
          <NumberInput
            value={num(config, ["capture", "frame_count"])}
            min={0}
            onChange={(value) =>
              update(["capture", "frame_count"], value > 0 ? Math.round(value) : null)
            }
          />
        </Row>
        <Row label="Use dark library">
          <Toggle
            label="Use dark library"
            checked={bool(config, ["capture", "use_darks"], true)}
            onChange={(value) => update(["capture", "use_darks"], value)}
          />
        </Row>
      </Section>

      <Section title="Exposure">
        <Row label="Automatic exposure">
          <Toggle
            label="Automatic exposure"
            checked={auto}
            onChange={(value) => update(["capture", "auto_exposure", "enabled"], value)}
          />
        </Row>
        <Row label="Exposure (s)">
          <NumberInput
            value={num(config, ["capture", "camera", "exposure_s"], 1)}
            min={0.000032}
            step={0.1}
            disabled={auto}
            onChange={(value) => update(["capture", "camera", "exposure_s"], value)}
          />
        </Row>
        <Row label="Gain">
          <NumberInput
            value={num(config, ["capture", "camera", "gain"], 120)}
            min={0}
            disabled={auto}
            onChange={(value) => update(["capture", "camera", "gain"], value)}
          />
        </Row>
        {auto && (
          <>
            <Row label="Target level" hint="Median brightness of the frame, 0 to 1">
              <NumberInput
                value={num(config, ["capture", "auto_exposure", "target_level"], 0.22)}
                min={0.01}
                max={0.9}
                step={0.01}
                onChange={(value) => update(["capture", "auto_exposure", "target_level"], value)}
              />
            </Row>
            <Row label="Exposure limits (s)">
              <div className="flex gap-2">
                <NumberInput
                  value={num(config, ["capture", "auto_exposure", "min_exposure_s"], 0.001)}
                  min={0.000032}
                  step={0.01}
                  onChange={(value) =>
                    update(["capture", "auto_exposure", "min_exposure_s"], value)
                  }
                />
                <NumberInput
                  value={num(config, ["capture", "auto_exposure", "max_exposure_s"], 30)}
                  min={0.001}
                  step={1}
                  onChange={(value) =>
                    update(["capture", "auto_exposure", "max_exposure_s"], value)
                  }
                />
              </div>
            </Row>
            <Row label="Gain limits">
              <div className="flex gap-2">
                <NumberInput
                  value={num(config, ["capture", "auto_exposure", "min_gain"], 0)}
                  min={0}
                  onChange={(value) => update(["capture", "auto_exposure", "min_gain"], value)}
                />
                <NumberInput
                  value={num(config, ["capture", "auto_exposure", "max_gain"], 400)}
                  min={0}
                  onChange={(value) => update(["capture", "auto_exposure", "max_gain"], value)}
                />
              </div>
            </Row>
            {expert && (
              <>
                <Row label="Priority" expert hint="Which knob moves first when more light is needed">
                  <Select
                    value={str(config, ["capture", "auto_exposure", "priority"], "exposure")}
                    options={[
                      { value: "exposure", label: "Exposure first" },
                      { value: "gain", label: "Gain first" },
                    ]}
                    onChange={(value) => update(["capture", "auto_exposure", "priority"], value)}
                  />
                </Row>
                <Row label="Deadband" expert hint="No change while the error is inside this band">
                  <NumberInput
                    value={num(config, ["capture", "auto_exposure", "tolerance"], 0.03)}
                    min={0}
                    max={0.49}
                    step={0.005}
                    onChange={(value) => update(["capture", "auto_exposure", "tolerance"], value)}
                  />
                </Row>
                <Row label="Damping" expert hint="Below 1 reacts more slowly and smoothly">
                  <NumberInput
                    value={num(config, ["capture", "auto_exposure", "damping"], 0.7)}
                    min={0.05}
                    max={1}
                    step={0.05}
                    onChange={(value) => update(["capture", "auto_exposure", "damping"], value)}
                  />
                </Row>
                <Row label="Max change per frame" expert hint="Anti flicker ramp limit">
                  <NumberInput
                    value={num(config, ["capture", "auto_exposure", "max_change_factor"], 1.6)}
                    min={1.01}
                    max={16}
                    step={0.1}
                    onChange={(value) =>
                      update(["capture", "auto_exposure", "max_change_factor"], value)
                    }
                  />
                </Row>
                <Row label="Max gain step" expert>
                  <NumberInput
                    value={num(config, ["capture", "auto_exposure", "max_gain_step"], 40)}
                    min={1}
                    onChange={(value) =>
                      update(["capture", "auto_exposure", "max_gain_step"], value)
                    }
                  />
                </Row>
                <Row label="Saturation limit" expert hint="Fraction of clipped pixels tolerated">
                  <NumberInput
                    value={num(config, ["capture", "auto_exposure", "saturation_limit"], 0.02)}
                    min={0}
                    max={1}
                    step={0.005}
                    onChange={(value) =>
                      update(["capture", "auto_exposure", "saturation_limit"], value)
                    }
                  />
                </Row>
              </>
            )}
          </>
        )}
      </Section>

      <Section title="Control">
        <div className="flex gap-2 pt-1">
          <Button
            variant="primary"
            disabled={busy || running}
            onClick={() => void api.startSession()}
          >
            Start now
          </Button>
          <Button variant="danger" disabled={!running} onClick={() => void api.stopSession()}>
            Stop now
          </Button>
        </div>
      </Section>
    </div>
  );
}
