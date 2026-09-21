import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Snapshot } from "./types";

const snapshot: Snapshot = {
  session: {
    session_name: "night",
    state: "idle",
    frames_captured: 12,
    frames_failed: 0,
    sequence: 12,
    exposure_s: 8,
    gain: 220,
    sensor_temp_c: -5.5,
    level: 0.21,
    dark_applied: true,
    last_error: null,
    directory: "/tmp/night",
  },
  camera: {
    connected: true,
    info: {
      name: "ASI294MC Pro",
      camera_id: "0",
      backend: "asi",
      max_width: 4144,
      max_height: 2822,
      bit_depth: 14,
      is_color: true,
      bayer_pattern: "RGGB",
      pixel_size_um: 4.63,
      has_cooler: true,
      supported_bins: [1, 2],
    },
    controls: { gain: { min: 0, max: 570, default: 120, unit: "", writable: true, auto_supported: true } },
    values: { gain: 220 },
    roi: { x: 0, y: 0, width: 4144, height: 2822, bin: 1 },
  },
  scheduler: { enabled: true, in_window: false },
  jobs: [],
  ffmpeg: { available: true },
  config: {
    capture: {
      session_name: "night",
      interval_s: 30,
      frame_count: null,
      use_darks: true,
      auto_exposure: { enabled: true, target_level: 0.22 },
      camera: { backend: "asi", exposure_s: 8, gain: 220, bin: 1, offset: 30 },
      output: { directory: "sessions", format: "jpeg", stretch: { mode: "auto" }, overlay: { enabled: true, items: [] } },
    },
    schedule: { enabled: true, mode: "solar", latitude: 43, longitude: -2 },
    video: { codec: "h264", fps: 24, crf: 18 },
    darks: { exposure_rel_tol: 0.05 },
  },
  stats: { median: 5000, level: 0.21, saturated_fraction: 0.001, max: 65535 },
  live_view: true,
  live_requested: true,
  live_error: null,
  camera_connected: true,
  directories: { sessions: "/tmp/sessions", darks: "/tmp/darks" },
};

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "WebSocket",
      class {
        onmessage: ((event: { data: string }) => void) | null = null;
        onerror: (() => void) | null = null;
        onclose: (() => void) | null = null;
        constructor() {
          setTimeout(() => this.onmessage?.({ data: JSON.stringify(snapshot) }), 0);
        }
        close() {}
      },
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }),
    );
  });

  it("shows the camera and session state", async () => {
    render(<App />);
    expect(await screen.findByText("ASI294MC Pro")).toBeTruthy();
    expect(screen.getByText(/night: idle/)).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
  });

  it("renders every panel tab", async () => {
    render(<App />);
    await screen.findByText("ASI294MC Pro");
    for (const label of [
      "Capture",
      "Camera",
      "Output",
      "Overlay",
      "Darks",
      "Video",
      "Timelapses",
      "Schedule",
      "Logs",
    ]) {
      expect(screen.getByRole("button", { name: label })).toBeTruthy();
    }
  });

  it("hides expert fields until expert mode is on", async () => {
    render(<App />);
    await screen.findByText("ASI294MC Pro");
    expect(screen.queryByText("Priority")).toBeNull();
    (await screen.findByRole("switch", { name: "Expert mode" })).click();
    await waitFor(() => expect(screen.getByText("Priority")).toBeTruthy());
  });

  it("starts a recording from the header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    (await screen.findByRole("button", { name: "Start recording" })).click();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => call[0] === "/api/session/start")).toBe(true),
    );
  });

  it("stops the live preview from the header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    (await screen.findByRole("button", { name: "Stop live preview" })).click();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => call[0] === "/api/live/stop")).toBe(true),
    );
  });

  it("opens the captures folder from the header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    (await screen.findByRole("button", { name: "Open folder" })).click();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => call[0] === "/api/open-folder")).toBe(true),
    );
  });
});
