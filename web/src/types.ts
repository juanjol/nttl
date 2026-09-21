export type Json = Record<string, unknown>;

export interface CameraInfo {
  name: string;
  camera_id: string | null;
  backend: string;
  max_width: number;
  max_height: number;
  bit_depth: number;
  is_color: boolean;
  bayer_pattern: string;
  pixel_size_um: number;
  has_cooler: boolean;
  supported_bins: number[];
}

export interface ControlRange {
  min: number;
  max: number;
  default: number;
  unit: string;
  writable: boolean;
  auto_supported: boolean;
}

export interface CameraState {
  connected: boolean;
  error?: string;
  info?: CameraInfo;
  controls?: Record<string, ControlRange>;
  values?: Record<string, number>;
  roi?: { x: number; y: number; width: number; height: number; bin: number };
}

export interface SessionStatus {
  session_name: string;
  state: "idle" | "running" | "finished" | "error";
  frames_captured: number;
  frames_failed: number;
  sequence: number;
  exposure_s: number;
  gain: number;
  sensor_temp_c: number | null;
  level: number | null;
  dark_applied: boolean;
  last_error: string | null;
  directory: string;
}

export interface JobInfo {
  id: string;
  name: string;
  state: string;
  progress: number;
  frames_done: number;
  frames_total: number;
  result: string | null;
  error: string | null;
}

export interface SchedulerState {
  enabled: boolean;
  in_window: boolean;
  night?: string | null;
  next_start?: string | null;
  next_end?: string | null;
  seconds_to_next_start?: number;
  seconds_to_end?: number;
  error?: string | null;
}

export interface FrameStatsView {
  median: number;
  level: number;
  saturated_fraction: number;
  max: number;
}

export interface Snapshot {
  session: SessionStatus;
  camera: CameraState;
  scheduler: SchedulerState;
  jobs: JobInfo[];
  ffmpeg: { available: boolean };
  config: Json;
  stats: FrameStatsView | null;
  live_view: boolean;
  live_requested?: boolean;
  live_error?: string | null;
  camera_connected?: boolean;
  directories?: { sessions: string; darks: string };
}

export interface CameraOption {
  camera_id: string;
  name: string;
  max_width: number;
  max_height: number;
  is_color: boolean;
  has_cooler: boolean;
}

export interface VideoEntry {
  session: string;
  name: string;
  path: string;
  size_bytes: number;
  modified_utc: string;
  url: string;
}

export interface LogEntry {
  id: number;
  time: string;
  level: string;
  logger: string;
  message: string;
}

export interface OverlayPreset {
  name: string;
  items: Record<string, unknown>[];
}

export interface SessionEntry {
  name: string;
  frames: number;
  path: string;
  first_frame_utc: string | null;
  last_frame_utc: string | null;
  videos: string[];
}

export interface DarkEntryView {
  name: string;
  exposure_s: number;
  gain: number;
  offset: number;
  sensor_temp_c: number;
  bin: number;
  width: number;
  height: number;
  frames: number;
  created_at: string;
}
