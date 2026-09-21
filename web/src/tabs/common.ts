import { getIn } from "../api";
import type { Json, Snapshot } from "../types";

export interface TabProps {
  snapshot: Snapshot;
  expert: boolean;
  update: (path: string[], value: unknown) => void;
  busy: boolean;
}

export function num(config: Json, path: string[], fallback = 0): number {
  const value = getIn(config, path);
  return typeof value === "number" ? value : fallback;
}

export function str(config: Json, path: string[], fallback = ""): string {
  const value = getIn(config, path);
  return typeof value === "string" ? value : fallback;
}

export function bool(config: Json, path: string[], fallback = false): boolean {
  const value = getIn(config, path);
  return typeof value === "boolean" ? value : fallback;
}

export function list<T>(config: Json, path: string[]): T[] {
  const value = getIn(config, path);
  return Array.isArray(value) ? (value as T[]) : [];
}
