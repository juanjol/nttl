import type { DarkEntryView, JobInfo, SessionEntry, Snapshot } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: init?.body ? { "content-type": "application/json" } : undefined,
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = (body as { detail?: string }).detail ?? detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  snapshot: () => request<Snapshot>("/api/state"),
  patchConfig: (patch: unknown) =>
    request<Record<string, unknown>>("/api/config", {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  setControl: (name: string, value: number) =>
    request<{ name: string; value: number }>("/api/camera/control", {
      method: "POST",
      body: JSON.stringify({ name, value }),
    }),
  setCooler: (enabled: boolean, target_c: number) =>
    request<unknown>("/api/camera/cooler", {
      method: "POST",
      body: JSON.stringify({ enabled, target_c }),
    }),
  startSession: (overrides?: Record<string, unknown>) =>
    request<unknown>("/api/session/start", {
      method: "POST",
      body: JSON.stringify({ overrides: overrides ?? null }),
    }),
  stopSession: () => request<unknown>("/api/session/stop", { method: "POST" }),
  sessions: () => request<{ sessions: SessionEntry[] }>("/api/sessions"),
  compile: (session: string, video?: Record<string, unknown>) =>
    request<JobInfo>("/api/compile", {
      method: "POST",
      body: JSON.stringify({ session, video: video ?? null }),
    }),
  darks: () => request<{ darks: DarkEntryView[] }>("/api/darks"),
  buildDarks: (exposure_s: number, gain: number, frames: number) =>
    request<JobInfo>("/api/darks", {
      method: "POST",
      body: JSON.stringify({ exposure_s, gain, frames }),
    }),
  deleteDark: (name: string) =>
    request<unknown>(`/api/darks/${encodeURIComponent(name)}`, { method: "DELETE" }),
  updateSchedule: (patch: Record<string, unknown>) =>
    request<unknown>("/api/schedule", { method: "PUT", body: JSON.stringify(patch) }),
};

export function setIn(target: unknown, path: string[], value: unknown): Record<string, unknown> {
  const [head, ...rest] = path;
  const base = (target ?? {}) as Record<string, unknown>;
  if (rest.length === 0) {
    return { ...base, [head]: value };
  }
  return { ...base, [head]: setIn(base[head], rest, value) };
}

export function getIn(target: unknown, path: string[]): unknown {
  return path.reduce<unknown>(
    (value, key) => (value == null ? undefined : (value as Record<string, unknown>)[key]),
    target,
  );
}

export function patchFor(path: string[], value: unknown): Record<string, unknown> {
  return setIn({}, path, value);
}
