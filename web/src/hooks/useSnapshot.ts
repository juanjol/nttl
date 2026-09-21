import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Snapshot } from "../types";

export function useSnapshot(intervalMs = 1000) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .snapshot()
      .then((value) => !cancelled && setSnapshot(value))
      .catch((exc: Error) => !cancelled && setError(exc.message));

    let timer: number | undefined;
    const startPolling = () => {
      timer = window.setInterval(() => {
        api
          .snapshot()
          .then((value) => setSnapshot(value))
          .catch((exc: Error) => setError(exc.message));
      }, intervalMs);
    };

    try {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${protocol}://${window.location.host}/api/ws`);
      socket.current = ws;
      ws.onmessage = (event) => {
        setSnapshot(JSON.parse(event.data as string) as Snapshot);
        setError(null);
      };
      ws.onerror = () => startPolling();
      ws.onclose = () => startPolling();
    } catch {
      startPolling();
    }

    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
      socket.current?.close();
    };
  }, [intervalMs]);

  return { snapshot, error };
}
